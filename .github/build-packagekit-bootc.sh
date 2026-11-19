#!/usr/bin/env bash
set -euo pipefail

# Build the upstream PackageKit backend that exposes bootc image upgrades to
# PackageKit clients such as KDE Discover. Pin the source for reproducibility.
readonly UPSTREAM_REPO="https://github.com/FyraLabs/PackageKit-bootc.git"
readonly UPSTREAM_COMMIT="7d82505b94ae5fc3388ef780520ca07dc9bdb994"
readonly BUILD_ROOT="$(mktemp -d /tmp/lyd-ark-packagekit-bootc.XXXXXX)"
readonly SOURCE_DIR="${BUILD_ROOT}/source"
readonly BUILD_DIR="${SOURCE_DIR}/builddir"
readonly HELPER="/usr/share/PackageKit/helpers/bootc/bootcBackend.py"
readonly BACKEND="/usr/lib/packagekit-backend/libpk_backend_bootc.so"
readonly CONFIG="/etc/PackageKit/PackageKit.conf"

cleanup() {
    rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

git clone --filter=blob:none --no-checkout "$UPSTREAM_REPO" "$SOURCE_DIR"
git -C "$SOURCE_DIR" checkout --detach "$UPSTREAM_COMMIT"
git -C "$SOURCE_DIR" submodule update --init --recursive

# Fix an upstream Meson version-string typo without changing the backend code.
sed -i "s/>=2\\. 54\\.0/>=2.54.0/" "$SOURCE_DIR/meson.build"
grep -Fq "version: '>=2.54.0'" "$SOURCE_DIR/meson.build"

meson setup "$BUILD_DIR" "$SOURCE_DIR" \
    --prefix=/usr \
    --libdir=lib \
    --buildtype=release
meson compile -C "$BUILD_DIR"
meson install -C "$BUILD_DIR"

test -s "$BACKEND"
test -x "$HELPER"
ldd "$BACKEND" | tee "$BUILD_ROOT/backend-dependencies.txt"
if grep -q "not found" "$BUILD_ROOT/backend-dependencies.txt"; then
    echo "PackageKit-bootc backend has unresolved shared-library dependencies." >&2
    exit 1
fi

# PackageKit must select the bootc backend instead of Arch's ALPM backend.
# Discover will then see the OS image as one updateable item, not host packages.
python - "$CONFIG" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
pattern = r"(?m)^[ \\t]*#?[ \\t]*DefaultBackend=.*$"
if re.search(pattern, text):
    text = re.sub(pattern, "DefaultBackend=bootc", text, count=1)
elif re.search(r"(?m)^\\[Daemon\\][ \\t]*$", text):
    text = re.sub(
        r"(?m)^(\\[Daemon\\][ \\t]*)$",
        r"\\1\\nDefaultBackend=bootc",
        text,
        count=1,
    )
else:
    text = text.rstrip() + "\\n\\n[Daemon]\\nDefaultBackend=bootc\\n"
path.write_text(text)
PY

grep -Eq '^DefaultBackend=bootc$' "$CONFIG"

# Validate the helper syntax without writing bytecode into the system image.
python -c "from pathlib import Path; p=Path('$HELPER'); compile(p.read_text(), str(p), 'exec')"

echo "Lyd Ark: PackageKit-bootc backend installed and selected."
