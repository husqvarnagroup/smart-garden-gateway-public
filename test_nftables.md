# Test procedures for the nftables migration

These steps test the move from iptables to nftables. Run the build checks first. Then run the target checks on a device with the new image. Keep one device with the old image for the comparison steps.

## 1. Build checks

Build the image. Make sure that the kernel config resolves without the removed options.

Run the dependency graph for the image:

```sh
bitbake -g <image>
grep -E 'iptables|ip6tables|xtables|xt-' <build-dir>/tmp/package-depends.dot
```

The grep must print nothing.

Check the image manifest:

```sh
grep -E '^(netbase|nftables) ' <build-dir>/tmp/deploy/images/<MACHINE>/<image>-<MACHINE>.manifest
grep -E '^(miniupnpd|firewalld|networkmanager|iptables)' <build-dir>/tmp/deploy/images/<MACHINE>/<image>-<MACHINE>.manifest
```

The first command must print `netbase` and `nftables`. The second command must print nothing.


## 4. Port scans

Run these scans from a LAN host against the old device and the new device:

```sh
nmap -Pn -sS -p- --reason <gateway-ip>
nmap -sU --top-ports 50 --reason <gateway-ip>
```

Save both outputs. Compare the open, closed, and filtered ports. A closed TCP port must answer with a reset. A closed UDP port must answer with port unreachable.

## Ensure ppp0 works properly

Check traffic class



## 7. Reload and failure

Start `ipcforward` as described in step 8. Then run:

```sh
systemctl restart firewall
nft list chain inet filter input
```

The rule with the `ipcforward-` comment must be gone.

Test a broken ruleset:

```sh
echo 'table inet filter { chain x { bogus } }' > broken.nft
nft -c -f broken.nft
nft list ruleset > after.nft
```

The `nft -c` command must fail. The file `after.nft` must match the ruleset from before the test.

## 8. ipcforward

Enable the debug flag:

```sh
fw_setenv dev_debug_enable_ipcforward 1
```

Start the forwarder:

```sh
ipcforward -q lwm2mserver 28150
```

In a second shell, run:

```sh
nft list chain inet filter input
```

The output must show one rule for ports 28150 and 28151. The rule must have the comment `ipcforward-lwm2mserver`.

Stop the forwarder with `kill -TERM <pid>`. Run `nft list chain inet filter input` again. The rule must be gone.

Stop the firewall table and start the forwarder again. The output must include `No firewall installed, not opening any ports.`

## 9. EOL and SSH

Clear the EOL state:

```sh
fw_setenv eol_test_passed 0
```

Reboot the device. SSH must work. Run the EOL path. Check that its SSH rule is the first rule in the input chain:

```sh
nft list chain inet filter input
```

# procfs

On Gateway:

```
root@GARDENA-2fed4b:~# cat /proc/modules
mt7603e 38368 0 - Live 0x00000000
mt76 31904 1 mt7603e, Live 0x00000000
mac80211 414560 2 mt7603e,mt76, Live 0x00000000
libarc4 832 1 mac80211, Live 0x00000000
cfg80211 243376 3 mt7603e,mt76,mac80211, Live 0x00000000
nft_counter 2176 27 - Live 0x00000000
nft_compat 6528 12 - Live 0x00000000
firmware_class 6544 2 mt7603e,cfg80211, Live 0x00000000
```