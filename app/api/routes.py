from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
import re
from app.core.auth import require_reader, require_approver
from langgraph.types import Command

from app.domain.models import ResumeRequest, StartIncidentRequest, WorkflowResponse, IncidentInput, EvidenceInput
from app.runtime import runtime
from app.services.pdf_ingest import extract_pdf_bytes, PdfIngestError, MAX_PDF_BYTES
from app.services.grounded_testcases import list_categories, generate_cases, render_cases, TestCaseSourceError
from pydantic import ValidationError


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
def list_inventory(_=Depends(require_reader)):
    return [item.model_dump(mode="json") for item in runtime.repository.list_all()]




@router.get("/testcases/document-grounded/categories")
def testcase_categories(_=Depends(require_reader)):
    """Read-only index of provenance-annotated RAG test case categories."""
    try:
        return list_categories()
    except TestCaseSourceError as exc:
        raise HTTPException(500, detail=str(exc)) from exc


@router.get("/testcases/document-grounded")
def documented_testcases(
    category: str | None = None,
    limit: int = Query(34, ge=1, le=100),
    _=Depends(require_reader),
):
    """Generate reviewable test *designs*. Does not run RAG or modify the knowledge store."""
    try:
        cases = generate_cases(category=category, limit=limit)
    except ValueError as exc:
        if isinstance(exc, TestCaseSourceError):
            raise HTTPException(500, detail=str(exc)) from exc
        raise HTTPException(422, detail=str(exc)) from exc
    return {"count": len(cases), "cases": cases, "executed": False}


@router.get("/testcases/document-grounded/export")
def export_documented_testcases(
    format: Literal["json", "markdown", "csv"] = "markdown",
    category: str | None = None,
    limit: int = Query(34, ge=1, le=100),
    _=Depends(require_reader),
):
    """Stream a bounded test-case design as text. Never writes into source or runtime."""
    try:
        content = render_cases(generate_cases(category=category, limit=limit), format=format)
    except ValueError as exc:
        if isinstance(exc, TestCaseSourceError):
            raise HTTPException(500, detail=str(exc)) from exc
        raise HTTPException(422, detail=str(exc)) from exc
    media = {"markdown": "text/markdown", "csv": "text/csv", "json": "application/json"}[format]
    return Response(content=content, media_type=media+"; charset=utf-8")


@router.get("/system/model")
def model_config(_=Depends(require_reader)):
    """Return non-secret model/quantization configuration for demo inspection."""
    return runtime.settings.public_model_config()


@router.post("/incidents", response_model=WorkflowResponse)
async def start_incident(payload: StartIncidentRequest, _=Depends(require_reader)):
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
        result = await run_in_threadpool(runtime.graph.invoke, initial_state, config=_config(thread_id))
        return _format_result(thread_id, result)
    except Exception as exc:
        runtime.audit.write("workflow_failed", thread_id, {"error": type(exc).__name__, "message": str(exc)[:500]})
        raise HTTPException(status_code=500, detail=f"workflow failed: {type(exc).__name__}") from exc




async def _parse_pdf_upload(upload: UploadFile) -> dict:
    # Enforce size after transport reception; content is never persisted by this handler.
    payload = await upload.read(MAX_PDF_BYTES + 1)
    await upload.close()
    try:
        return await run_in_threadpool(extract_pdf_bytes, payload)
    except PdfIngestError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/documents/pdf/extract")
async def extract_uploaded_pdf(file: UploadFile = File(...), _=Depends(require_reader)):
    """Read-only native-text PDF extraction. No RAG ingestion or CLI diagnosis."""
    return await _parse_pdf_upload(file)


@router.post("/incidents/from-pdf", response_model=WorkflowResponse)
async def start_incident_from_pdf(
    file: UploadFile = File(...),
    incident_json: str = Form(...),
    evidence_kind: Literal["terminal", "interface", "mac", "arp", "vlan"] = Form(...),
    observed_port: str | None = Form(None),
    observed_device: str | None = Form(None),
    collected_at: str | None = Form(None),
    _=Depends(require_reader),
):
    """Submit a text PDF explicitly labelled as one type of *untrusted* CLI evidence.

    Parsing a PDF never proves the command was run, or that its contents are current.
    No knowledge PDF is automatically promoted into the diagnosis evidence chain.
    """
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    result_pdf = await _parse_pdf_upload(file)
    if result_pdf["truncated"]:
        raise HTTPException(status_code=422, detail="PDF 文本已截断，不允许以不完整的命令输出进行诊断")
    try:
        incident = IncidentInput.model_validate_json(incident_json)
        evidence = EvidenceInput.model_validate({
            f"{evidence_kind}_output": result_pdf["text"],
            "observed_port": observed_port,
            "observed_device": observed_device,
            "collected_at": collected_at,
            "source_system": "pdf_sha256:" + result_pdf["sha256"],
            "evidence_mode": "provided_evidence",
        })
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="故障参数或证据字段校验不通过") from exc
    thread_id = uuid4().hex
    initial_state = {
        "thread_id": thread_id,
        "incident": incident.model_dump(mode="json"),
        "raw_evidence": evidence.model_dump(mode="json"),
        "status": "created",
    }
    try:
        graph_result = await run_in_threadpool(runtime.graph.invoke, initial_state, config=_config(thread_id))
        runtime.audit.write("pdf_evidence_submitted", thread_id, {
            "sha256": result_pdf["sha256"], "page_count": result_pdf["page_count"],
            "evidence_kind": evidence_kind, "source": "user_uploaded_pdf",
        })
        return _format_result(thread_id, graph_result)
    except Exception as exc:
        runtime.audit.write("workflow_failed", thread_id, {"error": type(exc).__name__})
        raise HTTPException(status_code=500, detail=f"workflow failed: {type(exc).__name__}") from exc


@router.post("/incidents/{thread_id}/resume", response_model=WorkflowResponse)
async def resume_incident(thread_id: str, payload: ResumeRequest, _=Depends(require_approver)):
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    if not re.fullmatch(r"[0-9a-f]{32}",thread_id):
        raise HTTPException(status_code=400,detail="invalid task ID")
    snapshot = await run_in_threadpool(runtime.graph.get_state, _config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404,detail="thread not found")
    if not any(getattr(t,"interrupts",()) for t in getattr(snapshot,"tasks",())):
        raise HTTPException(status_code=409,detail="task is not waiting for approval")
    try:
        result = await run_in_threadpool(runtime.graph.invoke,
            Command(resume=payload.model_dump(mode="json")),config=_config(thread_id))
        return _format_result(thread_id,result)
    except Exception as exc:
        runtime.audit.write("workflow_resume_failed", thread_id, {"error": type(exc).__name__, "message": str(exc)[:500]})
        raise HTTPException(status_code=500, detail=f"resume failed: {type(exc).__name__}") from exc


@router.get("/incidents/{thread_id}", response_model=WorkflowResponse)
async def get_incident(thread_id: str, _=Depends(require_reader)):
    if runtime.graph is None:
        raise HTTPException(status_code=503, detail="workflow runtime not initialized")
    if not re.fullmatch(r"[0-9a-f]{32}",thread_id):
        raise HTTPException(status_code=400,detail="invalid task ID")
    snapshot = await run_in_threadpool(runtime.graph.get_state, _config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="thread not found")
    state = dict(snapshot.values)
    waiting = any(getattr(t,"interrupts",()) for t in getattr(snapshot,"tasks",()))
    return WorkflowResponse(
        thread_id=thread_id,
        status="awaiting_approval" if waiting else state.get("status", "unknown"),
        state=state,
        interrupts=[],
    )
