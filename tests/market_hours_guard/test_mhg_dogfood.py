"""거래시간 점검기로 같은 플러그인의 투자자용 스킬을 검사한다.

두 스킬이 같은 정규장 기준을 쓰는지, 투자자용 스킬에 기준표에 없는 거래시간 값이 생기지 않았는지 지킨다.
"""

from conftest import REPO
from market_hours_guard.scan import scan_repo


def test_investor_skill_time_values_all_match_calendar(calendar):
    result = scan_repo(REPO / "src" / "skills" / "safe-trade-rule-builder", calendar)
    not_matching = [(f.status, f.path, f.line, f.found) for f in result.findings if f.status != "MATCH"]
    assert not_matching == []
    assert len(result.findings) >= 8  # 정규장 시작·마감(KRX·미국)과 오전 기준이 실제로 검사되었는지
