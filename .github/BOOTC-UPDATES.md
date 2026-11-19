# Lyd Ark bootc image updates

Lyd Ark publishes build stages independently (userspace base, kernel, and final
driver composition), but installed systems track **one final bootable image**.
The installer passes the selected final image reference to
`bootc install --source-imgref`. Bootc records that image origin for the
deployment.

The installed update service therefore runs `bootc upgrade` against the
recorded origin. It does not independently pull `base-desktop`,
`kernel-desktop-*`, or driver layers. Those are build inputs; the final
variant tag already contains the matching userspace, kernel, and driver.

## Schedule and behaviour

- First automatic check: 15 minutes after boot.
- Subsequent checks: approximately every 6 hours, with up to 30 minutes of
  randomized delay.
- A successful `bootc upgrade` stages the new deployment.
- The new deployment becomes active on reboot; this service does not reboot
  the machine automatically.
- The previous deployment remains available for bootc rollback.
- Alga's own self-update timer remains separate and is not the OS updater.

## Manual commands

Run as root (or through sudo):

- `sudo ark-os-update check` — fetch and stage an update from the installed
  image origin.
- `sudo ark-os-update status` — show the current and staged deployments.
- `systemctl status ark-bootc-update.timer` — inspect the automatic timer.
- `journalctl -u ark-bootc-update.service` — inspect update logs.

## Variant safety

The installer selects one final image reference, for example
`ghcr.io/lydiaperspective/lyd-ark-image:intel-modern-apex` or
`ghcr.io/lydiaperspective/lyd-ark-image:ark-nvidia-580`. Bootc upgrades that
recorded reference; it does not infer a different variant from the hardware
or switch between standard/Apex or NVIDIA/Intel variants.
