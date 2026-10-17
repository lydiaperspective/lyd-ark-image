#!/usr/bin/python3
"""Ark agent workspace and development environment launcher."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

SCHEMA = 1
IMAGE = 'ghcr.io/zamkara/ark-image:agents'
CONTAINER = 'ark-agent-workspace'
HELPER = '/usr/libexec/ark/agents-storage'
SKILLS = Path('/usr/share/agents/skills')
CONTAINER_SKILLS = Path('/usr/share/agents/skills')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def load_json(path, default):
    if not path.exists():
        return default.copy()
    data = json.loads(path.read_text())
    if data.get('schema') != SCHEMA:
        raise RuntimeError(f'Unsupported state schema in {path}; data was not changed')
    return data


def save_json(path, data):
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    # Exclusive creation refuses an unexpected file/symlink at this temporary path.
    try:
        with temporary.open('x') as output:
            json.dump(data, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def skill_links(home, skills=SKILLS):
    for location in ('.agents/skills', '.claude/skills', '.codex/skills', '.gemini/skills'):
        directory = home / location
        directory.mkdir(parents=True, exist_ok=True)
        for skill in skills.glob('*/SKILL.md'):
            target = directory / skill.parent.name
            if target.is_symlink() and target.resolve() == skill.parent.resolve():
                continue
            if target.exists() or target.is_symlink():
                print(f'Keeping existing skill: {target}', file=sys.stderr)
                continue
            target.symlink_to(skill.parent)


class Workspace:
    def __init__(self, root=Path('/agents'), home=None, uid=None):
        self.uid = os.getuid() if uid is None else uid
        self.home = Path.home() if home is None else home
        self.base = root / 'users' / str(self.uid)
        self.work = self.base / 'Work'
        self.config = self.base / 'config'
        self.data = self.base / 'data'
        self.cache = self.base / 'cache'
        self.settings_path = self.config / 'ark-agent.json'
        self.root = root

    def ready(self):
        if not self.work.is_dir() or not (self.home / 'Work').exists():
            raise RuntimeError('Workspace is not provisioned. Run ark-agent setup')
        if not os.path.samefile(self.work, self.home / 'Work'):
            raise RuntimeError('~/Work is not mounted from /agents. Run ark-agent setup')
        for path in (self.work, self.config, self.data, self.cache):
            if path.is_symlink() or path.stat().st_uid != self.uid:
                raise RuntimeError(f'Unexpected workspace ownership: {path}')

    def setup(self):
        try:
            self.ready()
        except (RuntimeError, FileNotFoundError):
            run('pkexec', HELPER, 'setup', '--uid', str(self.uid))
        self.ready()
        state = load_json(self.settings_path, {'schema': SCHEMA, 'agent': None, 'image': IMAGE})
        home = self.data / 'home'
        home.mkdir(mode=0o700, exist_ok=True)
        (self.config / 'tools').mkdir(mode=0o700, exist_ok=True)
        # Link inside the container to a read-only mount at the same system path.
        skill_links(self.home)
        # Use explicit container paths: absolute host symlinks would be broken there.
        for location in ('.agents/skills', '.claude/skills', '.codex/skills', '.gemini/skills'):
            directory = home / location
            directory.mkdir(parents=True, exist_ok=True)
            for skill in SKILLS.glob('*/SKILL.md'):
                target = directory / skill.parent.name
                if not target.exists() and not target.is_symlink():
                    target.symlink_to(CONTAINER_SKILLS / skill.parent.name)
        storage = self.config / 'containers-storage.conf'
        if not storage.exists():
            storage.write_text('[storage]\ndriver = "overlay"\n'
                               f'graphroot = "/orundum/users/{self.uid}/containers"\n'
                               f'runroot = "/run/user/{self.uid}/ark-agent-containers"\n')
            storage.chmod(0o600)
        host_storage = self.home / '.local/share/containers'
        private_storage = Path('/orundum/users') / str(self.uid) / 'containers'
        host_storage.parent.mkdir(parents=True, exist_ok=True)
        if host_storage.is_dir() and not host_storage.is_symlink() and not any(host_storage.iterdir()):
            if not os.path.ismount(host_storage):
                host_storage.rmdir()
        if not host_storage.exists() and not host_storage.is_symlink():
            host_storage.symlink_to(private_storage)
        # Existing storage, including the legacy shared symlink, is left intact.
        # Carrier/Distrobox keep their configured storage; the agent uses its
        # explicit private graphroot even on an older installation.
        fresh = not self.settings_path.exists()
        if fresh:
            save_json(self.settings_path, state)
        print(f'Workspace ready: {self.home / "Work"}')
        return fresh

    def settings(self):
        self.ready()
        return load_json(self.settings_path, {'schema': SCHEMA, 'agent': None, 'image': IMAGE})

    def container_exists(self):
        if not (self.config / 'containers-storage.conf').exists():
            return False
        os.environ['CONTAINERS_STORAGE_CONF'] = str(self.config / 'containers-storage.conf')
        return subprocess.run(['podman', 'container', 'exists', CONTAINER]).returncode == 0

    def owned_container(self):
        info = json.loads(run('podman', 'inspect', CONTAINER,
                              stdout=subprocess.PIPE).stdout)[0]
        labels = info['Config'].get('Labels') or {}
        if (labels.get('io.arklinux.agent-owner') != str(self.uid)
                or labels.get('io.arklinux.agent-path') != str(self.base)):
            raise RuntimeError('Container name belongs to another environment; refusing to reuse it')
        return info

    def environment(self, locked=False):
        settings = self.settings()
        # Serialize lazy creation across multiple desktop/terminal launches.
        with (self.config / 'environment.lock').open('a') as lock:
            if not locked:
                fcntl.flock(lock, fcntl.LOCK_EX)
            if not self.container_exists():
                (self.data / 'home').mkdir(mode=0o700, exist_ok=True)
                (self.config / 'tools').mkdir(mode=0o700, exist_ok=True)
                # Do not expose host home, session bus, SSH agent or engine sockets.
                run('podman', 'create', '--init', '--name', CONTAINER,
                    '--label', 'io.arklinux.agent-workspace=1',
                    '--label', f'io.arklinux.agent-owner={self.uid}',
                    '--label', f'io.arklinux.agent-path={self.base}',
                    '--userns=keep-id:uid=1000,gid=1000',
                    '--hostname', 'ark-agent',
                    '--mount', f'type=bind,src={self.data / "home"},dst=/home/agent',
                    '--mount', f'type=bind,src={self.work},dst=/home/agent/Work',
                    '--mount', f'type=bind,src={self.config / "tools"},dst=/home/agent/.config',
                    '--mount', f'type=bind,src={self.cache},dst=/home/agent/.cache',
                    '--mount', f'type=bind,src={SKILLS},dst={CONTAINER_SKILLS},ro=true',
                    '--publish', '127.0.0.1::3000',
                    '--publish', '127.0.0.1::5173',
                    '--publish', '127.0.0.1::8000',
                    '--publish', '127.0.0.1::8080',
                    settings['image'])
            info = self.owned_container()
            if not info['State']['Running']:
                run('podman', 'start', CONTAINER, stdout=subprocess.DEVNULL)
            save_json(self.config / 'environment.json', {
                'schema': SCHEMA, 'image_id': info['Image'],
                'image': settings['image'], 'container': CONTAINER,
            })

    def rebuild(self):
        with (self.config / 'environment.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._rebuild_locked()

    def _rebuild_locked(self):
        settings = self.settings()
        backup = None
        # Pull first: network failure must not disturb the working environment.
        os.environ['CONTAINERS_STORAGE_CONF'] = str(self.config / 'containers-storage.conf')
        run('podman', 'pull', settings['image'])
        if self.container_exists():
            self.owned_container()
            run('podman', 'stop', CONTAINER)
            backup = f'localhost/ark-agent-backup:{time.time_ns()}'
            run('podman', 'commit', CONTAINER, backup)
            run('podman', 'rm', CONTAINER)
        try:
            self.environment(locked=True)
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            if backup:
                if self.container_exists():
                    self.owned_container()
                    run('podman', 'rm', '-f', CONTAINER)
                desired_image = settings['image']
                settings['image'] = backup
                save_json(self.settings_path, settings)
                try:
                    self.environment(locked=True)
                finally:
                    # Retain the desired release so a later rebuild can retry.
                    settings['image'] = desired_image
                    save_json(self.settings_path, settings)
                print(f'Rebuild failed; previous toolchain restored from {backup}', file=sys.stderr)
            raise
        if backup:
            print(f'Previous toolchain retained as {backup}')

    def execute(self, command, root=False):
        self.environment()
        cwd = Path.cwd().resolve()
        try:
            relative = cwd.relative_to(self.work.resolve())
        except ValueError:
            try:
                relative = cwd.relative_to((self.home / 'Work').resolve())
            except ValueError:
                if cwd == self.home.resolve():
                    relative = Path('.')
                else:
                    raise RuntimeError('Run from ~/Work, or use --host for a host-side agent')
        args = ['podman', 'exec', '-i']
        if sys.stdin.isatty():
            args.append('-t')
        if root:
            args += ['--user', '0']
        args += ['--workdir', str(Path('/home/agent/Work') / relative), CONTAINER, *command]
        os.execvp(args[0], args)

    def migrate(self):
        load_json(self.settings_path, {'schema': SCHEMA})
        if not self.config.is_dir():
            subprocess.run(['pkexec', HELPER, 'setup', '--uid', str(self.uid)], check=False)
        with (self.config / 'migration.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('A Work migration is already in progress')
            return self._migrate_locked()

    def _migrate_locked(self):
        completed = load_json(self.config / 'work-migration.json', {'schema': SCHEMA})
        if completed.get('complete') and (self.home / 'Work').exists() and os.path.samefile(self.home / 'Work', self.work):
            print(f'Migration already complete; original retained at {completed["backup"]}')
            return
        if self.container_exists():
            raise RuntimeError('Remove/stop the existing agent environment before migrating Work')
        journal = self.config / 'work-migration.json'
        target = self.home / 'Work'
        if not self.config.is_dir():
            # setup provisions storage before refusing a nonempty target.
            subprocess.run(['pkexec', HELPER, 'setup', '--uid', str(self.uid)], check=False)
        state = load_json(journal, {'schema': SCHEMA})
        if 'backup' in state:
            backup = Path(state['backup'])
            if backup.parent != self.home or not backup.name.startswith('Work.before-agents-'):
                raise RuntimeError('Unexpected migration backup location')
        else:
            if target.is_symlink() or not target.is_dir() or os.path.ismount(target):
                raise RuntimeError('Migration requires an ordinary ~/Work directory')
            backup = self.home / f'Work.before-agents-{time.time_ns()}'
            state['backup'] = str(backup)
            save_json(journal, state)
        if not backup.exists():
            target.rename(backup)
            directory_fd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        if target.exists() and any(target.iterdir()):
            if os.path.samefile(target, self.work):
                print(f'Migration already mounted; backup retained at {backup}')
                return
            raise RuntimeError('New files appeared in ~/Work; migration paused without overwriting them')
        run('rsync', '-aHAX', '--', str(backup) + '/', str(self.work) + '/')
        difference = run('rsync', '-aHAXnci', '--delete', '--', str(backup) + '/',
                         str(self.work) + '/', stdout=subprocess.PIPE).stdout
        if difference:
            raise RuntimeError('Source changed during migration. Stop writers and rerun; backup retained')
        self.setup()
        state['complete'] = True
        save_json(journal, state)
        print(f'Migration verified. Original retained at {backup}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='store_true', help='Run the selected agent directly on the host')
    sub = parser.add_subparsers(dest='action')
    setup = sub.add_parser('setup', help='Prepare the user workspace and skills')
    setup.add_argument('--notify', action='store_true')
    default = sub.add_parser('default', help='Show/set the default agent executable')
    default.add_argument('executable', nargs='?')
    sub.add_parser('status')
    sub.add_parser('rebuild', help='Refresh the environment, retaining its previous toolchain')
    sub.add_parser('shell', help='Open a shell with mutable development tooling')
    install = sub.add_parser('install', help='Install a user-selected npm agent in the environment')
    install.add_argument('package')
    sub.add_parser('stop')
    sub.add_parser('ports', help='Show localhost preview ports')
    sub.add_parser('snapshot', help='Create a read-only snapshot of Work')
    sub.add_parser('snapshots', help='List your Work snapshots')
    restore = sub.add_parser('restore', help='Restore Work, retaining a snapshot of current data')
    restore.add_argument('snapshot')
    sub.add_parser('migrate-work', help='Move existing Work with a retained original and verification')
    command = sub.add_parser('run', help='Run a command in the agent environment')
    command.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.host and args.action:
        parser.error('--host launches the selected agent without a subcommand')
    if os.getuid() == 0:
        parser.error('Run ark-agent as your regular user')
    workspace = Workspace()
    if args.action == 'setup':
        fresh = workspace.setup()
        if args.notify and fresh:
            run('notify-send', 'Ark Agent', 'Workspace ready. Choose a tool with ark-agent default <command>.')
        return
    if args.action == 'migrate-work':
        workspace.migrate()
        return
    settings = workspace.settings()
    if args.action == 'default':
        if args.executable:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.executable):
                parser.error('Use an executable name without arguments or a path')
            settings['agent'] = args.executable
            save_json(workspace.settings_path, settings)
        print(settings.get('agent') or 'No agent selected')
    elif args.action == 'status':
        print(json.dumps({'workspace': str(workspace.work), 'settings': settings,
                          'environment': load_json(workspace.config / 'environment.json',
                                                   {'schema': SCHEMA})}, indent=2))
    elif args.action == 'ports':
        if not workspace.container_exists():
            raise RuntimeError('Agent environment has not been created')
        workspace.owned_container()
        run('podman', 'port', CONTAINER)
    elif args.action == 'stop':
        if workspace.container_exists():
            workspace.owned_container()
            run('podman', 'stop', CONTAINER)
    elif args.action == 'snapshots':
        run('pkexec', HELPER, 'snapshots', '--uid', str(workspace.uid))
    elif args.action == 'restore':
        with (workspace.config / 'environment.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if workspace.container_exists():
                workspace.owned_container()
                run('podman', 'stop', CONTAINER)
            run('pkexec', HELPER, 'restore', '--uid', str(workspace.uid), '--snapshot', args.snapshot)
    elif args.action == 'snapshot':
        if workspace.container_exists():
            info = workspace.owned_container()
            if info['State']['Running']:
                raise RuntimeError('Stop the environment and other workspace writers before snapshotting')
        run('pkexec', HELPER, 'snapshot', '--uid', str(workspace.uid))
    elif args.action == 'rebuild':
        workspace.rebuild()
    elif args.action == 'shell':
        workspace.execute(['bash', '-l'])
    elif args.action == 'install':
        if args.package.startswith('-') or any(c.isspace() for c in args.package):
            parser.error('Use one npm package specification')
        workspace.execute(['npm', 'install', '--global', '--', args.package])
    elif args.action == 'run':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('run requires a command')
        workspace.execute(command)
    elif not settings.get('agent'):
        print('Choose your coding agent with ark-agent default <command>.\n'
              'Install it with ark-agent install <npm-package>, or use ark-agent shell.')
    elif args.host:
        # Host execution deliberately uses host tools/configuration and permissions.
        if Path.cwd().resolve() == workspace.home.resolve():
            os.chdir(workspace.home / 'Work')
        os.execvp(settings['agent'], [settings['agent']])
    else:
        workspace.execute([settings['agent']])


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f'Ark agents: {error}', file=sys.stderr)
        if '--notify' in sys.argv:
            subprocess.run(['notify-send', 'Ark Agent workspace needs attention', str(error)], check=False)
        raise SystemExit(1)
