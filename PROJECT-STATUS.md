# Lyd Ark Project Status

**Last reviewed:** 2026-11-20  
**Primary repository:** [lyd-ark-image](https://github.com/lydiaperspective/lyd-ark-image)

This document is the central, maintained overview of Lyd Ark's architecture, implemented features, work in progress, known issues, and development roadmap.

> **Status terminology**
> - **Implemented** means the change exists in source or image configuration.
> - **User-confirmed** means the user has explicitly reported that the feature works.
> - **CI-verified** means a relevant automated workflow completed successfully.
> - **Runtime verification pending** means the code is committed but has not yet been validated on a built, installed, running system.
> - **Planned** means it is a design or roadmap item, not an implemented feature.

A successful source commit or syntax check does not prove that a complete image builds or that a feature works on physical hardware.

---

## 1. Project overview

Lyd Ark is an Arch Linux-based immutable operating system built with **bootc and OSTree**. It is intended to provide a polished KDE Plasma desktop, hardware-specific gaming and desktop images, and a separate headless server edition.

The project is organized around several repositories:

| Repository | Responsibility |
|---|---|
| [lyd-ark-image](https://github.com/lydiaperspective/lyd-ark-image) | OS image definitions, package integration, feature scripts and image workflows |
| [lyd-agka](https://github.com/lydiaperspective/lyd-agka) | Alga graphical installer and system updater fork |
| [lyd-ark-fork](https://github.com/lydiaperspective/lyd-ark-fork) | Live installer ISO |
| [lyd-ark-themes](https://github.com/lydiaperspective/lyd-ark-themes) | Lyd Ark visual themes and Plymouth assets |

System Manager, update infrastructure beyond the existing bootc/Alga flow, and future ChatGPT integration remain roadmap work unless separately implemented.

## 2. Image architecture and variants

The image pipeline has been refactored into modular layers:

`base → kernel → final image`

The intended final desktop and server variants are:

| Image tag | Edition | Hardware / driver profile |
|---|---|---|
| `intel-modern` | Desktop | Standard Intel |
| `intel-modern-apex` | Desktop | Apex Intel |
| `ark-nvidia-open` | Desktop | Standard kernel, open NVIDIA driver |
| `ark-apex-nvidia-open` | Desktop | Apex kernel, open NVIDIA driver |
| `ark-nvidia-580` | Desktop | Standard kernel, proprietary NVIDIA 580 driver |
| `ark-apex-nvidia-580` | Desktop | Apex kernel, proprietary NVIDIA 580 driver |
| `intel3-server-lts` | Server | Intel Ivy Bridge-oriented LTS profile |

These are the configured image targets. The build and hardware compatibility of every target must be tracked independently; listing a target here does not mean every variant has passed a clean build and boot test.

## 3. Feature status

### 3.1 Core operating system

| Feature | Status | Notes |
|---|---|---|
| Arch-based immutable OS | Implemented | bootc/OSTree image model |
| Modular base/kernel/final image build | Implemented | CI/build validation ongoing |
| GHCR image publishing | Implemented | Final image tags are used by the installer |
| bootc image upgrades | Implemented | Integrated with the Alga update flow |
| Deployment rollback | Implemented in architecture | Needs ongoing end-to-end validation |
| Btrfs filesystem | Implemented | ZFS intentionally excluded |
| Snapper and snap-pac | Implemented in image package set | Installer setup and rollback require testing |
| systemd-boot | Implemented | grub-btrfs omitted |
| TuneD and tuned-ppd | Implemented in desktop/server configuration | Runtime power-profile validation pending |

### 3.2 KDE desktop

| Feature | Status | Notes |
|---|---|---|
| KDE Plasma desktop | Implemented | Replaces the former GNOME desktop |
| Plasma Login Manager | Implemented in image/ISO configuration | SDDM is not intended to be used |
| First-boot administrator account creation | User-confirmed | User reported the account creator works |
| KDE System Settings | Implemented | Full module audit and runtime checks remain |
| KScreen display configuration | Package added | Verify display configuration on installed system |
| Discover | Implemented | bootc-aware PackageKit integration added; runtime verification pending |
| Flatpak support | Implemented | Verify Discover and app installation on target |
| Steam | Implemented | System package in desktop image |
| Waterfox | Implemented as first-boot Flatpak installation | Requires network; runtime verification pending |
| Solaar | Implemented | System package; optional per-user service |
| Sunshine | Implemented as optional feature | System Flatpak install and user service; runtime verification pending |
| No installed-system autologin | Implemented | Live ISO may use a disposable live account |

### 3.3 Installer and updater (Alga)

The Alga fork provides the graphical installer and installed-system update experience.

Implemented capabilities include:

- UEFI installation.
- Btrfs partitioning and subvolume layout.
- bootc image installation.
- First administrator account creation during installation.
- Installed-system home-directory provisioning.
- bootc-based system updates.
- Application self-update and periodic update checks.
- Boot entry synchronization for current and rollback deployments.
- Network connectivity check.
- NVIDIA driver choice, including the proprietary 580 image family.

The Alga package build workflow completed successfully in the latest reviewed status. The full install → first boot → update → rollback path still needs repeatable end-to-end testing.

### 3.4 Server edition

The server image is designed to be headless and use the LTS kernel.

Configured capabilities:

- Cockpit web administration and relevant add-ons.
- SSH server, with root SSH login disabled.
- Podman.
- Btrfs and Snapper.
- TuneD.
- LTS kernel profile.

The server image must remain free of KDE and desktop display-manager dependencies. Server installation, remote administration, storage and container workflows require dedicated testing.

### 3.5 Ark feature manager

The `ark` command provides opt-in feature management.

| Feature | Status | Notes |
|---|---|---|
| Steam | Implemented | Optional feature action |
| Tailscale | Implemented | Optional service action |
| Podman | Implemented | Rootless API socket management |
| GitHub Actions runner | Implemented | Registration and lifecycle actions |
| Solaar | Implemented | Per-user service enable/disable/status |
| Sunshine | Implemented | Optional installation and per-user service |
| Development | Initial implementation committed | Distrobox toolchain and AI coding CLIs; runtime testing pending |
| Virtualization | Initial implementation committed | QEMU/KVM/libvirt management; runtime testing pending |

#### Development environment

The `ark development` feature is designed to create a user-owned Arch Distrobox containing a development toolchain, including:

- Claude Code and OpenAI Codex CLI installers.
- Git, Git LFS and GitHub CLI.
- Node.js/npm and Python/pip.
- Rust/Cargo, Rustfmt and Clippy.
- GCC/Clang, CMake, Ninja and pkgconf.
- Debugging, code-search and shell-quality tools.

Available actions include `enable`, `status`, `shell`, `update` and `disable`.

Distrobox shares the user's home directory and is a development environment, **not a security sandbox**. AI coding agents run with the logged-in user's permissions and may access files available to that user. Credentials should not be baked into OS images.

#### Desktop virtualization

The desktop image is configured to include:

- QEMU/KVM and libvirt.
- virt-manager and virt-viewer.
- SPICE desktop support.
- OVMF UEFI firmware.
- swtpm virtual TPM.
- dnsmasq and NAT networking dependencies.

The libvirt host service is intended to be opt-in. The local `ark virtualization` commands cover service management and common VM operations. The local CLI/virt-manager foundation is **not yet a ChatGPT remote-management integration**.

KVM acceleration depends on CPU virtualization support being enabled in firmware and exposed to the OS (normally `/dev/kvm`). This must be checked on the actual host hardware.

## 4. Themes and user experience roadmap

### Wicca theme

**Initial Plymouth assets implemented** in [lyd-ark-themes](https://github.com/lydiaperspective/lyd-ark-themes).

Design direction:
- Midnight plum and deep-purple palette.
- Antique-gold crescent moon.
- Matching boot splash and branding.
- KDE Plasma integration, icons and wallpapers.

The image builder has theme integration work. Cold-boot appearance and complete desktop theme consistency still need validation.

### Cute theme

**Planned.**

Design direction:
- Pink primary palette.
- Soft pastel and lavender accents.
- Cute, friendly artwork and iconography.
- Matching KDE Plasma styling, wallpapers and application integration.

### Lyd Ark System Manager

**Planned.**

Intended capabilities:
- KDE-native interface that follows the active Plasma theme.
- System image/update status and update controls.
- Ark feature management.
- Hardware and system information.
- Storage, snapshots and recovery information.
- Virtual machine management.

The application itself should be treated as a separate project milestone; the current `ark` CLI is not the finished System Manager.

## 5. Known bugs, fixes and outstanding verification

This section records issues encountered during development. A source-level correction is not considered fully closed until the affected workflow or runtime path has been tested.

| Issue encountered | Change made | Current assessment |
|---|---|---|
| ZFS/SPL DKMS compilation caused image build problems | Removed ZFS/SPL from the shared package set; standardized on Btrfs/Snapper | Source fix implemented; keep build regression coverage |
| NVIDIA 580 packages conflicted with standard NVIDIA packages (including `nvidia-utils` / `nvidia-libgl`) | Remove conflicting standard NVIDIA packages before installing the 580 stack | Fix committed; verify full 580 image build |
| Duplicate CachyOS repository configuration in Apex + NVIDIA build | Corrected repository setup and cleanup | Source fix implemented |
| Installer account creation was unreliable in the live install stage | Moved first account creation to a first-boot system service | User-confirmed working |
| Installer encountered a non-writable `/var` during account setup | Avoided doing installed-system account provisioning from the live environment | Addressed by first-boot design |
| ISO workflow waited for image builds unnecessarily | Changed ISO workflow to use the latest published desktop base image | Implemented; workflow has completed successfully |
| Small ISO images were split unnecessarily | Split only when the artifact exceeds the configured size threshold | Implemented |
| ISO attempted to enable missing `sddm.service` | Replaced SDDM references with Plasma Login Manager | Implemented in source; verify on live ISO |
| Installed image lacked KDE Display Configuration | Added `kscreen` | Package added; runtime verification pending |
| Discover failed to activate `org.freedesktop.PackageKit` | Added bootc-specific PackageKit backend and D-Bus activation handling | Fix implemented; runtime verification pending |
| Waterfox did not persist when installed during image build | Changed to first-boot Flathub installation service | Fix implemented; runtime verification pending |
| Installer image selection/install flow had failures | Updated image mapping and installer/image integration | Needs fresh install regression testing |
| GNOME components remained during KDE migration | Replaced desktop package/configuration and login-manager references | Audit for remaining GNOME dependencies |

### Active verification list

These are not all confirmed current defects. They are the highest-priority paths that still need evidence from clean builds or real installations:

1. Complete clean builds of all seven image targets.
2. Complete a fresh installation using the current Alga fork and current image tags.
3. Verify first-boot account creation and Plasma Login Manager startup.
4. Verify KScreen and all expected KDE System Settings modules.
5. Verify Discover OS updates, Flatpak updates and PackageKit D-Bus activation.
6. Verify Waterfox installation after first boot and network availability.
7. Verify NVIDIA 580 and open-driver image boot/display paths.
8. Verify Btrfs/Snapper snapshot creation and recovery/rollback behavior.
9. Verify Solaar and Sunshine user services.
10. Verify development Distrobox creation, toolchain installation and agent login.
11. Verify libvirt service enable/disable, KVM acceleration, NAT networking, VM creation, snapshots and console access.
12. Verify the server remains headless and Cockpit/SSH/Podman work as intended.

## 6. Build and CI status

The following is a historical snapshot of the latest workflow observations made during the November 20, 2026 project review. Workflow state can change; use the linked Actions pages for current results.

| Workflow | Last observed result | Link |
|---|---|---|
| KDE installer ISO build | Completed successfully | [Actions run](https://github.com/lydiaperspective/lyd-ark-fork/actions/runs/44673472794) |
| Alga package release | Completed successfully | [Actions run](https://github.com/lydiaperspective/lyd-agka/actions/runs/44619260237) |
| NVIDIA 580 Apex full payload | In progress at review time | [Actions run](https://github.com/lydiaperspective/lyd-ark-image/actions/runs/44769854965) |
| Base image rebuild | Cancelled at review time | [Actions run](https://github.com/lydiaperspective/lyd-ark-image/actions/runs/44769484188) |
| Ark feature-script Bash syntax CI | Passed in the reviewed run | [Actions run](https://github.com/lydiaperspective/lyd-ark-image/actions/runs/44769615746) |

A syntax-check workflow validates shell parsing; it does not validate package availability, image build success, service startup or runtime behavior.

## 7. Development roadmap

Recommended order of work:

### Phase 1 — Stabilize image builds

- [ ] Confirm the modular base → kernel → final build pipeline.
- [ ] Build all seven final variants successfully.
- [ ] Resolve any NVIDIA 580 package or DKMS regressions.
- [ ] Confirm package validation for desktop and server images.
- [ ] Audit for leftover GNOME packages and services.

### Phase 2 — Installer and recovery validation

- [ ] Build and boot the current KDE installer ISO.
- [ ] Perform a fresh install for Intel and NVIDIA profiles.
- [ ] Verify Btrfs subvolume layout and Snapper initialization.
- [ ] Verify first-boot account creation and login.
- [ ] Test bootc upgrade and rollback behavior.
- [ ] Test installer handling of failed or unavailable image pulls.

### Phase 3 — Desktop integration

- [ ] Verify KDE modules and display configuration.
- [ ] Verify Discover and PackageKit bootc integration.
- [ ] Verify Flatpak installation and Waterfox first-boot setup.
- [ ] Verify Steam, Solaar and Sunshine.
- [ ] Test power profiles and graphics/display behavior.
- [ ] Test Plymouth and Wicca theme on cold boot.

### Phase 4 — Development and virtualization

- [ ] Test Distrobox development environment on a clean install.
- [ ] Verify Claude Code and Codex installation/authentication.
- [ ] Verify rootless Podman prerequisites and development workflow.
- [ ] Test libvirt/KVM enablement and Polkit authorization.
- [ ] Test VM networking, UEFI, virtual TPM, snapshots and console.
- [ ] Document host hardware requirements and troubleshooting.

### Phase 5 — Lyd Ark applications and themes

- [ ] Complete Wicca KDE theme integration.
- [ ] Develop the Cute theme.
- [ ] Design and implement Lyd Ark System Manager.
- [ ] Integrate Ark feature controls into System Manager.
- [ ] Ensure applications follow the active KDE theme.

### Phase 6 — Remote VM integration and release readiness

- [ ] Design a restricted local VM management API.
- [ ] Define authentication, authorization and confirmation requirements.
- [ ] Add a supported MCP transport only when the target ChatGPT environment supports it.
- [ ] Keep network-facing VM management disabled by default.
- [ ] Test all remote operations and audit logs.
- [ ] Prepare installation, recovery and release documentation.

## 8. Design and security principles

- Keep the base OS immutable; put mutable development dependencies in containers where practical.
- Do not bake user credentials, API keys or agent authentication into image builds.
- Treat Distrobox as a convenience and dependency boundary, not a security sandbox.
- Do not expose libvirt or a future VM API to the network without authentication and authorization.
- Prefer least-privilege operations and explicit confirmation for destructive VM actions.
- Preserve the separation between desktop and headless server images.
- Test image builds, installation, boot, updates and rollback as separate release gates.
- Keep documented feature status aligned with actual CI and runtime evidence.

## 9. Useful project links

- [Image builder](https://github.com/lydiaperspective/lyd-ark-image)
- [Image builder Actions](https://github.com/lydiaperspective/lyd-ark-image/actions)
- [Alga installer fork](https://github.com/lydiaperspective/lyd-agka)
- [Installer Actions](https://github.com/lydiaperspective/lyd-agka/actions)
- [KDE installer ISO repository](https://github.com/lydiaperspective/lyd-ark-fork)
- [Theme repository](https://github.com/lydiaperspective/lyd-ark-themes)

---

**Maintenance note:** Update this document when a feature is added, removed, materially changed, or verified. When closing a bug, record the corrective change and the evidence (CI run, installation test, or hardware test) that confirms the fix.
