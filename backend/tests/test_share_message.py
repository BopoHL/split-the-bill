from dataclasses import replace
from datetime import datetime

from app.services.bill_summary import BillSummary, SummaryLine, SummarySeat
from app.services.share_message import PAID_PREFIX, REFRESH_PREFIX, SEAT_BUTTONS, SEAT_PREFIX, PostKind, compose, fingerprint
from app.utils.telegram_html import TEXT_LIMIT, visible_length


def _summary(**overrides) -> BillSummary:
    values = dict(
        title="Ужин <в> чайхане",
        created_at=datetime(2026, 9, 25, 14, 0),
        currency="uzs",
        total=32_800_000,
        seats=(
            SummarySeat(2, "Алиса", 1, 3_200_000, False, True, (SummaryLine("Самса", 2, 2_400_000), SummaryLine("Чай", 1, 800_000))),
            SummarySeat(3, None, 2, 11_000_000, False, False, (SummaryLine("Шашлык", 2, 5_600_000), SummaryLine("Лепёшка", 2, 400_000))),
            SummarySeat(1, "Леонид", 0, 10_100_000, True, False, (SummaryLine("Плов", 1, 6_500_000),)),
        ),
        unassigned=(SummaryLine("Салат", 1, 2_200_000), SummaryLine("Самса", 2, 2_400_000)),
        unassigned_total=4_600_000,
        to_collect=14_200_000,
        collected=3_200_000,
        payment_details="8600 1234 5678 9012",
        is_closed=False,
    )
    values.update(overrides)
    return BillSummary(**values)


def _compose(summary: BillSummary, language: str = "ru", base_url: str | None = "https://stb.example/", kind: PostKind = PostKind.GROUP):
    return compose(
        summary, language, open_url="https://t.me/bot/app?startapp=inv_code", invite_code="abcdefghijkl",
        public_token="tok", base_url=base_url, kind=kind,
    )


def _with_free_guest(summary: BillSummary) -> BillSummary:
    alice, guest, owner = summary.seats
    return replace(summary, seats=(alice, replace(guest, is_free=True), owner))


OPEN_BUTTON = {"text": "🧾 Открыть", "url": "https://t.me/bot/app?startapp=inv_code"}
REFRESH_BUTTON = {"text": "🔄 Обновить", "callback_data": f"{REFRESH_PREFIX}abcdefghijkl"}
COPY_BUTTON = {"text": "💳 Карта", "copy_text": {"text": "8600123456789012"}}
PAID_BUTTON = {"text": "✅ Я оплатил(а)", "callback_data": f"{PAID_PREFIX}abcdefghijkl"}
# Paying in the app's order: copy the card, then say it is paid.
PAID = [COPY_BUTTON, PAID_BUTTON]
# The bill and a refresh end every post that has both, side by side.
OPEN_AND_REFRESH = [OPEN_BUTTON, REFRESH_BUTTON]
OPEN = [OPEN_BUTTON]


def test_the_text_lists_everyone_with_a_copyable_amount_what_nobody_took_and_the_card():
    message = _compose(_summary())

    assert visible_length(message.html) <= TEXT_LIMIT
    # The name, the total and how much is paid are on the picture; the text
    # opens on the people, a line apart from their heading; the short blocks
    # after them sit right under theirs.
    assert message.html.startswith("👥 <b>Участники</b>\n\n")
    assert "Ужин" not in message.html and "Итого" not in message.html and "Оплачено" not in message.html
    # Who took which dishes is the picture's job; here each person is a name
    # and an amount to copy.
    assert "👥 <b>Участники</b>\n\n<b>Алиса</b> ✅ — <code>32000</code> сум\n<b>Гость 2</b> — <code>110000</code> сум\n<b>Леонид</b> — <code>101000</code> сум\n" in message.html
    assert "Самса ×2, Чай" not in message.html and "организатор" not in message.html
    assert "📌 <b>Никто не взял</b>\n<blockquote expandable>Салат — 22 000 сум\nСамса ×2 — 24 000 сум</blockquote>" in message.html
    # Bare digits: Telegram recognises a card number itself and offers to copy it.
    assert message.html.endswith("💳 <b>Реквизиты</b>\n8600123456789012")


def test_payment_details_that_are_not_a_card_number_go_as_written():
    message = _compose(_summary(payment_details="Click: @leo <pay>"))

    assert message.html.endswith("💳 <b>Реквизиты</b>\nClick: @leo &lt;pay&gt;")


def test_the_picture_above_is_versioned_by_the_state_it_shows():
    message = _compose(_summary())
    paid = _compose(_summary(collected=14_200_000))

    assert message.preview_url == (
        f"https://stb.example/api/bills/public/tok/card.png?lang=ru&theme=light&v={message.fingerprint}"
    )
    assert message.link_preview == {"url": message.preview_url, "prefer_large_media": True, "show_above_text": True}
    assert paid.fingerprint != message.fingerprint
    assert fingerprint(_summary(), "uz") != message.fingerprint
    # The same state in the dark theme is another picture.
    assert fingerprint(_summary(), "ru", theme="dark") != message.fingerprint
    # A face that can be drawn now and could not before is a new picture too.
    assert fingerprint(_summary(), "ru", frozenset({42})) != message.fingerprint
    assert _compose(_summary(), base_url=None).link_preview == {"is_disabled": True}


def test_a_post_in_a_chat_offers_the_free_seats_paying_the_bill_and_a_refresh():
    # The card number copies with a tap on it in the text, so it needs no button.
    take_guest = [{"text": "👥 Гость 2 – занять", "callback_data": f"{SEAT_PREFIX}abcdefghijkl:3"}]

    assert _compose(_with_free_guest(_summary())).buttons == [take_guest, PAID, OPEN_AND_REFRESH]
    assert all(len(button["callback_data"].encode()) <= 64 for button in (*take_guest, PAID_BUTTON, REFRESH_BUTTON))


def test_only_the_first_free_seats_get_a_button():
    guests = tuple(SummarySeat(10 + n, None, n, 0, False, False, (), is_free=True) for n in range(1, 10))

    buttons = _compose(_summary(seats=guests)).buttons
    seat_rows = buttons[:SEAT_BUTTONS // 2]

    # Two to a row: «👥 Гость 1 – занять» fits half of one.
    assert all(len(row) == 2 for row in seat_rows)
    assert [button["callback_data"] for row in seat_rows for button in row] == [
        f"{SEAT_PREFIX}abcdefghijkl:{10 + n}" for n in range(1, SEAT_BUTTONS + 1)
    ]
    assert buttons[SEAT_BUTTONS // 2:] == [PAID, OPEN_AND_REFRESH]


def test_a_seat_with_a_long_name_takes_a_row_of_its_own():
    names = ("Ира", "Александра Константиновна", "Оля", "Катя")
    seats = tuple(SummarySeat(20 + n, name, n, 0, False, False, (), is_free=True) for n, name in enumerate(names))

    rows = _compose(_summary(seats=seats)).buttons[:3]

    assert [[button["text"] for button in row] for row in rows] == [
        ["👥 Ира – занять"],
        ["👥 Александра Константиновна – занять"],
        ["👥 Оля – занять", "👥 Катя – занять"],
    ]


def test_a_post_for_one_person_offers_no_seats_and_one_the_bot_sent_cannot_be_refreshed():
    summary = _with_free_guest(_summary())

    assert _compose(summary, kind=PostKind.SEAT).buttons == [PAID, OPEN_AND_REFRESH]
    assert _compose(summary, kind=PostKind.DIRECT).buttons == [PAID, OPEN]
    # Forwarded on by the sharer, a button could not tell whose tap it is; a
    # copy of the card is the same for anyone.
    assert _compose(summary, kind=PostKind.FORWARD).buttons == [[COPY_BUTTON], OPEN]


def test_a_post_the_bot_sends_someone_put_on_the_bill_says_so_first():
    direct = _compose(_summary(), kind=PostKind.DIRECT).html
    shared = _compose(_summary()).html

    assert direct == f"👋 <b>Вас добавили в счёт «Ужин &lt;в&gt; чайхане»</b>\n\n{shared}"
    assert _compose(_summary(title=None), language="en", kind=PostKind.DIRECT).html.startswith(
        "👋 <b>You were added to the bill «Untitled»</b>\n\n👥"
    )


def test_nothing_left_to_pay_takes_the_paid_button_away():
    assert _compose(_summary(collected=14_200_000)).buttons == [OPEN_AND_REFRESH]
    assert _compose(_summary(to_collect=0, collected=0)).buttons == [OPEN_AND_REFRESH]


def test_a_closed_bill_is_final_and_offers_nothing_to_refresh_or_pay():
    message = _compose(_summary(is_closed=True))

    assert message.html.startswith("🔒 Счёт закрыт\n\n👥")
    assert "Оплачено" not in message.html and "8600" not in message.html
    assert message.buttons == [OPEN]
    assert _compose(_with_free_guest(_summary(is_closed=True))).buttons == [OPEN]


def test_a_bill_without_takers_says_so_in_the_readers_language():
    message = _compose(_summary(seats=(), to_collect=0, collected=0, payment_details=None, title=None), language="en")

    assert message.html.splitlines()[:3] == ["👥 <b>Participants</b>", "", "<i>Nobody has picked anything yet — open the bill and mark your dishes.</i>"]
    assert "<i>Nobody has picked anything yet — open the bill and mark your dishes.</i>" in message.html
    assert message.title == "Untitled"


def test_a_huge_bill_still_fits_one_message():
    seats = tuple(
        SummarySeat(index, f"Person {index} " + "x" * 40, index, 100_000, False, False, tuple(SummaryLine(f"Dish {n} " + "y" * 30, 1, 1000) for n in range(12)))
        for index in range(1, 60)
    )
    unassigned = tuple(SummaryLine(f"Leftover {n} " + "z" * 30, 1, 1000) for n in range(80))

    message = _compose(_summary(seats=seats, unassigned=unassigned, unassigned_total=80_000))

    assert visible_length(message.html) <= TEXT_LIMIT
    assert "<b>Person 1 " in message.html


def test_the_card_copies_with_a_button_as_bare_digits_or_as_written():
    assert _compose(_summary(payment_details="8600-1234 5678 9012")).buttons[-2][0] == COPY_BUTTON
    written = _compose(_summary(payment_details=" Payme +998 90 123 45 67 ")).buttons[-2][0]
    assert written["copy_text"] == {"text": "Payme +998 90 123 45 67"}
    # Without details, or with nothing left to pay, there is nothing to copy.
    assert _compose(_summary(payment_details=None)).buttons[-2] == [PAID_BUTTON]
    assert COPY_BUTTON not in [button for row in _compose(_summary(collected=14_200_000)).buttons for button in row]


def test_a_reminder_counts_your_dishes_and_not_the_ones_the_table_shares():
    seat = SummarySeat(5, "Бобур", 3, 50_000, False, False, (SummaryLine("Пиво", 2, 30_000), SummaryLine("Хлеб", 2, 20_000, everyone=True)))
    text = compose(_summary(seats=(seat,)), "ru", open_url="https://t.me/x", invite_code="c", public_token="t", base_url=None, kind=PostKind.REMINDER, seat_id=5).html

    assert "Пиво ×2 — 300 сум\nХлеб — 200 сум" in text
    assert "на всех" not in text
