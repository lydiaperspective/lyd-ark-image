import importlib.util
import os
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
    def run_installer(self, failure='', variant=''):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            (d/'archives').mkdir()
            for name in ['plymouth','bootc','bootc-debug','linux-headers','nuttyimgconverter','nautilus-python','nautilus','gnome-system-monitor','gnome-disk-utility-git']:
                (d/'archives'/f'{name}-1-1-x86_64.pkg.tar.zst').touch()
            (d/'install').mkdir()
            (d/'hooks').mkdir()
            (d/'install/plymouth').touch()
            (d/'hooks/plymouth').touch()
            # Isolate the desktop integration checks from the host runner.
            fixtures = {
                'usr/lib/systemd/system/plasmalogin.service': '[Service]\n',
                'usr/lib/systemd/system/virt-secret-init-encryption.service': '[Service]\n',
                'usr/lib/systemd/system/virt-secret-init-encryption.service.d/10-ark-secret-directory.conf': 'ExecStartPre=/usr/bin/install -d -m 0700 -o root -g root /var/lib/libvirt/secrets\n',
                'usr/lib/systemd/user/ark-solaar.service': '[Service]\n',
                'usr/lib/systemd/user/ark-sunshine.service': '[Service]\n',
                'usr/libexec/ark/ark-development': '#!/bin/sh\n',
                'usr/libexec/ark/ark-virtualization': '#!/bin/sh\n',
                'usr/lib/packagekit-backend/libpk_backend_bootc.so': 'fixture\n',
                'usr/share/PackageKit/helpers/bootc/bootcBackend.py': '#!/usr/bin/env python3\n',
                'etc/PackageKit/PackageKit.conf': 'DefaultBackend=bootc\n',
                'etc/sudoers.d/10-wheel': '%wheel ALL=(ALL:ALL) ALL\n',
                'etc/pam.d/system-login': 'session required pam_mkhomedir.so skel=/etc/skel umask=0077\n',
            }
            if variant == 'intel3-server-lts':
                fixtures.pop('usr/lib/packagekit-backend/libpk_backend_bootc.so')
            for relative, content in fixtures.items():
                target = d/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                if relative.endswith(('bootcBackend.py', 'ark-development', 'ark-virtualization')):
                    target.chmod(0o755)
            mock=d/'pacman'
            mock.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "'''+str(d/'calls')+'''"
case "$1" in
  -Qp) file=${2##*/}; printf '%s 1-1\\n' "${file%-1-1-x86_64.pkg.tar.zst}" ;;
  -Si) [[ "$2" == plymouth ]] ;;
  -S) [[ "'''+failure+'''" != official ]] ;;
  -U)
    [[ "'''+failure+'''" != local ]] || exit 1
    shift
    for archive in "$@"; do
      file=${archive##*/}
      pkg=${file%-1-1-x86_64.pkg.tar.zst}
      touch "'''+str(d/'installed-gnome-apps')+'''-$pkg"
    done
    ;;
  -Qq)
    for marker in "'''+str(d/'installed-gnome-apps')+'''-"*; do
      [[ -e "$marker" ]] || continue
      pkg=${marker#*installed-gnome-apps-}
      [[ -e "'''+str(d/'removed-gnome-apps')+'''-$pkg" ]] || printf '%s\\n' "$pkg"
    done
    ;;
  -Q)
    if [[ "$#" -eq 2 ]]; then
      pkg="$2"
      case "$pkg" in
        nuttyimgconverter|nautilus-python|nautilus|gnome-system-monitor|gnome-disk-utility|gnome-disk-utility-git)
          [[ -e "'''+str(d/'installed-gnome-apps')+'''-$pkg" && ! -e "'''+str(d/'removed-gnome-apps')+'''-$pkg" ]]
          ;;
        plasma-login-manager)
          [[ "${VARIANT:-}" != intel3-server-lts ]]
          ;;
        *)
          true
          ;;
      esac
    fi
    ;;
  -Rns)
    shift 2
    for pkg in "$@"; do touch "'''+str(d/'removed-gnome-apps')+'''-$pkg"; done
    ;;
esac
''')
            mock.chmod(0o755)
            script=(ROOT/'install-packages.sh').read_text()
            for source, target in {
                '/usr/bin/pacman': str(mock),
                '/tmp/aur-packages': str(d/'archives'),
                '/usr/lib/initcpio': str(d),
                '/usr/lib/systemd/system': str(d/'usr/lib/systemd/system'),
                '/usr/lib/systemd/user': str(d/'usr/lib/systemd/user'),
                '/usr/libexec/ark': str(d/'usr/libexec/ark'),
                '/usr/lib/packagekit-backend': str(d/'usr/lib/packagekit-backend'),
                '/usr/share/PackageKit': str(d/'usr/share/PackageKit'),
                '/etc/PackageKit': str(d/'etc/PackageKit'),
                '/etc/sudoers.d': str(d/'etc/sudoers.d'),
                '/etc/pam.d': str(d/'etc/pam.d'),
            }.items():
                script=script.replace(source, target)
            env=os.environ.copy()
            if variant:
                env['VARIANT']=variant
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=env)
            return result,(d/'calls').read_text()
    def test_routes_official_and_local_and_skips_debug_headers(self):
        result,calls=self.run_installer()
        self.assertEqual(result.returncode,0,result.stderr + result.stdout)
        self.assertIn('-S --needed --noconfirm plymouth',calls)
        install=[line for line in calls.splitlines() if line.startswith('-U')][0]
        self.assertIn('bootc-1-1',install)
        self.assertNotIn('debug',install)
        self.assertNotIn('headers',install)
        removal_calls = [line for line in calls.splitlines() if line.startswith('-Rns --noconfirm ')]
        self.assertEqual(
            removal_calls,
            ['-Rns --noconfirm nuttyimgconverter nautilus-python nautilus gnome-system-monitor gnome-disk-utility-git'],
        )
    def test_server_skips_desktop_only_aur_archives(self):
        result,calls=self.run_installer(variant='intel3-server-lts')
        self.assertEqual(result.returncode,0,result.stderr + result.stdout)
        install=[line for line in calls.splitlines() if line.startswith('-U')][0]
        for package in ('nuttyimgconverter','nautilus-python','nautilus','gnome-system-monitor','gnome-disk-utility-git'):
            self.assertNotIn(package,install)
        self.assertIn('Skipping desktop-only package in server image: gnome-disk-utility-git',result.stdout)
        self.assertNotIn('-Rns --noconfirm',calls)
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
