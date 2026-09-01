"""Compare naive EPUB text scraping with Segnatura on a generated fixture.

The fixture is created at runtime and contains no third-party text. Run from
the repository root after installing Segnatura:

    python examples/compare_extraction.py
"""
from __future__ import annotations

import re
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from segnatura import extract


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)


def create_fixture(path: Path) -> None:
    """Write a small legal EPUB containing work text and obvious apparatus."""
    entries = {
        "META-INF/container.xml": """
          <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
            <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
          </container>""",
        "OEBPS/content.opf": """
          <package version="3.0" xmlns="http://www.idpf.org/2007/opf">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>The Clockmaker's Window</dc:title>
              <dc:creator id="author">Ada Example</dc:creator>
              <meta refines="#author" property="role"
                    scheme="marc:relators">aut</meta>
              <dc:language>en</dc:language>
              <dc:date>2026-08-27</dc:date>
            </metadata>
            <manifest>
              <item id="nav" href="nav.xhtml"
                    media-type="application/xhtml+xml" properties="nav"/>
              <item id="front" href="front.xhtml"
                    media-type="application/xhtml+xml"/>
              <item id="chapter" href="chapter.xhtml"
                    media-type="application/xhtml+xml"/>
              <item id="copyright" href="copyright.xhtml"
                    media-type="application/xhtml+xml"/>
            </manifest>
            <spine>
              <itemref idref="front"/>
              <itemref idref="nav"/>
              <itemref idref="chapter"/>
              <itemref idref="copyright"/>
            </spine>
          </package>""",
        "OEBPS/nav.xhtml": """
          <html xmlns="http://www.w3.org/1999/xhtml"><body>
            <nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">
              <h1>Contents</h1><ol>
                <li><a href="chapter.xhtml">Chapter One</a></li>
              </ol>
            </nav>
          </body></html>""",
        "OEBPS/front.xhtml": """
          <html xmlns="http://www.w3.org/1999/xhtml"><body>
            <h1>The Clockmaker's Window</h1><p>Ada Example</p>
          </body></html>""",
        "OEBPS/chapter.xhtml": """
          <html xmlns="http://www.w3.org/1999/xhtml"><body>
            <h1>Chapter One</h1>
            <p>Mara opened the workshop before sunrise. The brass clocks
            answered one another across the quiet room, each keeping a
            slightly different version of the morning.</p>
            <p>Behind the blue curtain she found the missing key and the note
            her grandfather had promised to leave.</p>
          </body></html>""",
        "OEBPS/copyright.xhtml": """
          <html xmlns="http://www.w3.org/1999/xhtml"><body>
            <h1>Copyright</h1><p>Copyright 2026 Example Press.</p>
            <p>All rights reserved. ISBN 978-0-00-000000-0.</p>
          </body></html>""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip",
                         compress_type=zipfile.ZIP_STORED)
        for name, content in entries.items():
            archive.writestr(name, content)


def naive_extract(path: Path) -> str:
    """Return every visible string from every XHTML member."""
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            parser = _VisibleText()
            parser.feed(archive.read(name).decode("utf-8"))
            parts.extend(parser.parts)
    return "\n".join(parts)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        epub = Path(temporary) / "comparison.epub"
        create_fixture(epub)
        naive = naive_extract(epub)
        book = extract(epub)
        filtered = book.text()

        print("=== Naive extraction (all visible EPUB strings) ===")
        print(naive)
        print("\n=== Segnatura extraction (work text only) ===")
        print(filtered)
        excluded = [text for text in ("Contents", "Copyright",
                                      "Copyright 2026 Example Press.",
                                      "All rights reserved.")
                    if text in naive and text not in filtered]
        print("\nVisible strings excluded:", "; ".join(excluded))


if __name__ == "__main__":
    main()
