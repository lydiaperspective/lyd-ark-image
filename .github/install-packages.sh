#!/usr/bin/env bash
set -euo pipefail

# Keep packages available in sync repositories aligned with the running system.
# Only AUR/local packages need the archives published by ark-aur and sibling repos.
shopt -s nullglob
archives=(/tmp/aur-packages/*.pkg.tar.zst)
((${#archives[@]})) || { echo 'No package archives found' >&2; exit 1; }
official=()
local_packages=()
for archive in "${archives[@]}"; do
    read -r name version < <(/usr/bin/pacman -Qp "$archive")
    case "$name" in
        *-debug|linux-headers|linux-zen-headers|linux-lts-headers|linux-hardened-headers)
            continue
            ;;
        # ZFS is intentionally not part of Ark Linux. The system uses Btrfs;
        # do not install ZFS/SPL packages from the shared ark-aur release.
        zfs|zfs-*|spl|spl-*)
            echo "Skipping unsupported filesystem package: $name"
            continue
            ;;
    esac
    if /usr/bin/pacman -Si "$name" >/dev/null 2>&1; then
        official+=("$name")
    else
        local_packages+=("$archive")
    fi
done

if ((${#official[@]})); then
    /usr/bin/pacman -S --needed --noconfirm "${official[@]}"
fi
if ((${#local_packages[@]})); then
    /usr/bin/pacman -U --noconfirm "${local_packages[@]}"
fi

# Stop at installation time rather than producing an incomplete bootable image.
/usr/bin/pacman -Q plymouth bootc bootupd libselinux alga
/usr/bin/pacman -Q btrfs-progs snapper snap-pac
if /usr/bin/pacman -Qq | grep -Eq '^(zfs|zfs-|spl|spl-)'; then
    echo "Unexpected ZFS/SPL package installed in a Btrfs-only image" >&2
    exit 1
fi
test -f /usr/lib/initcpio/install/plymouth
test -f /usr/lib/initcpio/hooks/plymouth
