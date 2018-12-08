#!/bin/bash

# This script sets up the public repositories as additional remotes.

base="git@github.com:husqvarnagroup"

declare -A UPSTREAM_REPOS=(
    [yocto/meta-openembedded]="smart-garden-gateway-yocto-meta-openembedded.git"
    [yocto/meta-gardena]="smart-garden-gateway-yocto-meta-gardena.git"
    [yocto/meta-distribution]="smart-garden-gateway-yocto-meta-distribution.git"
    [yocto/meta-mediatek]="smart-garden-gateway-yocto-meta-mediatek.git"
    [yocto/meta-readonly-rootfs-overlay]="smart-garden-gateway-yocto-meta-readonly-rootfs-overlay.git"
    [yocto/meta-swupdate]="smart-garden-gateway-yocto-meta-swupdate.git"
    [yocto/openembedded-core]="smart-garden-gateway-yocto-openembedded-core.git"
    [yocto/bitbake]="smart-garden-gateway-yocto-bitbake.git"
    [yocto/meta-lemonbeat-firmware]="smart-garden-gateway-yocto-meta-lemonbeat-firmware-public.git"
    [.]="smart-garden-gateway-public.git"
    )

scriptdir=$(dirname "$0")
for repo in "${!UPSTREAM_REPOS[@]}"; do
    echo "$repo"
    (cd "$scriptdir/$repo" && (git config --get remote.public.url || git remote add public "${base}/${UPSTREAM_REPOS[$repo]}"))
done
