# Overview

This directory contains tests for the GARDENA smart Gateway that drive the
gateway over its serial console with [labgrid](https://labgrid.readthedocs.io/).

Only a serial adapter whose DTR line switches the gateway's power is
required to run the tests on a real gateway.

It's expected that the test run on a Linux machine.

## Flashing the Gateway

Currently there is no strategy implemented in labgrid that flashes an image to the gateway. So
it's necessary to update the gateway manually to the desired image before running the tests.

## Quick Start

### Configure Serial Adapter

To use a custom serial adapter change the serial port in `config/gateway.yaml` to the one in use.

### Setup Test Project


Install uv first. Follow the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

If `pipx` is available, you can also run:

```
pipx install uv
```

Install project dependencies:

```
cd labgrid
uv sync --python 3.12
```

### Run Tests

```
uv run pytest --lg-env config/gateway.yaml tests/
```

Set `LG_NO_POWER_CYCLE=1` to skip the power cycle of the gateway at the start
of the session. The gateway has to be up already.

### Console Log

Each test run writes the serial console output to the file `console_main` in the directory where the
tests are run.

### Test Log

The output shows the steps of labgrid at INFO level. The expect steps of the
console are logged at DEBUG level, so they are hidden. To keep them in a log
file, run:

```
uv run pytest --lg-env config/gateway.yaml --log-file=pytest.log tests/
```

To show them in the terminal as well, add `-vvvv`.

## Running against QEMU

The suite runs without the bench against a QEMU instance of the same image.
Build the image first, then select the QEMU environment (from the repository root):

```
./scripts/bbwrapper.sh qemuarm gardena-image-foss-bnw
cd labgrid
uv run pytest --lg-env config/qemu.yaml tests/
```

The build directory and deploy path are fixed
(`build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`), so no extra
configuration is needed. If the image was not built yet, the tests stop
with an error that names the missing `*.qemuboot.conf` file.

If a run is killed rather than stopped, a `qemu-system-arm` process stays
behind, because labgrid never reaches `on_deactivate`. Check with
`pgrep -a qemu-system-arm` and end it before the next run.

