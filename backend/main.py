"""
TAO Server — FastAPI entry point with CORS, static files, and WebSocket support.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

from backend.api.routes import router
from backend.api.openai_proxy import proxy_router
from backend.ollama_judge.routes import judge_router
from backend.api.prometheus_exporter import prometheus_exporter
from backend.config import settings

app = FastAPI(
    title="TAO — Tiered Adversarial Oversight",
    description="Defense-in-depth framework for AI reward hacking prevention",
    version="1.0.0",
)

# ─── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Routes ────────────────────────────────────────────────
app.include_router(router)
app.include_router(proxy_router)
app.include_router(judge_router)


@app.get("/metrics")
async def get_metrics():
    """Prometheus OpenMetrics endpoint."""
    return PlainTextResponse(
        content=prometheus_exporter.export_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

# ─── Static Files (Frontend) ──────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/components", StaticFiles(directory=str(frontend_dir / "components")), name="components")
    app.mount("/utils", StaticFiles(directory=str(frontend_dir / "utils")), name="utils")
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/index.css")
    async def serve_css():
        return FileResponse(str(frontend_dir / "index.css"))

    @app.get("/app.js")
    async def serve_js():
        return FileResponse(str(frontend_dir / "app.js"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
