# EPUB safety boundaries

Segnatura treats an EPUB as untrusted ZIP and XML input. The default extraction
path validates the archive directory before reading metadata or content and
then applies bounded decompression and document-structure limits.

## Default limits

| Boundary | Default |
|---|---:|
| ZIP members | 20,000 |
| Decompressed bytes per member | 32 MiB |
| Total unique bytes read by Segnatura | 256 MiB |
| Elements per XML document | 250,000 |
| XML nesting depth | 256 |
| ZIP member path length | 1,024 characters |

The total-byte limit covers members Segnatura actually reads. Unreferenced
images, fonts, audio, and other binary assets are not decompressed by the text
extraction pipeline. Read members are cached during one extraction, so repeated
TOC, landmark, and spine access counts once and cannot multiply the budget.

Segnatura also rejects:

- absolute, parent-traversing, Windows-style, or NUL-containing ZIP paths;
- duplicate ZIP member names;
- encrypted ZIP members;
- XML documents containing entity declarations.

XML element count and nesting depth are checked by a streaming parser, before
any DOM tree is constructed. Malformed XHTML may still use the existing
bounded lexical fallback. The container, OPF package document, and NCX have no
lexical fallback and fail explicitly when they cannot be parsed.

## Trusted unusually large EPUB files

Applications may supply different positive limits explicitly:

```python
from segnatura import EpubSafetyLimits, extract

book = extract(
    "large-trusted-book.epub",
    safety_limits=EpubSafetyLimits(
        max_member_bytes=64 * 1024 * 1024,
        max_total_read_bytes=512 * 1024 * 1024,
    ),
)
```

Increasing a limit increases the maximum memory and CPU work accepted from the
input. Applications that receive EPUB files from other users should retain the
defaults or choose stricter limits based on their own deployment budget.

These checks are resource and structure boundaries, not antivirus scanning,
DRM support, schema validation, OCR, or a guarantee that publisher markup is
semantically correct.
