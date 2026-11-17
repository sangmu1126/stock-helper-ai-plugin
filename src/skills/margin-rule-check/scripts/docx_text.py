"""Word(.docx) 본문을 '문단 하나 = 한 줄' 텍스트로 읽는다. 표준 라이브러리(zipfile, xml)만 쓴다.

- 본문(word/document.xml)의 문단과 표 안 문단을 순서대로 읽는다. 머리글·바닥글·메모는 읽지 않는다.
- 줄 번호는 문단 번호가 된다(점검 결과의 `파일:줄`이 `파일:문단`).
- 옛 형식(.doc)과 한글(.hwp)은 읽지 않는다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_XML_BYTES = 20 * 1024 * 1024  # 압축을 푼 본문이 이보다 크면 읽지 않는다(압축 폭탄 방지)


class DocxError(ValueError):
    pass


def read_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise DocxError(f"본문이 너무 큽니다({info.file_size:,} bytes)")
            root = ElementTree.fromstring(archive.read(info))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError) as exc:
        raise DocxError(f"Word 파일을 읽지 못했습니다: {exc}") from exc
    paragraphs: list[str] = []
    _collect(root, paragraphs, None)
    return "\n".join(paragraphs)


def _collect(node: ElementTree.Element, paragraphs: list[str], current: list[str] | None) -> None:
    for child in node:
        if child.tag == f"{W}p":
            buffer: list[str] = []
            _collect(child, paragraphs, buffer)  # 글상자 안 문단은 바깥 문단보다 먼저 나온다
            paragraphs.append("".join(buffer).replace("\n", " "))
        elif child.tag == f"{W}t":
            if current is not None:
                current.append(child.text or "")
        elif child.tag == f"{W}tab":
            if current is not None:
                current.append("\t")
        elif child.tag in (f"{W}br", f"{W}cr"):
            if current is not None:
                current.append(" ")
        else:
            _collect(child, paragraphs, current)
