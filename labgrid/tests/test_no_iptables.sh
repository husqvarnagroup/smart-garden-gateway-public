#!/bin/sh
# shellcheck shell=dash
#
# Check that no iptables packages, tools, or kernel tables are on the target.
#
# The gateway uses nftables only. Run this script on the target. It prints a
# result for each check and exits with 1 if any check fails.

failures=0


#def test_no_iptable(gateway_reachable_on_network, shell):
#    output, _, exit_code = shell.run("opkg list-installed | grep -E '^(iptables|ip6tables|libxtables|kernel-module-xt-|kernel-module-ip)'")
#    # TODO: check dependent on gateway version
#    assert exit_code == 1, f"Unexpected iptables packages found installed: {output}"


# Print a result line and count failures.
report() {
    if [ "$1" = "ok" ]; then
        echo "ok:   $2"
    else
        echo "FAIL: $2"
        failures=$((failures + 1))
    fi
}

# Check 1: no iptables or xtables package is installed.
# opkg prints one line per installed package.
if opkg list-installed | grep -E '^(iptables|ip6tables|libxtables|kernel-module-xt-|kernel-module-ip)' >/dev/null; then
    report fail "an iptables related package is installed"
else
    report ok "no iptables related package is installed"
fi

# Check 2: no iptables binary is on the PATH.
if command -v iptables >/dev/null 2>&1 || command -v ip6tables >/dev/null 2>&1; then
    report fail "iptables or ip6tables binary is on the PATH"
else
    report ok "no iptables or ip6tables binary is on the PATH"
fi

# Check 3: the legacy iptables kernel tables are not loaded.
# The kernel creates these files only when the ip_tables modules exist.
for file in /proc/net/ip_tables_names /proc/net/ip6_tables_names; do
    if [ -e "$file" ]; then
        report fail "$file exists"
    else
        report ok "$file does not exist"
    fi
done

# Check 4: the nftables tables are present.
# The firewall creates the inet filter table, so it must exist on the target.
if nft list table inet filter >/dev/null 2>&1; then
    report ok "nftables table inet filter exists"
else
    report fail "nftables table inet filter does not exist"
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed."
    exit 1
fi

echo "All checks passed."
exit 0
