# Image build workflows

## Rebuild Base and Final Images

Use **Actions → Rebuild Base and Final Images → Run workflow** when a change
requires refreshing the shared userspace bases and every published bootable
image, but does not require rebuilding the installer or ISO.

Choose the runner:

- **github-hosted** uses GitHub-hosted Ubuntu runners.
- **self-hosted** uses the configured `ark-builder` runner.

The workflow calls the existing all-image payload pipeline in forced mode and
skips the separate agent development image. Its stages run in dependency order:

1. Build and publish `base-desktop` and `base-server`.
2. Rebuild and publish the three kernel-family images:
   - `kernel-desktop-standard`
   - `kernel-desktop-apex`
   - `kernel-server-lts`
3. Compose, bootc-lint, and publish all seven final variants:
   - `intel-modern`
   - `intel-modern-apex`
   - `intel3-server-lts`
   - `ark-nvidia-580`
   - `ark-apex-nvidia-580`
   - `ark-nvidia-open`
   - `ark-apex-nvidia-open`

### Why the kernel layers are rebuilt

The kernel stage is based on the userspace base image and contains that base
filesystem as part of its resulting image. Publishing a new base does not
change already-published kernel images. The kernel stages therefore have to be
reconstructed against the new base before the final images can use it.

The kernel build uses the existing AUR package release and the configured
Pacman package cache to reduce downloads, but it still runs the kernel-stage
build. GPU driver packages are installed as part of final-image composition;
there are no separate driver image tags in this pipeline.

### What this workflow does not build

- The separate agent development image.
- The Alga installer.
- The live ISO.
- Release orchestration or any other repositories' artifacts.

The workflow shares the `lyd-ark-image-release` concurrency lock with the
regular payload and base-image workflows so they cannot publish overlapping
base or image tags at the same time.

## Build All Lyd Ark Images

Use **Actions → Build All Lyd Ark Images** for the regular complete image
payload pipeline. It retains the agent-environment validation/build stages,
and supports source-change, weekly scheduled, and manual forced runs.
