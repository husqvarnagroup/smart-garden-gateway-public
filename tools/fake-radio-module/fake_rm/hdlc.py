"""PPP in HDLC-like framing (RFC 1662)."""

FLAG = 0x7E
ESCAPE = 0x7D
XOR = 0x20

FCS_INIT = 0xFFFF
FCS_GOOD = 0xF0B8

# By default, all control characters must be escaped.
ACCM_DEFAULT = 0xFFFFFFFF


def _make_fcs_table():
    table = []
    for byte in range(256):
        value = byte
        for _ in range(8):
            value = (value >> 1) ^ 0x8408 if value & 1 else value >> 1
        table.append(value)
    return table


_FCS_TABLE = _make_fcs_table()


def fcs16(data, fcs=FCS_INIT):
    """CRC-16/X-25 over data, as used for the frame check sequence."""
    for byte in data:
        fcs = (fcs >> 8) ^ _FCS_TABLE[(fcs ^ byte) & 0xFF]
    return fcs


def frame(payload, accm=ACCM_DEFAULT):
    """Wrap payload (address, control, protocol and information) into a frame.

    Control characters whose bit is set in accm are escaped.
    """
    fcs = fcs16(payload) ^ 0xFFFF
    body = bytes(payload) + bytes([fcs & 0xFF, fcs >> 8])

    out = bytearray([FLAG])
    for byte in body:
        if byte in (FLAG, ESCAPE) or (byte < 0x20 and accm & (1 << byte)):
            out.append(ESCAPE)
            out.append(byte ^ XOR)
        else:
            out.append(byte)
    out.append(FLAG)
    return bytes(out)


class Unframer:
    """Turns a stream of bytes into frames, dropping the ones that fail the FCS.

    The frames returned include address, control and protocol, but not the FCS.
    """

    def __init__(self, max_frame=4096):
        self._max_frame = max_frame
        self._buf = bytearray()
        self._in_frame = False
        self._escaped = False
        self.fcs_errors = 0

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == FLAG:
                # Two flags in a row are an empty frame, not a broken one.
                if self._in_frame and self._buf:
                    payload = self._checked(bytes(self._buf))
                    if payload is not None:
                        frames.append(payload)
                self._buf.clear()
                self._escaped = False
                self._in_frame = True
            elif not self._in_frame:
                continue  # Junk before the first flag.
            elif byte == ESCAPE:
                self._escaped = True
            else:
                self._buf.append(byte ^ XOR if self._escaped else byte)
                self._escaped = False
                if len(self._buf) > self._max_frame:
                    self._buf.clear()
                    self._in_frame = False
        return frames

    def _checked(self, raw):
        if len(raw) < 4 or fcs16(raw) != FCS_GOOD:
            self.fcs_errors += 1
            return None
        return raw[:-2]
