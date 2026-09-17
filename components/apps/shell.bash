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

# Observe interactive Codex sessions in this tmux pane. Keep custom functions/aliases
# intact; command codex remains an explicit bypass. The launcher execs Codex
# with its original arguments, terminal, process group and exit behavior.
if ! declare -F codex >/dev/null && ! alias codex >/dev/null 2>&1 && command -v atlas-agents >/dev/null 2>&1; then
  function codex {
    local atlas_codex_binary
    atlas_codex_binary=$(type -P codex) || return
    if [[ -n ${TMUX:-} && -t 0 && -t 1 && ${ATLAS_AGENTS_AUTO:-1} != 0 ]]; then
      command atlas-agents launch -- "$atlas_codex_binary" "$@"
    else
      command "$atlas_codex_binary" "$@"
    fi
  }
fi
