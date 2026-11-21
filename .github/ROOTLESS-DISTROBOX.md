# Rootless Distrobox storage permissions

## Why this is needed

The desktop development environment uses rootless Podman with its graphroot
under `/orundum`. The configured graphroot may appear under the home directory
and reach `/orundum` through a symlink (for example,
`~/.local/share/containers/storage`). The helper resolves the graphroot with
`realpath -e` before applying permissions. Distrobox starts containers through
`crun`, which must traverse the host-side overlay path, including
`containers/storage/overlay/<layer>/merged`.

The first subordinate UID in the user's `/etc/subuid` mapping needs
**execute-only** access to the existing path parents. The graphroot also needs
a default ACL so directories Podman creates later inherit that traversal
permission. Without the default ACL, granting access only to the current
parents can still leave newly-created overlay directories inaccessible.

## Automatic setup

`ark development enable` runs this setup before creating or entering the
Distrobox:

1. Ensure the user has subordinate UID and GID ranges.
2. Read the rootless Podman graphroot.
3. Resolve the configured graphroot through symlinks, then grant the first
   subordinate UID execute-only access along the real `/orundum` path.
4. Apply execute-only access and default ACLs to existing overlay directories,
   and add a default ACL to the graphroot for future storage directories.
5. Verify the graphroot default ACL before proceeding.

The server image does not expose the desktop development environment, so this
setup is desktop-only.

## Diagnostics

Run as the normal desktop user:

    podman info --format '{{.Store.GraphRoot}}'
    realpath -e "$(podman info --format '{{.Store.GraphRoot}}')"
    grep "^$(id -un):" /etc/subuid
    getfacl -cp "$(realpath -e "$(podman info --format '{{.Store.GraphRoot}}')")"

The graphroot ACL should contain a line similar to
`default:user:100000:--x`, where `100000` is the first subordinate UID
reported by `/etc/subuid`.

## Security scope

The subordinate UID receives execute-only access, not directory listing or
file read access. This is a host-path traversal permission for rootless
container storage; it does not grant the user's regular UID additional access.

## Validation

After the setup, run:

    ark development enable
    ark development status
    ark development shell

A successful enable must create the `ark-development` container, enter it to
install the toolchain, and return without a `crun` overlay-path permission
error.
