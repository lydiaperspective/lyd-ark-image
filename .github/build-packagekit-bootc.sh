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
python /tmp/patch-packagekit-bootc.py "$HELPER"

test -s "$BACKEND"
test -x "$HELPER"
grep -Fq "Staged Lyd Ark system update (ready to reboot)" "$HELPER"

DISCOVER_VERSION="$(pacman -Q discover | awk '{print $2}')"
if [[ "$(vercmp "$DISCOVER_VERSION" "6.8.0")" -lt 0 ]]; then
    echo "Discover $DISCOVER_VERSION predates the upstream bootc/OSTree PackageKit fix; refusing to ship an incompatible backend." >&2
    exit 1
fi
ldd "$BACKEND" | tee "$BUILD_ROOT/backend-dependencies.txt"
if grep -q "not found" "$BUILD_ROOT/backend-dependencies.txt"; then
    echo "PackageKit-bootc backend has unresolved shared-library dependencies." >&2
    exit 1
fi

# PackageKit must select the bootc backend instead of Arch's ALPM backend.
# Discover will then see the OS image as one updateable item, not host packages.
python - "$CONFIG" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
backend_line = None

for index, line in enumerate(lines):
    candidate = line.strip()
    if candidate.startswith("#"):
        candidate = candidate[1:].strip()
    if candidate.startswith("DefaultBackend="):
        backend_line = index
        break

if backend_line is not None:
    lines[backend_line] = "DefaultBackend=bootc"
elif "[Daemon]" in lines:
    lines.insert(lines.index("[Daemon]") + 1, "DefaultBackend=bootc")
else:
    lines.extend(["", "[Daemon]", "DefaultBackend=bootc"])

path.write_text("\n".join(lines) + "\n")
PY

grep -Eq '^DefaultBackend=bootc
# Validate the helper syntax without writing bytecode into the system image.
python -c "from pathlib import Path; p=Path('$HELPER'); compile(p.read_text(), str(p), 'exec')"

echo "Lyd Ark: PackageKit-bootc backend installed and selected."
 "$CONFIG"

# Arch disables PackageKit activation on OSTree systems by default. Lyd Ark
# uses bootc/OSTree, so replace that condition with an explicit bootc check.
PACKAGEKIT_UNIT=/usr/lib/systemd/system/packagekit.service
PACKAGEKIT_DROPIN_DIR=/usr/lib/systemd/system/packagekit.service.d
if [[ ! -s "$PACKAGEKIT_UNIT" ]]; then
    echo "PackageKit systemd service unit is missing; cannot configure bootc activation." >&2
    exit 1
fi
install -d "$PACKAGEKIT_DROPIN_DIR"
cat > "$PACKAGEKIT_DROPIN_DIR/10-lyd-ark-bootc.conf" <<'EOF'
[Unit]
ConditionPathExists=
ConditionPathExists=/run/ostree-booted
EOF
grep -Fq 'ConditionPathExists=/run/ostree-booted' "$PACKAGEKIT_DROPIN_DIR/10-lyd-ark-bootc.conf"


# Validate the helper syntax without writing bytecode into the system image.
python -c "from pathlib import Path; p=Path('$HELPER'); compile(p.read_text(), str(p), 'exec')"

echo "Lyd Ark: PackageKit-bootc backend installed and selected."
