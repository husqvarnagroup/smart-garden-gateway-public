import configparser
import json
from pathlib import Path

from labgrid.util.qmp import QMPError

DEPLOY_DIR = (
    Path(__file__).parent.parent.parent
    / "build-qemuarm"
    / "tmp"
    / "deploy"
    / "images"
    / "gardena-sg-qemuarm"
)


def read_qemuboot_conf():
    conf_file_path = (
        DEPLOY_DIR / "gardena-image-foss-bnw-gardena-sg-qemuarm.qemuboot.conf"
    )
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

    setup_kernel_boot_args(bsp, driver)


def setup_kernel_boot_args(bsp: dict[str, str], driver):
    """Fill in the QEMUDriver boot_args field. Most of it comes from the qeumuarm
    build's configuration file.
    """

    # The drive is a 'virtio' ext4 disk, this is provided by the labgrid QEMUDriver, but the
    # kernel command line needs to know where to find the root filesystem.
    boot_args = ["root=/dev/vda rw"]

    # the serial port in the conf file is in the format: serial_consoles = 115200;ttyAMA0
    # we need to convert it to the format that qemu expects: console=ttyAMA0,115200
    serial_console = bsp["serial_consoles"].split(";")
    assert len(serial_console) == 2
    boot_args.append(f"console={serial_console[1]},{serial_console[0]}")

    # 'qb_no_pni' contains something like 'net.ifnames=0' which keeps the interface named 'eth0'.
    # This is what unique-hostname reads to build the GARDENA-<id> hostname.
    boot_args.append(bsp["qb_no_pni"])

    # Append the rest of the kernel command line.
    boot_args.append(bsp["qb_kernel_cmdline_append"])

    driver.boot_args = " ".join(boot_args)


def read_parse_json_skipping_text(self):
    """QEMU prints plain text on stdout, and labgrid reads QMP from stdout (-qmp stdio).
    labgrid parses every line as JSON, so one stray line breaks the next QMP command.
    Possible fix in labgrid:
    https://github.com/labgrid-project/labgrid/pull/2022
    """

    while True:
        line = self.monitor_out.readline().decode("utf-8")
        self.logger.debug("Received line: %s", line.rstrip("\r\n"))
        if not line:
            raise QMPError("Received empty response")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            self.logger.warning(
                "Skipped non-JSON line on QMP stream: %s", line.rstrip("\r\n")
            )
