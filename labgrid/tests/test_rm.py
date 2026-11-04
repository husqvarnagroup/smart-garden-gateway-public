import re


def test_flash_rm(gateway_system_is_running, shell):
    # Check latest RM firmware version
    stdout, _, exit_code = shell.run("cat /etc/rm-firmware-version.latest")
    assert exit_code == 0
    assert len(stdout) == 1
    latest_rm_version = stdout[0].strip()
    assert re.match(r"^\d+\.\d+\.\d+\Z", latest_rm_version)

    # Set new RM firmware version to 0.0.0 to enforce flashing
    _, _, exit_code = shell.run("echo 0.0.0 > /etc/rm-firmware-version")
    assert exit_code == 0

    # Flash the RM firmware
    _, _, exit_code = shell.run("systemctl restart rm-flashing", timeout=60)
    assert exit_code == 0, "Failed to flash RM firmware"

    # Check if the RM firmware version is updated (this is only an indirect check that flashing was successful)
    stdout, _, exit_code = shell.run("cat /etc/rm-firmware-version")
    assert exit_code == 0
    assert len(stdout) == 1
    current_rm_version_from_file = stdout[0].strip()
    assert current_rm_version_from_file == latest_rm_version, f"Expected RM firmware version dos not match latest version"

    # TODO
    #stdout, _, exit_code = shell.run("/usr/bin/lb_radio_gateway -u /run/lemonbeatd/radiomodule_api get_app_versio", timeout=30)
    #assert exit_code == 0
    #assert len(stdout) == 1
    #rm_version_from_device = stdout[0].strip()
    #assert rm_version_from_device == latest_rm_version, f"Expected RM firmware version from device does not match latest version"
