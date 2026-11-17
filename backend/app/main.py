import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
from contextlib import asynccontextmanager
from app.routers import (
    admin, admin_bot_queue, admin_catalog, admin_labeling, admin_pro, admin_senders, app_config, auth, bills,
    broadcast_media, demo_bills, invites, payment_methods, pro, receipts, telegram, users
)
from app.bot_worker import update_worker
from app.worker import worker_loop
from app.scheduler import scheduler_loop
import asyncio
from app.services.bot_commands import register_bot_commands
from app.utils import crypto


@asynccontextmanager
async def lifespan(app: FastAPI):
    crypto.require_key()
    register_bot_commands()

    # Receipts and the bot's updates are event-driven; the scheduler ticks on a clock.
    background = [
        asyncio.create_task(worker_loop()),
        asyncio.create_task(update_worker.run()),
        asyncio.create_task(scheduler_loop()),
    ]
    yield
    for task in background:
        task.cancel()
    for task in background:
        try:
            await task
        except asyncio.CancelledError:
            pass


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


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(users.public_router, prefix="/api")
app.include_router(pro.router, prefix="/api")
app.include_router(invites.router, prefix="/api")
app.include_router(bills.public_router, prefix="/api")
app.include_router(bills.router, prefix="/api")
app.include_router(demo_bills.router, prefix="/api")
app.include_router(broadcast_media.router, prefix="/api")
app.include_router(receipts.public_router, prefix="/api")
app.include_router(receipts.router, prefix="/api")
app.include_router(payment_methods.router, prefix="/api")
app.include_router(telegram.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_senders.router, prefix="/api")
app.include_router(admin_pro.router, prefix="/api")
app.include_router(admin_catalog.router, prefix="/api")
app.include_router(admin_labeling.router, prefix="/api")
app.include_router(admin_bot_queue.router, prefix="/api")
app.include_router(app_config.router, prefix="/api")


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
