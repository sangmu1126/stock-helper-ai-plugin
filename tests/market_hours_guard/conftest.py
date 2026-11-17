import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "src" / "skills" / "market-hours-guard"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def calendar_path() -> Path:
    return SKILL / "assets" / "calendar.demo.toml"


@pytest.fixture
def calendar(calendar_path):
    from market_hours_guard.calendar_model import load_calendar

    return load_calendar(calendar_path)


@pytest.fixture
def examples() -> Path:
    return SKILL / "examples"


@pytest.fixture
def mhg_script() -> Path:
    return SCRIPTS / "mhg.py"
