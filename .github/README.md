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

The workflow builds only the three required kernel layers, then composes the seven final variants. The NVIDIA driver is added only in the final stage that needs it. The independent agent development environment is built alongside the payload rather than acting as a prerequisite.

For targeted testing, there are seven individually named **full payload** workflows. Each one builds only the selected image's required userspace base, matching kernel, and final image. The base and kernel are built locally on the same runner and are not pushed as intermediate tags; only the selected final image is published. This avoids unrelated variants, repeated runner setup, and intermediate registry uploads.

| Actions workflow | Final image |
|---|---|
| [Build Full Payload - Intel Standard Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-intel-modern.yml) | `intel-modern` |
| [Build Full Payload - Intel Apex Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-intel-modern-apex.yml) | `intel-modern-apex` |
| [Build Full Payload - NVIDIA Open Standard Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-ark-nvidia-open.yml) | `ark-nvidia-open` |
| [Build Full Payload - NVIDIA Open Apex Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-ark-apex-nvidia-open.yml) | `ark-apex-nvidia-open` |
| [Build Full Payload - NVIDIA 580 Standard Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-ark-nvidia-580.yml) | `ark-nvidia-580` |
| [Build Full Payload - NVIDIA 580 Apex Desktop](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-ark-apex-nvidia-580.yml) | `ark-apex-nvidia-580` |
| [Build Full Payload - Intel Server LTS](https://github.com/lydiaperspective/lyd-ark-image/actions/workflows/build-full-intel3-server-lts.yml) | `intel3-server-lts` |

All seven use the shared `.github/workflows/build-single-final-payload.yml` implementation. They serialize with the other image-release workflows because the existing full pipeline publishes shared image tags. Package downloads and the prebuilt Pacman package cache are retained in GitHub Actions cache by release identity. The separate agent development environment job no longer blocks base-image builds; it runs independently.

For a full non-Apex rebuild, `.github/workflows/build-payload-standard.yml` runs the same base → kernel → final pipeline but builds only `kernel-desktop-standard` and `kernel-server-lts`. It publishes the standard Intel desktop and server images, plus the standard-kernel NVIDIA 580 and NVIDIA open variants. It never builds the Apex kernel or Apex final images. Run it manually from Actions → **Build Lyd Ark Standard Payload** → **Run workflow**; it supports the same GitHub-hosted and self-hosted runner choices.

For quick iteration, `.github/workflows/build-final-variant.yml` provides a separate **Build Individual Lyd Ark Final Image** workflow. Run it from the Actions tab using **Run workflow**, choose one of the seven final variants, and choose the runner. It pulls the already-published matching kernel tag, builds and lints only the selected final image, then publishes that variant tag. It does not rebuild the base or kernel layers, so those prerequisite tags must already exist and be up to date. The default selection is `ark-nvidia-580`.

## Build arguments

- `VARIANT`: selects the desktop/server profile and the kernel or driver configuration.
- `BASE_IMAGE`: source userspace image for the kernel stage.
- `KERNEL_IMAGE`: source kernel image for the final driver stage.
- `AUR_SHA`, `CARRIER_SHA`, and `CARRIER_URL`: pin the external Ark payload inputs used by the build.

## System design

Ark uses Btrfs + Snapper + snap-pac. ZFS/SPL packages are excluded. The installer creates the Btrfs subvolume layout and initializes Snapper's `root` configuration on the target filesystem.

The desktop profile installs Arch's `plasma-meta` package to keep the complete supported KDE Plasma desktop component set in place, plus Plasma workspace wallpapers and the Plymouth settings module. It includes Discover/Flatpak, Steam, Dolphin, Ark, Okular, Kate, Konsole, Spectacle, and Partition Manager, alongside Waterfox from Flathub, TuneD/tuned-ppd, Podman, Solaar, and the Ark feature manager. Solaar is installed as a system package, with its tray service opt-in per user. Sunshine is available as an optional system-wide Flathub feature and runs as a per-user graphical-session service. This is the full Plasma desktop stack rather than the separate `kde-applications` collection of hundreds of optional KDE apps. NVIDIA images enable DRM kernel modesetting for compositor features such as adaptive sync where the GPU and driver support them. The server profile is headless, uses the LTS kernel, enables Cockpit and SSH, and permits SSH password authentication while disabling root SSH login.

## Optional development and desktop virtualization

The desktop base includes the QEMU/KVM and libvirt package stack, but the
libvirt host service is not enabled automatically. This keeps virtualization
available without starting its daemon on every desktop boot.

### Development environment

Run `ark development enable` to create a user-owned Arch Linux Distrobox
named `ark-development`. It contains base-devel, Git/Git LFS, GitHub CLI,
Node.js/npm, Python/pip, Rust, C/C++ tooling, CMake, Ninja, and pkgconf.
The feature also installs Claude Code and OpenAI Codex CLI using their
vendor-provided user-level installers.

The Distrobox container provides a mutable development toolchain without
adding the compilers and SDKs to the immutable host image. Projects and
credentials remain in the user's home directory. Commands:

```bash
ark development enable
ark development status
ark development update
ark development disable
```

Disabling removes the `ark-development` container but deliberately retains
user projects, agent credentials/configuration, and the user-installed
Claude Code/Codex executables.

### Virtualization

Desktop images include QEMU, libvirt, virt-manager, virt-viewer, OVMF UEFI
firmware, swtpm, dnsmasq, and the NAT networking dependencies. The
`libvirtd` service is opt-in on desktop images; the server image retains its
existing Cockpit/libvirt configuration.

```bash
ark virtualization enable
ark virtualization status
ark virtualization list
ark virtualization host
ark virtualization gui
ark virtualization info VM
ark virtualization start VM
ark virtualization shutdown VM
ark virtualization restart VM
ark virtualization snapshot VM SNAPSHOT_NAME
ark virtualization console VM
ark virtualization disable
```

Enabling starts libvirt and configures its default NAT network. VM management
uses the desktop's Polkit authorization rather than granting every desktop
user unrestricted libvirt group access. Disabling is refused while any VM is
running; VM definitions, disks, and network configuration are retained.
KVM acceleration requires CPU virtualization support enabled in firmware and
available to the host as `/dev/kvm`.

The current VM manager is a local CLI/virt-manager foundation. A restricted
local API and MCP transport for future ChatGPT integration are a separate
follow-up; no network-facing VM management endpoint is enabled by this change.

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
- `ark-development` and `ark-virtualization` — optional development and local VM feature managers
- `ark-solaar.service` and `ark-sunshine.service` — opt-in per-user graphical-session services

## Deployment

The installer consumes the final tags above. Intermediate `base-*` and `kernel-*` tags are build inputs only.
