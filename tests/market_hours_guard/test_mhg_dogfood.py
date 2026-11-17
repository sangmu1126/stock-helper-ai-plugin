"""거래시간 점검기로 같은 플러그인의 투자자용 스킬을 검사한다.

두 스킬이 같은 정규장 기준을 쓰는지, 투자자용 스킬에 기준표에 없는 거래시간 값이 생기지 않았는지 지킨다.
"""

from conftest import REPO
from market_hours_guard.scan import scan_repo


def test_investor_skill_and_runtime_time_values_all_match_calendar(calendar):
    """투자자용 스킬과 로컬 런타임(세션 설정 market_sessions.json 포함)의 거래시간 값이 모두 기준표와 일치한다."""
    findings = []
    for folder in ("src/skills/safe-trade-rule-builder", "src/runtime"):
        findings += scan_repo(REPO / folder, calendar).findings
    not_matching = [(f.status, f.path, f.line, f.found) for f in findings if f.status != "MATCH"]
    assert not_matching == []
    found = {f.found for f in findings}
    # 정규장·애프터마켓·수능일(정규장·애프터마켓)·미국 정규장·미국 조기 폐장·오전 기준이 실제로 검사되었는지
    assert {"09:00", "15:30", "16:00", "20:00", "10:00", "16:30", "17:00", "09:30", "13:00", "12:00"} <= found
