# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from qemuboot_conf import read_qemuboot_conf


def test_reads_config_bsp_section(tmp_path):
    (tmp_path / "gardena-image-foss-bnw-gardena-sg-qemuarm.qemuboot.conf").write_text(
        "[config_bsp]\n"
        "qb_machine = -machine versatilepb\n"
        "qb_mem = -m 128\n"
    )

    bsp = read_qemuboot_conf(tmp_path)

    assert bsp["qb_machine"] == "-machine versatilepb"
    assert bsp["qb_mem"] == "-m 128"


def test_raises_when_no_conf_file_found(tmp_path):
    with pytest.raises(RuntimeError, match="found 0"):
        read_qemuboot_conf(tmp_path)


def test_raises_when_multiple_conf_files_found(tmp_path):
    (tmp_path / "a.qemuboot.conf").write_text("[config_bsp]\n")
    (tmp_path / "b.qemuboot.conf").write_text("[config_bsp]\n")

    with pytest.raises(RuntimeError, match="found 2"):
        read_qemuboot_conf(tmp_path)


def test_treats_a_symlink_and_its_target_as_one_match(tmp_path):
    # Yocto's deploy dir has both a timestamped *.qemuboot.conf and a
    # stable-named symlink to it, matching the glob twice for one file.
    target = tmp_path / "image-machine-20261002071132.qemuboot.conf"
    target.write_text("[config_bsp]\nqb_machine = -machine versatilepb\n")
    (tmp_path / "image-machine.qemuboot.conf").symlink_to(target.name)

    bsp = read_qemuboot_conf(tmp_path)

    assert bsp["qb_machine"] == "-machine versatilepb"
