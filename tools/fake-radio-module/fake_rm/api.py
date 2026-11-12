"""The radio module's TCP API, as used by lb_radio_gateway.

Requests consist of [version][command][length][payload], answers of
[version][result][length][payload]. The commands and statistics TLVs are taken
from lb_radio_gateway.py, which is part of the gateway-firmware-zephyr recipe in
meta-gardena.
"""

import logging
import struct
import time

API_VERSION = 1

SET_NETWORK_KEY = 0x01
SET_MAC_ADDRESS = 0x02
WAKEUP_DEVICE = 0x03
RESET_DEVICE_NONCE = 0x04
SET_TX_MAC_COUNTER = 0x05
GET_MAC_ADDRESS = 0x06
GET_ANTENNA_DIVERSITY_MODE = 0x07
SET_ANTENNA_DIVERSITY_MODE = 0x08
GET_ANTENNA_DIVERSITY = 0x09
SET_ANTENNA_DIVERSITY = 0x0A
GET_ANTENNA_INT_EXT = 0x0B
SET_ANTENNA_INT_EXT = 0x0C
GET_APP_VERSION = 0x0D
GET_TX_MAC_COUNTER = 0x0E
GET_LB_RADIO_DRIVER_STATE = 0x0F
GET_UPTIME = 0x10
GET_STACK_USAGE = 0x11
GET_NETWORK_KEY = 0x12
SI4467_START_CW = 0xE0
SI4467_STOP_TX = 0xE1
GET_SI4467_GPIO = 0xE2
LOG_STACK_USAGE = 0xE3
RESET_DEVICE_NONCES = 0xE4
REBOOT = 0xE5
GET_STATS = 0xE6
RESTART_TRANSCEIVER = 0xE7
SET_SI4467_SDN_PIN = 0xE8
LOG = 0xE9

OKAY = 0x00
UNSUPPORTED_COMMAND = 0x04
INVALID_ARGUMENT = 0x10
NO_NW_KEY_AVAILABLE = 0x14

# Statistics reported by the module, as (tag, value) pairs. Tags below 50 are
# signed RSSI readings. A value of 255 means "not measured yet".
STATISTICS = [
    (0, 255),
    (1, 255),
    (2, -72),
    (3, -70),
    (50, 0),
    (51, 0),
    (52, 0),
    (100, 0),
    (101, 0),
    (102, 0),
    (150, 0),
    (151, 0),
    (170, 0),
]

log = logging.getLogger(__name__)


class RadioModuleAPI:
    """Answers the API commands with plausible, mostly constant values."""

    def __init__(self, mac, app_version="3.6.2"):
        self.mac = mac
        self.app_version = app_version
        self.network_key = None
        self.tx_mac_counter = 0
        self.antenna_diversity_mode = 1
        self.antenna_diversity = 0
        self.antenna_internal = 1
        self._started = time.monotonic()
        self._buffer = b""

    def handle(self, data):
        """Process the received bytes and return the answers to send."""
        self._buffer += data
        answers = []
        while len(self._buffer) >= 3:
            version, command, length = self._buffer[0], self._buffer[1], self._buffer[2]
            if len(self._buffer) < 3 + length:
                break
            payload = self._buffer[3 : 3 + length]
            self._buffer = self._buffer[3 + length :]

            if version != API_VERSION:
                log.warning("ignoring request with API version %d", version)
                continue
            answer = self._dispatch(command, payload)
            if answer is not None:
                answers.append(answer)
        return b"".join(answers)

    def _dispatch(self, command, payload):
        if command == REBOOT:
            log.info("reboot requested, staying up anyway")
            return None  # The real module resets instead of answering.

        # The network key must not end up in the log.
        shown = "<redacted>" if command == SET_NETWORK_KEY else payload.hex()
        log.debug("command 0x%02x, payload: %s", command, shown)
        handler = getattr(self, f"_command_{command:02x}", None)
        if handler is None:
            log.info("unsupported command 0x%02x", command)
            return _answer(UNSUPPORTED_COMMAND)
        return handler(payload)

    def _command_01(self, payload):  # SET_NETWORK_KEY
        if len(payload) != 16:
            return _answer(INVALID_ARGUMENT)
        self.network_key = bytes(payload)
        return _answer(OKAY)

    def _command_02(self, payload):  # SET_MAC_ADDRESS
        if len(payload) != 6:
            return _answer(INVALID_ARGUMENT)
        self.mac = bytes(payload)
        return _answer(OKAY)

    def _command_03(self, payload):  # WAKEUP_DEVICE
        return _answer(OKAY)

    def _command_04(self, payload):  # RESET_DEVICE_NONCE
        return _answer(OKAY)

    def _command_05(self, payload):  # SET_TX_MAC_COUNTER
        if len(payload) != 8:
            return _answer(INVALID_ARGUMENT)
        self.tx_mac_counter = int.from_bytes(payload, "little")
        return _answer(OKAY)

    def _command_06(self, payload):  # GET_MAC_ADDRESS
        return _answer(OKAY, self.mac)

    def _command_07(self, payload):  # GET_ANTENNA_DIVERSITY_MODE
        return _answer(OKAY, bytes([self.antenna_diversity_mode]))

    def _command_08(self, payload):  # SET_ANTENNA_DIVERSITY_MODE
        if len(payload) != 1:
            return _answer(INVALID_ARGUMENT)
        self.antenna_diversity_mode = payload[0]
        return _answer(OKAY)

    def _command_09(self, payload):  # GET_ANTENNA_DIVERSITY
        return _answer(OKAY, bytes([self.antenna_diversity]))

    def _command_0a(self, payload):  # SET_ANTENNA_DIVERSITY
        if len(payload) != 1:
            return _answer(INVALID_ARGUMENT)
        self.antenna_diversity = payload[0]
        return _answer(OKAY)

    def _command_0b(self, payload):  # GET_ANTENNA_INT_EXT
        return _answer(OKAY, bytes([self.antenna_internal]))

    def _command_0c(self, payload):  # SET_ANTENNA_INT_EXT
        if len(payload) != 1:
            return _answer(INVALID_ARGUMENT)
        self.antenna_internal = payload[0]
        return _answer(OKAY)

    def _command_0d(self, payload):  # GET_APP_VERSION
        return _answer(OKAY, self.app_version.encode())

    def _command_0e(self, payload):  # GET_TX_MAC_COUNTER
        return _answer(OKAY, struct.pack("<Q", self.tx_mac_counter))

    def _command_0f(self, payload):  # GET_LB_RADIO_DRIVER_STATE
        return _answer(OKAY, b"idle")

    def _command_10(self, payload):  # GET_UPTIME
        uptime = int((time.monotonic() - self._started) * 1000) & 0xFFFFFFFF
        return _answer(OKAY, struct.pack("<I", uptime))

    def _command_11(self, payload):  # GET_STACK_USAGE
        return _answer(OKAY, b"lb_radio: 512/2048")

    def _command_12(self, payload):  # GET_NETWORK_KEY
        if self.network_key is None:
            return _answer(NO_NW_KEY_AVAILABLE)
        return _answer(OKAY, self.network_key)

    def _command_e0(self, payload):  # SI4467_START_CW
        return _answer(OKAY)

    def _command_e1(self, payload):  # SI4467_STOP_TX
        return _answer(OKAY)

    def _command_e2(self, payload):  # GET_SI4467_GPIO
        return _answer(OKAY, b"\x00")

    def _command_e3(self, payload):  # LOG_STACK_USAGE
        return _answer(OKAY)

    def _command_e4(self, payload):  # RESET_DEVICE_NONCES
        return _answer(OKAY)

    def _command_e6(self, payload):  # GET_STATS
        blob = b"".join(
            bytes([tag, 4]) + struct.pack("<i", value) for tag, value in STATISTICS
        )
        return _answer(OKAY, blob)

    def _command_e7(self, payload):  # RESTART_TRANSCEIVER
        return _answer(OKAY)

    def _command_e8(self, payload):  # SET_SI4467_SDN_PIN
        return _answer(OKAY)

    def _command_e9(self, payload):  # LOG
        return _answer(OKAY)


def _answer(result, payload=b""):
    return bytes([API_VERSION, result, len(payload)]) + bytes(payload)
