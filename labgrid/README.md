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

### Console Log

Each test run writes the serial console output to the file `console_main` in the directory where the
tests are run.

## Running against QEMU

The suite runs without the bench against a QEMU instance of the same image.
Build the image first, then select the QEMU environment (from the repository root):

```
./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr
cd labgrid
poetry run pytest --lg-env config/qemu.yaml tests/
```

The build directory and deploy path are fixed
(`build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`), so no extra
configuration is needed. If the image was not built yet, labgrid stops
with a message naming that directory and that no `*.qemuboot.conf` file
was found there.

If a run is killed rather than stopped, a `qemu-system-arm` process stays
behind, because labgrid never reaches `on_deactivate`. Check with
`pgrep -a qemu-system-arm` and end it before the next run.

