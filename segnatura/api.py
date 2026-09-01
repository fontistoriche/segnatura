"""Stable English API for EPUB extraction, citations, and RAG ingestion."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from .apparati import analizza_apparati
from .categories import PUBLIC_CATEGORIES, WORK_TEXT, to_internal, to_public
from .epub_safety import EpubSafetyLimits
from .ingestione import (ConfigurazioneChunking, IntervalloSorgente,
                         IntervalloToken, PacchettoIngestione,
                         TokenizzatoreSemplice)


SCHEMA_RAG_RECORD = "segnatura-rag-record-1"


def _selected_categories(categories: Iterable[str] | str) -> tuple[str, ...]:
    if categories == "all":
        selected = PUBLIC_CATEGORIES
    elif isinstance(categories, str):
        raise ValueError("categories must be an iterable of category names")
    else:
        selected = tuple(dict.fromkeys(categories))
    unknown = tuple(item for item in selected
                    if item not in PUBLIC_CATEGORIES)
    if unknown:
        raise ValueError(f"unknown categories: {', '.join(unknown)}")
    return tuple(to_internal(item) for item in selected)


class EpubExtractionError(RuntimeError):
    """Raised when an EPUB cannot be read or classified safely."""


@dataclass(frozen=True)
class TokenSpan:
    """Half-open character offsets for one tokenizer token."""

    start: int
    end: int


class Tokenizer(Protocol):
    """Offset-aware tokenizer contract used by :meth:`rag_records`.

    Spans refer to Python string character indexes, must be ordered and
    non-overlapping, and must omit special tokens that have no source text.
    """

    name: str
    exact: bool

    def spans(self, text: str) -> Sequence[TokenSpan]: ...


class _TokenizerAdapter:
    def __init__(self, tokenizer: Tokenizer):
        self._tokenizer = tokenizer
        self.nome = tokenizer.name
        self.esatto = tokenizer.exact

    def intervalli(self, testo: str) -> list[IntervalloToken]:
        return [IntervalloToken(item.start, item.end)
                for item in self._tokenizer.spans(testo)]


def _source(anchor: IntervalloSorgente) -> dict[str, Any]:
    return {
        "epub_sha256": anchor.inizio.epub_fingerprint,
        "href": anchor.inizio.href,
        "start": {
            "xpath": anchor.inizio.xpath,
            "offset": anchor.inizio.offset,
            "element_fingerprint": anchor.inizio.fingerprint_elemento,
        },
        "end": {
            "xpath": anchor.fine.xpath,
            "offset": anchor.fine.offset,
            "element_fingerprint": anchor.fine.fingerprint_elemento,
        },
        "text_fingerprint": anchor.fingerprint_testo,
        "quote": anchor.citazione,
    }


@dataclass(frozen=True)
class ExtractionUnit:
    id: str
    order: int
    title: str | None
    text: str
    category: str
    confidence: float
    classification_source: str
    evidence: tuple[str, ...]
    source: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionDocument:
    """One EPUB spine document exposed for inspection and custom auditing."""

    href: str
    order: int
    title: str | None
    title_source: str | None
    linear: bool
    visible_characters: int
    block_count: int
    category_counts: dict[str, int]
    visible_text_excerpt: str
    epub_types: tuple[str, ...] = ()
    aria_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["epub_types"] = list(self.epub_types)
        data["aria_roles"] = list(self.aria_roles)
        return data


@dataclass(frozen=True)
class ExtractionBlock:
    """One classified block, including excluded material and exact location."""

    id: str
    href: str
    order: int
    xpath: str
    fingerprint: str
    shape: str
    title: str | None
    text: str
    category: str
    confidence: float
    classification_source: str
    classification_rule: str = "fallback"
    evidence: tuple[str, ...] = ()
    epub_types: tuple[str, ...] = ()
    aria_roles: tuple[str, ...] = ()
    dom_markers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("evidence", "epub_types", "aria_roles", "dom_markers"):
            data[key] = list(data[key])
        return data


@dataclass(frozen=True)
class Creator:
    """One EPUB creator with preserved role and sorting metadata."""

    name: str
    roles: tuple[str, ...] = ()
    file_as: str | None = None
    opf_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "roles": list(self.roles),
            "file_as": self.file_as,
            "opf_id": self.opf_id,
        }


@dataclass(frozen=True)
class RAGRecord:
    """A vector-store-ready text record with exact EPUB provenance."""
    id: str
    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "metadata": self.metadata}


@dataclass(frozen=True)
class TextMatch:
    query: str
    text: str
    source: dict[str, Any]
    sequence_id: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExtractedBook:
    """Classified EPUB with stable, chunk-independent source coordinates."""

    def __init__(self, path: Path, analysis, package: PacchettoIngestione):
        self.path = path
        self._analysis = analysis
        self._package = package

    @property
    def title(self) -> str | None:
        return self._analysis.analisi.libro.titolo

    @property
    def language(self) -> str | None:
        return self._analysis.analisi.libro.lingua

    @property
    def publisher(self) -> str | None:
        return self._analysis.analisi.libro.editore

    @property
    def creators(self) -> tuple[Creator, ...]:
        return tuple(Creator(
            name=item.nome,
            roles=item.ruoli,
            file_as=item.ordinamento,
            opf_id=item.id_opf,
        ) for item in self._analysis.analisi.libro.creatori)

    @property
    def authors(self) -> tuple[str, ...]:
        candidates = (
            item.name for item in self.creators
            if not item.roles or {"aut", "author"} & set(item.roles)
        )
        return tuple(dict.fromkeys(candidates))

    @property
    def publication_date(self) -> str | None:
        return self._analysis.analisi.libro.data_pubblicazione

    @property
    def publication_date_raw(self) -> str | None:
        return self._analysis.analisi.libro.data_pubblicazione_originale

    @property
    def epub_sha256(self) -> str:
        return self._package.epub_fingerprint

    @property
    def coverage_is_valid(self) -> bool:
        return self._package.copertura.valida

    def book_metadata(self) -> dict[str, Any]:
        """Return serializable bibliographic identity and EPUB provenance."""
        return {
            "title": self.title,
            "creators": [item.to_dict() for item in self.creators],
            "authors": list(self.authors),
            "language": self.language,
            "publisher": self.publisher,
            "publication_date": self.publication_date,
            "publication_date_raw": self.publication_date_raw,
            "path": str(self.path),
            "epub_sha256": self.epub_sha256,
        }

    def documents(self, *, excerpt_characters: int = 900) \
            -> tuple[ExtractionDocument, ...]:
        """Return every spine document, including excluded material."""
        if excerpt_characters < 0:
            raise ValueError("excerpt_characters cannot be negative")
        by_href: dict[str, list] = {}
        for result in self._analysis.blocchi:
            by_href.setdefault(
                result.esito_base.documento.href, []).append(result)
        records = []
        for section in self._analysis.analisi.libro.sezioni:
            counts: dict[str, int] = {}
            for result in by_href.get(section.href, []):
                category = to_public(result.categoria)
                counts[category] = counts.get(category, 0) + 1
            text = " ".join(section.testo.split())
            if excerpt_characters and len(text) > excerpt_characters:
                first = excerpt_characters // 2
                last = excerpt_characters - first
                text = f"{text[:first]} [...] {text[-last:]}"
            elif excerpt_characters == 0:
                text = ""
            records.append(ExtractionDocument(
                href=section.href,
                order=section.indice,
                title=section.titolo,
                title_source=section.origine_titolo,
                linear=section.linear,
                visible_characters=section.caratteri,
                block_count=len(section.blocchi),
                category_counts=counts,
                visible_text_excerpt=text,
                epub_types=tuple(sorted(section.epub_type)),
                aria_roles=tuple(sorted(section.ruoli_aria)),
            ))
        return tuple(records)

    def blocks(self) -> tuple[ExtractionBlock, ...]:
        """Return the complete deterministic block inventory."""
        records = []
        for result in self._analysis.blocchi:
            block = result.esito_base.blocco
            records.append(ExtractionBlock(
                id=block.id,
                href=result.esito_base.documento.href,
                order=block.indice,
                xpath=block.xpath,
                fingerprint=block.fingerprint,
                shape=block.forma,
                title=block.titolo,
                text=block.testo,
                category=to_public(result.categoria),
                confidence=result.confidenza,
                classification_source=result.fonte,
                classification_rule=result.esito_base.rule_id,
                evidence=tuple(result.prove),
                epub_types=tuple(sorted(block.epub_type)),
                aria_roles=tuple(sorted(block.ruoli_aria)),
                dom_markers=tuple(block.marcatori_dom),
            ))
        return tuple(records)

    def units(
            self, *, categories: Iterable[str] | str = (WORK_TEXT,)) \
            -> tuple[ExtractionUnit, ...]:
        """Return units for selected categories, or every unit with ``all``."""
        internal = _selected_categories(categories)
        return tuple(ExtractionUnit(
            id=item.id,
            order=item.ordine,
            title=item.titolo,
            text=item.testo,
            category=to_public(item.categoria),
            confidence=item.confidenza,
            classification_source=item.fonte,
            evidence=item.prove,
            source=_source(item.ancora),
        ) for item in self._package.units_for_categories(internal))

    def text(self, *, categories: Iterable[str] | str = (WORK_TEXT,),
             separator: str = "\n\n") -> str:
        return separator.join(item.text for item in self.units(
            categories=categories))

    def find_text(self, query: str, *,
                  categories: Iterable[str] | str = (WORK_TEXT,),
                  case_sensitive: bool = False) -> tuple[TextMatch, ...]:
        """Find literal occurrences in the selected operational categories.

        This is the deterministic companion to semantic retrieval. Use it for
        exhaustive names or phrases within the selected categories; embeddings
        alone cannot guarantee recall. Pass ``categories="all"`` to search the
        complete classified EPUB inventory.
        """
        if not query:
            raise ValueError("query must not be empty")
        internal = _selected_categories(categories)
        needle = query if case_sensitive else query.casefold()
        matches: list[TextMatch] = []
        for sequence in self._package.sequences_for_categories(internal):
            haystack = sequence.testo if case_sensitive else sequence.testo.casefold()
            start = 0
            while True:
                index = haystack.find(needle, start)
                if index < 0:
                    break
                end = index + len(query)
                passage = self._package.passaggio(sequence.id, index, end)
                matches.append(TextMatch(
                    query=query, text=passage.testo,
                    source=_source(passage.ancora),
                    sequence_id=sequence.id, start=index, end=end,
                ))
                start = max(end, index + 1)
        return tuple(matches)

    def rag_records(
            self, *, categories: Iterable[str] | str = (WORK_TEXT,),
            max_tokens: int = 350, min_tokens: int = 80,
            overlap_tokens: int = 40, context_tokens: int = 1200,
            tokenizer: Tokenizer | None = None) -> tuple[RAGRecord, ...]:
        """Create small-to-big retrieval records without crossing hard roles."""
        if tokenizer is None:
            internal_tokenizer = TokenizzatoreSemplice()
        else:
            internal_tokenizer = _TokenizerAdapter(tokenizer)
        internal = _selected_categories(categories)
        config = ConfigurazioneChunking(
            massimo_token_piccolo=max_tokens,
            minimo_token_piccolo=min_tokens,
            overlap_token=overlap_tokens,
            budget_contesto=context_tokens,
            categories=internal,
        )
        plan = self._package.crea_chunk(
            config, tokenizzatore=internal_tokenizer)
        unit_by_id = {unit.id: unit for unit in self._package.unita}
        records = []
        for chunk in plan.chunk:
            titles = list(dict.fromkeys(
                unit_by_id[item].titolo for item in chunk.unita_ids
                if item in unit_by_id and unit_by_id[item].titolo))
            metadata = {
                "schema": SCHEMA_RAG_RECORD,
                "book": self.book_metadata(),
                "source": _source(chunk.ancora),
                "document_title": titles[0] if titles else None,
                "category": to_public(chunk.categoria),
                "confidence": chunk.confidenza,
                "classification_sources": list(chunk.fonti),
                "evidence": list(chunk.prove),
                "sequence_id": chunk.sequenza_id,
                "unit_ids": list(chunk.unita_ids),
                "previous_id": chunk.precedente_id,
                "next_id": chunk.successivo_id,
                "token_count": chunk.token,
                "tokenizer": plan.statistiche.tokenizer,
                "exact_token_count": plan.statistiche.token_esatti,
            }
            records.append(RAGRecord(chunk.id, chunk.testo, metadata))
        return tuple(records)

    def verify_source(self, source: dict[str, Any]) -> bool:
        """Verify that a serialized source reference still resolves."""
        try:
            start, end = source["start"], source["end"]
            from .ingestione import PuntoSorgente
            anchor = IntervalloSorgente(
                PuntoSorgente(source["epub_sha256"], source["href"],
                              start["xpath"], start["offset"],
                              start["element_fingerprint"]),
                PuntoSorgente(source["epub_sha256"], source["href"],
                              end["xpath"], end["offset"],
                              end["element_fingerprint"]),
                source["text_fingerprint"], source.get("quote", ""),
            )
            return self._package.verifica_ancora(anchor)
        except (KeyError, TypeError, ValueError):
            return False


def extract(path: Path | str, *,
            edition_profile: Path | str | dict | None = None,
            safety_limits: EpubSafetyLimits | None = None) \
        -> ExtractedBook:
    """Extract an EPUB with deterministic classification by default.

    An Edition Profile, when supplied, is applied only to the exact matching
    EPUB.
    Extraction is always deterministic. Optional LLMs belong to the separate
    :func:`segnatura.audit` review workflow and never mutate this result.
    """
    epub = Path(path).expanduser().resolve()
    if not epub.is_file():
        raise FileNotFoundError(epub)
    analysis = analizza_apparati(
        epub, edition_profile=edition_profile, safety_limits=safety_limits)
    if analysis.errore:
        raise EpubExtractionError(str(analysis.errore))
    package = analysis.prepara_ingestione()
    if not package.copertura.valida:
        details = "; ".join(package.copertura.errori
                            + package.copertura.anomalie_documenti)
        raise EpubExtractionError(
            "EPUB coverage validation failed" + (f": {details}" if details else ""))
    return ExtractedBook(epub, analysis, package)
