#!/bin/bash
#
# This is a convenience wrapper for the runqemu command. It boots an image
# built for the "qemuarm" machine, see scripts/bbwrapper.sh.
#
# Usage: scripts/runqemu.sh [<image>] [<runqemu option>...]
#
# Another image can be named as the first argument, and everything after it
# reaches runqemu unchanged:
#
#     scripts/runqemu.sh gardena-image-foss-bnw qemuparams="-m 256"
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

source yocto/openembedded-core/oe-init-build-env "${BUILD_DIR}" >/dev/null

exec runqemu "${conf}" ext4 slirp nographic "$@"
