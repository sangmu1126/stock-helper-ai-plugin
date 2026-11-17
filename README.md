# 카카오페이증권 안전 거래 Codex 플러그인

[![CI](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml)

카카오페이증권의 공개·검증 가능한 문제(반복되는 전산장애, 신용거래 반대매매 오안내)를 해결하는 Codex 플러그인입니다. 사내용 스킬 2개와 일반 투자자용 스킬 1개로 구성되며, **클라우드 계정도 외부 AI API도 없이 PC 하나에서** 동작합니다.

## 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 형태 | Codex 플러그인(스킬 3개 + 로컬 런타임), Python 3.11+ |
| 핵심 구조 | 판정은 결정적 코드가 맡고, 문장 이해·설명·코드 수정은 Codex가 맡음 |
| 근거 | 금감원 전산장애 통계, 담보비율 오안내 보도, 회사 공식 안내·공지, 거래소 발표 ([근거 문서](src/docs/MARKET_HOURS_EVIDENCE.md), [신용 가드 근거](src/docs/MARGIN_GUARD.md)) |
| 검증 | 테스트 255개와 ruff 린트를 GitHub Actions CI에서 실행. 합성 저장소·가상 자료로 수정 전후 재현 |
| 외부 연결 | 없음. 실시간 시세(yfinance)만 선택 사항 |

## 배경

2026년 AX 인재전쟁 해커톤의 카카오페이증권 과제에서 시작했습니다. 처음 만든 기능(감정적 매매를 안전한 룰 초안으로 바꾸기)은 회사 고유의 문제라는 공개 근거가 약했습니다. 그래서 이후 공개 자료로 입증되는 문제를 다시 찾았고, 문제와 해결이 직접 이어지는 기능 중심으로 다시 설계했습니다. 주제 선정 과정과 결정 기록은 [docs/reboot/](docs/reboot/DECISION_LOG.md)에 있습니다.

## 누가, 무엇을 하나

| 대상 | 스킬 | 해결하는 일 | 공개 근거 |
| --- | --- | --- | --- |
| **사내 개발자·QA** | `market-hours-guard` | 거래시간 제도 변경(애프터마켓, SOR 적용 시간, 미국 서머타임)과 특수일(수능일)·휴장일을 코드·설정에 빠짐없이 반영했는지 점검하고 경계 시각 테스트로 확인 | MTS 장애 42건, 대형 12개사 중 공동 1위·4년 연속 증가한 유일한 회사(금감원 자료). 애프터마켓 개장 첫날 SOR 시간 변경 과정의 장애 |
| **사내 상담 품질·QA·개발자** | `margin-rule-check` | 상담 스크립트·안내 문구·앱 설정·계산 코드의 담보비율·반대매매 일정이 공식 규칙과 맞는지 점검 | 상담 과정의 담보비율 오안내(120%로 안내, 실제 140%) 보도, 상반기 민원 829% 증가 |
| **일반 투자자** | `safe-trade-rule-builder` | 반대매매 기한·필요 금액·한시 유예를 출처와 함께 계산하고, 매매 요청을 수동 확인이 필요한 안전한 룰 초안으로 변환 | 신용공여 1년 새 168.5% 증가, 2026-11-06 반대매매 한시 유예 공지 |

## 동작 방식

```text
사용자 요청 (Codex 앱·CLI 채팅)
  → Codex가 요청에 맞는 스킬의 SKILL.md(작업 지침)를 읽음
  → Codex가 스크립트를 실행 (매매 요청은 Codex가 룰 JSON으로 만들어 전달)
  → 스크립트가 출처 붙은 규칙 파일로 계산·판정 (같은 입력이면 같은 결과)
  → Codex가 결과를 설명하고, 필요하면 코드·문서를 고친 뒤 다시 검사
```

별도 화면은 없고 Codex 채팅이 곧 인터페이스입니다. 같은 플러그인은 ChatGPT에서도 설치할 수 있습니다.

## 설치와 실행

Python 3.11 이상이 필요합니다.

```bash
git clone https://github.com/sangmu1126/stock-helper-ai-plugin.git
cd stock-helper-ai-plugin
pip install -r src/requirements.txt
python -m pytest -q
```

Windows 콘솔에서 한글이 깨지면 `$env:PYTHONIOENCODING="utf-8"`을 먼저 설정하세요.

점검 명령(`mhg.py scan`, `margin_rule_check.py lint`, `margin_check.py assess`)의 종료 코드 1은 실행 실패가 아니라 "고칠 것(또는 담보부족)이 있다"는 뜻입니다. CI에서 배포를 막는 용도로 씁니다.

**Codex에 플러그인으로 설치하려면**

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
   - "SOR 적용 시간이 20:00까지 늘어난 변경과 수능일 시간 변경이 이 저장소에 반영됐는지 점검해줘."
   - "상담 스크립트와 앱 설정에 담보비율 안내가 규칙과 다르게 적힌 곳을 찾아줘."
   - "담보비율 120%만 맞추면 반대매매 안 되지?"

## 1. 거래시간 변경 점검기 (`market-hours-guard`, 사내 개발자·QA)

거래시간 규칙은 세션 판정, 주문 라우팅(SOR), 배치, 알림, 화면 문구에 흩어져 있습니다. 제도가 바뀌거나 특수일이 오면 그 값들이 같은 기준으로 함께 바뀌어야 합니다. 이 스킬은 승인된 기준표(TOML, 모든 값에 출처)와 코드·설정의 시각 표현을 대조합니다.

- **판정:** `STALE`(폐기된 기준값), `DST_RISK`(미국 시각을 한국시간 고정값으로 씀), `AMBIGUOUS`(의미 불명확), `UNMAPPED`(기준표에 없는 값), `MISMATCH`(주석과 값 불일치)
- **주석으로 의미 고정:** Codex가 고친 줄에 `mhg: <기준 ID>`를 답니다. 다음에 기준표가 바뀌면 그 줄이 자동으로 `MISMATCH`가 됩니다.
- **경계 시각 테스트:** 기준표에서 구간 경계 ±1초, 서머타임 전후, 특수일·휴장일 케이스를 생성합니다.
- 표준 라이브러리만 씁니다.

```bash
python src/skills/market-hours-guard/scripts/mhg.py check-calendar --calendar src/skills/market-hours-guard/assets/calendar.demo.toml
python src/skills/market-hours-guard/scripts/mhg.py scan --repo src/skills/market-hours-guard/examples/toy-broker --calendar src/skills/market-hours-guard/assets/calendar.demo.toml
python -m pytest -q tests/market_hours_guard
```

합성 저장소(실제 회사 코드 아님) 결과:

| 단계 | 정적 스캔 | 경계 테스트 50건 |
| --- | --- | --- |
| 수정 전 (`toy-broker`) | STALE 1 · DST_RISK 2 · AMBIGUOUS 1 · UNMAPPED 1 · MATCH 4 | 17 실패 |
| 수정 후 (`toy-broker-fixed`) | MATCH 16 (15개는 주석으로 의미 고정) | 50 통과 |

- 같은 `15:30`을 정규장 마감(정상), 과거 SOR 종료(변경 누락), 판단 보류로 구분합니다.
- 미국 장 시각을 한국시간으로 고정한 코드는 11월 1일 서머타임 해제 이후 케이스에서만 실패합니다.
- **수능일(2026-11-19)에는 정규장이 10:00~16:30, 애프터마켓이 17:00~20:00입니다.** 평소 시각을 쓰는 코드는 그날 09:00을 정규장으로, 15:30 이후를 장 종료로 잘못 판정합니다.
- **휴장일은 한국거래소가 공지한 달력(2026~2027년)을 씁니다.** 연말휴장일(12/31)처럼 공휴일이 아닌 휴장일을 모르는 코드는 그날 09:00을 정규장으로 판정합니다.
- 이 스킬로 투자자용 스킬과 로컬 런타임을 검사하면 거래시간 값이 모두 기준표와 일치합니다. 이 상태는 테스트로 고정돼 있습니다.

자세한 설계는 [MARKET_HOURS_GUARD.md](src/docs/MARKET_HOURS_GUARD.md)에 있습니다.

## 2. 신용거래 규칙 점검 (`margin-rule-check`, 사내 상담 품질·QA·개발자)

보도된 담보비율 오안내는 상담 과정에서 "120%면 된다"고 안내한 사건이었습니다. 이 스킬은 그런 안내가 문서·스크립트·앱 설정·계산 코드에 남아 있는지 배포 전에 찾습니다. 규칙 값은 투자자용 스킬과 같은 파일(`config/margin_rules.json`)을 씁니다.

```bash
python src/skills/margin-rule-check/scripts/margin_rule_check.py lint --repo src/skills/margin-rule-check/examples/support-docs
python src/skills/margin-rule-check/scripts/margin_rule_check.py gen-tests --out mrc-output/tests
```

| 대상 (가상 자료) | 수정 전 | 수정 후 |
| --- | --- | --- |
| 상담 스크립트·앱 설정 lint | 고칠 것 5건: 잘못된 "안전" 안내 2, 유지비율 130%, D+3 반대매매, 반대매매 3영업일 설정 | 0건 |
| 계산 로직 경계 테스트 21건 (연말 휴장일을 건너뛰는 반대매매 날짜 포함) | 9 실패 | 21 통과 |

## 3. 안전 매매·반대매매 가드 (`safe-trade-rule-builder`, 일반 투자자)

투자자의 매수·매도·신용 요청을 바로 주문으로 연결하지 않습니다. 반대매매 위험, 감정 표현, 세션·시간 조건, 데이터 신뢰도, 계좌 한도, 중복 실행, 수동 확인 절차를 거친 룰 초안과 설명으로 바꿉니다. 실주문은 하지 않습니다.

### 3-1. 반대매매 가드

신용으로 투자하는 고객이 반대매매를 피하려면 언제까지, 얼마를 넣어야 하는지 알아야 합니다. 기준(140% 유지, 120% 긴급, D+1·D+2, 한시 유예)은 상담 과정에서도 틀릴 만큼 복잡합니다.

- 신용 매수 요청이면 시작 담보비율과 140%·120%까지의 하락률을 계산하고 확인 질문을 붙입니다(`REQUIRE_CLARIFICATION`).
- 계좌 스냅샷을 넣으면 140% 회복에 필요한 입금액·상환액, 반대매매 예정일, 한시 유예 판정을 계산합니다. 날짜는 주말과 한국거래소 휴장일을 뺀 영업일로 셉니다(예: 12/30 담보부족 → 12/31 연말휴장일·1/1 신정을 건너뛰어 1/5 반대매매).
- "담보비율 150% 아래로 내려가면 알려줘"는 알림 룰로 처리합니다.

```bash
python src/skills/safe-trade-rule-builder/scripts/margin_check.py assess --account src/skills/safe-trade-rule-builder/examples/margin/misguided_after_deposit.json
python src/skills/safe-trade-rule-builder/scripts/rule_builder.py --intent "담보비율 120%만 맞추면 반대매매 안 되지?" --format markdown
```

오안내 사례를 본뜬 가상 계좌에서 7,600만 원을 입금해 127.2%가 돼도, 그날 120% 미만이었다면 당일 140% 회복 의무가 남아 **다음 날 반대매매 대상**입니다. 이 기능은 추가로 6,400만 원 입금 또는 4,571만 원 상환이 필요하다고 안내합니다.

### 3-2. 안전 매매 룰

- **문장 해석:** Codex가 사용자 문장을 룰 JSON으로 만들어 넘기면(`--rule-json`) 스크립트가 형식 검증, 정규화, 안전 규칙, 정책 판단을 합니다. 외부 AI API는 쓰지 않습니다. JSON 없이 실행하면 오프라인 파서가 해석합니다.
- **세션과 시간 조건:** 정규장, KRX 애프터마켓(16~20시), "장 초반 제외", "오전 제외", "장 마감 30분 전에만"을 종목 시장의 현지 시각으로 판정합니다. 미국 종목은 뉴욕 시간 기준이라 서머타임 전후에도 맞습니다. 한국거래소·NYSE 휴장일과 수능일·미국 조기 폐장 같은 특수일 일정도 반영합니다. 휴장일 달력이 공지되지 않은 날짜, 공지되지 않은 세션, "3일 연속" 조건은 통과시키지 않습니다.
- **가격과 통화:** "4만원 아래로", "200달러 아래로", "$180 넘으면"을 통화와 함께 인식합니다. 원화 조건을 달러 시세와 비교하는 일은 막습니다(`TRIGGER_CURRENCY_MISMATCH`).
- **종목과 금액:** 국내 23개·미국 15개 주요 종목, 6자리 코드, 미국 티커를 인식합니다. "100만원 매수", "1,000,000원", "1억원" 같은 금액은 인식하고, 가격 조건에 쓰인 금액은 주문 금액으로 보지 않습니다.
- **감정 점검:** 손실 회복, FOMO, 몰빵, 조급함 표현이 있으면 확인 질문으로 낮춥니다.

```bash
python src/skills/safe-trade-rule-builder/scripts/rule_builder.py --intent "카카오가 전일 종가보다 3% 떨어지면 장 마감 30분 전에만 10만원만 매수 후보로 알려줘. 하루 한 번만." --rule-json src/skills/safe-trade-rule-builder/references/rule_json_example.json --format markdown
python src/skills/safe-trade-rule-builder/scripts/rule_builder.py --intent "테슬라가 200달러 아래로 내려가면 알려줘" --format markdown
python src/skills/safe-trade-rule-builder/scripts/rule_builder.py --intent "카카오가 3% 떨어지면 알려줘" --backtest --provider demo-fixture --format markdown
```

### 3-3. 로컬 런타임

`src/runtime/runtime_handler.py`의 `handle_event(event)`가 룰 이벤트(시세, 브로커 상태, 계좌 한도 포함)를 받아 결정을 냅니다. 결정은 `STOP`, `WAIT`, `NOTIFY_ONLY`, `MANUAL_CONFIRM`, `REQUIRE_CLARIFICATION`, `BLOCK` 중 하나입니다. 세션 시간, 휴장일, 특수일은 `src/runtime/market_sessions.json`에 있고, 스킬과 런타임이 함께 씁니다.

| 설정 | 동작 |
| --- | --- |
| 기본값 (`memory`) | 호출마다 새 메모리 저장소. 테스트·데모용 |
| `SAFE_TRADE_STATE_BACKEND=file` + `SAFE_TRADE_STATE_FILE` | 중복 실행 차단·쿨다운을 로컬 JSON 파일에 유지. 실행이 바뀌어도 같은 결정이 다시 나오지 않음 |
| `SAFE_TRADE_DECISION_LOG_BACKEND=file` + `SAFE_TRADE_DECISION_LOG_FILE` | 감사 로그를 로컬 JSONL 파일에 추가 |
| `SAFE_TRADE_METRICS_LOG=0` | 표준 에러로 남기는 지표 로그 끄기 |
| `SAFE_TRADE_POLICY_CONFIG_PATH` 등 | 정책·리스크·프롬프트 보안 규칙 JSON 경로 바꾸기(재시작 없이 다시 읽음) |

## 설계 결정

- **판정은 코드, 이해는 Codex.** 숫자와 규칙 판정을 AI에 맡기지 않습니다. Codex는 문장 이해, 룰 JSON 작성, 결과 설명, 코드 수정을 맡습니다.
- **외부 AI API 없음.** Codex 자체가 언어 모델이라, 스크립트 안에서 다시 AI API를 부르는 것은 중복 비용이자 실패 지점이었습니다. 그래서 제거했습니다.
- **클라우드 없음.** 처음에는 AWS Lambda·DynamoDB로 배포했지만 플러그인 흐름에서 쓰이지 않았고 심사자·사용자가 실행해 볼 수도 없었습니다. 로컬 저장소로 같은 기능(중복 차단, 쿨다운, 감사 로그)을 유지하고 AWS 리소스는 백업 후 삭제했습니다.
- **모든 기준값에 출처.** 거래시간, 휴장일, 140%·120%, 한시 유예, 수능일 일정은 출처 ID가 붙은 설정 파일에만 있고, 출처 없는 규칙은 로드 단계에서 거부합니다.
- **같은 기준 공유.** 런타임 세션 설정과 거래시간 기준표, 투자자용 반대매매 계산과 사내용 규칙 점검이 같은 값을 쓰는지 테스트가 지킵니다.
- **확인 못 하면 통과 안 함.** 공지되지 않은 세션, 휴장일 달력 범위 밖 날짜, 통화가 다른 가격 조건, 단일 시세로 확인할 수 없는 조건, 저장소·설정 오류는 모두 `WAIT`나 `STOP`으로 처리합니다.

## 검증

```bash
python -m pytest -q
ruff check src tests tools
```

- 테스트 255개가 파이썬 경로 설정 없이 통과합니다. CI(GitHub Actions)에서 린트와 함께 실행합니다.
- 플러그인 소스에 클라우드 SDK나 외부 AI API SDK가 없다는 것도 테스트로 확인합니다.

## 프로젝트 구조

```text
src/                                  # Codex 플러그인 루트
├── .codex-plugin/plugin.json
├── skills/
│   ├── market-hours-guard/           # 사내 개발자·QA: 거래시간 변경 점검
│   ├── margin-rule-check/            # 사내 상담 품질·QA·개발자: 신용거래 규칙 점검
│   └── safe-trade-rule-builder/      # 일반 투자자: 반대매매 가드 + 안전 매매 룰
├── runtime/                          # 룰을 평가하는 로컬 런타임 (세션 설정 공용)
├── docs/                             # 근거·설계 문서, 프로젝트 요약
└── requirements.txt
tests/                                # 테스트 255개
docs/reboot/                          # 주제 선정 과정, 결정 기록, 보관 자료
tools/package_submission.py           # 해커톤 제출용 패키징 도구(기록용)
```

## 한계

- 사내용 스킬은 합성 저장소와 가상 자료로 검증했습니다. 실제 회사 저장소·문서에서의 효과는 측정하지 않았습니다.
- 담보비율 계산식은 공식 안내에 없어 업계 일반식을 쓰며, 출력에 "앱 표시값 우선"을 표시합니다.
- 휴장일 달력은 거래소가 공지한 2027년 말까지만 들어 있습니다. 그 뒤 날짜는 세션 판정에서 `WAIT`로 두고 반대매매 날짜 계산에는 경고를 붙이므로, 매년 공지를 받아 갱신해야 합니다. 특수일은 공지가 확인된 날만 넣습니다.
- 카카오페이증권 공개 주문·계좌 API가 없어 시세는 yfinance(선택)나 데모 시세를 쓰고, 계좌 정보는 사용자가 입력합니다.
- 조건을 계속 지켜보다 알리는 상시 감시는 범위 밖입니다. 요청한 시점의 값으로 판단합니다.

## 안전 고지

이 플러그인은 투자 조언, 종목 추천, 수익 보장, 실주문 시스템이 아닙니다. 백테스트는 과거 조건 발동 양상을 보는 안전성 검토이지 미래 성과 예측이 아닙니다. 모든 주문 판단은 사용자가 증권사 화면에서 직접 확인해야 합니다.

## 변경 이력

- **2026-07 (해커톤 예선):** Safe Trade Rule Builder. 감정적 매매 의도를 안전한 룰 초안으로 바꾸고, AWS Lambda·DynamoDB 런타임과 GPT API 파서를 붙였습니다.
- **2026-11 (재설계):** 공개 근거를 다시 조사해 거래시간 변경 점검기와 반대매매 가드를 추가하고, 사용자 대상별로 재정리했습니다.
- **2026-11 (정리·확장):**
  - AWS를 제거해 로컬 전용으로 바꾸고, 외부 AI API를 제거했습니다(Codex가 룰 JSON 작성).
  - 세션 판정을 공통화했습니다(애프터마켓, 수능일, 로컬 런타임 시간 조건).
  - 한국거래소·NYSE 공식 휴장일 달력(2026~2027)과 미국 조기 폐장을 세션 판정, 반대매매 영업일 계산, 두 사내용 스킬의 테스트 생성에 반영했습니다.
  - 달러 가격 조건과 사내용 신용 규칙 점검을 추가하고, CI 린트를 다시 켰습니다.
