from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.data.repository import InventoryRepository
from app.domain.models import EvidenceInput, IncidentInput
from app.parsers.aggregate import parse_all_evidence
from app.services.diagnosis import diagnose
from app.services.knowledge import RoutedKnowledgeBase
from app.services.pdf_ingest import extract_pdf_base64, PdfIngestError
from app.services.grounded_testcases import list_categories, generate_cases, render_cases


settings = get_settings()
repository = InventoryRepository(settings.inventory_db)
repository.initialize(settings.data_dir / "inventory.csv")
knowledge_base = RoutedKnowledgeBase(settings)
knowledge_base.load()

mcp = FastMCP("telecom-netops-readonly", json_response=True)


@mcp.tool()
def query_access_relation(ip_address: str) -> dict:
    """按私网 IP 查询模拟接入号、登记设备、端口和 VLAN。只读。"""
    incident = IncidentInput(ip_address=ip_address, symptom="MCP resource lookup")
    record = repository.find_by_ip(incident.ip_address)
    return {"found": record is not None, "record": record.model_dump(mode="json") if record else None}


@mcp.tool()
def parse_switch_evidence(
    interface_output: str = "",
    mac_output: str = "",
    arp_output: str = "",
    vlan_output: str = "",
    terminal_output: str = "",
    target_mac: str | None = None,
    observed_device: str | None = None,
    observed_port: str | None = None,
) -> dict:
    """解析脱敏后的接口、MAC、VLAN 和终端命令输出，不连接真实设备。"""
    evidence = EvidenceInput(
        interface_output=interface_output,
        mac_output=mac_output,
        arp_output=arp_output,
        vlan_output=vlan_output,
        terminal_output=terminal_output,
        observed_device=observed_device,
        observed_port=observed_port,
    )
    return parse_all_evidence(evidence, target_mac).model_dump(mode="json")


@mcp.tool()
def diagnose_access_issue(
    ip_address: str,
    symptom: str,
    interface_output: str = "",
    mac_output: str = "",
    arp_output: str = "",
    vlan_output: str = "",
    terminal_output: str = "",
    target_mac: str | None = None,
    observed_device: str | None = None,
    observed_port: str | None = None,
) -> dict:
    """基于模拟台账、确定性解析和规则引擎生成只读辅助诊断。"""
    incident = IncidentInput(ip_address=ip_address, symptom=symptom, target_mac=target_mac)
    evidence = EvidenceInput(
        interface_output=interface_output,
        mac_output=mac_output,
        arp_output=arp_output,
        vlan_output=vlan_output,
        terminal_output=terminal_output,
        observed_device=observed_device,
        observed_port=observed_port,
    )
    inventory = repository.find_by_ip(incident.ip_address)
    parsed = parse_all_evidence(evidence, incident.target_mac, incident.ip_address)
    result = diagnose(incident, inventory, parsed)
    return {
        "inventory": inventory.model_dump(mode="json") if inventory else None,
        "parsed_evidence": parsed.model_dump(mode="json"),
        "diagnosis": result.model_dump(mode="json"),
    }


@mcp.tool()
def search_netops_runbook(query: str, top_k: int = 3) -> list[dict]:
    """通过 LangChain + Ollama Embedding + FAISS 检索本地脱敏运维知识。"""
    return [item.model_dump(mode="json") for item in knowledge_base.search(query, top_k=top_k)]




@mcp.tool()
def extract_pdf_document(pdf_base64: str) -> dict:
    """只读解析客户端提交的文本型 PDF（Base64）。不访问任意本地路径、不执行命令、不过滤权限。

    工具只提取文本和页码；提取结果不自动成为设备证据或 RAG 知识。
    扫描版和加密 PDF 不支持，大小和页数受限。
    """
    try:
        return extract_pdf_base64(pdf_base64)
    except PdfIngestError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc)}


@mcp.tool()
def list_document_grounded_testcases() -> dict:
    """列出可溯源 RAG 检索测试用例分类。不会运行模型、不访问外部服务。"""
    return list_categories()


@mcp.tool()
def generate_document_grounded_testcases(category: str = "", limit: int = 34) -> dict:
    """从人工整理的电信资料 Query 与 Gold 生成待执行测试用例（只读）。

    不创造新的故障工单、不将 Query 当作故障分类标签、不声称已通过测试。
    """
    cases = generate_cases(category=category or None, limit=limit)
    return {"count": len(cases), "cases": cases, "trust": "curated_metadata_not_live_fault_cases"}


@mcp.tool()
def export_document_grounded_testcases(format: str = "markdown", category: str = "", limit: int = 34) -> dict:
    """将资料约束测试用例以 JSON/Markdown/CSV 文本返回给客户端，不写本地文件。"""
    cases = generate_cases(category=category or None, limit=limit)
    return {"format": format, "count": len(cases), "content": render_cases(cases, format=format)}


@mcp.tool()
def get_readonly_boundary() -> dict:
    """返回本项目允许和禁止的操作边界。"""
    return {
        "allowed": [
            "查询模拟资源台账",
            "解析用户粘贴的脱敏只读命令输出",
            "生成辅助诊断与排障建议",
            "检索本地知识文档",
            "只读提取客户端提供的文本型 PDF 并保留页码（不自动归因）",
            "从来源标注 Query 与 Gold 生成待执行的 RAG 检索测试用例，支持 JSON/Markdown/CSV",
        ],
        "forbidden": [
            "连接生产 MSE、网管、交换机或终端",
            "执行配置修改、重启、封禁和自动修复",
            "保存真实账号、密钥、客户信息或设备地址",
        ],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
