#!/usr/bin/env python3
"""Apply Lyd Ark's staged-deployment visibility patch to PackageKit-bootc."""

from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()

old_summary = '    summary = f"Container image update ({added_size} to download)"'
new_summary = '''    if update_info.get("staged"):
        summary = "Staged Lyd Ark system update (ready to reboot)"
        description_prefix = "Staged bootc image update; reboot to activate. "
    else:
        summary = f"Container image update ({added_size} to download)"
        description_prefix = "bootc container image update; "'''
assert source.count(old_summary) == 1, "Unexpected upstream update-summary code"
source = source.replace(old_summary, new_summary, 1)

old_description = 'description=f"bootc container image update; Digest: {digest}; Layers:'
new_description = 'description=f"{description_prefix}Digest: {digest}; Layers:'
assert source.count(old_description) == 1, "Unexpected upstream update-details code"
source = source.replace(old_description, new_description, 1)

old_get_updates = '''def cmd_get_updates(filters):
    """Handle get-updates command"""
    status(STATUS_QUERY)

    bootc_output = bootc_check_updates()
    if bootc_output is None:
        # bootc_check_updates already called error() and finished()
        return

    # Check if no updates available
    no_changes_image = parse_no_changes(bootc_output)
    if no_changes_image:
        # No updates available - just finish without emitting any packages
        pass
    else:
        # Check for available updates
        update_info = parse_update_available(bootc_output)
        if update_info:
            print_update_available(update_info)

    finished()
'''
new_get_updates = '''def get_staged_update_info():
    """
    Return a PackageKit update record when bootc already has an update staged.

    Lyd Ark's background updater may stage an image before Discover is opened.
    Keep that deployment visible in Discover until the user reboots.
    """
    try:
        result = subprocess.run(
            [BOOTC_CMD, "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        status_data = json.loads(result.stdout).get("status", {})
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    staged = status_data.get("staged")
    if not isinstance(staged, dict) or not staged.get("image"):
        return None

    staged_image = staged["image"]
    image_ref = staged_image.get("image", {}).get("image")
    digest = staged_image.get("imageDigest", "")
    if not image_ref or not digest:
        return None

    return {
        "image": image_ref,
        "digest": digest,
        "added_size": "already downloaded",
        "total_new_size_bytes": 0,
        "added_size_bytes": 0,
        "removed_size_bytes": 0,
        "total_size_bytes": 0,
        "total_new_layers": 0,
        "added_layers": 0,
        "removed_layers": 0,
        "staged": True,
    }


def cmd_get_updates(filters):
    """Handle get-updates command"""
    status(STATUS_QUERY)

    bootc_output = bootc_check_updates()
    if bootc_output is None:
        # bootc_check_updates already called error() and finished()
        return

    update_info = parse_update_available(bootc_output)
    if update_info:
        print_update_available(update_info)
    else:
        # The periodic Lyd Ark updater may have staged the latest image already.
        staged_update = get_staged_update_info()
        if staged_update:
            print_update_available(staged_update)

    finished()
'''
assert source.count(old_get_updates) == 1, "Unexpected upstream get-updates implementation"
source = source.replace(old_get_updates, new_get_updates, 1)

path.write_text(source)
print(f"Patched staged-update visibility in {path}")
