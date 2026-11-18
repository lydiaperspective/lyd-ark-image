# ark-image

OCI container image build logic for an immutable Arch Linux system.

This repository defines the base `Containerfile` used to provision the OSTree deployment. It builds upon `archlinux:latest` and integrates `bootc` to enable atomic system updates. It is strictly vanilla Arch Linux, packaged as an immutable container.

## Included Software

| Package | Source |
|---------|--------|
| GNOME Shell + core apps | Arch official repos |
| systemd-boot (via bootc) | Arch official repos |
| Btrfs + Snapper + snap-pac | Arch official repos |
| Podman + Distrobox | Arch official repos |
| Nix package manager | Pre-built via ark-aur |
| Plymouth (boot splash) | Pre-built via ark-aur |
| MoreWaita icon theme | Pre-built via ark-aur |
| starship, fastfetch | Pre-built via ark-aur |
| bootc, bootupd, ostree | Pre-built via ark-aur |

## Build arguments

- `VARIANT`: Specifies kernel and driver combinations (e.g., `ark-zen-nvidia`).

The current GitHub Actions workflow intentionally builds and publishes only `ark-nvidia-580`: the regular Arch `linux` kernel with the proprietary NVIDIA 580xx DKMS driver and matching userspace packages sourced from CachyOS. CachyOS is removed from the installed image's enabled repository configuration after the driver is installed. Other kernel/driver combinations remain represented in the Containerfile but are not built or published by CI while this initial variant is being tested.

The system filesystem and snapshot stack is Btrfs + Snapper, with `snap-pac` for Pacman transaction snapshots. ZFS/SPL packages are explicitly excluded from the shared ark-aur package release and the build verifies that none are installed. The installer must create the Btrfs subvolume layout and initialize Snapper's `root` configuration on the target filesystem; the image build cannot create Btrfs subvolumes inside its ordinary container build root. The system currently uses systemd-boot, so `grub-btrfs` is not included.

## Local Build

```bash
podman build -t localhost/ark-image:test -f .github/Containerfile --build-arg VARIANT="ark-nvidia-580" .github/
```

## Repository Structure

All build files live inside `.github/`:

- `Containerfile` — image definition
- `bls-sync.sh` — BLS boot entry sync script (runs on every boot and after upgrades)
- `ark-bls-sync.service` — systemd service for boot-time BLS sync
- `bls-sync.conf` — drop-in for ostree/bootc finalize-staged services
- `ark-home.conf` — tmpfiles.d entry ensuring `/var/home` exists on every boot
- `alga-wrapper.sh` — wrapper that prefers updated alga binary from `/var/lib/alga/bin`
- `pacman.sh` — catches accidental `pacman` calls on immutable host

## BLS Boot Entry Behavior

After `bootc upgrade`, two boot entries appear in systemd-boot:
- Current deployment: `Arch Linux YYYYMMDDHHMMSS` (new)
- Rollback deployment: `Arch Linux YYYYMMDDHHMMSS` (previous)

On each subsequent upgrade, the oldest deployment is pruned by OSTree, leaving always exactly 2 entries.

## System Deployment

Deployment requires a bootable environment containing `bootc`. See the [ark.linux](https://github.com/zamkara/ark.linux) Live ISO or the [alga](https://github.com/zamkara/alga) installer frontend.

## License

MIT
