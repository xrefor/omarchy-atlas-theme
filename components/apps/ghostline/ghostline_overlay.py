#!/usr/bin/env python3
"""Short-lived, display-only notification cards for ATLAS GHOSTLINE."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import signal
import sys
import time
from datetime import datetime


BG = "\x1b[48;2;10;9;8m"
FG = "\x1b[38;2;214;207;196m"
BRIGHT = "\x1b[38;2;242;235;224m"
MUTED = "\x1b[38;2;110;103;92m"
ORANGE = "\x1b[38;2;255;90;18m"
AMBER = "\x1b[38;2;240;162;2m"
GREEN = "\x1b[38;2;168;184;92m"
CYAN = "\x1b[38;2;143;184;176m"
RESET = "\x1b[0m"

CARDS = {
    "rf_lock": (
        "RF TARGET LOCK",
        "EMBER ARRAY / SECTOR 07",
        ["emitter     02:7C:20:91:4E:A8", "channel     149 / 80 MHz", "bearing     071.4° ± 2.1°", "confidence  0.987"],
    ),
    "burst": (
        "ENTROPY DEVIATION",
        "WIDEBAND BURST CLASSIFIED",
        ["window      1.204 s", "modulation  OFDM / 1024-QAM", "signature   4E91:B27C", "priority    ELEVATED"],
    ),
    "key": (
        "KEY MATERIAL ACCEPTED",
        "CINDER-9E / TRANSIENT SLOT",
        ["exchange    4 / 4 VERIFIED", "cipher      GCMP-256", "replay      000000000000", "channel     0xA71C3E"],
    ),
    "shard": (
        "SHARD 07 COMMITTED",
        "DATAWAVE QUERY FABRIC",
        ["records     184,921", "provenance  SEALED", "index lag   11 ms", "replicas    6 / 6"],
    ),
    "selector": (
        "SELECTOR COLLISION",
        "SABLE FUSION / HIGH CONFIDENCE",
        ["device      7C20:CC19", "session     A71C:3E90", "cluster     ORPHEUS", "confidence  0.982"],
    ),
    "pcode": (
        "CONTROL FLOW RESOLVED",
        "GHIDRA SRE / P-CODE GRID",
        ["function    callback_dispatch", "xrefs       17", "blocks      42 / 42", "signature   4E91B2…7AC0"],
    ),
    "route": (
        "ROUTE 03 DEGRADED",
        "VECTORLINE / AUTOMATIC MUTATION",
        ["old exit    198.51.100.17", "new exit    203.0.113.71", "handoff     38 ms", "trust       94 / 100"],
    ),
    "gate": (
        "POLICY GATE // ACCEPT",
        "ACCESS FABRIC / RELEASE CONTROL",
        ["task        0x71E4", "identity    SERVICE-17", "scope       OBJECTIVE", "expires     T-00:41"],
    ),
    "objective": (
        "OBJECTIVE ACQUIRED",
        "OPERATION CINDER VEIL",
        ["object      4E91:B27C:7AC0", "integrity   VERIFIED", "provenance  SEALED", "status      SECURED"],
    ),
    "track": (
        "TACTICAL TRACK FUSED",
        "VECTORLINE / CELL KILO-7",
        ["track       VTX-071", "bearing     071.4°", "velocity    18.2 m/s", "confidence  0.974"],
    ),
    "perimeter": (
        "PERIMETER DELTA",
        "FACILITY RING 03 / SENSOR FUSION",
        ["grid        63T WK 2198", "ingress     NODE-04", "sensors     7 / 7", "integrity   NOMINAL"],
    ),
    "relay": (
        "LEO RELAY WINDOW",
        "EMBER ARRAY / ORBITAL HANDOFF",
        ["relay       LANTERN-12", "uplink      18.7 dB", "handoff     00:00:38", "channel     AUTHENTICATED"],
    ),
    "pump": (
        "CENTRIFUGAL BOOSTER P-204",
        "PROCESS LINE 07 / PUMP TRAIN A",
        ["suction     3.8 bar", "discharge   11.6 bar", "flow        842 m³/h", "vibration   1.7 mm/s"],
    ),
    "inspection": (
        "INLINE INSPECTION RUN",
        "PIPELINE 07 / GEOMETRY + MFL ARRAY",
        ["distance    18.42 km", "velocity    2.4 m/s", "coverage    360°", "coupling    NOMINAL"],
    ),
}

STYLE_FOR_KIND = {
    "rf_lock": "scope",
    "track": "scope",
    "perimeter": "scope",
    "burst": "spectrum",
    "relay": "spectrum",
    "key": "credential",
    "gate": "credential",
    "objective": "credential",
    "pcode": "trace",
    "route": "trace",
    "shard": "matrix",
    "selector": "matrix",
    "pump": "pump",
    "inspection": "inspection",
}

EVENT_CONTEXT = {
    "MIC VERIFIED": "VOICEPRINT + LIVENESS CONSENSUS",
    "OBJECT TRANSFER": "P-CODE OBJECT GRAPH PROMOTED",
    "ACCESS PACKAGE": "SCOPED RELEASE ENVELOPE",
    "CHANNEL OPEN": "ROUTE CONSENSUS ESTABLISHED",
    "VOLATILE RETIRE": "EPHEMERAL HOP REVOKED",
    "PROVENANCE": "SHARD LINEAGE SEALED",
}


def fields_as_pairs(fields: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for field in fields:
        parts = re.split(r"\s{2,}", field.strip(), maxsplit=1)
        pairs.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return pairs


def meter(value: float, width: int, accent: str = ORANGE) -> str:
    width = max(6, width)
    filled = max(0, min(width, round(value * width)))
    return f"{accent}{'━' * filled}{MUTED}{'─' * (width - filled)}{FG}"


def sparkline(values: list[float], width: int, accent: str) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    sampled = [values[index * len(values) // max(1, width)] for index in range(max(1, width))]
    return accent + "".join(blocks[min(7, max(0, round(value * 7)))] for value in sampled) + FG


def masthead(label: str, title: str, source: str, width: int, accent: str) -> list[str]:
    rule = "━" * max(18, min(94, width - 4))
    context = EVENT_CONTEXT.get(label, title)
    return [
        f"{accent}▌{FG} {MUTED}ATLAS / GHOSTLINE{FG}   {accent}{label}{FG}",
        f"  {BRIGHT}{context}{FG}",
        f"  {MUTED}{source}  ·  {datetime.now().strftime('%H:%M:%S')}{FG}",
        f"  {accent}{rule}{FG}",
    ]


def scope_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    phase = elapsed * 1.8
    contact = 7 + round(math.sin(phase) * 3)
    accent = CYAN if kind in {"rf_lock", "track"} else AMBER
    confidence = next((value for key, value in fields if key == "confidence"), "0.974")
    bearing = next((value for key, value in fields if key == "bearing"), "063T / RING 03")
    lines = masthead(label, title, source, width, accent)
    lines += [
        "",
        f"  {MUTED}AZIMUTH{FG}  {BRIGHT}{bearing:<24}{FG} {MUTED}TRACK QUALITY{FG}  {accent}{confidence}{FG}",
        f"                         {MUTED}N{FG}",
        f"                {MUTED}┌────────┼────────┐{FG}",
        f"             {MUTED}W──┤{FG}     {accent}{'·' * contact}◆{FG}  {MUTED}├──E{FG}",
        f"                {MUTED}│     ╱  │        │{FG}",
        f"                {MUTED}└────┼────┴────────┘{FG}",
        f"                         {MUTED}S{FG}",
        "",
    ]
    for key, value in fields[:4]:
        lines.append(f"  {MUTED}{key.upper():<12}{FG} {BRIGHT}{value:<26}{FG}")
    lines += ["", f"  {MUTED}CORRELATION{FG}  {meter(0.84 + math.sin(phase) * 0.04, min(44, width - 20), accent)}"]
    return lines


def spectrum_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    accent = AMBER if kind == "burst" else CYAN
    bins = [
        max(0.04, min(1.0, 0.24 + 0.20 * math.sin(index * 0.73 + elapsed * 2.2) + (0.62 if index in {13, 14, 27} else 0)))
        for index in range(40)
    ]
    plot_width = max(24, min(76, width - 8))
    lines = masthead(label, title, source, width, accent)
    lines += [
        "",
        f"  {MUTED}SPECTRAL ENVELOPE / LIVE{FG}",
        f"  {sparkline(bins, plot_width, accent)}",
        f"  {MUTED}2.40G{' ' * max(4, plot_width // 2 - 10)}5.20G{' ' * max(4, plot_width // 2 - 10)}6.10G{FG}",
        "",
    ]
    left = fields[:2]
    right = fields[2:4]
    for index in range(max(len(left), len(right))):
        first = left[index] if index < len(left) else ("", "")
        second = right[index] if index < len(right) else ("", "")
        lines.append(
            f"  {MUTED}{first[0].upper():<11}{FG}{BRIGHT}{first[1]:<22}{FG}"
            f"{MUTED}{second[0].upper():<11}{FG}{BRIGHT}{second[1]}{FG}"
        )
    sweep = (elapsed * 0.23) % 1.0
    lines += ["", f"  {MUTED}CAPTURE WINDOW{FG}  {meter(1.0 - sweep, min(58, width - 24), accent)}"]
    return lines


def credential_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    verdict = "OBJECTIVE SECURED" if kind == "objective" else ("POLICY ACCEPT" if kind == "gate" else "IDENTITY VERIFIED")
    lines = masthead(label, title, source, width, GREEN)
    lines += [
        "",
        f"  {GREEN}●  {BRIGHT}{verdict}{FG}    {MUTED}assurance / A4{FG}",
        f"  {GREEN}✓{FG} {MUTED}identity binding{FG}     {GREEN}✓{FG} {MUTED}integrity proof{FG}     {GREEN}✓{FG} {MUTED}scope check{FG}",
        "",
    ]
    for key, value in fields:
        state = GREEN if any(word in value for word in ("VERIFIED", "SEALED", "SECURED", "AUTHENTICATED")) else BRIGHT
        lines.append(f"  {MUTED}{key.upper():<13}{FG} {state}{value}{FG}")
    remaining = max(0.0, 1.0 - elapsed / 8.0)
    lines += ["", f"  {MUTED}VALIDITY{FG}  {meter(remaining, min(50, width - 18), GREEN)}"]
    return lines


def trace_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    accent = CYAN if kind == "pcode" else AMBER
    lines = masthead(label, title, source, width, accent)
    lines.append("")
    if kind == "pcode":
        cursor = int(elapsed * 3) % 4
        instructions = [
            ("0041A7C0", "LOAD", "r3, [frame+0x18]"),
            ("0041A7C8", "CALL", "verify_tag(frame, key)"),
            ("0041A7D4", "CBRANCH", "r0 == 0 → reject"),
            ("0041A7E0", "STORE", "object → trusted_set"),
        ]
        lines.append(f"  {MUTED}ADDRESS     OPERATION    P-CODE / RESOLVED FLOW{FG}")
        for index, (address, op, statement) in enumerate(instructions):
            marker = f"{accent}▶{FG}" if index == cursor else " "
            lines.append(f" {marker} {MUTED}{address}{FG}  {accent}{op:<11}{FG}{BRIGHT}{statement}{FG}")
        lines += ["", f"  {MUTED}ENTRY{FG} ─── {accent}VALIDATE{FG} ─── {accent}PROMOTE{FG} ─── {GREEN}COMMIT{FG}"]
    else:
        hop = int(elapsed * 2) % 4
        nodes = ("INGRESS", "RELAY-03", "MUTATOR", "EXIT-71")
        route = []
        for index, node in enumerate(nodes):
            colour = accent if index == hop else (GREEN if index < hop else MUTED)
            route.append(f"{colour}{node}{FG}")
        lines += [
            f"  {MUTED}ROUTE CONTROL / LIVE MUTATION{FG}",
            "",
            "  " + f" {MUTED}──▶{FG} ".join(route),
            "",
            f"  {MUTED}HOP        ENDPOINT          RTT     TRUST{FG}",
            f"  {BRIGHT}01         198.51.100.17     22 ms   96{FG}",
            f"  {accent}02         203.0.113.71      38 ms   94  ACTIVE{FG}",
        ]
    lines.append("")
    lines.extend(f"  {MUTED}{key.upper():<12}{FG} {BRIGHT}{value}{FG}" for key, value in fields[:3])
    return lines


def matrix_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    accent = ORANGE if kind == "selector" else CYAN
    pulse = int(elapsed * 4) % 6
    lines = masthead(label, title, source, width, accent)
    lines += [
        "",
        f"  {MUTED}NODE       STATE       LATENCY    CONFIDENCE    LINEAGE{FG}",
    ]
    for index, node in enumerate(("SHARD-A1", "SHARD-B4", "INDEX-C2", "REPLICA-F6", "VAULT-K9", "AUDIT-P3")):
        marker = accent + "●" + FG if index == pulse else MUTED + "○" + FG
        confidence = 91 + (index * 7) % 9
        lines.append(
            f"  {marker} {BRIGHT}{node:<10}{FG} {GREEN}{'SEALED' if index % 2 == 0 else 'SYNCED':<11}{FG}"
            f"{MUTED}{8 + index * 3:>3} ms{FG}     {accent}{confidence / 100:.2f}{FG}          {MUTED}0{index + 1}/06{FG}"
        )
    lines += ["", f"  {MUTED}CONSENSUS{FG}  {meter(0.92 + math.sin(elapsed) * 0.025, min(48, width - 20), accent)}", ""]
    lines.extend(f"  {MUTED}{key.upper():<12}{FG} {BRIGHT}{value}{FG}" for key, value in fields[:3])
    return lines


def pump_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    """Original process-pump schematic with a simple animated impeller."""
    impellers = ("┼", "╱", "×", "╲")
    impeller = impellers[int(elapsed * 7) % len(impellers)]
    flow_marks = ("▶  ▷  ▷", "▷  ▶  ▷", "▷  ▷  ▶")
    flow = flow_marks[int(elapsed * 4) % len(flow_marks)]
    load = 0.72 + math.sin(elapsed * 2.4) * 0.06
    lines = masthead(label, title, source, width, ORANGE)
    lines += [
        "",
        f"  {MUTED}SUCTION HEADER{FG}                                      {MUTED}DISCHARGE MANIFOLD{FG}",
        f"  {CYAN}═══════▶{FG}  {MUTED}┌────────────── P-204A BOOSTER TRAIN ──────────────┐{FG}  {ORANGE}═══════▶{FG}",
        f"            {MUTED}│{FG}   {BRIGHT}MOTOR{FG}       {MUTED}COUPLING{FG}       {ORANGE}VOLUTE / IMPELLER{FG}   {MUTED}│{FG}",
        f"            {MUTED}│{FG}  ╭───────╮       ╥         ╭──────────────╮       {MUTED}│{FG}",
        f"  {CYAN}INLET ────┤{FG}  │  M-17 │══════╬═════════│     {ORANGE}{impeller}{FG}  {BRIGHT}2840 rpm{FG} │───────{ORANGE}┤ OUTLET{FG}",
        f"            {MUTED}│{FG}  ╰───────╯       ╨         ╰──────┬───────╯       {MUTED}│{FG}",
        f"            {MUTED}│{FG}                             {MUTED}BEARING / SEAL{FG}       {MUTED}│{FG}",
        f"            {MUTED}└───────────────────────────────────────────────┘{FG}",
        "",
        f"  {MUTED}PROCESS FLOW{FG}   {ORANGE}{flow}{FG}    {MUTED}ROTATION{FG} {ORANGE}CW{FG}    {MUTED}STATE{FG} {GREEN}ON CURVE{FG}",
        f"  {MUTED}HYDRAULIC LOAD{FG} {meter(load, min(62, width - 24), ORANGE)}",
        "",
    ]
    left, right = fields[:2], fields[2:4]
    for index in range(2):
        lines.append(
            f"  {MUTED}{left[index][0].upper():<12}{FG} {BRIGHT}{left[index][1]:<20}{FG}"
            f"{MUTED}{right[index][0].upper():<12}{FG} {BRIGHT}{right[index][1]}{FG}"
        )
    return lines


def inspection_view(kind: str, label: str, title: str, source: str, fields: list[tuple[str, str]], width: int, elapsed: float) -> list[str]:
    """Original side-view of a generic instrumented inline inspection gauge."""
    wheel_frames = (("◜", "◟"), ("◝", "◞"))
    upper_wheel, lower_wheel = wheel_frames[int(elapsed * 5) % len(wheel_frames)]
    scan = int(elapsed * 5) % 5
    sensor_marks = ["·"] * 5
    sensor_marks[scan] = "◆"
    sensor_line = " ".join(sensor_marks)
    coverage = 0.90 + math.sin(elapsed * 1.7) * 0.035
    lines = masthead(label, title, source, width, CYAN)
    lines += [
        "",
        f"  {MUTED}PIPE WALL  ═════════════════════════════════════════════════════════════════════{FG}",
        f"  {ORANGE}FLOW ▶▶▶{FG}       {MUTED}{upper_wheel} ODOMETER{FG}                  {MUTED}ODOMETER {upper_wheel}{FG}",
        f"              {MUTED}╲{FG}       {AMBER}CALIPER / SENSOR RING{FG}         {MUTED}╱{FG}",
        f"       {CYAN}╭─ CUP ─╮{FG}  ╭╨╮  ╭────────────────────────╮  ╭╨╮  {CYAN}╭─ CUP ─╮{FG}",
        f"  ─────{CYAN}〈       〉{FG}──┤{AMBER}◉{FG}├──│ {BRIGHT}BATTERY · IMU · RECORDER{FG} │──┤{AMBER}◉{FG}├──{CYAN}〈       〉{FG}─────",
        f"       {CYAN}╰───────╯{FG}  ╰╥╯  ╰────────────────────────╯  ╰╥╯  {CYAN}╰───────╯{FG}",
        f"              {MUTED}╱{FG}       {CYAN}{sensor_line}{FG}       {MUTED}╲{FG}",
        f"             {MUTED}{lower_wheel} DRIVE / CENTERING{FG}       {MUTED}DRIVE / CENTERING {lower_wheel}{FG}",
        f"  {MUTED}PIPE WALL  ═════════════════════════════════════════════════════════════════════{FG}",
        "",
        f"  {MUTED}CIRCUMFERENTIAL COVERAGE{FG} {meter(coverage, min(54, width - 34), CYAN)} {CYAN}360°{FG}",
        f"  {MUTED}CHANNELS{FG} {BRIGHT}128 ACTIVE{FG}   {MUTED}MAGNETIC COUPLING{FG} {GREEN}NOMINAL{FG}   {MUTED}CLOCK{FG} {BRIGHT}LOCKED{FG}",
        "",
    ]
    lines.extend(f"  {MUTED}{key.upper():<12}{FG} {BRIGHT}{value}{FG}" for key, value in fields)
    return lines


VIEW_RENDERERS = {
    "scope": scope_view,
    "spectrum": spectrum_view,
    "credential": credential_view,
    "trace": trace_view,
    "matrix": matrix_view,
    "pump": pump_view,
    "inspection": inspection_view,
}


def render(kind: str, label: str, duration: float) -> None:
    title, subtitle, fields = CARDS[kind]
    pairs = fields_as_pairs(fields)
    view = VIEW_RENDERERS[STYLE_FOR_KIND[kind]]
    started = time.monotonic()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    sys.stdout.write("\x1b[?1049h\x1b[?25l" + BG + FG + "\x1b[2J")
    sys.stdout.flush()
    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= duration:
                break
            width, height = shutil.get_terminal_size((76, 16))
            lines = view(kind, label, title, subtitle, pairs, width, elapsed)
            lines.extend([""] * max(0, height - len(lines)))
            frame = "\x1b[K\n".join(lines[:height]) + "\x1b[K"
            sys.stdout.write(BG + "\x1b[H" + frame + "\x1b[J")
            sys.stdout.flush()
            time.sleep(0.12)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        sys.stdout.write(RESET + "\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(CARDS))
    parser.add_argument("--label")
    parser.add_argument("--duration", type=float, default=3.4)
    args = parser.parse_args()
    render(args.kind, (args.label or CARDS[args.kind][0]).upper(), max(1.0, min(args.duration, 8.0)))
