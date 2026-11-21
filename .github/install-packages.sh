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
    # The ark-aur release is shared by desktop and server images. Keep
    # desktop-only GNOME utilities out of the server profile entirely.
    if [[ "${VARIANT:-}" == "intel3-server-lts" ]]; then
        case "$name" in
            nuttyimgconverter|nautilus-python|nautilus|gnome-system-monitor|gnome-disk-utility|gnome-disk-utility-git)
                echo "Skipping desktop-only package in server image: $name"
                continue
                ;;
        esac
    fi
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

/usr/bin/pacman -Q inetutils
command -v hostname >/dev/null

# Stop at installation time rather than producing an incomplete bootable image.
/usr/bin/pacman -Q plymouth bootc bootupd libselinux alga
/usr/bin/pacman -Q btrfs-progs snapper snap-pac
if /usr/bin/pacman -Qq | grep -Eq '^(zfs|zfs-|spl|spl-)'; then
    echo "Unexpected ZFS/SPL package installed in a Btrfs-only image" >&2
    exit 1
fi
test -f /usr/lib/initcpio/install/plymouth
test -f /usr/lib/initcpio/hooks/plymouth

# Desktop images must retain the bootc-aware Discover integration after the
# kernel and driver layers are composed. Server images intentionally omit it.
if [[ "${VARIANT:-}" == "intel3-server-lts" ]]; then
    if [[ -e /usr/lib/packagekit-backend/libpk_backend_bootc.so ]]; then
        echo "Server image unexpectedly contains the desktop PackageKit bootc backend." >&2
        exit 1
    fi
    if /usr/bin/pacman -Qq | grep -qx plasma-login-manager; then
        echo "Server image unexpectedly contains a graphical login manager." >&2
        exit 1
    fi
else
    # AUR packages are installed after the base userspace layer and can pull
    # GNOME utilities back in as dependencies. Remove them from the composed
    # desktop image, then fail the build if any remain.
    unwanted_packages=(nuttyimgconverter nautilus-python nautilus gnome-system-monitor gnome-disk-utility gnome-disk-utility-git)
    installed_packages="$(/usr/bin/pacman -Qq)"
    packages_to_remove=()
    for pkg in "${unwanted_packages[@]}"; do
        if grep -Fxq -- "$pkg" <<< "$installed_packages"; then
            packages_to_remove+=("$pkg")
        fi
    done
    # Remove the complete installed set in one transaction. Separate pacman
    # removals can orphan/remove later targets, making a subsequent removal fail.
    if ((${#packages_to_remove[@]})); then
        /usr/bin/pacman -Rns --noconfirm "${packages_to_remove[@]}"
    fi
    for pkg in "${unwanted_packages[@]}"; do
        if /usr/bin/pacman -Q "$pkg" >/dev/null 2>&1; then
            echo "ERROR: unwanted GNOME application remains installed: $pkg" >&2
            exit 1
        fi
    done

    /usr/bin/pacman -Q discover packagekit packagekit-qt6 plasma-meta plasma-desktop plasma-workspace kwin kscreen plasma-login-manager \
        bluedevil kde-cli-tools kde-gtk-config kdeplasma-addons kglobalacceld kinfocenter kmenuedit kpipewire \
        kscreenlocker ksystemstats kwallet-pam plasma-browser-integration plasma-disks plasma-firewall \
        plasma-integration plasma-keyboard plasma-nm plasma-pa plasma-systemmonitor plasma-thunderbolt \
        plasma-vault plasma-welcome polkit-kde-agent powerdevil print-manager spectacle systemsettings \
        xdg-desktop-portal-kde breeze-cursors plasma-workspace-wallpapers plymouth-kcm solaar
    /usr/bin/pacman -Q qemu-full libvirt virt-manager virt-viewer spice-gtk dnsmasq iptables-nft edk2-ovmf swtpm
    test -x /usr/bin/ark
    test -x /usr/bin/lydsys
    /usr/bin/pacman -Q libarchive
    ! /usr/bin/pacman -Qq | grep -qx ark
    test "$(readlink -f /usr/bin/lydsys)" = /usr/bin/ark
    test -x /usr/libexec/ark/ark-development
    test -x /usr/libexec/ark/ark-virtualization
    ! /usr/bin/pacman -Qq | grep -qx sddm
    test -s /usr/lib/systemd/system/plasmalogin.service
    test -s /usr/lib/systemd/system/virt-secret-init-encryption.service
    grep -Fq 'ExecStartPre=/usr/bin/install -d -m 0700 -o root -g root /var/lib/libvirt/secrets' /usr/lib/systemd/system/virt-secret-init-encryption.service.d/10-ark-secret-directory.conf
    test -s /usr/lib/systemd/user/ark-solaar.service
    test -s /usr/lib/systemd/user/ark-sunshine.service
    test -s /usr/lib/packagekit-backend/libpk_backend_bootc.so
    test -x /usr/share/PackageKit/helpers/bootc/bootcBackend.py
    grep -Eq '^DefaultBackend=bootc$' /etc/PackageKit/PackageKit.conf
    grep -q '^%wheel ALL=(ALL:ALL) ALL$' /etc/sudoers.d/10-wheel
    grep -q 'pam_mkhomedir.so' /etc/pam.d/system-login
fi
