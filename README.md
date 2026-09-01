# Segnatura

Segnatura turns an EPUB into content that remains distinguishable by editorial
function. It classifies each source block as work text, note, bibliography,
index, or paratext; supports different uses for those parts; and preserves
stable EPUB coordinates for citations and downstream retrieval.

Extraction is deterministic and has no runtime dependencies outside the Python
standard library. An optional LLM auditor reviews the completed result without
changing it. Only corrections accepted by a person and saved in an
exact-edition Edition Profile affect a later extraction.

## Install

Segnatura requires Python 3.10 or newer and has no required runtime dependency
outside the Python standard library.

```console
python -m pip install segnatura
```

Install the local browser tool as well:

```console
python -m pip install "segnatura[tools]"
```

To install from a clone of this repository instead, run the same commands from
the repository root with `.` in place of the package name.

## Quick start

```python
from segnatura import extract

book = extract("book.epub")
plain_text = book.text()
print(plain_text)
```

By default, `text()` returns only the readable text of the work. The same
extracted book also exposes metadata and lets callers select other editorial
categories when needed:

```python
print(book.authors, book.publication_date)

# Work text and notes
with_notes = book.text(categories={"work_text", "note"})

# Any classified category can be requested alone or in combination
for unit in book.units(categories={"bibliography"}):
    print(unit.category, unit.source["href"], unit.source["start"]["xpath"])
```

The intended public top-level contract is deliberately small:

- extraction and results: `extract`, `ExtractedBook`, `ExtractionUnit`,
  `ExtractionDocument`, `ExtractionBlock`, `Creator`, `RAGRecord`, and
  `TextMatch`;
- chunk tokenization: `Tokenizer` and `TokenSpan`;
- independent audit: `audit`, `AuditConfig`, `AuditReport`, `AuditFinding`,
  `AuditCoverage`, `AuditEstimate`, `AuditValidationIssue`,
  `AuditCancelledError`, `estimate_audit`, `AuditBackend`,
  `StructuredLLMBackend`,
  `StructuredResponse`, `OpenAICompatibleConfig`, and
  `OpenAICompatibleBackend`;
- public errors and limits: `EpubExtractionError`, `EpubSafetyLimits`, the
  three English LLM errors, and the three Edition Profile errors;
- schema and version identifiers: `SCHEMA_RAG_RECORD`,
  `SCHEMA_AUDIT_REPORT`, `AUDIT_PROMPT_VERSION`, and `__version__`.

These are the names listed in `segnatura.__all__`. Deterministic implementation
modules remain internal and outside the intended compatibility surface.
Starting with 1.0.0, compatible additions use a minor release, compatible fixes
use a patch release, and incompatible changes require a major release.

Creator metadata is not collapsed to one author string. `book.creators`
preserves every OPF creator, available MARC role codes, sort name, and local
OPF identifier; `book.authors` is a convenience view containing explicit or
unqualified authors. `publication_date_raw` preserves the OPF value and
`publication_date` is populated only when an ISO calendar prefix is valid.

## Executable comparison

During development, Segnatura was compared with the common baseline of joining
all visible XHTML strings. That comparison checks editorial separation rather
than speed: the reproducible example below shows exactly what each method keeps.

The repository includes a self-contained example that generates its own
copyright-free EPUB. It shows the visible strings returned by naive XHTML
scraping beside the work text retained by Segnatura:

```console
python examples/compare_extraction.py
```

The generated book deliberately contains a title page, navigation document,
chapter, and copyright page, so the difference is visible without downloading
or redistributing a third-party EPUB.

An Edition Profile is checked against the complete SHA-256 of the EPUB before any
manual override is applied:

```python
book = extract("book.epub", edition_profile="book.segnatura.json")
```

## Validation

Segnatura was evaluated in two separate controlled experiments on Italian
corpora.

**Classification accuracy.** One hundred blocks from ten EPUB files were
labelled by hand against the rendered original, with Segnatura's prediction
hidden during annotation. The production category matched the human label in
45 of 50 random-audit cases and 48 of 50 targeted challenge cases: 93 of 100
overall, with 99.65% character-weighted accuracy. The targeted cases were
deliberately difficult, so the combined result is a regression benchmark on a
limited set of Italian EPUBs and publishers, not an estimate for every EPUB.

**Effect on retrieval.** The full evaluation used 50 EPUB files and 300
questions: 240 local questions, 30 questions requiring sources from different
parts of the corpus, and 30 negative controls. With identical fixed chunking,
embedding, and retrieval settings, Segnatura reduced searchable records by
5.61% and indexed tokens by 6.33% compared with a document-level keyword
filter that already excluded front matter, contents, indexes, and
bibliographies. Across the 240 local questions, no paired difference in
retrieval of the registered sources was statistically significant at the
conventional 0.05 level. These results establish a smaller index at unchanged
retrieval quality on this corpus.


## Command line

```console
segnatura book.epub --output book.txt
segnatura book.epub --category work_text --category note \
  --format units-json --output book.json
segnatura book.epub --category bibliography --output bibliography.txt
segnatura book.epub --category all --format units-json --output all.json
segnatura book.epub --format rag-jsonl --output book.jsonl
```

The same selector is available in Python. Pass one or more explicit public
categories, or use `categories="all"` when the complete classified inventory
is required:

```python
work_and_notes = book.units(categories={"work_text", "note"})
everything = book.units(categories="all")
```

Chunk size is deliberately a caller policy:

```console
segnatura book.epub --format rag-jsonl --max-tokens 350 \
  --overlap-tokens 40 --context-tokens 1200 --output book.jsonl
```

The built-in Unicode tokenizer preserves valid boundaries but cannot know the
exact token count of an embedding model. Applications can pass that model's
own offset-aware tokenizer through the English `Tokenizer` protocol. Its
`spans(text)` method returns ordered, non-overlapping `TokenSpan(start, end)`
objects and declares a `name` plus whether its counts are `exact`.

## Local RAG and exact provenance

Every RAG record includes the book title, creators, derived author list,
language, publisher, publication date, path, complete EPUB SHA-256, internal
XHTML path, start/end XPath and character offsets, element and text
fingerprints, a short quote, classification evidence, and stable IDs.
Segnatura therefore can identify the exact book and source location after a
retriever returns a passage.

Vector search does not guarantee that it will retrieve every occurrence of a
name. For exhaustive questions such as “which books contain Sherlock Holmes?”,
combine vector retrieval with literal or full-text search. `find_text()` uses
the same category policy as extraction: its default searches work text only.
Pass `categories="all"` when “contains” means anywhere in the complete
classified EPUB inventory, including notes, bibliographies, indexes, and
paratext:

```python
for hit in book.find_text("Sherlock Holmes", categories="all"):
    print(book.title, hit.source["href"], hit.source["start"])
```

See [RAG and provenance](https://github.com/fontistoriche/segnatura/blob/main/docs/RAG.md)
for the recommended multi-book design.

## Independent LLM audit: no required provider

`extract()` never contacts an LLM. The separate `audit()` workflow receives the
original EPUB and the complete deterministic result, submits every block for
review, and returns non-binding suggestions with exact source coordinates.
The stable backend contract is provider-neutral. Segnatura includes a protocol
adapter for compatible Chat Completions endpoints; this is not an OpenAI
requirement.

```python
from segnatura import audit, estimate_audit, extract, OpenAICompatibleBackend

llm = OpenAICompatibleBackend.lm_studio("your-loaded-model")
estimate = estimate_audit(extract("book.epub"))
print(estimate.total_calls, estimate.blocks)
report = audit("book.epub", backend=llm)
assert report.coverage.complete
for finding in report.findings:
    print(finding.href, finding.proposed_category, finding.explanation)
```

For another compatible local or hosted endpoint:

```python
from segnatura import OpenAICompatibleBackend, OpenAICompatibleConfig

llm = OpenAICompatibleBackend(OpenAICompatibleConfig(
    model="model-name",
    base_url="https://example.invalid/v1",
    api_key="...",
))
```

Running an audit never changes extraction or creates an Edition Profile. Suggestions
must be reviewed in the local tool; accepted, edited, and rejected decisions
remain separate, and only approved category corrections are exported. A remote
backend receives EPUB content, so the caller is responsible for privacy,
copyright, cost, and provider terms.

`ExtractedBook.documents()` and `ExtractedBook.blocks()` expose the complete
classified inventory, including excluded material. Every block reports the
stable `classification_rule` decision identifier alongside its source and
evidence, so custom auditors do not need private attributes.
`estimate_audit()` performs no network request. Audit
coverage records documents and blocks successfully submitted to structurally
valid model calls; it cannot claim that a model internally attended to every
token. A malformed response envelope aborts the audit, while isolated invalid
findings are discarded and listed in `report.validation_issues`.

Segnatura includes runtime type annotations for the public API but does not
currently ship a `py.typed` marker. The complete package has not yet passed a
strict static type check, and publishing the marker would overstate typing
coverage of the internal deterministic engine.

## Edition Profile application

The optional local application combines the original EPUB viewer, manual
corrections, and LLM-assisted review. It binds only to `127.0.0.1`, rejects
non-loopback `Host` headers, and rejects an `Origin` that does not match the
active local address and port. The interface defaults to English and also
offers Italian.

```console
segnatura-edition-profile C:\path\to\epubs
segnatura-edition-profile C:\path\to\epubs --audit-lm-studio your-loaded-model
```

The Edition Profile folder argument is optional. When it is omitted, the app
starts from the current directory and lets the user choose an EPUB with the
system file picker:

```console
segnatura-edition-profile
```

The selected EPUB is copied only to a temporary session directory and is not
added to a Segnatura library. Review state lives only in memory and disappears
when the application stops. Passing a folder remains useful for browsing a
collection recursively and lets the application save the final profile next
to its source EPUB. A file selected through the browser is exported through
the browser's normal download flow because browsers do not reveal its original
filesystem path.

The exported `.segnatura.json` Edition Profile is the portable, reproducible
result. Pass it explicitly as `extract(..., edition_profile=...)` or with
`segnatura --edition-profile`. The exact EPUB SHA-256 is verified before any
correction is applied. The application creates no database or hidden working
directory.

Local LLM calls allow 900 seconds by default because complete EPUB review can
be substantially slower than interactive chat. Override this per request with
`--audit-timeout SECONDS`. This is a timeout for each model call, not a global
wall-clock budget. In the interface, **Estimate calls** calculates the exact
number of requests before **Start review** becomes available. Segnatura never
presents a partial, timed-out review as complete. The user may stop a review
explicitly between calls, while the synchronous call already in progress must
first return or reach its own timeout.

The Edition Profile interface can discover models from compatible `/models`
endpoints and run a minimal structured-output test before an audit. Model
discovery is optional because some compatible endpoints do not publish a
model list. API keys and review state exist only in the running process and are
never written to caches, logs, or Edition Profiles.

The application displays Segnatura's deterministic result, accepts manual
corrections, and can optionally review every block with an LLM. Suggestions
never apply themselves: the user accepts, edits, or rejects them before export.
Manual review can also classify an exact text range inside a mixed block;
applying the profile then produces separate, fully cited extraction units
without changing the EPUB.

See [Edition Profiles](https://github.com/fontistoriche/segnatura/blob/main/docs/EDITION-PROFILES.md)
and [Classifier rules](https://github.com/fontistoriche/segnatura/blob/main/docs/CLASSIFIER.md).

## Scope and limitations

- Segnatura can process EPUBs in any language because structural extraction is
  language-independent. Lexical classification rules are strongest for Italian
  and English, with partial support for French, German, and Spanish; other
  languages may require an Edition Profile or LLM-assisted review.
- Segnatura classifies editorial function; it is not an EPUB renderer, OCR
  engine, vector database, embedding model, or complete RAG application.
- Exact source attribution is guaranteed only while the EPUB fingerprint and
  referenced source fragments still match.
- Image-only pages require OCR outside Segnatura.
- Malformed or unusually generated EPUB files can still require an Edition
  Profile.

Segnatura bounds the number of ZIP members, decompressed member and total
bytes, XML element count, and XML nesting depth. It also rejects unsafe member
paths, duplicate or encrypted members, and XML entity declarations. The
defaults can be replaced explicitly with `EpubSafetyLimits` for a trusted,
unusually large edition. See
[EPUB safety boundaries](https://github.com/fontistoriche/segnatura/blob/main/docs/EPUB-SAFETY.md).

## Contributing

Bug reports should include a minimal legally shareable EPUB or structural
fixture, the expected operational category, and Segnatura's evidence. New
language rules should be accompanied by independently labelled EPUB cases.
Contributions that improve publisher diversity are especially useful.

Segnatura is released under the
[MIT License](https://github.com/fontistoriche/segnatura/blob/main/LICENSE).
