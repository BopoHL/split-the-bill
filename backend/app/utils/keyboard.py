"""Inline keyboards laid out the way a phone shows them."""

# Two buttons share a row while each is short enough for half of it; Telegram
# does not wrap a button's text, it cuts it off with «…».
HALF_ROW = 20


def in_pairs(buttons: list[dict]) -> list[list[dict]]:
    """Buttons two to a row, in order; one too long for half a row gets a
    row of its own."""
    rows: list[list[dict]] = []
    for button in buttons:
        if len(button["text"]) <= HALF_ROW and rows and len(rows[-1]) == 1 and len(rows[-1][0]["text"]) <= HALF_ROW:
            rows[-1].append(button)
        else:
            rows.append([button])
    return rows
