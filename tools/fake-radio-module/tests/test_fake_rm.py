"""Unit tests for the fake radio module.

Bugs in the framing or TCP layer are hard to find in QEMU, where they only show
up as a link that never comes up. To run the tests from the
tools/fake-radio-module directory:

    python3 -m unittest discover tests
"""

import os
import socket
import struct
import tempfile
import time
import unittest

from fake_rm import FakeRadioModule, hdlc, inet, ppp, tcp
from fake_rm.api import RadioModuleAPI

OUR_ID = bytes.fromhex("8e055 1fffe0006e2".replace(" ", ""))
PEER_ID = bytes.fromhex("0011223344556677")


class HDLCTest(unittest.TestCase):
    def test_fcs_check_value(self):
        # Check value from the CRC-16/X-25 definition.
        self.assertEqual(hdlc.fcs16(b"123456789") ^ 0xFFFF, 0x906E)

    def test_round_trip(self):
        payload = b"\xff\x03\xc0\x21\x01\x01\x00\x0c" + bytes(8)
        for accm in (0x00000000, 0xFFFFFFFF):
            self.assertEqual(hdlc.Unframer().feed(hdlc.frame(payload, accm)), [payload])

    def test_flag_and_escape_are_always_escaped(self):
        framed = hdlc.frame(b"\x7e\x7d", accm=0)
        self.assertNotIn(0x7E, framed[1:-1])
        self.assertEqual(hdlc.Unframer().feed(framed), [b"\x7e\x7d"])

    def test_accepts_a_frame_split_across_reads(self):
        payload = b"\xff\x03\x00\x57" + bytes(range(32))
        framed = hdlc.frame(payload)
        unframer = hdlc.Unframer()
        frames = []
        for index in range(len(framed)):
            frames += unframer.feed(framed[index : index + 1])
        self.assertEqual(frames, [payload])

    def test_drops_a_frame_with_a_broken_fcs(self):
        framed = bytearray(hdlc.frame(b"\xff\x03\xc0\x21\x09\x01\x00\x04"))
        framed[6] ^= 0xFF
        unframer = hdlc.Unframer()
        self.assertEqual(unframer.feed(bytes(framed)), [])
        self.assertEqual(unframer.fcs_errors, 1)


class Loopback:
    """Collects what the link sends and hands back decoded control packets."""

    def __init__(self):
        self.unframer = hdlc.Unframer()
        self.packets = []
        self.raw = bytearray()

    def write(self, data):
        self.raw = bytearray(data)
        for frame in self.unframer.feed(data):
            protocol = struct.unpack("!H", frame[2:4])[0]
            self.packets.append((protocol, frame[4:]))

    def take(self):
        packets, self.packets = self.packets, []
        return packets


def control_packet(protocol, code, identifier, options=b""):
    packet = struct.pack("!BBH", code, identifier, len(options) + 4) + options
    return hdlc.frame(b"\xff\x03" + struct.pack("!H", protocol) + packet)


class PPPTest(unittest.TestCase):
    def setUp(self):
        self.loopback = Loopback()
        self.link = ppp.PPPLink(self.loopback, OUR_ID)
        self.link.open()

    def test_starts_with_an_lcp_configure_request(self):
        protocol, packet = self.loopback.take()[0]
        self.assertEqual(protocol, ppp.PROTO_LCP)
        self.assertEqual(packet[0], ppp.CONFIGURE_REQUEST)

    def test_rejects_options_it_does_not_implement(self):
        options = ppp.build_options([(1, b"\x05\xdc"), (7, b""), (8, b"")])
        self.loopback.take()
        self.link.feed(control_packet(ppp.PROTO_LCP, ppp.CONFIGURE_REQUEST, 7, options))

        _, reply = self.loopback.take()[0]
        self.assertEqual(reply[0], ppp.CONFIGURE_REJECT)
        self.assertEqual([option for option, _ in ppp.parse_options(reply[4:])], [7, 8])

    def test_negotiates_both_protocols(self):
        self._negotiate()
        self.assertTrue(self.link.up)
        self.assertEqual(self.link.ipv6cp.peer_interface_id, PEER_ID)

    def test_escapes_control_characters_even_after_acking_a_zero_accm(self):
        self._negotiate()
        self.loopback.take()
        self.link.send(ppp.PROTO_IPV6, b"\x00\x01\x02")
        # See PPPLink.send() for why control characters are always escaped.
        raw = self.loopback.raw
        self.assertNotIn(0x00, raw[1:-1])
        self.assertNotIn(0x01, raw[1:-1])

    def test_answers_an_echo_request(self):
        self._negotiate()
        self.loopback.take()
        payload = struct.pack("!I", 0xDEADBEEF) + b"ping"
        self.link.feed(control_packet(ppp.PROTO_LCP, ppp.ECHO_REQUEST, 3, payload))

        protocol, reply = self.loopback.take()[0]
        self.assertEqual(protocol, ppp.PROTO_LCP)
        self.assertEqual(reply[0], ppp.ECHO_REPLY)
        self.assertEqual(reply[8:], b"ping")

    def _negotiate(self):
        options = ppp.build_options(
            [
                (1, b"\x05\xdc"),
                (2, b"\x00\x00\x00\x00"),
                (5, b"\xde\xad\xbe\xef"),
            ]
        )
        self.link.feed(control_packet(ppp.PROTO_LCP, ppp.CONFIGURE_REQUEST, 8, options))
        self.link.feed(
            control_packet(
                ppp.PROTO_LCP,
                ppp.CONFIGURE_ACK,
                self.link.lcp._id,
                self.link.lcp._pending,
            )
        )

        peer = ppp.build_options([(1, PEER_ID)])
        self.link.feed(control_packet(ppp.PROTO_IPV6CP, ppp.CONFIGURE_REQUEST, 9, peer))
        self.link.feed(
            control_packet(
                ppp.PROTO_IPV6CP,
                ppp.CONFIGURE_ACK,
                self.link.ipv6cp._id,
                self.link.ipv6cp._pending,
            )
        )


class InetTest(unittest.TestCase):
    def test_answers_an_echo_request(self):
        us = inet.link_local(OUR_ID)
        them = inet.link_local(PEER_ID)
        request = bytearray(struct.pack("!BBHHH", 128, 0, 0, 0x1234, 1) + b"payload")
        request[2:4] = struct.pack(
            "!H", inet.upper_layer_checksum(them, us, 58, bytes(request))
        )

        reply = inet.echo_reply(them, us, bytes(request))
        self.assertEqual(reply[0], inet.ICMPV6_ECHO_REPLY)
        self.assertEqual(reply[4:], bytes(request)[4:])
        self.assertEqual(inet.upper_layer_checksum(us, them, 58, reply), 0)

    def test_ignores_anything_but_an_echo_request(self):
        us = inet.link_local(OUR_ID)
        them = inet.link_local(PEER_ID)
        self.assertIsNone(inet.echo_reply(them, us, b"\x87\x00\x00\x00"))


class TCPTest(unittest.TestCase):
    def setUp(self):
        self.us = inet.link_local(OUR_ID)
        self.them = inet.link_local(PEER_ID)
        self.sent = []
        self.received = []
        self.server = tcp.TCPServer(self.us, 8888, self._send, self._handle)
        self.peer_seq = 1000

    def _send(self, source, destination, next_header, segment):
        self.sent.append(self._parse(segment))

    def _handle(self, data):
        self.received.append(data)
        return b"pong"

    def _parse(self, segment):
        _, _, seq, ack = struct.unpack("!HHII", segment[:12])
        offset = (segment[12] >> 4) * 4
        return {
            "seq": seq,
            "ack": ack,
            "flags": segment[13],
            "payload": segment[offset:],
        }

    def _feed(self, flags, payload=b"", port=40000):
        header = struct.pack(
            "!HHIIBBHHH",
            port,
            8888,
            self.peer_seq,
            self.server.snd_nxt,
            5 << 4,
            flags,
            4096,
            0,
            0,
        )
        segment = header + payload
        checksum = inet.upper_layer_checksum(
            self.them, self.us, inet.NEXT_HEADER_TCP, segment
        )
        segment = segment[:16] + struct.pack("!H", checksum) + segment[18:]
        self.server.handle(self.them, self.us, segment)
        self.peer_seq += len(payload) + (1 if flags & (tcp.SYN | tcp.FIN) else 0)

    def _connect(self):
        self._feed(tcp.SYN)
        self.sent.clear()
        self._feed(tcp.ACK)

    def test_completes_the_handshake(self):
        self._feed(tcp.SYN)
        reply = self.sent[-1]
        self.assertEqual(reply["flags"], tcp.SYN | tcp.ACK)
        self.assertEqual(reply["ack"], 1001)
        self._feed(tcp.ACK)
        self.assertEqual(self.server.state, tcp.ESTABLISHED)

    def test_answers_data(self):
        self._connect()
        self._feed(tcp.PSH | tcp.ACK, b"ping")
        self.assertEqual(self.received, [b"ping"])
        self.assertEqual(self.sent[-1]["payload"], b"pong")

    def test_acknowledges_but_drops_out_of_order_data(self):
        self._connect()
        self.peer_seq += 100
        self._feed(tcp.PSH | tcp.ACK, b"gap")
        self.assertEqual(self.received, [])
        self.assertEqual(self.sent[-1]["flags"], tcp.ACK)

    def test_closes_on_fin(self):
        self._connect()
        self._feed(tcp.FIN | tcp.ACK)
        self.assertEqual(self.sent[-1]["flags"], tcp.FIN | tcp.ACK)
        self.assertEqual(self.server.state, tcp.LAST_ACK)
        self._feed(tcp.ACK)
        self.assertEqual(self.server.state, tcp.LISTEN)

    def test_refuses_a_second_connection(self):
        self._connect()
        self.sent.clear()
        self._feed(tcp.SYN, port=40001)
        self.assertTrue(self.sent[-1]["flags"] & tcp.RST)
        self.assertEqual(self.server.state, tcp.ESTABLISHED)


class APITest(unittest.TestCase):
    def setUp(self):
        self.api = RadioModuleAPI(bytes.fromhex("8c05510006e2"))

    def request(self, command, payload=b""):
        return self.api.handle(bytes([1, command, len(payload)]) + payload)

    def test_logs_the_payload(self):
        with self.assertLogs("fake_rm.api", level="DEBUG") as logs:
            self.request(0x08, b"\x02")
        self.assertIn("command 0x08, payload: 02", logs.output[0])

    def test_does_not_log_the_network_key(self):
        with self.assertLogs("fake_rm.api", level="DEBUG") as logs:
            self.request(0x01, bytes.fromhex("ab") * 16)
        self.assertIn("<redacted>", logs.output[0])
        self.assertNotIn("abab", logs.output[0])

    def test_reports_the_firmware_version(self):
        self.assertEqual(self.request(0x0D), b"\x01\x00\x053.6.2")

    def test_rejects_an_unknown_command(self):
        self.assertEqual(self.request(0x77), b"\x01\x04\x00")

    def test_stores_the_network_key(self):
        key = bytes(range(16))
        self.assertEqual(self.request(0x01, key), b"\x01\x00\x00")
        self.assertEqual(self.request(0x12), b"\x01\x00\x10" + key)

    def test_reports_no_key_until_one_is_set(self):
        self.assertEqual(self.request(0x12), b"\x01\x14\x00")

    def test_reboot_is_not_answered(self):
        self.assertEqual(self.request(0xE5), b"")

    def test_waits_for_a_request_split_across_segments(self):
        self.assertEqual(self.api.handle(b"\x01\x0d"), b"")
        self.assertEqual(self.api.handle(b"\x00"), b"\x01\x00\x053.6.2")

    def test_answers_two_requests_in_one_segment(self):
        answers = self.api.handle(bytes([1, 0x0D, 0]) + bytes([1, 0x06, 0]))
        self.assertEqual(
            answers, b"\x01\x00\x053.6.2" + b"\x01\x00\x06\x8c\x05\x51\x00\x06\xe2"
        )


class FakeRadioModuleTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "rm.sock")
        self.module = FakeRadioModule(self.path)
        self.addCleanup(self.module.stop)

    def accept_connection(self):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(self.path)
        server.listen(1)
        server.settimeout(5)
        self.module.start()
        client, _ = server.accept()
        self.addCleanup(client.close)
        client.settimeout(5)
        return client

    def wait_for_thread_end(self):
        deadline = time.monotonic() + 5
        while self.module.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.module.is_alive())

    def test_stop_closes_the_connection(self):
        client = self.accept_connection()
        self.assertTrue(self.module.is_alive())
        self.module.stop()
        self.assertFalse(self.module.is_alive())
        while client.recv(4096):
            pass

    def test_ends_when_qemu_closes_the_connection(self):
        client = self.accept_connection()
        with self.assertNoLogs("fake-rm", level="ERROR"):
            client.close()
            self.wait_for_thread_end()
        self.module.stop()

    def test_stop_does_not_wait_for_the_connect_timeout(self):
        self.module.start()
        started = time.monotonic()
        self.module.stop()
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(self.module.is_alive())


if __name__ == "__main__":
    unittest.main()
