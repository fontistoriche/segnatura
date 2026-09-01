"""Local tools that display EPUB files in their original rendered context.

Flask is optional. The server binds only to loopback and reads resources
directly from each EPUB archive instead of extracting books into a public
directory.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import copy
import tempfile
import threading
import uuid
import webbrowser
import weakref
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .apparati import analizza_apparati
from .api import ExtractedBook
from .audit import (AuditCancelledError, AuditConfig, AuditReport, audit,
                    estimate_audit)
from .edition_profile import (SCHEMA_EDITION_PROFILE,
                              create_edition_profile_payload)
from .categories import PUBLIC_CATEGORIES, to_public
from .llm import (InvalidLLMResponseError, LLMError,
                  OpenAICompatibleBackend, OpenAICompatibleConfig,
                  StructuredLLMBackend)
from .lettura import Libro, leggi

SCHEMA_EXPORT = SCHEMA_EDITION_PROFILE
PROFILE_LABELS = PUBLIC_CATEGORIES + ("mixed",)
HTML_SUFFIXES = {".xhtml", ".html", ".htm"}
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LLM_CONNECTION_TEST_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "segnatura_connection_test",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}
MAX_EPUB_UPLOAD_BYTES = 512 * 1024 * 1024


def _loopback_authority(value: str) -> tuple[str, int | None] | None:
    """Return a validated loopback host and optional port."""
    if not value or value != value.strip() or "://" in value:
        return None
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError:
        return None
    hostname = (parsed.hostname or "").casefold()
    if (hostname not in LOOPBACK_HOSTS or parsed.username is not None
            or parsed.password is not None or parsed.path
            or parsed.query or parsed.fragment):
        return None
    return hostname, port


def _origin_matches_host(origin: str, host: str, request_scheme: str) -> bool:
    """Accept only an HTTP(S) Origin equal to the request's loopback host."""
    expected = _loopback_authority(host)
    if expected is None:
        return False
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    if (parsed.scheme not in {"http", "https"}
            or hostname != expected[0]
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        return False
    default_origin_port = 443 if parsed.scheme == "https" else 80
    default_request_port = 443 if request_scheme == "https" else 80
    return ((origin_port or default_origin_port)
            == (expected[1] or default_request_port))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error_message(error: Exception, *secrets: str | None) -> str:
    """Return a bounded diagnostic without URL queries or credential text."""
    message = str(error)
    message = re.sub(r"([?&](?:api[_-]?key|key|token|access_token)=)[^&\s]+",
                     r"\1[redacted]", message, flags=re.I)
    message = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+",
                     r"\1[redacted]", message)
    for secret in secrets:
        if secret and len(secret) >= 4:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"https?://([^/?#\s]+)[^\s]*",
                     r"https://\1/[redacted]", message)
    return message[:2_000]


def _package_version() -> str:
    try:
        return version("segnatura")
    except PackageNotFoundError:
        return "0+local"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> str | None:
    """Restituisce un nome ZIP POSIX sicuro o ``None``."""
    if not name or "\\" in name or name.startswith("/"):
        return None
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _mime_type(name: str) -> str:
    guessed = mimetypes.guess_type(name)[0]
    extras = {
        ".xhtml": "text/html",
        ".opf": "application/oebps-package+xml",
        ".ncx": "application/x-dtbncx+xml",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    return extras.get(PurePosixPath(name).suffix.lower(), guessed or
                      "application/octet-stream")


def _decode_html(raw: bytes) -> str:
    head = raw[:300].decode("ascii", "ignore")
    match = re.search(r"encoding\s*=\s*['\"]([^'\"]+)", head, re.I)
    encodings = [match.group(1)] if match else []
    encodings += ["utf-8", "cp1252"]
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def _inject_highlight(raw: bytes, fragments: list[dict], nonce: str) -> bytes:
    """Aggiunge l'evidenziazione senza eseguire script dell'editore."""
    document = _decode_html(raw)
    payload = json.dumps(fragments, ensure_ascii=False).replace("</", "<\\/")
    addition = f"""
<style id="segnatura-annotation-style">
.segnatura-target {{
  box-shadow: inset 5px 0 #efb83f, inset -5px 0 #efb83f !important;
  background: rgba(255, 225, 120, .30) !important;
  scroll-margin: 18vh !important;
}}
.segnatura-target-start {{ border-top: 5px solid #efb83f !important; }}
.segnatura-target-end {{ border-bottom: 5px solid #efb83f !important; }}
::highlight(segnatura-saved-range) {{
  background: rgba(46, 125, 246, .28);
}}
::highlight(segnatura-range-preview) {{
  background: rgba(46, 125, 246, .58);
}}
</style>
<script nonce="{nonce}">
(() => {{
  const fragments = {payload};
  const targets = [];
  const resolved = [];
  for (const fragment of fragments) {{
    try {{
      const result = document.evaluate(fragment.xpath, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      let node = result.singleNodeValue;
      const source = node;
      if (node && node.nodeType !== Node.ELEMENT_NODE) node = node.parentElement;
      if (node && !targets.includes(node)) targets.push(node);
      if (source) resolved.push({{...fragment, source}});
    }} catch (_) {{}}
  }}
  if (!targets.length) return;
  for (const target of targets) target.classList.add('segnatura-target');
  targets[0].classList.add('segnatura-target-start');
  targets[targets.length - 1].classList.add('segnatura-target-end');
  requestAnimationFrame(() => targets[0].scrollIntoView({{block:'center'}}));

  function normalizedUnits(source) {{
    let nodes = [];
    if (source.nodeType === Node.TEXT_NODE) nodes = [source];
    else {{
      const walker = document.createTreeWalker(source, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode())
        nodes.push(node);
    }}
    const raw = [];
    nodes.forEach((node, index) => {{
      if (index) raw.push({{
        char:' ', before:[nodes[index - 1], nodes[index - 1].data.length],
        after:[node, 0]
      }});
      for (let offset = 0; offset < node.data.length; offset++) raw.push({{
        char:node.data[offset], before:[node, offset], after:[node, offset + 1]
      }});
    }});
    const units = [];
    for (const item of raw) {{
      if (/\\s/u.test(item.char)) {{
        const previous = units[units.length - 1];
        if (previous?.char === ' ') previous.after = item.after;
        else units.push({{char:' ', before:item.before, after:item.after}});
      }} else units.push(item);
    }}
    while (units[0]?.char === ' ') units.shift();
    while (units[units.length - 1]?.char === ' ') units.pop();
    return units;
  }}

  function rangesFor(intervals) {{
    const ranges = [];
    for (const interval of intervals || []) {{
      const start = Number(interval.start);
      const end = Number(interval.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) || end <= start)
        continue;
      for (const fragment of resolved) {{
        const overlapStart = Math.max(start, fragment.start);
        const overlapEnd = Math.min(end, fragment.end);
        if (overlapEnd <= overlapStart) continue;
        const units = normalizedUnits(fragment.source);
        const localStart = overlapStart - fragment.start;
        const localEnd = overlapEnd - fragment.start;
        if (localStart < 0 || localEnd > units.length || !units[localStart] ||
            !units[localEnd - 1]) continue;
        const range = document.createRange();
        range.setStart(...units[localStart].before);
        range.setEnd(...units[localEnd - 1].after);
        ranges.push(range);
      }}
    }}
    return ranges;
  }}

  addEventListener('message', event => {{
    if (event.source !== parent || event.data?.type !== 'segnatura-ranges') return;
    if (!CSS.highlights || typeof Highlight === 'undefined') return;
    CSS.highlights.delete('segnatura-saved-range');
    CSS.highlights.delete('segnatura-range-preview');
    const saved = rangesFor(event.data.saved);
    const preview = rangesFor(event.data.preview ? [event.data.preview] : []);
    if (saved.length) CSS.highlights.set(
      'segnatura-saved-range', new Highlight(...saved));
    if (preview.length) CSS.highlights.set(
      'segnatura-range-preview', new Highlight(...preview));
  }});
}})();
</script>"""
    closing = re.search(r"</body\s*>", document, re.I)
    if closing:
        document = document[:closing.start()] + addition + document[closing.start():]
    else:
        closing = re.search(r"</html\s*>", document, re.I)
        at = closing.start() if closing else len(document)
        document = document[:at] + addition + document[at:]
    return document.encode("utf-8")


@dataclass
class OpenBook:
    id: str
    sha256: str
    path: Path
    relative_path: str
    book: Libro
    extraction: object | None = None

    @property
    def documents(self) -> dict[str, object]:
        return {section.href: section for section in self.book.sezioni}

    @property
    def blocks(self) -> dict[str, tuple[object, object]]:
        return {
            block.id: (section, block)
            for section in self.book.sezioni
            for block in section.blocchi
        }


class SessionStore:
    """Keep one application session in memory; nothing is persisted locally."""

    def __init__(self):
        self._lock = threading.RLock()
        self._books: dict[str, dict] = {}
        self._annotations: dict[str, dict[str, dict[str, dict]]] = {}
        self._audit_runs: dict[str, dict] = {}

    def _book_annotations(self, book_id: str) -> dict[str, dict[str, dict]]:
        return self._annotations.setdefault(
            book_id, {"documents": {}, "blocks": {}, "ranges": {}})

    def remember_book(self, opened: OpenBook) -> None:
        with self._lock:
            self._books[opened.id] = {
                "book_id": opened.id,
                "sha256": opened.sha256,
                "relative_path": opened.relative_path,
                "title": opened.book.titolo,
                "language": opened.book.lingua,
                "opened_at": _now(),
            }
            self._book_annotations(opened.id)

    def save_document(self, book_id: str, href: str, label: str,
                      certainty: str, note: str) -> None:
        with self._lock:
            self._book_annotations(book_id)["documents"][href] = {
                "href": href, "label": label, "certainty": certainty,
                "note": note, "updated_at": _now(),
            }

    def save_block(self, book_id: str, block, label: str,
                   certainty: str, note: str) -> None:
        with self._lock:
            self._book_annotations(book_id)["blocks"][block.id] = {
                "block_id": block.id, "href": block.href,
                "xpath": block.xpath, "fingerprint": block.fingerprint,
                "label": label, "certainty": certainty, "note": note,
                "updated_at": _now(),
            }

    def save_range(self, book_id: str, block, start: int, end: int,
                   label: str, certainty: str, note: str) -> dict:
        selected = block.testo[start:end]
        text_fingerprint = hashlib.sha256(
            re.sub(r"\s+", " ", selected).strip().casefold().encode("utf-8")
        ).hexdigest()[:20]
        range_id = hashlib.sha256(
            f"{book_id}\0{block.id}\0{start}\0{end}".encode("utf-8")
        ).hexdigest()[:24]
        updated_at = _now()
        with self._lock:
            ranges = self._book_annotations(book_id)["ranges"]
            overlap = any(
                item["range_id"] != range_id
                and item["block_id"] == block.id
                and item["start"] < end and item["end"] > start
                for item in ranges.values()
            )
            if overlap:
                raise ValueError("range overlaps an existing correction")
            record = {
            "range_id": range_id, "block_id": block.id, "href": block.href,
            "xpath": block.xpath, "block_fingerprint": block.fingerprint,
            "start": start, "end": end,
            "text_fingerprint": text_fingerprint, "label": label,
            "certainty": certainty, "note": note,
            "updated_at": updated_at,
            }
            ranges[range_id] = record
            return copy.deepcopy(record)

    def delete_range(self, book_id: str, range_id: str) -> bool:
        with self._lock:
            ranges = self._book_annotations(book_id)["ranges"]
            return ranges.pop(range_id, None) is not None

    def annotations(self, book_id: str) -> dict:
        with self._lock:
            return copy.deepcopy(self._book_annotations(book_id))

    def create_audit_run(self, run_id: str, opened: OpenBook,
                         total_calls: int, provider: str,
                         requested_model: str) -> None:
        with self._lock:
            self._audit_runs[run_id] = {
                "run_id": run_id, "book_id": opened.id,
                "status": "running", "created_at": _now(),
                "completed_at": None, "report": None, "error": "",
                "progress_current": 0, "progress_total": total_calls,
                "current_phase": "", "cancel_requested": 0,
                "provider": provider, "requested_model": requested_model,
                "decisions": {},
            }

    def update_audit_progress(self, run_id: str, current: int,
                              total: int, phase: str) -> None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if run and run["status"] in {"running", "cancelling"}:
                run.update(progress_current=current, progress_total=total,
                           current_phase=phase)

    def complete_audit_run(self, run_id: str, report: AuditReport) -> None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            run.update(status="completed", completed_at=_now(),
                       report=report.to_dict(), error="",
                       progress_current=run["progress_total"])

    def fail_audit_run(self, run_id: str, error: str) -> None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if run:
                run.update(status="failed", completed_at=_now(),
                           error=error[:20_000])

    def request_audit_cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if not run or run["status"] != "running":
                return False
            run.update(status="cancelling", cancel_requested=1)
            return True

    def cancel_audit_run(self, run_id: str) -> None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if run and run["status"] in {"running", "cancelling"}:
                run.update(status="cancelled", completed_at=_now(),
                           error="Audit cancelled by the user.")

    def latest_audit(self, book_id: str) -> dict | None:
        runs = self.audits(book_id)
        return runs[-1] if runs else None

    def audits(self, book_id: str) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(run) for run in sorted(
                (item for item in self._audit_runs.values()
                 if item["book_id"] == book_id),
                key=lambda item: item["created_at"],
            )]

    def audit_run(self, run_id: str) -> dict | None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            return copy.deepcopy(run) if run else None

    def save_audit_decision(self, run_id: str, finding_id: str,
                            decision: str, category: str | None,
                            note: str) -> None:
        with self._lock:
            run = self._audit_runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            run["decisions"][finding_id] = {
                "finding_id": finding_id, "decision": decision,
                "category": category, "note": note, "updated_at": _now(),
            }

class GoldApplication:
    def __init__(self, root: Path,
                 audit_backend: StructuredLLMBackend | None = None,
                 audit_config: AuditConfig | None = None,
                 import_root: Path | None = None):
        self.root = root.resolve()
        self.store = SessionStore()
        self.open_books: dict[str, OpenBook] = {}
        self.audit_backend = audit_backend
        self.audit_provider = (
            "OpenAI-compatible" if audit_backend is not None else "")
        self.audit_model = ""
        self.audit_timeout_per_call: float | None = None
        if audit_backend is not None:
            config = getattr(audit_backend, "config", None)
            self.audit_model = str(getattr(config, "model", "") or "")
            configured_timeout = getattr(config, "timeout", None)
            if isinstance(configured_timeout, (int, float)):
                self.audit_timeout_per_call = float(configured_timeout)
            base_url = str(getattr(config, "base_url", "") or "")
            if "localhost" in base_url or "127.0.0.1" in base_url:
                self.audit_provider = "LM Studio"
        self.audit_config = audit_config or AuditConfig()
        self._audit_lock = threading.Lock()
        self._active_audits: dict[str, str] = {}
        self._audit_cancellations: dict[str, threading.Event] = {}
        self.import_root = import_root.resolve() if import_root else None
        self._imported_books: dict[str, tuple[Path, str]] = {}

    def audit_backend_status(self) -> dict:
        return {
            "configured": self.audit_backend is not None,
            "provider": self.audit_provider,
            "model": self.audit_model,
            "timeout_per_call": self.audit_timeout_per_call,
        }

    @staticmethod
    def _audit_connection_from_input(
            data: dict,
    ) -> tuple[str, str, str, str | None, str | None, float]:
        """Validate provider transport settings without requiring a model."""
        provider = str(data.get("provider") or "openai_compatible")
        if provider not in {"lm_studio", "openai_compatible"}:
            raise ValueError("unsupported LLM provider")
        base_url = str(data.get("base_url") or "").strip().rstrip("/")
        api_key = str(data.get("api_key") or "").strip() or None
        reasoning = str(data.get("reasoning_effort") or "").strip() or None
        if len(base_url) > 2_000 or (
                api_key is not None and len(api_key) > 4_000):
            raise ValueError("LLM configuration value is too long")
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("base_url must be an HTTP(S) endpoint")
        try:
            timeout = float(data.get("timeout", 900.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a number") from exc
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        label = (
            "LM Studio" if provider == "lm_studio" else
            "OpenAI-compatible")
        return provider, label, base_url, api_key, reasoning, timeout

    def _audit_backend_from_input(
            self, data: dict, *, max_tokens: int = 6000,
            cache: Path | None = None,
    ) -> tuple[OpenAICompatibleBackend, str, str | None]:
        """Build a model-specific backend without retaining its API key."""
        provider, label, base_url, api_key, reasoning, timeout = \
            self._audit_connection_from_input(data)
        model = str(data.get("model") or "").strip()
        if not model:
            raise ValueError("model cannot be empty")
        if len(model) > 300:
            raise ValueError("LLM configuration value is too long")
        config = OpenAICompatibleConfig(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            reasoning_effort=reasoning,
            max_tokens=max_tokens,
            discover_model=provider == "lm_studio",
            cache=cache,
        )
        return OpenAICompatibleBackend(config), label, api_key

    def configure_audit_backend(self, data: dict) -> dict:
        backend, label, _ = self._audit_backend_from_input(
            data, cache=None)
        self.audit_backend = backend
        self.audit_provider = label
        model = str(data.get("model") or "").strip()
        self.audit_model = model
        self.audit_timeout_per_call = backend.config.timeout
        return self.audit_backend_status()

    def discover_audit_models(self, data: dict) -> dict:
        """Test endpoint authentication and return any exposed models."""
        _, _, base_url, api_key, _, timeout = \
            self._audit_connection_from_input(data)
        return {"models": OpenAICompatibleBackend.discover_models(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )}

    def test_audit_backend(self, data: dict) -> dict:
        """Run one minimal structured completion without saving settings."""
        backend, label, _ = self._audit_backend_from_input(
            data, max_tokens=128, cache=None)
        response = backend.request_structured(
            {"task": "connection_test"},
            "Return exactly one JSON object with the boolean field ok set "
            "to true. Do not add any other field.",
            LLM_CONNECTION_TEST_SCHEMA,
            "segnatura-connection-test-1",
            retry_invalid=False,
        )
        if response.data != {"ok": True}:
            raise InvalidLLMResponseError(
                "the selected model did not return the required structured "
                "test response")
        return {"ok": True, "provider": label, "model": response.model}

    def resolve_epub(self, relative: str) -> tuple[Path, str]:
        imported = self._imported_books.get(relative)
        if imported is not None:
            path, display_name = imported
            if not path.is_file():
                raise FileNotFoundError(relative)
            return path, display_name
        candidate = (self.root / relative).resolve()
        try:
            canonical = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path outside the configured library") from exc
        if candidate.suffix.casefold() != ".epub" or not candidate.is_file():
            raise FileNotFoundError(relative)
        return candidate, canonical.as_posix()

    def catalog(self) -> list[dict]:
        books = []
        for path in sorted(self.root.rglob("*.epub"),
                           key=lambda p: str(p).casefold()):
            relative = path.relative_to(self.root).as_posix()
            books.append({
                "path": relative,
                "name": path.stem,
                "folder": path.parent.relative_to(self.root).as_posix(),
                "selected_from_disk": False,
            })
        for token, (path, display_name) in self._imported_books.items():
            if path.is_file():
                books.append({
                    "path": token,
                    "name": Path(display_name).stem,
                    "folder": "",
                    "selected_from_disk": True,
                })
        return books

    def register_import(self, path: Path, display_name: str) -> dict:
        """Expose one session-only EPUB selected through the browser."""
        if self.import_root is None:
            raise RuntimeError("session EPUB imports are not configured")
        resolved = path.resolve()
        try:
            resolved.relative_to(self.import_root)
        except ValueError as exc:
            raise ValueError("import path is outside the session directory") \
                from exc
        token = f"selected/{uuid.uuid4().hex}.epub"
        self._imported_books[token] = (resolved, display_name)
        return {
            "path": token,
            "name": Path(display_name).stem,
            "folder": "",
            "selected_from_disk": True,
        }

    def open(self, relative: str) -> OpenBook:
        path, canonical = self.resolve_epub(relative)
        sha = _sha256(path)
        book_id = sha[:20]
        cached = self.open_books.get(book_id)
        if cached and cached.path == path:
            return cached
        extraction = analizza_apparati(path)
        if extraction.errore:
            raise ValueError(extraction.errore)
        opened = OpenBook(
            book_id, sha, path, canonical, extraction.analisi.libro,
            extraction=extraction,
        )
        self.open_books[book_id] = opened
        self.store.remember_book(opened)
        return opened

    def get(self, book_id: str) -> OpenBook:
        if book_id not in self.open_books:
            raise KeyError(book_id)
        return self.open_books[book_id]

    def profile_destination(self, opened: OpenBook) -> Path | None:
        """Return the adjacent profile path for a non-temporary source EPUB."""
        if self.import_root is not None:
            try:
                opened.path.relative_to(self.import_root)
                return None
            except ValueError:
                pass
        return opened.path.with_name(f"{opened.path.stem}.segnatura.json")

    def estimate_book_audit(self, book_id: str) -> dict:
        """Return the exact call count without contacting the LLM backend."""
        if self.audit_backend is None:
            raise RuntimeError("LLM audit is not configured for this server")
        opened = self.get(book_id)
        extracted = ExtractedBook(
            opened.path, opened.extraction,
            opened.extraction.prepara_ingestione())
        return estimate_audit(
            extracted, config=self.audit_config).to_dict()

    def start_audit(self, book_id: str) -> dict:
        backend = self.audit_backend
        if backend is None:
            raise RuntimeError("LLM audit is not configured for this server")
        opened = self.get(book_id)
        extracted = ExtractedBook(
            opened.path, opened.extraction,
            opened.extraction.prepara_ingestione())
        total_calls = estimate_audit(
            extracted, config=self.audit_config).total_calls
        with self._audit_lock:
            existing = self._active_audits.get(book_id)
            if existing:
                return self.store.audit_run(existing) or {}
            run_id = uuid.uuid4().hex
            self._active_audits[book_id] = run_id
            self._audit_cancellations[run_id] = threading.Event()
            self.store.create_audit_run(
                run_id, opened, total_calls,
                self.audit_provider, self.audit_model)
        worker = threading.Thread(
            target=self._run_audit,
            args=(run_id, opened, extracted, backend),
            name=f"segnatura-audit-{run_id[:8]}", daemon=True,
        )
        worker.start()
        return self.store.audit_run(run_id) or {}

    def _run_audit(self, run_id: str, opened: OpenBook,
                   extracted: ExtractedBook,
                   backend: StructuredLLMBackend) -> None:
        cancellation = self._audit_cancellations[run_id]
        try:
            report = audit(
                extracted, backend=backend,
                config=self.audit_config,
                progress=lambda current, total, phase:
                self.store.update_audit_progress(
                    run_id, current, total, phase),
                cancelled=cancellation.is_set,
            )
            self.store.complete_audit_run(run_id, report)
        except AuditCancelledError:
            self.store.cancel_audit_run(run_id)
        except Exception as exc:  # Keep redacted worker failures in this session.
            backend_config = getattr(backend, "config", None)
            api_key = getattr(backend_config, "api_key", None)
            self.store.fail_audit_run(
                run_id, _safe_error_message(exc, api_key))
        finally:
            with self._audit_lock:
                self._active_audits.pop(opened.id, None)
                self._audit_cancellations.pop(run_id, None)

    def cancel_audit(self, run_id: str) -> dict:
        run = self.store.audit_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] not in {"running", "cancelling"}:
            raise PermissionError("audit is not running")
        with self._audit_lock:
            cancellation = self._audit_cancellations.get(run_id)
            if cancellation is None:
                raise PermissionError("audit worker is not active")
            cancellation.set()
            self.store.request_audit_cancel(run_id)
        return self.store.audit_run(run_id) or {}

    def save_audit_decision(self, run_id: str, finding_id: str,
                            decision: str, category: str | None,
                            note: str) -> dict:
        run = self.store.audit_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] != "completed" or not run["report"]:
            raise PermissionError("audit is not complete")
        finding = next((item for item in run["report"]["findings"]
                        if item["id"] == finding_id), None)
        if finding is None:
            raise KeyError(finding_id)
        if decision not in {"accepted", "edited", "rejected"}:
            raise ValueError("invalid audit decision")
        if len(note) > 5000:
            raise ValueError("note too long")
        selected = None
        if decision == "accepted":
            selected = finding.get("proposed_category")
        elif decision == "edited":
            selected = category
        if selected is not None:
            if (selected not in PUBLIC_CATEGORIES
                    or not finding.get(
                        "can_create_edition_profile_override")):
                raise ValueError(
                    "finding cannot create this Edition Profile override")
        self.store.save_audit_decision(
            run_id, finding_id, decision, selected, note)
        return self.store.audit_run(run_id) or {}

    def accept_all_audit_findings(self, run_id: str) -> dict:
        run = self.store.audit_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] != "completed" or not run["report"]:
            raise PermissionError("audit is not complete")
        for finding in run["report"]["findings"]:
            if finding.get("can_create_edition_profile_override"):
                self.store.save_audit_decision(
                    run_id, finding["id"], "accepted",
                    finding.get("proposed_category"), "")
        return self.store.audit_run(run_id) or {}

    def annotations_for_export(self, opened: OpenBook) -> dict:
        """Merge approved audit suggestions under explicit manual choices."""
        manual = self.store.annotations(opened.id)
        documents: dict[str, dict] = {}
        blocks: dict[str, dict] = {}
        ranges = dict(manual["ranges"])
        for run in self.store.audits(opened.id):
            if run["status"] != "completed" or not run["report"]:
                continue
            findings = {
                item["id"]: item for item in run["report"]["findings"]}
            for finding_id, decision in run["decisions"].items():
                if decision["decision"] not in {"accepted", "edited"}:
                    continue
                finding = findings.get(finding_id)
                category = decision.get("category")
                if (not finding or category not in PUBLIC_CATEGORIES
                        or not finding.get(
                            "can_create_edition_profile_override")):
                    continue
                record = {
                    "label": category,
                    "certainty": "certain",
                    "note": (decision.get("note")
                             or finding["explanation"]),
                    "updated_at": decision["updated_at"],
                }
                if finding["scope"] == "document":
                    record["href"] = finding["href"]
                    documents[finding["href"]] = record
                elif finding["scope"] == "block":
                    record.update({
                        "block_id": finding["block_id"],
                        "href": finding["href"],
                        "xpath": finding["xpath"],
                        "fingerprint": finding["fingerprint"],
                    })
                    blocks[finding["block_id"]] = record
        documents.update(manual["documents"])
        blocks.update(manual["blocks"])
        return {"documents": documents, "blocks": blocks, "ranges": ranges}


def _book_payload(opened: OpenBook, *, include_classification: bool = True) -> dict:
    classified = {}
    if include_classification and opened.extraction is not None:
        classified = {
            item.esito_base.blocco.id: item
            for item in opened.extraction.blocchi
        }
    documents = []
    for section in opened.book.sezioni:
        document_results = [classified.get(block.id) for block in section.blocchi]
        document_categories = {
            to_public(item.categoria) for item in document_results if item
        }
        documents.append({
            "href": section.href,
            "index": section.indice,
            "position": len(documents) + 1,
            "title": section.titolo or section.nome,
            "linear": section.linear,
            "characters": section.caratteri,
            "deterministic_category": (
                next(iter(document_categories))
                if len(document_categories) == 1 else None
            ),
            "blocks": [dict({
                "id": block.id,
                "index": block.indice,
                "position": index + 1,
                "shape": block.forma,
                "title": block.titolo,
                "characters": block.caratteri,
            }, **({
                "deterministic_category": to_public(classified[block.id].categoria),
                "deterministic_confidence": classified[block.id].confidenza,
                "classification_source": classified[block.id].fonte,
                "classification_rule": classified[block.id].esito_base.rule_id,
                "classification_evidence": list(classified[block.id].prove),
            } if block.id in classified else {}))
                       for index, block in enumerate(section.blocchi)],
        })
    return {
        "id": opened.id,
        "sha256": opened.sha256,
        "path": opened.relative_path,
        "title": opened.book.titolo or opened.path.stem,
        "language": opened.book.lingua,
        "publisher": opened.book.editore,
        "epub_version": opened.book.versione,
        "documents": documents,
    }


def _profile_annotation_input(data: dict) -> tuple[str, str, str]:
    """Validate a decisive Edition Profile annotation."""
    label = str(data.get("label") or "")
    note = str(data.get("note") or "").strip()
    if label not in PROFILE_LABELS:
        raise ValueError("invalid Edition Profile label")
    if "certainty" in data:
        raise ValueError("certainty is not supported by Edition Profiles")
    if len(note) > 5000:
        raise ValueError("note too long")
    return label, "certain", note


def _range_input(data: dict, text: str) -> tuple[int, int, str, str, str]:
    try:
        start = int(data.get("start"))
        end = int(data.get("end"))
    except (TypeError, ValueError) as exc:
        raise ValueError("range offsets must be integers") from exc
    label = str(data.get("label") or "")
    note = str(data.get("note") or "").strip()
    if start < 0 or end <= start or end > len(text):
        raise ValueError("invalid range offsets")
    if not text[start:end].strip():
        raise ValueError("selected range must contain text")
    if label not in PUBLIC_CATEGORIES:
        raise ValueError("invalid range category")
    if "certainty" in data:
        raise ValueError("certainty is not supported by Edition Profiles")
    if len(note) > 5000:
        raise ValueError("note too long")
    return start, end, label, "certain", note


def create_app(root: Path | str,
               audit_backend: StructuredLLMBackend | None = None,
               audit_config: AuditConfig | None = None):
    try:
        from flask import (Flask, Response, abort, jsonify, render_template,
                           request, send_file)
    except ImportError as exc:
        raise RuntimeError(
            "Flask is not installed. Run: python -m pip install "
            "\"segnatura[tools]\""
        ) from exc

    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"EPUB folder does not exist: {root}")
    import_directory = Path(tempfile.mkdtemp(
        prefix="segnatura-edition-profile-"))
    service = GoldApplication(
        root,
        audit_backend=audit_backend, audit_config=audit_config,
        import_root=import_directory,
    )
    web_root = Path(__file__).with_name("gold_web")
    app = Flask(__name__, template_folder=str(web_root / "templates"),
                static_folder=str(web_root / "static"),
                static_url_path="/static")
    app.config.update(
        JSON_AS_ASCII=False,
        MAX_CONTENT_LENGTH=MAX_EPUB_UPLOAD_BYTES + 1024 * 1024,
    )
    app.extensions["segnatura_gold"] = service
    app.extensions["segnatura_epub_imports"] = import_directory
    weakref.finalize(app, shutil.rmtree, import_directory, True)

    @app.before_request
    def require_local_browser_origin():
        host = request.headers.get("Host", "")
        if _loopback_authority(host) is None:
            return jsonify({"error": "invalid local Host header"}), 400
        origin = request.headers.get("Origin")
        if origin and not _origin_matches_host(origin, host, request.scheme):
            return jsonify({"error": "cross-origin request rejected"}), 403
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/books")
    def books():
        return jsonify({"books": service.catalog(), "root": str(service.root)})

    @app.post("/api/import")
    def import_epub():
        upload = request.files.get("epub")
        raw_name = str(getattr(upload, "filename", "") or "")
        display_name = PurePosixPath(raw_name.replace("\\", "/")).name
        if (upload is None or not display_name
                or Path(display_name).suffix.casefold() != ".epub"
                or len(display_name) > 255):
            return jsonify({"error": "select one valid .epub file"}), 400
        destination = service.import_root / f"{uuid.uuid4().hex}.epub"
        try:
            upload.save(destination)
            if (not destination.is_file() or destination.stat().st_size == 0
                    or destination.stat().st_size > MAX_EPUB_UPLOAD_BYTES):
                raise ValueError("the selected EPUB is empty or too large")
            with zipfile.ZipFile(destination) as archive:
                if archive.read("mimetype").strip() != b"application/epub+zip":
                    raise ValueError("the selected file is not a valid EPUB")
            item = service.register_import(destination, display_name)
        except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
            destination.unlink(missing_ok=True)
            return jsonify({"error": str(exc)}), 400
        return jsonify({"book": item}), 201

    @app.post("/api/open")
    def open_book():
        data = request.get_json(silent=True) or {}
        relative = str(data.get("path") or "")
        try:
            opened = service.open(relative)
        except FileNotFoundError:
            abort(404)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        payload = _book_payload(opened)
        payload["annotations"] = service.store.annotations(opened.id)
        payload["audit_available"] = service.audit_backend is not None
        payload["audit"] = service.store.latest_audit(opened.id)
        payload["audits"] = service.store.audits(opened.id)
        payload["llm"] = service.audit_backend_status()
        payload["audit_estimate"] = None
        return jsonify(payload)

    @app.get("/api/llm/config")
    def llm_config():
        return jsonify(service.audit_backend_status())

    @app.put("/api/llm/config")
    def configure_llm():
        data = request.get_json(silent=True) or {}
        try:
            result = service.configure_audit_backend(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.post("/api/llm/models")
    def discover_llm_models():
        data = request.get_json(silent=True) or {}
        api_key = str(data.get("api_key") or "")
        try:
            result = service.discover_audit_models(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except LLMError as exc:
            return jsonify({
                "error": _safe_error_message(exc, api_key),
            }), 502
        return jsonify(result)

    @app.post("/api/llm/test")
    def test_llm_configuration():
        data = request.get_json(silent=True) or {}
        api_key = str(data.get("api_key") or "")
        try:
            result = service.test_audit_backend(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except LLMError as exc:
            return jsonify({
                "error": _safe_error_message(exc, api_key),
            }), 502
        return jsonify(result)

    @app.get("/api/books/<book_id>/blocks/<block_id>")
    def block(book_id: str, block_id: str):
        try:
            opened = service.get(book_id)
            section, item = opened.blocks[block_id]
        except KeyError:
            abort(404)
        return jsonify({
            "id": item.id,
            "href": section.href,
            "xpath": item.xpath,
            "fingerprint": item.fingerprint,
            "text": item.testo,
            "shape": item.forma,
            "title": item.titolo,
            "characters": item.caratteri,
            "fragments": [fragment.xpath for fragment in item.frammenti_dom],
        })

    @app.put("/api/books/<book_id>/annotations/document")
    def annotate_document(book_id: str):
        try:
            opened = service.get(book_id)
        except KeyError:
            abort(404)
        data = request.get_json(silent=True) or {}
        href = str(data.get("href") or "")
        if href not in opened.documents:
            abort(404)
        try:
            label, certainty, note = _profile_annotation_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        service.store.save_document(book_id, href, label, certainty, note)
        return jsonify({"saved": True, "updated_at": _now()})

    @app.put("/api/books/<book_id>/annotations/block")
    def annotate_block(book_id: str):
        try:
            opened = service.get(book_id)
        except KeyError:
            abort(404)
        data = request.get_json(silent=True) or {}
        block_id = str(data.get("block_id") or "")
        try:
            _, item = opened.blocks[block_id]
        except KeyError:
            abort(404)
        try:
            label, certainty, note = _profile_annotation_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        service.store.save_block(book_id, item, label, certainty, note)
        return jsonify({"saved": True, "updated_at": _now()})

    @app.put("/api/books/<book_id>/annotations/range")
    def annotate_range(book_id: str):
        try:
            opened = service.get(book_id)
        except KeyError:
            abort(404)
        data = request.get_json(silent=True) or {}
        block_id = str(data.get("block_id") or "")
        try:
            _, item = opened.blocks[block_id]
        except KeyError:
            abort(404)
        try:
            start, end, label, certainty, note = _range_input(
                data, item.testo)
            saved = service.store.save_range(
                book_id, item, start, end, label, certainty, note)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"saved": True, "range": saved})

    @app.delete("/api/books/<book_id>/annotations/range/<range_id>")
    def delete_range(book_id: str, range_id: str):
        try:
            service.get(book_id)
        except KeyError:
            abort(404)
        if not service.store.delete_range(book_id, range_id):
            abort(404)
        return jsonify({"deleted": True})

    @app.get("/api/books/<book_id>/annotations")
    def annotations(book_id: str):
        try:
            service.get(book_id)
        except KeyError:
            abort(404)
        return jsonify(service.store.annotations(book_id))

    @app.post("/api/books/<book_id>/audit")
    def start_audit(book_id: str):
        try:
            result = service.start_audit(book_id)
        except KeyError:
            abort(404)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(result), 202

    @app.get("/api/books/<book_id>/audit-estimate")
    def estimate_book_audit(book_id: str):
        try:
            result = service.estimate_book_audit(book_id)
        except KeyError:
            abort(404)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(result)

    @app.get("/api/books/<book_id>/audit")
    def latest_audit(book_id: str):
        try:
            service.get(book_id)
        except KeyError:
            abort(404)
        result = service.store.latest_audit(book_id)
        return jsonify({"audit": result})

    @app.get("/api/books/<book_id>/audits")
    def audit_history(book_id: str):
        try:
            service.get(book_id)
        except KeyError:
            abort(404)
        return jsonify({"audits": service.store.audits(book_id)})

    @app.get("/api/audits/<run_id>")
    def audit_status(run_id: str):
        result = service.store.audit_run(run_id)
        if result is None:
            abort(404)
        return jsonify(result)

    @app.post("/api/audits/<run_id>/cancel")
    def cancel_audit(run_id: str):
        try:
            result = service.cancel_audit(run_id)
        except KeyError:
            abort(404)
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(result), 202

    @app.put("/api/audits/<run_id>/findings/<finding_id>")
    def decide_audit_finding(run_id: str, finding_id: str):
        data = request.get_json(silent=True) or {}
        try:
            result = service.save_audit_decision(
                run_id, finding_id,
                str(data.get("decision") or ""),
                (str(data.get("category")) if data.get("category") else None),
                str(data.get("note") or "").strip(),
            )
        except KeyError:
            abort(404)
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.post("/api/audits/<run_id>/accept-all")
    def accept_all_audit_findings(run_id: str):
        try:
            result = service.accept_all_audit_findings(run_id)
        except KeyError:
            abort(404)
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(result)

    @app.get("/api/books/<book_id>/export")
    def export(book_id: str):
        try:
            opened = service.get(book_id)
        except KeyError:
            abort(404)
        saved = service.annotations_for_export(opened)
        payload = create_edition_profile_payload(
            {
                "sha256": opened.sha256,
                "path": opened.relative_path,
                "title": opened.book.titolo or opened.path.stem,
                "language": opened.book.lingua,
            },
            saved["documents"].values(), saved["blocks"].values(),
            created_at=_now(), segnatura_version=_package_version(),
            range_annotations=saved["ranges"].values(),
        )
        if (not payload["documents"] and not payload["blocks"]
                and not payload["ranges"]):
            return jsonify({
                "code": "no_applicable_corrections",
                "error": "The Edition Profile has no applicable corrections. "
                         "Classify at least one document or block with a "
                         "concrete category."
            }), 409
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        filename = re.sub(r"[^a-zA-Z0-9._-]+", "-", opened.path.stem).strip("-")
        saved_next_to_epub = False
        destination = service.profile_destination(opened)
        if destination is not None:
            temporary = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_bytes(data)
                temporary.replace(destination)
                saved_next_to_epub = True
            except OSError:
                temporary.unlink(missing_ok=True)
        return Response(
            data,
            content_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{filename}.segnatura.json"',
                "X-Segnatura-Saved-Next-To-EPUB":
                    "1" if saved_next_to_epub else "0",
            },
        )

    @app.get("/epub/<book_id>/<path:member>")
    def epub_resource(book_id: str, member: str):
        safe = _safe_member(member)
        if safe is None:
            abort(404)
        try:
            opened = service.get(book_id)
        except KeyError:
            abort(404)
        try:
            with zipfile.ZipFile(opened.path) as archive:
                raw = archive.read(safe)
        except (KeyError, zipfile.BadZipFile):
            abort(404)
        suffix = PurePosixPath(safe).suffix.lower()
        nonce = hashlib.sha256(f"{book_id}\0{safe}".encode()).hexdigest()[:24]
        if suffix in HTML_SUFFIXES:
            block_id = request.args.get("block", "")
            fragments: list[dict] = []
            if block_id:
                found = opened.blocks.get(block_id)
                if found and found[0].href == safe:
                    item = found[1]
                    fragments = [{
                        "xpath": fragment.xpath,
                        "start": fragment.inizio_blocco,
                        "end": fragment.fine_blocco,
                    } for fragment in item.frammenti_dom]
                    if not fragments:
                        fragments = [{
                            "xpath": item.xpath,
                            "start": 0,
                            "end": len(item.testo),
                        }]
            raw = _inject_highlight(raw, fragments, nonce)
        content_type = ("text/html; charset=utf-8"
                        if suffix in HTML_SUFFIXES else _mime_type(safe))
        response = Response(raw, content_type=content_type)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' data: blob:; "
            f"script-src 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; "
            "object-src 'none'; frame-ancestors 'self'; base-uri 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


def run(root: Path | str, port: int = 8766, open_browser: bool = True,
        audit_backend: StructuredLLMBackend | None = None,
        audit_config: AuditConfig | None = None) -> None:
    if not (1024 <= port <= 65535):
        raise ValueError("port must be between 1024 and 65535")
    app = create_app(
        root,
        audit_backend=audit_backend, audit_config=audit_config,
    )
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Segnatura Edition Profile: {url}")
    print("Books and annotations stay on this computer.")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
