#!/bin/sh
# Build + self-test + .dmg on macOS (M2, arm64). Run from the project
# root: packaging/build_mac.sh
#
# One-time setup before the first run:
#   - Xcode Command Line Tools: xcode-select --install
#   - uv: curl -LsSf https://astral.sh/uv/install.sh | sh
set -eu

cd "$(dirname "$0")/.."

echo "== uv sync =="
uv sync

echo "== pytest =="
QT_QPA_PLATFORM=offscreen uv run pytest -q

echo "== pyinstaller =="
rm -rf packaging/build packaging/dist
uv run pyinstaller packaging/shop.spec --distpath packaging/dist --workpath packaging/build --noconfirm

APP="packaging/dist/BachHoa705.app"
if [ ! -d "$APP" ]; then
    echo "Build did not produce $APP" >&2
    exit 1
fi

echo "== self-test =="
SELFTEST_DATA="$(mktemp -d)/data"
SELFTEST_OUT="packaging/dist/selftest-output"
rm -rf "$SELFTEST_OUT"
SHOP_DATA_DIR="$SELFTEST_DATA" SHOP_SELFTEST_OUT="$SELFTEST_OUT" \
    "$APP/Contents/MacOS/BachHoa705" --self-test
RESULT="$SELFTEST_OUT/result.txt"
if [ ! -f "$RESULT" ] || [ "$(head -n1 "$RESULT")" != "OK" ]; then
    echo "Self-test failed, see $RESULT" >&2
    cat "$RESULT" 2>/dev/null || true
    exit 1
fi
echo "Self-test OK. Screenshots in $SELFTEST_OUT for a manual look."

echo "== .dmg =="
DMG="packaging/dist/BachHoa705.dmg"
rm -f "$DMG"
hdiutil create -volname "BachHoa705" -srcfolder "$APP" -ov -format UDZO "$DMG"

echo "Done: $DMG"
echo "Reminder: this build is ad-hoc signed (Apple Silicon requires some"
echo "signature), not notarized. First launch on any Mac needs:"
echo "  System Settings -> Privacy & Security -> \"Open Anyway\""
echo "See CLAUDE_hethongson.md muc 7 for the full first-run + Documents"
echo "permission steps (DiBeKho hit the same thing)."
