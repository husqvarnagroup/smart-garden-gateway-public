#!/bin/bash

# This script pushes a specific version (tag) to GitHub.
#
# Usage:  ./publicify.sh <tag> [GitHub username]

# Example: ./publicify.sh release/linux-system-3.3.0.2 husqvarnagroup

set -eu -o pipefail

readonly release_tag=$1
readonly base="git@github.com:${2-husqvarnagroup}"

declare -A PUBLIC_REPOS=(
    [yocto/meta-openembedded]="smart-garden-gateway-yocto-meta-openembedded.git"
    [yocto/meta-gardena]="smart-garden-gateway-yocto-meta-gardena.git"
    [yocto/meta-distribution]="smart-garden-gateway-yocto-meta-distribution.git"
    [yocto/meta-mediatek]="smart-garden-gateway-yocto-meta-mediatek.git"
    [yocto/meta-readonly-rootfs-overlay]="smart-garden-gateway-yocto-meta-readonly-rootfs-overlay.git"
    [yocto/meta-swupdate]="smart-garden-gateway-yocto-meta-swupdate.git"
    [yocto/openembedded-core]="smart-garden-gateway-yocto-openembedded-core.git"
    [yocto/bitbake]="smart-garden-gateway-yocto-bitbake.git"
    [yocto/meta-rust]="smart-garden-gateway-yocto-meta-rust.git"
    [.]="smart-garden-gateway-public.git"
    )

scriptdir=$(dirname "$0")
for repo in "${!PUBLIC_REPOS[@]}"; do
    echo "$repo"
    (cd "$scriptdir/$repo" && (git remote set-url public "${base}/${PUBLIC_REPOS[$repo]}" || remote add public "${base}/${PUBLIC_REPOS[$repo]}"))
done

git submodule foreach "git push public \"${release_tag}\""
git push public master "${release_tag}"
