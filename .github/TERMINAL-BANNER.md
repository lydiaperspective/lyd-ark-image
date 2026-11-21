# Terminal banner and command names

The desktop and server userspace images install a small interactive terminal
banner using the Lyd Ark Wicca palette. It is shown only in interactive terminal
sessions; non-interactive commands, scripts, and redirected output remain quiet.

## Commands

| Command | Purpose | Help / launch |
| --- | --- | --- |
| ark | Lyd Ark System Manager | ark --help |
| lydsys | Compatibility alias for the same System Manager | lydsys --help |
| lydstore | Lyd Ark Storage Manager | lydstore --help |
| alga | Graphical installer and system updater | Run alga in a graphical desktop session |

The ark command is the canonical name. lydsys resolves to the same
executable for compatibility. The KDE Ark archive-manager package is omitted
from desktop images so its executable cannot conflict with the Lyd Ark command.
The libarchive library remains installed for archive-format support in other
applications.

Alga is a graphical application, not a command-line utility; it does not provide
a CLI --help interface.

## Shell integration

- Bash and other /etc/profile login shells source
  /etc/profile.d/lyd-ark-banner.sh.
- Fish loads /etc/fish/conf.d/lyd-ark-banner.fish.
- The banner renderer lives at /usr/libexec/ark/terminal-banner.

The renderer checks each command with command -v before listing it and honors
the standard NO_COLOR environment variable and TERM=dumb.

## Validation

Run these checks in the image build environment:

    bash -n /usr/libexec/ark/terminal-banner
    bash -n /etc/profile.d/lyd-ark-banner.sh
    ark --help
    lydsys --help
    lydstore --help

For a desktop image, verify the KDE Ark package is absent while libarchive
remains installed. Verify that readlink -f /usr/bin/lydsys resolves to
/usr/bin/ark. On the server image, verify both command names and lydstore
are available; Alga remains listed only when its executable is installed.
