# 카카오페이증권 안전 거래 Codex 플러그인

[![CI](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/sangmu1126/stock-helper-ai-plugin/actions/workflows/ci.yml)

카카오페이증권의 공개·검증 가능한 문제(반복되는 전산장애, 신용거래 반대매매 오안내)를 해결하는 Codex 플러그인입니다. 사내용 스킬 2개와 일반 투자자용 스킬 1개로 구성되며, **클라우드 계정도 외부 AI API도 없이 PC 하나에서** 동작합니다.

## 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 형태 | Codex 플러그인(스킬 3개 + 로컬 런타임), Python 3.11+ |
| 핵심 구조 | 판정은 결정적 코드가 맡고, 문장 이해·설명·코드 수정은 Codex가 맡음 |
| 근거 | 금감원 전산장애 통계, 담보비율 오안내 보도, 회사 공식 안내·공지, 거래소 발표 ([근거 문서](src/docs/MARKET_HOURS_EVIDENCE.md), [신용 가드 근거](src/docs/MARGIN_GUARD.md)) |
| 검증 | 자동 테스트와 ruff 린트를 GitHub Actions CI에서 실행(생성된 JUnit 테스트를 실제 JDK로 실행하는 것 포함). 합성 저장소·가상 자료로 수정 전후 재현, 공개 증권 저장소 5곳으로 오탐 평가 |
| 외부 연결 | 없음. 실시간 시세(yfinance)만 선택 사항 |

### 실행 기록과 외부 기여

- **공개 PR:** 한국투자증권 공식 예제의 폐지된 시간외 단일가 안내 9곳을 수정하는 [PR #91](https://github.com/koreainvestment/open-trading-api/pull/91)을 제출했습니다. 설명 문구만 변경했으며 해당 TR의 현행 제공 시간은 확정하지 않았습니다. PR 제출은 반영·승인을 의미하지 않습니다.
- **실제 CLI 기록:** [실행 요약](docs/media/demo-evidence/summary.json), [변경 전 경계 테스트](docs/media/demo-evidence/mhg-before-tests.txt), [수정 예제 경계 테스트](docs/media/demo-evidence/mhg-after-tests.txt), [상담 문구 점검](docs/media/demo-evidence/mrc-lint.txt), [반대매매 가드](docs/media/demo-evidence/margin-guard.txt), [달러 조건 룰](docs/media/demo-evidence/usd-rule.txt).
- **가격 알림 실사용 흐름 (0.7.0):** 빈 작업 폴더에서 [초안](docs/media/alert-flow/01-draft.txt) → [조건 확인](docs/media/alert-flow/02-confirm.txt) → [등록](docs/media/alert-flow/03-register.txt) → [감시](docs/media/alert-flow/04-watch.txt) → [알림](docs/media/alert-flow/05-notify.txt) → [Ctrl+C 중지](docs/media/alert-flow/06-stop.txt)까지 이어서 실행했습니다([요약](docs/media/alert-flow/summary.json)). 실제로 표시된 [Windows 알림 화면](docs/media/alert-flow/notification.png)도 남겼습니다.
  - **1~6단계는 합성 시세(`demo-fixture`)입니다.** 조건이 맞도록 만든 가짜 가격이며, 알림 제목에 `[DEMO]`가 붙습니다.
  - **[7단계](docs/media/alert-flow/07-real-quote.txt)는 실제 시세(Yahoo Finance)입니다.** 같은 룰을 실제 시세로 한 번 평가했습니다. 카카오는 Yahoo에 애프터마켓 시세가 없어 마지막 시세가 1시간 넘게 지난 정규장 종가였고, `STALE_QUOTE`로 알리지 않았습니다. TSLA는 미국 정규장 밖이라 `WAIT`였습니다. **실제 시세로 알림이 발송된 기록은 아직 없습니다.**
- **화면 촬영:** [캡처 안내와 현재 상태](docs/media/CAPTURE.md). 위 CLI 기록은 Codex 앱 화면 캡처나 실시간 수정 녹화가 아닙니다. 알림 화면만 실제 바탕화면을 잘라 저장했습니다.

CLI 기록은 `python tools/record_demo_evidence.py`로, 가격 알림 흐름은 `python tools/record_alert_flow.py --screenshot`(KRX 정규장 또는 애프터마켓 시간에 실행)으로 다시 생성할 수 있습니다. 작업·사용자 경로 접두어만 가렸고 AI 전체 대화 로그는 변경하지 않았습니다.

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
- **경계 시각 테스트:** 기준표에서 구간 경계 ±1초, 서머타임 전후, 특수일·휴장일 케이스를 생성합니다. Python 저장소는 pytest, Java·Kotlin 저장소는 JUnit 5(`--format junit`)로 만듭니다.
- **읽는 코드:** Python, Java·Kotlin(`LocalTime.of`), Spring cron(6필드), YAML·JSON·properties 설정, 주석·문서 속 시각.
- **CI와 PR 화면:** `--sarif`로 결과를 SARIF로 내보내면 GitHub code scanning이 PR의 해당 줄에 STALE·MISMATCH를 표시합니다. 이 저장소의 CI도 런타임 세션 설정을 이렇게 검사합니다.
- **기준표 변경 영향 미리보기:** 제도 변경 공지가 나오면 `impact`로 "새 기준표를 적용하면 어느 줄이 MISMATCH·STALE이 되는지"를 코드를 고치기 전에 봅니다.
- 표준 라이브러리만 씁니다.

```bash
python src/skills/market-hours-guard/scripts/mhg.py check-calendar --calendar src/skills/market-hours-guard/assets/calendar.demo.toml
python src/skills/market-hours-guard/scripts/mhg.py scan --repo src/skills/market-hours-guard/examples/toy-broker --calendar src/skills/market-hours-guard/assets/calendar.demo.toml
python src/skills/market-hours-guard/scripts/mhg.py gen-tests --calendar src/skills/market-hours-guard/assets/calendar.demo.toml --out mhg-output/junit --format junit --java-package toybroker
python src/skills/market-hours-guard/scripts/mhg.py scan --repo src/runtime --calendar src/skills/market-hours-guard/assets/calendar.demo.toml --sarif mhg-output/runtime.sarif
python -m pytest -q tests/market_hours_guard
```

합성 저장소(실제 회사 코드 아님) 결과입니다. Python판(`toy-broker`)과 Java판(`toy-broker-java`, Gradle·JUnit 5)이 같은 결과를 냅니다.

| 단계 | 정적 스캔 | 경계 테스트 50건 |
| --- | --- | --- |
| 수정 전 (`toy-broker`, `toy-broker-java`) | STALE 1 · DST_RISK 2 · AMBIGUOUS 1 · UNMAPPED 1 · MATCH 4 | 17 실패 |
| 수정 후 (`*-fixed`) | MATCH 16 (15개는 주석으로 의미 고정) | 50 통과 |

- 같은 `15:30`을 정규장 마감(정상), 과거 SOR 종료(변경 누락), 판단 보류로 구분합니다.
- 미국 장 시각을 한국시간으로 고정한 코드는 11월 1일 서머타임 해제 이후 케이스에서만 실패합니다.
- **수능일(2026-11-19)에는 정규장이 10:00~16:30, 애프터마켓이 17:00~20:00입니다.** 평소 시각을 쓰는 코드는 그날 09:00을 정규장으로, 15:30 이후를 장 종료로 잘못 판정합니다.
- **휴장일은 한국거래소가 공지한 달력(2026~2027년)을 씁니다.** 연말휴장일(12/31)처럼 공휴일이 아닌 휴장일을 모르는 코드는 그날 09:00을 정규장으로 판정합니다.
- 이 스킬로 투자자용 스킬과 로컬 런타임을 검사하면 거래시간 값이 모두 기준표와 일치합니다. 이 상태는 테스트로 고정돼 있습니다.
- 가상으로 SOR 종료를 21:00으로 바꾼 기준표를 `impact`에 넣으면, 주석을 단 2곳(라우터 상수, 정산 cron)이 새로 MISMATCH가 된다고 미리 알려 주고 종료 코드 1을 냅니다.

**공개 저장소 평가.** 증권사 공식 예제(한국투자, 키움)와 라이브러리·봇 등 공개 저장소 5곳에 돌렸습니다. 처음에는 769건 중 547건이 API 코드 목록(`4:10~20`), 종목코드(`"005930"`), 슬라이스(`row[9:21]`)를 시각으로 읽은 오탐이었습니다. 고친 뒤 223건 중 시각이 아닌 판정은 0건입니다. 한국투자증권 공식 예제에서는 2026-09-14에 폐지된 **시간외 단일가(16:00~18:00) 안내 9곳을 STALE로 찾았습니다.** 값만 같은 MATCH(일본 장 09:00 ↔ KRX 개장)와 1MB 넘는 파일 같은 한계도 함께 적었습니다 ([MARKET_HOURS_REAL_REPOS.md](src/docs/MARKET_HOURS_REAL_REPOS.md)).

자세한 설계는 [MARKET_HOURS_GUARD.md](src/docs/MARKET_HOURS_GUARD.md)에 있습니다.

## 2. 신용거래 규칙 점검 (`margin-rule-check`, 사내 상담 품질·QA·개발자)

보도된 담보비율 오안내는 상담 과정에서 "120%면 된다"고 안내한 사건이었습니다. 이 스킬은 그런 안내가 문서·스크립트·앱 설정·계산 코드에 남아 있는지 배포 전에 찾습니다. 규칙 값은 투자자용 스킬과 같은 파일(`config/margin_rules.json`)을 씁니다.

```bash
python src/skills/margin-rule-check/scripts/margin_rule_check.py lint --repo src/skills/margin-rule-check/examples/support-docs
python src/skills/margin-rule-check/scripts/margin_rule_check.py gen-tests --out mrc-output/tests
python src/skills/margin-rule-check/scripts/margin_rule_check.py gen-tests --out mrc-output/junit --format junit --java-package toymargin
python src/skills/margin-rule-check/scripts/margin_rule_check.py lint --repo src/skills/margin-rule-check/examples/support-docs --sarif mrc-output/mrc.sarif
```

- 문서는 md·txt·html·yaml·json 같은 텍스트와 **Word(.docx)** 를 읽습니다. Word는 문단 번호로 위치를 알려 줍니다. 옛 형식(.doc)과 한글(.hwp)은 읽지 않습니다.
- 계산 코드 테스트는 pytest와 **JUnit 5**(Java·Kotlin)로 만들 수 있습니다. Java판 가상 모듈(`toy-margin-service-java`)도 같은 결과를 냅니다.
- `--sarif`로 내보내면 잘못된 안내가 PR의 해당 줄(Word는 파일과 문단 번호)에 표시됩니다.

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

### 3-3. 로컬 가격 감시와 Windows 알림 (0.7.0)

가격 알림은 초안 생성에서 끝나지 않습니다. 확인한 알림 전용 규칙을 SQLite에 등록하고, 로컬 감시 프로세스가 조건을 반복 평가해 Windows 작업 표시줄 알림으로 제출합니다. 실주문은 하지 않습니다.

1. 아래 명령으로 초안을 저장하고 종목·통화·가격·세션·쿨다운을 확인합니다. 예시는 TSLA 200 USD 이하, 미국 정규장, 10분 쿨다운입니다. `price_cross_below`는 기존 평가기의 포함 비교(`<=`)를 사용하며, 엄격한 미만 비교가 아닙니다.

```powershell
$scripts = (Resolve-Path src/skills/safe-trade-rule-builder/scripts).Path
python "$scripts/rule_builder.py" --intent "테슬라가 200달러 아래로 내려가면 알려줘" --save-draft rule-output/tsla.json --format markdown
```

2. 값을 확인한 뒤 `--confirm`으로 등록합니다. 등록만으로 감시는 시작되지 않습니다.

```powershell
python "$scripts/alert_watch.py" add --draft rule-output/tsla.json --intent "테슬라가 200달러 아래로 내려가면 알려줘" --confirm
python "$scripts/alert_watch.py" setup-notifications
python "$scripts/alert_watch.py" test-notification
python "$scripts/alert_watch.py" run --interval 60
```

`run` 터미널을 열어 둔 동안 60초 간격으로 확인합니다. `Ctrl+C`는 감시를 종료하고 등록·쿨다운 기록은 남깁니다. 재부팅·절전·프로세스 종료 후에는 자동 재시작하지 않습니다. `run --once`는 한 번만 평가하는 검사이며 지속 감시가 아닙니다.

`setup-notifications`는 현재 사용자의 알림 앱 식별자와 표시명만 등록하며 알림 허용·방해 금지·보안 설정은 변경하지 않습니다. Windows 의존성은 `python -m pip install -r src/requirements.txt`로 설치합니다.

3. 다른 터미널에서 같은 프로젝트 폴더로 이동하고 `$scripts`를 다시 설정하면 상태·기록을 확인하고 중지·재개·삭제할 수 있습니다. 기본 DB는 현재 작업 폴더의 `rule-output/alerts.sqlite3`이며 다른 경로는 모든 명령에 동일하게 `--db <경로>`를 서브명령 앞에 지정합니다.

```powershell
python "$scripts/alert_watch.py" status
python "$scripts/alert_watch.py" list
python "$scripts/alert_watch.py" events
python "$scripts/alert_watch.py" pause <rule-id>
python "$scripts/alert_watch.py" resume <rule-id>
python "$scripts/alert_watch.py" remove <rule-id>
```

**범위와 한계:** 시세는 기존 yfinance 공급자(Yahoo Finance)를 사용하며 카카오페이증권 연동이 아닙니다. 15초보다 오래된 시세, 통화·종목 불일치, 휴장·장외 시각, 정책 위반에서는 발송하지 않습니다. Yahoo가 표시한 시세 지연은 KRX 20분, TSLA(나스닥) 15분입니다(2026-11-18 기록). 표시대로라면 이 공급자의 시세는 15초 기준을 넘어 알림이 발송되지 않습니다. 정규장 중 실제 시세 나이는 아직 재 보지 않았습니다. 폴링 사이의 가격 변동도 놓칠 수 있어 실시간·무누락 알림을 보장하지 않습니다. 가격 조건이 계속 맞으면 쿨다운마다 재알림할 수 있습니다. Windows 알림 설정·방해 금지에 따라 표시되지 않을 수 있으며 `submitted`는 OS 제출이지 수신·열람 확인이 아닙니다.

만료·연속일 조건, 뉴스·거래량·수동 검토 취소 조건은 자동으로 처리할 수 없어 등록 시 거절합니다. 계좌 자동 갱신·담보비율 지속 감시, 휴대폰 푸시·이메일, 로그인 시 자동 시작은 제공하지 않습니다. 발송 실패는 기록하고 새 시세에서 최소 60초 후 재시도합니다. OS 제출 직후 프로세스가 종료되면 기록 시점 차이로 재시작 후 중복이 생길 수 있어 정확히 한 번 전달을 보장하지 않습니다. 일시정지·삭제 전 이미 진행 중인 알림은 제출될 수 있습니다.

네이티브 알림은 Windows SDK 바인딩을 제공하는 [Windows-Toasts](https://windows-toasts.readthedocs.io/en/latest/)를 사용합니다. 초안·계좌·등록 DB·알림 이력은 `rule-output/` 아래 로컬 파일이므로 제출물이나 공개 저장소에 포함하지 마세요. 기존 0.6.0 설치본은 새 소스를 반영하도록 플러그인을 재설치하고 새 세션을 시작해야 합니다.

### 3-4. 로컬 런타임

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

- 테스트는 파이썬 경로 설정 없이 실행합니다. CI(GitHub Actions)에서 린트와 함께 실행합니다.
- 그중 4개는 생성된 JUnit 테스트를 실제로 컴파일·실행합니다. JDK와 JUnit 콘솔 런처(`JUNIT_CONSOLE_JAR`)가 없으면 로컬에서는 건너뛰고, CI에서는 실패로 처리합니다.
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
tests/                                # 스킬·런타임·로컬 알림 테스트
docs/reboot/                          # 주제 선정 과정, 결정 기록, 보관 자료
tools/package_submission.py           # 해커톤 제출용 패키징 도구(기록용)
```

## 한계

- 사내용 스킬은 합성 저장소, 가상 자료, 공개 저장소 5곳으로 검증했습니다. 실제 회사 저장소·문서에서의 효과는 측정하지 않았습니다.
- 거래시간 점검기의 MATCH는 "기준표에 있는 값"이라는 뜻입니다. 공개 저장소에서는 값만 같은 MATCH가 있었습니다(97건 중 37건, 수능일 기준을 고친 뒤 80건 중 20건). 그래서 고칠 대상은 문맥을 확인해 주석으로 의미를 고정합니다.
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
  - 사내용 스킬 두 개가 JUnit 5 테스트도 만들고(Java·Kotlin 저장소), 신용 규칙 점검이 Word(.docx)를 읽습니다. 공개 증권 저장소 5곳으로 거래시간 점검기를 평가해 오탐 원인 3가지를 고쳤습니다.
  - 두 사내용 스킬이 SARIF로 결과를 내보내 PR 화면에 표시하고, 거래시간 점검기에 기준표 변경 영향 미리보기(`impact`)를 더했습니다. 수능일 기준값이 우연히 MATCH 되던 문제를 고쳤습니다(값만 같은 MATCH 37건 → 20건).
  - 달러 가격 조건과 사내용 신용 규칙 점검을 추가하고, CI 린트를 다시 켰습니다.
