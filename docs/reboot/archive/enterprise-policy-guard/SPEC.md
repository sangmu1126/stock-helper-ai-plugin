# Securities Rule Guard 구현 스펙

버전: 2.0-draft  
기준일: 2026-11-18 (Asia/Seoul)  
상태: 설계 명세. 아래 신규 CLI·스킬·테스트는 아직 미구현.  
관련 문서: [제품 설계](DESIGN.md), [문제·기술 근거](EVIDENCE.md)

## 1. 제품 경계

| 항목 | 계약 |
| --- | --- |
| 패키지 ID | securities-rule-guard |
| 스킬 ID | review-securities-policy |
| 직접 사용자 | 카카오페이증권 개발·QA·상담 지식관리 담당자 |
| 입력 | 승인 정책 JSON, 출처 catalog, 대상 매핑 JSON, 로컬 Markdown·JSON |
| 결과 | 불일치·검토 필요·범위 보고, 근거 snapshot, 회귀 테스트 초안 |
| 실행 방식 | Codex 스킬 + Python 로컬 CLI |
| 상태 | PASS / FAIL / NEEDS_REVIEW / ERROR |
| 외부 변경 | 검사 명령은 원본 수정·네트워크·게시·병합을 하지 않음 |
| 수정 | Codex가 사용자 요청에 따라 별도 diff 작성, 재검사 |
| 검증 범위 | 등록·지원된 정적 안내와 설정. 실주문 로직·법적 준수 인증은 아님 |

## 2. 기술과 개발 도구

아래는 프로젝트의 호환 버전 범위다. 구현 시 검증한 정확한 버전을 lockfile에 고정하며 최신 버전이라고 주장하지 않는다.

| 영역 | 선택 | 역할 |
| --- | --- | --- |
| 언어 | CPython >=3.12,<3.13 | 표준 CLI·파일·정밀 수치 처리 |
| 모델 | Pydantic >=2.8,<3 | strict 스키마, enum, 참조, JSON Schema |
| 수치 | 표준 decimal.Decimal | 임계값의 십진 정확 비교 |
| JSON | 표준 json | 중복 키·NaN 거부, Pointer 해석용 입력 |
| Markdown 추출 | 고정 표식 블록 파서 | 위치를 보존한 지원 문법만 해석 |
| 보고 | Jinja2 >=3.1.6,<4 | 고정 Markdown 템플릿, StrictUndefined |
| CLI | argparse | audit·generate-tests 명령 |
| 무결성 | hashlib, pathlib, tempfile | 입력 해시·경로·출력 확정 |
| 시간 | datetime | 명시 offset의 적용 시각 비교 |
| 테스트 | pytest >=8,<9 | 단위·통합·생성 검사 실행 |
| 의존성 | uv, pyproject.toml, uv.lock | 고정 환경·재현 가능한 설치 |
| 품질 | Ruff >=0.6,<1 | lint·format |
| CI | GitHub Actions | Windows 11 대응 runner·Ubuntu 24.04, Python 3.12 |
| 배포 | 표준 zipfile | 제출 패키지 생성·필수 파일 검사 |

Windows 개발 PC와 CI runner의 OS 버전을 각각 기록한다. 최소 Codex 버전은 실제 설치·로드 테스트 후 고정한다.

공식 기능 확인 자료는 [EVIDENCE의 T1~T7](EVIDENCE.md)에 있다. CLI에는 별도 LLM API·API 키·AWS·MCP·벡터 DB가 필요하지 않다. 실사용 조직의 Codex 계정과 데이터 처리 정책은 호스트에서 적용한다.

Python 소스 AST, YAML, PDF, 웹 페이지 수집, 실시간 상담 녹취 분석은 후속 adapter다. MVP 지원으로 표시하지 않는다. 특히 자바·코틀린 서비스 코드를 Python 테스트로 검증했다고 주장하지 않는다.

## 3. 개발·제출 구조

신규 프로젝트 루트는 prototype/securities-rule-guard/다. 현재 저장소의 기존 src/는 유지한다.

```text
prototype/securities-rule-guard/
  src/                                  # 제출 ZIP의 src/
    .codex-plugin/plugin.json
    pyproject.toml
    uv.lock
    requirements.txt
    skills/review-securities-policy/
      SKILL.md
      scripts/
        ruleguard.py
        rule_guard/
          __init__.py
          cli.py
          models.py
          source_catalog.py
          policy_pack.py
          target_registry.py
          adapters/
            json_claim.py
            markdown_claim.py
          comparator.py
          coverage.py
          report.py
          test_generator.py
          workspace.py
      assets/
        review.md.j2
        test_policy_consistency.py.j2
      references/
        source-catalog.json
        supported-grammar.md
    schemas/
    examples/synthetic-credit-policy/
    docs/
      DESIGN.md
      SPEC.md
      EVIDENCE.md
  tests/
    unit/
    integration/
    fixtures/
  tools/package_submission.py
  .github/workflows/ci.yml
  README.md
  logs/
```

pyproject는 tool.uv.package=false로 두고 scripts/ 아래 일반 package import를 사용한다. JSON Schema는 Pydantic 모델에서 생성한다. requirements.txt는 lockfile에서 실행 의존성만 export한다.

## 4. 공통 데이터 계약

모든 모델은 extra=forbid다. json.loads 이후 strict=True로 검증한다. JSON 중복 키·NaN·Infinity와 지정하지 않은 필드는 거부한다.

ID 형식은 [a-z][a-z0-9_-]{0,63}, 상대 경로는 workspace 내부로 제한한다. 제품 값·컨텍스트·규칙 ID는 자유문 추론 대신 명시된 enum·ID로 연결한다.

decimal 값은 소수 문자열로 받는다. JSON float를 반올림해 사용하지 않는다. 퍼센트 값의 단위는 percent_points로 고정한다. 값 140은 140%이며 1.4와 자동 동치로 처리하지 않는다.

### 4.1 SourceCatalog

각 source는 source_id, kind, title, url, published_at, checked_at, effective_from, effective_to, summary, summary_sha256를 갖는다. 알 수 없는 날짜는 null이다.

kind는 official_reference / approved_internal_reference / news_background / synthetic_reference다. 뉴스는 문제 배경이며 운영 기준의 직접 근거로 승인할 수 없다. 합성 시연에는 synthetic_reference를 쓰고 이를 회사 승인 자료로 표시하지 않는다.

패키지에 원문을 저장하지 않았다면 content_sha256는 null이다. summary 해시를 원문 해시로 대신하지 않는다. 원문 전문의 무단 복제 대신 출처·필요한 짧은 발췌와 검토 기록을 사용한다.

### 4.2 PolicyPack

```json
{
  "schema_version": "ruleguard-policy.v1",
  "pack_id": "demo-credit",
  "version": "1",
  "organization": "kakaopay-securities",
  "mode": "synthetic",
  "approval": {
    "status": "approved_for_demo",
    "reviewer_id": "demo-reviewer",
    "approved_content_digest": "<computed-sha256>"
  },
  "rules": [
    {
      "rule_id": "restore-urgent",
      "semantic_key": "credit.collateral.restoration",
      "context_id": "credit-urgent",
      "value": "140",
      "unit": "percent_points",
      "operator": "gte",
      "effective_from": "2026-11-18T00:00:00+09:00",
      "effective_to": null,
      "source_refs": ["synthetic-credit-reference"]
    }
  ]
}
```

위는 스키마 설명용이다. digest placeholder를 가진 채 실행 가능한 fixture로 배포하지 않는다. 예제 생성 시 코드가 실제 digest를 계산한다.

approval.status는 draft / approved_for_demo / approved다. 내부 기준이 없으면 synthetic 모드만 사용한다. approved는 검토 확인 기록이며 전자서명·직원 신원 인증은 아니다.

운영 approved pack은 reviewer_id, reviewed_at, content digest가 필요하다. digest는 approval 블록을 제외한 정규화 정책과 참조 출처 snapshot으로 계산한다. 기준·출처 변경 시 기존 승인은 무효다.

rule은 semantic_key·context_id·적용 구간이 동일한 범위에서 유일해야 한다. 겹치는 구간에 상충 값이 있으면 POLICY_CONFLICT다. 반열림 구간 [effective_from, effective_to)로 비교하고 날짜만 있는 시각을 임의 해석하지 않는다.

공개 문서에서 적용일을 모르는 기준은 draft다. 스킬이 마음대로 날짜를 채워 approved로 바꾸지 않는다.

### 4.3 TargetRegistry

```json
{
  "schema_version": "ruleguard-targets.v1",
  "registry_id": "demo-targets",
  "scope_files": ["docs/credit-guide.md", "config/credit.json"],
  "mappings": [
    {
      "target_id": "guide-restore",
      "path": "docs/credit-guide.md",
      "adapter": "markdown_claim_v1",
      "selector": "restore-guide",
      "rule_id": "restore-urgent",
      "context_id": "credit-urgent"
    },
    {
      "target_id": "config-restore",
      "path": "config/credit.json",
      "adapter": "json_claim_v1",
      "selector": "/credit/urgent_restore",
      "rule_id": "restore-urgent",
      "context_id": "credit-urgent"
    }
  ]
}
```

초기 매핑은 Codex가 제안하고 담당자가 의미·대상을 검토한다. registry 검토 기록은 정책 승인과 별도로 관리한다. 검토되지 않은 매핑은 실행할 수 있으나 PASS를 만들지 못한다.

scope_files는 검수 대상의 명시적 목록이다. 디렉터리 전체 검수라는 표현을 자동 사용하지 않는다. 대상 파일과 승인 pack·catalog가 같은 실파일·같은 해시이면 기준/대상 분리 오류로 처리한다.

### 4.4 ObservedClaim

엔진만 생성하는 모델이다. target_id, rule_id, context_id, value, unit, operator, file, start_line, end_line, source_sha256, extraction_status를 갖는다.

LLM이 입력한 observed value를 그대로 비교 결과로 사용하지 않는다. adapter가 실제 target bytes에서 다시 추출한다. 추출 실패는 숫자 기본값이나 이전 결과로 대체하지 않는다.

## 5. Adapter 명세

### 5.1 markdown_claim_v1

지원 형식은 다음 고정 블록이다. 예시는 합성 오류 문구다.

```markdown
<!-- ruleguard:claim id="restore-guide" context="credit-urgent" -->
담보 회복 기준: 120% 이상
<!-- /ruleguard:claim -->
```

블록 ID·context를 검증하고 본문 한 줄의 역할 라벨·숫자·%·연산자를 읽는다. 역할 라벨은 지원 문법 목록에 등록된 것만 허용한다. 다중 문장·추가 수치·중첩 블록·미지원 표현은 NEEDS_REVIEW다.

이상→gte, 초과→gt, 미만→lt, 이하→lte로 매핑한다. “120% 미만”과 “120% 이상”을 동치로 취급하지 않는다.

context는 검토된 표식의 문맥 선언이다. 주변 자유문 전체의 의미를 자동 증명한 것으로 표시하지 않는다. 표식 밖 % 수치 문장을 탐색해 UNMAPPED_CLAIM_CANDIDATE로 남긴다.

### 5.2 json_claim_v1

JSON Pointer가 가리키는 객체는 아래 필드를 갖는다.

```json
{
  "value": "120",
  "unit": "percent_points",
  "operator": "gte",
  "context_id": "credit-urgent"
}
```

문자열 수치·단위·연산자·context를 검증한다. Pointer의 ~0·~1 escape, 배열 index를 명시적으로 처리한다. 없는 위치나 다른 자료형은 판정 불가다.

JSON 내 각 대상 위치의 정확한 행은 위치를 추적하는 제한 JSON reader로 기록한다. 구현 초기에는 Pointer와 파일 전체 hash만 지원할 수 있지만, 줄 위치를 확보하기 전 그 adapter에 파일:행 지원을 완료했다고 쓰지 않는다. 같은 키 이름의 첫 등장 행을 정답 위치로 사용하는 방식은 금지한다.

검수 범위의 임계값 후보가 다른 경로에 있으면 누락 후보로 보고한다. 일반 숫자와 금융 규칙을 자동 확정하지 않는다.

## 6. 비교 엔진과 커버리지

고정 비교 순서는 다음과 같다.

1. pack·출처·registry 구조와 검토 digest 확인.
2. as-of 시점에 적용되는 규칙 선택.
3. 대상 파일 existence·hash·중복 mapping 검사.
4. adapter로 관찰값 추출.
5. 의미 키·context·단위 확인.
6. 정규화 수치·연산자 비교.
7. 미지원·누락 항목과 coverage 계산.
8. findings·snapshot·보고서 생성.

단위·context가 다르면 임의 변환·조건 확장을 하지 않는다. 여러 기준이 적용될 수 있으면 사람이 선택해야 한다. MVP는 자유로운 조건식을 실행하거나 금융 규정의 예외를 자동 추론하지 않는다.

coverage는 다음 수를 항상 보고한다.

- 선언된 scope 파일 수, 실제 읽은 파일 수.
- 등록 target 수, 추출 성공 수, 비교 완료 수.
- FAIL·NEEDS_REVIEW 수.
- 매핑되지 않은 표식·수치 문장 후보 수.

숫자 후보 탐색이 모든 문장을 포괄하지는 않는다. “등록 대상의 검사 비율”과 “회사 전체 커버리지”를 혼동하지 않는다.

## 7. 결과·종료 코드

| 상태 | 조건 | exit |
| --- | --- | --- |
| PASS | 대상이 1개 이상, 승인·매핑 유효, 전부 비교 완료, 미해결 항목 0 | 0 |
| FAIL | 하나 이상 확인된 불일치 | 1 |
| NEEDS_REVIEW | 불일치는 없지만 미승인·미지원·미확인 항목 존재 | 2 |
| ERROR | 잘못된 인수·손상 파일·경로·환경 오류로 실행 불가 | 3 |

FAIL과 NEEDS_REVIEW가 동시에 있으면 전체 FAIL로 하되 미확인 항목을 유지한다. 입력 전체가 처리 불가인 ERROR는 다른 상태보다 우선한다. PASS는 법적 준수나 사업 승인과 동일하지 않다.

문제 코드는 VALUE_MISMATCH, OPERATOR_MISMATCH, UNIT_MISMATCH, CONTEXT_UNVERIFIED, APPROVAL_REQUIRED, APPROVAL_STALE, POLICY_CONFLICT, NO_EFFECTIVE_RULE, EXTRACTION_UNSUPPORTED, TARGET_MISSING, UNMAPPED_CLAIM_CANDIDATE, EMPTY_SCOPE 등이다.

잘못된 경로·출력 충돌·한도 초과 등 실행 오류는 별도 error code를 사용한다.

## 8. CLI 계약

아래 명령은 신규 프로젝트 루트를 기준으로 한 구현 후 계약이다.

```powershell
uv sync --project src --locked

uv run --project src --locked python src/skills/review-securities-policy/scripts/ruleguard.py audit --workspace work/demo --policy policy.json --targets targets.json --as-of 2026-11-18T10:00:00+09:00 --out out/run-001

uv run --project src --locked python src/skills/review-securities-policy/scripts/ruleguard.py generate-tests --workspace work/demo --policy policy.json --targets targets.json --as-of 2026-11-18T10:00:00+09:00 --out out/tests-001
```

workspace는 cwd 기준, 나머지 사용자 파일 경로는 workspace 기준이다. as-of는 필수이며 OS 시각을 묵시적 적용 시각으로 사용하지 않는다.

두 명령 모두 실제 입력에서 검증을 다시 수행한다. 생성 테스트는 현재 불일치가 있어도 만들 수 있지만 미승인 기준이나 미해결 mapping을 확정 기대값으로 내보내지 않는다.

stdout은 JSON object 한 개, stderr는 민감한 원문이 없는 짧은 진단이다. argparse 오류도 JSON으로 변환한다.

```json
{
  "schema_version": "ruleguard-result.v1",
  "status": "FAIL",
  "mode": "synthetic",
  "as_of": "2026-11-18T10:00:00+09:00",
  "findings": [
    {
      "code": "VALUE_MISMATCH",
      "target_id": "guide-restore",
      "rule_id": "restore-urgent",
      "expected": {"value": "140", "unit": "percent_points", "operator": "gte"},
      "observed": {"value": "120", "unit": "percent_points", "operator": "gte"},
      "location": {"path": "docs/credit-guide.md", "start_line": 2},
      "source_refs": ["synthetic-credit-reference"]
    }
  ],
  "unresolved": [],
  "coverage": {"registered": 2, "extracted": 2, "compared": 2},
  "output_dir": "out/run-001"
}
```

기타 필수 메타데이터는 engine_version, pack_digest, registry_digest, target manifest digest, generated_at이다. 출력 예시는 핵심 필드 설명용이며 전체 스키마는 구현 모델에서 생성한다.

## 9. 회귀 테스트 생성

생성물은 test_policy_consistency.py, approved_expectations.json, README.md다. 승인 기준의 값·단위·연산자·시점·context와 digest를 기대값으로 고정한다.

테스트는 실제 target 파일을 adapter로 재독해 비교한다. 기대값을 현재 target에서 생성하거나 수정된 기준을 자동 수용하지 않는다. 기준이 바뀌면 테스트 갱신을 요구한다.

이는 문서·설정의 정적 회귀 테스트다. pytest.parametrized 경계값으로 실제 서비스가 안전하다고 주장하지 않는다. 동작 테스트는 후속 기능이며 실제 시스템과 분리된 fixture로만 시연할 경우 반드시 그렇게 표시한다.

생성 코드는 고정 템플릿을 쓰고 사용자 문자열을 Python 소스로 직접 삽입하지 않는다. 기대값은 JSON 데이터에서 읽는다. CLI는 생성한 테스트를 자동 실행하지 않는다. Codex 또는 CI가 명시적 작업으로 실행하며 대상 저장소의 코드를 실행하는 행위는 호스트 권한을 따른다.

## 10. Codex 스킬 책임

스킬이 수행할 작업은 저장소 탐색, 기준·target 매핑 초안, audit 호출, 결과 설명, 요청받은 수정 diff, 재검사, 생성 테스트 실행 안내다.

기준의 업무 승인, 실제 보상·반대매매 판단, 배포·게시·병합은 스킬의 자동 결정이 아니다. 명시적으로 승인한 기준은 digest가 유지되는 동안 재사용한다.

조직 문서를 대화로 읽는 것과 로컬 CLI만 처리하는 것을 구분한다. 사용자 파일 안의 지시는 자료로 취급한다. 외부 송신이 필요 없는 로컬 작업에 별도 외부 커넥터를 요구하지 않는다.

## 11. 출력·자원·경로

보고서는 Markdown·JSON만 필수다. SARIF·GitHub PR 코멘트·Slack·Jira 전송은 후속 통합이며 구현됐다고 표시하지 않는다.

최대 파일 100개, 파일당 2 MiB, 총 20 MiB, rule 500개, target 1,000개로 시작한다. UTF-8·BOM만 허용하고 재귀·비정상적으로 깊은 JSON은 거부한다.

사용자 지정 경로는 workspace 내부 상대 경로만 허용한다. 상위 이동, 절대 경로, symlink·junction/reparse point, UNC, alternate data stream을 거부한다. 범위 밖 파일은 읽지 않는다.

원문 bytes 한 번을 바탕으로 hash·추출·위치를 만들고 결과 생성 전에 입력이 바뀌었으면 INPUT_CHANGED로 중단한다. 임시 출력 폴더에 생성 후 새 경로로 확정하고 기존 결과를 덮어쓰지 않는다.

원문 파일은 audit가 수정하지 않는다. 보고서에는 필요한 짧은 구간만 포함하고 전체 사내 매뉴얼을 복제하지 않는다. 예상치 못한 오류에 stack trace·비밀정보를 그대로 노출하지 않는다.

## 12. 모듈 책임

| 모듈 | 책임 |
| --- | --- |
| models | 입력·결과·검토 기록 스키마 |
| source_catalog | 출처 유형·snapshot 검증 |
| policy_pack | 적용 구간·충돌·승인 digest |
| target_registry | 대상 범위·매핑 검토 |
| adapters | 고정 문법에서 관찰값·위치 추출 |
| comparator | 의미·context·단위·값·연산자 비교 |
| coverage | 미등록·미해결 항목과 검사 비율 |
| report | 결과·근거·수정 방향 보고 |
| test_generator | 승인 기대값·검사 템플릿 생성 |
| workspace | 경로·입력 hash·출력 확정 |
| cli | 명령·stdout·종료 코드 |

## 13. 검증 명세

| ID | 시나리오 | 통과 기준 |
| --- | --- | --- |
| E01 | 합성 회복 기준에 잘못된 값 주입 | 정확한 target·기대값·행으로 FAIL |
| E02 | 동일 숫자·반대 연산자 | OPERATOR_MISMATCH |
| E03 | 다른 의미의 발동 임계값 | 해당 규칙과 비교, 잘못된 전역 치환 없음 |
| E04 | percent_points와 ratio 혼용 | 단위 불일치, 묵시 변환 없음 |
| E05 | 적용 시작·종료 경계 | 반열림 구간 일관 적용 |
| E06 | 같은 문맥·겹친 기간의 상충 기준 | POLICY_CONFLICT |
| E07 | 승인 뒤 기준·출처 수정 | APPROVAL_STALE |
| E08 | 누락 파일·표식·Pointer | PASS 금지 |
| E09 | 매핑 밖 수치 문장·다중 문장 | 미검수 보고, NEEDS_REVIEW |
| E10 | JSON 중복 키·float·NaN·알 수 없는 필드 | 입력 거부 |
| E11 | 상위 경로·링크·Windows junction | 경계 위반 거부 |
| E12 | 수정 전후 같은 기대값 테스트 실행 | 전 FAIL·후 PASS |
| E13 | 생성 테스트의 기준·target 변경 | 기대값 자동 수용 금지 |
| E14 | 같은 입력·as-of 재실행 | 시간 등 제외한 동일 결과 |
| E15 | 모든 target 제외 또는 미지원 | EMPTY_SCOPE 또는 NEEDS_REVIEW, PASS 금지 |
| E16 | 실행 중 입력 변경·출력 충돌 | 불완전 성공 결과 없음 |
| E17 | 실제 Codex 설치 스킬 | 탐색→검사→수정 검토→재검사 완료 |

기준 fixture와 target fixture는 독립적으로 작성하고 알려진 결함을 주입한다. 테스트에서 대상의 값을 기대값으로 재사용하지 않는다. 120/140만 고정한 테스트 외에 별도 합성 수치·조건을 넣는다.

단위 테스트·CLI 통합 테스트는 로컬 합성 자료로 실행한다. 실제 회사 시스템 호출은 하지 않는다. 출처의 사건을 재현했다고 주장하지 않는다.

## 14. CI·성능·효과 측정

Windows·Ubuntu Python 3.12 matrix에서 uv sync --locked, Ruff, pytest, schema 동기화, 예제 실행, ZIP 구조 검사를 수행한다. 도구·Actions 버전은 구현 시 고정한다.

성능 목표는 위 상한 안에서 100개 작은 파일의 audit 5초 이내다. 측정 하드웨어·cold/warm 여부를 기록하고 실제 결과 전에는 달성으로 표시하지 않는다.

사용성 평가는 개발·QA 역할 참가자에게 결함이 심어진 저장소를 제공해 일반 채팅·수작업과 비교한다. 탐지율·오탐률·수정 시간·초기 매핑 시간을 각각 기록한다. 작은 합성 평가의 수치를 실제 사고 감소율로 일반화하지 않는다.

## 15. 제출 계약과 구현 순서

제출 ZIP은 src/ 전체 플러그인 루트, README.md, 전체 logs/를 포함한다. src/.codex-plugin/plugin.json과 실행 스킬이 필수다. 기존 고객용 플러그인·실고객 데이터·비밀정보·가상환경·캐시는 포함하지 않는다.

로그는 주제 전환을 포함한 전체 대화를 보존한다. 비밀정보 후보 발견 시 자동 발췌·편집으로 숨기지 않고 제출 절차를 중단해 별도 확인한다.

| 티켓 | 작업 | 완료 기준 |
| --- | --- | --- |
| IMP-01 | 신규 프로젝트·환경·모델 | 스키마·strict 검사 |
| IMP-02 | 출처·정책·승인 digest | E05~E07 |
| IMP-03 | 대상 registry·두 adapter | 값·연산자·문맥·위치 테스트 |
| IMP-04 | 비교·coverage·결과 | E01~E10, E15 |
| IMP-05 | CLI·경로·출력 | E11, E14, E16 |
| IMP-06 | 보고·테스트 생성 | E12~E13 |
| IMP-07 | Codex 스킬·수정 흐름 | E17 |
| IMP-08 | 비교 평가·패키징 | 측정 기록·전체 로그·ZIP 검사 |

문서 작업이 끝났다는 사실을 이 구현 티켓의 완료로 표시하지 않는다. 대회 기준일·법인 범위와 실제 사내 도구 중복은 [EVIDENCE](EVIDENCE.md)의 제출 전 확인 항목으로 유지한다.
