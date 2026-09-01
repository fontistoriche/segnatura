# RAG and provenance

Segnatura prepares records for a retrieval system; it does not prescribe a
vector database. A robust local system should store `RAGRecord.text` as the
retrievable field and keep the entire `RAGRecord.metadata` object unchanged.

For multiple books, use two retrieval paths:

1. literal or full-text search for exhaustive names, quotations, identifiers,
   and spelling-sensitive questions;
2. vector or hybrid search for semantic questions.

Merge and rank the candidates, then cite the stored source object. The metadata
identifies the exact EPUB with `epub_sha256`, the internal document with `href`,
and the DOM range with XPath, offsets, and fingerprints. The `book` object also
contains the human-readable title, all OPF creators with their available roles,
a derived author list, language, publisher, normalized and raw publication
date, and original local path. Keep the complete `book` object in the index: a
displayed author string can always be derived later, whereas discarded creator
roles cannot be recovered from a chunk.

Chunk IDs are not citations. They may change when tokenizer or chunk budgets
change. Source coordinates are built from the EPUB structure and can be
verified with `ExtractedBook.verify_source()`.

## Small-to-big retrieval

`ExtractedBook.rag_records()` creates small child records without crossing a
document or operational-role boundary. Its `categories` argument selects any
combination of `work_text`, `note`, `bibliography`, `index`, and `paratext`;
the default is work text only, while `categories="all"` selects the complete
classified inventory. The same category selection is available on `units()`,
`text()`, and `find_text()`. After retrieval, applications can use
the associated sequence and source units to present broader context. This keeps
embedding records focused while preventing context expansion from crossing
from work text into notes, bibliography, an index, or paratext.

## Completeness

Exact provenance answers “where did this returned passage come from?”. It does
not answer “did the retriever find every relevant passage?”. Use
`ExtractedBook.find_text()` or a conventional full-text index when completeness
for literal terms matters. Completeness is always relative to the selected
operational categories: the default searches work text, while
`find_text(query, categories="all")` searches every classified category in the
EPUB.
