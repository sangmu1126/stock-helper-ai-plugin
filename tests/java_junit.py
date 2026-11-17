"""생성된 JUnit 5 테스트를 실제로 컴파일·실행하는 테스트 도우미.

JDK(javac, java)와 JUnit 콘솔 런처 jar(환경 변수 JUNIT_CONSOLE_JAR)가 있을 때만 실행하고, 없으면 건너뛴다.
CI는 jar를 받아 체크섬을 확인한 뒤 이 변수를 설정한다(.github/workflows/ci.yml).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JAR = os.environ.get("JUNIT_CONSOLE_JAR", "")
COPY_IGNORE = shutil.ignore_patterns("build", ".gradle", "out")


def require_junit() -> None:
    if not (JAR and Path(JAR).is_file() and shutil.which("javac") and shutil.which("java")):
        reason = "JDK와 JUNIT_CONSOLE_JAR(junit-platform-console-standalone jar)가 있어야 실행됩니다"
        if os.environ.get("REQUIRE_JUNIT") == "1":  # CI에서는 건너뛰지 않고 실패시킨다
            pytest.fail(reason)
        pytest.skip(reason)


def run_junit(project: Path) -> tuple[int, dict[str, int]]:
    """project 아래 .java를 모두 컴파일해 JUnit으로 실행하고 (종료 코드, {found, successful, failed})를 돌려준다."""
    out = project / "out"
    sources = [str(p) for p in sorted(project.rglob("*.java"))]
    compiled = subprocess.run(["javac", "-encoding", "UTF-8", "-cp", JAR, "-d", str(out), *sources],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    proc = subprocess.run(["java", "-jar", JAR, "execute", "--class-path", str(out), "--scan-class-path",
                           "--disable-banner", "--disable-ansi-colors", "--details=summary"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    counts = {kind: int(n) for n, kind in re.findall(r"\[\s*(\d+) tests (found|successful|failed)", proc.stdout)}
    return proc.returncode, counts
