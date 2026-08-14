from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_demo_ip
from app.domain.enums import DiagnosisCode, FaultType, Layer, Severity


class IncidentInput(BaseModel):
    ip_address: str
    symptom: str = Field(min_length=2, max_length=1000)
    department: str | None = Field(default=None, max_length=100)
    area: str | None = Field(default=None, max_length=100)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fault_type: FaultType = FaultType.OTHER
    oa_address_changed: bool = False
    oa_accessible: bool | None = None
    internet_accessible: bool | None = None
    intermittent: bool = False
    target_mac: str | None = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return validate_demo_ip(value)


class EvidenceInput(BaseModel):
    terminal_output: str = Field(default="", max_length=50_000)
    interface_output: str = Field(default="", max_length=50_000)
    mac_output: str = Field(default="", max_length=50_000)
    arp_output: str = Field(default="", max_length=50_000)
    vlan_output: str = Field(default="", max_length=50_000)
    observed_device: str | None = Field(default=None, max_length=100)
    observed_port: str | None = Field(default=None, max_length=100)


class StartIncidentRequest(BaseModel):
    incident: IncidentInput
    evidence: EvidenceInput = Field(default_factory=EvidenceInput)


class ResumeRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)


class InventoryRecord(BaseModel):
    ip_address: str
    access_id: str
    user_area: str
    device_name: str
    device_role: str
    device_location: str
    registered_port: str
    expected_vlan: int
    network_domain: str
    expected_gateway: str | None = None
    expected_dns: str | None = None
    registered_mac: str | None = None


class ParsedInterface(BaseModel):
    status: str | None = None
    protocol_status: str | None = None
    port: str | None = None
    input_errors: int | None = None
    output_errors: int | None = None
    input_drops: int | None = None
    output_drops: int | None = None


class ParsedMac(BaseModel):
    target_found: bool | None = None
    target_mac: str | None = None
    learned_port: str | None = None
    vlan: int | None = None
    entry_type: str | None = None
    total_entries: int = 0


class ParsedArp(BaseModel):
    target_found: bool | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    interface: str | None = None
    entry_type: str | None = None
    total_entries: int = 0


class ParsedVlan(BaseModel):
    link_type: str | None = None
    access_vlan: int | None = None
    trunk_vlans: list[int] = Field(default_factory=list)
    interface_shutdown: bool | None = None
    description: str | None = None


class ParsedTerminal(BaseModel):
    ip_address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)
    mac_address: str | None = None
    ping_success: bool | None = None
    dns_success: bool | None = None


class ParsedEvidence(BaseModel):
    interface: ParsedInterface = Field(default_factory=ParsedInterface)
    mac: ParsedMac = Field(default_factory=ParsedMac)
    arp: ParsedArp = Field(default_factory=ParsedArp)
    vlan: ParsedVlan = Field(default_factory=ParsedVlan)
    terminal: ParsedTerminal = Field(default_factory=ParsedTerminal)
    observed_device: str | None = None
    observed_port: str | None = None


class DiagnosisResult(BaseModel):
    code: DiagnosisCode
    likely_layer: Layer
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    escalation_required: bool = False


class KnowledgeHit(BaseModel):
    title: str
    source: str
    score: float
    content: str


class ReportResult(BaseModel):
    title: str
    markdown: str
    generated_by: str
    disclaimer: str
    generation_meta: dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    thread_id: str
    status: str
    state: dict[str, Any]
    interrupts: list[dict[str, Any]] = Field(default_factory=list)
