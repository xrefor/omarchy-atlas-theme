function promptLooksFingerprint(text) {
  var s = String(text || "").toLowerCase()
  return /\bfingerprint\b|\bfprintd?\b/.test(s)
    || /\bfinger\b.*\b(reader|sensor)\b/.test(s)
    || /\b(place|touch|swipe|scan)\b.*\bfinger\b/.test(s)
}

function fingerprintConfiguredFromPamConfig(raw) {
  // Fingerprint is available whenever pam_fprintd appears anywhere in the auth
  // stack — it need not be the first module. A clamshell gate (pam_exec) may
  // legitimately precede it to skip fingerprint while the lid is closed.
  // Strip comments before joining continuations: a backslash inside a comment
  // does not continue that comment onto the next physical line.
  var physical = String(raw || "").split(/\r?\n/)
  var lines = []
  var current = ""
  for (var p = 0; p < physical.length; p++) {
    var part = physical[p].replace(/#.*/, "")
    var continued = /\\\s*$/.test(part)
    if (continued) part = part.replace(/\\\s*$/, "")
    part = part.replace(/^\s+|\s+$/g, "")
    if (part) current += (current ? " " : "") + part
    if (!continued) {
      if (current) lines.push(current)
      current = ""
    }
  }
  if (current) lines.push(current)

  for (var i = 0; i < lines.length; i++) {
    // pam.d rules are: type, control, module-path, then arguments. The control
    // may be a bracketed expression containing spaces.
    var rule = lines[i].match(/^-?auth\s+(.+)$/i)
    if (!rule) continue
    var rest = rule[1].replace(/^\s+|\s+$/g, "")
    if (rest.charAt(0) === "[") {
      var close = rest.indexOf("]")
      if (close === -1) continue
      rest = rest.slice(close + 1).replace(/^\s+/, "")
    } else {
      var simple = rest.match(/^\S+\s+(.+)$/)
      if (!simple) continue
      var control = rest.match(/^(\S+)/)[1].toLowerCase()
      // include/substack name another PAM service rather than a module.
      if (control === "include" || control === "substack") continue
      rest = simple[1]
    }
    var module = rest.match(/^(\S+)/)
    if (!module) continue
    var pathParts = module[1].split("/")
    if (pathParts[pathParts.length - 1] === "pam_fprintd.so") return true
  }
  return false
}

function authorizationLabel(message) {
  var text = String(message || "")
  var match = text.match(/^Authentication is (?:needed|required) to run [`']([^`'\r\n]+)[`'] as ([^\r\n]+)$/i)
  if (match && match[0].length === text.length) return "Authorize running '" + match[1] + "' as " + match[2]
  var manage = text.match(/^Authentication is (?:needed|required) to (start|stop|restart|reload) (?:the )?['`]?([^'`\r\n]+?)['`]?$/i)
  if (manage && manage[0].length === text.length) {
    var action = manage[1].toLowerCase()
    var gerund = action === "stop" ? "stopping" : action === "start" ? "starting" : action === "reload" ? "reloading" : "restarting"
    return "Authorize " + gerund + " '" + manage[2].replace(/\.service$/, "") + "'"
  }
  return text
}

if (typeof module !== "undefined") {
  module.exports = {
    promptLooksFingerprint: promptLooksFingerprint,
    fingerprintConfiguredFromPamConfig: fingerprintConfiguredFromPamConfig,
    authorizationLabel: authorizationLabel
  }
}
