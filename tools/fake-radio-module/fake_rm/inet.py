"""Minimal IPv6 support for the radio module's TCP API.

PPP links have no link-layer addresses, so no neighbor discovery is needed
(RFC 5072). Echo replies are needed for the healthcheck ping test.
"""

import socket
import struct

NEXT_HEADER_TCP = 6
NEXT_HEADER_ICMPV6 = 58

ICMPV6_ECHO_REQUEST = 128
ICMPV6_ECHO_REPLY = 129

HEADER_LENGTH = 40
LINK_LOCAL_PREFIX = bytes.fromhex("fe800000000000000000000000000000")


def link_local(interface_id):
    return LINK_LOCAL_PREFIX[:8] + interface_id


def format_address(address):
    return socket.inet_ntop(socket.AF_INET6, address)


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def upper_layer_checksum(source, destination, next_header, payload):
    pseudo = (
        source + destination + struct.pack("!IBBBB", len(payload), 0, 0, 0, next_header)
    )
    return checksum(pseudo + payload)


def parse(packet):
    """Return (source, destination, next_header, payload), or None.

    Extension headers are not handled, as the gateway does not send any on this
    link.
    """
    if len(packet) < HEADER_LENGTH or packet[0] >> 4 != 6:
        return None
    payload_length, next_header = struct.unpack("!HB", packet[4:7])
    source = packet[8:24]
    destination = packet[24:40]
    payload = packet[HEADER_LENGTH : HEADER_LENGTH + payload_length]
    if len(payload) < payload_length:
        return None
    return source, destination, next_header, payload


def build(source, destination, next_header, payload, hop_limit=64, traffic_class=0):
    header = struct.pack(
        "!IHBB",
        (6 << 28) | (traffic_class << 20),
        len(payload),
        next_header,
        hop_limit,
    )
    return header + source + destination + bytes(payload)


def echo_reply(source, destination, payload):
    """Answer an ICMPv6 echo request, or return None for anything else."""
    if len(payload) < 4 or payload[0] != ICMPV6_ECHO_REQUEST:
        return None
    if upper_layer_checksum(source, destination, NEXT_HEADER_ICMPV6, payload) != 0:
        return None

    reply = bytearray(payload)
    reply[0] = ICMPV6_ECHO_REPLY
    reply[2:4] = b"\0\0"
    body = bytes(reply)
    total = upper_layer_checksum(destination, source, NEXT_HEADER_ICMPV6, body)
    return body[:2] + struct.pack("!H", total) + body[4:]
