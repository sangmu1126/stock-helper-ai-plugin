# AWS 제거 기록 (2026-11-18)

Safe Trade Rule Builder는 7월에 AWS(SAM, Lambda, DynamoDB)로 배포한 적이 있다. 이 플러그인은 Codex 안에서 로컬로 동작하고 배포된 런타임은 쓰이지 않아서, 코드에서 AWS 의존을 모두 제거하고 리소스를 삭제했다.

## 삭제한 리소스 (계정 ****7539, ap-northeast-2)

| 리소스 | 처리 |
| --- | --- |
| CloudFormation 스택 `safe-trade-rule-builder-integration` | 삭제(Lambda `SafeTradeRuntimeFunction`, IAM 역할, DynamoDB 테이블 2개 포함) |
| CloudFormation 스택 `aws-sam-cli-managed-default` | 삭제 |
| S3 버킷 `aws-sam-cli-managed-default-samclisourcebucket-clqwolvjqeyv` | 객체 11개(전 버전) 삭제 후 버킷 삭제. 모두 이 프로젝트의 7/10 배포 산출물이었음 |
| 로그 그룹 `/aws/lambda/safe-trade-rule-builder-i-SafeTradeRuntimeFunction-VhZoIY7GltOa` | **남아 있음.** IAM 사용자 `kakaoPay`에 `logs:DeleteLogGroup` 권한이 없음. 약 12KB |

같은 계정의 다른 프로젝트 리소스(`/ecs/deplight-task`, `/ecs/everytown-es`, `/aws/lambda/tudolam`, `/faas/controller`, `RDSOSMetrics` 로그 그룹 등)는 이 프로젝트와 무관해 건드리지 않았다.
SSM Parameter Store, AppConfig, EventBridge 규칙은 조회 권한이 없어 확인하지 못했다. 배포 기록상 이 프로젝트가 만든 적은 없다.

## 백업 (`backup-2026-11-18/`)

- `decision_log_table.json`: 결정 로그 테이블 전체 스캔(27건, DynamoDB JSON 형식)
- `state_table.json`: 상태 테이블 전체 스캔(6건)
- `deployed_template_processed.json`: 실제 배포된 템플릿(SAM 변환 후)
- `stack_description.json`: 삭제 직전 스택 정보

`AWS_PERMISSION_CHECK.md`는 당시의 배포·권한 검증 기록이다.

## 남은 로그 그룹 삭제 방법 (관리자 권한 필요)

```powershell
aws logs delete-log-group --region ap-northeast-2 --log-group-name /aws/lambda/safe-trade-rule-builder-i-SafeTradeRuntimeFunction-VhZoIY7GltOa
```

또는 콘솔: CloudWatch → 로그 그룹 → 위 이름 선택 → 삭제.
