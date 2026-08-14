from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from langgraph.types import Command

from app.domain.models import ResumeRequest, StartIncidentRequest, WorkflowResponse
from app.runtime import runtime


router = APIRouter(prefix="/api/v1", tags=["netops"])


def _serialize_interrupt(item: Any) -> dict[str, Any]:
    return {
        "id": getattr(item, "id", None),
        "value": getattr(item, "value", item),
    }


def _format_result(thread_id: str, result: dict[str, Any]) -> WorkflowResponse:
    raw_interrupts = result.get("__interrupt__", [])
    interrupts = [_serialize_interrupt(item) for item in raw_interrupts]
    state = {key: value for key, value in result.items() if key != "__interrupt__"}
    status = "awaiting_approval" if interrupts else state.get("status", "unknown")
    return WorkflowResponse(thread_id=thread_id, status=status, state=state, interrupts=interrupts)


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@router.get("/inventory")
def list_inventory():
    return [item.model_dump(mode="json") for item in runtime.repository.list_all()]




@router.get("/system/model")
def model_config():
    """Return non-secret model/quantization configuration for demo inspection."""
    return runtime.settings.public_model_config()


@router.post("/incidents", response_model=WorkflowResponse)
async def start_incident(payload: StartIncidentRequest):
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    thread_id = uuid4().hex
    initial_state = {
        "thread_id": thread_id,
        "incident": payload.incident.model_dump(mode="json"),
        "raw_evidence": payload.evidence.model_dump(mode="json"),
        "status": "created",
    }
    try:
        result = runtime.graph.invoke(initial_state, config=_config(thread_id))
        return _format_result(thread_id, result)
    except Exception as exc:
        runtime.audit.write("workflow_failed", thread_id, {"error": type(exc).__name__, "message": str(exc)[:500]})
        raise HTTPException(status_code=500, detail=f"workflow failed: {type(exc).__name__}") from exc


@router.post("/incidents/{thread_id}/resume", response_model=WorkflowResponse)
async def resume_incident(thread_id: str, payload: ResumeRequest):
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    try:
        result = runtime.graph.invoke(
            Command(resume=payload.model_dump(mode="json")),
            config=_config(thread_id),
        )
        return _format_result(thread_id, result)
    except Exception as exc:
        runtime.audit.write("workflow_resume_failed", thread_id, {"error": type(exc).__name__, "message": str(exc)[:500]})
        raise HTTPException(status_code=500, detail=f"resume failed: {type(exc).__name__}") from exc


@router.get("/incidents/{thread_id}", response_model=WorkflowResponse)
async def get_incident(thread_id: str):
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    snapshot = runtime.graph.get_state(_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="thread not found")
    state = dict(snapshot.values)
    return WorkflowResponse(
        thread_id=thread_id,
        status=state.get("status", "unknown"),
        state=state,
        interrupts=[],
    )
