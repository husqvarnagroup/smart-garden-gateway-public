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
