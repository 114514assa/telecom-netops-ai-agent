from app.parsers.arp import parse_arp_output
from app.parsers.interface import parse_interface_output
from app.parsers.mac import parse_mac_output
from app.parsers.terminal import parse_terminal_output
from app.parsers.vlan import parse_vlan_output


def test_interface_down():
    result = parse_interface_output(
        "GigabitEthernet0/0/10 current state : DOWN\nLine protocol current state : DOWN"
    )
    assert result.status == "DOWN"
    assert result.protocol_status == "DOWN"


def test_mac_target_found():
    result = parse_mac_output("200 0011-2233-4415 dynamic GE0/0/15", "00:11:22:33:44:15")
    assert result.target_found is True
    assert result.vlan == 200
    assert result.learned_port == "GE0/0/15"


def test_vlan_access():
    result = parse_vlan_output("port link-type access\nport default vlan 210\nundo shutdown")
    assert result.link_type == "access"
    assert result.access_vlan == 210
    assert result.interface_shutdown is False


def test_terminal_parse():
    result = parse_terminal_output(
        "IPv4 Address : 10.20.30.15\nDefault Gateway : 10.20.30.1\n"
        "DNS Servers : 10.20.0.53\nPhysical Address : 00-11-22-33-44-15\nRequest timed out."
    )
    assert result.ip_address == "10.20.30.15"
    assert result.gateway == "10.20.30.1"
    assert result.mac_address == "00:11:22:33:44:15"
    assert result.ping_success is False


def test_arp_target_found():
    result = parse_arp_output("10.20.30.15 0011-2233-4415 dynamic Vlanif200", "10.20.30.15")
    assert result.target_found is True
    assert result.mac_address == "00:11:22:33:44:15"
    assert result.interface == "Vlanif200"
