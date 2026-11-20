#!/usr/bin/env bash
# Build "Claude Sessions.app" in ~/Applications: a Dock-friendly launcher that
# starts the server (via start.sh) if it is not running, then opens it.
# Re-run after moving the repo or changing your login shell.
# Icon source: macos/icon.png, drawn by `swift macos/draw-icon.swift macos/icon.png`.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
app="$HOME/Applications/Claude Sessions.app"
# Run the server under a login shell so it gets your PATH (uv, node version).
# Defaults to the account shell; set LAUNCH_SHELL if your terminal uses another,
# e.g. LAUNCH_SHELL=/opt/homebrew/bin/fish ./macos/make-app.sh
shell=${LAUNCH_SHELL:-$(dscl . -read "$HOME" UserShell | awk '{print $2}')}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/launcher.applescript" <<EOF
set sh to "u=http://127.0.0.1:8765
curl -sf -o /dev/null \$u/api/version || { '$shell' -lc \"exec '$repo/start.sh'\" > \\"\$HOME/Library/Logs/claude-sessions.log\\" 2>&1 & }
for i in \$(seq 90); do curl -sf -o /dev/null \$u/api/version && break; sleep 1; done
open \$u"
do shell script sh
EOF

mkdir -p "$tmp/icon.iconset" "$HOME/Applications"
for s in 16 32 128 256 512; do
  sips -z $s $s "$here/icon.png" --out "$tmp/icon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$here/icon.png" --out "$tmp/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$tmp/icon.iconset" -o "$tmp/icon.icns"

rm -rf "$app"
osacompile -o "$app" "$tmp/launcher.applescript"
cp "$tmp/icon.icns" "$app/Contents/Resources/applet.icns"
# osacompile's asset catalog takes precedence over applet.icns, so drop it.
/usr/libexec/PlistBuddy -c 'Delete :CFBundleIconName' "$app/Contents/Info.plist"
rm -f "$app/Contents/Resources/Assets.car"
codesign --force -s - "$app"
touch "$app"
echo "Built $app. Drag it to the Dock to pin it."
