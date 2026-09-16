#!/usr/bin/env python3
"""ATLAS preferences, local diagnostics and managed-file restoration."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'lib'))
from atlas.settings import main

if __name__ == '__main__':
    raise SystemExit(main(ROOT))
