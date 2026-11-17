# 보관된 이전 후보

현재 채택안 문서는 제출물에 포함되도록 `src/docs/`로 옮겼다: [거래시간 변경 점검기](../../../src/docs/MARKET_HOURS_GUARD.md), [근거](../../../src/docs/MARKET_HOURS_EVIDENCE.md), [신용거래 반대매매 가드](../../../src/docs/MARGIN_GUARD.md). 아래는 탈락하거나 보류한 후보이며, 문서 안의 상대 링크는 작성 당시 기준이라 일부 깨질 수 있다.

| 폴더 | 후보 | 판단 |
| --- | --- | --- |
| `customer-incident/` | 고객용 거래장애 기록 도우미 | 입증한 문제(장애)와 해결(문의서 작성) 사이 간격 |
| `customer-candidates/` | 배당세 정산 설명 등 고객 후보 재조사 (RESEARCH_02) | "설명해주면 편리" 수준 |
| `enterprise-policy-guard/` | 증권 정책 정합성 검증기 (Codex 직전안) | 근거(상담원 구두 오안내)와 해결(문서 대조)의 연결이 약함 |
| `aws/` | AWS 배포 기록과 삭제 전 백업 (2026-11-18 AWS 제거) | 플러그인 흐름에서 쓰이지 않아 제거. 자세한 내용은 `aws/README.md` |

최초 후보인 Safe Trade Rule Builder는 저장소 루트 `src/`에 그대로 있다.
