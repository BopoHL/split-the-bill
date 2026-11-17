import asyncio

from fastapi.responses import StreamingResponse
from sqlmodel import Session, SQLModel, create_engine

import app.routers.bills as bills_router
from app.models import Bill, User
from app.services.sse_ticket_service import resource_key, sse_tickets


def test_an_open_bill_stream_holds_no_database_connection(monkeypatch, tmp_path):
    """A stream lives as long as the screen does. While it held a pooled
    connection, fifteen open bills emptied the pool for every other request."""
    engine = create_engine(f"sqlite:///{tmp_path / 'stream.db'}", pool_size=1, max_overflow=0)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(telegram_id=1)
        session.add(owner)
        session.commit()
        bill = Bill(owner_id=owner.id)
        session.add(bill)
        session.commit()
        owner_id, bill_id = owner.id, bill.id
    monkeypatch.setattr(bills_router, "engine", engine)
    ticket = sse_tickets.issue(owner_id, resource_key("bill", bill_id))

    response = asyncio.run(bills_router.bill_events(bill_id, ticket))

    assert isinstance(response, StreamingResponse)
    assert engine.pool.checkedout() == 0
    engine.dispose()
