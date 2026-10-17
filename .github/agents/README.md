# Ark agent environment

The installed OS provides `/agents` as persistent Btrfs storage. Alga creates
`@agents` for fresh installs. The image's `ark-agents-storage.service` can also
create and mount it on an existing Btrfs installation. Initialization refuses a
nonempty unmounted `/agents` and respects an existing fstab entry.

Each account owns `Work`, `config`, `data`, and `cache` below
`/agents/users/<uid>`. The parent directory is managed by root, with an ACL granting traversal only
to that account. This keeps migrated projects private even when their original
directory permissions are preserved. `~/Work` is a
bind mount of Work. A per-user graphroot under `/orundum/users/<uid>/containers`
keeps agent containers separate from the legacy shared container directory.
New accounts also receive a private container-storage symlink for Carrier and
Distrobox. Existing host storage, including legacy shared symlinks and custom
configuration, is retained for an explicit administrator migration. Host
Podman configuration files are not rewritten.

A GNOME autostart entry performs repeatable setup after the account exists.
The polkit action permits an active local user to invoke the fixed helper for
their own UID; arbitrary commands, other accounts, and storage initialization
are not accepted through that action. Root initializes storage at boot.

## Commands

```sh
ark-agent setup
ark-agent install <npm-package>
ark-agent default <executable>
ark-agent
ark-agent shell
ark-agent run python -m unittest
ark-agent ports
ark-agent status
ark-agent stop
ark-agent snapshot
ark-agent snapshots
ark-agent restore <snapshot-name>
ark-agent rebuild
```

A tool can also be installed interactively with its supported installer in
`ark-agent shell`. No vendor is selected by default. Agent-specific flags can
be passed with `ark-agent run <executable> <arguments>`.

The default launcher runs in a rootless Podman environment with Git, C/C++,
Python/uv, Node/npm, Rust, Go, CMake, and Chromium. Dependency installation with
sudo applies inside that environment. Project paths are mapped relative to
Work. Downloads, tool configuration, home state, and cache persist separately
from the mutable container root. Only `config/tools` is mounted as the tool
configuration directory; launcher state and Podman storage configuration stay
outside the container. The actual environment image ID is recorded.
`rebuild` pulls first, retains a committed copy of the previous toolchain, and
recreates the environment. Project dependency manifests remain the preferred
way to reproduce system dependencies. Retained images require deliberate
pruning after confirming they are no longer needed.

Preview services listening on container ports 3000, 5173, 8000, and 8080 have
randomly allocated host ports bound to localhost. Use `ark-agent ports` to see
the mappings, and bind the development server to `0.0.0.0` inside the container.
The host home, engine sockets, SSH agent, and desktop session bus are not mounted.
`ark-agent --host` explicitly runs the chosen executable on the host with host
configuration and the user's host permissions.

For headless browser checks inside the environment, Chromium was verified with
`chromium --headless --no-sandbox --disable-dev-shm-usage --dump-dom about:blank`.

## Existing Work

Setup never mounts over a populated Work. Close editors, shells whose current
directory is in Work, and other writers, then run:

```sh
ark-agent migrate-work
```

Migration journals the original directory, renames it to a retained sibling,
copies with rsync preserving metadata, verifies content and metadata, then
activates the bind mount. A failed copy can be resumed with the same command.
The original is not automatically deleted. Existing symlinks or mounts need
an explicit administrator migration rather than automatic replacement.

## Recovery

Work is its own subvolume, so snapshots omit tool state and cache. Snapshotting
refuses nested subvolumes rather than producing a misleading incomplete copy.
Stop the agent environment and other writers before taking a snapshot. Restore
stops the agent environment and snapshots the current Work first, then copies
the selected read-only snapshot as the user. Close other writers before restore.
An interrupted copy can be resumed by restoring the same snapshot again.

OS rollback does not restore workspace data or tool state. Unknown state schema
versions are refused. Snapshot retention and quota must follow the machine's
Btrfs policy; this feature does not enable or change filesystem-wide quota modes.
Snapshots on the same filesystem do not replace an external backup.

## Validation and rollout

`python3 -m unittest discover -s .github/agents/tests -v` checks user state,
migration recovery, skill conflicts, path checks, and mount failure behavior.
`tests/integration.sh` runs the privileged Btrfs/multi-user checks in a disposable
VM or CI runner. Do not run that script on an installed desktop: it provisions
fixture mounts and users on the test machine.

Publish the development environment before payloads that reference it. Release
Alga support only alongside a compatible payload. Update the live ISO's Alga
package after those artifacts are available. Verify an actual Ark ISO install,
first login, second account, reboot, OS update/rollback, and Work recovery before
marking the feature production ready.

## Carrier integration

Carrier remains the host package-manager gateway into Distrobox. It is not
installed inside the agent toolchain, where pacman and other native package
commands operate directly on that environment. Agent execution does not export
applications into the host automatically. Existing Carrier containers are not
removed, renamed, or migrated by agent setup.
