import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
from contextlib import asynccontextmanager
from app.database import create_db_and_tables
from app.routers import users, bills


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Split The Bill API",
    description="Backend API for Split The Bill Telegram Mini App",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(users.router, prefix="/api")
app.include_router(bills.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "Welcome to Split The Bill API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
