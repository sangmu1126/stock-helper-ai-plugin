# Codex 화면 촬영 상태와 재현 안내

## 현재 상태

2026-11-19 기준 소스 버전은 `0.7.2`(거래시간 점검기 CSV 검사 추가)이고, 공개 예제를 CLI로 실행한 설치 버전은 `0.7.1`입니다. `demo-evidence/`는 0.6.0, `alert-flow/`와 `us-real-alert/`는 0.7.0의 당시 실행 기록이며, 각 `summary.json`의 버전·커밋을 기준으로 읽습니다. 설치된 0.7.1의 공개 예제 실행은 CLI로 확인했지만 Codex 앱의 대화 화면을 촬영한 증거와는 구분합니다.

초기 0.6.0 기록 작업에서는 Computer Use 초기화가 `failed to write kernel assets`로 실패해 PNG·GIF를 촬영하지 못했습니다. 2026-11-19 재시도도 `trusted Node process exited unexpectedly`로 종료됐습니다. 아래 0.7.0의 실제 Windows 알림 PNG는 별도 기록 도구로 확보한 자료이며, "모든 스크린샷이 없다"는 뜻은 아닙니다. 꾸며 만든 대화 화면은 사용하지 않습니다.

`demo-evidence/`에는 실제 CLI 실행 기록을 남겼습니다. 이것은 앱 설치·스킬 자동 선택·실시간 코드 수정이 촬영됐다는 증거가 아닙니다. 전후 테스트는 기존 합성 원본과 수정 예제를 각각 임시 폴더로 복사해 실행한 비교입니다.

공개용 CLI 기록은 작업·사용자 경로 접두어를 가리고 줄바꿈·행 끝 공백만 정규화했습니다. 전체 AI 대화 로그는 편집하지 않았습니다.

### 가격 알림 흐름 (0.7.0)

`alert-flow/`에는 빈 작업 폴더에서 초안 → 조건 확인 → 등록 → 감시 → Windows 알림 → Ctrl+C 중지까지 이어서 실행한 기록이 있습니다(`python tools/record_alert_flow.py --screenshot`).

- 1~6단계는 합성 시세(`demo-fixture`)라 알림 제목에 `[DEMO]`가 붙습니다. 7단계만 실제 시세(Yahoo Finance)이며, 국내 시간대에 실행해 알림은 나가지 않았습니다.
- 미국 정규장 실제 시세 기록은 `us-real-alert/`에 따로 있습니다(`python tools/record_us_real_alert.py --screenshot`). 시세 나이 표본과 실제 시세 TSLA 알림(제목에 `[DEMO]` 없음)의 화면입니다. 알림 조건은 경로 확인용으로 반드시 맞게 정했습니다.
- `alert-flow/notification.png`는 실제로 표시된 Windows 알림을 촬영한 것입니다. 알림과 작업 표시줄 시계만 남기고 잘랐습니다.
- 이것도 CLI 실행이며, Codex 앱에서 대화로 진행한 화면은 아닙니다. 앱 화면은 아래 4번으로 촬영합니다.

## 촬영 순서

앱에서 최신 플러그인을 설치·로드한 다음 아래 요청을 실행합니다. 별도 테스트 폴더를 사용하고 원본 예제는 보존합니다.

| 순서 | 요청 | 화면에 담을 내용 | 파일 |
| --- | --- | --- | --- |
| 1 | `src/skills/market-hours-guard/examples/toy-broker를 임시 폴더에 복사해서 SOR 20:00 연장, 미국 DST, 수능일, 연말 휴장일 반영을 검사하고 고쳐줘. 기존 calendar.demo.toml을 사용하고 원본 예제는 수정하지 마.` | 스킬 호출, 실제 스캔, 수정 diff의 mhg 주석, 테스트 전후 결과 | `mhg-demo.gif` |
| 2 | `src/skills/margin-rule-check/examples/support-docs 상담 스크립트와 설정을 신용 규칙과 대조해줘.` | 고칠 것 5건과 수정 제안 | `mrc-lint.png` |
| 3 | `src/skills/safe-trade-rule-builder/examples/margin/misguided_after_deposit.json을 점검해줘. 120%를 넘겼으니 반대매매를 피할 수 있나?` | 127.2% 계좌의 오해 교정, 기한, 필요한 금액, 가정 | `margin-guard.png` |
| 4 | `카카오가 애프터마켓에서 전일 종가보다 3% 떨어지면 알려줘. 10분에 한 번만. 시연이니 demo-fixture 시세로 등록하고 감시를 시작해줘.` (KRX 16:00~20:00에 실행) | 초안 확인 → 확인 후 등록 → `run` 터미널 → `[DEMO]` Windows 알림 → Ctrl+C 중지와 `status` | `alert-flow.gif` |
| 5 | `$market-hours-guard`를 선택하고 `public_example.py로 hours와 retired-finance를 --fetch로 실행해줘. 해시·위치·한계를 보고하고 원본은 실행·수정하지 마.` | 실제 원본 14개 해시, STALE 9·UNMAPPED 9, API 참조 7종. 합성 경계 테스트 결과와 분리 | `public-kis.png` |

4번은 평소 거래일 시각 예시입니다. 수능일 등 특수일에는 `market_sessions.json`의 세션 시각에 맞춰 실행하며, 알림이 나가지 않았는데 표시됐다고 기록하지 않습니다. 공개 예제의 7종 API 참조 대조도 서버 차단 시험으로 소개하지 않습니다.

저장 위치는 `docs/media/`입니다. PNG/GIF가 실제로 존재하고 내용 검토가 끝난 뒤에만 README에 이미지 링크를 추가합니다. 현재 README에는 없는 이미지 링크를 넣지 않았습니다.

## 이번에 확인한 CLI 결과

- 변경 전 합성 예제: 경계 테스트 17 실패, 33 통과.
- 기존 수정 합성 예제: 경계 테스트 50 통과.
- 상담 자료 lint: 고칠 것 5건.
- 반대매매 가드: 담보비율 127.2%, 추가 입금 64,000,000원 또는 상환 45,714,286원이라는 계산 결과. 공식 계산식이 아닌 가정과 앱 표시 우선 문구 포함.
- 달러 조건 룰: CLI 정상 종료.

실행 환경·각 종료 코드와 조건 충족 여부는 [summary.json](demo-evidence/summary.json)에 있습니다. 수정 중인 소스가 있으면 해당 경로도 기록됩니다. 반복 기록은 다음 명령으로 생성합니다.

```powershell
python tools/record_demo_evidence.py
```

## 공개 전 확인

계정명·이메일·사용자 경로·토큰이 화면에 보이면 캡처 범위를 좁혀 가립니다. 고객 계좌가 아닌 합성 계좌만 사용합니다. 가린 화면은 데모 공개용 자료이며 제출용 전체 AI 대화 로그와는 별도입니다.

GIF는 실제 촬영한 30~60초 분량을 목표로 하고, 수치가 읽히는 해상도를 유지합니다. 앱 재시작·로그인·플러그인 재설치는 캡처 도구 오류가 해소된 뒤 실제 상태를 확인하고 진행해야 합니다.
