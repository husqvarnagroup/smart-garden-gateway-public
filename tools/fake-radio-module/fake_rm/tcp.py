"""Minimal TCP server for the radio module's API port.

The real radio module accepts a single connection on port 8888 and only answers
short requests. As the link is a lossless local socket, there is no congestion
control, window scaling, or reassembly.
"""

import logging
import random
import struct
import time

from . import inet

FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10

LISTEN = "LISTEN"
SYN_RECEIVED = "SYN-RECEIVED"
ESTABLISHED = "ESTABLISHED"
LAST_ACK = "LAST-ACK"

WINDOW = 4096
MSS = 1440
RETRANSMIT_TIMEOUT = 0.5
MAX_RETRANSMITS = 5

log = logging.getLogger(__name__)


def _wrap(value):
    return value & 0xFFFFFFFF


class TCPServer:
    """One listening port, one connection at a time."""

    def __init__(self, address, port, send_ipv6, handler):
        self.address = address
        self.port = port
        self._send_ipv6 = send_ipv6
        self._handler = handler
        self._reset()

    def _reset(self):
        self.state = LISTEN
        self.peer = None
        self.peer_port = None
        self.snd_una = 0
        self.snd_nxt = 0
        self.rcv_nxt = 0
        self._unacked = b""
        self._unacked_seq = 0
        self._unacked_flags = 0
        self._unacked_options = b""
        self._sent_at = None
        self._retransmits = 0

    def tick(self, now):
        if self._sent_at is None or now - self._sent_at < RETRANSMIT_TIMEOUT:
            return
        if self._retransmits >= MAX_RETRANSMITS:
            log.warning("peer stopped acknowledging, dropping the connection")
            if self.peer is not None:
                self._send(RST | ACK)
            self._reset()
            return
        self._retransmits += 1
        log.debug("retransmitting %d bytes", len(self._unacked))
        self._send(
            self._unacked_flags,
            self._unacked,
            seq=self._unacked_seq,
            options=self._unacked_options,
        )

    def handle(self, source, destination, segment):
        if len(segment) < 20 or destination != self.address:
            return
        if (
            inet.upper_layer_checksum(
                source, destination, inet.NEXT_HEADER_TCP, segment
            )
            != 0
        ):
            log.debug("dropping segment with a bad checksum")
            return

        source_port, destination_port, seq, ack = struct.unpack("!HHII", segment[:12])
        offset = (segment[12] >> 4) * 4
        flags = segment[13]
        payload = segment[offset:]

        if destination_port != self.port:
            return

        if self.state == LISTEN:
            if flags & SYN:
                self._accept(source, source_port, seq)
            elif not flags & RST:
                self._send_reset(source, source_port, seq, ack, flags, len(payload))
            return

        if source != self.peer or source_port != self.peer_port:
            # Like the real module, refuse a second connection.
            self._send_reset(source, source_port, seq, ack, flags, len(payload))
            return

        if flags & RST:
            log.info("peer reset the connection")
            self._reset()
            return

        if flags & ACK:
            self._process_ack(ack)

        if self.state == SYN_RECEIVED:
            if flags & ACK and ack == self.snd_nxt:
                self.state = ESTABLISHED
                log.info("API connection established")
            else:
                return

        if self.state in (ESTABLISHED, LAST_ACK):
            self._process_segment(seq, flags, payload)

    def _accept(self, source, source_port, seq):
        self.peer = source
        self.peer_port = source_port
        self.rcv_nxt = _wrap(seq + 1)
        self.snd_una = random.getrandbits(32)
        self.snd_nxt = _wrap(self.snd_una + 1)
        self.state = SYN_RECEIVED
        options = struct.pack("!BBH", 2, 4, MSS)
        self._send(SYN | ACK, seq=self.snd_una, options=options)

    def _process_ack(self, ack):
        if ack == self.snd_nxt:
            self._unacked = b""
            self._sent_at = None
            self._retransmits = 0
        self.snd_una = ack
        if self.state == LAST_ACK and self.snd_una == self.snd_nxt:
            log.info("API connection closed")
            self._reset()

    def _process_segment(self, seq, flags, payload):
        if seq != self.rcv_nxt:
            # Out of order. Acknowledge what we have so far, so the peer resends.
            if payload or flags & FIN:
                self._send(ACK)
            return

        if payload:
            self.rcv_nxt = _wrap(self.rcv_nxt + len(payload))
            response = self._handler(payload)
            if response:
                self._send(PSH | ACK, response)
            else:
                self._send(ACK)

        if flags & FIN:
            self.rcv_nxt = _wrap(self.rcv_nxt + 1)
            self._send(FIN | ACK)
            self.state = LAST_ACK

    def _send(self, flags, payload=b"", seq=None, options=b""):
        if seq is None:
            seq = self.snd_nxt
        segment = self._build(
            self.peer, self.peer_port, seq, self.rcv_nxt, flags, payload, options
        )
        self._send_ipv6(self.address, self.peer, inet.NEXT_HEADER_TCP, segment)

        consumed = len(payload) + (1 if flags & (SYN | FIN) else 0)
        if consumed:
            self.snd_nxt = _wrap(seq + consumed)
            self._unacked = payload
            self._unacked_seq = seq
            self._unacked_flags = flags
            self._unacked_options = options
            self._sent_at = time.monotonic()

    def _send_reset(self, peer, peer_port, seq, ack, flags, payload_length):
        if flags & RST:
            return
        if flags & ACK:
            reset_seq, reset_ack, reset_flags = ack, 0, RST
        else:
            reset_seq = 0
            reset_ack = _wrap(seq + payload_length + (1 if flags & SYN else 0))
            reset_flags = RST | ACK
        segment = self._build(
            peer, peer_port, reset_seq, reset_ack, reset_flags, b"", b""
        )
        self._send_ipv6(self.address, peer, inet.NEXT_HEADER_TCP, segment)

    def _build(self, peer, peer_port, seq, ack, flags, payload, options):
        if len(options) % 4:
            options += b"\0" * (4 - len(options) % 4)
        offset = (20 + len(options)) // 4
        header = struct.pack(
            "!HHIIBBHHH",
            self.port,
            peer_port,
            seq,
            ack,
            offset << 4,
            flags,
            WINDOW,
            0,
            0,
        )
        segment = header + options + bytes(payload)
        total = inet.upper_layer_checksum(
            self.address, peer, inet.NEXT_HEADER_TCP, segment
        )
        return segment[:16] + struct.pack("!H", total) + segment[18:]
