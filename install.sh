#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage: ./install.sh [--dry-run] [--home PATH] [--offline] [--no-refresh]

Install all ATLAS user components and activate the theme. Boot appearance stays
separate. Use --dry-run to preview or --home PATH --offline for staging.
EOF
}

dry_run=false
staged=false
expect_home=false
for argument in "$@"; do
  if "$expect_home"; then
    [ -n "$argument" ] || { printf '%s\n' 'ATLAS: --home requires a path' >&2; exit 2; }
    case "$argument" in -*) printf '%s\n' 'ATLAS: --home requires a path' >&2; exit 2 ;; esac
    staged=true
    expect_home=false
    continue
  fi
  case "$argument" in
    --help|-h) usage; exit 0 ;;
    --dry-run) dry_run=true ;;
    --home) expect_home=true ;;
    --home=) printf '%s\n' 'ATLAS: --home requires a path' >&2; exit 2 ;;
    --home=*) staged=true ;;
    --offline) staged=true ;;
    --no-refresh) ;;
    *) printf 'ATLAS: unsupported installer option: %s\n' "$argument" >&2; usage >&2; exit 2 ;;
  esac
done
"$expect_home" && { printf '%s\n' 'ATLAS: --home requires a path' >&2; exit 2; }

[ "$(id -u)" -ne 0 ] || { printf '%s\n' 'ATLAS: run this installer as your normal user' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'ATLAS: python3 is required' >&2; exit 1; }

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$script_dir/install.py" doctor --all "$@"
if ! "$dry_run" && ! "$staged" && [ -t 0 ]; then
  python3 "$script_dir/lib/atlas/optional.py"
fi
python3 "$script_dir/install.py" --all "$@"

if ! "$dry_run" && ! "$staged"; then
  omarchy theme set atlas
  printf '%s\n' 'ATLAS is installed and active. Open a new terminal to load the workspace.'
  printf '%s\n' 'In Codex, use /theme to select ATLAS or ATLAS Readable for syntax highlighting.'
fi
