## Foreword
Please be aware that any modification to your gateway, in particular a modification of U-Boot, may permanently brick your device and is not covered by warranty.

# Compiling the Software

## Obtaining the Source Code

The source code of this project is maintained with git.

```
git clone --recurse-submodules <repository>
cd smart-garden-gateway-public
```

Older versions of the build system can be found in the history. However, only for the most recent master we intend to ensure that the build works.

Source code packages for all distributed versions can be found [here](https://opensource.smart.gardena.dev/gateway/index.html).

## Prerequisites

* The Yocto build host packages need [to be installed](https://www.yoctoproject.org/docs/2.5.1/brief-yoctoprojectqs/brief-yoctoprojectqs.html#brief-build-system-packages)

## Build Instructions
Set TEMPLATECONF, initiate build directory and run bitbake.

### Article Number 19005 (MediaTek MT7688)
```bash
export TEMPLATECONF=${PWD}/yocto/meta-distribution/conf
source yocto/openembedded-core/oe-init-build-env build-mt7688
bitbake gardena-image-opensource-prod
```

## Repository Layout

* ```/``` Top level project.
    * ```/yocto/bitbake``` – the Bitbake build tool
    * ```/yocto/openembedded-core``` – OpenEmbedded core layer
    * ```/yocto/meta-mediatek``` – the MediaTek Board Support Package (BSP), used only for Art. No. 19005
    * ```/yocto/meta-distribution``` – our own distribution (specifies packages to install)
    * ```/yocto/meta-gardena``` – our own code (testing, WiFi provisioning, etc.)
    * ```/yocto/meta-openembedded``` – Collection of layers for the OE-core universe
    * ```/yocto/meta-readonly-rootfs-overlay``` – Writable rootfs overlay on top of a read-only rootfs
    * ```/yocto/meta-swupdate``` – Update mechanism software
    * ```/yocto/meta-atmel``` – our Atmel Board Support Package (BSP), used only for Art. No. 19000

# Getting access

## Art. No. 19005
The serial port can be found on J7. Settings are 115200 8N1, the level is 3.3V.

![PCBA](doc/19005-pins.jpg)

Once connected, simply follow the instructions printed during startup.

## Art. No. 19000
We do not provide (yet!) any help rooting this device. The internet however does.
