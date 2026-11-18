from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "src/skills/market-hours-guard/scripts"
sys.path.insert(0, str(SCRIPTS))

from public_example import (
    EXAMPLE,
    REPOSITORY,
    audit,
    fetch_sources,
    finance_reference,
    load_manifest,
    main,
    render_report,
)


def manifest_for(data: bytes):
    return {"repository": REPOSITORY, "revision": "a" * 40,
            "cases": {"hours": [{"path": "example.py", "sha256": hashlib.sha256(data).hexdigest()}]}}


def test_real_manifest_has_pinned_unmodified_sources_and_provenance():
    manifest = load_manifest()
    assert len(manifest["cases"]["hours"]) == 7
    assert len(manifest["cases"]["retired-finance"]) == 7
    assert len({item["endpoint"] for item in manifest["cases"]["retired-finance"]}) == 7
    assert "supplied by the user" in manifest["notice"]["verification"]
    assert not manifest["notice"]["live_api_called"]
    assert "DEMO" not in (EXAMPLE / "calendar.public.toml").read_text(encoding="utf-8")


def test_download_requires_opt_in_and_verifies_bytes(tmp_path):
    data = b"raise AssertionError('never execute downloaded source')\n"
    manifest = manifest_for(data)
    with pytest.raises(ValueError, match="--fetch"):
        fetch_sources(manifest, "hours", tmp_path)

    class Response(io.BytesIO):
        def geturl(self):
            return f"https://raw.githubusercontent.com/{REPOSITORY}/{'a' * 40}/example.py"

    requested = []

    def opener(url, timeout):
        requested.append((url, timeout))
        return Response(data)

    result = fetch_sources(manifest, "hours", tmp_path, fetch=True, opener=opener)
    assert requested[0][1] == 30
    assert (tmp_path / "example.py").read_bytes() == data
    assert result[0]["verified"]
    # Cache replay must not make any network request or execute source code.
    fetch_sources(manifest, "hours", tmp_path, opener=lambda *a, **kw: pytest.fail("network called"))


def test_changed_source_is_not_overwritten(tmp_path):
    data = b"source = 'original'\n"
    target = tmp_path / "example.py"
    target.write_bytes(b"source = 'user changes'\n")
    with pytest.raises(ValueError, match="hash/size mismatch"):
        fetch_sources(manifest_for(data), "hours", tmp_path, fetch=True)
    assert target.read_bytes() == b"source = 'user changes'\n"


@pytest.mark.parametrize("path", ["../escape.py", "/absolute.py", "C:/escape.py", "x\\y.py"])
def test_manifest_rejects_unsafe_source_paths(tmp_path, path):
    manifest = manifest_for(b"source\n")
    manifest["cases"]["hours"][0]["path"] = path
    file = tmp_path / "manifest.json"
    file.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe"):
        load_manifest(file)


def test_download_rejects_hash_mismatch_without_writing(tmp_path):
    class Response(io.BytesIO):
        def geturl(self):
            return f"https://raw.githubusercontent.com/{REPOSITORY}/{'a' * 40}/example.py"

    with pytest.raises(ValueError, match="hash/size mismatch"):
        fetch_sources(manifest_for(b"original"), "hours", tmp_path, fetch=True,
                      opener=lambda *a, **kw: Response(b"changed"))
    assert not (tmp_path / "example.py").exists()


def test_financial_api_reference_uses_ast_not_execution():
    item = {"path": "example.py", "name": "balance sheet", "endpoint": "/finance/balance-sheet", "tr_id": "TR123"}
    data = b'''raise AssertionError("must not execute")
API_URL = "/finance/balance-sheet"
def finance():
    tr_id = "TR123"
    return ka._url_fetch(API_URL, tr_id, "", {})
'''
    finding = finance_reference(data, item)
    assert finding["line"] == 2
    assert finding["call_lines"] == [5]
    assert finding["runtime_reachability"] == "not_verified"
    assert not finding["live_api_called"]
    assert finance_reference(data, {**item, "tr_id": "OTHER"}) is None


def test_mentions_without_fetch_call_are_not_claimed_as_calls():
    item = {"path": "example.py", "name": "balance sheet", "endpoint": "/finance/balance-sheet", "tr_id": "TR123"}
    assert finance_reference(b'API_URL = "/finance/balance-sheet"\ntr_id = "TR123"', item) is None


def test_public_calendar_scans_legacy_label_without_synthetic_probe(tmp_path):
    (tmp_path / "example.py").write_text(
        '"""국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간호가 데이터 확인 가능합니다."""\n',
        encoding="utf-8",
    )
    result = audit(load_manifest(), "hours", tmp_path)
    assert result["finding_count"] == 1
    assert not result["source_executed"]
    result["verified_sources"] = []
    assert "websocket TR" in render_report(result)


def test_finance_report_retains_source_verification_limits(tmp_path):
    manifest = load_manifest()
    manifest["cases"]["retired-finance"] = []
    result = audit(manifest, "retired-finance", tmp_path)
    assert result["finding_count"] == 0
    assert result["notice"]["verification"]
    assert not result["kakaopay_internal_system"]


def test_cli_without_cache_does_not_fetch(tmp_path, capsys):
    assert main(["--case", "hours", "--out", str(tmp_path)]) == 2
    assert "--fetch" in capsys.readouterr().err
