#!/usr/bin/python3
"""Remove build-time caches and runtime state, preserving injected mounts."""
import os
from pathlib import Path


def clean(path):
    if path.is_symlink():
        path.unlink()
        return True
    if os.path.ismount(path):
        return False
    if path.is_dir():
        empty = True
        for child in path.iterdir():
            empty = clean(child) and empty
        if not empty:
            return False
        path.rmdir()
    else:
        path.unlink()
    return True


if __name__ == '__main__':
    for directory in (Path('/run'), Path('/tmp'), Path('/var/cache/pacman/pkg'),
                      Path('/var/cache/fontconfig')):
        if directory.is_dir() and not os.path.ismount(directory):
            for entry in directory.iterdir():
                clean(entry)
