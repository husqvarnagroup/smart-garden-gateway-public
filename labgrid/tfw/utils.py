


def remove_or_touch_and_restore_empty_file(shell, file_path, touch=False):
    """Remove a file on the gateway and restore it after the test, if it was present before."""
    file_was_present = False
    _, _, exit_code = shell.run(f"test -f {file_path}")
    if exit_code == 0:
        file_was_present = True

    if touch:
        output, _, exit_code = shell.run(f"touch {file_path}")
        assert exit_code == 0, f"Failed to touch {file_path}: {output}"
    else:
        output, _, exit_code = shell.run(f"rm -f {file_path}")
        assert exit_code == 0, f"Failed to remove {file_path}: {output}"

    yield

    if not file_was_present:
        output, _, exit_code = shell.run(f"touch {file_path}")
        assert exit_code == 0, f"Failed to restore {file_path}: {output}"


def set_and_restore_fw_env_var(shell, fw_env_var, value=""):
    """Set a U-Boot environment variable on the gateway and restore it after the test.
    Setting an empty value (default) will remove the variable."""
    previous_fw_env_var_value = ""
    output, _, exit_code = shell.run(f"fw_printenv -n {fw_env_var}")
    if exit_code == 0:
        previous_fw_env_var_value = output[0].strip()

    output, _, exit_code = shell.run(f"fw_setenv {fw_env_var} {value}")
    assert exit_code == 0, f"Failed to set {fw_env_var}: {output}"
    yield

    output, _, exit_code = shell.run(f"fw_setenv {fw_env_var} {previous_fw_env_var_value}")
    assert exit_code == 0, f"Failed to restore {fw_env_var}: {output}"
