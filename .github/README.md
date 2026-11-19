# Ark image builder

This repository builds the immutable Ark Linux OCI images used by the installer. Images are composed in three independently published stages:

1. **Userspace base** — desktop KDE profile or headless server profile, shared system services and common tools. No kernel or GPU driver is installed in this stage.
2. **Kernel image** — adds one kernel family and its headers to the appropriate userspace base, then installs the shared Ark AUR payload.
3. **Final image** — adds the selected GPU driver (if any), builds the initramfs after the driver is present, and performs bootc cleanup and validation.

The intermediate tags are implementation layers. Users and the installer should consume the final variant tags listed below.

## Published final images

| Final tag | Userspace | Kernel | GPU driver |
|---|---|---|---|
| `intel-modern` | KDE Plasma desktop | Arch `linux` | Mesa / Intel iGPU |
| `intel-modern-apex` | KDE Plasma desktop | CachyOS Apex | Mesa / Intel iGPU |
| `intel3-server-lts` | Headless server | Arch `linux-lts` | No proprietary GPU stack |
| `ark-nvidia-580` | KDE Plasma desktop | Arch `linux` | NVIDIA 580 proprietary DKMS |
| `ark-apex-nvidia-580` | KDE Plasma desktop | CachyOS Apex | NVIDIA 580 proprietary DKMS |
| `ark-nvidia-open` | KDE Plasma desktop | Arch `linux` | NVIDIA open DKMS |
| `ark-apex-nvidia-open` | KDE Plasma desktop | CachyOS Apex | NVIDIA open DKMS |

The existing final image tags remain stable so installer references do not need to change during this refactor.

## Intermediate image tags

The workflow publishes these tags to GHCR so each stage can be reused:

| Stage | Tags |
|---|---|
| Userspace bases | `base-desktop`, `base-server` |
| Kernel images | `kernel-desktop-standard`, `kernel-desktop-apex`, `kernel-server-lts` |

The build order is **base → kernel → final driver image**. The final stage always generates the initramfs after adding the selected driver, ensuring the boot image contains the correct modules. The intermediate base and kernel tags are not bootable install targets.

## Build workflow

`.github/workflows/build-payload.yml` runs the stages in dependency order and publishes each stage to GHCR. Existing automatic push/scheduled builds use GitHub-hosted runners. Manual dispatch supports either:

- `github-hosted` — GitHub-hosted runner (default)
- `self-hosted` — a registered x86_64 Linux runner with rootless Podman, `wget`, and `curl`, labelled `ark-builder`

The workflow builds only the three required kernel layers, then composes the seven final variants. The NVIDIA driver is no longer reinstalled for every kernel build; it is added only in the final stage that needs it.

## Build arguments

- `VARIANT`: selects the desktop/server profile and the kernel or driver configuration.
- `BASE_IMAGE`: source userspace image for the kernel stage.
- `KERNEL_IMAGE`: source kernel image for the final driver stage.
- `AUR_SHA`, `CARRIER_SHA`, and `CARRIER_URL`: pin the external Ark payload inputs used by the build.

## System design

Ark uses Btrfs + Snapper + snap-pac. ZFS/SPL packages are excluded. The installer creates the Btrfs subvolume layout and initializes Snapper's `root` configuration on the target filesystem.

The desktop profile uses KDE Plasma, Waterfox from Flathub, TuneD/tuned-ppd, Podman, and the Ark feature manager. The server profile is headless, uses the LTS kernel, enables Cockpit and SSH, and permits SSH password authentication while disabling root SSH login.

## Local build examples

Build the desktop userspace base:

```bash
podman build --target base --build-arg VARIANT=intel-modern \
  -t localhost/ark:base-desktop -f .github/Containerfile .github/
```

Build its standard kernel layer:

```bash
podman build --target kernel \
  --build-arg BASE_IMAGE=localhost/ark:base-desktop \
  --build-arg VARIANT=intel-modern \
  -t localhost/ark:kernel-desktop-standard \
  -f .github/Containerfile .github/
```

Build the final image (for an NVIDIA-free Intel desktop):

```bash
podman build \
  --build-arg KERNEL_IMAGE=localhost/ark:kernel-desktop-standard \
  --build-arg VARIANT=intel-modern \
  -t localhost/ark:intel-modern \
  -f .github/Containerfile .github/
```

Kernel-stage builds also require the AUR package bundle and pacman cache mount used by the GitHub Actions workflow.

## Repository structure

Build files live in `.github/`:

- `Containerfile` — three-stage userspace, kernel, and final-driver image definition
- `install-packages.sh` — installs and validates the shared prebuilt Ark AUR payload
- `build-payload.yml` — staged image build and GHCR publication workflow
- `bls-sync.sh`, `ark-bls-sync.service`, and `bls-sync.conf` — boot entry synchronization
- `ark` and related scripts — Ark runtime feature and system integration tools

## Deployment

The installer consumes the final tags above. Intermediate `base-*` and `kernel-*` tags are build inputs only.
