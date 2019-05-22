## Obtaining the Source Code

The source code of this project is maintained with git.

```
git clone --recurse-submodules <repository>
cd smart-garden-gateway-public
```

## Prerequisites

* The Yocto build host packages need [to be installed](https://www.yoctoproject.org/docs/2.5.1/brief-yoctoprojectqs/brief-yoctoprojectqs.html#brief-build-system-packages)

## Build Instructions
Set TEMPLATECONF, initiate build directory and run bitbake.

```bash
export TEMPLATECONF=${PWD}/yocto/meta-distribution/conf
source yocto/openembedded-core/oe-init-build-env build-gardena
bitbake gardena-image-opensource-prod
```

## Repository Layout

* ```/``` Top level project
    * ```/yocto/bitbake``` – the Bitbake build tool
    * ```/yocto/openembedded-core``` – OpenEmbedded core layer
    * ```/yocto/meta-mediatek``` – the MediaTek Board Support Package (BSP)
    * ```/yocto/meta-distribution``` – our own distribution (specifies packages to install)
    * ```/yocto/meta-gardena``` – our own code (testing, WiFi provisioning, etc.)
    * ```/yocto/meta-openembedded``` – Collection of layers for the OE-core universe
    * ```/yocto/meta-readonly-rootfs-overlay``` – Writable rootfs overlay on top of a read-only rootfs
    * ```/yocto/meta-swupdate``` – Update mechanism software
