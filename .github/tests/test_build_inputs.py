import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT/'download-aur-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def package(self, name):
        return {'name': f'{name}-1-1-x86_64.pkg.tar.zst'}
    def test_required_packages_and_debug_filter(self):
        assets = [self.package(n) for n in ['plymouth','bootc','bootupd','libselinux','bootc-debug']]
        self.assertEqual(len(release.select_assets({'assets':assets},'packages')),4)
    def test_missing_package_fails(self):
        with self.assertRaises(ValueError):
            release.select_assets({'assets':[self.package('plymouth')]},'packages')
    def test_duplicates_fail(self):
        assets = [self.package(n) for n in ['plymouth','bootc','bootupd','libselinux','plymouth']]
        with self.assertRaises(ValueError):
            release.select_assets({'assets':assets},'packages')
    def test_complete_cache_beyond_six_parts(self):
        assets=[{'name':f'pacman-cache.tar.gz.part-a{c}'} for c in 'abcdefgh']
        self.assertEqual(len(release.select_assets({'assets':assets},'cache')),8)
    def test_missing_cache_part_fails(self):
        with self.assertRaises(ValueError):
            release.select_assets({'assets':[{'name':'pacman-cache.tar.gz.part-ab'}]},'cache')

class InstallerTests(unittest.TestCase):
    def run_installer(self, failure=''):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            (d/'archives').mkdir()
            for name in ['plymouth','bootc','bootc-debug','linux-headers']:
                (d/'archives'/f'{name}-1-1-x86_64.pkg.tar.zst').touch()
            (d/'install').mkdir()
            (d/'hooks').mkdir()
            (d/'install/plymouth').touch()
            (d/'hooks/plymouth').touch()
            mock=d/'pacman'
            mock.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "'''+str(d/'calls')+'''"
case "$1" in
  -Qp) file=${2##*/}; printf '%s 1-1\\n' "${file%-1-1-x86_64.pkg.tar.zst}" ;;
  -Si) [[ "$2" == plymouth ]] ;;
  -S) [[ "'''+failure+'''" != official ]] ;;
  -U) [[ "'''+failure+'''" != local ]] ;;
  -Q) true ;;
esac
''')
            mock.chmod(0o755)
            script=(ROOT/'install-packages.sh').read_text().replace('/usr/bin/pacman',str(mock)).replace('/tmp/aur-packages',str(d/'archives')).replace('/usr/lib/initcpio',str(d))
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True)
            return result,(d/'calls').read_text()
    def test_routes_official_and_local_and_skips_debug_headers(self):
        result,calls=self.run_installer()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('-S --needed --noconfirm plymouth',calls)
        install=[line for line in calls.splitlines() if line.startswith('-U')][0]
        self.assertIn('bootc-1-1',install)
        self.assertNotIn('debug',install)
        self.assertNotIn('headers',install)
    def test_official_failure_stops_before_local_install(self):
        result,calls=self.run_installer('official')
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('-U ',calls)
    def test_local_failure_stops_before_boot_checks(self):
        result,calls=self.run_installer('local')
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('-Q plymouth',calls)

if __name__ == "__main__":
    unittest.main(verbosity=2)
