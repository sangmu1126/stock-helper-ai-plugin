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


def test_csv_spec_text_is_checked(tmp_path, calendar):
    """실제 저장소 평가에서 놓친 것 4: 한국투자 API 명세 data.csv에 남은 폐지된 시간외 단일가 안내."""
    (tmp_path / "data.csv").write_text(
        "category,api_name,description\n"
        'domestic_stock,overtime_asking_price_krx,"국내주식 시간외 실시간호가 (KRX) API입니다. '
        '국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간호가 데이터 확인 가능합니다."\n',
        encoding="utf-8")
    result = scan_repo(tmp_path, calendar)
    assert [(f.path, f.line, f.found) for f in result.findings if f.status == "STALE"] == [("data.csv", 2, "18:00")]
    assert result.stats.csv_data_values == 0


def test_csv_session_table_uses_column_names_as_context(tmp_path, calendar):
    (tmp_path / "sessions.csv").write_text(
        "market,session,open,close\nKRX,regular,09:00,15:30\nKRX,single_price_overtime,16:00,18:00\n",
        encoding="utf-8")
    (tmp_path / "windows.csv").write_text(
        "name,session_open,session_close\n" + "".join(f"{c},09:00,15:30\n" for c in "abcd"), encoding="utf-8")
    found = statuses(scan_repo(tmp_path, calendar))
    assert found[("sessions.csv", 3, "18:00")] == "STALE"
    assert found[("sessions.csv", 2, "09:00")] == "MATCH"
    # 5행은 열 이름에서 두 줄 넘게 떨어져 있어도 열 이름(session)이 문맥이 된다
    assert ("windows.csv", 5, "15:30") in found


def test_csv_market_data_values_are_skipped_and_reported(tmp_path, calendar):
    """시세·체결 기록의 시각은 규칙이 아니다. 행마다 판정을 내지 않고, 건너뛴 수를 보고서에 남긴다."""
    from market_hours_guard.report import render_markdown

    bars = ["date,time,open,high,low,close,volume"]
    bars += [f"2026-11-18,{9 + i // 60:02d}:{i % 60:02d},71000,71500,70900,71200,1000" for i in range(120)]
    (tmp_path / "krx").mkdir()
    (tmp_path / "krx" / "kospi_1min.csv").write_text("\n".join(bars) + "\n", encoding="utf-8")
    ticks = ["symbol,date,time,price"]
    ticks += [f"AAPL,2026-11-18,{9 + (30 + i) // 60:02d}:{(30 + i) % 60:02d},230.5" for i in range(60)]
    (tmp_path / "us_market_ticks.csv").write_text("\n".join(ticks) + "\n", encoding="utf-8")

    result = scan_repo(tmp_path, calendar)
    assert result.findings == []
    assert result.stats.csv_data_values == 180
    assert sorted(result.stats.csv_data_files) == ["krx/kospi_1min.csv", "us_market_ticks.csv"]
    assert result.to_json()["coverage"]["skipped_csv_data_values"] == 180
    assert "CSV 기록 데이터로 보고 건너뛴 시각 180개" in render_markdown(result)


def test_long_line_snippet_shows_the_found_value(tmp_path, calendar):
    """CSV 한 행처럼 긴 줄은 첫 200자가 아니라 발견 위치 주변을 보여 준다."""
    line = "x," + "가" * 300 + " 장중 거래량이 많아 장 종료 이후(15:30 이후) 조회하시고 " + "나" * 300
    (tmp_path / "spec.csv").write_text("id,description\n" + line + "\n", encoding="utf-8")
    [finding] = scan_repo(tmp_path, calendar).findings
    assert "15:30" in finding.snippet
    assert finding.snippet.startswith("…") and finding.snippet.endswith("…")
