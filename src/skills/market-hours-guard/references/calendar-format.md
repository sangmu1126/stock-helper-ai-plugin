# 거래시간 기준표 형식 (TOML)

기준표는 담당자가 승인한 정답이다. 모든 값에 `source`를 달고, `source`는 `[sources]`에 정의한다.

```toml
[meta]
name = "카카오페이증권 거래시간 기준표"
local_tz = "Asia/Seoul"        # 코드가 기본으로 쓰는 현지 시간대
basis_date = 2026-11-18        # 서머타임 환산에 쓰는 기준 연도

[sources]
E5 = "머니투데이 2026-09-13: KRX 애프터마켓 2026-09-14 개장, 16:00~20:00"

[scan]
context_keywords = ["mts", "거래소"]   # 기본 어휘에 더할 '거래시간 문맥' 단어

[[boundary]]                    # 현행 경계
id = "KRX_AFTER_OPEN"           # 영문·숫자·밑줄
market = "KRX"
time = "16:00"                  # HH:MM 또는 HH:MM:SS
tz = "Asia/Seoul"               # 생략 시 meta.local_tz. 미국 시장은 "America/New_York"
meaning = "KRX 애프터마켓 시작"
keywords = ["after", "aftermarket", "애프터"]
effective_from = 2026-09-14     # 선택
source = "E5"

[[retired]]                     # 폐기된 경계 — 코드에 남아 있으면 STALE
id = "SOR_END_UNTIL_20260913"
time = "15:30"
meaning = "SOR 적용 종료 (애프터마켓 개장 전)"
keywords = ["sor", "smart", "rout", "최선집행"]
replaced_by = "SOR_END"         # 반드시 현행 boundary id
retired_on = 2026-09-14
source = "E6"

[[probe]]                       # 경계 테스트로 확인할 동작
id = "krx_session"
description = "KRX 세션 판정"
tz = "Asia/Seoul"               # 구간 시각의 시간대
default = "CLOSED"              # 어느 구간에도 없을 때 기대값
sample_dates = [2026-11-18]     # 거래일(평일)만

  [[probe.window]]              # [start, end) 반열린 구간, 같은 날 겹치면 오류
  start = "16:00"
  end = "20:00"
  expect = "AFTER"
  effective_from = 2026-09-14   # 선택: 이 날짜 이전 표본에는 적용 안 함
  source = "E5"
```

## 특수일 (거래소가 시간을 바꾼 날)

```toml
[[special_day]]
date = 2026-11-19
name = "2027학년도 수능일"
confirmed_until = "16:30"   # 이 시각 이후는 공지가 없어 경계 테스트를 만들지 않는다
source = "CSAT_2026"

  # probe 구간에 날짜 조건을 단다
  [[probe.window]]          # 평소 정규장: 수능일에는 적용 안 함
  start = "09:00"
  end = "15:30"
  expect = "REGULAR"
  exclude_dates = [2026-11-19]
  source = "KRX"

  [[probe.window]]          # 수능일 정규장: 그날만 적용
  start = "10:00"
  end = "16:30"
  expect = "REGULAR"
  dates = [2026-11-19]
  source = "CSAT_2026"
```

- `dates`가 있으면 그 날짜에만, `exclude_dates`에 든 날짜에는 적용하지 않는다.
- 특수일에는 그날 적용되는 구간의 경계와 함께, **그날 빠진 평소 구간의 경계**(예: 09:00, 15:30)도 검사한다. 하드코딩된 평소 시각이 특수일에 틀리는 것을 잡기 위해서다.
- 특수일 시각을 코드에 둘 때는 `# mhg: KRX_REGULAR_OPEN_CSAT_2026`처럼 특수일용 경계 ID로 주석을 단다.

## 키워드 일치 규칙

- 영문: 식별자를 단어로 쪼갠 토큰과 일치. 4자 이상 키워드는 접두어 일치(`rout` → router, routing).
  `US_OPEN_KST` → us, open, kst / `isUsRegularOpen` → is, us, regular, open.
- 한글: 문맥(현재 줄, 위 두 줄, 감싸는 함수·상위 키, 파일 경로)에 부분 문자열로 포함되면 일치.
- 같은 시각의 현행·폐기 기준이 있을 때, 폐기 기준 키워드가 더 많이 일치하면 STALE, 같으면 AMBIGUOUS.

## 코드 주석 (`mhg:`)

| 주석 | 뜻 |
| --- | --- |
| `# mhg: SOR_END` | 이 값은 SOR_END다. 기준표 값이 바뀌면 MISMATCH |
| `# mhg: SOR_END+5m` | SOR_END 5분 뒤(`-10m`, `+1h` 가능) |
| `# mhg: KRX_AFTER_OPEN, KRX_AFTER_CLOSE` | 한 줄의 여러 값에 순서대로 대응 |
| `# mhg: ignore — 이유` | 거래시간과 무관 |

주석은 같은 줄, 또는 시각 표현이 없는 바로 윗줄에 둔다. 생성 파일(`mhg:generated` 표식)은 스캔하지 않는다.
