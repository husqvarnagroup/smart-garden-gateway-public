# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import ipaddress
import json

import pytest

pytestmark = pytest.mark.lg_feature("wifi")

# Address and DHCP range of the gateway's AP. See dnsmasq@.service and
# dnsmasq.d/wlan0/gardena.conf in meta-distribution.
GATEWAY_AP_ADDRESS = ipaddress.ip_address("10.0.0.1")
GATEWAY_AP_DHCP_FIRST = ipaddress.ip_address("10.0.0.2")
GATEWAY_AP_DHCP_LAST = ipaddress.ip_address("10.0.0.254")
GATEWAY_AP_PREFIX = 24

IPERF3_DURATION = 10
# The throughput required in each direction, in bits per second.
MIN_THROUGHPUT = 4e6


def iperf3_throughput(shell, server, reverse):
    """Runs the iperf3 client on the gateway and returns the bits per second."""
    cmd = f"iperf3 --client {server} --json --time {IPERF3_DURATION}"
    if reverse:
        cmd += " --reverse"
    output = shell.run_check(cmd, timeout=IPERF3_DURATION + 30)
    return json.loads("\n".join(output))["end"]["sum_received"]["bits_per_second"]


def test_ap(shell, gateway_ap, wifi_container, ap_connection, iperf3_server):
    lease = ap_connection
    ssid = gateway_ap

    assert lease.ssid == ssid
    assert GATEWAY_AP_DHCP_FIRST <= lease.ip <= GATEWAY_AP_DHCP_LAST
    assert lease.prefix == GATEWAY_AP_PREFIX
    assert lease.gateway == GATEWAY_AP_ADDRESS

    wifi_container.check("ping", "-c", "3", "-W", "2", str(GATEWAY_AP_ADDRESS))

    from_gateway = iperf3_throughput(shell, lease.ip, reverse=False)
    to_gateway = iperf3_throughput(shell, lease.ip, reverse=True)
    print(
        f"Throughput: {from_gateway / 1e6:.1f} Mbit/s from the gateway, "
        f"{to_gateway / 1e6:.1f} Mbit/s to the gateway"
    )
    assert from_gateway > MIN_THROUGHPUT
    assert to_gateway > MIN_THROUGHPUT
