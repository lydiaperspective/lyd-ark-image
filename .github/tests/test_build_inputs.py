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
            (d/'bin').mkdir()
            for executable in ('ark', 'lydsys'):
                target = d/'bin'/executable
                target.write_text('#!/bin/sh\\nexit 0\\n')
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
                '/usr/bin/ark': str(d/'bin/ark'),
                '/usr/bin/lydsys': str(d/'bin/lydsys'),
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



class SteamPackageManagerTests(unittest.TestCase):
    def test_steam_feature_uses_carrier_pacman_and_multilib(self):
        feature_manager = (ROOT/'ark').read_text()
        self.assertIn('as_root pacman -Syu --needed --noconfirm steam', feature_manager)
        self.assertIn('distrobox enter archlinux -- sudo sh -c', feature_manager)
        self.assertIn('^\\\\[multilib\\\\]', feature_manager)
        self.assertIn('pacman -Rns --noconfirm steam', feature_manager)
        self.assertNotIn('flatpak install --system --noninteractive --assumeyes --or-update flathub "$APP_ID_STEAM"', feature_manager)
        self.assertIn('remove_legacy_steam_flatpak', feature_manager)

    def test_steam_documentation_describes_pacman_container(self):
        readme = (ROOT/'README.md').read_text()
        self.assertIn('Steam on demand through Pacman in the Arch Distrobox', readme)

class DesktopArchiveCommandTests(unittest.TestCase):
    def test_kde_ark_keeps_its_executable_and_zip_backend(self):
        containerfile = (ROOT/'Containerfile').read_text()
        installer = (ROOT/'install-packages.sh').read_text()
        self.assertIn('dolphin ark libarchive okular', containerfile)
        self.assertIn('COPY ark /usr/bin/lydsys', containerfile)
        self.assertNotIn('COPY ark /usr/bin/ark', containerfile)
        self.assertIn('pacman -Q ark libarchive', containerfile)
        self.assertIn('test -x /usr/bin/ark', containerfile)
        self.assertIn('test -x /usr/bin/ark', installer)
        self.assertIn('test -x /usr/bin/lydsys', installer)

    def test_feature_manager_examples_use_lydsys(self):
        feature_manager = (ROOT/'ark').read_text()
        self.assertIn('Usage:', feature_manager)
        self.assertIn('lydsys feature list', feature_manager)
        self.assertIn('lydsys development enable', feature_manager)
        self.assertNotIn('ark development enable', feature_manager)


class BlsSyncTests(unittest.TestCase):
    def test_read_only_boot_mount_is_not_selected_for_mirroring(self):
        script = (ROOT/'bls-sync.sh').read_text()
        guard = 'case ",$BOOT_OPTIONS," in'
        self.assertIn(guard, script)
        self.assertIn('echo "bls-sync: /boot is read-only; skipping optional /boot mirror"', script)
        self.assertLess(script.index(guard), script.index('BOOT_DIR="$candidate"'))
        self.assertIn('findmnt -n -o OPTIONS --target "$candidate"', script)



class ServerFirstBootLoginTests(unittest.TestCase):
    def test_server_uses_tty_account_setup_and_masks_graphical_login(self):
        containerfile = (ROOT/'Containerfile').read_text()
        server_unit = (ROOT/'ark-initial-account-server.service').read_text()
        self.assertIn('install -m 0644 /usr/lib/systemd/system/ark-initial-account-server.service /usr/lib/systemd/system/ark-initial-account.service', containerfile)
        self.assertIn('systemctl enable ark-initial-account.service getty@tty1.service', containerfile)
        self.assertIn('systemctl mask display-manager.service plasmalogin.service', containerfile)
        self.assertIn('ExecStartPost=/usr/bin/systemctl --no-block start getty@tty1.service', server_unit)

    def test_desktop_keeps_plasma_first_boot_dependency(self):
        containerfile = (ROOT/'Containerfile').read_text()
        self.assertIn("mkdir -p /usr/lib/systemd/system/plasmalogin.service.d", containerfile)
        self.assertIn("'Requires=ark-initial-account.service'", containerfile)
        self.assertIn("printf '%s\\n' '[Unit]' 'Requires=ark-initial-account.service' 'After=ark-initial-account.service'", containerfile)
        self.assertNotIn("printf '%s\\\\n' '[Unit]' 'Requires=ark-initial-account.service'", containerfile)


class ServerNetworkWaitOnlineTests(unittest.TestCase):
    def test_server_masks_unused_systemd_networkd_wait_online(self):
        containerfile = (ROOT/'Containerfile').read_text()
        self.assertIn('systemctl enable NetworkManager tuned tuned-ppd sshd cockpit.socket libvirtd.service tailscaled.service', containerfile)
        self.assertIn('systemctl mask systemd-networkd-wait-online.service', containerfile)



class StorageManagerImageTests(unittest.TestCase):
    def test_lydstore_is_installed_in_shared_base_for_desktop_and_server(self):
        containerfile = (ROOT/'Containerfile').read_text()
        self.assertIn('ARG LYDSTORE_SHA=', containerfile)
        self.assertIn('lyd-ark-storage-manager.git', containerfile)
        self.assertIn('pip install --break-system-packages --no-build-isolation --no-deps', containerfile)
        self.assertIn('lydstore --help', containerfile)
        self.assertEqual(containerfile.count('rclone fuse3 python-pip python-setuptools ntfs-3g exfatprogs'), 2)

    def test_ark_storage_tmpfiles_uses_persistent_root_and_non_destructive_symlink(self):
        tmpfiles = (ROOT/'ark-storage.tmpfiles').read_text()
        self.assertIn('d /orundum/ark ', tmpfiles)
        self.assertIn('d /orundum/ark/Containers ', tmpfiles)
        self.assertIn('L /ark - - - - /orundum/ark', tmpfiles)
        containerfile = (ROOT/'Containerfile').read_text()
        self.assertNotIn('systemd-tmpfiles --create /usr/lib/tmpfiles.d/ark-storage.conf', containerfile)

    def test_fuse_allows_other_users_for_rootless_container_access(self):
        containerfile = (ROOT/'Containerfile').read_text()
        self.assertIn("user_allow_other", containerfile)


if __name__ == "__main__":
    unittest.main(verbosity=2)
