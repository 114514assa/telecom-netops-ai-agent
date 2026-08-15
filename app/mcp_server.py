from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.data.repository import InventoryRepository
from app.domain.models import EvidenceInput, IncidentInput
from app.parsers.aggregate import parse_all_evidence
from app.services.diagnosis import diagnose
from app.services.knowledge import RoutedKnowledgeBase


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
def get_readonly_boundary() -> dict:
    """返回本项目允许和禁止的操作边界。"""
    return {
        "allowed": [
            "查询模拟资源台账",
            "解析用户粘贴的脱敏只读命令输出",
            "生成辅助诊断与排障建议",
            "检索本地知识文档",
        ],
        "forbidden": [
            "连接生产 MSE、网管、交换机或终端",
            "执行配置修改、重启、封禁和自动修复",
            "保存真实账号、密钥、客户信息或设备地址",
        ],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
