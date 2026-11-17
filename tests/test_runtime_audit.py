from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src" / "runtime"


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.syspath_prepend(str(RUNTIME))
    for path in RUNTIME.glob("*.py"):
        monkeypatch.delitem(sys.modules, path.stem, raising=False)
    handler = importlib.import_module("runtime_handler")
    state = importlib.import_module("state_store")
    logs = importlib.import_module("decision_log_store")
    factory = importlib.import_module("store_factory")
    state_store = state.InMemoryStateStore()
    log_store = logs.InMemoryDecisionLogStore()
    monkeypatch.setattr(handler._STORE_FACTORY, "make_state_store", lambda config: state_store)
    monkeypatch.setattr(handler._STORE_FACTORY, "make_decision_log_store", lambda config: log_store)
    monkeypatch.setenv("SAFE_TRADE_METRICS_LOG", "0")
    event = json.loads((RUNTIME / "sample_events" / "matched_manual_confirm.json").read_text(encoding="utf-8"))
    event["quote"]["timestamp"] = int(time.time())
    event["user_id"] = "customer-1"
    return SimpleNamespace(
        handler=handler, state=state, logs=logs, factory=factory, event=event,
        state_store=state_store, log_store=log_store,
    )


@pytest.mark.parametrize("scenario,expected", [
    ("matched", "MANUAL_CONFIRM"),
    ("broker_down", "STOP"),
    ("not_matched", "WAIT"),
    ("notify", "NOTIFY_ONLY"),
    ("clarify", "REQUIRE_CLARIFICATION"),
    ("blocked", "BLOCK"),
])
def test_every_evaluation_is_logged(runtime, scenario, expected):
    event = runtime.event
    if scenario == "broker_down":
        event["broker_health"]["ok"] = False
    elif scenario == "not_matched":
        event["quote"]["regular_market_price"] = 100000
    elif scenario == "notify":
        event["rule"]["action"] = "notify_only"
        event["rule"]["execution_mode"] = "notify_only"
    elif scenario == "clarify":
        event["rule"]["ambiguities"] = ["Missing user confirmation"]
    elif scenario == "blocked":
        event["intent"] = "종목 추천해줘"

    response = runtime.handler.handle_event(event)

    assert response["decision"] == expected
    assert runtime.log_store.entries == [response["decision_log"]]


def test_duplicate_attempt_is_logged_separately(runtime):
    first = runtime.handler.handle_event(runtime.event)
    second = runtime.handler.handle_event(runtime.event)

    assert first["decision"] == "MANUAL_CONFIRM"
    assert second["decision"] == "WAIT"
    assert "DUPLICATE_DECISION_BLOCKED" in second["reasons"]
    assert len(runtime.log_store.entries) == 2
    assert first["decision_log"]["decision_id"] != second["decision_log"]["decision_id"]


def test_conditional_race_clears_confirmation_and_logs_wait(runtime, monkeypatch):
    def lose_race(*args, **kwargs):
        raise runtime.state.DuplicateStateRecordError("race")

    monkeypatch.setattr(runtime.state_store, "record_decision_state", lose_race)
    response = runtime.handler.handle_event(runtime.event)

    assert response["decision"] == "WAIT"
    assert response["decision_result"]["confirmation_required"] is False
    assert response["decision_result"]["fire_rule_id"] is None
    assert response["decision_log"]["confirmation_required"] is False
    assert runtime.log_store.entries == [response["decision_log"]]


def test_audit_failure_stops_evaluation(runtime, monkeypatch):
    def fail(log):
        raise RuntimeError("Audit store unavailable")

    monkeypatch.setattr(runtime.log_store, "append", fail)
    response = runtime.handler.handle_event(runtime.event)
    assert response["decision"] == "STOP"
    assert response["reasons"] == ["INTERNAL_ERROR"]


def test_user_history_uses_hashed_identity(runtime, tmp_path):
    response = runtime.handler.handle_event(runtime.event)
    file_store = runtime.logs.FileDecisionLogStore(tmp_path / "audit.jsonl")
    file_store.append(response["decision_log"])
    for store in (runtime.log_store, file_store):
        assert len(store.query_user_decisions("customer-1")["items"]) == 1
        assert store.query_user_decisions("other-customer")["items"] == []
    assert "customer-1" not in json.dumps(response["decision_log"], ensure_ascii=False)


# ── 로컬 저장소 ────────────────────────────────────────────


def _fresh_factory():
    """픽스처가 바꿔치기한 함수가 아닌, 원래 store_factory 모듈을 새로 읽는다."""
    spec = importlib.util.spec_from_file_location("store_factory_fresh", RUNTIME / "store_factory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_factory_defaults_to_memory(runtime):
    factory = _fresh_factory()
    config = {"state_backend": "memory", "decision_log_backend": "memory"}
    assert isinstance(factory.make_state_store(config), runtime.state.InMemoryStateStore)
    assert isinstance(factory.make_decision_log_store(config), runtime.logs.InMemoryDecisionLogStore)
    assert isinstance(factory.make_state_store({}), runtime.state.InMemoryStateStore)


def test_factory_file_backend_requires_path(runtime, tmp_path):
    config = {
        "state_backend": "file", "state_file": str(tmp_path / "state.json"),
        "decision_log_backend": "file", "decision_log_file": str(tmp_path / "audit.jsonl"),
    }
    factory = _fresh_factory()
    assert isinstance(factory.make_state_store(config), runtime.state.FileStateStore)
    assert isinstance(factory.make_decision_log_store(config), runtime.logs.FileDecisionLogStore)
    with pytest.raises(RuntimeError, match="SAFE_TRADE_STATE_FILE"):
        factory.make_state_store({"state_backend": "file"})


@pytest.mark.parametrize("backend", ["dynamodb", "s3", "unknown"])
def test_factory_rejects_unsupported_backend(runtime, backend):
    with pytest.raises(ValueError, match="Unsupported"):
        _fresh_factory().make_state_store({"state_backend": backend})


def test_file_backend_blocks_duplicates_across_runs(runtime, monkeypatch, tmp_path):
    """file 백엔드면 매번 새 저장소 객체를 만들어도(=실행이 바뀌어도) 중복이 차단되고 로그가 쌓인다."""
    monkeypatch.setattr(runtime.handler, "_STORE_FACTORY", _fresh_factory())
    monkeypatch.setenv("SAFE_TRADE_STATE_BACKEND", "file")
    monkeypatch.setenv("SAFE_TRADE_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("SAFE_TRADE_DECISION_LOG_BACKEND", "file")
    monkeypatch.setenv("SAFE_TRADE_DECISION_LOG_FILE", str(tmp_path / "audit.jsonl"))

    first = runtime.handler.handle_event(json.loads(json.dumps(runtime.event)))
    second = runtime.handler.handle_event(json.loads(json.dumps(runtime.event)))

    assert first["decision"] == "MANUAL_CONFIRM"
    assert second["decision"] == "WAIT" and "DUPLICATE_DECISION_BLOCKED" in second["reasons"]
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_file_state_store_records_decision_state_once(runtime, tmp_path):
    store = runtime.state.FileStateStore(tmp_path / "state.json")
    store.record_decision_state("key-1", "rule-1", now=100)
    assert store.cooldown_active("rule-1", now=120, cooldown_seconds=60) is True
    with pytest.raises(runtime.state.DuplicateStateRecordError):
        runtime.state.FileStateStore(tmp_path / "state.json").record_decision_state("key-1")


# ── 외부 서비스 미사용 보장 ──────────────────────────────


def test_metrics_log_goes_to_stderr_not_stdout(runtime, monkeypatch, capsys):
    monkeypatch.setenv("SAFE_TRADE_METRICS_LOG", "1")
    runtime.handler.handle_event(runtime.event)
    captured = capsys.readouterr()
    assert captured.out == ""
    record = json.loads(captured.err.strip().splitlines()[-1])
    assert record["type"] == "safe_trade_metrics" and "_aws" not in record


def test_no_cloud_sdk_imports_in_plugin_source():
    """플러그인 소스 어디에서도 AWS SDK를 import하지 않는다."""
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] in {"boto3", "botocore", "aioboto3"} for name in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    assert not (ROOT / "src" / "infra").exists()
    assert not (RUNTIME / "lambda_handler.py").exists()
