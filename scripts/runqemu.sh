#!/bin/bash
#
# This is a convenience wrapper for the runqemu command. It boots an image
# built for the "qemuarm" machine, see scripts/bbwrapper.sh.
#
# Usage: scripts/runqemu.sh [<image>] [--no-rm-simulation] [--rm-verbose]
#                           [<runqemu option>...]
#
# Another image can be named as the first argument. Other options are forwarded
# to runqemu:
#
#     scripts/runqemu.sh gardena-image-foss-bnw qemuparams="-m 256"
#
# The gateway's second serial port is connected to a fake radio module (see
# tools/fake-radio-module). Pass --no-rm-simulation to leave it unconnected, or
# --rm-verbose to log every API command and control packet.
#
# For SSH access, run:
#
#     ssh -p 2222 root@localhost

set -e -o pipefail

MACHINE="gardena-sg-qemuarm"
BUILD_DIR="build-qemuarm"

IMAGE="gardena-image-foss-bnw"
if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then
    IMAGE="$1"
    shift
fi

RM_SIMULATION=1
rm_args=()
qemuparams=""
args=()
for arg in "$@"; do
    if [ "${arg}" = "--no-rm-simulation" ]; then
        RM_SIMULATION=0
    elif [ "${arg}" = "--rm-verbose" ]; then
        rm_args+=("--verbose")
    elif [ "${arg#qemuparams=}" != "${arg}" ]; then
        qemuparams="${arg#qemuparams=}"
    else
        args+=("${arg}")
    fi
done
set -- "${args[@]}"

script_dir="$(dirname "$(readlink -f "$0")")"
cd "${script_dir}"
gitroot="$(git rev-parse --show-toplevel)"
cd "$gitroot"

if [ ! -d "${BUILD_DIR}" ]; then
    echo "No build directory '${BUILD_DIR}'. Build the image first:" >&2
    echo "  scripts/bbwrapper.sh qemuarm ${IMAGE}" >&2
    exit 1
fi

conf="${BUILD_DIR}/tmp/deploy/images/${MACHINE}/${IMAGE}-${MACHINE}.qemuboot.conf"
if [ ! -e "${conf}" ]; then
    echo "No image '${IMAGE}' for machine '${MACHINE}'. Build it first:" >&2
    echo "  scripts/bbwrapper.sh qemuarm ${IMAGE}" >&2
    exit 1
fi
conf="${gitroot}/${conf}"

if [ "${RM_SIMULATION}" = 1 ]; then
    sock="${gitroot}/${BUILD_DIR}/fake-rm.sock"
    log="${gitroot}/${BUILD_DIR}/fake-rm.log"
    rm -f "${sock}"

    # With "nographic", runqemu ignores QB_SERIAL_OPT and leaves the second
    # serial port unconnected. When both ports are passed explicitly, runqemu
    # keeps them as they are. runqemu only uses the last qemuparams argument, so
    # the options passed by the user are merged here.
    qemuparams="-serial mon:stdio -serial unix:${sock},server=on,wait=off ${qemuparams}"

    # Log to a file, as the terminal is used for the gateway console.
    PYTHONPATH="${gitroot}/tools/fake-radio-module" python3 -m fake_rm "${rm_args[@]}" "${sock}" > "${log}" 2>&1 &
    fake_rm_pid=$!
    trap 'kill "${fake_rm_pid}" 2>/dev/null; rm -f "${sock}"' EXIT
    echo "Fake radio module is logging to ${log}" >&2
fi

if [ -n "${qemuparams}" ]; then
    set -- "$@" "qemuparams=${qemuparams}"
fi

source yocto/openembedded-core/oe-init-build-env "${BUILD_DIR}" >/dev/null

runqemu "${conf}" ext4 slirp nographic "$@"
