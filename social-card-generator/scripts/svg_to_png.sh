#!/usr/bin/env sh
# Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
# Rasterize an SVG card to PNG with whatever renderer is installed
# (rsvg-convert > inkscape > chrome-headless-shell > Chrome/Chromium), then
# verify the PNG signature, pixel dimensions and size budget.
# OpenGraph/X/LinkedIn require PNG or JPEG: never ship an SVG as og:image.
#
# Usage: svg_to_png.sh card.svg [card.png] [scale]
#   scale: 1 (default) or 2 for retina exports.
# Exit codes: 0 = ok, 1 = render/verify failed, 2 = usage error / no renderer.
set -eu

[ $# -ge 1 ] || { echo "usage: $0 input.svg [output.png] [scale]" >&2; exit 2; }
IN=$1
OUT=${2:-${IN%.svg}.png}
SCALE=${3:-1}
[ -f "$IN" ] || { echo "error: $IN not found" >&2; exit 2; }
case $SCALE in 1|2) ;; *) echo "error: scale must be 1 or 2" >&2; exit 2 ;; esac

DIMS=$(python3 - "$IN" <<'PY'
import re, sys
raw = open(sys.argv[1], encoding="utf-8").read()
tag = re.search(r"<svg\b[^>]*>", raw, flags=re.S)
tag = tag.group(0) if tag else ""
w = re.search(r'\swidth="(\d+)', tag)
h = re.search(r'\sheight="(\d+)', tag)
vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', tag)
W = w.group(1) if w else (str(int(float(vb.group(1)))) if vb else "")
H = h.group(1) if h else (str(int(float(vb.group(2)))) if vb else "")
print(W or "?", H or "?")
PY
)
W=${DIMS% *}; H=${DIMS#* }
[ "$W" != "?" ] && [ "$H" != "?" ] || { echo "error: cannot read SVG dimensions" >&2; exit 2; }
PW=$((W * SCALE)); PH=$((H * SCALE))
CROP=0

first_executable() {
  for c in "$@"; do
    [ -z "$c" ] && continue
    if command -v "$c" >/dev/null 2>&1; then command -v "$c"; return 0; fi
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

ABS=$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")
mkdir -p "$(dirname "$OUT")"
OUT_ABS=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
CHROME_FLAGS="--no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=$SCALE --default-background-color=00000000"

if command -v rsvg-convert >/dev/null 2>&1; then
  rsvg-convert -w "$PW" -h "$PH" -o "$OUT_ABS" "$ABS"
elif command -v inkscape >/dev/null 2>&1; then
  inkscape "$ABS" --export-type=png --export-filename="$OUT_ABS" -w "$PW" -h "$PH" >/dev/null 2>&1
elif SHELL_BIN=$(first_executable chrome-headless-shell headless_shell \
      /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell \
      /opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell); then
  # shellcheck disable=SC2086
  "$SHELL_BIN" $CHROME_FLAGS --window-size="$W,$H" --screenshot="$OUT_ABS" "file://$ABS" >/dev/null 2>&1
elif CHROME=$(first_executable "${CHROME_BIN:-}" chromium chromium-browser google-chrome google-chrome-stable \
      /opt/pw-browsers/chromium-*/chrome-linux/chrome \
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"); then
  # New-headless Chrome reserves part of the window for UI: render taller, then crop.
  # shellcheck disable=SC2086
  "$CHROME" --headless $CHROME_FLAGS --window-size="$W,$((H + 160))" --screenshot="$OUT_ABS" "file://$ABS" >/dev/null 2>&1
  CROP=1
else
  echo "error: no renderer found (install librsvg2-bin, inkscape or chromium)" >&2
  exit 2
fi
[ -s "$OUT_ABS" ] || { echo "FAIL: renderer produced no output" >&2; exit 1; }

python3 - "$OUT_ABS" "$PW" "$PH" "$CROP" <<'PY'
import os, struct, sys, zlib
path, ew, eh, crop = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1"
data = open(path, "rb").read()
if data[:8] != b"\x89PNG\r\n\x1a\n":
    sys.exit(f"FAIL: {path} is not a PNG")
chunks, pos = [], 8
while pos < len(data):
    length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
    chunks.append((ctype, data[pos + 8:pos + 8 + length]))
    pos += 12 + length
ihdr = chunks[0][1]
w, h, depth, color, _c, _f, interlace = struct.unpack(">IIBBBBB", ihdr)
if crop and h > eh:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    if interlace or depth != 8:
        sys.exit("FAIL: cannot crop interlaced / non-8-bit PNG")
    raw = zlib.decompress(b"".join(d for t, d in chunks if t == b"IDAT"))
    # Scanline filters only reference earlier rows, so the first eh rows stay valid as-is.
    raw = raw[: eh * (1 + w * channels)]
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    new_ihdr = struct.pack(">IIBBBBB", w, eh, depth, color, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", new_ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(out)
    h = eh
kb = os.path.getsize(path) / 1024
if (w, h) != (ew, eh):
    sys.exit(f"FAIL: {path} is {w}x{h}, expected {ew}x{eh}")
if kb > 5 * 1024:
    sys.exit(f"FAIL: {path} is {kb:.0f} KB; X/Twitter limit is 5 MB")
print(f"wrote {path} ({w}x{h}, {kb:.0f} KB)")
PY
