"""LCP and IPV6CP, as much of RFC 1661 as the gateway's pppd needs.

The gateway runs pppd with "noauth noccp noip +ipv6", so only LCP and IPV6CP
are needed.
"""

import logging
import os
import random
import struct
import time

from . import hdlc

PROTO_IPV6 = 0x0057
PROTO_IPV6CP = 0x8057
PROTO_LCP = 0xC021

CONFIGURE_REQUEST = 1
CONFIGURE_ACK = 2
CONFIGURE_NAK = 3
CONFIGURE_REJECT = 4
TERMINATE_REQUEST = 5
TERMINATE_ACK = 6
CODE_REJECT = 7
PROTOCOL_REJECT = 8
ECHO_REQUEST = 9
ECHO_REPLY = 10
DISCARD_REQUEST = 11

RESTART_TIMEOUT = 3.0

# Configure-Requests are repeated until pppd answers, which may take a while.
# After this many attempts, a message is logged.
COMPLAIN_AFTER = 10

log = logging.getLogger(__name__)


def parse_options(data):
    """Split a Configure-* option list into (type, value) pairs."""
    options = []
    while len(data) >= 2:
        otype, olen = data[0], data[1]
        if olen < 2 or olen > len(data):
            break
        options.append((otype, data[2:olen]))
        data = data[olen:]
    return options


def build_options(options):
    return b"".join(bytes([otype, len(value) + 2]) + value for otype, value in options)


class ControlProtocol:
    """Shared Configure-Request/Ack/Nak/Reject handling.

    The full RFC 1661 state machine is not implemented. With a cooperative pppd
    on a lossless socket, tracking whether each direction has been configured
    is enough.
    """

    protocol = 0
    name = "?"

    def __init__(self, link):
        self.link = link
        self.local_open = False
        self.peer_open = False
        self._id = random.randrange(256)
        self._pending = None
        self._deadline = None
        self._restarts = 0

    @property
    def opened(self):
        return self.local_open and self.peer_open

    def open(self):
        self.local_open = False
        self.peer_open = False
        self._restarts = 0
        self._send_configure_request()

    def close(self):
        self.local_open = False
        self.peer_open = False
        self._pending = None
        self._deadline = None

    def tick(self, now):
        if self._deadline is None or now < self._deadline:
            return
        self._restarts += 1
        if self._restarts == COMPLAIN_AFTER:
            log.info("%s: still waiting for the gateway to answer", self.name)
        self._retransmit()

    def local_options(self):
        return []

    def _send_configure_request(self):
        self._id = (self._id + 1) & 0xFF
        self._pending = build_options(self.local_options())
        self._send(CONFIGURE_REQUEST, self._id, self._pending)
        self._deadline = time.monotonic() + RESTART_TIMEOUT

    def _retransmit(self):
        log.debug("%s: retransmitting Configure-Request", self.name)
        self._send(CONFIGURE_REQUEST, self._id, self._pending)
        self._deadline = time.monotonic() + RESTART_TIMEOUT

    def _send(self, code, identifier, payload=b""):
        packet = struct.pack("!BBH", code, identifier, len(payload) + 4) + payload
        self.link.send(self.protocol, packet)

    def handle(self, packet):
        if len(packet) < 4:
            return
        code, identifier, length = struct.unpack("!BBH", packet[:4])
        payload = packet[4:length] if 4 <= length <= len(packet) else packet[4:]

        if code == CONFIGURE_REQUEST:
            self._handle_configure_request(identifier, payload)
        elif code == CONFIGURE_ACK:
            if identifier == self._id:
                self._deadline = None
                self.local_open = True
                log.debug("%s: our configuration was acknowledged", self.name)
                self._check_opened()
        elif code in (CONFIGURE_NAK, CONFIGURE_REJECT):
            self._handle_configure_reply(code, payload)
        elif code == TERMINATE_REQUEST:
            self._send(TERMINATE_ACK, identifier, payload)
            log.info("%s: peer terminated the link", self.name)
            self.link.down()
        elif code == ECHO_REQUEST:
            self._handle_echo_request(identifier, payload)
        elif code in (TERMINATE_ACK, ECHO_REPLY, DISCARD_REQUEST, CODE_REJECT):
            pass
        else:
            self._send(CODE_REJECT, identifier, packet[: self.link.mru - 4])

    def _handle_configure_request(self, identifier, payload):
        acked, nakked, rejected = [], [], []
        for otype, value in parse_options(payload):
            verdict, suggestion = self.review_option(otype, value)
            if verdict == "ack":
                acked.append((otype, value))
            elif verdict == "nak":
                nakked.append((otype, suggestion))
            else:
                rejected.append((otype, value))

        if rejected:
            self._send(CONFIGURE_REJECT, identifier, build_options(rejected))
        elif nakked:
            self._send(CONFIGURE_NAK, identifier, build_options(nakked))
        else:
            for otype, value in acked:
                self.apply_option(otype, value)
            self._send(CONFIGURE_ACK, identifier, build_options(acked))
            self.peer_open = True
            log.debug("%s: acknowledged the peer's configuration", self.name)
            self._check_opened()

    def _handle_configure_reply(self, code, payload):
        for otype, value in parse_options(payload):
            if code == CONFIGURE_REJECT:
                self.drop_option(otype)
            else:
                self.adopt_option(otype, value)
        self._restarts = 0
        self._send_configure_request()

    def _handle_echo_request(self, identifier, payload):
        self._send(ECHO_REPLY, identifier, struct.pack("!I", self.magic) + payload[4:])

    def _check_opened(self):
        if self.opened:
            log.info("%s: opened", self.name)
            self.link.protocol_opened(self)

    # Option handling, overridden by the subclasses.

    magic = 0

    def review_option(self, otype, value):
        """Return ("ack"|"nak"|"reject", suggested value)."""
        return "reject", value

    def apply_option(self, otype, value):
        pass

    def drop_option(self, otype):
        pass

    def adopt_option(self, otype, value):
        pass


class LCP(ControlProtocol):
    protocol = PROTO_LCP
    name = "LCP"

    OPT_MRU = 1
    OPT_ACCM = 2
    OPT_AUTH = 3
    OPT_MAGIC = 5
    OPT_PFC = 7
    OPT_ACFC = 8

    def __init__(self, link):
        super().__init__(link)
        self.magic = random.getrandbits(32)
        self.peer_magic = 0
        self.want_accm = 0x00000000

    def local_options(self):
        # Ask pppd not to escape control characters. PFC and ACFC are not
        # requested, so its frames are not compressed.
        return [
            (self.OPT_ACCM, struct.pack("!I", self.want_accm)),
            (self.OPT_MAGIC, struct.pack("!I", self.magic)),
        ]

    def review_option(self, otype, value):
        if otype == self.OPT_MRU and len(value) == 2:
            return "ack", value
        if otype == self.OPT_ACCM and len(value) == 4:
            return "ack", value
        if otype == self.OPT_MAGIC and len(value) == 4:
            if struct.unpack("!I", value)[0] == self.magic:
                # Our own magic number indicates a loopback (RFC 1661).
                return "nak", struct.pack("!I", random.getrandbits(32))
            return "ack", value
        return "reject", value

    def apply_option(self, otype, value):
        if otype == self.OPT_MRU:
            self.link.peer_mru = struct.unpack("!H", value)[0]
        elif otype == self.OPT_MAGIC:
            self.peer_magic = struct.unpack("!I", value)[0]

    def drop_option(self, otype):
        if otype == self.OPT_MAGIC:
            self.magic = 0

    def adopt_option(self, otype, value):
        if otype == self.OPT_ACCM and len(value) == 4:
            self.want_accm = struct.unpack("!I", value)[0]
        elif otype == self.OPT_MAGIC and len(value) == 4:
            self.magic = struct.unpack("!I", value)[0]


class IPv6CP(ControlProtocol):
    protocol = PROTO_IPV6CP
    name = "IPV6CP"

    OPT_INTERFACE_ID = 1

    def __init__(self, link, interface_id):
        super().__init__(link)
        self.interface_id = interface_id
        self.peer_interface_id = b"\0" * 8

    def local_options(self):
        return [(self.OPT_INTERFACE_ID, self.interface_id)]

    def review_option(self, otype, value):
        if otype == self.OPT_INTERFACE_ID and len(value) == 8:
            if value == b"\0" * 8 or value == self.interface_id:
                return "nak", os.urandom(8)
            return "ack", value
        return "reject", value

    def apply_option(self, otype, value):
        if otype == self.OPT_INTERFACE_ID:
            self.peer_interface_id = value

    def adopt_option(self, otype, value):
        if otype == self.OPT_INTERFACE_ID and len(value) == 8:
            self.interface_id = value


class PPPLink:
    """Runs LCP and IPV6CP over an HDLC-framed byte stream."""

    def __init__(self, transport, interface_id, on_ipv6=None, mru=1500):
        self.transport = transport
        self.mru = mru
        self.peer_mru = mru
        self.on_ipv6 = on_ipv6

        self._unframer = hdlc.Unframer(max_frame=mru + 64)
        self.lcp = LCP(self)
        self.ipv6cp = IPv6CP(self, interface_id)

    @property
    def up(self):
        return self.lcp.opened and self.ipv6cp.opened

    def open(self):
        self.ipv6cp.close()
        self.lcp.open()

    def down(self):
        self.lcp.close()
        self.ipv6cp.close()

    def tick(self, now):
        self.lcp.tick(now)
        if self.lcp.opened:
            self.ipv6cp.tick(now)

    def send(self, protocol, payload):
        # Always escape all control characters, even if the peer asked for an
        # ACCM of 0. pppd only applies the new ACCM once the negotiation has
        # completed, so it would drop an unescaped Configure-Ack.
        packet = b"\xff\x03" + struct.pack("!H", protocol) + bytes(payload)
        self.transport.write(hdlc.frame(packet, hdlc.ACCM_DEFAULT))

    def send_ipv6(self, packet):
        self.send(PROTO_IPV6, packet)

    def feed(self, data):
        for packet in self._unframer.feed(data):
            self._dispatch(packet)

    def protocol_opened(self, protocol):
        if protocol is self.lcp:
            self.ipv6cp.open()

    def _dispatch(self, packet):
        if packet[:2] == b"\xff\x03":  # Address and control, unless compressed.
            packet = packet[2:]
        if not packet:
            return
        if packet[0] & 1:  # Compressed, single byte protocol field.
            protocol, payload = packet[0], packet[1:]
        elif len(packet) >= 2:
            protocol, payload = struct.unpack("!H", packet[:2])[0], packet[2:]
        else:
            return

        if protocol == PROTO_LCP:
            self.lcp.handle(payload)
        elif protocol == PROTO_IPV6CP:
            self.ipv6cp.handle(payload)
        elif protocol == PROTO_IPV6:
            if self.on_ipv6 is not None:
                self.on_ipv6(payload)
        elif self.lcp.opened:
            log.debug("rejecting protocol 0x%04x", protocol)
            self.lcp._send(
                PROTOCOL_REJECT,
                (self.lcp._id + 1) & 0xFF,
                struct.pack("!H", protocol) + payload[: self.mru - 6],
            )
