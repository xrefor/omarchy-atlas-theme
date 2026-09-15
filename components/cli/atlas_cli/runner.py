"""Color human-readable stdout without changing command arguments or files."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys

from .palette import RESET, fg, load_theme, want_color

APPS = {"nmap", "ping", "ip", "ss", "dig", "shodan"}
TOKEN = re.compile(
    r"(?P<address>(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d+)?(?![\w.])"
    r"|(?<![\w:])(?:[\da-fA-F]{0,4}:){2,}[\da-fA-F:.]*(?:%[\w.-]+)?(?:/\d+)?)"
    r"|(?P<latency>\btime[=<]\s*[\d.]+\s*ms)"
    r"|(?P<loss>\b[\d.]+% packet loss)"
    r"|(?P<warning>\b(?:open\|filtered|closed\|filtered|filtered|UNKNOWN|STALE|DELAY|TIME-WAIT|SYN-SENT|SYN-RECV|NXDOMAIN|REFUSED)\b)"
    r"|(?P<error>\b(?:closed|DOWN|FAILED|SERVFAIL|unreachable|Unreachable|ERROR|Error|error|failed|timed out)\b)"
    r"|(?P<success>\b(?:open|UP|LOWER_UP|REACHABLE|ESTAB|LISTEN|NOERROR)\b)"
    r"|(?P<port>\b\d+/(?:tcp|udp|sctp)\b)"
    r"|(?P<record>\b(?:IN|A|AAAA|CNAME|MX|NS|PTR|SOA|TXT|SRV|CAA|DNSKEY|RRSIG)\b)"
)
HEADINGS = {
    "nmap": re.compile(r"^(?:Starting Nmap|Nmap scan report for|PORT\s|Nmap done:)"),
    "ping": re.compile(r"^(?:PING |--- |rtt |round-trip )"),
    "ip": re.compile(r"^\d+: [^:]+:"),
    "ss": re.compile(r"^(?:Netid\s|State\s|Total:)"),
    "dig": re.compile(r"^;; (?:QUESTION|ANSWER|AUTHORITY|ADDITIONAL) SECTION:"),
    "tcpdump": re.compile(r"^(?:tcpdump:|\d+ packets (?:captured|received by filter|dropped by kernel))"),
    "shodan": re.compile(r"^(?:Shodan|IP|Hostnames|Organization|Ports|Vulnerabilities|Total Results)\b", re.I),
}


def colorize(app: str, text: str, colors: dict[str, str]) -> str:
    if "\x1b" in text:
        return text
    base = "heading" if HEADINGS[app].match(text) else "foreground"
    if app == "dig" and text.startswith(";;") and base != "heading":
        base = "secondary"

    def replace(match: re.Match[str]) -> str:
        role = match.lastgroup or "foreground"
        if role == "latency":
            value = float(re.search(r"[\d.]+", match[0])[0])
            role = "error" if value >= 200 else "warning" if value >= 50 else "success"
        elif role == "loss":
            role = "success" if float(match[0].split("%", 1)[0]) == 0 else "warning"
        elif role in ("port", "record"):
            role = "accent"
        return fg(colors, role) + match[0] + fg(colors, base)

    return fg(colors, base) + TOKEN.sub(replace, text) + RESET


def passthrough(app: str, args: list[str]) -> bool:
    """Bypass modes that produce structured, binary, or control-oriented output."""
    if app == "nmap":
        return any(arg.startswith(("-o", "--resume", "--webxml", "--stylesheet", "--no-stylesheet")) for arg in args)
    if app == "ip":
        return "exec" in args or any(
            arg.startswith(("-j", "-c", "--json", "--batch", "--color"))
            or (arg.startswith("-b") and not arg.startswith("-br"))
            for arg in args
        )
    if app == "ss":
        return any(
            arg.startswith(("--diag", "-D"))
            or (arg.startswith("-") and not arg.startswith("--") and "D" in arg[1:])
            for arg in args
        )
    if app == "ping":
        return any(arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:] for arg in args)
    if app == "dig":
        return any(
            arg.startswith("+")
            and any(option.startswith(arg[1:].split("=", 1)[0].lower()) for option in ("short", "yaml"))
            for arg in args
        )
    if app == "shodan":
        machine_flags = ("--json", "--raw", "--fields", "--separator")
        # init may prompt without a newline; piping it would hide the prompt.
        machine_commands = {"convert", "download", "init", "parse"}
        return bool(args and args[0] in machine_commands) or any(
            arg == flag or arg.startswith(flag + "=") for arg in args for flag in machine_flags
        )
    return False


def run_colored(command: list[str], app: str, colors: dict[str, str]) -> int:
    if os.path.exists("/usr/bin/stdbuf"):
        command = ["/usr/bin/stdbuf", "-oL", *command]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    handlers = {}

    def forward(signum, _frame):
        if process.poll() is None:
            try:
                process.send_signal(signum)
            except ProcessLookupError:
                pass

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        handlers[signum] = signal.signal(signum, forward)
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            rendered = colorize(app, raw.decode("utf-8", "surrogateescape"), colors)
            sys.stdout.buffer.write(rendered.encode("utf-8", "surrogateescape"))
            sys.stdout.buffer.flush()
    except BrokenPipeError:
        process.terminate()
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
    finally:
        if process.stdout is not None:
            process.stdout.close()
        code = process.wait()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    if code < 0:
        signum = -code
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    return code


def main(app: str) -> int:
    if app not in APPS:
        return 127
    real = "/usr/bin/" + app
    args = sys.argv[1:]
    if not os.path.exists(real):
        print(f"{app}: {real} is not installed", file=sys.stderr)
        return 127
    mode = os.environ.get("ATLAS_COLOR", "auto")
    if not want_color(mode) or passthrough(app, args):
        os.execv(real, [real, *args])
    try:
        return run_colored([real, *args], app, load_theme())
    except OSError as error:
        print(f"{app}: {error}", file=sys.stderr)
        return 127
