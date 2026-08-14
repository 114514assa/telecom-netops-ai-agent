from enum import Enum


class FaultType(str, Enum):
    NETWORK_DOWN = "network_down"
    OA_SERVICE = "oa_service"
    INTERNET = "internet"
    ADDRESS_MIGRATION = "address_migration"
    ACCESS_UNKNOWN = "access_unknown"
    INTERMITTENT = "intermittent"
    OTHER = "other"


class DiagnosisCode(str, Enum):
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_INCONSISTENCY = "resource_inconsistency"
    PHYSICAL_OR_TERMINAL_LINK = "physical_or_terminal_link"
    L2_NO_MAC = "l2_no_mac"
    VLAN_MISMATCH = "vlan_mismatch"
    TERMINAL_CONFIG = "terminal_config"
    LINK_QUALITY = "link_quality"
    UPLINK_POLICY_OR_APPLICATION = "uplink_policy_or_application"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Layer(str, Enum):
    RESOURCE = "资源数据层"
    TERMINAL = "终端配置层"
    PHYSICAL = "物理链路层"
    L2 = "二层接入层"
    L3 = "三层网络层"
    POLICY = "策略/业务层"
    UNKNOWN = "待补充证据"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
