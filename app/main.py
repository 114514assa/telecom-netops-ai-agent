from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.runtime import runtime


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime.start()
    yield
    runtime.stop()


app = FastAPI(
    title="Telecom NetOps AI Agent",
    version="0.2.0",
    description="Read-only access-network troubleshooting Agent with LangGraph, MCP, RAG and optional quantized local LLM inference.",
    lifespan=lifespan,
)
app.include_router(router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "workflow_ready": runtime.graph is not None,
        "mode": "read-only-simulated-data",
    }
