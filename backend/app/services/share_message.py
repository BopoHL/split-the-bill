"""The text and buttons of a shared bill.

Telegram draws the ticket picture (see share_card) as the link preview above
this text. The picture shows who took which dishes, the total and how much is
paid; the text carries what has to be copied — each person's amount, the card
number — and the dishes nobody has taken yet. Both are built from the same summary, and the summary's
fingerprint versions the picture URL: Telegram keeps a preview per URL, so a
new state needs a new address — and so does a face that could not be drawn
before and can be now.
"""
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from html import escape

from app.services.bill_summary import BillSummary, SummaryLine, SummarySeat
from app.services.drawing import DEFAULT_THEME
from app.utils.bot_copy import t
from app.utils.currency import currency_symbol, format_amount, format_number
from app.utils.keyboard import in_pairs
from app.utils.telegram_html import TEXT_LIMIT, visible_length

REFRESH_PREFIX = "share_refresh:"
SEAT_PREFIX = "share_seat:"
PAID_PREFIX = "share_paid:"
# A few free seats under the post, in seat order; the rest are taken in the app.
SEAT_BUTTONS = 6
# The most a copy button may put on the clipboard.
COPY_LIMIT = 256


class PostKind(str, Enum):
    """Who a post is for, which decides what its buttons may do."""

    # Shared into a chat: anyone there may take a free seat.
    GROUP = "group"
    # Shared to one person, for the seat its link is for.
    SEAT = "seat"
    # Sent by the bot to someone already on their seat.
    DIRECT = "direct"
    # Sent by the bot for the sharer to forward: nothing on it acts for anyone.
    FORWARD = "forward"
    # A reminder to one person on their seat: their dishes, their share, the card.
    REMINDER = "reminder"


def bare_details(details: str) -> str:
    """A card number as bare digits — what Telegram recognises as a card in
    a text and what a bank app takes pasted; anything else as written."""
    digits = re.sub(r"[\s-]", "", details)
    return digits if digits.isdigit() else details.strip()


def seat_label(seat: SummarySeat, language: str) -> str:
    return seat.name or t(language, "share_guest").format(n=seat.seat_index)


@dataclass(frozen=True)
class ShareMessage:
    html: str
    buttons: list[list[dict]]
    preview_url: str | None
    fingerprint: str
    title: str
    description: str
    # A closed bill's message is its last word: nothing will change it again.
    is_final: bool

    @property
    def link_preview(self) -> dict:
        if not self.preview_url:
            return {"is_disabled": True}
        return {"url": self.preview_url, "prefer_large_media": True, "show_above_text": True}

    @property
    def reply_markup(self) -> dict:
        return {"inline_keyboard": self.buttons}


def fingerprint(
    summary: BillSummary, language: str, faces: frozenset[int] = frozenset(), theme: str = DEFAULT_THEME
) -> str:
    """`faces`: the Telegram ids whose photos the picture will show."""
    return hashlib.sha256(f"{language}|{theme}|{summary!r}|{sorted(faces)}".encode()).hexdigest()[:16]


class _Writer:
    def __init__(self, summary: BillSummary, language: str):
        self.summary = summary
        self.language = language

    def copy(self, key: str, **values) -> str:
        return escape(t(self.language, key).format(**values))

    def amount(self, tiins: int) -> str:
        return escape(format_amount(tiins, self.summary.currency, self.language))

    def payable(self, tiins: int) -> str:
        """An amount someone will pay: tapping the monospace figure copies it,
        bare, the way a banking app takes it."""
        currency = escape(currency_symbol(self.summary.currency, self.language))
        return f"<code>{format_number(tiins, grouped=False)}</code> {currency}".rstrip()

    def name(self, seat: SummarySeat) -> str:
        return escape(seat_label(seat, self.language))

    def dish(self, line: SummaryLine) -> str:
        label = escape(line.name)
        return f"{label} {line.count}" if line.count else label

    def payment_details(self, details: str) -> str:
        return escape(bare_details(details))

    def seat(self, seat: SummarySeat) -> str:
        paid = " ✅" if seat.is_paid else ""
        return f"<b>{self.name(seat)}</b>{paid} — {self.payable(seat.amount)}"

    def unassigned(self, limit: int | None) -> list[str]:
        summary = self.summary
        lines = summary.unassigned if limit is None else summary.unassigned[:limit]
        rows = [f"{self.dish(line)} — {self.amount(line.amount)}" for line in lines]
        if len(lines) < len(summary.unassigned):
            rows.append(self.copy("share_more_dishes", n=len(summary.unassigned) - len(lines)))
        # Folded to a few lines: what nobody has taken is a to-do, not the news.
        folded = [f"<blockquote expandable>{chr(10).join(rows)}</blockquote>"] if rows else []
        return [f"📌 <b>{self.copy('share_unassigned')}</b>", *folded]

    def text(self, seat_limit: int | None, unassigned_limit: int | None, intro: str | None = None) -> str:
        summary = self.summary
        blocks = [[intro]] if intro else []
        # The bill's name is on the picture right above.
        if summary.is_closed:
            blocks.append([f"🔒 {self.copy('share_closed')}"])

        seats = summary.seats if seat_limit is None else summary.seats[:seat_limit]
        people = [self.seat(seat) for seat in seats]
        if len(seats) < len(summary.seats):
            people.append(self.copy("share_more_people", n=len(summary.seats) - len(seats)))
        if not summary.seats:
            people.append(f"<i>{self.copy('share_nobody_yet')}</i>")
        # The list of people, the post's main part, stands a line apart from
        # its heading; the short blocks after it sit right under theirs.
        blocks.append([f"👥 <b>{self.copy('share_people')}</b>", "", *people])

        if summary.unassigned_total > 0:
            blocks.append(self.unassigned(unassigned_limit))
        if summary.payment_details and not summary.is_closed:
            blocks.append([
                f"💳 <b>{self.copy('share_payment_details')}</b>", self.payment_details(summary.payment_details),
            ])
        return "\n\n".join("\n".join(block) for block in blocks)

    def reminder(self, seat: SummarySeat, line_limit: int | None) -> str:
        summary = self.summary
        title = summary.title or t(self.language, "bill_untitled")
        blocks = [[f"🔔 <b>{self.copy('remind_title')}</b>", self.copy("remind_intro", title=title)]]
        if summary.is_closed:
            blocks.append([f"🔒 {self.copy('share_closed')}"])

        lines = seat.lines if line_limit is None else seat.lines[:line_limit]
        if lines:
            rows = [self.own_dish(line) for line in lines]
            if len(lines) < len(seat.lines):
                rows.append(self.copy("share_more_dishes", n=len(seat.lines) - len(lines)))
            blocks.append([f"🧾 <b>{self.copy('remind_dishes')}</b>", f"<blockquote>{chr(10).join(rows)}</blockquote>"])
        blocks.append([f"💰 <b>{self.copy('remind_share')}:</b> {self.payable(seat.amount)}"])

        if summary.is_closed:
            return "\n\n".join("\n".join(block) for block in blocks)
        if seat.is_paid:
            blocks.append([self.copy("remind_paid")])
        else:
            if summary.payment_details:
                blocks.append([
                    f"💳 <b>{self.copy('share_payment_details')}</b>", self.payment_details(summary.payment_details),
                ])
            blocks.append([self.copy("remind_ask")])
        return "\n\n".join("\n".join(block) for block in blocks)

    def own_dish(self, line: SummaryLine) -> str:
        return f"{self.dish(line)} — {self.amount(line.amount)}"

    def direct_intro(self) -> str:
        """Why the bot writes: the owner put this person on the bill."""
        title = self.summary.title or t(self.language, "bill_untitled")
        return f"👋 <b>{self.copy('direct_intro', title=title)}</b>"


def _fitting_reminder(writer: _Writer, seat: SummarySeat) -> str:
    """Every dish of the seat if they fit one message, otherwise the first ones
    and how many more there are — the share below them stays whole."""
    text = ""
    for limit in [None, *range(len(seat.lines) - 1, -1, -1)]:
        text = writer.reminder(seat, limit)
        if visible_length(text) <= TEXT_LIMIT:
            break
    return text


def _fitting_text(writer: _Writer, intro: str | None) -> str:
    """The whole bill if it fits one message, otherwise less of it: what nobody
    has taken goes first, then people from the end of the list."""
    summary = writer.summary
    attempts = [(None, None)]
    attempts += [(None, limit) for limit in range(len(summary.unassigned) - 1, -1, -1)]
    attempts += [(limit, 0) for limit in range(len(summary.seats) - 1, 0, -1)]
    text = ""
    for seat_limit, unassigned_limit in attempts:
        text = writer.text(seat_limit, unassigned_limit, intro)
        if visible_length(text) <= TEXT_LIMIT:
            break
    return text


def _buttons(summary: BillSummary, language: str, open_url: str, invite_code: str, kind: PostKind) -> list[list[dict]]:
    """Free seats to take, «I've paid» while anything is still owed, the bill
    itself, and a refresh where the bot can keep the post current."""
    rows = []
    if not summary.is_closed and kind is PostKind.GROUP:
        free = [seat for seat in summary.seats if seat.is_free][:SEAT_BUTTONS]
        rows += in_pairs([{
            "text": t(language, "share_btn_take_seat").format(name=seat_label(seat, language)),
            "callback_data": f"{SEAT_PREFIX}{invite_code}:{seat.participant_id}",
        } for seat in free])
    owed = 0 < summary.to_collect and summary.collected < summary.to_collect
    if not summary.is_closed and owed:
        # Paying goes in the app's order: copy the card, pay, say so.
        paying = []
        details = bare_details(summary.payment_details or "")
        if 0 < len(details) <= COPY_LIMIT:
            paying.append({"text": t(language, "share_btn_copy_card"), "copy_text": {"text": details}})
        if kind is not PostKind.FORWARD:
            paying.append({"text": t(language, "share_btn_paid"), "callback_data": f"{PAID_PREFIX}{invite_code}"})
        if paying:
            rows.append(paying)
    last = [{"text": t(language, "share_btn_open"), "url": open_url}]
    if not summary.is_closed and kind in (PostKind.GROUP, PostKind.SEAT):
        last.append({"text": t(language, "share_btn_refresh"), "callback_data": f"{REFRESH_PREFIX}{invite_code}"})
    rows.append(last)
    return rows


def _reminder_buttons(summary: BillSummary, seat: SummarySeat, language: str, open_url: str, invite_code: str) -> list[list[dict]]:
    """For the one person it was sent to: copy the card and say «I've paid»
    while their share is still owed, then the bill and a refresh."""
    rows = []
    if not summary.is_closed and not seat.is_paid and seat.amount > 0:
        paying = []
        details = bare_details(summary.payment_details or "")
        if 0 < len(details) <= COPY_LIMIT:
            paying.append({"text": t(language, "share_btn_copy_card"), "copy_text": {"text": details}})
        paying.append({"text": t(language, "share_btn_paid"), "callback_data": f"{PAID_PREFIX}{invite_code}"})
        rows.append(paying)
    last = [{"text": t(language, "share_btn_open"), "url": open_url}]
    if not summary.is_closed:
        last.append({"text": t(language, "share_btn_refresh"), "callback_data": f"{REFRESH_PREFIX}{invite_code}"})
    rows.append(last)
    return rows


def compose(
    summary: BillSummary,
    language: str,
    *,
    open_url: str,
    invite_code: str,
    public_token: str,
    base_url: str | None,
    kind: PostKind = PostKind.GROUP,
    faces: frozenset[int] = frozenset(),
    theme: str = DEFAULT_THEME,
    seat_id: int | None = None,
) -> ShareMessage:
    """`theme`: the app theme the picture is drawn in — the sharer's.
    `seat_id`: whose reminder it is, for a REMINDER."""
    stamp = fingerprint(summary, language, faces, theme)
    preview_url = (
        f"{base_url.rstrip('/')}/api/bills/public/{public_token}/card.png?lang={language}&theme={theme}&v={stamp}"
        if base_url
        else None
    )
    title = summary.title or t(language, "bill_untitled")
    if kind is PostKind.REMINDER:
        seat = next((seat for seat in summary.seats if seat.participant_id == seat_id), None)
        if seat is None:
            raise ValueError(f"No seat {seat_id} on the bill to remind")
        return ShareMessage(
            html=_fitting_reminder(_Writer(summary, language), seat),
            buttons=_reminder_buttons(summary, seat, language, open_url, invite_code),
            preview_url=preview_url,
            fingerprint=stamp,
            title=title,
            description=f"{t(language, 'remind_share')}: {format_amount(seat.amount, summary.currency, language)}",
            # Paid is not the last word: the payment can still be taken back.
            is_final=summary.is_closed,
        )
    writer = _Writer(summary, language)
    return ShareMessage(
        html=_fitting_text(writer, writer.direct_intro() if kind is PostKind.DIRECT else None),
        buttons=_buttons(summary, language, open_url, invite_code, kind),
        preview_url=preview_url,
        fingerprint=stamp,
        title=title,
        description=f"{t(language, 'share_total')}: {format_amount(summary.total, summary.currency, language)}",
        is_final=summary.is_closed,
    )
