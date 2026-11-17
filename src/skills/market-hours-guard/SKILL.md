---
name: market-hours-guard
description: 증권사 거래시간 제도 변경(KRX 애프터마켓·프리마켓 도입, NXT 세션, SOR 적용 시간 변경, 미국 서머타임 전환, 거래시간 연장)을 코드·설정에 빠짐없이 반영했는지 점검한다. 승인된 거래시간 기준표(TOML)와 저장소의 시각 표현을 대조해 변경 누락(STALE), 서머타임 미반영(DST_RISK), 의미 불명확(AMBIGUOUS) 지점을 찾고, 수정 diff와 경계 시각 테스트를 만든 뒤 재검사한다. Use when a brokerage developer asks to apply or verify a trading-hours / market-session / SOR window / DST change across a repository.
---

# Market Hours Guard (거래시간 변경 점검기)

거래시간 제도가 바뀌면 세션 판정, 주문 라우팅(SOR), 배치 스케줄, 알림, 화면 문구가 함께 바뀌어야 한다.
이 스킬은 그 변경을 **빠짐없이, 같은 기준으로** 반영하도록 돕는다.

역할 분담:
- `scripts/mhg.py`(결정적 코드): 기준표 검증, 시각 표현 추출·판정, 경계 테스트 생성. 같은 입력이면 같은 결과.
- Codex(너): 판정 결과의 코드 문맥을 읽고 의미를 확정, 최소 수정 diff 작성, 어댑터 연결, 테스트 실행, 결과 보고.
- 사람(담당자): 기준표 값과 출처 승인, 의미가 불분명한 지점의 최종 판단.

## 지켜야 할 원칙

1. **기준표 값을 추측하지 않는다.** 거래시간·적용일은 사용자가 준 공지·문서에서만 가져오고 `source`를 단다. 출처가 없으면 묻는다.
2. 기준표를 새로 만들거나 바꾸면 **변경 내용을 보여주고 승인받은 뒤** 스캔한다.
3. 같은 숫자라도 의미가 다를 수 있다(15:30 = KRX 정규장 마감 / 과거 SOR 종료). 숫자 일괄 치환을 하지 않는다.
4. AMBIGUOUS·UNMAPPED는 코드를 읽고 판단하되, 확신이 없으면 추측해서 고치지 말고 사용자에게 근거와 함께 묻는다.
5. 테스트 통과는 "기준표에 적힌 동작"의 확인일 뿐이다. 장애가 없다는 보증이나 용량·성능 검증으로 말하지 않는다.
6. 사용자가 요청하지 않으면 커밋·푸시·배포하지 않는다.

## 작업 순서

스크립트 경로는 이 스킬 폴더 기준 `scripts/mhg.py`다. Python 3.11 이상, 외부 패키지 불필요.

### 1. 기준표 준비

- 저장소에 기준표(예: `market_hours.toml`)가 있으면 그것을 쓴다.
- 없으면 `assets/calendar.demo.toml`을 복사해 시작하되, 값은 사용자가 준 공지로 채우고 데모 값(`DEMO` 출처)은 지운다.
- 제도 변경을 반영할 때: 바뀌는 경계를 `[[retired]]`로 옮기고(`replaced_by`, `retired_on`, `source`), 새 값을 `[[boundary]]`에 둔다. 동작 계약은 `[[probe]]`에 적는다. 형식은 `references/calendar-format.md` 참고.
- 수능일처럼 거래소가 특정 날짜의 시간을 바꾸면 `[[special_day]]`와 날짜가 붙은 probe 구간(`dates`, `exclude_dates`)으로 적는다. 공지되지 않은 시간대는 `confirmed_until`로 테스트에서 뺀다.
- 휴장일은 `[holidays.<시장>]`에 거래소 공지 그대로 적고(`confirmed_through` 필수), probe에 `market`을 달면 그 시장의 휴장일 표본에서 평소 경계가 모두 `default`인지 검사한다.

```bash
python scripts/mhg.py check-calendar --calendar market_hours.toml
```

### 2. 스캔

```bash
python scripts/mhg.py scan --repo . --calendar market_hours.toml --out mhg-output
```

`mhg-output/report.md`를 읽는다. 종료 코드 1은 MISMATCH·STALE·DST_RISK가 있다는 뜻이다.

| 상태 | 뜻 | 너의 조치 |
| --- | --- | --- |
| MISMATCH | `mhg:` 주석으로 지정한 기준과 값이 다름 | 기준표 변경을 반영해 값 수정 |
| STALE | 폐기된 기준값을 문맥 근거와 함께 사용 | 코드 문맥 확인 후 새 값으로 수정, `mhg: <새 ID>` 주석 |
| DST_RISK | 미국 시각을 한국시각 고정값으로 사용 | 해당 시간대(`America/New_York`)로 변환해 비교하도록 수정 |
| AMBIGUOUS | 현행·폐기 기준에 모두 해당 | 코드 의미를 읽고 판단. 불확실하면 질문 |
| UNMAPPED | 거래시간 문맥인데 기준표에 없는 값 | 파생 값이면 `mhg: ID+5m`, 무관하면 `mhg: ignore — 이유`, 빠진 기준이면 기준표 추가 제안 |
| MATCH | 현행 기준과 일치 | 주석이 없으면 `mhg: <ID>` 추가를 권장 |

### 3. 수정

- 각 지점을 열어 주변 코드와 호출처를 확인한 뒤 **최소 diff**로 고친다.
- 고친 줄에는 의미 주석을 단다: `# mhg: SOR_END`, `// mhg: KRX_AFTER_OPEN`, YAML은 `# mhg: SOR_END+5m`.
  주석이 있으면 다음 제도 변경 때 기준표만 바꿔도 이 줄이 MISMATCH로 자동 검출된다.
- 같은 의미의 값이 여러 곳에 하드코딩되어 있으면 상수 하나로 모으는 것을 제안하되, 범위가 커지면 사용자에게 먼저 묻는다.

### 4. 경계 테스트

```bash
python scripts/mhg.py gen-tests --calendar market_hours.toml --out tests/market_hours
```

- 생성된 `tests/market_hours/mhg_adapter.py`의 `PROBES`를 저장소의 실제 함수에 연결한다. 각 함수는 한국시간 aware `datetime`을 받아 probe의 `expect` 형식(문자열·bool 등)을 돌려줘야 한다. 연결할 함수가 없으면 `"skip"`과 이유를 남긴다.
- **Java·Kotlin 저장소**는 JUnit 5로 만든다: `python scripts/mhg.py gen-tests --calendar market_hours.toml --out src/test/java/<패키지 경로> --format junit --java-package <패키지>`. `MarketHoursBoundaryTest.java`(케이스 내장, junit-jupiter만 필요)와 `MhgAdapter.java`가 생긴다. `MhgAdapter.PROBES`에 `OffsetDateTime`을 받는 메서드를 연결하고(`String.valueOf(결과)`가 expect와 같아야 함), 없는 동작은 `SKIP`에 넣는다. `gradle test`로 실행한다. 생성 파일은 ASCII만 쓴다.
- 저장소의 테스트 명령으로 실행한다(예: `python -m pytest tests/market_hours -q`).
- 실패하면 기대값과 실제값, 경계 시각(예: 서머타임 해제 후 23:29:59)을 근거로 코드를 고친다. 기준표 쪽이 틀렸다고 판단되면 고치지 말고 사용자에게 알린다.

### 5. 재검사와 보고

스캔과 테스트를 다시 돌려 아래 형식으로 보고한다.

```text
기준표: <이름> (<digest>)
수정 전: STALE n · DST_RISK n · AMBIGUOUS n · UNMAPPED n / 경계 테스트 실패 n
수정 후: ... / 경계 테스트 n건 통과
변경 파일: <파일:줄 — 무엇을 왜>
남은 확인 사항: <사람이 판단해야 할 것, 검사 범위 밖인 것>
```

CI에 넣으려면 `scan`(실패 시 종료 코드 1)과 생성된 테스트를 파이프라인에 추가하도록 제안한다. GitHub를 쓰면 `scan --sarif mhg.sarif`(경로는 저장소 루트 기준)로 내보내고 `github/codeql-action/upload-sarif`로 올리면 PR의 해당 줄에 판정이 표시된다.

### 6. 제도 변경 전에 영향 미리보기

```bash
python scripts/mhg.py impact --repo <저장소> --calendar market_hours.toml --new-calendar market_hours.next.toml
```

- 공지를 받아 새 기준표 초안을 만들었으면, 코드를 고치기 전에 `impact`로 판정이 바뀌는 줄(새 MISMATCH·STALE, 다른 기준으로 해석이 바뀌는 줄)을 보여 준다. 코드는 바꾸지 않는다.
- 새 실패가 생기면 종료 코드 1. 결과(`impact.md`)를 사용자와 함께 보고 수정 범위를 정한다.

## 시연

`examples/toy-broker/`는 일부러 변경을 누락한 합성 저장소(실제 회사 코드 아님)이고, `examples/toy-broker-fixed/`는 수정 후 기대 상태다. 같은 내용의 Java판(Gradle 프로젝트)이 `examples/toy-broker-java/`, `examples/toy-broker-java-fixed/`에 있다.
사용자가 시연을 요청하면 `examples/toy-broker`를 임시 폴더에 복사해 위 작업 순서를 그대로 수행한다(원본 예제는 수정하지 않는다).

## 범위 밖

시스템 용량·성능 테스트, 거래소·SOR 제공사 장애 원인 분석, 실주문, 코드에 적힌 휴장일 목록의 정적 대조(휴장일은 경계 테스트로만 확인), DB·원격 설정 서버에 저장된 값.

판정을 보고할 때 주의할 점(공개 저장소 평가에서 확인, `src/docs/MARKET_HOURS_REAL_REPOS.md`):
- 특수일 기준(예: 수능일 10:00)은 `requires_keyword = true`라 그날의 단어가 문맥에 있을 때만 MATCH가 된다. 새 특수일 기준을 넣을 때도 이 표시를 단다.
- MATCH는 "기준표에 있는 값"이라는 뜻이지 의미까지 맞다는 뜻이 아니다. 일본 장 09:00처럼 값만 같은 경우가 있으니, 고칠 대상의 MATCH도 문맥을 읽고 `mhg:` 주석으로 의미를 고정한다.
- 1MB를 넘는 파일은 읽지 않는다. 출력의 `검사하지 않은 파일` 목록을 사용자에게 그대로 알린다.
- 주변에 거래 관련 단어가 없는 시각(예: `if t <= "090000"`)은 보고하지 않을 수 있다.
