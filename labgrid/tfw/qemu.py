import configparser
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fake_rm import DEFAULT_MAC, FakeRadioModule
from labgrid.util.qmp import QMPError

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
BUILD_DIR = REPO_ROOT / "build-qemuarm"

DEPLOY_DIR = BUILD_DIR / "tmp" / "deploy" / "images" / "gardena-sg-qemuarm"


@contextmanager
def qemu_test_environment_setup(target):
    """Set up a FakeRadioModule and a QEMUDriver for the test session.

    This is a no-op for targets without the 'qemu' feature, such as a real
    labgrid test jig in config/gateway.yaml.
    """
    if is_qemu_test_environment(target):
        logger.debug("Setting up QEMU test environment")
        with TemporaryDirectory() as socket_dir:
            radio_module_socket = Path(socket_dir) / "fake-rm.sock"
            with radio_module_simulation(radio_module_socket):
                driver = target.get_driver("QEMUDriver", activate=False)
                setup_qemu_driver(driver, radio_module_socket)
                yield target
    else:
        yield target


def is_qemu_test_environment(target):
    """Return True if the target config has the feature 'qemu'."""
    features = target.env.config.data.get("features")
    return features and "qemu" in features


@contextmanager
def radio_module_simulation(radio_module_socket):
    """Start a FakeRadioModule.

    The socket path is passed to QEMUDriver to connect the guest's serial port
    to the simulation.
    """
    rm_sim = FakeRadioModule(str(radio_module_socket), mac=DEFAULT_MAC)
    rm_sim.start()
    logger.info("Started radio module simulation")
    try:
        yield
    finally:
        rm_sim.stop()
        logger.info("Stopped radio module simulation")


def setup_qemu_driver(driver, radio_module_socket):
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
    add_radio_module_serial(driver, radio_module_socket)


def read_qemuboot_conf():
    conf_file_path = (
        DEPLOY_DIR / "gardena-image-foss-bnw-gardena-sg-qemuarm.qemuboot.conf"
    )
    if not conf_file_path.is_file():
        raise FileNotFoundError(
            f"No QEMU boot configuration at {conf_file_path}. Build the image first."
        )
    conf = configparser.ConfigParser()
    logger.debug("Reading QEMU boot configuration from %s", conf_file_path)
    conf.read(conf_file_path)
    return dict(conf["config_bsp"])


def setup_kernel_boot_args(bsp: dict[str, str], driver):
    """Fill in the QEMUDriver boot_args field. Most of it comes from the qemuarm
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


def add_radio_module_serial(driver, radio_module_socket):
    """Connect the radio module socket as QEMU's second serial port.

    labgrid appends its console serial port after extra_args, so the radio
    module port must be added after labgrid built the command line. The console
    stays on ttyAMA0 and the radio module on ttyAMA1.
    """

    on_activate = driver.on_activate

    def on_activate_with_radio_module():
        on_activate()
        driver._cmd.extend(
            ["-serial", f"unix:{radio_module_socket},server=on,wait=off"]
        )

    driver.on_activate = on_activate_with_radio_module


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
