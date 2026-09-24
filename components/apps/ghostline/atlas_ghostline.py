#!/usr/bin/env python3
"""ATLAS GHOSTLINE display-only advanced-operations sequence.

The renderer is intentionally inert: it opens no sockets, invokes no tools,
reads no host data, and uses reserved addresses plus locally administered MACs.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import shutil
import signal
import sys
import time
from collections import deque
from datetime import datetime


BG = "\x1b[48;2;16;14;12m"
FG = "\x1b[38;2;214;207;196m"
BRIGHT = "\x1b[38;2;242;235;224m"
MUTED = "\x1b[38;2;110;103;92m"
ORANGE = "\x1b[38;2;255;90;18m"
AMBER = "\x1b[38;2;240;162;2m"
GREEN = "\x1b[38;2;168;184;92m"
CYAN = "\x1b[38;2;143;184;176m"
BLUE = "\x1b[38;2;138;168;188m"
RESET = "\x1b[0m"
ANSI_RE = re.compile(r"(\x1b\[[0-9;?]*[ -/]*[@-~])")

ROLE_NAMES = {
    "core": "MISSION CONTROL",
    "wireless": "RF ACCESS",
    "fusion": "SIGNAL FUSION",
    "graph": "SELECTOR GRAPH",
    "sre": "BINARY ANALYSIS",
    "access": "ACCESS FABRIC",
}

PHASES = [
    (0, 8, "00", "COLD START"),
    (8, 25, "01", "RF DISCOVERY"),
    (25, 42, "02", "KEY RECOVERY"),
    (42, 61, "03", "SIGNAL FUSION"),
    (61, 80, "04", "BINARY LIFT"),
    (80, 101, "05", "ACCESS ORCHESTRATION"),
    (101, 116, "06", "OBJECTIVE SECURED"),
]
SEQUENCE_LENGTH = PHASES[-1][1]

IPS = [
    "192.0.2.14", "192.0.2.44", "198.51.100.17", "198.51.100.82",
    "203.0.113.9", "203.0.113.71", "203.0.113.208",
]
MACS = [
    "02:1A:7C:91:4E:20", "02:4F:B2:11:6D:A8", "02:70:39:CC:21:07",
    "02:88:A1:5E:90:3B", "02:B4:20:63:19:D2",
]

EVENTS = [
    (0, "init", "loading operation profile CINDER VEIL"),
    (2, "trust", "sealed workspace acquired"),
    (5, "mesh", "relay fabric standing by"),
    (8, "rf", "wideband survey started"),
    (12, "rf", "candidate infrastructure isolated"),
    (17, "rf", "802.11 management plane mapped"),
    (23, "rf", "authentication exchange observed"),
    (25, "key", "recovery workers dispatched"),
    (31, "key", "pairwise key material ranked"),
    (38, "key", "transport key recovered"),
    (42, "flow", "collection stream admitted"),
    (47, "flow", "protocols normalized and enriched"),
    (52, "graph", "selector graph converging"),
    (58, "graph", "infrastructure cluster resolved"),
    (61, "sre", "binary lift assigned to analysis grid"),
    (67, "sre", "P-code control flow recovered"),
    (74, "sre", "callback state machine identified"),
    (80, "access", "access package staged"),
    (86, "access", "route mutation accepted"),
    (92, "access", "distributed tasking synchronized"),
    (98, "access", "objective channel established"),
    (101, "done", "mission objective secured"),
    (108, "done", "evidence sealed / volatile state retiring"),
]

ACTIVITY = {
    "core": [
        "scheduler :: worker-{n:02d} acknowledged phase task",
        "control   :: epoch {token} committed to audit chain",
        "relay     :: heartbeat {latency}ms / variance {jitter}ms",
        "policy    :: release gate {n:02d} returned ALLOW",
        "mission   :: objective vector recalculated / score {score}",
        "crypto    :: ephemeral channel 0x{token} rotated",
    ],
    "wireless": [
        "survey    :: channel {channel} occupancy {percent}%",
        "bearing   :: emitter 02:{token}:7C triangulated ±{jitter}°",
        "frame     :: beacon sequence {n:04d} classified",
        "spectrum  :: burst at 5.{channel} GHz / width 80 MHz",
        "handshake :: message {msg}/4 retained / replay 0",
        "rf-model  :: modulation signature confidence {score}",
    ],
    "fusion": [
        "nifi      :: flowfile {token} routed → normalize",
        "datawave  :: shard {n:02d} committed / lag {latency}ms",
        "decoder   :: protocol family {proto} confidence {score}",
        "enrich    :: selector attributes +{msg} / conflicts 0",
        "index     :: mutation {token} propagated to 6 nodes",
        "stream    :: {percent}k records/s / backpressure 0",
    ],
    "graph": [
        "edge      :: device:7C20 → session:{token} weight {score}",
        "query     :: intersection returned {n} candidates",
        "resolve   :: cluster ORPHEUS merged +{msg} observations",
        "temporal  :: window Δ{latency}ms / confidence {score}",
        "selector  :: EMBER/{token} fanout {n}",
        "graph     :: revision {n:04d} sealed / orphan count 0",
    ],
    "sre": [
        "analyzer  :: function FUN_0040{token} lifted",
        "p-code    :: block {n:03d} SSA transform complete",
        "xref      :: callback_dispatch ← {msg} callers",
        "decompile :: type propagation {percent}%",
        "symbol    :: thunk_{token} renamed route_commit",
        "cfg       :: edge {n:03d} dominance resolved",
    ],
    "access": [
        "broker    :: task {token} leased to RELAY-{msg}",
        "route     :: {ip} → {next_ip} / {latency}ms",
        "identity  :: service token 0x{token} accepted",
        "fabric    :: node {n:02d} state synchronized",
        "channel   :: frame {n:04d} authenticated / ack {msg}",
        "mutation  :: egress path advanced / trust {percent}",
    ],
}


def colour(text: str, code: str) -> str:
    return f"{code}{text}{FG}"


def fit(text: str, width: int) -> str:
    remaining = max(1, width - 1)
    output: list[str] = []
    for part in ANSI_RE.split(text):
        if not part:
            continue
        if part.startswith("\x1b["):
            output.append(part)
            continue
        chunk = part[:remaining]
        output.append(chunk)
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return "".join(output) + FG + "\x1b[K"


def phase_at(elapsed: float) -> tuple[int, int, str, str, float]:
    position = elapsed % SEQUENCE_LENGTH
    for index, (start, end, number, name) in enumerate(PHASES):
        if start <= position < end:
            progress = (position - start) / (end - start)
            return index, number, name, f"{int(position):03d}", progress
    return 0, "00", "COLD START", "000", 0.0


def phase_bar(progress: float, width: int = 24) -> str:
    used = max(0, min(width, round(progress * width)))
    return f"{ORANGE}{'━' * used}{MUTED}{'─' * (width - used)}{FG}"


def activity_line(role: str, rng: random.Random, tick: int) -> str:
    template = rng.choice(ACTIVITY[role])
    values = {
        "n": (tick * 7 + rng.randrange(1, 97)) % 4096,
        "token": f"{rng.randrange(0x1000, 0xFFFF):04X}",
        "latency": rng.randrange(7, 89),
        "jitter": rng.randrange(1, 9),
        "score": f"{rng.uniform(0.901, 0.999):.3f}",
        "percent": rng.randrange(31, 99),
        "channel": rng.choice([36, 44, 100, 116, 149, 157]),
        "msg": rng.randrange(1, 9),
        "proto": rng.choice(["TLS", "QUIC", "802.11", "DNS", "CINDER/4"]),
        "ip": rng.choice(IPS),
        "next_ip": rng.choice(IPS),
    }
    marker = colour("●", ORANGE if tick % 5 == 0 else GREEN)
    return f" {MUTED}{datetime.now().strftime('%H:%M:%S')}.{tick % 1000:03d}{FG} {marker} {template.format(**values)}"


def activity_block(history: deque[str], room: int, tick: int) -> list[str]:
    if room < 3:
        return []
    pulse = "SCANNING" if tick % 8 < 4 else "CORRELATING"
    lines = ["", f" {ORANGE}LIVE TASK STREAM{FG}  {MUTED}[{pulse}]{FG}"]
    lines.extend(list(history)[-max(1, room - 2):])
    return lines[:room]


def header(role: str, width: int, elapsed: float) -> list[str]:
    _, number, phase, timer, progress = phase_at(elapsed)
    rule = "─" * max(8, width - 1)
    return [
        f"{ORANGE} ATLAS // GHOSTLINE{FG}  {BRIGHT}{ROLE_NAMES[role]}{FG}",
        f" {MUTED}OPERATION CINDER VEIL // TACTICAL SYSTEMS{FG}  {ORANGE}PHASE {number}{FG} / {BRIGHT}{phase}{FG}",
        f" {MUTED}{datetime.now().strftime('%H:%M:%S')}  T+{timer}s{FG}  {phase_bar(progress)}",
        f"{MUTED}{rule}{FG}",
    ]


def core_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    position = elapsed % SEQUENCE_LENGTH
    out = [f" {ORANGE}OPERATION EVENT STREAM{FG}", ""]
    visible = [(at, source, text) for at, source, text in EVENTS if at <= position]
    rows = max(6, height - 13)
    for at, source, text in visible[-rows:]:
        pulse = ORANGE if int(position) - at < 2 else GREEN
        out.append(f" {MUTED}T+{at:03d}{FG} {colour('[+]', pulse)} {source:<7} :: {text}")
    phase_index, _, phase, _, progress = phase_at(elapsed)
    out += [
        "",
        f" {ORANGE}━━ EXECUTION ENVELOPE{FG}",
        f" phase         {phase}",
        f" completion    {phase_bar(progress, 32)} {int(progress * 100):>3}%",
        f" task fabric   {GREEN}{4 + min(phase_index, 4)}/8 ACTIVE{FG}",
        f" audit chain   {GREEN}SEALED{FG}",
        f" mission grid  63T WK 2198 4471 / cell KILO-7",
        f" sensor net    {ORANGE}{6 + phase_index:02d} TRACKS{FG} / authority gate {GREEN}VALID{FG}",
    ]
    if phase_index == len(PHASES) - 1:
        out += ["", f" {GREEN}OBJECTIVE SECURED // CINDER VEIL{FG}"]
    return out


def wireless_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    phase_index, _, _, _, progress = phase_at(elapsed)
    out = [f" {ORANGE}RF OPERATIONS{FG}  {MUTED}// tactical spectrum / sector KILO-7{FG}", ""]
    if phase_index == 0:
        out += [
            f" {MUTED}phy0{FG}  calibrating channel geometry",
            f" {MUTED}phy1{FG}  synchronizing observation clock",
            f" {MUTED}dsp{FG}   loading spectral classifier",
            "",
            f" {ORANGE}{'▁▂▃▅▆▃▂▁' * 7}{FG}",
        ]
    elif phase_index == 1:
        out += [
            f" {ORANGE}AIRCRACK // DISCOVERY ENGINE{FG}  {MUTED}CAPTURE 149 / 80 MHz{FG}",
            "",
            f" {MUTED}BSSID             PWR  BEACONS  DATA   CH  ENC   ESSID{FG}",
        ]
        names = ["ORPHEUS-MESH", "OPS-TRANSIT", "FACILITY-7", "UMBRA-LINK", "CINDER-GUEST"]
        for i, (mac, name) in enumerate(zip(MACS, names)):
            selected = i == min(2, int(progress * 3))
            c = ORANGE if selected else FG
            out.append(f" {colour(mac, c)}  {-31-i*7:>3}  {210+i*87:>7}  {tick*9+i*31:>5}  {149-i*4:>3}  WPA3  {colour(name, c)}")
        out += ["", f" {MUTED}STATION            BSSID             RATE       FRAMES{FG}"]
        for i in range(4):
            out.append(f" {MACS[(i+1)%len(MACS)]}  {MACS[i]}  866.7e-6e  {80 + tick*3 + i*17:>6}")
    elif phase_index == 2:
        keys = 160000 + int(progress * 3_840_000)
        rate = 712 + int(90 * math.sin(tick / 5))
        out += [
            f" {ORANGE}AIRCRACK // RECOVERY ENGINE{FG}  {MUTED}LEXICON CINDER / SLOT 9E{FG}",
            "",
            f" {BRIGHT}Aircrack-ng 1.7{FG}",
            "",
            f"        [{datetime.now().strftime('%H:%M:%S')}] {keys:,} keys tested ({rate:.1f} k/s)",
            "",
            f"        Time left: {max(0, int((1-progress)*17)):02d} seconds",
            f"        Candidate vector: {rng.choice(['ember-array', 'vector-cinder', 'orange-veil', 'vault-spine'])}-{tick%97:02d}",
            "",
            f"        Master Key     {ORANGE}8A 31 7F 2C 99 10 44 C8{FG}",
            f"        Transient Key  {MUTED}74 A0 18 E3 5B 22 11 90{FG}",
        ]
        if progress > 0.72:
            out += ["", f"        {GREEN}KEY MATERIAL ACCEPTED // SLOT CINDER-9E{FG}"]
    else:
        out += [
            f" {GREEN}CHANNEL ACCESS MAINTAINED{FG}", "",
            f" BSSID       {MACS[0]}",
            f" ESSID       ORPHEUS-MESH",
            f" cipher      GCMP-256",
            f" session     0xA71C3E",
            "",
            f" {ORANGE}SPECTRAL OCCUPANCY{FG}",
        ]
        for channel in range(145, 166, 4):
            strength = (channel + tick) % 10 + 8
            out.append(f" CH {channel}  {ORANGE}{'█' * strength}{MUTED}{'░' * (22-strength)}{FG}  {-92+strength*3:>3} dBm")
    return out


def fusion_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    phase_index, _, _, _, progress = phase_at(elapsed)
    out = [f" {ORANGE}SIGNAL FUSION{FG}  {MUTED}// sensor tasking · process · analyze{FG}", ""]
    stages = [
        ("COLLECT", "RF / IP / telemetry"),
        ("NIFI", "flow control + provenance"),
        ("NORMALIZE", "protocol lift / schema"),
        ("DATAWAVE", "distributed ingest + query"),
        ("ENRICH", "selectors / language / geo"),
        ("DISSEMINATE", "mission channels"),
    ]
    active = min(len(stages) - 1, max(0, phase_index - 1))
    for i, (name, detail) in enumerate(stages):
        if i < active:
            state, c = "COMMITTED", GREEN
        elif i == active:
            state, c = "STREAMING", ORANGE
        else:
            state, c = "STANDBY", MUTED
        out.append(f" {colour(f'{i+1:02d}', c)}  {name:<12} {detail:<30} {colour(state, c)}")
        if i < len(stages) - 1:
            out.append(f" {MUTED} │{FG}")
    out += ["", f" {ORANGE}INGEST FABRIC{FG}", f" {MUTED}FLOW        RATE       LAG   CLASSIFIER       STATE{FG}"]
    flows = ["rf.80211", "tls.meta", "dns.graph", "voice.sig", "device.fp", "binary.obj"]
    for i, flow in enumerate(flows[:max(2, height - len(out) - 2)]):
        rate = 1.4 + abs(math.sin((tick + i) / 7)) * 18
        state = colour("indexed", GREEN) if phase_index >= 3 else colour("buffering", AMBER)
        out.append(f" {flow:<11} {rate:>5.1f}k/s  {rng.randrange(2,39):>3}ms  model-{12+i:<8} {state}")
    return out


def graph_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    phase_index, _, _, _, progress = phase_at(elapsed)
    out = [f" {ORANGE}LEMONGRAPH // TACTICAL ENTITY RESOLUTION{FG}", ""]
    graph = [
        "                  ┌── device:7C20 ──┐",
        " selector:EMBER ──┤                 ├── infra:ORPHEUS",
        "        │         └── account:K-17 ─┘        │",
        "        │                   │                │",
        "   location:SECTOR-7 ── session:A71C3E ── endpoint:440",
        "                            │",
        "                     binary:4E91B2",
    ]
    for i, line in enumerate(graph):
        c = ORANGE if (tick // 2 + i) % 7 == 0 else (CYAN if i % 2 else GREEN)
        out.append(" " + colour(line, c))
    out += ["", f" {ORANGE}SELECTOR QUERY{FG}",
            f" {MUTED}DATAWAVE / shard scan / attribute intersection{FG}", ""]
    selectors = [
        ("device.fp", "7c20:cc19", 0.998),
        ("account", "kestrel-17", 0.974),
        ("infrastructure", "orpheus-mesh", 0.961),
        ("protocol", "cinder/4", 0.933),
        ("location", "sector-07", 0.907),
    ]
    revealed = max(1, min(len(selectors), phase_index - 1 if phase_index > 2 else 1))
    for kind, value, score in selectors[:revealed]:
        out.append(f" {colour('MATCH', GREEN)}  {kind:<16} {value:<20} confidence {score:.3f}")
    out += ["", f" cluster confidence  {phase_bar(min(1.0, 0.18 + phase_index * 0.14), 30)}"]
    return out


def sre_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    phase_index, _, _, _, progress = phase_at(elapsed)
    out = [f" {ORANGE}GHIDRA SRE // P-CODE LIFT{FG}  {MUTED}sample 4e91b2{FG}", ""]
    if phase_index < 4:
        out += [
            f" {MUTED}analysis grid waiting for object transfer{FG}", "",
            f" image base    00400000",
            f" language      x86:LE:64:default",
            f" compiler      gcc",
            f" sha256        4e91b2…7ac0",
            "",
            f" {phase_bar(min(0.96, phase_index * 0.21), 38)}",
        ]
    else:
        out += [
            f" {MUTED}FUNCTION            XREFS  SIZE  CLASS{FG}",
            f" FUN_00401180           9   0x9a  transport_init",
            f" {ORANGE}FUN_00401240{FG}          17   0xe4  callback_dispatch",
            f" FUN_00401388           4   0x72  policy_gate",
            f" FUN_00401410          12   0xbc  route_mutate",
            "",
            f" {ORANGE}DECOMPILER // callback_dispatch{FG}",
            f" {BLUE}int{FG} dispatch(ctx_t *ctx, frame_t *frame) {{",
            f"   {BLUE}uint64_t{FG} key = rotate(ctx->epoch, 0x17);",
            f"   {GREEN}if{FG} (verify_tag(frame, key) != 0) return -1;",
            f"   node = graph_lookup(frame->selector);",
            f"   route_commit(node, frame->payload);",
            f"   {GREEN}return{FG} 0;",
            " }",
            "",
            f" P-CODE   LOAD → INT_XOR → CBRANCH → CALLIND",
        ]
        if progress > 0.63 or phase_index > 4:
            out += [f" {GREEN}CONTROL-FLOW MODEL RESOLVED{FG}"]
    return out


def access_lines(rng: random.Random, tick: int, height: int, elapsed: float) -> list[str]:
    phase_index, _, _, _, progress = phase_at(elapsed)
    out = [f" {ORANGE}DISTRIBUTED ACCESS FABRIC{FG}  {MUTED}// tactical relay grid{FG}", ""]
    mesh = [
        "                        EDGE-1",
        "                          │",
        "              ┌──────── BROKER ────────┐",
        "              │            │           │",
        "          RELAY-A       RELAY-B      RELAY-C",
        "              │            │           │",
        "           SENSOR       ACCESS       ARCHIVE",
    ]
    for i, line in enumerate(mesh):
        c = ORANGE if (i + tick // 3) % 6 == 0 else (GREEN if phase_index >= 5 else MUTED)
        out.append(" " + colour(line, c))
    out += ["", f" {ORANGE}ROUTE MUTATION{FG}",
            f" {MUTED}#  EXIT             RTT  JIT  TRUST  STATE{FG}"]
    rows = max(3, height - len(out) - 4)
    for i in range(min(rows, len(IPS))):
        live = phase_index >= 5 and i <= int(progress * len(IPS))
        state = colour("active", GREEN) if live else colour("standby", MUTED)
        out.append(f" {i+1:02d} {IPS[(i + tick//9) % len(IPS)]:<15} {rng.randrange(18,72):>2}ms {rng.randrange(2,9):>2}ms  {88+i:>3}   {state}")
    if phase_index == 6:
        out += ["", f" {GREEN}ACCESS WINDOW OPEN // CHANNEL 0xA71C3E{FG}"]
    return out


RENDERERS = {
    "core": core_lines,
    "wireless": wireless_lines,
    "fusion": fusion_lines,
    "graph": graph_lines,
    "sre": sre_lines,
    "access": access_lines,
}


def run(role: str, start: float) -> None:
    rng = random.Random(f"atlas-ghostline-{role}")
    tick = 0
    history: deque[str] = deque(maxlen=80)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    sys.stdout.write("\x1b[?1049h\x1b[?25l" + BG + FG + "\x1b[2J")
    sys.stdout.flush()
    try:
        while True:
            elapsed = max(0.0, time.time() - start)
            size = shutil.get_terminal_size((100, 32))
            lines = header(role, size.columns, elapsed)
            lines.extend(RENDERERS[role](rng, tick, size.lines, elapsed))
            if tick % 2 == 0:
                history.append(activity_line(role, rng, tick))
            if tick % 11 == 0:
                history.append(activity_line(role, rng, tick + 1))
            lines.extend(activity_block(history, size.lines - len(lines), tick))
            frame = "\x1b[H" + "\n".join(fit(line, size.columns) for line in lines[:size.lines]) + "\x1b[J"
            sys.stdout.write(BG + FG + frame)
            sys.stdout.flush()
            tick += 1
            time.sleep(0.14 if role in {"wireless", "fusion"} else 0.24)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        sys.stdout.write(RESET + "\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=sorted(RENDERERS))
    parser.add_argument("--start", type=float, default=time.time())
    args = parser.parse_args()
    run(args.role, args.start)
