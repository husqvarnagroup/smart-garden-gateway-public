# labgrid QEMU Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing `tests/` pytest suite against a QEMU instance of the gateway, with the same test code that runs against the hardware bench.

**Architecture:** Add a second labgrid environment file, `tests/config/qemu.yaml`, next to the existing `tests/config/gateway.yaml`. It uses labgrid's `QEMUDriver`, which implements `PowerProtocol` and `ConsoleProtocol`. The `shell` fixture in `tests/tests/conftest.py` already uses only these two protocols, so the test bodies do not change. The target is selected with `--lg-env`.

A later change can add a similar setup where the DUT (gateway) is flashed with a new image. This plan does not cover that change. It is noted here only for future extensibility.

**Tech Stack:** Python 3.12 or later, poetry, pytest 9, labgrid 26, QEMU (`qemu-system-arm`), Yocto build `./scripts/bbwrapper.sh qemuarm gardena-image-foss-bnw`.

**Spec:** None. The design was agreed in chat and is restated in this plan. This is a bounded change to code that already exists in `tests/`.

## Global Constraints

- Work on the current branch `gardena/lw/labgrid-qemu`.
- Python requirement stays `>=3.12`. Dependency pins stay `labgrid (>=26.0,<27.0)` and `pytest (>=9.1.1,<10.0.0)`.
- Do not delete existing tests, fixtures, or markers.
- Commit message prefix follows the repository convention: `tests: <summary>`. Keep the first line short. Put the reason in the body.
- labgrid substitutes only `BASE` and environment variables whose name starts with `LG_` inside `!template`. Any new variable must therefore start with `LG_`.

All paths in this plan are relative to the repository root `/home/lukas/projects/smart-garden-gateway-public`, unless the step says otherwise.

## Review Focus

Running qemu image: `scripts/runqemu.sh gardena-image-foss-bnw`. Use as inspiration on how to use `QEMUDriver` and other utilities from labgrid.

- `LG_DEPLOY_DIR` is not set. labgrid raises `InvalidConfigError` naming the unknown variable. Make sure that the README states the variable, so the reader can act on the error. Pinned in Task 1.
- The image file is missing or was renamed by a rebuild. QEMU exits at once and `QEMUDriver.on_activate` raises `IOError: QEMU exited immediately` with the QEMU error text. Pinned in Task 1.
- systemd reaches `degraded` on QEMU because a unit that needs real hardware fails. `test_system_running` then fails for a reason that is not a regression. Pinned in Task 1.
- A killed pytest run leaves a `qemu-system-arm` process behind, because `on_deactivate` never runs. The next run then competes for the same image file. Pinned in Task 3.

---

### Task 1: QEMU environment file and a passing boot test

**Files:**
- Create: `tests/config/qemu.yaml`
- Test: `tests/tests/test_boot.py` (existing, run unchanged)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: an environment file with the target name `main`, a `QEMUDriver` and a `ShellDriver`. Later tasks run `pytest --lg-env config/qemu.yaml`. The environment variable `LG_DEPLOY_DIR` holds the Yocto deploy directory for the machine `gardena-sg-qemuarm`.

- [ ] **Step 1: Build and install the QEMU binary**

./scripts/bbwrapper.sh qemuarm gardena-image-foss-bnw

- [ ] **Step 2: Boot the image by hand once**

./scripts/runqemu.sh gardena-image-foss-bnw

- [ ] **Step 3: Write the environment file**

Create `tests/config/qemu.yaml`:

```yaml
# QEMU counterpart of gateway.yaml. The kernel, device tree and root
# filesystem come from the Yocto build for MACHINE = gardena-sg-qemuarm.
# Point LG_DEPLOY_DIR at that build's deploy directory, for example:
#   export LG_DEPLOY_DIR=$PWD/build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm
targets:
  main:
    resources: {}
    drivers:
      - QEMUDriver:
          qemu_bin: qemu_arm
          # machine, memory and device tree follow the build's
          # gardena-image-bnw-zephyr-gardena-sg-qemuarm.qemuboot.conf
          machine: versatilepb
          memory: 128M
          kernel: kernel
          dtb: dtb
          nic: 'user,model=virtio-net-pci'
          # The disk cannot use the driver's own "disk:" key, because
          # QEMUDriver only wires a disk for vexpress-a9, pc, q35 and virt
          # and raises NotImplementedError for anything else
          # (labgrid/driver/qemudriver.py:192). runqemu turns the machine's
          # QB_DRIVE_TYPE of /dev/sd into a virtio SCSI disk, so do the same
          # here and boot from /dev/sda.
          extra_args: !template '-drive if=none,id=hd,file=$LG_DEPLOY_DIR/gardena-image-bnw-zephyr-gardena-sg-qemuarm.ext4,format=raw -device virtio-scsi-pci,id=scsi -device scsi-hd,drive=hd'
          # net.ifnames=0 keeps the interface named eth0, which is what
          # unique-hostname reads to build the GARDENA-<id> hostname
          boot_args: 'root=/dev/sda rootwait swiotlb=0 console=ttyAMA0,115200 net.ifnames=0'
      - ShellDriver:
          login_prompt: 'GARDENA-[0-9a-f]{6} login: '
          username: root
          # the image's PS1 prints "ERROR: <code> | " before the prompt when
          # the previous command exited non-zero
          prompt: '(?:ERROR: \d+ \| )?root@GARDENA-[0-9a-f]{6}:~# '
          login_timeout: 120
          post_login_settle_time: 2
images:
  kernel: !template '$LG_DEPLOY_DIR/zImage'
  dtb: !template '$LG_DEPLOY_DIR/qemu-gardena-smart-gateway.dtb'
tools:
  qemu_arm: /usr/bin/qemu-system-arm
```

- [ ] **Step 4: Run the boot test against QEMU**

Run:

```bash
cd tests
poetry install
poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py -v
```

Expected: PASS.

`QEMUDriver` starts QEMU paused, because `on_activate` passes `-S` (`labgrid/driver/qemudriver.py:236`). The `shell` fixture in `tests/tests/conftest.py` calls `cycle()` on the `PowerProtocol`, and `cycle()` calls `on()`, which sends `cont`. That is what starts the boot.

- [ ] **Step 5: If the boot test fails, find out why before changing anything**

If `test_system_running` reports a state other than `running`, the failure message already lists the failed units. Read that list.

- If the failed unit needs real hardware that QEMU does not have, do not weaken the test. Record the unit name and stop. Ask which behavior is wanted before you continue, because loosening `test_system_running` also loosens it for the bench.
- If QEMU exits with `IOError: QEMU exited immediately`, read the QEMU error text in the same message. A wrong or missing file path is the usual cause. Repeat Step 2.
- If labgrid reports `configuration file ... refers to unknown variable 'LG_DEPLOY_DIR'`, the variable is not exported in this shell. Repeat Step 2.

- [ ] **Step 6: Check the two error paths on purpose**

Run:

```bash
env -u LG_DEPLOY_DIR poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py 2>&1 | tail -5
LG_DEPLOY_DIR=/nonexistent poetry run pytest --lg-env config/qemu.yaml tests/test_boot.py 2>&1 | tail -5
```

Expected: the first names `LG_DEPLOY_DIR` as an unknown variable. The second reports a missing image file or `QEMU exited immediately`. Both messages must say enough for a reader to fix the cause. If they do not, add the missing fact to the README in Task 3.

- [ ] **Step 7: Commit**

### Task 2: Power-cycle before login (already done)

**Files:**
- Already modified: `tests/tests/conftest.py`

**Interfaces:**
- Consumes: `config/qemu.yaml` from Task 1, to check that the existing fixture also works against QEMU.
- Produces: nothing new.

The `shell` fixture in `tests/tests/conftest.py` already power-cycles the target before returning the `ShellDriver`:

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

`test_boot.py` and `tests/test_gw_info.py` already use `shell`, together with the `gateway_system_is_running` fixture that depends on it. This is exactly what QEMU needs: `QEMUDriver` starts the emulator paused, and `cycle()` is what sends the `cont` that starts the boot (see Task 1, Step 4). No fixture change is needed for QEMU. What remains is to check that the existing fixture also passes against the QEMU target once Task 1 lands.

- [ ] **Step 1: Run the full suite against QEMU**

Run:

```bash
cd tests
poetry run pytest --lg-env config/qemu.yaml tests/ -v
```

- [ ] **Step 2: Check that `test_system_running`, `test_proc_version` and `test_os_release` pass unmodified**

### Task 3: Document the QEMU target and the path to more targets

**Files:**
- Modify: `tests/README.md`

**Interfaces:**
- Consumes: everything from Tasks 1 and 2.
- Produces: nothing that code depends on.

- [ ] **Step 1: Add a QEMU section to the README**

Add the following after the "Quick Start" section of `tests/README.md`:

```markdown
## Running against QEMU

The suite runs without the bench against a QEMU instance of the same image.
Build the image for the machine `gardena-sg-qemuarm`, install
`qemu-system-arm`, then point `LG_DEPLOY_DIR` at the deploy directory and
select the QEMU environment:

    export LG_DEPLOY_DIR=$PWD/../build-qemuarm/tmp/deploy/images/gardena-sg-qemuarm
    poetry run pytest --lg-env config/qemu.yaml tests/

labgrid substitutes only `BASE` and variables whose name starts with `LG_`,
which is why the variable is called `LG_DEPLOY_DIR`. If it is not set,
labgrid stops with `configuration file ... refers to unknown variable`.

If a run is killed rather than stopped, a `qemu-system-arm` process stays
behind, because labgrid never reaches `on_deactivate`. Check with
`pgrep -a qemu-system-arm` and end it before the next run.
```

- [ ] **Step 2: Add a section on adding more targets**

Add this at the end of `tests/README.md`:

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

Run:

```bash
cd tests
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
cd tests
poetry run python -c "from labgrid import Environment; Environment('config/qemu.yaml'); Environment('config/gateway.yaml'); print('both parse')"
```

Expected: `both parse`. `LG_DEPLOY_DIR` has to be exported, because
`config/qemu.yaml` refers to it.

- [ ] **Step 5: Run the full suite once more on both targets**

Run:

```bash
cd tests
poetry run pytest --lg-env config/qemu.yaml tests/ -v
poetry run pytest --lg-env config/gateway.yaml tests/ -v
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/lukas/projects/smart-garden-gateway-public
git add tests/README.md
git commit -m "tests: Document the QEMU target

Also records the two rules that keep the layout working when more targets
are added: udev-matched serial ports, and a resources-only change when a
coordinator arrives."
```
