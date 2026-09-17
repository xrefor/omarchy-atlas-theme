#!/usr/bin/env bash
# Install only the read-only palette resolver required by portable tests.
set -euo pipefail

if [[ $# != 1 || -z $1 ]]; then
  echo "Usage: tools/ci-deps.sh <temporary-bin-directory>" >&2
  exit 2
fi

atlas_ci_bin=$1
mkdir -p "$atlas_ci_bin"
atlas_ci_download=$(mktemp "$atlas_ci_bin/.omarchy-theme-color.XXXXXX")
trap 'rm -f "$atlas_ci_download"' EXIT
# Omarchy v4.0.4; the same resolver used for reference-workstation validation.
curl --fail --silent --show-error --location --retry 3 \
  https://raw.githubusercontent.com/omacom/omarchy/c668141e9c42b13c80c9ca4ea108e11708c5e8a5/bin/omarchy-theme-color \
  --output "$atlas_ci_download"
printf '%s  %s\n' a429ed1b18114ff3e784fc4479c6b829e9effb64c0f9d22d3b15eda4c62d86b5 "$atlas_ci_download" | sha256sum --check --status
chmod 755 "$atlas_ci_download"
mv "$atlas_ci_download" "$atlas_ci_bin/omarchy-theme-color"
echo "Prepared Omarchy v4.0.4 palette resolver in $atlas_ci_bin"
