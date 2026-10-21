# labgrid QEMU Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing `labgrid/tests/` pytest suite against a QEMU instance of the gateway, with the same test code that runs against the hardware bench.

**Architecture:** Add a second labgrid environment file, `labgrid/config/qemu.yaml`, next to the existing `labgrid/config/gateway.yaml`. It uses labgrid's `QEMUDriver`, which implements `PowerProtocol` and `ConsoleProtocol`. The `shell` fixture in `labgrid/tests/conftest.py` already uses only these two protocols, so the test bodies do not change. The target is selected with `--lg-env`.

The image comes from the Yocto `qemuarm` machine target, built with `./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr`. That wrapper fixes the build directory to `build-qemuarm` and the machine name to `gardena-sg-qemuarm`, so the deploy directory is always `build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`. It never changes, so the environment file reads it as a plain relative path. No environment variable and no `!template` substitution is needed.

`QEMUDriver` cannot run `scripts/runqemu.sh` itself as its QEMU binary. The driver always treats `tools.qemu_arm` as the literal `qemu-system-arm` binary. It builds its own argument list (`-kernel`, `-dtb`, `-machine`, `-cpu`, `-S`, `-qmp stdio`). It talks to that binary over the `-qmp stdio` channel. `runqemu.sh` parses a different argument convention. It also does its own setup and logging on the same stdio. The two scripts cannot combine. Instead, read the machine, memory, and QEMU binary path from the build's own generated `*.qemuboot.conf` file. This is the same file `runqemu.sh` itself reads. These values then cannot drift from a future board or image change, and they are not typed in twice by hand. The `*.qemuboot.conf` needs to be read at runtime when the tests are executed. So changes in the QEMU target are reflected in the tests.

A later change can add a similar setup where the DUT (gateway) is flashed with a new image. This plan does not cover that change. It is noted here only for future extensibility.

**Tech Stack:** Python 3.12 or later, poetry, pytest 9, labgrid 26, QEMU (from Yocto build, DON'T USE SYSTEM QEMU), Yocto build `./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr`.

**Spec:** None. The design was agreed in chat and is restated in this plan. This is a bounded change to code that already exists in `labgrid/`.

## Global Constraints

- Work on the current branch `gardena/lw/labgrid-qemu`.
- Python requirement stays `>=3.12`. Dependency pins stay `labgrid (>=26.0,<27.0)` and `pytest (>=9.1.1,<10.0.0)`.
- Do not delete existing tests, fixtures, or markers.
- Do not change existing tests.
- Commit message prefix follows the repository convention: `tests: <summary>`. Keep the first line short. Put the reason in the body.
- The deploy directory is fixed at `build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`. Do not reintroduce an environment variable or `!template` substitution for it.
- New files need the same SPDX header already used across `labgrid/` (`SPDX-FileCopyrightText: GARDENA GmbH`, `SPDX-License-Identifier: GPL-3.0-or-later`).

All paths in this plan are relative to the repository root `/home/lukas/projects/smart-garden-gateway-public`, unless the step says otherwise.

## Review Focus

- The build has run, so the deploy directory exist. Make sure the README states the build command, so the reader can act on the error. Pinned in Task 1 and Task 3.
- `*.qemuboot.conf`'s own `qb_drive_type` field reads `/dev/sd` (SCSI). That field only matters for `runqemu`'s "VM container" filesystem types (`hddimg`, `iso`). This build uses a plain `ext4` image instead, the same type `scripts/runqemu.sh` uses. For `ext4`, `runqemu` always attaches the rootfs as a plain virtio drive and boots `root=/dev/vda rw`, no matter what `qb_drive_type` says. Deriving the disk from `qb_drive_type` produces a kernel that waits forever for a `/dev/sda` that is never attached. Hardcode the virtio drive and `root=/dev/vda` instead, and say why in a comment. Pinned in Task 1.
- The image file is missing or was renamed by a rebuild. QEMU exits at once and `QEMUDriver.on_activate` raises `IOError: QEMU exited immediately` with the QEMU error text. Pinned in Task 1.
- systemd reaches `degraded` on QEMU because a unit that needs real hardware fails. `test_system_running` then fails for a reason that is not a regression. Pinned in Task 1.
- A killed pytest run leaves a `qemu-system-arm` process behind, because `on_deactivate` never runs. The next run then competes for the same image file. Pinned in Task 3.

---

### Task 1: QEMU environment file and a passing boot test

**Files:**
- Create: `labgrid/tests/qemuboot_conf.py`
- Create: `labgrid/tests/test_qemuboot_conf.py`
- Create: `labgrid/config/qemu.yaml`
- Modify: `labgrid/tests/conftest.py`
- Test: `labgrid/tests/test_boot.py` (existing, run unchanged)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `read_qemuboot_conf(deploy_dir) -> dict[str, str]` in `labgrid/tests/qemuboot_conf.py`, used by the `target` fixture in `conftest.py`. An environment file with the target name `main`, a `QEMUDriver` and a `ShellDriver`. Later tasks run `pytest --lg-env config/qemu.yaml`.

- [ ] **Step 1: Build the QEMU image**

```bash
./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr
```

This creates `build-qemuarm/`, always under that fixed name (`scripts/bbwrapper.sh` sets `BUILD_DIR="build-${MACHINE}"`), with the Yocto build for machine `gardena-sg-qemuarm`. The deploy directory ends up at `build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`.

- [ ] **Step 2: Boot the image by hand once**

```bash
./scripts/runqemu.sh gardena-image-bnw-zephyr
```

This proves the build boots before anything in `labgrid/` depends on it. Note the login prompt and the disk and boot arguments `runqemu` prints. They must match what Step 5 writes into `qemu.yaml`.

- [ ] **Step 3: Write the failing tests for reading the build's own configuration file**

Create `labgrid/tests/test_qemuboot_conf.py`:

```python
# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from qemuboot_conf import read_qemuboot_conf


def test_reads_config_bsp_section(tmp_path):
    (tmp_path / "gardena-image-bnw-zephyr-gardena-sg-qemuarm.qemuboot.conf").write_text(
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
    # stable-named symlink to it, matching a plain glob twice for one file.
    target = tmp_path / "image-machine-20261002071132.qemuboot.conf"
    target.write_text("[config_bsp]\nqb_machine = -machine versatilepb\n")
    (tmp_path / "image-machine.qemuboot.conf").symlink_to(target.name)

    bsp = read_qemuboot_conf(tmp_path)

    assert bsp["qb_machine"] == "-machine versatilepb"
```

- [ ] **Step 4: Run the tests to check they fail**

```bash
cd labgrid
poetry run pytest tests/test_qemuboot_conf.py -v
```

Expected: FAIL, `ModuleNotFoundError: No module named 'qemuboot_conf'`.

- [ ] **Step 5: Implement `read_qemuboot_conf(deploy_dir) -> dict[str, str]` in `labgrid/tests/qemuboot_conf.py`**

Glob `deploy_dir` for `*.qemuboot.conf`. Resolve each match first, so the timestamped file and its stable-named symlink count as one. Require exactly one result. Parse it with `configparser` and return its `[config_bsp]` section as a plain `dict`.

- [ ] **Step 6: Run the tests to check they pass**

```bash
cd labgrid
poetry run pytest tests/test_qemuboot_conf.py -v
```

Expected: PASS, 4/4.

- [ ] **Step 7: Write the environment file**

Create `labgrid/config/qemu.yaml`:

```yaml
# SPDX-FileCopyrightText: GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

# QEMU counterpart of gateway.yaml. The kernel, device tree and root
# filesystem come from the Yocto build for MACHINE = gardena-sg-qemuarm,
# always at the fixed path ../../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm,
# relative to this file.
# Build it first with:
#   ./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr
targets:
  main:
    resources: {}
    drivers:
      - QEMUDriver:
          # qemu_bin, machine and memory are filled in by the "target"
          # fixture in conftest.py, read from the build's own
          # *.qemuboot.conf, so they cannot drift from a future board or
          # image change. qemu_bin ends up as the qemu-system-arm that
          # the Yocto build produced for itself, the same one
          # scripts/runqemu.sh uses, not a system-wide install. These
          # three are placeholders, only to satisfy QEMUDriver's
          # required fields at load time.
          qemu_bin: ''
          machine: ''
          memory: ''
          # versatilepb's real core is an ARM926EJ-S, and runqemu does not
          # pass -cpu at all, so QEMU falls back to this machine's default.
          # labgrid's QEMUDriver has no such default and requires "cpu".
          # qemuboot.conf has no matching field, so this stays hardcoded.
          cpu: arm926
          kernel: kernel
          dtb: dtb
          nic: 'user,model=virtio-net-pci'
          # The disk cannot use the driver's own "disk:" key, because
          # QEMUDriver only wires a disk for vexpress-a9, pc, q35 and virt
          # and raises NotImplementedError for anything else
          # (labgrid/driver/qemudriver.py:192). qemuboot.conf's own
          # qb_drive_type reads "/dev/sd" (SCSI), but that field only
          # applies to runqemu's "VM container" filesystem types (hddimg,
          # iso); for a plain ext4 image, runqemu always attaches a
          # virtio drive and boots root=/dev/vda, so do the same here
          # rather than follow qb_drive_type.
          extra_args: '-drive file=../../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm/gardena-image-bnw-zephyr-gardena-sg-qemuarm.ext4,if=virtio,format=raw'
          # net.ifnames=0 keeps the interface named eth0, which is what
          # unique-hostname reads to build the GARDENA-<id> hostname
          boot_args: 'root=/dev/vda rw rootwait swiotlb=0 console=ttyAMA0,115200 net.ifnames=0'
      - ShellDriver:
          login_prompt: 'GARDENA-[0-9a-f]{6} login: '
          username: root
          # the image's PS1 prints "ERROR: <code> | " before the prompt when
          # the previous command exited non-zero
          prompt: '(?:ERROR: \d+ \| )?root@GARDENA-[0-9a-f]{6}:~# '
          login_timeout: 120
          post_login_settle_time: 2
images:
  # These two filenames match kernel_imagetype and qb_dtb in the build's
  # *.qemuboot.conf. Update them by hand if a future board or image
  # change renames either file.
  kernel: ../../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm/zImage
  dtb: ../../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm/qemu-gardena-smart-gateway.dtb
```

- [ ] **Step 8: Add the `target` fixture**

Add to `labgrid/tests/conftest.py`, above the existing `shell` fixture:

```python
from pathlib import Path

from qemuboot_conf import read_qemuboot_conf

DEPLOY_DIR = (
    Path(__file__).parent.parent.parent
    / "build-qemuarm" / "tmp" / "deploy" / "images" / "gardena-sg-qemuarm"
)


@pytest.fixture(scope="session")
def target(target):
    """Fill in the QEMUDriver fields that come from the build's own configuration file.

    Runs before the driver is first activated, so qemu_bin, machine and
    memory never hold their qemu.yaml placeholder values at boot time.
    """
    bsp = read_qemuboot_conf(DEPLOY_DIR)
    driver = target.get_driver("QEMUDriver", activate=False)
    driver.machine = bsp["qb_machine"].removeprefix("-machine ")
    driver.memory = bsp["qb_mem"].removeprefix("-m ")
    driver.qemu_bin = str(
        (DEPLOY_DIR / bsp["staging_bindir_native"] / bsp["qb_system_name"]).resolve()
    )
    return target
```

One line on the approach: labgrid's pytest plugin already provides a fixture named `target` for `--lg-env`. Redefining it under the same name lets pytest's fixture override mechanism run this setup once. That happens before `shell`, which also depends on `target`, calls `get_driver` for real.

- [ ] **Step 9: Run the boot test against QEMU**

```bash
cd labgrid
poetry install
poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py -v
```

Expected: PASS.

`QEMUDriver` starts QEMU paused, because `on_activate` passes `-S` (`labgrid/driver/qemudriver.py:236`). The `shell` fixture in `labgrid/tests/conftest.py` calls `cycle()` on the `PowerProtocol`, and `cycle()` calls `on()`, which sends `cont`. That is what starts the boot.

- [ ] **Step 10: If the boot test fails, find out why before changing anything**

If `test_system_running` reports a state other than `running`, the failure message already lists the failed units. Read that list.

- If the failed unit needs real hardware that QEMU does not have, do not weaken the test. Record the unit name and stop. Ask which behavior is wanted before you continue, because loosening `test_system_running` also loosens it for the bench.
- If QEMU exits with `IOError: QEMU exited immediately`, read the QEMU error text in the same message. A wrong or missing file path is the usual cause. Repeat Step 2.
- If `read_qemuboot_conf` raises `found 0`, the deploy directory does not exist yet. Repeat Step 1.
- If `read_qemuboot_conf` raises `found 2` or more, a second image was built into the same deploy directory. List `*.qemuboot.conf` in that directory and remove the files for any image other than `gardena-image-bnw-zephyr`.

- [ ] **Step 11: Check the two error paths on purpose**

```bash
# commands below assume the shell is still inside labgrid/, from Step 4
mv ../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm /tmp/qemuarm-deploy-backup
poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py 2>&1 | tail -5
mkdir -p ../build-qemuarm/tmp/deploy/images
mv /tmp/qemuarm-deploy-backup ../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm
mv ../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm/gardena-image-bnw-zephyr-gardena-sg-qemuarm.ext4 /tmp/
poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py 2>&1 | tail -5
mv /tmp/gardena-image-bnw-zephyr-gardena-sg-qemuarm.ext4 ../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm/
```

Expected: the first names the missing deploy directory and that zero `*.qemuboot.conf` files were found there. The second reports a missing image file or `QEMU exited immediately`. Both messages must say enough for a reader to fix the cause. If they do not, add the missing fact to the README in Task 3.

- [ ] **Step 12: Commit**

```bash
git add labgrid/tests/qemuboot_conf.py labgrid/tests/test_qemuboot_conf.py labgrid/config/qemu.yaml labgrid/tests/conftest.py
git commit -m "tests: Add QEMU labgrid target

Reads machine, memory and the QEMU binary path from the Yocto build's
own *.qemuboot.conf, so they cannot drift from a future board or image
change and are not duplicated by hand."
```

### Task 2: Power-cycle before login (already done)

**Files:**
- Already modified: `labgrid/tests/conftest.py`

**Interfaces:**
- Consumes: `config/qemu.yaml` and the `target` fixture from Task 1, to check that the existing fixture also works against QEMU.
- Produces: nothing new.

The `shell` fixture in `labgrid/tests/conftest.py` already power-cycles the target before returning the `ShellDriver`:

```python
@pytest.fixture(scope="session")
def shell(target):
    """Power-cycle the target and log in.

    Cycling on setup rather than cleaning up on teardown keeps the starting
    state independent of whatever a previous run left behind.
    """
    target.get_driver("PowerProtocol").cycle()
    return target.get_driver("ShellDriver")
```

`test_boot.py` and `labgrid/tests/test_gw_info.py` already use `shell`, together with the `gateway_system_is_running` fixture that depends on it. This is exactly what QEMU needs: `QEMUDriver` starts the emulator paused, and `cycle()` is what sends the `cont` that starts the boot (see Task 1, Step 9). No fixture change is needed for QEMU beyond the `target` override from Task 1. What remains is to check that the existing fixture also passes against the QEMU target once Task 1 lands.

- [ ] **Step 1: Run the full suite against QEMU**

```bash
cd labgrid
poetry run pytest --lg-env config/qemu.yaml tests/ -v
```

- [ ] **Step 2: Check that `test_system_running`, `test_proc_version` and `test_os_release` pass unmodified**

### Task 3: Document the QEMU target and the path to more targets

**Files:**
- Modify: `labgrid/README.md`

**Interfaces:**
- Consumes: everything from Tasks 1 and 2.
- Produces: nothing that code depends on.

- [ ] **Step 1: Add a QEMU section to the README**

Add the following after the "Quick Start" section of `labgrid/README.md`:

```markdown
## Running against QEMU

The suite runs without the bench against a QEMU instance of the same image.
Build the image first, then select the QEMU environment:

    ./scripts/bbwrapper.sh qemuarm gardena-image-bnw-zephyr
    cd labgrid
    poetry run pytest --lg-env config/qemu.yaml tests/

The build directory and deploy path are fixed
(`build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm`), so no extra
configuration is needed. If the image was not built yet, labgrid stops
with a message naming that directory and that no `*.qemuboot.conf` file
was found there.

If a run is killed rather than stopped, a `qemu-system-arm` process stays
behind, because labgrid never reaches `on_deactivate`. Check with
`pgrep -a qemu-system-arm` and end it before the next run.
```

- [ ] **Step 2: Add a section on adding more targets**

Add this at the end of `labgrid/README.md`:

```markdown
## Adding more targets

One file per target under `config/`, selected with `--lg-env` or `LG_ENV`.
The tests read nothing that is specific to a bench.

Two rules keep this working as the number of targets grows:

- With a second serial adapter on the same machine, `/dev/ttyUSB0` is no
  longer stable. Replace `RawSerialPort` with `USBSerialPort` and a udev
  `match:`, which names the adapter by its USB path instead of its order.
- With a labgrid coordinator, only the `resources:` block changes, to
  `RemotePlace` with `name: !template '$LG_PLACE'`. Drivers, fixtures and
  tests stay as they are. QEMU is not affected, because labgrid has no QEMU
  resource and no QEMU exporter. QEMU always runs on the machine that runs
  pytest, so it never needs a reservation.
```

- [ ] **Step 3: Check the stale process claim**

```bash
cd labgrid
poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py &
sleep 20
kill -9 %1
pgrep -a qemu-system-arm
```

Expected: `pgrep` lists a process. That matches the README warning. End it with `pkill -f qemu-system-arm` before you continue.

- [ ] **Step 4: Check that both environment files still parse**

This repository has no pre-commit configuration, so there is no linter to run
over these files. Parse both environment files instead, which catches a YAML
mistake without waiting for a boot:

```bash
cd labgrid
poetry run python -c "from labgrid import Environment; Environment('config/qemu.yaml'); Environment('config/gateway.yaml'); print('both parse')"
```

Expected: `both parse`.

- [ ] **Step 5: Run the full suite once more on both targets**

```bash
cd labgrid
poetry run pytest --lg-env config/qemu.yaml tests/ -v
poetry run pytest --lg-env config/gateway.yaml tests/ -v
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/lukas/projects/smart-garden-gateway-public
git add labgrid/README.md
git commit -m "tests: Document the QEMU target

Also records the two rules that keep the layout working when more targets
are added: udev-matched serial ports, and a resources-only change when a
coordinator arrives."
```
