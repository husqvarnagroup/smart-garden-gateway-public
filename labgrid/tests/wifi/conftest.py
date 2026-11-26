# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fixtures that join the gateway's AP from inside a Docker container.

A dedicated adapter on the host is moved into the network namespace of a
container. The host's own networking and routing stay untouched. When the
container ends, the kernel returns the adapter to the host.

The settings are options of the labgrid target. See the README for the
list.
"""

import io
import ipaddress
import logging
import os
import re
import tarfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import docker
import pytest
from docker.errors import ContainerError, DockerException, NotFound
from docker.models.containers import Container

logger = logging.getLogger(__name__)

IMAGE_TAG = "wifi-tests"
WPA_CONF = "/tmp/wpa.conf"
WPA_LOG = "/tmp/wpa.log"

GATEWAY_AP_IFACE = "wlan0"
GATEWAY_AP_TIMEOUT = 120
# The AP may show up only some time after hostapd has started.
GATEWAY_AP_SCAN_TIMEOUT = 120
GATEWAY_ETH_IFACE = "eth0"

container_key = pytest.StashKey["WifiContainer"]()


@dataclass
class WifiConfig:
    host_iface: str
    assoc_timeout: float
    dhcp_timeout: int


@dataclass
class WifiContainer:
    container: Container
    iface: str

    def run(self, *cmd):
        """Runs a command in the container and returns its exit code and output."""
        exit_code, output = self.container.exec_run(list(cmd))
        return exit_code, output.decode(errors="replace")

    def check(self, *cmd):
        """Runs a command in the container and fails the test if it fails."""
        exit_code, output = self.run(*cmd)
        if exit_code != 0:
            pytest.fail(f"{' '.join(cmd)} failed with exit code {exit_code}:\n{output}")
        return output

    def put_file(self, path, content):
        """Writes a file into the container."""
        data = content.encode()
        info = tarfile.TarInfo(Path(path).name)
        info.size = len(data)
        info.mode = 0o600
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            tar.addfile(info, io.BytesIO(data))
        self.container.put_archive(str(Path(path).parent), archive.getvalue())

    def wpa_status(self):
        """Returns the output of wpa_cli status as a dictionary."""
        _, output = self.run("wpa_cli", "-i", self.iface, "status")
        status = {}
        for line in output.splitlines():
            key, sep, value = line.partition("=")
            if sep:
                status[key] = value
        return status


@dataclass
class WifiLease:
    iface: str
    ssid: str
    bssid: str
    ip: ipaddress.IPv4Address
    prefix: int
    gateway: ipaddress.IPv4Address | None


def docker_client():
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as e:
        pytest.skip(f"Docker is not reachable: {e}")
    return client


@pytest.fixture(scope="session", autouse=True)
def wifi_config(target):
    """Reads the Wi-Fi settings and skips if the adapter is missing.

    The adapter is taken from LG_WIFI_IFACE, or else from the target option
    wifi_host_iface. The other settings are target options. This fixture is
    autouse, so the check runs before the gateway boots.
    """

    def option(name, default):
        return target.env.config.get_target_option(target.name, name, default)

    host_iface = os.environ.get("LG_WIFI_IFACE") or option("wifi_host_iface", "")
    if not host_iface:
        pytest.skip("Set LG_WIFI_IFACE to the Wi-Fi adapter of the test host")
    if not Path(f"/sys/class/net/{host_iface}/phy80211").exists():
        pytest.skip(f"No Wi-Fi interface {host_iface} on the host")
    docker_client()

    return WifiConfig(
        host_iface=host_iface,
        assoc_timeout=float(option("wifi_assoc_timeout", 30)),
        dhcp_timeout=int(option("wifi_dhcp_timeout", 20)),
    )


@pytest.fixture(scope="session")
def wifi_container(pytestconfig, wifi_config):
    """Starts a container that holds the Wi-Fi adapter."""
    client = docker_client()

    host_iface = wifi_config.host_iface
    phy = Path(f"/sys/class/net/{host_iface}/phy80211/name").read_text().strip()

    client.images.build(path=str(Path(__file__).parent), tag=IMAGE_TAG, rm=True)

    container = client.containers.run(
        IMAGE_TAG,
        ["sleep", "infinity"],
        detach=True,
        remove=True,
        network_mode="none",
        cap_add=["NET_ADMIN", "NET_RAW"],
    )
    try:
        container.reload()
        pid = container.attrs["State"]["Pid"]

        # iw resolves the PID in its own PID namespace, hence pid_mode="host".
        logger.info(
            "Moving %s (%s) into container %s", host_iface, phy, container.short_id
        )
        try:
            client.containers.run(
                IMAGE_TAG,
                ["iw", "phy", phy, "set", "netns", str(pid)],
                remove=True,
                privileged=True,
                network_mode="host",
                pid_mode="host",
            )
        except ContainerError as e:
            pytest.fail(
                f"Moving {phy} into the container failed:\n{e.stderr.decode(errors='replace')}"
            )

        # The interface name may differ from the one on the host. The
        # namespace may also hold other interfaces, e.g. tunl0.
        wifi = WifiContainer(container, "")
        for iface in wifi.check("ls", "/sys/class/net").split():
            exit_code, name = wifi.run("cat", f"/sys/class/net/{iface}/phy80211/name")
            if exit_code == 0 and name.strip() == phy:
                wifi.iface = iface
                break
        else:
            pytest.fail(f"No interface of {phy} in the container")
        logger.info("Wi-Fi interface in the container: %s", wifi.iface)

        pytestconfig.stash[container_key] = wifi
        yield wifi
    finally:
        if container_key in pytestconfig.stash:
            del pytestconfig.stash[container_key]
        # kill() and not stop(), because sleep ignores SIGTERM as PID 1.
        try:
            container.kill()
        except NotFound:
            pass


def wpa_config(ssid):
    """Returns a wpa_supplicant configuration for an open network.

    The SSID is written in hex, so it may contain any character.
    """
    return (
        "ctrl_interface=/run/wpa_supplicant\n\n"
        f"network={{\n    ssid={ssid.encode().hex()}\n    key_mgmt=NONE\n}}\n"
    )


def parse_lease(wifi):
    output = wifi.check("ip", "-4", "-o", "addr", "show", "dev", wifi.iface)
    for line in output.splitlines():
        fields = line.split()
        if "inet" in fields:
            interface = ipaddress.ip_interface(fields[fields.index("inet") + 1])
            break
    else:
        pytest.fail(f"No IPv4 address on {wifi.iface}:\n{output}")

    gateway = None
    output = wifi.check("ip", "-4", "route", "show", "default")
    for line in output.splitlines():
        fields = line.split()
        if "via" in fields:
            gateway = ipaddress.ip_address(fields[fields.index("via") + 1])
            break

    status = wifi.wpa_status()
    return WifiLease(
        iface=wifi.iface,
        ssid=status.get("ssid", ""),
        bssid=status.get("bssid", ""),
        ip=interface.ip,
        prefix=interface.network.prefixlen,
        gateway=gateway,
    )


@contextmanager
def connect(wifi, config, ssid):
    """Joins an open Wi-Fi network and gets an IPv4 address over DHCP."""
    wifi.put_file(WPA_CONF, wpa_config(ssid))

    try:
        # Alpine's wpa_supplicant is built without -f, so the output is
        # redirected to the log instead.
        wifi.container.exec_run(
            [
                "sh",
                "-c",
                f"exec wpa_supplicant -i {wifi.iface} -c {WPA_CONF} -dd -t"
                f" > {WPA_LOG} 2>&1",
            ],
            detach=True,
        )

        deadline = time.monotonic() + config.assoc_timeout
        while wifi.wpa_status().get("wpa_state") != "COMPLETED":
            if wifi.run("pgrep", "-f", "wpa_supplicant")[0] != 0:
                pytest.fail("wpa_supplicant exited")
            if time.monotonic() > deadline:
                pytest.fail(
                    f"No association with {ssid!r} within {config.assoc_timeout} s"
                )
            time.sleep(0.5)
        logger.info("Associated with %s", ssid)

        # -n exits with an error if there is no lease. -q exits after getting one.
        wifi.check(
            "timeout",
            str(config.dhcp_timeout),
            "udhcpc",
            "-i",
            wifi.iface,
            "-n",
            "-q",
            "-t",
            "5",
            "-T",
            "3",
        )

        lease = parse_lease(wifi)
        logger.info("Got lease %s", lease)
        yield lease
    finally:
        wifi.run("pkill", "wpa_supplicant")
        wifi.run("ip", "addr", "flush", "dev", wifi.iface)


def gateway_ap_ssid(hostname):
    """Returns the SSID of the gateway's AP, e.g. GARDENA_config(004cdf).

    The hostname has the form GARDENA-004cdf.
    """
    match = re.fullmatch(r"GARDENA-([0-9a-f]{6})", hostname)
    if not match:
        pytest.fail(f"Unexpected hostname {hostname!r}")
    return f"GARDENA_config({match.group(1)})"


@pytest.fixture(scope="session")
def gateway_iperf3(gateway_system_is_running, shell):
    """Installs iperf3 on the gateway from the opkg feed.

    The gateway runs the iperf3 client. The installation needs Ethernet, so it has to run before the AP is started.
    """
    _, _, exit_code = shell.run("command -v iperf3")
    if exit_code != 0:
        shell.run_check("opkg update && opkg install iperf3", timeout=300)


@pytest.fixture(scope="session")
def gateway_ap(gateway_iperf3, shell):
    """Starts the AP of the gateway and returns its SSID.

    The accessory-server only opens the AP if there is no Ethernet
    connection, so eth0 is set down first. The AP has no password.
    """
    shell.run_check(f"ip link set {GATEWAY_ETH_IFACE} down")
    try:
        shell.run_check("systemctl restart accessory-server")
        deadline = time.monotonic() + GATEWAY_AP_TIMEOUT
        while True:
            _, _, exit_code = shell.run(
                f"systemctl is-active --quiet hostapd@{GATEWAY_AP_IFACE}"
            )
            if exit_code == 0:
                break
            if time.monotonic() > deadline:
                pytest.fail(
                    f"The gateway is not in AP mode after {GATEWAY_AP_TIMEOUT} s"
                )
            time.sleep(2)

        ssid = gateway_ap_ssid(shell.run_check("hostname")[0].strip())
        logger.info("Gateway AP: %s", ssid)
        yield ssid
    finally:
        shell.run(f"ip link set {GATEWAY_ETH_IFACE} up")


@pytest.fixture
def iperf3_server(wifi_container):
    """Runs an iperf3 server in the container.

    The gateway runs the client. This way, its firewall needs no changes,
    because it accepts the replies to connections it opened.
    """
    wifi_container.container.exec_run(["iperf3", "--server"], detach=True)
    deadline = time.monotonic() + 10
    while wifi_container.run("sh", "-c", "netstat -ltn | grep -q :5201")[0] != 0:
        if time.monotonic() > deadline:
            pytest.fail("The iperf3 server did not start")
        time.sleep(0.5)
    try:
        yield
    finally:
        wifi_container.run("pkill", "iperf3")


def wait_for_ssid(wifi, ssid, timeout):
    """Scans until a network with the SSID shows up."""
    wifi.check("ip", "link", "set", wifi.iface, "up")
    start = time.monotonic()
    while True:
        # The scan fails while the interface is busy, so failures are retried.
        exit_code, output = wifi.run("iw", "dev", wifi.iface, "scan")
        if exit_code == 0 and f"SSID: {ssid}" in map(str.strip, output.splitlines()):
            break
        if time.monotonic() - start > timeout:
            pytest.fail(f"{ssid!r} did not show up in a scan within {timeout} s")
        time.sleep(2)
    logger.info("%s showed up after %.0f s", ssid, time.monotonic() - start)


@pytest.fixture
def ap_connection(wifi_config, wifi_container, gateway_ap):
    """Joins the AP of the gateway."""
    wait_for_ssid(wifi_container, gateway_ap, GATEWAY_AP_SCAN_TIMEOUT)
    with connect(wifi_container, wifi_config, gateway_ap) as lease:
        yield lease


def diagnostics(wifi):
    sections = []
    for title, cmd in (
        ("wpa_supplicant log", ["tail", "-n", "200", WPA_LOG]),
        ("wpa_cli scan_results", ["wpa_cli", "-i", wifi.iface, "scan_results"]),
        ("ip addr", ["ip", "addr"]),
        ("ip route", ["ip", "route"]),
        ("iw link", ["iw", "dev", wifi.iface, "link"]),
    ):
        try:
            _, output = wifi.run(*cmd)
        except DockerException as e:
            output = str(e)
        sections.append(f"--- {title} ---\n{output}")
    return "\n".join(sections)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Attaches diagnostics from the container to failed Wi-Fi tests."""
    report = yield
    if report.when in ("setup", "call") and report.failed:
        wifi = item.config.stash.get(container_key, None)
        if wifi is not None and wifi.iface:
            report.sections.append(("Wi-Fi diagnostics", diagnostics(wifi)))
    return report
