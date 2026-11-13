# Fake radio module

The code in this project simulates the radio module of the GARDENA Gateway. It
is meant to be used in conjunction with a gateway image run in QEMU. QEMU's second
serial port is bound to `/dev/ttyAMA1`, as a UNIX socket. The simulation
connects to that socket.

Three parts of the radio module are simulated: PPP, IPv6, and the TCP API on
port 8888.

## Run

Generally this project does not need to be run manually. It is started as part of
the `runqemu.sh` script and in the labgrid tests.

To run it manually, execute this command from this directory. Pass the path
of the UNIX socket that QEMU exports.

    uv run fake_rm /tmp/fake-rm.sock

Pass `--mac` to set the radio module MAC address. Pass `-v` to log every API
command and control packet.

## Test

Run the unit tests from this directory:

    uv run python3 -m unittest discover tests

