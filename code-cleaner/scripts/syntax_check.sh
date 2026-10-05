#!/usr/bin/env sh
# Syntax-check files with the language's own toolchain when it is installed.
# Python is always available (py_compile); php -l, node --check and tsc --noEmit
# are used when present and skipped with a notice otherwise.
#
# Usage: syntax_check.sh FILE [FILE...]
# Exit codes: 0 = all checked files valid, 1 = syntax error(s), 2 = usage error.
set -u
[ $# -ge 1 ] || { echo "usage: $0 FILE [FILE...]" >&2; exit 2; }

status=0
for f in "$@"; do
  [ -f "$f" ] || { echo "MISSING $f"; status=1; continue; }
  case $f in
    *.py)
      if python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read(), sys.argv[1])' "$f" 2>/tmp/.syntax_err.$$; then
        echo "OK      $f"
      else
        echo "INVALID $f: $(tail -1 /tmp/.syntax_err.$$)"; status=1
      fi ;;
    *.php)
      if command -v php >/dev/null 2>&1; then
        out=$(php -l "$f" 2>&1) && echo "OK      $f" || { echo "INVALID $f: $out"; status=1; }
      else echo "SKIP    $f (php not installed)"; fi ;;
    *.js|*.mjs|*.cjs)
      if command -v node >/dev/null 2>&1; then
        out=$(node --check "$f" 2>&1) && echo "OK      $f" || { echo "INVALID $f: $(echo "$out" | head -5)"; status=1; }
      else echo "SKIP    $f (node not installed)"; fi ;;
    *.ts|*.tsx)
      if command -v tsc >/dev/null 2>&1; then
        out=$(tsc --noEmit --skipLibCheck --strict "$f" 2>&1) && echo "OK      $f" || { echo "INVALID $f: $(echo "$out" | head -5)"; status=1; }
      else echo "SKIP    $f (tsc not installed)"; fi ;;
    *.sh)
      if sh -n "$f" 2>/tmp/.syntax_err.$$; then echo "OK      $f"; else echo "INVALID $f: $(cat /tmp/.syntax_err.$$)"; status=1; fi ;;
    *.json)
      if python3 -m json.tool "$f" >/dev/null 2>/tmp/.syntax_err.$$; then echo "OK      $f"; else echo "INVALID $f: $(cat /tmp/.syntax_err.$$)"; status=1; fi ;;
    *) echo "SKIP    $f (no checker for this extension)" ;;
  esac
done
rm -f /tmp/.syntax_err.$$
exit $status
