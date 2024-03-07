#!/bin/bash
#
# This is a convenience wrapper for the bitbake command.

set -e -o pipefail

MACHINE="$1"
BUILD_DIR="build-${MACHINE}"

script_dir="$(dirname "$(readlink -f "$0")")"
cd "${script_dir}"
gitroot="$(git rev-parse --show-toplevel)"
cd "$gitroot"

# If BitBake (and therefore the build directory) was not set up before, then do it now.
if ! type bitbake >/dev/null 2>&1; then
  TEMPLATECONF="${gitroot}/yocto/meta-distribution/conf"
  export TEMPLATECONF
  source yocto/openembedded-core/oe-init-build-env "${BUILD_DIR}"
  sed -i 's/\(^MACHINE ??= "\).*\(".*\)/\1'gardena-sg-${MACHINE}'\2/g' conf/local.conf
fi

# Using git and annotated tags in the form or release/linux-system-X.Y.Z[-suffix] to determine the distribution version.
DISTRO_VERSION_ID="$(git describe --tags --dirty --match release/linux-system* | cut -c 22-)"
DISTRO_VERSION="$(echo "${DISTRO_VERSION_ID}" | egrep -o '[0-9]+\.[0-9]+\.[0-9]+' )"
DISTRO_UPDATE_URL="${DISTRO_UPDATE_URL:-http://10.42.0.1:8000/gardena-update-image-prod-gardena-sg-${MACHINE}.swu}"
DISTRO_UPDATE_URL_BASE="${DISTRO_UPDATE_URL_BASE:-http://gateway.iot.sg.dss.husqvarnagroup.net/images}"
PACKAGE_FEED_URIS="${PACKAGE_FEED_URIS:-http://gateway.iot.sg.dss.husqvarnagroup.net/archive/${DISTRO_VERSION}/gardena-sg-${MACHINE}}"

BB_ENV_EXTRAWHITE="$BB_ENV_EXTRAWHITE \
  DISTRO_UPDATE_URL \
  DISTRO_UPDATE_URL_BASE \
  DISTRO_VERSION \
  DISTRO_VERSION_ID \
  PACKAGE_FEED_URIS \
"
export \
  BB_ENV_EXTRAWHITE \
  DISTRO_UPDATE_URL \
  DISTRO_UPDATE_URL_BASE \
  DISTRO_VERSION \
  DISTRO_VERSION_ID \
  PACKAGE_FEED_URIS

exec bitbake "${@:2}"
