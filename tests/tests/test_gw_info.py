# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re


def test_proc_version(shell):
    stdout, _, exit_code = shell.run("cat /proc/version")
    assert exit_code == 0
    assert stdout
    assert "Linux" in stdout[0]


def parse_os_release(content):
    os_release = {}
    for line in content:
        if "=" in line:
            key, value = line.split("=", 1)
            os_release[key] = value.strip('"')
    return os_release


def test_os_release(shell):
    stdout, _, exit_code = shell.run("cat /etc/os-release")
    assert exit_code == 0
    assert stdout

    content = parse_os_release(stdout)
    assert content["ID"] == "gardena"
    assert content["NAME"] == "GARDENA smart Gateway"

    assert content["VERSION"] == content["VERSION_ID"]
    version = content["VERSION"]
    assert re.match(r"^\d+\.\d+\.\d+\Z", version)

    assert "VERSION_CODENAME" in content
    assert content["CPE_NAME"] == f"cpe:/o:openembedded:gardena:{version}"
    assert "BUILD_ID" in content
    assert "CODENAME" in content
    assert "IMAGE_ID" in content
