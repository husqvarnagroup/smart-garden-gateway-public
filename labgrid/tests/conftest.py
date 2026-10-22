# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later
import configparser
import json
import logging
from pathlib import Path

import pytest
from labgrid import ConsoleLoggingReporter
from labgrid.exceptions import NoDriverFoundError
from labgrid.util.qmp import QMPError, QMPMonitor

logger = logging.getLogger(__name__)

ConsoleLoggingReporter.start(".")


# QEMU prints plain text on stdout, and labgrid reads QMP from stdout (-qmp stdio).
# labgrid parses every line as JSON, so one stray line breaks the next QMP command.
# Remove this once labgrid skips non-JSON lines.
def read_parse_json_skipping_text(self):
    while True:
        line = self.monitor_out.readline().decode("utf-8")
        self.logger.debug("Received line: %s", line.rstrip("\r\n"))
        if not line:
            raise QMPError("Received empty response")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            self.logger.warning("Skipped non-JSON line on QMP stream: %s", line.rstrip("\r\n"))


QMPMonitor._read_parse_json = read_parse_json_skipping_text

# systemctl --wait blocks until the system reaches a final state, so this
# has to cover the rest of the boot and not just a round trip to the shell
TIMEOUT_SYSTEM_RUNNING = 300.0

DEPLOY_DIR = (
    Path(__file__).parent.parent.parent
    / "build-qemuarm"
    / "tmp"
    / "deploy"
    / "images"
    / "gardena-sg-qemuarm"
)

def read_qemuboot_conf():
    conf_file_path = DEPLOY_DIR / "gardena-image-foss-bnw-gardena-sg-qemuarm.qemuboot.conf"
    conf = configparser.ConfigParser()
    conf.read(conf_file_path)
    return dict(conf["config_bsp"])


def setup_qemu_driver(driver):
    """Fill in the QEMUDriver fields that come from the build's own configuration file.

    Runs before the driver is first activated, so qemu_bin, machine and
    memory never hold their qemu.yaml placeholder values at boot time.
    """

    bsp = read_qemuboot_conf()
    driver.machine = bsp["qb_machine"].removeprefix("-machine ")
    driver.memory = bsp["qb_mem"].removeprefix("-m ")
    driver.qemu_bin = str(
        (DEPLOY_DIR / bsp["staging_bindir_native"] / bsp["qb_system_name"]).resolve()
    )
    image = DEPLOY_DIR / f"{bsp['image_link_name']}.ext4"
    driver.extra_args = f"-drive file={image},if=virtio,format=raw"


@pytest.fixture(scope="session")
def target(target):
    """Handle the QEMUDriver setup.

    This is a no-op for targets without a QEMUDriver, such as the real
    bench in config/gateway.yaml.
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
