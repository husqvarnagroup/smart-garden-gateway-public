# SPDX-FileCopyrightText: GARDENA GmbH

# SPDX-License-Identifier: GPL-3.0-or-later


def test_system_running(gateway_system_is_running, shell):
    """The gateway boots and systemd reaches the running state."""
    stdout, exit_code = gateway_system_is_running

    # is-system-running only names the aggregate state, so say which units
    # are responsible for it
    failed, _, _ = shell.run("systemctl --failed --no-legend --plain")

    assert exit_code == 0, (
        f"system state is {' '.join(stdout)}, failed units: {'; '.join(failed)}"
    )
