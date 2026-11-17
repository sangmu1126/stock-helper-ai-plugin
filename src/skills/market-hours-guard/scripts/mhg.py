#!/usr/bin/env python3
"""Market Hours Guard 실행 진입점.

    python mhg.py check-calendar --calendar <기준표.toml>
    python mhg.py scan --repo <저장소> --calendar <기준표.toml> [--out mhg-output] [--sarif mhg.sarif]
    python mhg.py gen-tests --calendar <기준표.toml> --out <저장소>/tests/market_hours [--format junit]
    python mhg.py impact --repo <저장소> --calendar <현재.toml> --new-calendar <새.toml>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_hours_guard.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
