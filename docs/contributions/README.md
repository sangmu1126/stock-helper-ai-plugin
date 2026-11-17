# 공개 기여 기록

- 원본 저장소: [koreainvestment/open-trading-api](https://github.com/koreainvestment/open-trading-api)
- PR: [#91 — 폐지된 KRX 시간외 단일가 시간 안내 수정](https://github.com/koreainvestment/open-trading-api/pull/91)
- 확인 상태: OPEN, 일반 PR (draft 아님)
- 포크: [sangmu1126/open-trading-api](https://github.com/sangmu1126/open-trading-api)
- 브랜치: `docs/clarify-overtime-websocket-sessions`
- 커밋: `a3f1b76310166169d6ee0b1e669d428e897d7f98`
- 기준 커밋: `74b0a082fa67a0be5bf53f561719c853890ed2df`
- 범위: 7개 파일의 docstring 9곳. 실행 로직 변경 없음.

[제출 본문](KIS_OVERTIME_PR.md)과 공개 PR의 내용은 동일한 수정 범위를 설명합니다. 지원 여부가 확인되지 않은 TR에 새 거래시간을 지정하지 않았습니다.

검증은 문법 파싱, docstring 제거 후 AST 동일성, 공백 검사로 수행했습니다. 실제 API 요청이나 주문은 실행하지 않았습니다. PR이 제출됐다는 사실과 유지보수자가 내용을 인정·반영했다는 사실은 구분합니다.
