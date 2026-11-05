"""Simulates the radio module on QEMU's second serial port.

QEMU exports /dev/ttyAMA1 as a UNIX socket. The gateway runs pppd on that port,
and this program implements the radio module's side of the link: PPP, IPv6 and
the TCP API.
"""

import argparse
import logging
import sys

from .radio_module import DEFAULT_MAC, FakeRadioModule


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("socket", help="UNIX socket QEMU exports as ttyAMA1")
    parser.add_argument(
        "--mac",
        default=DEFAULT_MAC,
        help="radio module MAC address (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log every API command and control packet",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    try:
        FakeRadioModule(args.socket, args.mac).run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
