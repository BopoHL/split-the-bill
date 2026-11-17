import os
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel, Session
from contextlib import asynccontextmanager
from typing import AsyncGenerator

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

if all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?client_encoding=utf8"
else:
    DATABASE_URL = "sqlite:///./split_the_bill.db"

connect_args = {}
pool_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Requests, the receipt and bot workers and eleven jobs (each holds a second
    # connection for its advisory lock) share this pool; Postgres allows 30.
    pool_args = {"pool_size": 10, "max_overflow": 10}

# SQL logging is opt-in: every SSE REFRESH re-reads the bill, so echoing on a
# 2 GB VPS is pure noise and overhead.
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO") == "1",
    connect_args=connect_args,
    **pool_args,
)


def get_session():
    with Session(engine) as session:
        yield session
