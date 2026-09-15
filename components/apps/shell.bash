# Native Bash refresh: one small file read per prompt, no palette subprocess.
_atlas_theme_refresh() {
  local revision
  if IFS= read -r revision < "$HOME/.config/atlas/revision" 2>/dev/null &&
     [[ $revision != ${_ATLAS_REVISION:-} ]]; then
    source "$HOME/.config/atlas/terminal-colors.bash"
    source "$HOME/.config/atlas/palette.bash"
    _ATLAS_REVISION=$revision
  fi
}
_atlas_theme_refresh
if [[ ! ${_ATLAS_PROMPT_HOOK:-} ]]; then
  # Bash treats a scalar as element zero when append syntax promotes it to array.
  PROMPT_COMMAND+=(_atlas_theme_refresh)
  _ATLAS_PROMPT_HOOK=1
fi
