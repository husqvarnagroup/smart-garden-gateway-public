# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest


@pytest.fixture(scope="session")
def shell(target):
    """Power-cycle the target and log in.

    Cycling on setup rather than cleaning up on teardown keeps the starting
    state independent of whatever a previous run left behind.
    """
    target.get_driver("PowerProtocol").cycle()
    return target.get_driver("ShellDriver")
