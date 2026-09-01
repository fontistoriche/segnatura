"""Independent, full-book LLM audit for deterministic EPUB extraction.

The auditor never changes an extraction result.  It submits the complete
deterministic block inventory to a caller-supplied structured LLM backend and
returns review suggestions that a human may accept, edit, or reject before an
Edition Profile is created.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from .api import ExtractedBook, extract
from .categories import PUBLIC_CATEGORIES
from .epub_safety import EpubSafetyLimits
from .llm import InvalidLLMResponseError, StructuredLLMBackend


SCHEMA_AUDIT_REPORT = "segnatura-audit-report-2"
AUDIT_PROMPT_VERSION = "segnatura-full-book-audit-3"
AUDIT_FINDING_KINDS = (
    "category_change",
    "possible_omission",
    "structure_issue",
)
AUDIT_FINDING_SCOPES = ("book", "document", "block")
AUDIT_SEVERITIES = ("info", "warning", "critical")


class AuditCancelledError(RuntimeError):
    """Raised when a caller stops a complete audit between model calls."""


@runtime_checkable
class AuditBackend(Protocol):
    """Provider-neutral backend accepted by :func:`audit`.

    This deliberately matches :class:`StructuredLLMBackend`: existing local
    LM Studio and compatible remote adapters can be reused without coupling
    the audit contract to a provider.
    """

    def request_structured(self, input_data: dict, system_prompt: str,
                           schema: dict, prompt_version: str): ...


@dataclass(frozen=True)
class AuditConfig:
    """Batch policy for a complete audit.

    There is intentionally no default call budget: once a user explicitly
    requests an audit, every deterministic block must be submitted.  Limits
    here bound individual requests, not book coverage.
    """

    max_blocks_per_batch: int = 18
    max_text_characters_per_batch: int = 24_000
    document_excerpt_characters: int = 900
    max_documents_per_overview_batch: int = 40
    max_overview_characters_per_batch: int = 48_000
    max_findings_per_call: int = 24

    def __post_init__(self) -> None:
        if self.max_blocks_per_batch < 1:
            raise ValueError("max_blocks_per_batch must be positive")
        if self.max_text_characters_per_batch < 1_000:
            raise ValueError(
                "max_text_characters_per_batch must be at least 1000")
        if self.document_excerpt_characters < 0:
            raise ValueError("document_excerpt_characters cannot be negative")
        if self.max_documents_per_overview_batch < 1:
            raise ValueError(
                "max_documents_per_overview_batch must be positive")
        if self.max_overview_characters_per_batch < 1_000:
            raise ValueError(
                "max_overview_characters_per_batch must be at least 1000")
        if self.max_findings_per_call < 1:
            raise ValueError("max_findings_per_call must be positive")


@dataclass(frozen=True)
class AuditFinding:
    """One non-binding LLM suggestion tied to exact EPUB coordinates."""

    id: str
    kind: str
    scope: str
    href: str
    block_id: str | None
    xpath: str | None
    fingerprint: str | None
    current_category: str | None
    proposed_category: str | None
    severity: str
    confidence: float
    explanation: str
    evidence: tuple[str, ...] = ()
    excerpt: str = ""

    @property
    def can_create_edition_profile_override(self) -> bool:
        return (
            self.kind == "category_change"
            and self.scope in {"document", "block"}
            and self.proposed_category in PUBLIC_CATEGORIES
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        data["can_create_edition_profile_override"] = \
            self.can_create_edition_profile_override
        return data


@dataclass(frozen=True)
class AuditCoverage:
    documents_total: int
    documents_submitted: int
    blocks_total: int
    blocks_submitted: int

    @property
    def complete(self) -> bool:
        return (
            self.documents_total == self.documents_submitted
            and self.blocks_total == self.blocks_submitted
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "complete": self.complete,
        }


@dataclass(frozen=True)
class AuditEstimate:
    """Deterministic work estimate computed before contacting an LLM."""

    documents: int
    blocks: int
    overview_calls: int
    block_review_calls: int
    total_calls: int
    text_characters: int
    estimated_input_characters: int
    largest_overview_documents: int
    largest_overview_input_characters: int
    largest_batch_blocks: int
    largest_batch_text_characters: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class AuditValidationIssue:
    """One malformed finding discarded without losing valid batch findings."""

    call: str
    finding_index: int
    reason: str
    href: str = ""
    block_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    """Serializable output of an independent full-book review."""

    book: dict[str, Any]
    generated_at: str
    prompt_version: str
    models: tuple[str, ...]
    coverage: AuditCoverage
    findings: tuple[AuditFinding, ...]
    validation_issues: tuple[AuditValidationIssue, ...]
    calls: int
    cached_calls: int
    network_attempts: int
    invalid_json_responses: int
    schema: str = SCHEMA_AUDIT_REPORT

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "prompt_version": self.prompt_version,
            "book": self.book,
            "models": list(self.models),
            "coverage": self.coverage.to_dict(),
            "statistics": {
                "calls": self.calls,
                "cached_calls": self.cached_calls,
                "network_attempts": self.network_attempts,
                "invalid_json_responses": self.invalid_json_responses,
                "findings": len(self.findings),
                "discarded_findings": len(self.validation_issues),
            },
            "findings": [item.to_dict() for item in self.findings],
            "validation_issues": [
                item.to_dict() for item in self.validation_issues
            ],
        }


_SYSTEM_PROMPT = """You are independently auditing a complete EPUB extraction.
Segnatura has already produced a final deterministic category for every parsed
block. Do not assume that low confidence means wrong, and do not limit review
to uncertain-looking blocks. Inspect every supplied target.

Operational categories:
- work_text: readable content of the work, including introductions, prefaces,
  afterwords, appendices, epigraphs, glossaries, and useful chronologies;
- note: footnotes, endnotes, and note apparatus linked to the work;
- bibliography: autonomous lists of references or works cited;
- index: tables of contents and analytical, name, place, or illustration
  indexes;
- paratext: title pages, copyright, colophons, publisher promotion, and other
  production metadata.

Report only actionable disagreements or structural anomalies. A heading is
work_text when it belongs to the work; it is index only when it appears as an
entry inside an index or contents page. Never rewrite the EPUB and never claim
that a suggestion has already been applied. Every finding must identify an
existing target from the input and cite observable evidence.

The document overview may be split into numbered batches. When it is split,
each call receives only part of the document inventory and must make only
document-scoped findings about supplied targets, never book-wide conclusions.
"""


def _response_schema(scopes: tuple[str, ...], maximum: int) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "segnatura_epub_audit",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "maxItems": maximum,
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": list(AUDIT_FINDING_KINDS),
                                },
                                "scope": {
                                    "type": "string", "enum": list(scopes),
                                },
                                "href": {"type": "string"},
                                "block_id": {"type": "string"},
                                "proposed_category": {
                                    "type": "string",
                                    "enum": ["", *PUBLIC_CATEGORIES],
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": list(AUDIT_SEVERITIES),
                                },
                                "confidence": {
                                    "type": "number", "minimum": 0,
                                    "maximum": 1,
                                },
                                "explanation": {"type": "string"},
                                "evidence": {
                                    "type": "array", "maxItems": 4,
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "kind", "scope", "href", "block_id",
                                "proposed_category", "severity", "confidence",
                                "explanation", "evidence",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["findings"],
                "additionalProperties": False,
            },
        },
    }


def _excerpt(text: str, maximum: int) -> str:
    text = " ".join(text.split())
    if maximum <= 0 or len(text) <= maximum:
        return text
    first = maximum // 2
    last = maximum - first
    return f"{text[:first]} [...] {text[-last:]}"


def _document_manifest(book: ExtractedBook, maximum: int) -> list[dict]:
    return [
        item.to_dict()
        for item in book.documents(excerpt_characters=maximum)
    ]


def _overview_input(common: dict[str, Any], documents: list[dict],
                    index: int, count: int) -> dict[str, Any]:
    return {
        **common,
        "audit_pass": "book_overview",
        "overview_batch_index": index,
        "overview_batch_count": count,
        "documents": documents,
    }


def _serialized_characters(data: dict[str, Any]) -> int:
    return len(json.dumps(
        data, ensure_ascii=False, separators=(",", ":")))


def _overview_batches(manifest: list[dict], config: AuditConfig,
                      common: dict[str, Any]) \
        -> list[list[dict]]:
    """Split the document inventory before it can fill one model request."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    # The final batch count is not known yet.  Using the maximum possible
    # index/count keeps this first pass conservative about their digit width.
    maximum_marker = max(1, len(manifest))
    for item in manifest:
        candidate = [*current, item]
        size = _serialized_characters(_overview_input(
            common, candidate, maximum_marker, maximum_marker))
        if current and (
                len(current) >= config.max_documents_per_overview_batch
                or size > config.max_overview_characters_per_batch):
            batches.append(current)
            current = []
            candidate = [item]
            size = _serialized_characters(_overview_input(
                common, candidate, maximum_marker, maximum_marker))
        if size > config.max_overview_characters_per_batch:
            raise ValueError(
                "one document overview exceeds "
                "max_overview_characters_per_batch; reduce "
                "document_excerpt_characters or raise the overview limit")
        current = candidate
    if current:
        batches.append(current)
    return batches


def _block_record(block) -> dict[str, Any]:
    return {
        "block_id": block.id,
        "href": block.href,
        "order": block.order,
        "xpath": block.xpath,
        "fingerprint": block.fingerprint,
        "shape": block.shape,
        "title": block.title,
        "text": block.text,
        "deterministic_category": block.category,
        "deterministic_confidence": block.confidence,
        "classification_source": block.classification_source,
        "classification_rule": block.classification_rule,
        "classification_evidence": list(block.evidence),
        "epub_types": list(block.epub_types),
        "aria_roles": list(block.aria_roles),
        "dom_markers": list(block.dom_markers),
    }


def _batches(book: ExtractedBook, config: AuditConfig):
    by_href: dict[str, list] = {}
    for block in book.blocks():
        by_href.setdefault(block.href, []).append(block)
    for document in book.documents(excerpt_characters=0):
        current: list = []
        characters = 0
        for block in by_href.get(document.href, []):
            size = len(block.text)
            if current and (
                    len(current) >= config.max_blocks_per_batch
                    or characters + size > config.max_text_characters_per_batch):
                yield document, current
                current, characters = [], 0
            current.append(block)
            characters += size
        if current:
            yield document, current


def _finding_id(kind: str, scope: str, href: str, block_id: str,
                proposed: str, explanation: str) -> str:
    payload = "\0".join(
        (kind, scope, href, block_id, proposed, explanation)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _validate_finding(raw: Any, *, allowed_scopes: set[str],
                      documents: dict[str, Any], blocks: dict[str, Any]) \
        -> AuditFinding:
    if not isinstance(raw, dict):
        raise InvalidLLMResponseError("audit finding must be an object")
    kind = raw.get("kind")
    scope = raw.get("scope")
    href = str(raw.get("href") or "")
    block_id = str(raw.get("block_id") or "")
    proposed = str(raw.get("proposed_category") or "") or None
    severity = raw.get("severity")
    explanation = str(raw.get("explanation") or "").strip()
    evidence = raw.get("evidence")
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise InvalidLLMResponseError(
            "audit confidence must be numeric") from exc
    if kind not in AUDIT_FINDING_KINDS:
        raise InvalidLLMResponseError(f"invalid audit finding kind: {kind!r}")
    if scope not in allowed_scopes:
        raise InvalidLLMResponseError(f"invalid audit finding scope: {scope!r}")
    if severity not in AUDIT_SEVERITIES:
        raise InvalidLLMResponseError(f"invalid audit severity: {severity!r}")
    if not 0 <= confidence <= 1:
        raise InvalidLLMResponseError(
            "audit confidence must be between 0 and 1")
    if not explanation:
        raise InvalidLLMResponseError("audit explanation cannot be empty")
    if (not isinstance(evidence, list)
            or any(not isinstance(item, str) for item in evidence)):
        raise InvalidLLMResponseError(
            "audit evidence must be an array of strings")
    if proposed is not None and proposed not in PUBLIC_CATEGORIES:
        raise InvalidLLMResponseError(
            f"invalid proposed category: {proposed!r}")

    current_category = None
    xpath = fingerprint = None
    excerpt = ""
    if scope == "book":
        if href or block_id:
            raise InvalidLLMResponseError(
                "book finding cannot identify a document or block")
    elif scope == "document":
        target = documents.get(href)
        if target is None or block_id:
            raise InvalidLLMResponseError(
                f"audit document target does not exist: {href!r}")
        categories = target["category_counts"]
        current_category = (next(iter(categories))
                            if len(categories) == 1 else None)
        excerpt = target["visible_text_excerpt"]
    else:
        target = blocks.get((href, block_id))
        if target is None:
            raise InvalidLLMResponseError(
                f"audit block target does not exist: {href}#{block_id}")
        current_category = target["deterministic_category"]
        xpath = target["xpath"]
        fingerprint = target["fingerprint"]
        excerpt = _excerpt(target["text"], 500)

    if kind == "category_change":
        if scope == "book" or proposed is None:
            raise InvalidLLMResponseError(
                "category_change requires a document or block category")
        if current_category is not None and proposed == current_category:
            raise InvalidLLMResponseError(
                "category_change must change the current category")

    return AuditFinding(
        id=_finding_id(kind, scope, href, block_id, proposed or "",
                       explanation),
        kind=kind,
        scope=scope,
        href=href,
        block_id=block_id or None,
        xpath=xpath,
        fingerprint=fingerprint,
        current_category=current_category,
        proposed_category=proposed,
        severity=severity,
        confidence=round(confidence, 6),
        explanation=explanation,
        evidence=tuple(item.strip() for item in evidence if item.strip()),
        excerpt=excerpt,
    )


def _validate_findings(data: Any, *, call: str,
                       allowed_scopes: set[str],
                       documents: dict[str, Any], blocks: dict[str, Any]) \
        -> tuple[list[AuditFinding], list[AuditValidationIssue]]:
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise InvalidLLMResponseError("audit response must contain findings array")
    findings: list[AuditFinding] = []
    issues: list[AuditValidationIssue] = []
    for index, raw in enumerate(data["findings"], 1):
        try:
            findings.append(_validate_finding(
                raw, allowed_scopes=allowed_scopes,
                documents=documents, blocks=blocks))
        except InvalidLLMResponseError as error:
            raw_target = raw if isinstance(raw, dict) else {}
            issues.append(AuditValidationIssue(
                call=call,
                finding_index=index,
                reason=str(error),
                href=str(raw_target.get("href") or ""),
                block_id=str(raw_target.get("block_id") or ""),
            ))
    return findings, issues


def estimate_audit(source: ExtractedBook | Path | str, *,
                   config: AuditConfig | None = None,
                   edition_profile: Path | str | dict | None = None,
                   safety_limits: EpubSafetyLimits | None = None) \
        -> AuditEstimate:
    """Estimate complete-audit calls without contacting any LLM.

    When ``source`` is already an :class:`ExtractedBook`, ``edition_profile`` and
    ``safety_limits`` are ignored because extraction has already completed.
    """
    config = config or AuditConfig()
    book = (source if isinstance(source, ExtractedBook) else
            extract(source, edition_profile=edition_profile,
                    safety_limits=safety_limits))
    batches = list(_batches(book, config))
    batch_sizes = [len(items) for _, items in batches]
    batch_characters = [sum(len(item.text) for item in items)
                        for _, items in batches]
    blocks = book.blocks()
    manifest = _document_manifest(book, config.document_excerpt_characters)
    documents = {item["href"]: item for item in manifest}
    common = {
        "book": book.book_metadata(),
        "deterministic_result_is_final": True,
    }
    overview_batches = _overview_batches(manifest, config, common)
    inputs = [
        _overview_input(common, batch, index, len(overview_batches))
        for index, batch in enumerate(overview_batches, 1)
    ]
    overview_input_characters = [
        _serialized_characters(item) for item in inputs
    ]
    for batch_index, (document, items) in enumerate(batches, 1):
        inputs.append({
            **common,
            "audit_pass": "complete_block_review",
            "batch_index": batch_index,
            "target_document": documents[document.href],
            "blocks": [_block_record(item) for item in items],
        })
    return AuditEstimate(
        documents=len(book.documents(excerpt_characters=0)),
        blocks=len(blocks),
        overview_calls=len(overview_batches),
        block_review_calls=len(batches),
        total_calls=len(overview_batches) + len(batches),
        text_characters=sum(len(item.text) for item in blocks),
        estimated_input_characters=sum(len(json.dumps(
            item, ensure_ascii=False, separators=(",", ":")))
            for item in inputs),
        largest_overview_documents=max(
            (len(item) for item in overview_batches), default=0),
        largest_overview_input_characters=max(
            overview_input_characters, default=0),
        largest_batch_blocks=max(batch_sizes, default=0),
        largest_batch_text_characters=max(batch_characters, default=0),
    )


def audit(source: ExtractedBook | Path | str, *, backend: AuditBackend,
          config: AuditConfig | None = None,
          edition_profile: Path | str | dict | None = None,
          safety_limits: EpubSafetyLimits | None = None,
          progress: Callable[[int, int, str], None] | None = None,
          cancelled: Callable[[], bool] | None = None) -> AuditReport:
    """Audit every deterministic document and block without changing them.

    The returned suggestions are deliberately non-binding.  A caller must
    present them for human review and create an Edition Profile from accepted
    choices. When ``source`` is already an :class:`ExtractedBook`,
    ``edition_profile`` and ``safety_limits`` are ignored because extraction
    has already completed.
    """

    if not isinstance(backend, StructuredLLMBackend):
        raise TypeError("backend must implement request_structured")
    config = config or AuditConfig()
    book = (source if isinstance(source, ExtractedBook) else
            extract(source, edition_profile=edition_profile,
                    safety_limits=safety_limits))
    manifest = _document_manifest(book, config.document_excerpt_characters)
    documents = {item["href"]: item for item in manifest}
    all_blocks = {
        (record["href"], record["block_id"]): record
        for record in (_block_record(item) for item in book.blocks())
    }
    common = {
        "book": book.book_metadata(),
        "deterministic_result_is_final": True,
    }
    overview_batches = _overview_batches(manifest, config, common)
    block_batches = list(_batches(book, config))
    total_calls = len(overview_batches) + len(block_batches)

    calls = cached_calls = network_attempts = invalid_json = 0
    models: list[str] = []
    findings: list[AuditFinding] = []
    validation_issues: list[AuditValidationIssue] = []

    def request(input_data: dict, scopes: tuple[str, ...], version: str):
        nonlocal calls, cached_calls, network_attempts, invalid_json
        if cancelled is not None and cancelled():
            raise AuditCancelledError("audit cancelled by the user")
        response = backend.request_structured(
            input_data, _SYSTEM_PROMPT,
            _response_schema(scopes, config.max_findings_per_call), version,
        )
        calls += 1
        cached_calls += int(bool(response.cached))
        network_attempts += int(response.network_attempts)
        invalid_json += int(response.invalid_json_responses)
        if response.model and response.model not in models:
            models.append(response.model)
        if progress is not None:
            progress(calls, total_calls, str(input_data["audit_pass"]))
        if cancelled is not None and cancelled():
            raise AuditCancelledError("audit cancelled by the user")
        return response.data

    submitted_blocks: set[tuple[str, str]] = set()
    submitted_documents: set[str] = set()
    overview_scopes = (("book", "document") if len(overview_batches) == 1
                       else ("document",))
    for overview_index, overview_batch in enumerate(overview_batches, 1):
        overview = request(
            _overview_input(common, overview_batch, overview_index,
                            len(overview_batches)),
            overview_scopes, f"{AUDIT_PROMPT_VERSION}-overview")
        overview_findings, overview_issues = _validate_findings(
            overview, call=f"book_overview_{overview_index}",
            allowed_scopes=set(overview_scopes),
            documents=documents, blocks=all_blocks)
        findings.extend(overview_findings)
        validation_issues.extend(overview_issues)
        submitted_documents.update(item["href"] for item in overview_batch)
    for batch_index, (document, results) in enumerate(block_batches, 1):
        records = [_block_record(item) for item in results]
        batch_blocks = {
            (item["href"], item["block_id"]): item for item in records
        }
        response_data = request({
            **common,
            "audit_pass": "complete_block_review",
            "batch_index": batch_index,
            "target_document": documents[document.href],
            "blocks": records,
        }, ("block",), f"{AUDIT_PROMPT_VERSION}-blocks")
        batch_findings, batch_issues = _validate_findings(
            response_data, call=f"block_batch_{batch_index}",
            allowed_scopes={"block"},
            documents=documents, blocks=batch_blocks)
        findings.extend(batch_findings)
        validation_issues.extend(batch_issues)
        submitted_blocks.update(batch_blocks)

    deduplicated = {item.id: item for item in findings}
    coverage = AuditCoverage(
        documents_total=len(documents),
        documents_submitted=len(submitted_documents),
        blocks_total=len(all_blocks),
        blocks_submitted=len(submitted_blocks),
    )
    if (submitted_documents != set(documents)
            or submitted_blocks != set(all_blocks)
            or not coverage.complete):
        raise RuntimeError("internal audit coverage failure")
    return AuditReport(
        book=book.book_metadata(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        prompt_version=AUDIT_PROMPT_VERSION,
        models=tuple(models),
        coverage=coverage,
        findings=tuple(deduplicated.values()),
        validation_issues=tuple(validation_issues),
        calls=calls,
        cached_calls=cached_calls,
        network_attempts=network_attempts,
        invalid_json_responses=invalid_json,
    )


__all__ = [
    "SCHEMA_AUDIT_REPORT", "AUDIT_PROMPT_VERSION", "AuditBackend",
    "AuditCancelledError",
    "AuditConfig", "AuditFinding", "AuditCoverage", "AuditEstimate",
    "AuditValidationIssue", "AuditReport", "estimate_audit", "audit",
]
