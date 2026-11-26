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

## Wi-Fi Tests

The tests in `tests/wifi` join the AP of the gateway with a dedicated
adapter on the test host. They check the DHCP lease and measure the
throughput in both directions with iperf3. They need Docker and run as a
user in the `docker` group.

The adapter is moved into the network namespace of a container, so the
host's own networking is not touched. When the container ends, the kernel
returns the adapter to the host. The adapter's driver must support moving
it between network namespaces. Most mac80211 drivers do.

Prevent the host from meddling with the adapter. For NetworkManager, run:

```
IFACE=wl...
echo -e "[keyfile]\nunmanaged-devices=interface-name:$IFACE" | \
    sudo tee /etc/NetworkManager/conf.d/$IFACE.conf
sudo systemctl reload NetworkManager
```

Run the tests with `LG_WIFI_IFACE` set to the interface name:

```
LG_WIFI_IFACE=wl... uv run pytest --lg-env config/gateway.yaml tests/wifi
```

They only run on environments with the labgrid feature `wifi`, i.e. not
with `config/qemu.yaml`. They are skipped if `LG_WIFI_IFACE` is not set, the
adapter does not exist or Docker is not reachable.

The settings are options of the target `main` in the environment file:

| Option               | Default | Purpose                               |
|----------------------|---------|---------------------------------------|
| `wifi_host_iface`    |         | Adapter if `LG_WIFI_IFACE` is not set |
| `wifi_assoc_timeout` | `30`    | Seconds to wait for association       |
| `wifi_dhcp_timeout`  | `20`    | Seconds to wait for a lease           |

The accessory-server only opens the AP if there is no Ethernet connection.
The tests therefore install iperf3 from the opkg feed while the gateway is
still connected. Then they set `eth0` down and restart the
accessory-server. The gateway needs Ethernet with access to the feed.

The SSID of the AP is derived from the hostname, e.g.
`GARDENA_config(004cdf)` for `GARDENA-004cdf`. The AP has no password. The
tests fail if `hostapd` does not start within 120 s, or if the AP does not
show up in a scan within another 120 s.

The iperf3 server runs in the container and the gateway runs the client.
This way, the firewall of the gateway needs no changes. Each direction
runs for 10 s and must reach more than 4 Mbit/s.

Only one test session can use an adapter at a time.
