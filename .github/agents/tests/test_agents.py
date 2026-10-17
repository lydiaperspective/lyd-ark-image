import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('ark_' + name, ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


storage = load('storage')
cli = load('cli')


class UserStateTests(unittest.TestCase):
    def test_unknown_schema_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            path.write_text('{"schema": 99, "agent": "personal"}')
            with self.assertRaises(RuntimeError):
                cli.load_json(path, {'schema': 1})
            self.assertIn('personal', path.read_text())

    def test_atomic_state_write_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            victim = Path(d) / 'victim'
            victim.write_text('untouched')
            path.with_name(f'state.json.{os.getpid()}.tmp').symlink_to(victim)
            with self.assertRaises(FileExistsError):
                cli.save_json(path, {'schema': 1})
            self.assertEqual(victim.read_text(), 'untouched')

    def test_skill_linking_preserves_personal_content_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = root / 'system/ark-linux'
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('skill')
            home = root / 'home'
            custom = home / '.agents/skills/ark-linux'
            custom.mkdir(parents=True)
            (custom / 'SKILL.md').write_text('personal')
            cli.skill_links(home, root / 'system')
            cli.skill_links(home, root / 'system')
            self.assertEqual((custom / 'SKILL.md').read_text(), 'personal')
            self.assertEqual((home / '.claude/skills/ark-linux').resolve(), skill)

    def test_workspace_refuses_unmounted_work(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            (home / 'Work').mkdir(parents=True)
            work = root / 'agents/users' / str(os.getuid()) / 'Work'
            work.mkdir(parents=True)
            workspace = cli.Workspace(root / 'agents', home)
            with self.assertRaisesRegex(RuntimeError, 'not mounted'):
                workspace.ready()

    def test_migration_retains_original_and_resumes_after_copy_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            (home / 'Work').mkdir(parents=True)
            (home / 'Work/source.txt').write_text('uncommitted work')
            workspace = cli.Workspace(root / 'agents', home)
            workspace.work.mkdir(parents=True)
            workspace.config.mkdir()
            with patch.object(workspace, 'container_exists', return_value=False), \
                 patch.object(workspace, 'setup'), patch.object(cli, 'run',
                     side_effect=subprocess.CalledProcessError(1, 'rsync')):
                with self.assertRaises(subprocess.CalledProcessError):
                    workspace.migrate()
            state = json.loads((workspace.config / 'work-migration.json').read_text())
            backup = Path(state['backup'])
            self.assertEqual((backup / 'source.txt').read_text(), 'uncommitted work')
            with patch.object(workspace, 'container_exists', return_value=False), \
                 patch.object(workspace, 'setup'):
                workspace.migrate()
            self.assertEqual((workspace.work / 'source.txt').read_text(), 'uncommitted work')
            self.assertTrue(backup.exists())

    def test_user_setup_preserves_existing_container_storage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            home.mkdir()
            workspace = cli.Workspace(root / 'agents', home)
            for path in (workspace.work, workspace.config, workspace.data, workspace.cache):
                path.mkdir(parents=True, exist_ok=True)
            (home / 'Work').symlink_to(workspace.work)
            storage = home / '.local/share/containers'
            storage.mkdir(parents=True)
            (storage / 'personal-state').write_text('keep')
            with patch.object(cli, 'SKILLS', root / 'no-system-skills'), patch.object(cli, 'run') as run:
                workspace.setup()
                workspace.setup()
                run.assert_not_called()
            self.assertFalse(storage.is_symlink())
            self.assertEqual((storage / 'personal-state').read_text(), 'keep')

    def test_setup_unknown_schema_has_no_user_configuration_side_effects(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            home.mkdir()
            workspace = cli.Workspace(root / 'agents', home)
            for path in (workspace.work, workspace.config, workspace.data, workspace.cache):
                path.mkdir(parents=True, exist_ok=True)
            (home / 'Work').symlink_to(workspace.work)
            workspace.settings_path.write_text('{"schema": 99}')
            with self.assertRaises(RuntimeError):
                workspace.setup()
            self.assertFalse((home / '.agents').exists())
            self.assertFalse((workspace.config / 'containers-storage.conf').exists())

    def test_rebuild_network_failure_keeps_existing_environment(self):
        with tempfile.TemporaryDirectory() as d:
            workspace = cli.Workspace(Path(d))
            workspace.config.mkdir(parents=True)
            with patch.object(workspace, 'settings', return_value={'schema': 1, 'image': 'desired'}), \
                 patch.object(workspace, 'container_exists') as exists, \
                 patch.object(cli, 'run', side_effect=subprocess.CalledProcessError(1, 'pull')):
                with self.assertRaises(subprocess.CalledProcessError):
                    workspace.rebuild()
                exists.assert_not_called()

    def test_rebuild_failure_restores_previous_toolchain(self):
        with tempfile.TemporaryDirectory() as d:
            workspace = cli.Workspace(Path(d))
            workspace.config.mkdir(parents=True)
            with patch.object(workspace, 'settings', return_value={'schema': 1, 'image': 'desired'}), \
                 patch.object(workspace, 'container_exists', side_effect=[True, False]), \
                 patch.object(workspace, 'owned_container'), \
                 patch.object(cli, 'run'), \
                 patch.object(workspace, 'environment', side_effect=[RuntimeError('failed'), None]) as environment:
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    workspace.rebuild()
                saved = json.loads(workspace.settings_path.read_text())
                self.assertEqual(saved['image'], 'desired')
                self.assertEqual(environment.call_count, 2)

    def test_rebuild_refuses_unrelated_container_before_stopping_it(self):
        with tempfile.TemporaryDirectory() as d:
            workspace = cli.Workspace(Path(d))
            workspace.config.mkdir(parents=True)
            unrelated = {'Config': {'Labels': {}}, 'State': {'Running': True}}
            response = subprocess.CompletedProcess([], 0, stdout=json.dumps([unrelated]))
            with patch.object(workspace, 'settings', return_value={'schema': 1, 'image': 'desired'}), \
                 patch.object(workspace, 'container_exists', return_value=True), \
                 patch.object(cli, 'run', return_value=response) as commands:
                with self.assertRaisesRegex(RuntimeError, 'another environment'):
                    workspace.rebuild()
                self.assertFalse(any(call.args[:2] in [('podman', 'stop'), ('podman', 'rm')]
                                     for call in commands.call_args_list))


class StorageTests(unittest.TestCase):
    def test_directory_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'actual').mkdir()
            (root / 'link').symlink_to(root / 'actual')
            with self.assertRaises(RuntimeError):
                storage.Storage.directory(root / 'link', owner=os.getuid())

    def test_existing_home_symlink_is_refused_before_mount(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            home.mkdir()
            (home / 'Work').symlink_to('/tmp')
            source = root / 'work'
            source.mkdir()
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home))
            with patch.object(storage.Storage, 'run') as run:
                with self.assertRaises(OSError):
                    storage.Storage(root).bind_work(account, source)
                run.assert_not_called()

    def test_nonempty_work_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / 'home'
            (home / 'Work').mkdir(parents=True)
            (home / 'Work/project').write_text('keep')
            (root / 'source').mkdir()
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home))
            with patch.object(storage.Storage, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'contains data'):
                    storage.Storage(root).bind_work(account, root / 'source')
                run.assert_not_called()
            self.assertEqual((home / 'Work/project').read_text(), 'keep')

    def test_restore_rejects_traversal(self):
        store = storage.Storage()
        with patch.object(store, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Invalid snapshot'):
                store.restore(SimpleNamespace(pw_uid=1000), Path('/unused'), '../../etc')
            run.assert_not_called()

    def test_missing_mount_refuses_user_provision(self):
        store = storage.Storage()
        with patch.object(store, 'mounted', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'not mounted'):
                store.provision(SimpleNamespace(pw_uid=1000))

    def test_snapshot_rejects_nested_subvolumes(self):
        store = storage.Storage()
        with patch.object(store, 'run', return_value=SimpleNamespace(stdout='ID 123 nested')):
            with self.assertRaisesRegex(RuntimeError, 'nested subvolumes'):
                store.snapshot(SimpleNamespace(pw_uid=1000), Path('/unused'))


if __name__ == '__main__':
    unittest.main()
