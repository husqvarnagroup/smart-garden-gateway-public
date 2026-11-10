import ipaddress
from subprocess import run

import pytest

from tfw.network import ping_gateway, get_gateway_ip_address


def test_gateway_network_active(gateway_network_active):
    assert gateway_network_active

TCP_PORTS_LOCAL = [22, 80, 443, 8001]
TCP_PORTS_REMOTE = [80, 443, 8001]
UDP_PORTS_REMOTE = [5353]


@pytest.fixture(scope="module")
def get_open_udp_sockets(shell):
    """Get listening udp sockets on DUT."""
    # gather information about open udp sockets
    output, _, exit_code = shell.run("netstat -lun\n")

    test_port_v4 = set()
    test_port_v6 = set()
    for line in output[3:]:
        proto, _recvq, _sendq, local, _foreign = line.split()

        assert proto == 'udp'
        ip_addr = ipaddress.ip_address(":".join(local.split(':')[:-1]))
        port = local.split(':')[-1]
        if ip_addr.version == 4:
            test_port_v4.add(port)
        elif ip_addr.version == 6:
            test_port_v6.add(port)

    return {'ipv4': test_port_v4, 'ipv6': test_port_v6}


def test_local_listening_tcp(gateway_reachable_on_network, shell):
    """Ensure no unexpected and all expected TCP sockets are listening locally.
    This test is inspired by the internal Gardena test jig.
    """
    found_ports = set()

    result, _, exit_code = shell.run("netstat -ltn\r\n")
    assert exit_code == 0, f"netstat -ltn failed with exit code {exit_code}: {result}"

    # check for unexpected ports
    for line in result[2:]:
        proto, _recvq, _sendq, local, _foreign, state = line.split()

        assert proto == 'tcp'
        assert state == 'LISTEN'
        port = int(local.split(':')[-1])
        found_ports.add(port)
        assert port in TCP_PORTS_LOCAL, f"Unexpected TCP port found listening on gateway: {port}"

    # check all expected ports are open
    for port in TCP_PORTS_LOCAL:
        assert port in found_ports, f"Expected TCP port {port} not found listening on gateway"


@pytest.mark.parametrize("protocol", ['ipv4', 'ipv6'])
def test_remote_listening_tcp(gateway_reachable_on_network, shell, protocol):
    """Ensure no unexpected and all expected TCP processes are reachable from a remote host on LAN.
    This test is inspired by the internal Gardena test jig.
    Note: this test requires nmap to be installed on the test runner (host)."""
    found_ports = set()

    # run nmap on host
    # -6 IPv6 run
    # -p 0-65535 full TCP port range
    # -T4 aggressive mode, faster scan on reliable network
    if protocol == "ipv4":
        ipv4_address = get_gateway_ip_address(shell, protocol="ipv4")
        cmd = f"nmap {ipv4_address} -p 0-65535 -T4".split()
        result = run(cmd, capture_output=True, check=True)
    elif protocol == "ipv6":
        ipv6_address = get_gateway_ip_address(shell, protocol="ipv6")
        cmd = f"nmap -6 {ipv6_address} -p 0-65535 -T4".split()
        result = run(cmd, capture_output=True, check=True)
    else:
        raise RuntimeError

    for line in result.stdout.split(b"\n"):
        columns = line.decode('utf-8').split()

        if len(columns) == 0:
            continue
        if columns[0] not in ['Starting', 'Nmap', 'Host', 'Not', 'PORT']:
            port = int(columns[0].split('/')[0])
            found_ports.add(port)
            assert port in TCP_PORTS_REMOTE, f"Unexpected open TCP port found: {port}"

    # check all expected ports open
    for port in TCP_PORTS_REMOTE:
        assert port in found_ports, f"Expected TCP port {port} not found open on gateway"
