"""What a receipt line is, and where a bill was run up — asked of a model in
batches, so that one call labels dozens of wordings at once.

Both answers are kept, not recomputed: a wording is labeled once for everyone
who ever writes it, and a bill's place once until its scan or title changes.
"""
import json
import logging
from dataclasses import dataclass

from app.models import DishGroup
from app.services.llm import get_openai_client

logger = logging.getLogger(__name__)

KIND_KEY_MAX = 40
KIND_NAME_MAX = 60
PLACE_NAME_MAX = 80


@dataclass(frozen=True)
class KindNames:
    ru: str
    uz: str
    en: str


@dataclass(frozen=True)
class DishAnswer:
    group: DishGroup
    kind: str | None
    names: KindNames | None


@dataclass(frozen=True)
class PlaceQuestion:
    """What a bill says about where it was: the venue line of its scanned
    receipts, and the title someone gave it."""

    scanned: list[str]
    title: str | None


DISH_PROMPT = (
    "You label lines from restaurant and café receipts in Uzbekistan. Lines are in Russian, "
    "Uzbek or English, often abbreviated. For EVERY line return one object with:\n"
    "- `i`: the line's index as given;\n"
    "- `group`: one of food, drink, dessert, alcohol, fee, discount, other. `fee` is a service "
    "charge, tip, delivery or packaging; `discount` takes money off; `other` is anything that "
    "is not something eaten or drunk;\n"
    "- `kind`: the dish or drink it is, as a short lowercase English key in snake_case shared by "
    "all its variants — «Чизбургер Double» and «Бургер классик» are both `burger`, «Капучино 0,4» "
    "is `cappuccino`, «Lavash tovuq» is `lavash`, «Пиво Sarbast» is `beer`. Prefer a common "
    "everyday kind over a brand. null for fee, discount and other;\n"
    "- `ru`, `uz`, `en`: the kind's name in Russian, Uzbek (Latin script) and English, singular, "
    "capitalized — «Бургер», «Burger», «Burger». null when `kind` is null.\n"
    'Answer in JSON as {"lines": [...]} with one object per given line.'
)

PLACE_PROMPT = (
    "You name the venue a restaurant bill was run up at, from what the bill says about itself. "
    "For EVERY bill return {`i`: its index, `place`: the venue's name as guests know it, or null}. "
    "`scanned` are venue lines read from its receipts — often a legal entity («OOO», «MCHJ», "
    "«MAS'ULIYATI CHEKLANGAN JAMIYAT»), a branch («Ц-1», «Chilonzor filiali») or an address: keep the "
    "brand only, in its usual spelling and case («CAFFEINE Ц-1 ООО» → «Caffeine»). A legal entity "
    "that is clearly not a venue name gives null. `title` is what people called the bill: take a "
    "venue only when it plainly names one («Ужин в «Плов Центре»» → «Плов Центр», «Evos с "
    "командой» → «Evos»), never from a date, an occasion or a person («Счёт 3 окт», «ДР Дианы», "
    "«Такси в аэропорт» → null). When in doubt, null.\n"
    'Answer in JSON as {"places": [...]} with one object per given bill.'
)


def label_dishes(names: list[str], model: str) -> list[DishAnswer | None]:
    """One answer per name, in the same order: None for a line the model left
    out, which stays unlabeled until the wording turns up again. A line it got
    wrong is `other`, so it is not asked about again and again."""
    lines = [{"i": index, "line": name} for index, name in enumerate(names)]
    by_index = _by_index(_ask(model, DISH_PROMPT, {"lines": lines}).get("lines"))
    return [_dish_answer(by_index[index]) if index in by_index else None for index in range(len(names))]


def name_places(questions: list[PlaceQuestion], model: str) -> list[str | None]:
    bills = [
        {"i": index, "scanned": question.scanned, "title": question.title}
        for index, question in enumerate(questions)
    ]
    by_index = _by_index(_ask(model, PLACE_PROMPT, {"bills": bills}).get("places"))
    return [_place_name(by_index.get(index)) for index in range(len(questions))]


def _by_index(rows) -> dict[int, dict]:
    """The model's rows by the index they answer, which it may write as "3"."""
    indexed = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            indexed.setdefault(int(row.get("i")), row)
        except (TypeError, ValueError):
            continue
    return indexed


def _ask(model: str, instructions: str, payload: dict) -> dict:
    response = get_openai_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


def _dish_answer(row: dict) -> DishAnswer:
    try:
        group = DishGroup(row.get("group"))
    except ValueError:
        group = DishGroup.OTHER
    kind = _kind_key(row.get("kind")) if group not in (DishGroup.FEE, DishGroup.DISCOUNT, DishGroup.OTHER) else None
    names = None
    if kind:
        ru, uz, en = (_text(row.get(lang), KIND_NAME_MAX) for lang in ("ru", "uz", "en"))
        names = KindNames(ru=ru or kind, uz=uz or en or kind, en=en or kind)
    return DishAnswer(group, kind, names)


def _kind_key(value) -> str | None:
    text = _text(value, KIND_KEY_MAX)
    if not text:
        return None
    key = "".join(char if char.isascii() and char.isalnum() else "_" for char in text.lower()).strip("_")
    return key or None


def _place_name(row: dict | None) -> str | None:
    return _text(row.get("place"), PLACE_NAME_MAX) if row else None


def _text(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None
