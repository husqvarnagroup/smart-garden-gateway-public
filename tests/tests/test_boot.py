# SPDX-FileCopyrightText: GARDENA GmbH

# SPDX-License-Identifier: GPL-3.0-or-later

import os

import pytest


def test_system_running(gateway_system_is_running, shell, env):
    """The gateway boots and systemd reaches the running state."""
    stdout, exit_code = gateway_system_is_running

    # is-system-running only names the aggregate state, so say which units
    # are responsible for it
    failed, _, _ = shell.run("systemctl --failed --no-legend --plain")

    if os.path.basename(env.config_file) == "qemu.yaml":
        # QEMU has no radio module, so reset-rm.service and
        # rm-flashing.service always fail and systemd never reaches
        # "running". Revisit once QEMU gets a stub for the radio module.
        pytest.xfail(
            f"QEMU has no radio module, system state is {' '.join(stdout)}, "
            f"failed units: {'; '.join(failed)}"
        )

    assert exit_code == 0, (
        f"system state is {' '.join(stdout)}, failed units: {'; '.join(failed)}"
    )
