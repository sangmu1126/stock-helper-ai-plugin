# 카카오페이증권 안전 거래 Codex 플러그인

[![CI](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml)

카카오페이증권의 공개·검증 가능한 문제를 해결하는 Codex 플러그인입니다. 플러그인 하나에 **사내 개발자용 스킬**과 **일반 투자자용 스킬**이 들어 있습니다. 매니페스트 ID는 최초 버전부터 쓰던 `safe-trade-rule-builder`를 그대로 씁니다.

## 누가, 어디서 쓰나

| 대상 | 스킬 | 쓰는 곳 | 해결하는 일 | 공개 근거 |
| --- | --- | --- | --- | --- |
| **사내 개발자·QA** (주력) | `market-hours-guard` | Codex 앱·CLI에서 회사 저장소를 열고 요청 | 거래시간 제도 변경(KRX 애프터마켓·프리마켓, SOR 적용 시간, 미국 서머타임)을 코드·설정에 빠짐없이 반영하고 경계 시각 테스트로 확인 | MTS 장애 42건, 대형 12개사 중 공동 1위·4년 연속 증가한 유일한 회사(금감원 자료). 애프터마켓 개장 첫날 SOR 시간 변경 과정의 장애 |
| **일반 투자자** (부가) | `safe-trade-rule-builder` | Codex 앱·CLI. 같은 플러그인을 ChatGPT에서도 설치할 수 있음 | 신용거래 반대매매 기준 계산(필요 입금액·기한·한시 유예), 감정적 주문 요청을 안전한 룰 초안으로 변환 | 신용공여 1년 새 168.5% 증가, 상반기 민원 829% 증가, 담보비율 오안내 보도(120%로 안내, 실제 140%) |

Codex는 요청이 스킬 설명과 맞으면 그 스킬의 `SKILL.md` 지침을 읽고 스크립트를 실행한 뒤 결과를 설명합니다. 숫자 계산과 판정은 스크립트가 맡고, 문맥 이해·설명·코드 수정은 Codex가 맡습니다. 별도 화면은 없고 Codex 채팅이 곧 인터페이스입니다.

## 설치와 실행

Python 3.11 이상이 필요합니다. AWS 계정이나 OpenAI 키 없이 동작합니다.

### 바로 실행해 보기 (Codex 없이)

```powershell
git clone https://github.com/sangmu1126/stock-helper-ai-plugin.git
cd stock-helper-ai-plugin
pip install -r src/requirements.txt
python -m pytest -q
```

그다음 아래 1·2장의 명령으로 각 기능을 실행합니다. 합성 저장소와 가상 계좌 예제가 들어 있습니다. Windows 콘솔에서 한글이 깨지면 `$env:PYTHONIOENCODING="utf-8"`을 먼저 설정하세요.

### Codex에 플러그인으로 설치

1. 저장소 루트에 `.agents/plugins/marketplace.json`을 만들고 아래 내용을 넣습니다. `.agents/`는 개인 설정 폴더라 저장소에 포함하지 않습니다.

   ```json
   {
     "name": "local",
     "interface": { "displayName": "Local" },
     "plugins": [
       {
         "name": "safe-trade-rule-builder",
         "source": { "source": "local", "path": "./src" },
         "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
         "category": "Productivity"
       }
     ]
   }
   ```

2. Codex 앱을 다시 시작하거나 Codex CLI에서 `/plugins`로 설치합니다. Codex IDE 확장은 플러그인을 지원하지 않습니다.
3. 예시 요청
   - 개발자: "SOR 적용 시간이 20:00까지 늘어난 변경이 이 저장소에 빠짐없이 반영됐는지 점검하고 경계 테스트까지 만들어줘."
   - 투자자: "담보비율 120%만 맞추면 반대매매 안 되지?" / "삼성전자가 3% 떨어지면 신용으로 100만원어치 매수 후보로 알려줘."

개발자용 스킬은 표준 라이브러리만 쓰고, 투자자용 스킬은 `src/requirements.txt`의 패키지가 필요합니다.

## 제출 구조

```text
submission.zip
├── src/                                     # Codex 플러그인 루트
│   ├── .codex-plugin/plugin.json
│   ├── skills/market-hours-guard/           # 사내 개발자용: 거래시간 변경 점검기
│   ├── skills/safe-trade-rule-builder/      # 일반 투자자용: 신용거래 가드 + 안전 매매 룰
│   ├── runtime/                             # 투자자용 룰을 평가하는 로컬 런타임
│   ├── docs/                                # 근거·설계 문서
│   └── requirements.txt
├── README.md
└── logs/
```

`logs/`에는 AI와 주고받은 대화 로그를 편집 없이 포함합니다.

## 1. 사내 개발자용: 거래시간 변경 점검기 (`market-hours-guard`)

카카오페이증권 개발자·QA가 거래시간 제도 변경(KRX 애프터마켓·프리마켓, NXT 세션, SOR 적용 시간, 미국 서머타임)을 시스템에 반영할 때 씁니다. 코드·설정에 흩어진 시각 값을 승인된 기준표와 대조해 누락을 찾고, 경계 시각 테스트로 동작까지 확인합니다.

- 문제: 카카오페이증권 MTS 장애 42건으로 대형 12개사 중 공동 1위, 4년 연속 증가한 유일한 회사(금감원 자료). 거래시간이 계속 확대되는 중(KRX 애프터마켓 2026-09-14 개장, 프리마켓 예정)이고, 업계는 전산 개발 부담을 이유로 일정을 미뤘으며, 개장 첫날 SOR 적용 시간 변경(15:30→20:00) 과정에서 대형사 장애가 났습니다. 출처와 입증 범위는 [src/docs/MARKET_HOURS_EVIDENCE.md](src/docs/MARKET_HOURS_EVIDENCE.md), 설계는 [src/docs/MARKET_HOURS_GUARD.md](src/docs/MARKET_HOURS_GUARD.md).
- 해결: 결정적 스캐너가 시각 표현을 찾아 `STALE`(폐기된 기준값) · `DST_RISK`(서머타임 미반영) · `AMBIGUOUS`(의미 불명확) · `UNMAPPED` · `MISMATCH`로 판정하고, Codex가 문맥을 읽어 수정한 뒤 `mhg:` 주석으로 의미를 고정합니다. 기준표에서 경계 ±1초·서머타임 전후 테스트를 생성합니다.
- 의존성: 표준 라이브러리만 사용(Python 3.11+). 외부 API·클라우드 불필요.

```powershell
$S = "src\skills\market-hours-guard\scripts\mhg.py"
$C = "src\skills\market-hours-guard\assets\calendar.demo.toml"
$E = "src\skills\market-hours-guard\examples"
python $S check-calendar --calendar $C
python $S scan --repo "$E\toy-broker" --calendar $C --out mhg-output        # 수정 전: 종료 코드 1
python $S scan --repo "$E\toy-broker-fixed" --calendar $C --out mhg-output  # 수정 후: 종료 코드 0
python $S gen-tests --calendar $C --out "$env:TEMP\mhg-tests"               # 경계 테스트 28건 생성
pytest tests\market_hours_guard -q                                          # 스킬 자체 테스트 40개
```

합성 저장소(`examples/toy-broker`, 실제 회사 코드 아님) 결과:

| 단계 | 정적 스캔 | 경계 테스트 28건 |
| --- | --- | --- |
| 수정 전 | STALE 1 · DST_RISK 2 · AMBIGUOUS 1 · UNMAPPED 1 · MATCH 4 | 7 실패 |
| 수정 후 (`toy-broker-fixed`) | MATCH 12 (11개는 `mhg:` 주석으로 의미 고정) | 28 통과 |

- 같은 `15:30`을 정규장 마감(정상)·과거 SOR 종료(누락)·판단 보류로 구분합니다.
- 미국 장 시각을 한국시간으로 고정한 코드는 11월 1일 서머타임 해제 이후 케이스에서만 실패합니다.
- 정적 스캔으로 안 보이는 애프터마켓 세션 누락을 경계 테스트가 잡습니다.
- 이 스킬로 같은 플러그인의 투자자용 스킬을 검사하면 거래시간 값 11개가 모두 기준표와 일치(MATCH)합니다. 테스트가 이 상태를 계속 지킵니다.
- 한계: 용량·성능, 외부 거래소·SOR 장애, DB·원격 설정 값, 휴장일 달력은 범위 밖입니다. 데모 기준표의 `DEMO` 출처 값은 시연용 가정입니다.

## 2. 일반 투자자용: Safe Trade Rule Builder (`safe-trade-rule-builder`)

투자자가 자연어로 말한 매수·매도·신용 요청을 바로 주문으로 연결하지 않고, 반대매매 위험·감정 표현·데이터 신뢰도·계좌 한도·중복 실행·수동 확인 절차를 거친 룰 초안과 설명으로 바꿉니다. 실주문은 하지 않고 `STOP`, `WAIT`, `NOTIFY_ONLY`, `MANUAL_CONFIRM`, `REQUIRE_CLARIFICATION`까지만 반환합니다. 모든 기능이 로컬에서 동작하며 클라우드 계정이 필요 없습니다.

### 2-1. 신용거래 반대매매 가드

신용(빚투)으로 투자하는 고객이 반대매매를 피하려면 **언제까지·얼마를** 넣어야 하는지 알아야 합니다. 기준(140% 유지·120% 긴급·D+1/D+2·한시 유예)은 상담 과정에서도 틀린 안내가 나올 만큼 복잡합니다.

- 근거: 카카오페이증권 신용공여 1년 새 168.5% 증가, 상반기 민원 829% 증가, "120%면 된다"는 담보비율 오안내(실제 140%) 보도, 2026-11-06 한시 유예 공지. 출처와 입증 범위는 [src/docs/MARGIN_GUARD.md](src/docs/MARGIN_GUARD.md).
- 신용 매수 의도 → 시작 담보비율과 140%·120%까지의 하락률을 계산하고 확인 질문을 추가합니다. 기존 정책 엔진을 거쳐 `REQUIRE_CLARIFICATION`이 됩니다.
- 계좌 스냅샷 → 140% 회복에 필요한 입금액/상환액, 납부 기한·반대매매 예정일, 한시 유예 판정을 계산합니다.
- "담보비율 150% 아래로 내려가면 알려줘" → `notify_only` 알림 룰입니다(이전에는 '주가 하락' 룰로 잘못 해석됨).
- 규칙은 [config/margin_rules.json](src/skills/safe-trade-rule-builder/config/margin_rules.json)에만 두고, 모든 값에 출처를 붙입니다.

```powershell
$M = "src\skills\safe-trade-rule-builder"
python "$M\scripts\margin_check.py" assess --account "$M\examples\margin\misguided_after_deposit.json"
python "$M\scripts\rule_builder.py" --intent "삼성전자가 3% 떨어지면 신용으로 100만원어치 매수 후보로 알려줘" --parser deterministic --format markdown
python "$M\scripts\rule_builder.py" --intent "담보비율 120%만 맞추면 반대매매 안 되지?" --format markdown
```

오안내 사례를 본뜬 가상 계좌에서 "120%만 넘기면 된다"고 믿고 7,600만 원을 입금하면 담보비율은 127.2%가 됩니다. 그날 120% 미만이었기 때문에 **당일 140% 회복 의무가 남아 다음 날 반대매매 대상**이며, 추가로 6,400만 원 입금 또는 4,571만 원 상환이 필요하다고 안내합니다.

### 2-2. 안전 매매 룰

- 감정 점검: 손실 회피·본전 회복·FOMO·몰빵·조급함 표현이 있으면 주문 준비를 확인 질문으로 낮춥니다.
- 시간 조건: "장 초반 제외", "오전 제외", "장 마감 30분 전에만"을 종목 시장의 현지 시각으로 실제 판정합니다. 미국 종목은 뉴욕 시간 기준이라 서머타임 전후에도 정확합니다. 확인할 수 없는 "3일 연속" 조건은 통과시키지 않습니다.
- 종목 인식: API 키 없이 쓰는 오프라인 파서도 국내 23개·미국 15개 주요 종목과 6자리 코드·미국 티커를 인식합니다.
- 금액 인식: "10만원만", "50만원어치", "100만원 매수", "1,000,000원", "1억원"을 인식하고, "4만원 아래로"처럼 가격 조건인 금액은 주문 금액으로 보지 않습니다.
- 안전장치: 정책 엔진, 리스크 한도, 시세 freshness, broker/account provider, 중복 실행 차단(idempotency)·쿨다운.
- 실행 환경: 모두 로컬에서 동작합니다. 클라우드 계정이나 외부 저장소가 필요 없습니다(아래 "로컬 런타임").

아래 섹션은 투자자용 스킬의 세부 기능과 로컬 런타임 설명입니다.

## 핵심 기능

- GPT API 기반 LLM 우선 자연어 파싱, 실패 시 deterministic parser fallback
- Pydantic 기반 스키마 검증
- prompt injection 및 실주문 유도 표현 사전 차단
- policy, risk limit, prompt-security rule을 로컬 JSON에서 읽고, 파일을 바꾸면 TTL 뒤 다시 읽음(핫로딩)
- 감정적 의도 탐지 시 주문 준비를 clarification flow로 downgrade
- yfinance 기반 시장 데이터 조회
- 과거 데이터 기반 백테스트와 안전성 경고
- 마크다운 리포트 생성
- 로컬 런타임(`src/runtime/runtime_handler.py`)으로 룰 이벤트 평가
- 중복 실행 차단·쿨다운 상태 저장소: 메모리(기본) 또는 로컬 JSON 파일
- 변경 불가 감사 로그: 메모리(기본) 또는 로컬 JSONL 파일
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

## 로컬 런타임

`src/runtime/runtime_handler.py`의 `handle_event(event)`가 룰 이벤트(시세·브로커 상태·계좌 한도 포함)를 받아 다음 순서로 결정합니다. 모두 사용자 PC에서 실행되며 외부 서비스에 접속하지 않습니다.

1. 로컬 정책 룰 로드
2. 브로커/계좌/거래소/시세 freshness 점검
3. 트리거 조건 평가
4. 정책 결과와 상태 저장소를 DecisionEngine에서 조합
5. 감사 로그 저장
6. 한국어 사용자 행동 안내와 확인 체크리스트 반환

반환 decision:

- `STOP`: 안전장치 실패(내부 오류도 `STOP`으로 반환)
- `WAIT`: 조건 미충족 또는 중복 실행 차단
- `NOTIFY_ONLY`: 알림만 허용
- `MANUAL_CONFIRM`: 사용자가 수동 확인할 수 있는 후보
- `REQUIRE_CLARIFICATION`: 룰이 모호해 추가 확인 필요
- `BLOCK`: 정책상 차단

```powershell
python -X utf8 -c "import json,sys; sys.path.insert(0,'src/runtime'); import runtime_handler as h; e=json.load(open('src/runtime/sample_event.json',encoding='utf-8')); print(h.handle_event(e)['decision'])"
```

저장소 선택:

| 설정 | 동작 |
| --- | --- |
| 기본값 (`memory`) | 호출마다 새 메모리 저장소. 테스트·데모용 |
| `SAFE_TRADE_STATE_BACKEND=file` + `SAFE_TRADE_STATE_FILE` | 중복 차단·쿨다운을 로컬 JSON 파일에 유지. 실행이 바뀌어도 같은 결정이 다시 나오지 않음 |
| `SAFE_TRADE_DECISION_LOG_BACKEND=file` + `SAFE_TRADE_DECISION_LOG_FILE` | 감사 로그를 로컬 JSONL 파일에 한 줄씩 추가 |

## 환경변수

`.env.example`은 로컬 템플릿입니다. 실제 `.env`와 API key는 제출물에 포함하지 않습니다.

- `OPENAI_API_KEY`: LLM parser 사용 시 필요
- `SAFE_TRADE_RULE_LLM_MODEL`: GPT API parser 모델. 기본값 `gpt-4.1-mini`
- `SAFE_TRADE_RULE_LLM_TIMEOUT_SECONDS`: GPT API timeout. 기본값 `20`
- `SAFE_TRADE_ENV`: 실행 환경 표시. 기본값 `local`
- `SAFE_TRADE_STATE_BACKEND`: `memory`(기본) 또는 `file`
- `SAFE_TRADE_STATE_FILE`: `file` 백엔드의 상태 JSON 경로
- `SAFE_TRADE_DECISION_LOG_BACKEND`: `memory`(기본) 또는 `file`
- `SAFE_TRADE_DECISION_LOG_FILE`: `file` 백엔드의 감사 로그 JSONL 경로
- `SAFE_TRADE_METRICS_LOG`: `0`이면 표준 에러로 남기는 구조화 지표 로그를 끔. 기본값 `1`
- `SAFE_TRADE_CONFIG_TTL_SECONDS`: 정책 설정 캐시 TTL. 기본값 `60`
- `SAFE_TRADE_POLICY_CONFIG_PATH`: policy JSON 경로 override
- `SAFE_TRADE_RISK_LIMITS_PATH`: risk-limit JSON 경로 override
- `SAFE_TRADE_PROMPT_SECURITY_CONFIG_PATH`: prompt-security JSON 경로 override
- `KAKAOPAY_API_BASE_URL`, `KAKAOPAY_API_KEY`, `KAKAOPAY_API_SECRET`, `KAKAOPAY_ACCOUNT_ID`: 추후 API 연동용(현재 미사용)

정책성 설정은 기본적으로 `src/runtime/policy_rules.json`, `src/runtime/risk_limits.json`, `src/runtime/prompt_security_rules.json`을 사용합니다. 경로 override 파일을 읽지 못하면 패키지에 든 기본값을 쓰고, decision log에 사용된 config version, source, fallback 여부가 남습니다.

## 검증 명령

```powershell
python -m pytest -q
python tools\package_submission.py --check-only
python tools\package_submission.py
```

현재 기준:

- pytest: `188 passed`. `PYTHONPATH` 없이도 실행됩니다.
- 제출 구조: valid
- 플러그인 소스 어디에서도 클라우드 SDK를 import하지 않는다는 것을 테스트로 확인합니다.

추가 검증 문서:

- `src/docs/LLM_SMOKE_TEST.md`: 실제 GPT API Structured Output smoke test
- `src/docs/DUPLICATION_BOUNDARIES.md`: runtime/scripts 중복 경계

### 평가 감사 로그

- 정상 후보뿐 아니라 `STOP`, `WAIT`, `BLOCK`, `REQUIRE_CLARIFICATION`, 중복 차단 결과도 저장합니다.
- 새 결정은 idempotency key와 쿨다운을 함께 기록하고, 이미 기록된 key면 `WAIT / DUPLICATE_DECISION_BLOCKED`로 바꿉니다.
- 감사 로그 저장에 실패하면 평가를 `STOP`으로 반환합니다(fail-closed).
- 사용자별 조회에는 원문 ID가 아니라 해시 식별자를 사용합니다.

## 안전 고지

이 플러그인은 투자 조언, 종목 추천, 수익 보장, 실주문 시스템이 아닙니다. 백테스트는 과거 조건 발동 양상을 확인하는 안전성 검토이며, 미래 성과 예측이 아닙니다. 모든 주문 판단은 사용자의 수동 확인과 별도 증권사 화면에서 이루어져야 합니다.

---

## 💡 회고

1. **AWS 제거 (2026-11-18)**
   - 예선·본선 시기에는 룰 평가를 AWS Lambda + DynamoDB로 배포하고 트랜잭션, JWT 인증, EventBridge, AppConfig까지 붙였습니다.
   - 그러나 Codex 플러그인은 사용자 PC에서 스크립트로 동작하고, 배포된 런타임은 플러그인 흐름에서 쓰이지 않았으며, 심사자가 실행해 볼 수도 없었습니다. 스케줄 실행·시세 연결이 없어 "룰을 계속 지켜보는" 목적도 완성되지 않았습니다.
   - 그래서 클라우드 의존을 모두 걷어내고 로컬 기본값(메모리·파일 저장소, 로컬 JSON 설정)만 남겼습니다. 배포했던 AWS 리소스(CloudFormation 스택 2개, Lambda, DynamoDB 테이블 2개, S3 배포 버킷)는 데이터를 백업한 뒤 삭제했습니다. 이전 구현은 git 이력에 남아 있습니다.
2. **시스템 장애 Fail-Closed 보장**
   - 저장소나 설정 로드에 실패해도 예외를 밖으로 던지지 않고, 최상위 경계에서 구조화된 `STOP` 응답을 돌려줍니다.
