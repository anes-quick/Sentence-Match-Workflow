from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router

def create_app() -> FastAPI:
    app = FastAPI(title="Sentence Match Workflow", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "null",  # file:// when opening index.html directly
            "http://localhost:8000", "http://127.0.0.1:8000",
            "http://localhost:8001", "http://127.0.0.1:8001",
            "http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:5173", "http://127.0.0.1:5173",
        ],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app

app = create_app()
