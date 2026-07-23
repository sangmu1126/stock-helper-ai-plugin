from __future__ import annotations

from dataclasses import asdict, dataclass


CONFIRMATION_SCHEMA_VERSION = "confirmation-checklist.v1"


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class ConfirmationChecklist:
    schema_version: str
    required_for_decision: str
    items: tuple[ChecklistItem, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["items"] = [asdict(item) for item in self.items]
        return data


def build_confirmation_checklist(decision: str, *, action: str) -> dict[str, object]:
    if decision not in {"MANUAL_CONFIRM", "NOTIFY_ONLY"}:
        return ConfirmationChecklist(CONFIRMATION_SCHEMA_VERSION, decision, ()).to_dict()
    items = [
        ChecklistItem("not_investment_advice", "이 결과는 투자 조언이나 수익 보장이 아니라는 점을 확인했습니다."),
        ChecklistItem("rule_conditions_understood", "가격 조건, 기준 가격, 쿨다운, 취소 조건을 직접 확인했습니다."),
        ChecklistItem("stale_data_blocks_action", "시세 지연이나 브로커 상태 이상이 있으면 진행이 중단된다는 점을 이해했습니다."),
    ]
    if action in {"prepare_buy_order", "prepare_sell_order"}:
        items.extend(
            [
                ChecklistItem("manual_confirmation_only", "다음 단계는 자동 주문이 아니라 수동 확인이라는 점을 이해했습니다."),
                ChecklistItem("max_order_limit_checked", "최대 주문 금액 또는 수량 한도를 확인했습니다."),
            ]
        )
    else:
        items.append(ChecklistItem("notify_only_no_order", "이 룰은 알림만 제공하며 주문 후보를 만들지 않습니다."))
    return ConfirmationChecklist(CONFIRMATION_SCHEMA_VERSION, decision, tuple(items)).to_dict()
