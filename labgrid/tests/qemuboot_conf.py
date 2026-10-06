# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import configparser
from pathlib import Path


def read_qemuboot_conf(deploy_dir):
    """Return the [config_bsp] section of the deploy dir's *.qemuboot.conf.

    The Yocto build writes exactly one such file next to its images, with
    the machine-specific values (`qb_machine`, `qb_mem`, ...) that
    `scripts/runqemu.sh` itself reads to build its QEMU command line.
    """
    # The deploy dir has both a timestamped *.qemuboot.conf and a
    # stable-named symlink to it, which the glob would otherwise count
    # as two matches for the same file.
    matches = sorted({p.resolve() for p in Path(deploy_dir).glob("*.qemuboot.conf")})
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one *.qemuboot.conf in {deploy_dir}, "
            f"found {len(matches)}"
        )

    conf = configparser.ConfigParser()
    conf.read(matches[0])
    return dict(conf["config_bsp"])
