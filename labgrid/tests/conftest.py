# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later
import logging

import pytest
from labgrid import ConsoleLoggingReporter
from labgrid.exceptions import NoDriverFoundError
from labgrid.util.qmp import QMPMonitor

from tfw.qemu import read_parse_json_skipping_text, setup_qemu_driver

logger = logging.getLogger(__name__)

ConsoleLoggingReporter.start(".")

# Workaround for QEMU printing non-JSON lines on stdout
# which breaks labgrid's QMPMonitor._read_parse_json.
QMPMonitor._read_parse_json = read_parse_json_skipping_text

# systemctl --wait blocks until the system reaches a final state, so this
# has to cover the rest of the boot and not just a round trip to the shell
TIMEOUT_SYSTEM_RUNNING = 300.0


@pytest.fixture(scope="session")
def target(target):
    """Handle the QEMUDriver setup.

    This is a no-op for targets without a QEMUDriver, such as a real
    labgrid test jig in config/gateway.yaml.
    """
    try:
        driver = target.get_driver("QEMUDriver", activate=False)
        setup_qemu_driver(driver)
    except NoDriverFoundError:
        pass

    return target


@pytest.fixture(scope="session")
def shell(target):
    """Power-cycle the target and log in.

    Cycling on setup rather than cleaning up on teardown keeps the starting
    state independent of whatever a previous run left behind.
    """
    target.get_driver("PowerProtocol").cycle()
    return target.get_driver("ShellDriver")


@pytest.fixture(scope="session")
def gateway_system_is_running(shell):
    stdout, _, exit_code = shell.run(
        "systemctl --wait is-system-running", timeout=TIMEOUT_SYSTEM_RUNNING
    )

    if exit_code != 0:
        logger.error(
            "systemctl --wait is-system-running failed with exit code %d, output: %s",
            exit_code,
            stdout,
        )
    else:
        logger.debug("systemctl --wait is-system-running succeeded")

    yield stdout, exit_code
