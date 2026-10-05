#!/usr/bin/env sh
# End-to-end self-test for every skill script against known-good and known-bad fixtures.
# Each case asserts an exact exit code. Usage: sh tests/run_all.sh
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
FX="$ROOT/tests/fixtures"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
pass=0; fail=0

expect() {  # expect <exit-code> <description> <command...>
  want=$1; desc=$2; shift 2
  "$@" >"$OUT/last.log" 2>&1
  got=$?
  if [ "$got" -eq "$want" ]; then
    pass=$((pass + 1)); printf 'ok    %s\n' "$desc"
  else
    fail=$((fail + 1)); printf 'FAIL  %s (exit %s, want %s)\n' "$desc" "$got" "$want"; sed 's/^/      /' "$OUT/last.log" | head -20
  fi
}

PY=python3
LP="$ROOT/landing-page-builder/scripts"
PF="$ROOT/portfolio-maker/scripts"
PD="$ROOT/pdf-maker/scripts"
SC="$ROOT/social-card-generator/scripts"
CC="$ROOT/code-cleaner/scripts"
TH="$ROOT/text-humanizer/scripts"

echo "== repository"
expect 0 "all SKILL.md manifests valid"            $PY "$ROOT/scripts/validate_skills.py" "$ROOT"

echo "== landing-page-builder / portfolio-maker"
expect 0 "good page passes enterprise --strict"     $PY "$LP/audit_html.py" "$FX/good_page.html" --tier enterprise --strict
expect 1 "bad page fails starter"                   $PY "$LP/audit_html.py" "$FX/bad_page.html" --tier starter
expect 0 "contrast pass"                            $PY "$LP/audit_html.py" --contrast "#0f172a" "#ffffff"
expect 1 "contrast fail"                            $PY "$LP/audit_html.py" --contrast "#94a3b8" "#ffffff"
expect 2 "missing file is usage error"              $PY "$LP/audit_html.py" "$OUT/nope.html"
expect 0 "profile valid (enterprise)"               $PY "$PF/validate_profile.py" "$FX/profile.json" --tier enterprise --normalize "$OUT/p.json"
printf '{"name":"x","role":"y","contact":{"email":"bad"},"skills":{},"projects":[]}' > "$OUT/badprofile.json"
expect 1 "invalid profile fails"                    $PY "$PF/validate_profile.py" "$OUT/badprofile.json"

echo "== pdf-maker"
expect 0 "markdown compiles"                        $PY "$PD/md_to_pdf.py" "$FX/sample.md" -o "$OUT/s.pdf"
expect 0 "pdf verifies"                             $PY "$PD/verify_pdf.py" "$OUT/s.pdf" --require-title --min-pages 2
printf '# T\n\nनमस्ते\n' > "$OUT/u.md"
expect 1 "strict fails on unsupported glyphs"       $PY "$PD/md_to_pdf.py" "$OUT/u.md" -o "$OUT/u.pdf" --strict
printf '  \n' > "$OUT/empty.md"
expect 2 "empty input rejected"                     $PY "$PD/md_to_pdf.py" "$OUT/empty.md" -o "$OUT/e.pdf"
printf '%%PDF-1.4\nbroken' > "$OUT/broken.pdf"
expect 1 "broken pdf fails verification"           $PY "$PD/verify_pdf.py" "$OUT/broken.pdf"

echo "== social-card-generator"
expect 0 "card renders"                             $PY "$SC/render_card.py" --title "Premium Agent Skills" --subtitle "Zero-dependency validators" --badge "Open Source" --handle "@octo" --url "github.com/octo/skills" -o "$OUT/c.svg" --strict
expect 0 "card validates"                           $PY "$SC/validate_svg.py" "$OUT/c.svg" --size og
expect 1 "low-contrast card refused"                $PY "$SC/render_card.py" --title "x" --fg "#334155" -o "$OUT/bad.svg"
printf '<!DOCTYPE x [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>' > "$OUT/xxe.svg"
expect 1 "XXE svg rejected"                         $PY "$SC/validate_svg.py" "$OUT/xxe.svg"
if command -v rsvg-convert >/dev/null 2>&1 || command -v inkscape >/dev/null 2>&1 \
   || ls /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell >/dev/null 2>&1 \
   || command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; then
  expect 0 "png rasterises at exact size"           sh "$SC/svg_to_png.sh" "$OUT/c.svg" "$OUT/c.png" 1
else
  echo "skip  png rasterisation (no renderer installed)"
fi

echo "== code-cleaner"
expect 1 "dirty python fails"                       $PY "$CC/scan_smells.py" "$FX/dirty.py"
expect 0 "clean python passes --fail-on warn"       $PY "$CC/scan_smells.py" "$FX/clean.py" --fail-on warn
expect 1 "dirty php fails"                          $PY "$CC/scan_smells.py" "$FX/dirty.php"
expect 0 "refactor compare passes"                  $PY "$CC/scan_smells.py" --compare "$FX/dirty.py" "$FX/clean.py"
expect 1 "reverse compare regresses"                $PY "$CC/scan_smells.py" --compare "$FX/clean.py" "$FX/dirty.py"
expect 0 "python syntax ok"                         sh "$CC/syntax_check.sh" "$FX/clean.py" "$FX/dirty.py"
printf 'def broken(:\n' > "$OUT/broken.py"
expect 1 "python syntax error caught"               sh "$CC/syntax_check.sh" "$OUT/broken.py"

echo "== text-humanizer"
expect 1 "AI draft exceeds gate"                    $PY "$TH/ai_tells.py" scan "$FX/ai_draft.txt" --max-score 20
expect 0 "human rewrite under gate"                 $PY "$TH/ai_tells.py" scan "$FX/human_rewrite.txt" --max-score 20
expect 0 "faithful rewrite preserves facts"         $PY "$TH/ai_tells.py" compare "$FX/ai_draft.txt" "$FX/human_rewrite.txt"
expect 1 "unfaithful rewrite caught"                $PY "$TH/ai_tells.py" compare "$FX/ai_draft.txt" "$FX/bad_rewrite.txt"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
