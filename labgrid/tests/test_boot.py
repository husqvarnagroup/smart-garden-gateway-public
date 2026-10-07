# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

# systemctl --wait blocks until the system reaches a final state, so this
# has to cover the rest of the boot and not just a round trip to the shell
TIMEOUT_SYSTEM_RUNNING = 300.0


def test_system_running(shell):
    """The gateway boots and systemd reaches the running state."""
    stdout, _, exit_code = shell.run(
        "systemctl --wait is-system-running", timeout=TIMEOUT_SYSTEM_RUNNING
    )

    # is-system-running only names the aggregate state, so say which units
    # are responsible for it
    failed, _, _ = shell.run("systemctl --failed --no-legend --plain")

    assert exit_code == 0, (
        f"system state is {' '.join(stdout)}, failed units: {'; '.join(failed)}"
    )
