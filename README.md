# Safe Trade Rule Builder

[![CI](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml)
카카오페이증권 문제의식에 맞춘 Codex 플러그인 프로토타입입니다. 초보 투자자가 자연어로 말한 매수·매도 의도를 바로 주문으로 연결하지 않고, 감정 표현·데이터 신뢰도·계좌 한도·중복 실행·수동 확인 절차를 통과한 서버리스 룰 초안으로 변환합니다.

## 5줄 요약

- 문제: 초보 투자자는 손실 회피, 본전 회복, FOMO 때문에 매수·매도 판단을 감정적으로 내리기 쉽습니다.
- 해결: 자연어 의도를 구조화된 룰, 안전장치, 백테스트, 수동 확인 체크리스트로 바꿉니다.
- 안전장치: 정책 엔진, 리스크 한도, 시세 freshness, broker/account provider, DynamoDB idempotency를 적용했습니다.
- 서버리스: AWS SAM 기반 Lambda + DynamoDB 통합 테스트를 완료했습니다.
- 원칙: 실주문은 하지 않고 `STOP`, `WAIT`, `NOTIFY_ONLY`, `MANUAL_CONFIRM`까지만 반환합니다.

## 제출 구조

```text
submission.zip
├── src/
│   ├── .codex-plugin/plugin.json
│   ├── skills/safe-trade-rule-builder/SKILL.md
│   ├── runtime/
│   ├── infra/template.yaml
│   ├── docs/
│   └── requirements.txt
├── README.md
└── logs/
```

`src/`가 Codex 플러그인 루트입니다. `logs/`에는 AI와 주고받은 대화 로그를 편집 없이 포함합니다.

## 핵심 기능

- GPT API 기반 LLM 우선 자연어 파싱, 실패 시 deterministic parser fallback
- Pydantic 기반 스키마 검증
- prompt injection 및 실주문 유도 표현 사전 차단
- policy, risk limit, prompt-security rule의 runtime config provider와 local fallback
- 감정적 의도 탐지 시 주문 준비를 clarification flow로 downgrade
- yfinance 기반 시장 데이터 조회
- 과거 데이터 기반 백테스트와 안전성 경고
- 마크다운 리포트 생성
- AWS Lambda 런타임 산출물 생성
- DynamoDB 기반 idempotency/cooldown state store
- DynamoDB 기반 immutable decision log store
- 브로커/계좌 provider interface 분리
- 한국어 사용자 행동 안내와 확인 체크리스트

## 카카오페이증권 API 관련 전제

카카오페이 개발자센터의 공개 API에는 현재 증권 시세·계좌·주문 API가 확인되지 않습니다. 따라서 이 프로토타입은 다음 구조로 설계했습니다.

- 시장 데이터: `yfinance` provider 사용
- 계좌/브로커 상태: event 기반 provider로 주입
- 카카오페이증권 연동: 추후 공식 또는 제휴 API가 제공되면 provider만 교체
- 실주문: 지원하지 않음
- 최종 행동: 사용자가 MTS에서 직접 판단할 수 있는 수동 확인 단계까지만 제공

이 접근은 해커톤 주제의 핵심인 “정답 추천”보다 “납득 가능한 의사결정 과정 설계”에 초점을 둡니다.

## 실행 예시

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py `
  --intent "카카오가 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘" `
  --parser deterministic `
  --format markdown
```

시장 데이터 포함:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py `
  --intent "카카오가 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘" `
  --with-market-data `
  --provider yfinance `
  --format markdown
```

GPT API 파서 사용:

```powershell
# .env 또는 현재 셸 환경변수에 OPENAI_API_KEY를 설정한 뒤 실행
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py `
  --intent "카카오가 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘" `
  --parser llm `
  --format markdown
```

백테스트 포함:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py `
  --intent "카카오가 전일 종가보다 3% 떨어지면 알려줘" `
  --backtest `
  --provider demo-fixture `
  --format markdown
```

## 서버리스 런타임

런타임은 `src/runtime/lambda_handler.py`입니다. 배포 시 다음 흐름으로 결정합니다.

1. 외부 정책 룰 로드
2. 브로커/계좌/거래소/시세 freshness 점검
3. 트리거 조건 평가
4. 정책 결과와 상태 저장소를 DecisionEngine에서 조합
5. decision log 저장
6. 한국어 사용자 행동 안내와 확인 체크리스트 반환

반환 decision:

- `STOP`: 안전장치 실패
- `WAIT`: 조건 미충족 또는 중복 실행 차단
- `NOTIFY_ONLY`: 알림만 허용
- `MANUAL_CONFIRM`: 사용자가 수동 확인할 수 있는 후보
- `REQUIRE_CLARIFICATION`: 룰이 모호해 추가 확인 필요
- `BLOCK`: 정책상 차단

## AWS 검증 결과

실제 AWS 통합 테스트를 완료했습니다.

- Stack: `safe-trade-rule-builder-integration`
- Lambda: `safe-trade-rule-builder-i-SafeTradeRuntimeFunction-VhZoIY7GltOa`
- State table: `safe-trade-rule-builder-integration-SafeTradeStateTable-FYJ0VD4HDDQH`
- Decision log table: `safe-trade-rule-builder-integration-SafeTradeDecisionLogTable-EN0YEE61PIZ`
- 첫 호출: `MANUAL_CONFIRM`
- 동일 이벤트 재호출: `WAIT / DUPLICATE_DECISION_BLOCKED`
- broker latency 이벤트: `STOP / BROKER_LATENCY_LIMIT_EXCEEDED`
- State table: idempotency row와 cooldown row 생성 확인
- Decision log table: 허용, 중복, 중단 경로 로그 저장 확인
- 동시성 부하 테스트: 동일 이벤트 20개 병렬 호출에서 `MANUAL_CONFIRM` 1건, `WAIT / DUPLICATE_DECISION_BLOCKED` 19건 확인

상세 기록은 `src/docs/AWS_PERMISSION_CHECK.md`에 있습니다.

## SAM 배포

로컬 기본값은 `memory` backend입니다. AWS 통합 테스트는 parameter override로 DynamoDB backend를 사용합니다.

```powershell
sam deploy --template-file .aws-sam\build\template.yaml `
  --stack-name safe-trade-rule-builder-integration `
  --region ap-northeast-2 `
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND `
  --resolve-s3 `
  --parameter-overrides StateBackend=dynamodb DecisionLogBackend=dynamodb `
  --no-confirm-changeset `
  --no-fail-on-empty-changeset
```

테스트 후 삭제:

```powershell
aws cloudformation delete-stack `
  --region ap-northeast-2 `
  --stack-name safe-trade-rule-builder-integration
```

## 환경변수

`.env.example`은 로컬 템플릿입니다. 실제 `.env`, AWS credential, API key는 제출물에 포함하지 않습니다.

- `OPENAI_API_KEY`: LLM parser 사용 시 필요
- `SAFE_TRADE_RULE_LLM_MODEL`: GPT API parser 모델. 기본값 `gpt-4.1-mini`
- `SAFE_TRADE_RULE_LLM_TIMEOUT_SECONDS`: GPT API timeout. 기본값 `20`
- `SAFE_TRADE_ENV`: `local`, `dev`, `prod`
- `SAFE_TRADE_STATE_BACKEND`: `memory` 또는 `dynamodb`
- `SAFE_TRADE_STATE_TABLE`: DynamoDB state table
- `SAFE_TRADE_DECISION_LOG_BACKEND`: `memory` 또는 `dynamodb`
- `SAFE_TRADE_DECISION_LOG_TABLE`: DynamoDB decision log table
- `SAFE_TRADE_BROKER_SECRET`: Secrets Manager secret 이름
- `SAFE_TRADE_CONFIG_BACKEND`: `local`, `ssm`, `appconfig`. 기본값 `local`
- `SAFE_TRADE_CONFIG_TTL_SECONDS`: runtime config cache TTL. 기본값 `60`
- `SAFE_TRADE_POLICY_CONFIG_PATH`: local policy JSON override
- `SAFE_TRADE_RISK_LIMITS_PATH`: local risk-limit JSON override
- `SAFE_TRADE_PROMPT_SECURITY_CONFIG_PATH`: local prompt-security JSON override
- `SAFE_TRADE_POLICY_SSM_PARAMETER`: policy JSON SSM parameter 이름
- `SAFE_TRADE_RISK_SSM_PARAMETER`: risk-limit JSON SSM parameter 이름
- `SAFE_TRADE_PROMPT_SECURITY_SSM_PARAMETER`: prompt-security JSON SSM parameter 이름
- `SAFE_TRADE_APPCONFIG_APPLICATION`: AppConfig application identifier
- `SAFE_TRADE_APPCONFIG_ENVIRONMENT`: AppConfig environment identifier
- `SAFE_TRADE_APPCONFIG_PROFILE`: AppConfig 기본 profile identifier
- `SAFE_TRADE_POLICY_APPCONFIG_PROFILE`: policy AppConfig profile override
- `SAFE_TRADE_RISK_APPCONFIG_PROFILE`: risk AppConfig profile override
- `SAFE_TRADE_PROMPT_SECURITY_APPCONFIG_PROFILE`: prompt-security AppConfig profile override
- `KAKAOPAY_API_BASE_URL`: 추후 API 연동용
- `KAKAOPAY_API_KEY`: 추후 API 연동용
- `KAKAOPAY_API_SECRET`: 추후 API 연동용
- `KAKAOPAY_ACCOUNT_ID`: 추후 API 연동용

정책성 설정은 기본적으로 `src/runtime/policy_rules.json`, `src/runtime/risk_limits.json`, `src/runtime/prompt_security_rules.json`을 사용합니다. 운영에서는 `SAFE_TRADE_CONFIG_BACKEND=ssm` 또는 `appconfig`로 바꾸고, 실패 시 packaged local fallback을 사용합니다. decision log에는 사용된 config version, source, fallback 여부가 남습니다.

## 검증 명령

```powershell
python -m pytest -q
python tools\package_submission.py --check-only
python tools\package_submission.py
```

현재 기준:

- pytest: `56 passed`
- 제출 구조: valid
- `submission.zip`: 생성 완료

추가 검증 문서:

- `src/docs/LLM_SMOKE_TEST.md`: 실제 GPT API Structured Output smoke test
- `src/docs/AWS_PERMISSION_CHECK.md`: AWS Lambda/DynamoDB 통합 검증
- `src/docs/DUPLICATION_BOUNDARIES.md`: runtime/scripts 중복 경계

## 안전 고지

이 플러그인은 투자 조언, 종목 추천, 수익 보장, 실주문 시스템이 아닙니다. 백테스트는 과거 조건 발동 양상을 확인하는 안전성 검토이며, 미래 성과 예측이 아닙니다. 모든 주문 판단은 사용자의 수동 확인과 별도 증권사 화면에서 이루어져야 합니다.

---

## 💡 회고 및 향후 개선 과제 (Post-Mortem)

해커톤 본선 이후, 본 프로젝트의 엔터프라이즈 프로덕션 환경(Production-Ready) 기준을 충족하기 위해 아래와 같은 아키텍처 결함을 자체 진단하고 리팩토링을 완료했습니다.

1. **DynamoDB 트랜잭션 고립 (Race Condition) 해결**: 
   - 기존에는 `idempotency_key` 저장과 `cooldown` 갱신이 독립된 두 번의 쿼리로 분리되어 있어, 그 사이에 Lambda 크래시가 발생할 경우 고아(Orphan) 락이 발생하는 치명적 결함이 존재했습니다. 
   - 이를 `TransactWriteItems`를 활용한 원자적 단일 트랜잭션 연산(`record_decision_state`)으로 통합하여 데이터 무결성을 100% 보장하도록 개선했습니다.
   - **(Phase 7 추가 고도화)**: 기존에는 상태 저장(Idempotency, Cooldown)과 결정 이력(Decision Log) 저장이 분리되어 있었습니다. Phase 7에서는 이 3가지 쓰기 작업을 **단일 `TransactWriteItems` 명령**으로 완벽하게 병합하여, 람다가 죽더라도 로그 누락이나 고아 락이 발생하지 않는 진정한 원자성(Atomicity)을 달성했습니다.
2. **보안 인가 계층 고도화 (Phase 7)**:
   - 단순한 `x-api-key` 검증을 넘어, `Authorization: Bearer <token>` 형태의 JWT(JSON Web Token) 파싱 미들웨어를 추가했습니다. 클라이언트가 넘긴 페이로드를 신뢰하지 않고, JWT 내부의 `sub` 클레임을 기반으로 `user_id`를 강제 주입하여 인가(Authorization)의 빈틈을 완벽하게 틀어막았습니다.
3. **비동기 이벤트 분리를 통한 동기 병목 해소 (Phase 7)**:
   - 평가 결정 후 체결 로그 적재나 사용자 알림과 같은 무거운 후처리 작업이 API Gateway의 동기 응답 속도를 깎아먹지 않도록, AWS EventBridge로 `DecisionMade` 이벤트를 비동기 발송(`emit_async_decision_event`)하는 클라우드 네이티브 패턴을 적용했습니다.
4. **AppConfig 호출 비용 및 지연 최적화**: 
   - 매 Lambda 호출마다 새로운 AppConfig 세션을 여는 구조에서 발생하는 Latency와 비용 낭비를 막기 위해, `InitialConfigurationToken` 이후의 `NextPollConfigurationToken`을 전역(Global) 메모리에 캐싱하여 재사용하도록 아키텍처를 변경했습니다.
5. **DynamoDB 스토리지 누수 방어**: 
   - 애플리케이션 코드에는 TTL 속성이 정의되어 있었으나 IaC (`template.yaml`) 수준에서 빠져있던 `TimeToLiveSpecification`을 명시적으로 활성화하여 무한히 쌓이는 스토리지 비용을 방어했습니다.
6. **시스템 장애 Fail-Closed 보장**: 
   - 외부 DB나 Config 서비스 장애 시 Lambda가 502 에러를 뱉고 크래시하는 것을 막기 위해 최상위 핸들러에 예외 처리 경계(Boundary)를 구축하고, 장애 시에도 클라이언트에게 구조화된 `STOP` JSON 응답을 보장하도록 개선했습니다.
