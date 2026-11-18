"""저장소 스캔: 추출 → 판정 → 결과 묶음."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .calendar_model import Calendar
from .classify import SEVERITY, STATUS_ORDER, Finding, classify
from .extract import FileStats, extract_repo


@dataclass
class ScanResult:
    repo: Path
    calendar: Calendar
    findings: list[Finding]
    stats: FileStats
    occurrences: int
    non_market: int
    scanned_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def counts(self) -> dict[str, int]:
        result = {status: 0 for status in STATUS_ORDER}
        for finding in self.findings:
            result[finding.status] += 1
        return result

    def failing(self, statuses: set[str]) -> list[Finding]:
        return [f for f in self.findings if f.status in statuses]

    def to_json(self) -> dict:
        return {
            "schema": "market-hours-guard/findings@1",
            "tool_version": __version__,
            "scanned_at": self.scanned_at,
            "repo": self.repo.name,
            "calendar": {
                "name": self.calendar.name,
                "path": self.calendar.path.name,
                "digest": self.calendar.digest,
                "basis_date": self.calendar.basis_date.isoformat() if self.calendar.basis_date else None,
            },
            "coverage": {
                "files_scanned": self.stats.files_scanned,
                "skipped_large": self.stats.skipped_large,
                "skipped_large_files": self.stats.large_files,
                "skipped_generated": self.stats.skipped_generated,
                "skipped_csv_data_values": self.stats.csv_data_values,
                "csv_data_files": self.stats.csv_data_files,
                "time_expressions": self.occurrences,
                "market_related": len(self.findings),
                "non_market_ignored": self.non_market,
            },
            "counts": self.counts(),
            "severity": SEVERITY,
            "findings": [asdict(f) for f in self.findings],
        }


def scan_repo(repo: Path, calendar: Calendar, include_docs: bool = False,
              exclude: tuple[Path, ...] = ()) -> ScanResult:
    repo = Path(repo)
    occurrences, stats = extract_repo(repo, include_docs=include_docs, exclude=exclude)
    findings: list[Finding] = []
    non_market = 0
    for occ in occurrences:
        finding = classify(occ, calendar)
        if finding is None:
            non_market += 1
        else:
            findings.append(finding)
    findings.sort(key=lambda f: (STATUS_ORDER.index(f.status), f.path, f.line, f.col))
    return ScanResult(repo=repo, calendar=calendar, findings=findings, stats=stats,
                      occurrences=len(occurrences), non_market=non_market)
