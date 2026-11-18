"""합성 저장소(수정 전·후)와 기준표 변경 시나리오로 판정을 검증한다."""

import shutil

from market_hours_guard.calendar_model import load_calendar
from market_hours_guard.scan import scan_repo


def statuses(result):
    return {(f.path, f.line, f.found): f.status for f in result.findings}


def test_before_repo_findings(calendar, examples):
    result = scan_repo(examples / "toy-broker", calendar)
    assert statuses(result) == {
        ("toy_broker/order_router.py", 6, "15:30"): "STALE",          # SOR 종료 15:30 → 20:00 누락
        ("toy_broker/us_market.py", 5, "22:30"): "DST_RISK",          # 서머타임 기준 고정값
        ("toy_broker/us_market.py", 6, "05:00"): "DST_RISK",
        ("toy_broker/order_validation.py", 4, "15:30"): "AMBIGUOUS",  # 정규장 마감인지 SOR 종료인지 불명
        ("config/batch_jobs.yaml", 4, "15:35"): "UNMAPPED",           # SOR 종료에서 파생된 배치 시각
        ("toy_broker/notifications.py", 4, "15:30"): "MATCH",         # 같은 15:30이지만 정규장 마감
        ("toy_broker/order_router.py", 4, "09:00"): "MATCH",
        ("toy_broker/session.py", 7, "09:00"): "MATCH",
        ("toy_broker/session.py", 7, "15:30"): "MATCH",
    }
    stale = next(f for f in result.findings if f.status == "STALE")
    assert stale.expected == "20:00" and "sor" in stale.evidence
    # 거래시간과 무관한 일일 리포트 배치(07:00)는 보고하지 않는다
    assert result.non_market == 1


def test_fixed_repo_is_clean_and_reviewed(calendar, examples):
    result = scan_repo(examples / "toy-broker-fixed", calendar)
    assert {f.status for f in result.findings} == {"MATCH"}
    annotated = [f for f in result.findings if f.reviewed]
    assert len(annotated) == 15
    cron = next(f for f in result.findings if f.path == "config/batch_jobs.yaml")
    assert (cron.found, cron.expected, cron.boundary) == ("20:05", "20:05", "SOR_END")


def test_calendar_change_flags_annotated_sites(tmp_path, calendar_path, examples):
    """기준이 바뀌면 주석으로 의미를 고정한 지점이 MISMATCH로 드러나야 한다 (가상 변경)."""
    text = calendar_path.read_text(encoding="utf-8")
    block = 'id = "SOR_END"\nmarket = "SOR"\ntime = "20:00"'
    assert block in text
    changed = tmp_path / "changed.toml"
    changed.write_text(text.replace(block, block.replace("20:00", "21:00")), encoding="utf-8")
    result = scan_repo(examples / "toy-broker-fixed", load_calendar(changed))
    mismatches = {(f.path, f.found, f.expected) for f in result.findings if f.status == "MISMATCH"}
    assert mismatches == {
        ("toy_broker/order_router.py", "20:00", "21:00"),
        ("config/batch_jobs.yaml", "20:05", "21:05"),
    }


def test_annotation_variants(tmp_path, calendar):
    repo = tmp_path / "repo"
    repo.mkdir()
    # 1: 폐기된 기준 지정 / 2: 없는 ID / 3: 무관 표시 / 4: 계절별 상수 / 5: 한 줄에 두 기준 / 6-7: 윗줄 주석
    sample = (
        'A = "15:30"  # mhg: SOR_END_UNTIL_20260913\n'
        'B = "15:30"  # mhg: NO_SUCH_ID\n'
        'C = "15:30"  # mhg: ignore — 테스트 고정값\n'
        'US_OPEN_KST_SUMMER = time(22, 30)  # 미국 정규장 서머타임\n'
        'AFTER = "16:00~20:00"  # mhg: KRX_AFTER_OPEN, KRX_AFTER_CLOSE\n'
        '# mhg: KRX_REGULAR_CLOSE\n'
        'CUTOFF = "15:30"\n'
    )
    (repo / "sample.py").write_text(sample, encoding="utf-8")
    got = statuses(scan_repo(repo, calendar))
    assert got == {
        ("sample.py", 1, "15:30"): "STALE",
        ("sample.py", 2, "15:30"): "MISMATCH",
        ("sample.py", 3, "15:30"): "IGNORED",
        ("sample.py", 4, "22:30"): "MATCH",
        ("sample.py", 5, "16:00"): "MATCH",
        ("sample.py", 5, "20:00"): "MATCH",
        ("sample.py", 7, "15:30"): "MATCH",
    }


def test_generated_files_are_skipped(tmp_path, calendar, examples):
    repo = tmp_path / "repo"
    shutil.copytree(examples / "toy-broker-fixed", repo)
    (repo / "tests" / "gen.py").write_text('# mhg:generated\nX = "15:30"  # SOR\n', encoding="utf-8")
    result = scan_repo(repo, calendar)
    assert result.stats.skipped_generated == 1
    assert all(f.path != "tests/gen.py" for f in result.findings)


def test_ide_compiled_output_is_not_scanned_twice(tmp_path, calendar):
    """VS Code Java 확장이 만든 bin/main/application.yml 사본이 같은 판정을 한 번 더 내던 문제."""
    config = 'cron: "0 30 15 * * MON-FRI"  # KRX 정규장 마감\n'
    (tmp_path / "src" / "main" / "resources").mkdir(parents=True)
    (tmp_path / "src" / "main" / "resources" / "application.yml").write_text(config, encoding="utf-8")
    (tmp_path / "bin" / "main").mkdir(parents=True)
    (tmp_path / "bin" / "main" / "application.yml").write_text(config, encoding="utf-8")
    (tmp_path / "bin" / "main" / "App.class").write_bytes(b"\xca\xfe\xba\xbe")
    (tmp_path / "tools" / "bin").mkdir(parents=True)
    (tmp_path / "tools" / "bin" / "close.sh").write_text('CLOSE="15:30"  # KRX 정규장 마감\n', encoding="utf-8")
    paths = sorted({f.path for f in scan_repo(tmp_path, calendar).findings})
    assert paths == ["src/main/resources/application.yml", "tools/bin/close.sh"]


def test_files_over_size_limit_are_listed_in_report(tmp_path, calendar):
    """크기 제한으로 읽지 않은 파일은 결과와 보고서에 이름이 나온다(실제 저장소 평가에서 키움 API 명세 3.8MB가 조용히 빠졌음)."""
    from market_hours_guard.extract import MAX_BYTES
    from market_hours_guard.report import render_markdown

    (tmp_path / "small.py").write_text('MARKET_CLOSE = "15:30"  # KRX 정규장 마감\n', encoding="utf-8")
    (tmp_path / "spec.json").write_text('{"x": "' + "a" * (MAX_BYTES + 1) + '"}', encoding="utf-8")
    result = scan_repo(tmp_path, calendar)
    assert result.stats.large_files == ["spec.json"]
    assert result.to_json()["coverage"]["skipped_large_files"] == ["spec.json"]
    assert "검사하지 않은 파일 1개" in render_markdown(result) and "`spec.json`" in render_markdown(result)
