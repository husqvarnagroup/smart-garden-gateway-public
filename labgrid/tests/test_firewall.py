import re
from subprocess import run

import pytest

from tfw.network import get_gateway_ip_address
from tfw.utils import remove_or_touch_and_restore_empty_file, set_and_restore_fw_env_var


TCP_PORTS_LOCAL = [22, 80, 443, 8001]
TCP_PORTS_REMOTE = [80, 443, 8001]



@pytest.fixture(scope="module")
def disable_ssh_fw_env_var(shell):
    """Make sure the dev_debug_allow_local_ssh is not set on the gateway."""
    yield set_and_restore_fw_env_var(shell, "dev_debug_allow_local_ssh")


@pytest.fixture(scope="module")
def disable_local_ssh_by_file(shell):
    yield remove_or_touch_and_restore_empty_file(shell, "/etc/allow-local-ssh", touch=False)


@pytest.fixture(scope="module")
def disable_websocketd_by_file(shell):
    yield remove_or_touch_and_restore_empty_file(shell, "/etc/enable-websocketd", touch=False)


@pytest.fixture(scope="module")
def setup_firewall(shell, disable_ssh_fw_env_var, disable_local_ssh_by_file, disable_websocketd_by_file):
    """Restart firewall service on gateway."""
    output, _, exit_code = shell.run("systemctl restart firewall")
    assert exit_code == 0, f"Failed to restart firewall: {output}"

    yield


def test_local_listening_tcp(gateway_reachable_on_network, shell, setup_firewall):
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
def test_remote_listening_tcp(gateway_reachable_on_network, shell, protocol, setup_firewall):
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


def test_netbase_services(gateway_reachable_on_network, shell, setup_firewall):
    """Ensure that netbase is installed and the services file on the gateway contains all expected services.
    They are required by the firewall script.
    """

    output, _, exit_code = shell.run("opkg status netbase 2>/dev/null | grep -q '^Package: netbase$'")
    assert exit_code == 0, f"netbase package is not installed: {output}"

    expected_services = {
        "ssh": 22,
        "http": 80,
        "https": 443,
        "mdns": 5353,
    }

    output, _, exit_code = shell.run("cat /etc/services")
    assert exit_code == 0, f"Failed to read /etc/services: {output}"

    result = "\n".join(output)

    for service, port in expected_services.items():
        pattern = rf"^{service}\s+{port}/.*"
        assert re.search(pattern, result, re.MULTILINE), f"Service {service} with port {port} not found in /etc/services"

