import ipaddress
import socket
import logging
from time import sleep

logger = logging.getLogger("tests.network")

def ping_gateway(ip_or_hostname):
    """Checking if the gateway is reachable on the network.

    Note: this is not a real IMCP ping, but a TCP connection attempt to port 80.
    # Inspired by: https://stackoverflow.com/a/72648222
    """
    s = socket.socket()

    success = False
    for i in range(10):
        try:
            s.connect((ip_or_hostname, 80))
            success = True
            break
        except (TimeoutError, OSError) as e:
            success = False
            sleep(i * 0.5)

    s.close()

    if success is False:
        logger.error(f"Failed to connect to {ip_or_hostname}: {e}")

    return success


def get_gateway_ip_address(shell, protocol: str) -> str:
    """Get the IP address of the gateway's eth0 interface for the specified protocol (IPv4 or IPv6)."""
    if protocol == "ipv4":
        ip_prot = "inet"
    elif protocol == "ipv6":
        ip_prot = "inet6"
    else:
        raise ValueError(f"Invalid protocol: {protocol}. Must be 'ipv4' or 'ipv6'.")

    cmd = "ip addr show eth0" # print the IP address of the gateway's eth0 interface
    cmd += f"| grep -w {ip_prot}" # find the lines for the specified protocol
    cmd += "| awk '{ print $2 }'" # print the IP address with CIDR notation
    cmd += "| cut -d/ -f1" # remove the prefix to get just the IP address
    cmd += "| head -n 1" # get the first line (in case there are multiple addresses)

    logger.info("Running command to get IP address of gateway: %s", cmd)
    output, _, exit_code = shell.run(cmd)
    if exit_code != 0 or len(output) != 1:
        raise RuntimeError(f"Failed to get IP address for gateway: {output}")
    addr = output[0].strip()

    # Validate the IP address
    if protocol == "ipv4":
        _ipv4_addr = ipaddress.IPv4Address(addr)
    elif protocol == "ipv6":
        _ipv6_addr = ipaddress.IPv6Address(addr)

    return addr
