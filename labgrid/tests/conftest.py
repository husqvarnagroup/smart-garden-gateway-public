# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

import pytest
from labgrid.driver import QEMUDriver

from qemuboot_conf import read_qemuboot_conf

logger = logging.getLogger(__name__)

# systemctl --wait blocks until the system reaches a final state, so this
# has to cover the rest of the boot and not just a round trip to the shell
TIMEOUT_SYSTEM_RUNNING = 300.0


@pytest.fixture(scope="session")
def target(env):
    """Return the "main" target.

    For the QEMU target, this also fills in QEMUDriver's qemu_bin,
    machine, memory, disk and boot_args from the Yocto build's own
    *.qemuboot.conf (see qemuboot_conf.py), so they cannot drift from a
    future board or image change. This has to run before the driver
    activates, so it fetches the driver with activate=False; the "shell"
    fixture's later get_driver() call is what actually activates it.
    """
    target = env.get_target()
    if target is None:
        raise RuntimeError('No target "main" in config')

    if os.path.basename(env.config_file) != "qemu.yaml":
        return target

    qemu = target.get_driver(QEMUDriver, activate=False)
    deploy_dir = os.environ["LG_DEPLOY_DIR"]
    bsp = read_qemuboot_conf(deploy_dir)

    # scripts/runqemu.sh does not use any system-wide qemu-system-arm; it
    # runs the one the Yocto build produced for itself, at this path
    # relative to the deploy dir (staging_bindir_native + qb_system_name).
    qemu.qemu_bin = os.path.normpath(
        os.path.join(deploy_dir, bsp["staging_bindir_native"], bsp["qb_system_name"])
    )
    qemu.machine = bsp["qb_machine"].removeprefix("-machine").strip()
    qemu.memory = bsp["qb_mem"].removeprefix("-m").strip() + "M"
    # scripts/runqemu.sh attaches the same image with "if=virtio",
    # producing /dev/vda, regardless of qb_drive_type: a SCSI-attached
    # disk (what qb_drive_type's "/dev/sd" would suggest) left the kernel
    # waiting forever for a root device it never recognized.
    qemu.extra_args = (
        f"-drive if=virtio,file={deploy_dir}/{bsp['image_link_name']}.ext4,format=raw"
    )
    # net.ifnames=0 (qb_no_pni) keeps the interface named eth0, which is
    # what unique-hostname reads to build the GARDENA-<id> hostname
    qemu.boot_args = (
        f"root=/dev/vda rw {bsp['qb_kernel_cmdline_append']} "
        f"console=ttyAMA0,115200 {bsp['qb_no_pni']}"
    )

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
