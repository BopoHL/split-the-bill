import app.utils.telegram as telegram


def _prepared_payload(monkeypatch, **options) -> dict:
    captured = {}

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"id": "PREP"}}

    def fake_post(url, json=None, timeout=None):
        captured.update(payload=json)
        return FakeResponse()

    monkeypatch.setenv("TG_TOKEN", "token")
    monkeypatch.setattr(telegram._http, "post", fake_post)
    assert telegram.save_prepared_text_message(
        123, result_id="share:abc", title="Dinner", description="", text_html="<b>Dinner</b>",
        link_preview_options={"is_disabled": True}, reply_markup={"inline_keyboard": []}, **options,
    ) == "PREP"
    return captured["payload"]


def test_a_prepared_post_goes_anywhere_but_bot_chats(monkeypatch):
    payload = _prepared_payload(monkeypatch)

    assert (payload["allow_user_chats"], payload["allow_group_chats"], payload["allow_channel_chats"]) == (True, True, True)
    assert payload["allow_bot_chats"] is False


def test_a_post_for_one_person_stays_out_of_groups_and_channels(monkeypatch):
    payload = _prepared_payload(monkeypatch, private_chats_only=True)

    assert payload["allow_user_chats"] is True
    assert not (payload["allow_group_chats"] or payload["allow_channel_chats"] or payload["allow_bot_chats"])


def test_unreachable_chat_covers_every_way_telegram_refuses_a_dm():
    refused = [
        "Telegram error: Forbidden: bot was blocked by the user",
        "Telegram error: Forbidden: bot can't initiate conversation with a user",
        "Telegram error: Bad Request: chat not found",
        "Telegram error: Forbidden: user is deactivated",
    ]
    assert all(telegram.is_unreachable_chat(RuntimeError(text)) for text in refused)
    # A transient failure is not a reason to write the person off.
    assert not telegram.is_unreachable_chat(RuntimeError("Telegram error: Too Many Requests"))


def test_calls_share_one_kept_alive_session_and_give_up_connecting_quickly(monkeypatch):
    timeouts = []

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": True}

    def fake_post(url, json=None, timeout=None):
        timeouts.append(timeout)
        return FakeResponse()

    monkeypatch.setenv("TG_TOKEN", "token")
    monkeypatch.setattr(telegram._http, "post", fake_post)

    telegram.answer_callback_query("cb")
    telegram.send_message(1, "hi")

    assert timeouts == [(telegram.CONNECT_TIMEOUT, 10), (telegram.CONNECT_TIMEOUT, 10)]


def test_only_opening_a_connection_is_tried_again_never_a_request():
    retry = telegram._http.get_adapter(telegram.TELEGRAM_API).max_retries

    assert (retry.connect, retry.read, retry.status, retry.other) == (1, 0, 0, 0)


def test_a_rich_message_sends_its_html_and_keyboard_and_waits_for_the_pictures(monkeypatch):
    calls = []

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 7}}

    def fake_post(url, json=None, timeout=None):
        calls.append((url.rsplit("/", 1)[-1], json, timeout))
        return FakeResponse()

    monkeypatch.setenv("TG_TOKEN", "token")
    monkeypatch.setattr(telegram._http, "post", fake_post)
    keyboard = {"inline_keyboard": [[{"text": "⭐ PRO", "url": "https://t.me/bot/app"}]]}

    assert telegram.send_rich_message(5, "<p>Привет</p>", reply_markup=keyboard) == {"message_id": 7}

    [(method, payload, timeout)] = calls
    assert method == "sendRichMessage"
    assert payload == {"chat_id": 5, "rich_message": {"html": "<p>Привет</p>"}, "reply_markup": keyboard}
    assert timeout == (telegram.CONNECT_TIMEOUT, 30)
