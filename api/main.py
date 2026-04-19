import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.logging_config import configure_logging  # noqa: E402

configure_logging()

app = FastAPI(title="PersonaGraph", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes import (
    router,  # noqa: E402 — import after app creation to avoid circular refs
)

app.include_router(router, prefix="/api")
