"""Connects the PPP link, IPv6 and the TCP API to QEMU's UNIX socket."""

import errno
import logging
import selectors
import socket
import threading
import time

from . import inet
from .api import RadioModuleAPI
from .ppp import PPPLink
from .tcp import TCPServer

DEFAULT_MAC = "8c:05:51:00:06:e2"
API_PORT = 8888

log = logging.getLogger("fake-rm")


def interface_id(mac):
    """Return the EUI-64 interface identifier the radio module would use."""
    octets = bytearray(int(part, 16) for part in mac.split(":"))
    if len(octets) != 6:
        raise ValueError(f"expected six octets, got {mac!r}")
    octets[0] ^= 0x02
    return bytes(octets[:3]) + b"\xff\xfe" + bytes(octets[3:])


class RadioModule:
    """Passes received IPv6 packets on to the ping responder or the API server."""

    def __init__(self, link, address, api):
        self.link = link
        self.address = address
        self.tcp = TCPServer(address, API_PORT, self.send, api.handle)

    def send(self, source, destination, next_header, payload):
        self.link.send_ipv6(inet.build(source, destination, next_header, payload))

    def handle_ipv6(self, packet):
        parsed = inet.parse(packet)
        if parsed is None:
            return
        source, destination, next_header, payload = parsed
        if next_header == inet.NEXT_HEADER_ICMPV6:
            reply = inet.echo_reply(source, destination, payload)
            if reply is not None:
                self.send(destination, source, inet.NEXT_HEADER_ICMPV6, reply)
        elif next_header == inet.NEXT_HEADER_TCP:
            self.tcp.handle(source, destination, payload)

    def tick(self, now):
        self.tcp.tick(now)


class Transport:
    """Connection to the UNIX socket exported by QEMU."""

    def __init__(self, path):
        self.path = path
        self.sock = None

    def connect(self, stop):
        """Return True once connected, or False if the stop event is set first."""
        timeout = 30.0
        deadline = time.monotonic() + timeout
        while not stop.is_set():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self.path)
            except OSError as err:
                sock.close()
                if time.monotonic() >= deadline:
                    raise
                if err.errno not in (errno.ENOENT, errno.ECONNREFUSED):
                    raise
                stop.wait(0.2)
                continue
            sock.setblocking(False)
            self.sock = sock
            log.info("connected to %s", self.path)
            return True
        return False

    def write(self, data):
        try:
            self.sock.sendall(data)
        except OSError as err:
            log.warning("write failed: %s", err)

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


class FakeRadioModule:
    """Simulates a radio module on the given UNIX socket.

    An instance handles one QEMU run. Create a new one for each QEMU start.
    """

    def __init__(self, socket_path, mac=DEFAULT_MAC):
        identifier = interface_id(mac)
        self.address = inet.link_local(identifier)
        self.api = RadioModuleAPI(bytes(int(part, 16) for part in mac.split(":")))
        self.transport = Transport(socket_path)
        self.link = PPPLink(self.transport, identifier)
        self.module = RadioModule(self.link, self.address, self.api)
        self.link.on_ipv6 = self.module.handle_ipv6
        self._stop = threading.Event()
        self._thread = None

    def run(self):
        """Run until stop() is called or QEMU closes the connection."""
        if not self.transport.connect(self._stop):
            return
        selector = selectors.DefaultSelector()
        try:
            self.link.open()
            log.info(
                "radio module is %s, API on port %d",
                inet.format_address(self.address),
                API_PORT,
            )
            selector.register(self.transport.sock, selectors.EVENT_READ)
            was_up = False
            while not self._stop.is_set():
                for _ in selector.select(timeout=0.2):
                    try:
                        data = self.transport.sock.recv(65536)
                    except ConnectionResetError:
                        data = b""
                    if not data:
                        log.info("QEMU closed the connection")
                        return
                    self.link.feed(data)
                now = time.monotonic()
                self.link.tick(now)
                self.module.tick(now)
                if self.link.up != was_up:
                    was_up = self.link.up
                    if was_up:
                        log.info(
                            "link up, gateway is %s",
                            inet.format_address(
                                inet.link_local(self.link.ipv6cp.peer_interface_id)
                            ),
                        )
                    else:
                        log.info("link down")
        finally:
            selector.close()
            self.transport.close()

    def _run_logging_errors(self):
        try:
            self.run()
        except Exception:
            log.exception("radio module failed")

    def start(self):
        """Call run() in a background thread."""
        self._thread = threading.Thread(
            target=self._run_logging_errors, name="fake-rm", daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop the module and wait for the background thread, if there is one."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def is_alive(self):
        """Return whether the background thread is still running."""
        return self._thread is not None and self._thread.is_alive()
