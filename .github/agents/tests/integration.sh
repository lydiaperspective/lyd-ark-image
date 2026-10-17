#!/bin/bash
# Run only in a disposable VM/CI machine. Never on the installed desktop.
set -euo pipefail
[[ ${ARK_AGENTS_DISPOSABLE_TEST:-} == 1 && $EUID == 0 ]] || {
  echo 'A disposable root test machine is required' >&2; exit 1;
}
for path in /agents /orundum; do
  [[ ! -e $path ]] || { echo "Fixture path already exists: $path" >&2; exit 1; }
done
# Fixture administration is root, not a request on behalf of the sudo caller.
unset SUDO_UID SUDO_GID SUDO_USER PKEXEC_UID
SOURCE_DIR=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p /agents /orundum /run/ark-agents /usr/libexec/ark /fixture-root
install -m755 "$SOURCE_DIR/storage.py" /usr/libexec/ark/agents-storage
truncate -s 768M /root/agents-test.btrfs
mkfs.btrfs -f /root/agents-test.btrfs
mount -o loop /root/agents-test.btrfs /fixture-root
btrfs subvolume create /fixture-root/@orundum
mount -o subvol=@orundum /dev/$(findmnt -rn -M /fixture-root -o SOURCE | xargs basename) /orundum
# Exercise existing-install initialization using the fixture Btrfs as /var's backing filesystem.
python3 - "$SOURCE_DIR/storage.py" <<'PY'
import importlib.util
import sys
spec = importlib.util.spec_from_file_location('storage', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class Fixture(m.Storage):
    @staticmethod
    def run(*args, **kwargs):
        if args[:4] == ('findmnt', '-rn', '-T', '/var'):
            args = (*args[:3], '/fixture-root', *args[4:])
        return m.Storage.run(*args, **kwargs)
Fixture().initialize()
PY
useradd -m -U -u 2000 -s /bin/bash ark-agent-a
useradd -m -U -u 2001 -s /bin/bash ark-agent-b
/usr/libexec/ark/agents-storage setup --uid 2000
/usr/libexec/ark/agents-storage setup --uid 2001
/usr/libexec/ark/agents-storage setup --uid 2000
runuser -u ark-agent-a -- bash -c 'echo first > ~/Work/project.txt'
test "$(cat /agents/users/2000/Work/project.txt)" = first
chmod 755 /agents/users/2000/Work
if runuser -u ark-agent-b -- cat /agents/users/2000/Work/project.txt; then exit 1; fi
if PKEXEC_UID=2000 /usr/libexec/ark/agents-storage setup --uid 2001; then exit 1; fi
if PKEXEC_UID=2000 /usr/libexec/ark/agents-storage init-storage; then exit 1; fi
SNAPSHOT=$(/usr/libexec/ark/agents-storage snapshot --uid 2000 | tail -n 1)
runuser -u ark-agent-a -- bash -c 'echo changed > ~/Work/project.txt; echo extra > ~/Work/extra.txt'
/usr/libexec/ark/agents-storage restore --uid 2000 --snapshot "${SNAPSHOT##*/}"
test "$(cat /agents/users/2000/Work/project.txt)" = first
test ! -e /agents/users/2000/Work/extra.txt
# Removing/recreating the mount must preserve the source and keep users separate.
umount /home/ark-agent-a/Work /home/ark-agent-b/Work
umount /agents
mount /agents
/usr/libexec/ark/agents-storage setup --uid 2000
test "$(cat /home/ark-agent-a/Work/project.txt)" = first
# Never hide existing Work or follow a target symlink.
runuser -u ark-agent-b -- bash -c 'echo keep > ~/Work/existing'
if /usr/libexec/ark/agents-storage setup --uid 2001; then exit 1; fi
test "$(cat /home/ark-agent-b/Work/existing)" = keep
mv /home/ark-agent-b/Work /home/ark-agent-b/Work.old
ln -s /tmp /home/ark-agent-b/Work
if /usr/libexec/ark/agents-storage setup --uid 2001; then exit 1; fi
# A nested subvolume must not be silently omitted from a workspace snapshot.
btrfs subvolume create /agents/users/2000/Work/nested
if /usr/libexec/ark/agents-storage snapshot --uid 2000; then exit 1; fi
echo ARK_AGENTS_INTEGRATION_PASS
