# Changelog

## 1.0.0 — 2026-09-01

- Added deterministic, structure-aware EPUB extraction with the public
  `extract()` API and command-line interface.
- Added operational classification for work text, notes, bibliographies,
  indexes, and paratext, with stable rule identifiers and complete document
  and block inventories.
- Added selectable category extraction across units, plain text, literal
  search, RAG records, and the command line.
- Added vector-store-ready RAG records with chunk-independent EPUB provenance,
  source verification, creator metadata, and configurable tokenization.
- Added bounded ZIP and streaming XML validation for untrusted EPUB input.
- Added provider-neutral, complete-book LLM auditing with batched overviews,
  call estimates, coverage reporting, progress, cancellation, and isolated
  malformed-finding handling.
- Added exact-edition Edition Profiles for human-approved document, block, and
  text-range corrections, verified against the EPUB and source fingerprints.
- Added the optional local Edition Profile application for manual and
  LLM-assisted review, model discovery and connection testing, in-memory review
  state, and JSON export without databases or hidden working directories.
- Added loopback `Host` and matching `Origin` validation to the local
  application, plus redaction of credential-bearing diagnostics.
- Added Windows and Linux CI for Python 3.10–3.13 and direct tests for the
  public API, CLI, application, audit, safety limits, packaging, classifier,
  and extraction pipeline.
