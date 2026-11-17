"""STB-82 / STB-87: receipt worker behaviour.

The worker talks to the DB through its own `Session(engine)` (not the request
session), so these tests build their own engine and point the worker at it, and
stub the Vision / OpenAI clients.
"""
import asyncio
import json

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

import app.worker as worker
from app.models import User, Bill, BillItem, BillUser, BillStatus, ReceiptTask, ReceiptTaskStatus, PaymentMethod, ScanMode
from app.services.app_settings import RECEIPT_MODEL_KEY, SCAN_MODE_KEY, set_setting
from app.utils.currency import to_tiins
from app.utils import crypto


FAKE_JSON = json.dumps(
    {"title": "Lunch", "total_sum": 100, "items": [{"name": "Cola", "count": 1, "amount": 100}]}
)


class _FakeText:
    def __init__(self, description):
        self.description = description


class _FakeVisionResponse:
    def __init__(self, text):
        self.text_annotations = [_FakeText(text)]


class _FakeVisionClient:
    def text_detection(self, image, timeout=None):
        return _FakeVisionResponse("COLA 100\nTOTAL 100")


def _fake_openai(payload, on_create=None):
    """Build a stub OpenAI client; `on_create` runs when the LLM is invoked.

    Whatever it was called with stays on the client as `last_kwargs`, so a test
    can check what the model was actually sent.
    """

    class _FakeOpenAI:
        last_kwargs: dict = {}

        def __init__(self):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            _FakeOpenAI.last_kwargs = kwargs
            if on_create:
                on_create()

            class _Msg:
                content = payload

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    return _FakeOpenAI()


def test_gpt_structure_uses_the_receipt_model(monkeypatch):
    captured = {}

    class _FakeOpenAI:
        def __init__(self):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured.update(kwargs)

            class _Msg:
                content = FAKE_JSON

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    monkeypatch.setattr(worker, "get_openai_client", lambda: _FakeOpenAI())

    data, raw = asyncio.run(worker._gpt_structure("COLA 100\nTOTAL 100", None, model="gpt-6-sol"))

    assert captured["model"] == "gpt-6-sol"
    assert data["title"] == "Lunch"
    assert raw == FAKE_JSON


def test_gpt_structure_prompt_treats_vat_surcharge_as_shared_adjustment(monkeypatch):
    client = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: client)

    asyncio.run(
        worker._gpt_structure(
            'Полная сумма: 1 530 000\nНадбавка "НДС 12%" (+12%): +183 600\n'
            "ИТОГО К ОПЛАТЕ: 1 713 600",
            None,
            model="gpt-6-luna",
        )
    )

    prompt = client.last_kwargs["messages"][1]["content"]
    assert "Надбавка" in prompt
    assert "grand total is larger than the items subtotal" in prompt
    assert "one POSITIVE item with `is_shared_globally`: true" in prompt
    assert "items already add up to the printed grand total" in prompt


@pytest.fixture
def worker_engine(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker, "engine", engine)
    monkeypatch.setattr(worker, "STORAGE_DIR", str(tmp_path))
    (tmp_path / "r.jpg").write_bytes(b"\xff\xd8\xff\xe0")  # dummy image bytes
    return engine


def _make_task(engine, expected_people=None, payment_details=None):
    """Mimic the upload endpoint: a provisional bill (with the wizard's
    headcount/payment) already exists and the task points at it. The worker
    only enriches THIS bill."""
    with Session(engine) as s:
        user = User(telegram_id=7, username="scan")
        s.add(user)
        s.commit()
        s.refresh(user)
        payment_method_id = None
        if payment_details:
            pm = PaymentMethod(user_id=user.id, enc_value=crypto.encrypt(payment_details))
            s.add(pm)
            s.commit()
            s.refresh(pm)
            payment_method_id = pm.id
        bill = Bill(
            owner_id=user.id,
            total_sum=0,
            unallocated_sum=0,
            status=BillStatus.OPEN,
            currency="uzs",
            expected_people=expected_people,
            payment_method_id=payment_method_id,
        )
        s.add(bill)
        s.commit()
        s.refresh(bill)
        s.add(BillUser(bill_id=bill.id, user_id=user.id, allocated_amount=0))
        s.commit()
        task = ReceiptTask(
            user_id=user.id,
            filename="r.jpg",
            status=ReceiptTaskStatus.PENDING,
            bill_id=bill.id,
            owns_bill=True,
        )
        s.add(task)
        s.commit()
        s.refresh(task)
        return user.id, task.id


def test_worker_flips_to_structuring_before_calling_the_llm(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine)
    seen = {}

    def capture():
        with Session(worker_engine) as s:
            seen["status"] = s.get(ReceiptTask, task_id).status

    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, capture))

    asyncio.run(worker.process_task(task_id))

    assert seen["status"] == ReceiptTaskStatus.STRUCTURING
    with Session(worker_engine) as s:
        final = s.get(ReceiptTask, task_id)
        assert final.status == ReceiptTaskStatus.COMPLETED
        assert final.bill_id is not None


def _boom():
    raise RuntimeError("model down")


def test_a_failed_first_scan_takes_its_provisional_bill_down(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine, expected_people=3)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, _boom))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.FAILED
        assert task.bill_id is None
        # The wizard lays the table up front, so the empty seats are no reason
        # to keep a bill nobody has seen.
        assert s.exec(select(Bill)).all() == []


def test_a_failed_scan_into_an_existing_bill_keeps_the_bill(worker_engine, monkeypatch):
    user_id, first_id = _make_task(worker_engine)
    with Session(worker_engine) as s:
        bill_id = s.get(ReceiptTask, first_id).bill_id
        rescan = ReceiptTask(
            user_id=user_id, filename="r.jpg",
            status=ReceiptTaskStatus.PENDING, bill_id=bill_id,
        )
        s.add(rescan)
        s.commit()
        s.refresh(rescan)
        rescan_id = rescan.id

    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, _boom))

    asyncio.run(worker.process_task(rescan_id))

    with Session(worker_engine) as s:
        assert s.get(ReceiptTask, rescan_id).status == ReceiptTaskStatus.FAILED
        assert s.get(Bill, bill_id) is not None


def _sent_to_the_bot(engine, task_id: int) -> int:
    """The task as the bot's wizard leaves it: for a bill it made, with a chat
    waiting on the answer. Returns that bill."""
    with Session(engine) as s:
        task = s.get(ReceiptTask, task_id)
        task.notify_chat_id = 7
        task.owns_bill = False
        s.add(task)
        s.commit()
        return task.bill_id


@pytest.mark.parametrize("read, outcome", [
    (None, {"ok": True}),
    (_boom, {"ok": False, "reason": "failed"}),
])
def test_how_a_scan_sent_to_the_bot_ended_is_counted(worker_engine, monkeypatch, product_events, read, outcome):
    user_id, task_id = _make_task(worker_engine)
    bill_id = _sent_to_the_bot(worker_engine, task_id)
    monkeypatch.setattr(worker, "report_scan", lambda *args: None)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, read))

    asyncio.run(worker.process_task(task_id))

    assert product_events == [(
        "receipt_scan_result",
        str(user_id),
        {"surface": "bot", "mode": "photo", "target": "new_bill", "bill_id": bill_id, **outcome},
    )]


def test_a_scan_from_the_app_is_left_for_the_app_to_count(worker_engine, monkeypatch, product_events):
    _, task_id = _make_task(worker_engine)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, _boom))

    asyncio.run(worker.process_task(task_id))

    assert product_events == []


def test_worker_persists_ocr_and_llm_response(worker_engine, monkeypatch):
    """The raw OCR text and LLM JSON are stored on the task for debugging
    (STB-69). Regression: the cancellation-check refresh used to wipe the
    un-committed llm_response, so it came back empty."""
    _, task_id = _make_task(worker_engine)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.COMPLETED
        assert task.llm_response == FAKE_JSON
        assert task.ocr_text == "COLA 100\nTOTAL 100"


def test_worker_stamps_expected_people_and_payment_onto_bill(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine, expected_people=4, payment_details="card-123")
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.COMPLETED
        bill = s.get(Bill, task.bill_id)
        assert bill.expected_people == 4
        assert bill.payment_method_id is not None
        pm = s.get(PaymentMethod, bill.payment_method_id)
        assert crypto.decrypt(pm.enc_value) == "card-123"


def test_second_scan_adds_a_receipt_without_touching_the_first(worker_engine, monkeypatch):
    """A re-scan replaces only AI-scanned items; manual items and the bill's
    title survive (STB-207)."""
    user_id, task_id = _make_task(worker_engine)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON))
    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        bill_id = s.get(ReceiptTask, task_id).bill_id
        # The owner adds an item by hand after the first scan.
        s.add(BillItem(
            bill_id=bill_id, name="Manual tea", price=to_tiins(50),
            count=1, item_sum=to_tiins(50),  # no receipt_task_id → manual
        ))
        s.commit()
        rescan = ReceiptTask(
            user_id=user_id, filename="r.jpg",
            status=ReceiptTaskStatus.PENDING, bill_id=bill_id,
        )
        s.add(rescan)
        s.commit()
        s.refresh(rescan)
        rescan_id = rescan.id

    new_receipt = json.dumps(
        {"title": "Lunch v2", "total_sum": 200,
         "items": [{"name": "Pizza", "count": 1, "amount": 200}]}
    )
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(new_receipt))
    asyncio.run(worker.process_task(rescan_id))

    with Session(worker_engine) as s:
        items = {i.name: i for i in s.exec(select(BillItem).where(BillItem.bill_id == bill_id)).all()}
        # A second scan is a second RECEIPT on the bill, not a replacement:
        # each scan owns its own lines, so the first one's «Cola» stays.
        assert set(items) == {"Manual tea", "Cola", "Pizza"}
        assert items["Manual tea"].receipt_task_id is None      # manual item kept
        assert items["Pizza"].receipt_task_id == rescan_id      # tied to the new scan
        bill = s.get(Bill, bill_id)
        assert bill.total_sum == to_tiins(50) + to_tiins(100) + to_tiins(200)
        assert bill.title == "Lunch"  # user-visible title kept across re-scan


def test_worker_skips_enrichment_when_cancelled_during_llm(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine)

    def cancel_now():
        with Session(worker_engine) as s:
            t = s.get(ReceiptTask, task_id)
            t.status = ReceiptTaskStatus.CANCELLED
            s.add(t)
            s.commit()

    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(FAKE_JSON, cancel_now))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.CANCELLED
        # Worker bails without enriching; deleting the provisional bill is the
        # cancel endpoint's job, so here the bill stays but is left untouched.
        bill = s.get(Bill, task.bill_id)
        assert bill is not None
        assert bill.title is None
        assert s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all() == []


def test_a_scan_cancelled_while_its_photo_is_read_stays_cancelled(worker_engine, monkeypatch):
    """Cancelled during OCR, before the model step: moving on to the model must
    not put it back to work, or its lines land on the bill after all."""
    _, task_id = _make_task(worker_engine)

    class _CancellingVision(_FakeVisionClient):
        def text_detection(self, image, timeout=None):
            with Session(worker_engine) as s:
                t = s.get(ReceiptTask, task_id)
                t.status = ReceiptTaskStatus.CANCELLED
                s.add(t)
                s.commit()
            return super().text_detection(image, timeout)

    monkeypatch.setattr(worker, "get_scan_mode", lambda session: ScanMode.OCR_LLM)
    monkeypatch.setattr(worker, "get_vision_client", lambda: _CancellingVision())
    openai = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: openai)

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.CANCELLED
        assert s.exec(select(BillItem).where(BillItem.bill_id == task.bill_id)).all() == []
    assert openai.last_kwargs == {}


def test_worker_treats_amount_as_line_total_and_shares_global_line(
    worker_engine, monkeypatch
):
    """`amount` is the whole-line total (qty included) — not multiplied by count —
    and a definitely global line becomes a shared item."""
    _, task_id = _make_task(worker_engine)
    payload = json.dumps(
        {
            "title": "Kofteci Ramiz",
            "total_sum": 362400,
            "items": [
                {
                    "name": "Донер Искандар",
                    "count": 2,
                    "amount": 188000,
                    "is_shared_globally": False,
                },
                {
                    "name": "Hizmet 20%",
                    "count": 1,
                    "amount": 60400,
                    "is_shared_globally": True,
                },
            ],
        }
    )
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(payload))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        bill = s.get(Bill, s.get(ReceiptTask, task_id).bill_id)
        items = {i.name: i for i in s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all()}

        doner = items["Донер Искандар"]
        assert doner.item_sum == to_tiins(188000)          # line total, NOT ×2
        assert doner.count == 2
        assert doner.price == to_tiins(188000) // 2         # per-unit for display

        hizmet = items["Hizmet 20%"]
        assert hizmet.is_shared_globally is True            # service fee → shared
        assert hizmet.item_sum == to_tiins(60400)           # positive, not negative

        # Bill total = sum of line totals = the receipt's grand total.
        assert bill.total_sum == to_tiins(188000) + to_tiins(60400)


def test_worker_shares_positive_vat_surcharge(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine)
    regular_items = [
        ("Blanc 1664", 1, 49000),
        ("Паста Альфредо", 1, 62000),
        ("Курица по тайски", 1, 89000),
        ("Малина и Лемонграсс", 3, 84000),
        ("Ассорти из маринадов", 1, 55000),
        ("Кимчи соус стопка", 1, 45000),
        ("Куриные котлеты с пюре", 1, 82000),
        ("Томлёные говяжьи рёбра", 1, 160000),
        ("Кальян С", 2, 340000),
        ("Изысканный бергамот", 6, 168000),
        ("Лимон", 6, 90000),
        ("Хлебная корзина", 1, 29000),
        ("Замена чаши С", 1, 85000),
        ("СЛОН лимонад", 6, 192000),
    ]
    payload = json.dumps(
        {
            "title": "SLON",
            "total_sum": 1713600,
            "items": [
                *[
                    {
                        "name": name,
                        "count": count,
                        "amount": amount,
                        "is_shared_globally": False,
                    }
                    for name, count, amount in regular_items
                ],
                {
                    "name": "Надбавка НДС 12%",
                    "count": 1,
                    "amount": 183600,
                    "is_shared_globally": True,
                },
            ],
        }
    )
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(payload))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        bill = s.get(Bill, s.get(ReceiptTask, task_id).bill_id)
        items = {
            i.name: i
            for i in s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all()
        }

        vat = items["Надбавка НДС 12%"]
        assert vat.is_shared_globally is True
        assert vat.item_sum == to_tiins(183600)
        assert bill.total_sum == to_tiins(1713600)


def test_worker_accepts_legacy_service_fee_flag(worker_engine, monkeypatch):
    """Old LLM payloads used `is_service_fee`; keep reading it as a fallback."""
    _, task_id = _make_task(worker_engine)
    payload = json.dumps(
        {
            "title": "Legacy",
            "total_sum": 120000,
            "items": [
                {
                    "name": "Burger",
                    "count": 1,
                    "amount": 100000,
                    "is_service_fee": False,
                },
                {
                    "name": "Service",
                    "count": 1,
                    "amount": 20000,
                    "is_service_fee": True,
                },
            ],
        }
    )
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(payload))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        bill = s.get(Bill, s.get(ReceiptTask, task_id).bill_id)
        items = {
            i.name: i
            for i in s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all()
        }

        assert items["Burger"].is_shared_globally is False
        assert items["Service"].is_shared_globally is True


def test_worker_treats_negative_amount_as_shared_discount(worker_engine, monkeypatch):
    """A discount line (negative `amount`) becomes a shared item with a negative
    line total, so it is spread across everyone and pulls the bill total down to
    the printed grand total."""
    _, task_id = _make_task(worker_engine)
    payload = json.dumps(
        {
            "title": "Мой ресторан",
            "total_sum": 76000,
            "items": [
                {
                    "name": "Жареный ростбиф",
                    "count": 1,
                    "amount": 95000,
                    "is_shared_globally": False,
                },
                {
                    "name": "Скидка 20%",
                    "count": 1,
                    "amount": -19000,
                    "is_shared_globally": True,
                },
            ],
        }
    )
    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    monkeypatch.setattr(worker, "get_openai_client", lambda: _fake_openai(payload))

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        bill = s.get(Bill, s.get(ReceiptTask, task_id).bill_id)
        items = {i.name: i for i in s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all()}

        dish = items["Жареный ростбиф"]
        assert dish.is_shared_globally is False            # a normal dish stays personal
        assert dish.item_sum == to_tiins(95000)

        discount = items["Скидка 20%"]
        assert discount.is_shared_globally is True         # discount → shared across everyone
        assert discount.item_sum == to_tiins(-19000)       # negative line total

        # Bill total = subtotal − discount = the receipt's printed grand total.
        assert bill.total_sum == to_tiins(76000)


def test_vision_mode_skips_ocr_and_records_who_read_the_receipt(worker_engine, monkeypatch):
    """The whole point of the mode is that Google Vision is not called at all."""
    _, task_id = _make_task(worker_engine)
    with Session(worker_engine) as s:
        set_setting(s, SCAN_MODE_KEY, ScanMode.VISION.value)

    def refuse():
        raise AssertionError("OCR must not run in vision mode")

    monkeypatch.setattr(worker, "get_vision_client", refuse)
    client = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: client)

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.COMPLETED
        assert task.scan_mode == ScanMode.VISION.value
        assert task.llm_model == "gpt-6-luna"
        assert task.ocr_text is None

    content = client.last_kwargs["messages"][1]["content"]
    assert any(part["type"] == "image_url" for part in content)


def test_the_model_picked_by_the_operator_reads_the_next_scan(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine)
    with Session(worker_engine) as s:
        set_setting(s, RECEIPT_MODEL_KEY, "gpt-6-sol")

    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    client = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: client)

    asyncio.run(worker.process_task(task_id))

    assert client.last_kwargs["model"] == "gpt-6-sol"
    with Session(worker_engine) as s:
        assert s.get(ReceiptTask, task_id).llm_model == "gpt-6-sol"


def test_hybrid_mode_reads_the_receipt_twice(worker_engine, monkeypatch):
    _, task_id = _make_task(worker_engine)
    with Session(worker_engine) as s:
        set_setting(s, SCAN_MODE_KEY, ScanMode.HYBRID.value)

    monkeypatch.setattr(worker, "get_vision_client", lambda: _FakeVisionClient())
    client = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: client)

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.scan_mode == ScanMode.HYBRID.value
        # Both readings are kept: the OCR text is what the model was given to
        # settle a doubtful glyph with.
        assert "COLA" in task.ocr_text

    content = client.last_kwargs["messages"][1]["content"]
    assert any(part["type"] == "image_url" for part in content)
    assert "COLA" in next(p for p in content if p["type"] == "text")["text"]


def test_hybrid_mode_reads_the_photo_alone_when_ocr_finds_nothing(worker_engine, monkeypatch):
    """A blank OCR pass is a reason to lean on the photo, not to fail the scan."""
    _, task_id = _make_task(worker_engine)
    with Session(worker_engine) as s:
        set_setting(s, SCAN_MODE_KEY, ScanMode.HYBRID.value)

    class _BlindVision:
        def text_detection(self, image, timeout=None):
            response = _FakeVisionResponse("")
            response.text_annotations = []
            return response

    monkeypatch.setattr(worker, "get_vision_client", lambda: _BlindVision())
    client = _fake_openai(FAKE_JSON)
    monkeypatch.setattr(worker, "get_openai_client", lambda: client)

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.COMPLETED
        assert task.ocr_text is None

    content = client.last_kwargs["messages"][1]["content"]
    assert any(part["type"] == "image_url" for part in content)
    assert "attached as a photo" in next(p for p in content if p["type"] == "text")["text"]
