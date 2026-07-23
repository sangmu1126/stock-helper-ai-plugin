# 발표/심사용 요약

## 한 문장 정의

Safe Trade Rule Builder는 초보 투자자의 자연어 매수·매도 의도를 바로 주문으로 실행하지 않고, 데이터 신뢰도·감정 통제·정책 검증·백테스트·수동 확인 절차를 거친 서버리스 매매 룰 후보로 바꾸는 Codex 플러그인입니다.

## 문제 적합성

- 카카오페이증권 본선 문제의 핵심은 “정답 종목 추천”보다 “사용자가 납득하고 안심할 수 있는 의사결정 과정”입니다.
- 이 플러그인은 매수·매도 판단을 대신하지 않고, 사용자의 말을 구조화한 뒤 왜 멈추는지, 왜 기다리는지, 왜 수동 확인이 필요한지 설명합니다.
- 공개 카카오페이 API에는 증권 주문 API가 확인되지 않아, 실주문 대신 provider interface와 yfinance 시장 데이터로 교체 가능한 구조를 만들었습니다.

## 데모 흐름

1. 사용자가 “카카오가 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘”라고 입력합니다.
2. GPT API 기반 LLM parser가 구조화 룰을 만들고, 실패하면 deterministic parser가 fallback합니다.
3. Pydantic schema가 trigger/action/execution mode를 검증합니다.
4. policy engine이 감정 표현, 투자 권유 요청, 주문 모호성을 검사합니다.
5. market data provider가 시세와 과거 데이터를 가져오고, backtest가 조건 발동 양상을 검토합니다.
6. Lambda runtime이 broker health, quote freshness, account limit, trigger match를 평가합니다.
7. DecisionEngine이 DynamoDB idempotency/cooldown을 확인하고 최종 decision을 반환합니다.
8. 사용자는 한국어 설명과 확인 체크리스트를 보고 MTS에서 직접 판단합니다.

## 심사 포인트

- 실제 Codex plugin 구조: `src/.codex-plugin/plugin.json`, `skills/.../SKILL.md`, runtime, infra, docs 포함
- 실제 서버리스 산출물: AWS SAM `template.yaml`, Lambda handler, DynamoDB state/log table
- 실제 통합 검증: 배포된 Lambda에서 DynamoDB backend로 중복 실행 차단과 STOP 경로 검증
- 실제 GPT API 검증: Responses API Structured Output 경로에서 `structured_output_used=true` 확인
- 안전 설계: 실주문 없음, 수동 확인만 반환, 감정 플래그 시 clarification으로 downgrade
- 입력 보안: prompt injection과 자동 주문 유도 표현은 runtime precheck에서 `STOP` 처리
- 운영 확장성: policy, risk limit, prompt-security rule은 local fallback을 유지하면서 SSM/AppConfig provider 경계로 핫로딩 가능
- 유지보수성: parser, validator, policy, evaluation, state store, decision log, provider, UX를 분리
- 감사 가능성: immutable decision log와 trace id, 한국어 user_action, error taxonomy 제공

## 현재 한계와 대책

- 카카오페이증권 공개 주문 API가 없어 yfinance와 event provider를 사용합니다. 추후 공식 API가 열리면 provider만 교체합니다.
- LLM parser는 운영 환경에서 비용, 지연, JSON 오류가 발생할 수 있습니다. schema validation과 deterministic fallback으로 방어합니다.
- 백테스트는 수익 예측이 아니라 조건 발동 빈도와 위험 신호 확인용입니다.
- 실거래 전에는 법무·준법감시·보안·장애 대응·관측성 기준을 별도 통과해야 합니다.
