import os
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel, Session
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Load environment variables
load_dotenv()

# Database component variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Construct DATABASE_URL if all components are provided
if all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Fallback to DATABASE_URL environment variable or SQLite default
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./split_the_bill.db")

# SQLite-specific connection arguments
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create engine
engine = create_engine(DATABASE_URL, echo=True, connect_args=connect_args)


def create_db_and_tables():
    """Create all database tables"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for getting database session"""
    with Session(engine) as session:
        yield session
