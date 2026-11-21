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
# PORT picks the server port (default 8765).
shell=${LAUNCH_SHELL:-$(dscl . -read "/Users/$(id -un)" UserShell 2>/dev/null | awk '{print $2}' || true)}
shell=${shell:-$SHELL}
port=${PORT:-8765}
[[ $port =~ ^[0-9]+$ ]] || { echo "PORT must be a number, got '$port'" >&2; exit 1; }

# Quote a value as an AppleScript string literal.
as_str() { local s=${1//\\/\\\\}; printf '"%s"' "${s//\"/\\\"}"; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Paths reach the shell through `quoted form of`, so quotes and spaces in them are safe.
# /api/version answering with "summaries" identifies this server, not just anything on the port.
cat > "$tmp/launcher.applescript" <<EOF
set repo to $(as_str "$repo")
set loginShell to $(as_str "$shell")
set srvPort to "$port"
set u to "http://127.0.0.1:" & srvPort
set logf to (POSIX path of (path to library folder from user domain)) & "Logs/claude-sessions.log"
set probe to "curl -sf " & u & "/api/version | grep -q summaries"
try
  do shell script probe
on error
  -- sessions.py indexes before it binds the port, so a cold start looks down for a while;
  -- don't start a second copy if one for this port is already building or indexing.
  try
    do shell script "pgrep -qf '(start[.]sh|sessions[.]py) --port " & srvPort & "\$'"
  on error
    set cmd to "exec " & quoted form of (repo & "/start.sh") & " --port " & srvPort
    do shell script quoted form of loginShell & " -lc " & quoted form of cmd & " > " & quoted form of logf & " 2>&1 &"
  end try
  set ok to false
  repeat 300 times
    try
      do shell script probe
      set ok to true
      exit repeat
    end try
    delay 1
  end repeat
  if not ok then
    display dialog "Claude Sessions did not start within 5 minutes. Details are in " & logf buttons {"OK", "Open Log"} default button "Open Log" with icon caution
    if button returned of result is "Open Log" then do shell script "open " & quoted form of logf
    return
  end if
end try
open location u
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
/usr/libexec/PlistBuddy -c 'Delete :CFBundleIconName' "$app/Contents/Info.plist" 2>/dev/null || true
rm -f "$app/Contents/Resources/Assets.car"
codesign --force -s - "$app"
touch "$app"
echo "Built $app. Drag it to the Dock to pin it."
