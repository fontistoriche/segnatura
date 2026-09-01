# Edition Profiles

An Edition Profile is a small JSON file containing human-approved operational
category corrections for one exact EPUB edition. Corrections may be entered
manually or begin as suggestions from an independent LLM review. Create one
with `segnatura-edition-profile` and pass it to
`extract(..., edition_profile=...)` or `segnatura --edition-profile`.
The command can be started without a path: the local interface then lets the
user select an EPUB from disk. That file is copied to a temporary session
directory and its final profile is downloaded by the browser.

Review state exists only in memory for the current application session. The
app creates no database or hidden working directory. When launched with an
EPUB folder, export writes `<EPUB name>.segnatura.json` next to the source
EPUB. The profile must be passed explicitly to
`extract(..., edition_profile=...)` or `segnatura --edition-profile`.

The schema is `segnatura-edition-profile-1`. A profile can override a complete
internal XHTML document, a classified block, or an exact character range
inside a block. Block overrides win over document overrides. Range overrides
split the effective source unit while leaving uncovered text in its existing
category. Concrete categories are `work_text`, `note`, `bibliography`,
`index`, and `paratext`.

Safety checks are intentionally strict:

- the complete EPUB SHA-256 must match;
- every block ID, internal path, XPath, and text fingerprint must still match;
- every range must be non-empty, inside its block, non-overlapping, and match
  the stored fingerprint of the selected normalized text;
- any mismatch rejects the complete profile rather than applying stale data;
- `mixed` marks a block that needs range-level decisions and is never applied
  directly as extraction policy. Every exported correction is explicit and
  human-approved.

Extraction is always deterministic. An LLM review produces a separate report
and cannot modify the result. The local tool keeps each review run distinct
during the current session, including its model, progress, elapsed time,
findings, and human decisions.
Only accepted or edited suggestions are merged into the exported profile. A
later accepted suggestion supersedes an earlier suggestion for the same
target, while an explicit manual correction always wins.

The app accepts LM Studio and compatible Chat Completions endpoints. It can
load a provider's model list when `/models` is available and can verify the
selected model with one minimal structured-output request before starting an
audit. Manual model entry remains available. A remote provider receives EPUB
excerpts. API credentials remain only in the running process: they are not
written to caches, logs, or the exported profile. Worker errors are redacted
before being shown.

The reviewer first selects **Estimate calls**. The tool then displays the
deterministic number of calls, documents, and blocks and enables the separate
start action. The configured timeout applies independently to each call; there
is no silent global deadline because an incomplete audit must not be reported
as complete. During a review the interface displays completed calls, total
calls, and elapsed time; after completion it preserves the total duration. The
review pane exposes only findings that can become concrete Edition Profile
overrides, while the complete diagnostic report remains available during the
current session. A reviewer may
request cancellation, which takes effect after the synchronous model call
already in progress returns or reaches its per-call timeout.

Edition Profiles run after deterministic classification. They change only the
operational inclusion category; they do not retrain the classifier or hide its
original fine-grained editorial role. Range overrides become separate source
units during ingestion, preserving continuous text coverage and exact EPUB
coordinates for every resulting unit and RAG record.
