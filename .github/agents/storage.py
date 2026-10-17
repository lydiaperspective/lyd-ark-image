#!/usr/bin/python3
"""Privileged, fixed-purpose provisioning for Ark agent storage."""
import argparse
import ctypes
import datetime
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile


class Storage:
    def __init__(self, root=Path('/agents'), runtime=Path('/run/ark-agents')):
        self.root = root
        self.runtime = runtime

    @staticmethod
    def run(*args, **kwargs):
        return subprocess.run(args, check=True, text=True, **kwargs)

    @staticmethod
    def directory(path, mode=0o755, owner=0):
        try:
            path.mkdir(mode=mode)
            os.chown(path, owner, -1, follow_symlinks=False)
        except FileExistsError:
            pass
        st = path.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != owner:
            raise RuntimeError(f'Unexpected directory or owner: {path}')
        if owner == 0 and st.st_mode & 0o022:
            raise RuntimeError(f'Writable system directory: {path}')

    def mounted(self):
        result = subprocess.run(['findmnt', '-rn', '-M', str(self.root), '-o', 'FSTYPE'],
                                capture_output=True, text=True)
        return result.returncode == 0 and result.stdout.strip() == 'btrfs'

    def initialize(self):
        if self.mounted():
            self.directory(self.root)
            return
        # A missing dedicated mount must never silently become ordinary storage.
        if any(self.root.iterdir()):
            raise RuntimeError('/agents is not mounted and is not empty; refusing to hide data')
        uuid = self.run('findmnt', '-rn', '-T', '/var', '-o', 'UUID',
                        stdout=subprocess.PIPE).stdout.strip()
        fs = self.run('findmnt', '-rn', '-T', '/var', '-o', 'FSTYPE',
                      stdout=subprocess.PIPE).stdout.strip()
        if fs != 'btrfs' or not uuid:
            raise RuntimeError('/agents requires a Btrfs filesystem; storage was not changed')
        fstab = Path('/etc/fstab')
        previous = fstab.read_text() if fstab.exists() else ''
        entries = [line.split() for line in previous.splitlines()
                   if line.strip() and not line.lstrip().startswith('#')]
        if any(len(row) > 1 and row[1] == str(self.root) for row in entries):
            # An existing administrator/installer mount must succeed as configured.
            self.run('mount', str(self.root))
            if not self.mounted():
                raise RuntimeError('/agents did not mount as Btrfs')
            return
        top = Path(tempfile.mkdtemp(prefix='btrfs-', dir=self.runtime))
        try:
            self.run('mount', '-t', 'btrfs', '-o', 'subvolid=5', f'UUID={uuid}', str(top))
            subvolume = top / '@agents'
            if not subvolume.exists():
                self.run('btrfs', 'subvolume', 'create', str(subvolume))
            else:
                self.run('btrfs', 'subvolume', 'show', str(subvolume), stdout=subprocess.DEVNULL)
            options = 'subvol=@agents,compress=zstd,noatime,nodev,nosuid,nofail'
            self.run('mount', '-t', 'btrfs', '-o', options.replace(',nofail', ''),
                     f'UUID={uuid}', str(self.root))
            # Publish fstab only after a successful mount; retry can reuse @agents.
            fd, temporary = tempfile.mkstemp(prefix='.ark-agents-', dir=fstab.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    output.write(previous.rstrip() + '\n'
                                 + f'UUID={uuid} /agents btrfs {options} 0 0\n')
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(temporary, stat.S_IMODE(fstab.stat().st_mode) if fstab.exists() else 0o644)
                os.replace(temporary, fstab)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        finally:
            subprocess.run(['umount', str(top)], check=False, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            top.rmdir()
        if not self.mounted():
            raise RuntimeError('/agents is not mounted')

    def user_namespace(self, account):
        ranges = []
        missing = []
        for filename, option in (('/etc/subuid', '--add-subuids'),
                                 ('/etc/subgid', '--add-subgids')):
            rows = []
            if Path(filename).exists():
                for line in Path(filename).read_text().splitlines():
                    fields = line.split(':')
                    if len(fields) == 3:
                        rows.append((fields[0], int(fields[1]), int(fields[2])))
            ranges.extend((start, start + count - 1) for _, start, count in rows)
            if not any(owner in (account.pw_name, str(account.pw_uid)) and count >= 65536
                       for owner, _, count in rows):
                missing.append(option)
        start = max([99999, *(end for _, end in ranges)]) + 1
        if start + 65535 > 4294967294:
            raise RuntimeError('No subordinate ID range available')
        for option in missing:
            self.run('usermod', option, f'{start}-{start + 65535}', account.pw_name)

    def private_parent(self, path, account):
        # Preserve project modes/ACLs during migration without exposing them via
        # /agents. Only this UID can traverse its root-managed parent directory.
        self.directory(path, 0o700)
        self.run('setfacl', '--set',
                 f'user::rwx,user:{account.pw_uid}:r-x,group::---,mask::r-x,other::---',
                 str(path))

    def provision(self, account):
        if not self.mounted():
            raise RuntimeError('/agents is not mounted; run systemctl start ark-agents-storage')
        self.directory(self.root)
        self.directory(self.root / 'users', 0o711)
        self.directory(self.root / 'shared')
        self.directory(self.root / 'shared/models')
        self.directory(self.root / 'shared/datasets')
        base = self.root / 'users' / str(account.pw_uid)
        self.private_parent(base, account)
        # Parent is root-owned: a user cannot replace these entries with symlinks.
        owner_file = base / '.owner.json'
        if owner_file.exists():
            owner = json.loads(owner_file.read_text())
            if owner.get('schema') != 1 or owner.get('uid') != account.pw_uid:
                raise RuntimeError('Unsupported storage owner schema or UID; data was not changed')
            if owner['username'] != account.pw_name:
                raise RuntimeError('Stored owner differs; explicit account migration is required')
        else:
            with owner_file.open('x') as owner_output:
                owner_output.write(json.dumps({'schema': 1, 'uid': account.pw_uid,
                                               'username': account.pw_name}) + '\n')
                owner_output.flush()
                os.fsync(owner_output.fileno())
            directory_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            owner_file.chmod(0o644)
        for name in ('Work', 'config', 'data', 'cache'):
            path = base / name
            if not path.exists() and not path.is_symlink():
                # Workspace snapshots exclude tool state and disposable cache.
                if name == 'Work':
                    self.run('btrfs', 'subvolume', 'create', str(path))
                else:
                    path.mkdir(mode=0o700)
                os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
                path.chmod(0o700)
            self.directory(path, 0o700, account.pw_uid)
        orundum = Path('/orundum')
        mounted = self.run('findmnt', '-rn', '-M', str(orundum), '-o', 'FSTYPE',
                           stdout=subprocess.PIPE).stdout.strip()
        if mounted != 'btrfs':
            raise RuntimeError('/orundum container storage is not mounted as Btrfs')
        self.directory(orundum)
        self.directory(orundum / 'users', 0o711)
        self.private_parent(orundum / 'users' / str(account.pw_uid), account)
        containers = orundum / 'users' / str(account.pw_uid) / 'containers'
        if not containers.exists() and not containers.is_symlink():
            containers.mkdir(mode=0o700)
            os.chown(containers, account.pw_uid, account.pw_gid, follow_symlinks=False)
        self.directory(containers, 0o700, account.pw_uid)
        return base

    @staticmethod
    def bind_descriptors(source_fd, target_fd):
        # Direct mount(2) keeps our descriptors pinned. External mount helpers
        # can close them or switch to move_mount, invalidating /proc/self/fd paths.
        libc = ctypes.CDLL(None, use_errno=True)
        mount = libc.mount
        mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                          ctypes.c_ulong, ctypes.c_void_p]
        mount.restype = ctypes.c_int
        source = os.fsencode(f'/proc/self/fd/{source_fd}')
        target = os.fsencode(f'/proc/self/fd/{target_fd}')
        if mount(source, target, None, 4096, None) != 0:  # MS_BIND
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), 'bind Work')

    def bind_work(self, account, source):
        home = Path(account.pw_dir).resolve(strict=True)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        home_fd = os.open(home, flags)
        try:
            if os.fstat(home_fd).st_uid != account.pw_uid:
                raise RuntimeError('Home directory has an unexpected owner')
            try:
                os.mkdir('Work', mode=0o700, dir_fd=home_fd)
                os.chown('Work', account.pw_uid, account.pw_gid, dir_fd=home_fd,
                         follow_symlinks=False)
            except FileExistsError:
                pass
            target_fd = os.open('Work', flags, dir_fd=home_fd)
            source_fd = os.open(source, flags)
            try:
                src = os.fstat(source_fd)
                dst = os.fstat(target_fd)
                if src.st_uid != account.pw_uid or dst.st_uid != account.pw_uid:
                    raise RuntimeError('Workspace has an unexpected owner')
                if (src.st_dev, src.st_ino) == (dst.st_dev, dst.st_ino):
                    return
                if os.listdir(target_fd):
                    raise RuntimeError('~/Work contains data; use ark-agent migrate-work first')
                target = home / 'Work'
                if subprocess.run(['mountpoint', '-q', str(target)]).returncode == 0:
                    raise RuntimeError('~/Work is mounted from a different source')
                # Resolve both endpoints through pinned descriptors, not mutable home paths.
                self.bind_descriptors(source_fd, target_fd)
            finally:
                os.close(source_fd)
                os.close(target_fd)
        finally:
            os.close(home_fd)

    def snapshot(self, account, base):
        nested = self.run('btrfs', 'subvolume', 'list', '-o', str(base / 'Work'),
                          stdout=subprocess.PIPE).stdout.strip()
        if nested:
            raise RuntimeError('Workspace has nested subvolumes; snapshot them separately')
        self.directory(self.root / 'snapshots', 0o711)
        snapshots = self.root / 'snapshots' / str(account.pw_uid)
        self.private_parent(snapshots, account)
        name = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        self.run('btrfs', 'subvolume', 'snapshot', '-r', str(base / 'Work'),
                 str(snapshots / name))
        print(snapshots / name)
        return snapshots / name

    def restore(self, account, base, name):
        if not re.fullmatch(r'[0-9]{8}T[0-9]{6}\.[0-9]{6}Z', name):
            raise RuntimeError('Invalid snapshot name')
        source = self.root / 'snapshots' / str(account.pw_uid) / name
        if source.is_symlink() or not source.is_dir():
            raise RuntimeError('Snapshot does not exist')
        readonly = self.run('btrfs', 'property', 'get', '-ts', str(source), 'ro',
                            stdout=subprocess.PIPE).stdout.strip()
        if readonly != 'ro=true':
            raise RuntimeError('Restore source is not a read-only snapshot')
        # Retain the current Work before copying. Copy as its user, never as root.
        # Interrupted copies can be resumed by restoring the same snapshot again.
        self.snapshot(account, base)
        self.run('runuser', '-u', account.pw_name, '--', 'rsync', '-aHAX', '--delete',
                 '--', str(source) + '/', str(base / 'Work') + '/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init-storage', 'setup', 'snapshot', 'restore', 'snapshots'])
    parser.add_argument('--uid', type=int)
    parser.add_argument('--snapshot')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('This helper must run through pkexec or systemd')
    storage = Storage()
    storage.directory(storage.runtime, 0o755)
    with (storage.runtime / 'storage.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'init-storage':
            if os.environ.get('PKEXEC_UID', '0') != '0':
                parser.error('Storage initialization is a system operation')
            storage.initialize()
            return
        caller = int(os.environ.get('PKEXEC_UID', os.environ.get('SUDO_UID', '0')))
        uid = args.uid if args.uid is not None else caller
        if uid < 1000 or uid == 65534 or caller not in (0, uid):
            parser.error('Use a regular local user account; cross-user requests are refused')
        account = pwd.getpwuid(uid)
        if account.pw_shell.endswith(('/nologin', '/false')):
            parser.error('This account does not have a login shell')
        base = storage.provision(account)
        if args.action == 'setup':
            storage.user_namespace(account)
            storage.bind_work(account, base / 'Work')
        elif args.action == 'snapshot':
            storage.snapshot(account, base)
        elif args.action == 'restore':
            storage.restore(account, base, args.snapshot or '')
        else:
            directory = storage.root / 'snapshots' / str(uid)
            if directory.exists():
                for snapshot in sorted(directory.iterdir()):
                    print(snapshot.name)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        raise SystemExit(f'Ark agents: {error}')
