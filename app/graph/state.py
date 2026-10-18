from typing import Any, TypedDict


class NetOpsState(TypedDict, total=False):
    thread_id: str
    incident: dict[str, Any]
    raw_evidence: dict[str, Any]
    inventory: dict[str, Any] | None
    collection_error: str | None
    parsed_evidence: dict[str, Any]
    diagnosis: dict[str, Any]
    knowledge_hits: list[dict[str, Any]]
    report: dict[str, Any]
    approved: bool | None
    approval_comment: str
    status: str
    errors: list[str]
