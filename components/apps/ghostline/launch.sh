#!/usr/bin/env bash
set -euo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -- "$(dirname -- "${script_path}")" && pwd)"
workspace="${ATLAS_GHOSTLINE_WORKSPACE:-2}"
roles=(core wireless fusion graph sre access)
action="${1:-start}"

usage() {
  printf 'Usage: ghostline [start|stop]\n'
  printf '       ghostline kill        # backwards-compatible alias for stop\n'
}

if ! [[ "${workspace}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'ATLAS GHOSTLINE requires a positive numeric workspace.\n' >&2
  exit 1
fi
if (( $# > 1 )); then
  usage >&2
  exit 2
fi
case "${action}" in
  start) ;;
  stop|kill) action="stop" ;;
  help|-h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

runtime_root="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [[ "${runtime_root}" != /* || ! -d "${runtime_root}" || -L "${runtime_root}" || ! -O "${runtime_root}" ]]; then
  printf 'ATLAS GHOSTLINE requires a private user runtime directory.\n' >&2
  exit 1
fi
state_dir="${runtime_root}/atlas-ghostline"
if [[ -L "${state_dir}" ]]; then
  printf 'ATLAS GHOSTLINE refuses a linked runtime state directory.\n' >&2
  exit 1
fi
install -d -m 0700 -- "${state_dir}"
if [[ ! -d "${state_dir}" || ! -O "${state_dir}" ]]; then
  printf 'ATLAS GHOSTLINE could not secure its runtime state directory.\n' >&2
  exit 1
fi
director_pid_file="${state_dir}/director-${workspace}.pid"

director_matches() {
  local candidate_pid="$1" candidate_command
  [[ "${candidate_pid}" =~ ^[1-9][0-9]*$ && -r "/proc/${candidate_pid}/cmdline" ]] || return 1
  candidate_command="$(tr '\0' ' ' <"/proc/${candidate_pid}/cmdline")"
  [[ "${candidate_command}" == *"${script_dir}/ghostline_director.py"* && "${candidate_command}" == *"--workspace ${workspace}"* ]]
}

# Stop only a previously recorded director whose command line matches this
# exact installation and workspace.
stop_director() {
  local old_director_pid
  if [[ -r "${director_pid_file}" ]]; then
    old_director_pid="$(<"${director_pid_file}")"
    if director_matches "${old_director_pid}"; then
      kill -TERM "${old_director_pid}" 2>/dev/null || true
      for _ in {1..30}; do
        director_matches "${old_director_pid}" || break
        sleep 0.1
      done
      # A one-command stop must not leave the scheduler alive. Escalate only
      # after revalidating the exact installation, workspace, PID and command.
      if director_matches "${old_director_pid}"; then
        kill -KILL "${old_director_pid}" 2>/dev/null || true
        for _ in {1..10}; do
          director_matches "${old_director_pid}" || break
          sleep 0.1
        done
      fi
      if director_matches "${old_director_pid}"; then
        printf 'Could not stop the GHOSTLINE director (PID %s).\n' "${old_director_pid}" >&2
        return 1
      fi
    fi
  fi
}

stop_director

if [[ "${action}" == "stop" ]]; then
  # Close only verified GHOSTLINE clients on the configured workspace. Using
  # compositor addresses avoids broad process-name kills and PID reuse races.
  mapfile -t ghostline_clients < <(hyprctl -j clients | jq -r --argjson workspace "${workspace}" \
    '.[] | select(.workspace.id == $workspace and .mapped == true and .pinned == false and (.class | startswith("atlas-ghostline-"))) | @base64')
  for encoded in "${ghostline_clients[@]}"; do
    client="$(base64 --decode <<<"${encoded}")"
    address="$(jq -r '.address' <<<"${client}")"
    pid="$(jq -r '.pid' <<<"${client}")"
    class="$(jq -r '.class' <<<"${client}")"
    valid="$(hyprctl -j clients | jq -r \
      --arg address "${address}" --arg class "${class}" --argjson pid "${pid}" --argjson workspace "${workspace}" \
      'any(.[]; .address == $address and .pid == $pid and .class == $class and .workspace.id == $workspace and .mapped == true and .pinned == false and (.class | startswith("atlas-ghostline-")))')"
    if [[ "${valid}" == "true" ]]; then
      hyprctl dispatch "hl.dsp.window.close({ window = \"address:${address}\" })" >/dev/null
    fi
  done

  for _ in {1..30}; do
    remaining="$(hyprctl -j clients | jq --argjson workspace "${workspace}" \
      '[.[] | select(.workspace.id == $workspace and .mapped == true and .pinned == false and (.class | startswith("atlas-ghostline-")))] | length')"
    [[ "${remaining}" == "0" ]] && break
    sleep 0.1
  done
  if [[ "${remaining}" != "0" ]]; then
    printf 'Could not close %s GHOSTLINE window(s).\n' "${remaining}" >&2
    exit 1
  fi
  printf 'ATLAS GHOSTLINE stopped.\n'
  exit 0
fi

if ! command -v alacritty >/dev/null 2>&1; then
  printf 'ATLAS GHOSTLINE requires alacritty.\n' >&2
  exit 1
fi

hyprctl dispatch "hl.dsp.focus({ workspace = \"${workspace}\" })" >/dev/null
active_workspace="$(hyprctl -j activeworkspace | jq -r '.id')"
if [[ "${active_workspace}" != "${workspace}" ]]; then
  printf 'Could not acquire workspace %s.\n' "${workspace}" >&2
  exit 1
fi

# Take over only this exact workspace. Revalidate each snapshotted client
# immediately before asking it to close; never kill by process or class name.
mapfile -t existing < <(hyprctl -j clients | jq -r --argjson workspace "${workspace}" \
  '.[] | select(.workspace.id == $workspace and .mapped == true and .pinned == false) | @base64')
for encoded in "${existing[@]}"; do
  client="$(base64 --decode <<<"${encoded}")"
  address="$(jq -r '.address' <<<"${client}")"
  pid="$(jq -r '.pid' <<<"${client}")"
  class="$(jq -r '.class' <<<"${client}")"
  valid="$(hyprctl -j clients | jq -r \
    --arg address "${address}" --arg class "${class}" --argjson pid "${pid}" --argjson workspace "${workspace}" \
    'any(.[]; .address == $address and .pid == $pid and .class == $class and .workspace.id == $workspace and .mapped == true and .pinned == false)')"
  if [[ "${valid}" == "true" ]]; then
    hyprctl dispatch "hl.dsp.window.close({ window = \"address:${address}\" })" >/dev/null
  fi
done

for _ in {1..20}; do
  remaining="$(hyprctl -j clients | jq --argjson workspace "${workspace}" \
    '[.[] | select(.workspace.id == $workspace and .mapped == true and .pinned == false)] | length')"
  [[ "${remaining}" == "0" ]] && break
  sleep 0.1
done
if [[ "${remaining}" != "0" ]]; then
  printf 'Workspace %s still contains %s window(s); takeover aborted.\n' "${workspace}" "${remaining}" >&2
  exit 1
fi

start="$(( $(date +%s) + 8 ))"
declare -A addresses=()
launch_complete=false

cleanup_failed_launch() {
  status=$?
  if [[ "${launch_complete}" != "true" ]]; then
    for role in "${!addresses[@]}"; do
      address="${addresses[$role]}"
      hyprctl dispatch "hl.dsp.window.close({ window = \"address:${address}\" })" >/dev/null 2>&1 || true
    done
  fi
  return "${status}"
}
trap cleanup_failed_launch EXIT
trap 'exit 130' INT TERM

for role in "${roles[@]}"; do
  title="ATLAS GHOSTLINE // ${role^^}"
  if command -v bwrap >/dev/null 2>&1; then
    command_parts=(alacritty --class "atlas-ghostline-${role}" --title "${title}"
      -o font.size=9.0 -o window.opacity=0.96 -o window.padding.x=8 -o window.padding.y=8 -e
      bwrap --unshare-net --die-with-parent --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp
      --clearenv --setenv HOME /tmp --setenv TERM xterm-256color --setenv LANG C.UTF-8
      /usr/bin/python3 -I -u "${script_dir}/atlas_ghostline.py" "${role}" --start "${start}")
  else
    command_parts=(alacritty --class "atlas-ghostline-${role}" --title "${title}"
      -o font.size=9.0 -o window.opacity=0.96 -o window.padding.x=8 -o window.padding.y=8 -e
      /usr/bin/python3 -I -u "${script_dir}/atlas_ghostline.py" "${role}" --start "${start}")
  fi
  printf -v command '%q ' "${command_parts[@]}"
  command_json="$(jq -Rn --arg command "${command% }" '$command')"
  hyprctl dispatch "hl.dsp.exec_cmd(${command_json})" >/dev/null

  address=""
  for _ in {1..50}; do
    address="$(hyprctl -j clients | jq -r --arg class "atlas-ghostline-${role}" --argjson workspace "${workspace}" \
      '.[] | select(.class == $class and .workspace.id == $workspace and .mapped == true) | .address' | head -n 1)"
    [[ -n "${address}" ]] && break
    sleep 0.1
  done
  if [[ -z "${address}" ]]; then
    printf 'Panel %s did not map; launch aborted.\n' "${role}" >&2
    exit 1
  fi
  addresses["${role}"]="${address}"
done

# Build a precise 3x2 operations wall on the focused monitor. All values are
# derived from its logical dimensions and reserved shell area.
monitor="$(hyprctl -j monitors | jq -c '.[] | select(.focused == true)')"
read -r monitor_x monitor_y monitor_width monitor_height left top right bottom < <(
  jq -r '
    (if ((.transform // 0) % 2) == 1 then [.height, .width] else [.width, .height] end) as $size
    | [.x, .y, ($size[0] / .scale | floor), ($size[1] / .scale | floor), .reserved[]]
    | @tsv
  ' <<<"${monitor}"
)
gap=10
cell_width=$(( (monitor_width - left - right - gap * 4) / 3 ))
cell_height=$(( (monitor_height - top - bottom - gap * 3) / 2 ))

for index in "${!roles[@]}"; do
  role="${roles[$index]}"
  column=$(( index % 3 ))
  row=$(( index / 3 ))
  x=$(( monitor_x + left + gap + column * (cell_width + gap) ))
  y=$(( monitor_y + top + gap + row * (cell_height + gap) ))
  target="address:${addresses[$role]}"
  hyprctl dispatch "hl.dsp.window.float({ action = \"enable\", window = \"${target}\" })" >/dev/null
  hyprctl dispatch "hl.dsp.window.resize({ x = ${cell_width}, y = ${cell_height}, relative = false, window = \"${target}\" })" >/dev/null
  hyprctl dispatch "hl.dsp.window.move({ x = ${x}, y = ${y}, relative = false, window = \"${target}\" })" >/dev/null
done

hyprctl dispatch "hl.dsp.focus({ window = \"address:${addresses[core]}\" })" >/dev/null

director_parts=(/usr/bin/python3 -I -u "${script_dir}/ghostline_director.py"
  --workspace "${workspace}" --start "${start}" --state-dir "${state_dir}")
printf -v director_command '%q ' "${director_parts[@]}"
director_json="$(jq -Rn --arg command "${director_command% }" '$command')"
hyprctl dispatch "hl.dsp.exec_cmd(${director_json})" >/dev/null

# Do not return before stop can identify the detached director. This closes a
# race where an immediate `ghostline stop` could arrive before the PID file.
director_ready=false
for _ in {1..50}; do
  if [[ -r "${director_pid_file}" ]]; then
    director_pid="$(<"${director_pid_file}")"
    if director_matches "${director_pid}"; then
      director_ready=true
      break
    fi
  fi
  sleep 0.1
done
if [[ "${director_ready}" != "true" ]]; then
  printf 'GHOSTLINE director did not become ready; launch aborted.\n' >&2
  exit 1
fi

launch_complete=true
trap - EXIT INT TERM
printf 'ATLAS GHOSTLINE running on workspace %s. Stop it with: ghostline stop\n' "${workspace}"
