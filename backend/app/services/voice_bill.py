"""A bill told out loud: the lines and who had them, said in one go. Pro only.

The recording is turned into words and dropped — nothing of it is kept. The
words and the bill as it stands go to the model that reads receipts, and its
answer is applied the way a hand edit is: in one transaction under the bill's
lock. A line whose change would move what somebody already paid is left as it
was and named back, so one paid guest does not stop the rest of what was said.

Synchronous on purpose: the Mini App's endpoint runs it in the request's
thread, the bot in the thread of the update it is handling.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException, UploadFile

from app.models import Bill, BillItem, BillItemAssignment, BillUser, SplitType
from app.notifier import notifier
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.app_settings import get_receipt_model
from app.services.bill_core_service import MAX_EXPECTED_PEOPLE
from app.services.bill_item_service import BillItemService
from app.services.bill_summary import seat_name
from app.services.llm import get_openai_client
from app.services.places import place_named
from app.services.validator import BillValidator
from app.utils.currency import from_tiins, to_tiins

logger = logging.getLogger(__name__)

DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-transcribe"
# Each call to OpenAI, with no retry: the two together stay under the 90 s the
# app waits, so nothing is applied after it gave up, and a slow OpenAI holds a
# bot slot this long, not the client's default ten minutes three times over.
OPENAI_TIMEOUT = 40
# A couple of minutes in any format a phone records; a bill is said in far less.
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_TEXT = 2000
MAX_NAME = 80
MAX_TITLE = 120
# A misheard «сто» must not lay a hundred plates on the receipt.
MAX_COUNT = 99
# What the browsers record into, by what they call it, as OpenAI names the format.
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}
CHANGES = ("set", "add", "remove")
# The speaker, said as a word rather than the id the model was given.
SPEAKER = {"я", "мне", "меня", "мной", "i", "me", "myself", "men", "menga", "meni"}


@dataclass
class Told:
    heard: str
    added: int = 0
    assigned: int = 0
    titled: bool = False
    placed: bool = False
    # Lines left as they were: changing them would move a share already paid.
    held: list[str] = field(default_factory=list)
    # Names said that no seat could be found or laid for.
    unseated: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.assigned or self.titled or self.placed)


def refused(status_code: int, code: str, **context) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **context})


def transcribe_model() -> str:
    return os.getenv("OPENAI_TRANSCRIBE_MODEL", "").strip() or DEFAULT_TRANSCRIBE_MODEL


def recording(upload: UploadFile) -> tuple[bytes, str]:
    """The bytes of an uploaded recording and a file name whose extension tells
    OpenAI the format; the codec in «audio/webm;codecs=opus» says nothing it needs."""
    extension = AUDIO_EXTENSIONS.get((upload.content_type or "").split(";")[0].strip().lower())
    if extension is None:
        raise refused(400, "VOICE_FORMAT")
    raw = upload.file.read(MAX_AUDIO_BYTES + 1)
    if len(raw) > MAX_AUDIO_BYTES:
        raise refused(413, "VOICE_TOO_LONG")
    return raw, f"voice.{extension}"


def _number(value) -> float | None:
    # JSON's true is an int to Python, and never a price or a count.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _id(value) -> int | None:
    """An id the model wrote as a number or as digits in a string."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    number = _number(value)
    return int(number) if isinstance(number, int) else None


def _default_labels(seat: BillUser) -> list[str]:
    """What the app and the bot call a seat nobody has named: «Гость 2»."""
    return [f"Гость {seat.seat_index}", f"Guest {seat.seat_index}", f"{seat.seat_index}-mehmon"]


def _seat_label(seat: BillUser, owner_id: int) -> str:
    if seat.user_id == owner_id:
        return "the speaker"
    return seat_name(seat) or " / ".join(f"«{label}»" for label in _default_labels(seat)) + ", no name yet"


def _names_of(seat: BillUser) -> set[str]:
    """What a seat may be called out loud: its name, or its @username."""
    names = {(seat_name(seat) or "").casefold()}
    if seat.user is not None and seat.user.username:
        names.add(seat.user.username.casefold())
    if seat.user_id is None and not seat.guest_name:
        names |= {label.casefold() for label in _default_labels(seat)}
    return names - {""}


def _plates(item: BillItem) -> dict[int, set[int]]:
    """Who has each portion of a line, by seat id."""
    count = max(1, item.count or 1)
    plates: dict[int, set[int]] = {portion: set() for portion in range(count)}
    for assignment in item.assignments:
        if assignment.portion_index in plates:
            plates[assignment.portion_index].add(assignment.participant_id)
    return plates


def _hint(items: list[BillItem], seats: list[BillUser]) -> str:
    """The dishes and names already on the bill, so they are spelled as written there."""
    names = [item.name for item in items] + [name for seat in seats if (name := seat_name(seat))]
    return ", ".join(names)[:500]


def _prompt(bill: Bill, items: list[BillItem], seats: list[BillUser], words: str) -> str:
    labels = {seat.id: _seat_label(seat, bill.owner_id) for seat in seats}
    lines = [
        f"#{item.id} {item.name} ×{item.count} = {from_tiins(item.item_sum):g}"
        + (" (whole table)" if item.is_shared_globally else "")
        + " — "
        + (", ".join(sorted({labels[a.participant_id] for a in item.assignments if a.participant_id in labels})) or "nobody yet")
        for item in items
    ]
    people = [f"{seat.id}: {labels[seat.id]}" for seat in seats]
    speaker = next((seat.id for seat in seats if seat.user_id == bill.owner_id), None)
    me = f"the speaker («я», «мне», «me», «men») is {speaker}. " if speaker else ""
    money = (
        "Amounts are in Uzbek sum, and people say prices in thousands: «восемьдесят» or «80» "
        "for a dish means 80000."
        if bill.currency == "uzs"
        else f"Amounts are in {bill.currency.upper()}."
    )
    return (
        "The host of a restaurant bill said what was ordered and who had it. Turn it into "
        "changes to the bill, as JSON of the shape "
        '{"title": string|null, "place": string|null, '
        '"items": [{"ref": string, "name": string, "count": number, "amount": number, '
        '"is_shared_globally": boolean}], '
        '"assign": [{"item": number|string, "people": [number|string], "portions": number|null, '
        '"everyone": boolean, "change": "set"|"add"|"remove"}]}.\n\n'
        f"{money}\n\n"
        "RULES:\n"
        "1. `items` are lines to ADD: only what was said and is not on the bill yet. A dish that "
        "matches a line already on the bill by meaning (another spelling, a short name) is that "
        "line, not a new one. `ref` is your own label for a new line (\"n1\", \"n2\"…) so `assign` "
        "can point at it. Keep names in the language they were said.\n"
        "2. `amount` is the line total for the whole `count` (unit price × count): «две пиццы по 80» "
        "is count 2, amount 160000. No price said: amount 0.\n"
        "3. A service charge, tip or discount said as a percent is a line of its own with "
        "`is_shared_globally`: true, worked out from the lines that are not shared (on the bill and "
        "new); a discount is negative.\n"
        "4. `assign` says who had a line, only for lines whose eaters were said. `item` is a line's "
        f"#id from the bill or a `ref` from `items`. `people` are ids from PEOPLE; {me}Someone "
        "named who is not in PEOPLE is their name as a string, in the nominative («Ане» → «Аня»).\n"
        "5. `change`: \"set\" when what was said is who had the line — it replaces whoever has it "
        "now; \"add\" when someone had it as well («Аня тоже ела пиццу», «ещё одно пиво Борису») — "
        "the others keep theirs; \"remove\" when someone did not have it («Борис не ел салат»).\n"
        "6. People sharing a line are one entry with all of them and `portions`: null. A line split "
        "by units («два пива: одно мне, одно Борису») is one entry per group, `portions` being how "
        "many units that group had. «Всё», «все блюда», «всё пополам» cover every line: one entry "
        "for each.\n"
        "7. `everyone`: true, with `people` empty, when a line is for the whole table («на всех», "
        "«общее»). «На всех, кроме Бориса» is `everyone`: true with `people`: [Борис] and "
        "`change`: \"remove\".\n"
        "8. Match a name to PEOPLE by who it is, not by spelling: a pet or short name, another "
        "alphabet or the first name alone is the same person (Аня = Анна = Anna Petrova). A name "
        "that could be either of two people in PEOPLE: leave that entry out.\n"
        "9. `place`: the venue's name as guests know it when it was said, without «кафе» or "
        "«ресторан» («мы в кафе Рейхан» → «Рейхан»), else null. `title`: a short name for the bill "
        "when the occasion was said («ужин в Рыбе» → «Ужин в Рыбе»), else null.\n"
        "10. Never invent lines, prices or people that were not said. Nothing to change: both "
        "lists empty.\n\n"
        "LINES ON THE BILL:\n" + ("\n".join(lines) or "none yet") + "\n\n"
        "PEOPLE:\n" + "\n".join(people) + "\n\n"
        f"WHAT THEY SAID:\n{words}"
    )


class VoiceBillService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def _open_bill(self, bill_id: int) -> Bill:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        return bill

    def hear(self, bill_id: int | None, audio: bytes, name: str) -> str:
        """The words of a recording. The dishes and names of the bill it is
        meant for, when there is one already, help spell them."""
        hint = ""
        if bill_id is not None:
            self._open_bill(bill_id)
            hint = _hint(
                self.bill_repo.get_items_by_bill_id(bill_id),
                self.bill_repo.get_participants_by_bill_id(bill_id),
            )
        # No transaction stays open while OpenAI works.
        self.bill_repo.session.rollback()
        try:
            result = get_openai_client().with_options(timeout=OPENAI_TIMEOUT, max_retries=0).audio.transcriptions.create(
                model=transcribe_model(), file=(name, audio), prompt=hint,
            )
        except Exception:
            logger.exception(f"Bill {bill_id}: could not transcribe the recording")
            raise refused(502, "VOICE_FAILED")
        return (result.text or "").strip()

    def tell(self, bill_id: int, words: str) -> Told:
        """Apply what was said. Nothing changed and nothing to say why is a 422
        that carries what was heard."""
        heard = (words or "").strip()[:MAX_TEXT]
        if not heard:
            raise refused(422, "VOICE_EMPTY")
        bill = self._open_bill(bill_id)
        prompt = _prompt(
            bill,
            self.bill_repo.get_items_by_bill_id(bill_id),
            self.bill_repo.get_participants_by_bill_id(bill_id),
            heard,
        )
        model = get_receipt_model(self.bill_repo.session)
        # No transaction stays open while the model thinks; the bill is read
        # again under its lock to apply the answer.
        self.bill_repo.session.rollback()
        try:
            changes = self._understand(prompt, model)
        except Exception:
            logger.exception(f"Bill {bill_id}: could not understand what was said")
            raise refused(502, "VOICE_FAILED")
        # What the model made of it, as the receipt worker logs its parse: a
        # line nobody was handed is otherwise impossible to tell apart.
        logger.info("Bill %s: voice heard %r, understood %s", bill_id, heard, json.dumps(changes, ensure_ascii=False))

        told = self.apply(bill_id, changes, heard)
        if not told.changed and not told.held and not told.unseated:
            raise refused(422, "VOICE_NOTHING", heard=heard)
        return told

    @staticmethod
    def _understand(prompt: str, model: str) -> dict:
        response = get_openai_client().with_options(timeout=OPENAI_TIMEOUT, max_retries=0).chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You keep a restaurant bill for the host. You turn what they say into "
                        "changes to it as one JSON object, and you re-check your arithmetic."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        changes = json.loads(response.choices[0].message.content)
        if not isinstance(changes, dict):
            raise ValueError("The model answered with something other than an object")
        return changes

    def apply(self, bill_id: int, changes: dict, heard: str = "") -> Told:
        """Add the new lines, name the bill if it has no name, and hand out the
        lines whose eaters were said. Every seat's share is left as it was
        unless what was said is about it."""
        session = self.bill_repo.session
        items_service = BillItemService(self.bill_repo, self.user_repo)
        told = Told(heard)
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            self.validator.ensure_bill_open(bill)
            paid_before = items_service._paid_allocations(bill_id)
            paid = set(paid_before)
            lines = {item.id: item for item in self.bill_repo.get_items_by_bill_id(bill_id)}
            seats = self.bill_repo.get_participants_by_bill_id(bill_id)
            hand_split = bill.split_type != SplitType.BY_ITEMS and any(seat.allocated_amount for seat in seats)

            added: list[BillItem] = []
            refs: dict[str, BillItem] = {}
            for said in changes.get("items") or []:
                item = self._new_line(bill_id, said) if isinstance(said, dict) else None
                if item is None:
                    continue
                if item.is_shared_globally and paid:
                    # Shared, it would take a part from everyone, the paid too:
                    # it goes on the bill for the host to hand out.
                    item.is_shared_globally = False
                    told.held.append(item.name)
                session.add(item)
                added.append(item)
                refs.setdefault(str(said.get("ref")), item)
            session.flush()

            title = changes.get("title")
            if isinstance(title, str) and title.strip() and not bill.title:
                bill.title = title.strip()[:MAX_TITLE]
                if not bill.place_by_owner:
                    # The new title may name the place: the labeling job asks again.
                    bill.place_checked_at = None
                told.titled = True

            place = " ".join(str(changes.get("place") or "").split())
            if place:
                # Said by the owner, so it is theirs: the labeling job leaves it be.
                bill.place_id = place_named(session, place).id
                bill.place_checked_at = datetime.utcnow()
                bill.place_by_owner = True
                told.placed = True

            # A line pointed at by its name rather than its ref or id; a new one wins.
            named = {item.name.casefold(): item for item in [*lines.values(), *added]}
            told_lines: dict[int, list[dict]] = {}
            for said in changes.get("assign") or []:
                if not isinstance(said, dict):
                    continue
                ref = said.get("item")
                item = refs.get(str(ref)) or lines.get(_id(ref)) or named.get(str(ref).strip().casefold())
                if item is not None:
                    told_lines.setdefault(item.id, []).append(said)
            by_id = {**lines, **{item.id: item for item in added}}

            for item_id, entries in told_lines.items():
                item = by_id[item_id]
                before = _plates(item)
                shared, plates = self._hand_out(item, entries, bill, seats, paid, by_id, told)
                if shared == item.is_shared_globally and (shared or plates == before):
                    continue
                if shared != item.is_shared_globally:
                    # Shared or no longer: every seat's part of it moves.
                    touched = {seat.id for seat in seats}
                else:
                    touched = set().union(*(before[p] | plates[p] for p in plates if before[p] != plates[p]))
                # On a bill split by hand, any hand-out turns it into a split by
                # dishes, which takes the hand-set shares away, the paid ones too.
                if touched & paid or (hand_split and paid):
                    if item.name not in told.held:
                        told.held.append(item.name)
                    continue
                for assignment in list(item.assignments):
                    session.delete(assignment)
                session.flush()
                session.expire(item, ["assignments"])
                for portion, eaters in plates.items():
                    for participant_id in eaters:
                        session.add(BillItemAssignment(
                            bill_item_id=item.id, participant_id=participant_id, portion_index=portion,
                        ))
                item.is_shared_globally = shared
                told.assigned += 1

            told.added = len(added)
            if not told.changed:
                # A seat named for nothing must not keep the name either.
                session.rollback()
                return told
            session.flush()
            for item in by_id.values():
                session.expire(item, ["assignments"])
            # Lines on a bill split it by who had what, as after a scan — but
            # shares set by hand stay until a line is handed out over them.
            if told.assigned or not hand_split:
                bill.split_type = SplitType.BY_ITEMS
            session.add(bill)
            items_service._recompute_totals_from_items(bill_id, commit=False)
            # What was held back above should leave nothing paid to move; this
            # is the same guard every edit of a bill ends with.
            items_service._ensure_paid_allocations_unchanged(bill_id, paid_before)
            session.commit()
        except Exception:
            session.rollback()
            raise

        notifier.broadcast(bill_id, "REFRESH")
        return told

    def _hand_out(
        self,
        item: BillItem,
        entries: list[dict],
        bill: Bill,
        seats: list[BillUser],
        paid: set[int],
        by_id: dict[int, BillItem],
        told: Told,
    ) -> tuple[bool, dict[int, set[int]]]:
        """Whether the line ends up shared by the table, and who has each of
        its portions, once what was said about it is played over what is there."""
        count = max(1, item.count or 1)
        shared = item.is_shared_globally
        plates = _plates(item)
        cleared = False
        cursor = 0
        for entry in entries:
            change = entry.get("change") if entry.get("change") in CHANGES else "set"
            # A new seat changes every share of a line the table shares; that
            # is a paid share moving as much as any other.
            may_seat = not paid or not any(line.is_shared_globally for line in by_id.values())
            eaters = {
                seat.id
                for who in entry.get("people") or []
                if (seat := self._seat_for(who, bill, seats, may_seat, told)) is not None
            }
            if entry.get("everyone") is True:
                shared = True
                plates = {portion: set() for portion in range(count)}
                if change != "remove":
                    continue
            if change == "remove":
                if shared:
                    # «Everyone but …»: the rest of the table has it.
                    shared = False
                    plates = {portion: {seat.id for seat in seats} for portion in range(count)}
                for portion in plates:
                    plates[portion] -= eaters
                continue
            if not eaters:
                continue
            units = _number(entry.get("portions"))
            units = int(units) if units is not None and units >= 1 else None
            if change == "add":
                if shared:
                    continue  # the whole table has it already
                if units is None:
                    portions = list(range(count))
                else:
                    # Portions nobody has first; past those, the last ones are shared.
                    free = [p for p in range(count) if not plates[p]]
                    taken = [p for p in reversed(range(count)) if plates[p]]
                    portions = (free + taken)[:units]
            else:
                if shared or not cleared:
                    # What was said is who had it: whoever had it before goes.
                    shared = False
                    plates = {portion: set() for portion in range(count)}
                    cleared = True
                    cursor = 0
                if units is None:
                    portions = list(range(count))
                else:
                    portions = list(range(cursor, min(count, cursor + units)))
                    cursor += units
            for portion in portions:
                plates[portion] |= eaters
        return shared, plates

    @staticmethod
    def _new_line(bill_id: int, said: dict) -> BillItem | None:
        name = str(said.get("name") or "").strip()[:120]
        if not name:
            return None
        count = int(min(MAX_COUNT, max(1, _number(said.get("count")) or 1)))
        item_sum = to_tiins(_number(said.get("amount")) or 0)
        return BillItem(
            bill_id=bill_id,
            name=name,
            price=item_sum // count,
            count=count,
            item_sum=item_sum,
            # A discount belongs to the whole table, as on a scanned receipt.
            is_shared_globally=said.get("is_shared_globally") is True or item_sum < 0,
        )

    def _seat_for(self, who, bill: Bill, seats: list[BillUser], may_seat: bool, told: Told) -> BillUser | None:
        """A seat by its id, or by a name said: the one person at the table
        called that, else the first guest seat with no name yet, else a new one
        at the end of the table. A name that fits two people gets neither."""
        if (seat_id := _id(who)) is not None:
            return next((seat for seat in seats if seat.id == seat_id), None)
        if not isinstance(who, str) or not who.strip():
            return None
        name = who.strip()[:MAX_NAME]
        key = name.casefold().lstrip("@")
        if key in SPEAKER:
            return next((seat for seat in seats if seat.user_id == bill.owner_id), None)
        same = [seat for seat in seats if key in _names_of(seat)]
        if not same:
            # «Anna» for «Anna Petrova».
            same = [seat for seat in seats if (seat_name(seat) or "").casefold().split()[:1] == [key]]
        if len(same) == 1:
            return same[0]
        seat = None if same else next((s for s in seats if s.user_id is None and not s.guest_name), None)
        if seat is None:
            if same or not may_seat or len(seats) >= MAX_EXPECTED_PEOPLE:
                if name not in told.unseated:
                    told.unseated.append(name)
                return None
            seat = BillUser(
                bill_id=bill.id,
                seat_index=max((s.seat_index for s in seats), default=-1) + 1,
                allocated_amount=0,
            )
            seats.append(seat)
            bill.expected_people = max(bill.expected_people or 0, len(seats))
        seat.guest_name = name
        self.bill_repo.session.add(seat)
        self.bill_repo.session.flush()
        return seat
