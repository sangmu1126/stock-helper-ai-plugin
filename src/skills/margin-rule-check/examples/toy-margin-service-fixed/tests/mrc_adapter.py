"""신용거래 규칙 테스트 어댑터 — 이 저장소의 계산 함수를 연결한다."""

from margin_service import classify, grace, liquidation_day

classify_ratio = classify
liquidation_date = liquidation_day
grace_status = grace
