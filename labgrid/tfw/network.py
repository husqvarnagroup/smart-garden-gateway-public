import socket
import logging
from time import sleep

logger = logging.getLogger("tests.network")

def ping_gateway(hostname):
    """Checking if the gateway is reachable on the network.

    Note: this is not a real IMCP ping, but a TCP connection attempt to port 80.
    # Inspired by: https://stackoverflow.com/a/72648222
    """
    s = socket.socket()

    success = False
    for i in range(10):
        try:
            s.connect((hostname, 80))
            success = True
            break
        except TimeoutError as e:
            success = False
            sleep(i * 0.5)

    s.close()

    if success is False:
        logger.error(f"Failed to connect to {hostname}: {e}")

    return success
