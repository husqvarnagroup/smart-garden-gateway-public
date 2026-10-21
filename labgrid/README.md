# Overview

This directory contains tests for the GARDENA smart Gateway that drive the
gateway over its serial console with [labgrid](https://labgrid.readthedocs.io/).

Only a serial adapter whose RTS line switches the gateway's power is 
required to run the tests on a real gateway.

It's expected that the test run on a Linux machine.

## Flashing the Gateway

Currently there is no strategy implemented in labgrid that flashes an image to the gateway. So
it's necessary to update the gateway manually to the desired image before running the tests.

## Quick Start

### Configure Serial Adapter

To use a custom serial adapter change the serial port in `config/gateway.yaml` to the one in use.

### Setup Test Project


Install poetry first:

```
sudo apt install python3-poetry
```

or if `pipx` is available:

```
pipx install poetry
```

Install project dependencies:

```
cd labgrid
poetry env use 3.12
poetry install
```

### Run Tests

```
poetry run pytest --lg-env config/gateway.yaml tests/
```

## Running against QEMU

The suite runs without the bench against a QEMU instance of the same image.
Build the image first, then select the QEMU environment:

    ./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr
    cd labgrid
    poetry run pytest --lg-env config/qemu.yaml tests/

The build directory and deploy path are fixed
(`build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`), so no extra
configuration is needed. If the image was not built yet, labgrid stops
with a message naming that directory and that no `*.qemuboot.conf` file
was found there.

If a run is killed rather than stopped, a `qemu-system-arm` process stays
behind, because labgrid never reaches `on_deactivate`. Check with
`pgrep -a qemu-system-arm` and end it before the next run.

Every QEMU run ends with a harmless but noisy teardown error. This
happens on normal runs, not only after a kill signal. QEMU writes an
unrelated hardware-emulation warning line to the same channel that the
QMP monitor reads. This breaks the QMP `quit` command during cleanup.
As a result, a `/tmp/labgrid-qemu-tmp-*` directory stays behind after
each run. Clean up these directories from time to time. For example,
run `rm -rf /tmp/labgrid-qemu-tmp-*` between runs.

Known limitation: `test_system_running`, `test_proc_version`, and
`test_os_release` do not pass under QEMU. All three depend on the
`gateway_system_is_running` fixture. That fixture waits for `systemctl
--wait is-system-running` to finish, with a 300-second timeout.

Several systemd units never settle under QEMU. They need hardware that
QEMU does not emulate. `reset-rm.service` and `rm-flashing.service` need
the Radio Module. `wpa_supplicant@wlan0.service` and
`sys-subsystem-net-devices-wlan0.device` need a WiFi device.
`swupdate-check.service` also fails under QEMU. The cause is not yet
known.

The wait times out after 300 seconds. Pytest then reports these three
tests as errors, not as passes or failures.

These tests and the `gateway_system_is_running` fixture stay the same
for the bench and for QEMU. A later change can add QEMU support for this
hardware, or split the fixture by target. This change does not add that
support.

## Adding more targets

One file per target under `config/`, selected with `--lg-env` or `LG_ENV`.
The tests read nothing that is specific to a bench.

Two rules keep this working as the number of targets grows:

- A second serial adapter needs its own udev `match:` so it is identified
  by USB path rather than enumeration order. `config/gateway.yaml`
  already does this for its one adapter.
- With a labgrid coordinator, only the `resources:` block changes, to
  `RemotePlace` with `name: !template '$LG_PLACE'`. Drivers, fixtures and
  tests stay as they are. QEMU is not affected, because labgrid has no QEMU
  resource and no QEMU exporter. QEMU always runs on the machine that runs
  pytest, so it never needs a reservation.
