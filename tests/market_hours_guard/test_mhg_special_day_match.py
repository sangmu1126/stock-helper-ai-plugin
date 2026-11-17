"""특수일 기준(requires_keyword)은 그날 문맥이 있을 때만 MATCH."""

from market_hours_guard.scan import scan_repo


def _scan_text(tmp_path, calendar, text, name="notes.py"):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return {(f.line, f.found): f for f in scan_repo(tmp_path, calendar).findings}


# ── 특수일 기준은 그날 문맥이 있을 때만 MATCH ─────────────────────

def test_special_day_values_need_their_context(tmp_path, calendar):
    """공개 저장소 평가에서 해외 예약주문 접수 10:00이 수능일 개장 10:00으로 MATCH 되던 문제."""
    findings = _scan_text(tmp_path, calendar, (
        "# 해외 예약주문 접수 10:00 ~ 23:20 (거래소 주문 전송)\n"
        "# 홍콩 거래소 (오후) 14:00 ~ 17:00\n"
        "# 수능일 KRX 정규장 10:00 개장, 16:30 마감\n"
    ))
    overseas, hong_kong = findings[(1, "10:00")], findings[(2, "17:00")]
    assert overseas.status == "UNMAPPED" and "KRX_REGULAR_OPEN_CSAT_2026" in overseas.reason
    assert hong_kong.status == "UNMAPPED" and "KRX_AFTER_OPEN_CSAT_2026" in hong_kong.reason
    suneung = findings[(3, "10:00")], findings[(3, "16:30")]
    assert [(f.status, f.boundary) for f in suneung] == [
        ("MATCH", "KRX_REGULAR_OPEN_CSAT_2026"), ("MATCH", "KRX_REGULAR_CLOSE_CSAT_2026")]


def test_requires_keyword_is_parsed(calendar):
    flagged = {b.id for b in calendar.active if b.requires_keyword}
    assert flagged == {"KRX_REGULAR_OPEN_CSAT_2026", "KRX_REGULAR_CLOSE_CSAT_2026", "KRX_AFTER_OPEN_CSAT_2026"}
