from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.config import Settings
from app.core.security import safe_report_path
from app.data.repository import InventoryRepository
from app.domain.models import (
    DiagnosisResult,
    EvidenceInput,
    IncidentInput,
    InventoryRecord,
    KnowledgeHit,
    ParsedEvidence,
    ReportResult,
)
from app.graph.state import NetOpsState
from app.parsers.aggregate import parse_all_evidence
from app.services.audit import AuditLogger
from app.services.diagnosis import diagnose
from app.services.knowledge import RoutedKnowledgeBase, build_retrieval_query
from app.services.report import ReportComposer


def build_graph(
    repository: InventoryRepository,
    knowledge_base: RoutedKnowledgeBase,
    settings: Settings,
    audit: AuditLogger,
    checkpointer: Any,
):
    composer = ReportComposer(settings)

    def normalize_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        evidence = EvidenceInput.model_validate(state.get("raw_evidence", {}))
        audit.write("incident_received", state["thread_id"], {"ip": incident.ip_address, "fault_type": incident.fault_type.value})
        return {
            "incident": incident.model_dump(mode="json"),
            "raw_evidence": evidence.model_dump(mode="json"),
            "status": "normalized",
            "errors": [],
        }

    def inventory_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        record = repository.find_by_ip(incident.ip_address)
        audit.write("inventory_queried", state["thread_id"], {"found": record is not None})
        return {"inventory": record.model_dump(mode="json") if record else None, "status": "inventory_queried"}

    def parse_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        evidence = EvidenceInput.model_validate(state["raw_evidence"])
        parsed = parse_all_evidence(evidence, incident.target_mac, incident.ip_address)
        audit.write(
            "evidence_parsed",
            state["thread_id"],
            {
                "interface_status": parsed.interface.status,
                "mac_found": parsed.mac.target_found,
                "access_vlan": parsed.vlan.access_vlan,
            },
        )
        return {"parsed_evidence": parsed.model_dump(mode="json"), "status": "evidence_parsed"}

    def diagnose_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        inventory = InventoryRecord.model_validate(state["inventory"]) if state.get("inventory") else None
        parsed = ParsedEvidence.model_validate(state["parsed_evidence"])
        result = diagnose(incident, inventory, parsed)
        audit.write(
            "diagnosis_created",
            state["thread_id"],
            {"code": result.code.value, "confidence": result.confidence, "layer": result.likely_layer.value},
        )
        return {"diagnosis": result.model_dump(mode="json"), "status": "diagnosed"}

    def retrieve_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        inventory = InventoryRecord.model_validate(state["inventory"]) if state.get("inventory") else None
        parsed = ParsedEvidence.model_validate(state["parsed_evidence"])
        diagnosis = DiagnosisResult.model_validate(state["diagnosis"])
        query = build_retrieval_query(incident, inventory, parsed, diagnosis)
        try:
            hits = knowledge_base.search(query, top_k=settings.rag_top_k)
            retrieval_error = getattr(knowledge_base, "last_error", None)
            if retrieval_error:
                audit.write(
                    "knowledge_retrieval_failed",
                    state["thread_id"],
                    {
                        "backend": "langchain-ollama-faiss",
                        "error": retrieval_error[:500],
                    },
                )
            else:
                audit.write(
                    "knowledge_retrieved",
                    state["thread_id"],
                    {
                        "count": len(hits),
                        "backend": "langchain-ollama-faiss" if settings.rag_enabled else "disabled",
                        "query_preview": query[:300],
                    },
                )
        except (RuntimeError, OSError, ValueError) as exc:
            # RAG is supporting evidence only. A retrieval outage must not
            # override or block deterministic diagnosis.
            hits = []
            audit.write(
                "knowledge_retrieval_failed",
                state["thread_id"],
                {
                    "backend": "langchain-ollama-faiss" if settings.rag_enabled else "disabled",
                    "error": type(exc).__name__,
                },
            )
        return {
            "knowledge_hits": [hit.model_dump(mode="json") for hit in hits],
            "status": "knowledge_retrieved",
        }

    def compose_node(state: NetOpsState) -> dict:
        incident = IncidentInput.model_validate(state["incident"])
        inventory = InventoryRecord.model_validate(state["inventory"]) if state.get("inventory") else None
        parsed = ParsedEvidence.model_validate(state["parsed_evidence"])
        diagnosis = DiagnosisResult.model_validate(state["diagnosis"])
        hits = [KnowledgeHit.model_validate(item) for item in state.get("knowledge_hits", [])]
        report = composer.compose(incident, inventory, parsed, diagnosis, hits)
        audit.write("report_composed", state["thread_id"], {"generated_by": report.generated_by})
        return {"report": report.model_dump(mode="json"), "status": "report_ready"}

    def approval_node(state: NetOpsState) -> dict:
        if not settings.require_approval:
            return {"approved": True, "approval_comment": "审批功能已由配置关闭", "status": "approved"}
        decision = interrupt(
            {
                "type": "report_approval",
                "message": "请确认报告是否可归档。批准不代表允许自动修改网络配置。",
                "report": state["report"],
                "diagnosis": state["diagnosis"],
            }
        )
        if not isinstance(decision, dict):
            decision = {"approved": bool(decision), "comment": ""}
        approved = bool(decision.get("approved", False))
        comment = str(decision.get("comment", ""))[:1000]
        audit.write("approval_decision", state["thread_id"], {"approved": approved, "comment": comment})
        return {
            "approved": approved,
            "approval_comment": comment,
            "status": "approved" if approved else "rejected",
        }

    def route_after_approval(state: NetOpsState) -> str:
        return "finalize" if state.get("approved") else END

    def finalize_node(state: NetOpsState) -> dict:
        report = ReportResult.model_validate(state["report"])
        target = safe_report_path(settings.report_dir, state["thread_id"])
        target.write_text(
            report.markdown
            + "\n\n---\n\n"
            + f"审批意见：{state.get('approval_comment') or '无'}\n",
            encoding="utf-8",
        )
        audit.write("report_archived", state["thread_id"], {"path": str(target)})
        return {"status": "completed"}

    builder = StateGraph(NetOpsState)
    builder.add_node("normalize", normalize_node)
    builder.add_node("inventory", inventory_node)
    builder.add_node("parse", parse_node)
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("compose", compose_node)
    builder.add_node("approval", approval_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "inventory")
    builder.add_edge("inventory", "parse")
    builder.add_edge("parse", "diagnose")
    builder.add_edge("diagnose", "retrieve")
    builder.add_edge("retrieve", "compose")
    builder.add_edge("compose", "approval")
    builder.add_conditional_edges("approval", route_after_approval, {"finalize": "finalize", END: END})
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
