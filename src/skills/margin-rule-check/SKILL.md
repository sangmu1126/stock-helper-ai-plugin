---
name: margin-rule-check
description: 사내용(상담 품질·QA·개발자) 신용거래 규칙 점검. 상담 스크립트, 고객 안내 문구, 앱 설정에 적힌 담보비율·반대매매 일정이 공식 규칙(140% 유지, 120% 긴급, D+1 납부·D+2 반대매매, 한시 유예)과 맞는지 찾고, "120%면 반대매매 안 된다" 같은 잘못된 안내를 잡는다. 회사의 담보비율 계산 코드에 대해서는 규칙에서 경계 테스트를 생성한다. Use when an in-house team asks to verify margin/collateral (담보비율, 반대매매, 신용) wording, configs, or calculation logic against the rules.
---

# Margin Rule Check (사내용 신용거래 규칙 점검)

2026년 8월, 상담 과정에서 "담보비율 120% 이상이면 반대매매가 없다"는 안내가 나갔고 실제 기준(140%)과 달라 반대매매가 발생한 사례가 보도됐다. 이 스킬은 그런 안내가 **문서·스크립트·앱 설정·계산 코드에 남아 있는지** 배포 전에 찾는다.

규칙 값은 투자자용 스킬의 `safe-trade-rule-builder/config/margin_rules.json` 하나만 쓴다(출처 포함). 규칙이 바뀌면 그 파일만 고치면 두 스킬이 함께 바뀐다.

## 1. 안내 문구·스크립트·설정 점검

```bash
python scripts/margin_rule_check.py lint --repo <점검할 폴더> --out mrc-output
```

| 상태 | 뜻 | 조치 |
| --- | --- | --- |
| MISCONCEPTION | 140% 미만인 값으로 "반대매매 없음/안전"이라고 안내 | 반드시 고친다. 140% 미만은 담보부족, 120%는 긴급 기준이라는 사실로 바꾼다 |
| MISMATCH | 유지·긴급·유예·알림 기준이나 D+N 일정이 규칙과 다름 | 규칙 값으로 고친다 |
| REVIEW | 담보비율 숫자인데 어떤 기준인지 문장에 없음 | 문맥을 읽고 판단. 무관하면 같은 줄에 `mrc: ignore` |
| OK | 규칙과 일치 | — |

- 같은 줄에 기준이 여러 개 나오면(예: "120% 미만이면 당일 140%까지") 각 숫자가 그 줄에 나온 기준 중 하나와 맞으면 OK로 본다.
- 설정 키(`maintenance_ratio`, `emergency_ratio`, `watch_alert_ratio`, `liquidation_*_days`, `deposit_deadline_*`)도 검사한다.
- 종료 코드 1이면 고칠 것이 있다. CI에 넣어 배포 전에 막을 수 있다.

Codex가 할 일: 보고서의 각 줄을 열어 고객에게 나가는 문장을 규칙에 맞게 고치고(수정 diff는 담당자 검토), 다시 lint를 돌려 0건을 확인한다. 법률·준법 표현은 바꾸지 말고 숫자와 일정만 고친다.

## 2. 계산 로직 경계 테스트

```bash
python scripts/margin_rule_check.py gen-tests --out <저장소>/tests/margin_rules
```

- 담보비율 경계(150/149.9/140/139.9/130/129.9/120/119.9), 담보부족·긴급 반대매매 날짜(주말과 한국거래소 휴장일 건너뜀, 성탄절·연말 포함), 한시 유예 판정(회차·구간·기간) 21건을 만든다.
- 기대값은 투자자용 스킬의 계산 모듈(`margin_guard.py`)이 규칙 파일로 계산한다.
- 생성된 `mrc_adapter.py`에 회사 함수 3개(`classify_ratio`, `liquidation_date`, `grace_status`)를 연결하고 pytest를 돌린다. 연결하지 않으면 실패, 해당 기능이 없으면 `"skip"`.

## 시연

`examples/support-docs/`(잘못된 상담 스크립트·앱 설정)와 `examples/toy-margin-service/`(규칙과 어긋난 계산 모듈)는 가상 자료다. `*-fixed/`가 고친 상태다.

| 대상 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 문구·설정 lint | 고칠 것 5 (잘못된 "안전" 안내 2, 유지비율 130%, D+3 반대매매, 반대매매 3영업일 설정) | 0 |
| 계산 로직 테스트 21건 | 9 실패 | 21 통과 |

## 범위 밖

법률·준법 문구 판단, 전화 상담 녹취 분석, 실제 고객 계좌 계산(투자자용 스킬의 `margin_check.py assess` 사용), 입금 인정 마감 시각.
