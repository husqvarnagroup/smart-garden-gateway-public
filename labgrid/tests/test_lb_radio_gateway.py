"""Test the lb_radio_gateway client tool. For simplicity, only a subset of the commands are tested.
The radio-module firmware might omit some functions, due to memory constraints on the SiM3U."""

import re

import pytest


def run_lb_radio_gateway_command(shell, args):
    """Run a lb_radio_gateway command and return the output."""
    base_command = "/usr/bin/lb_radio_gateway -u /run/lemonbeatd/radiomodule_api"
    command = f"{base_command} {args}"
    stdout, _, exit_code = shell.run(command)
    assert exit_code == 0, (
        f"lb_radio_gateway command '{command}' failed with exit code {exit_code}"
    )
    stdout = [line for line in stdout if line.strip()]
    return "\n".join(stdout)


def test_lb_radio_gateway_api_healthcheck(gateway_system_is_running, shell):
    """The gateway healthcheck script exits reports successful lb_radio_gateway client check.
    Note: We are only testing the lb_radio_gateway client here."""
    stdout, _, _ = shell.run("/usr/bin/healthcheck")
    stdout = [line for line in stdout if line.strip()]
    stdout = "\n".join(stdout)
    assert "OK: [lb_radio_gateway_api] result=0" in stdout, (
        f"healthcheck failed:\n{stdout}"
    )


def test_lb_radio_gateway_api_list_commands(gateway_system_is_running, shell):
    """Test that the lb_radio_gateway client lists some expected commands."""
    stdout = run_lb_radio_gateway_command(shell, "-l")

    # Just check that some commands are listed, not that the list is complete.
    expected_commands = [
        "get_antenna_diversity",
        "get_antenna_diversity_mode",
        "get_antenna_int_ext",
        "get_app_version",
        "get_lb_radio_driver_state",
        "get_mac_address",
        "get_network_key",
        "get_stack_usage",
        "get_stats",
    ]
    for command in expected_commands:
        assert command in stdout, (
            f"lb_radio_gateway command '-l' failed to list command '{command}':\n{stdout}"
        )


@pytest.mark.parametrize(
    "command",
    [
        "get_antenna_diversity",
        "get_antenna_diversity_mode",
        "get_antenna_int_ext",
    ],
)
def test_lb_radio_gateway_api_returning_digit(
    gateway_system_is_running, shell, command
):
    stdout = run_lb_radio_gateway_command(shell, command)
    assert re.match(r"^\d$", stdout), (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )


def test_lb_radio_gateway_api_get_lb_radio_driver_state(
    gateway_system_is_running, shell
):
    command = "get_lb_radio_driver_state"
    stdout = run_lb_radio_gateway_command(shell, command)
    assert "n/a" == stdout, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )


def test_lb_radio_gateway_api_get_get_app_version(gateway_system_is_running, shell):
    command = "get_app_version"
    stdout = run_lb_radio_gateway_command(shell, command)
    version = stdout.split(".")
    assert len(version) == 3, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    for d in version:
        assert d.isdigit(), (
            f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
        )


def test_lb_radio_gateway_api_get_mac_address(gateway_system_is_running, shell):
    command = "get_mac_address"
    stdout = run_lb_radio_gateway_command(shell, command)
    mac_address = stdout.split(":")
    assert len(mac_address) == 6, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    for d in mac_address:
        assert 0 <= int(d, 16) <= 255, (
            f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
        )


def test_lb_radio_gateway_api_get_network_key(gateway_system_is_running, shell):
    command = "get_network_key"
    stdout = run_lb_radio_gateway_command(shell, command)
    assert len(stdout) == 32, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    assert all(c in "0123456789abcdef" for c in stdout), (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )


def test_lb_radio_gateway_api_get_stack_usage(gateway_system_is_running, shell):
    command = "get_stack_usage"
    stdout = run_lb_radio_gateway_command(shell, command)
    assert re.match(r"^si4467@=\d+%$", stdout), (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )


def test_lb_radio_gateway_api_get_stats(gateway_system_is_running, shell):
    command = "get_stats"
    stdout = run_lb_radio_gateway_command(shell, command)

    assert "MAC ACK RSSI" in stdout, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    assert "Measured RSSI" in stdout, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    assert "RX" in stdout, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
    assert "TX" in stdout, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )


def test_lb_radio_gateway_api_get_uptime(gateway_system_is_running, shell):
    command = "get_uptime"
    stdout = run_lb_radio_gateway_command(shell, command)
    assert int(stdout) > 0, (
        f"lb_radio_gateway command '{command}' returned unexpected value: {stdout}"
    )
