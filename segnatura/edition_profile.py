"""Persistent, edition-specific classification corrections for Segnatura.

An Edition Profile changes only the operational category used by extraction. It does
not rewrite the deterministic classifier, train a model, or alter the fine
editorial role stored in ``EsitoBlocco``.  The exact EPUB SHA-256 and every
block fingerprint are checked before any correction is applied.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .categories import (BIBLIOGRAPHY, INDEX, NOTE, PARATEXT,
                         PUBLIC_CATEGORIES, WORK_TEXT, to_internal)

if TYPE_CHECKING:
    from .apparati import AnalisiApparati


SCHEMA_EDITION_PROFILE = "segnatura-edition-profile-1"
CATEGORY_POLICY_VERSION = 1

EDITION_PROFILE_CATEGORIES = PUBLIC_CATEGORIES
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EditionProfileError(ValueError):
    """Base error for an invalid or inapplicable Edition Profile."""


class EditionProfileSchemaError(EditionProfileError):
    """The JSON does not conform to the Edition Profile schema."""


class EditionProfileMismatchError(EditionProfileError):
    """The profile targets a different EPUB or a changed source block."""


@dataclass(frozen=True)
class BookIdentity:
    sha256: str
    path: str = ""
    title: str = ""
    language: str = ""


@dataclass(frozen=True)
class DocumentOverride:
    href: str
    category: str
    note: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class BlockOverride:
    block_id: str
    href: str
    xpath: str
    fingerprint: str
    category: str
    note: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class RangeOverride:
    range_id: str
    block_id: str
    href: str
    xpath: str
    block_fingerprint: str
    start: int
    end: int
    text_fingerprint: str
    category: str
    note: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class EditionProfile:
    book: BookIdentity
    documents: tuple[DocumentOverride, ...] = ()
    blocks: tuple[BlockOverride, ...] = ()
    ranges: tuple[RangeOverride, ...] = ()
    created_at: str = ""
    segnatura_version: str = ""
    ignored_annotations: tuple[dict[str, Any], ...] = ()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EditionProfileSchemaError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise EditionProfileSchemaError(f"{name} must be an array")
    return value


def _string(record: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = record.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        requirement = "a non-empty string" if required else "a string"
        raise EditionProfileSchemaError(f"{key} must be {requirement}")
    return value.strip() if required else value


def _category(record: dict[str, Any]) -> str:
    category = _string(record, "category")
    if category not in EDITION_PROFILE_CATEGORIES:
        raise EditionProfileSchemaError(
            f"unsupported Edition Profile category: {category}")
    return category


def _metadata(record: dict[str, Any]) -> tuple[str, str]:
    note = _string(record, "note", required=False)
    updated_at = _string(record, "updated_at", required=False)
    return note, updated_at


def _integer(record: dict[str, Any], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EditionProfileSchemaError(f"{key} must be an integer")
    return value


def _text_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def load_edition_profile(
        source: Path | str | dict[str, Any] | EditionProfile
) -> EditionProfile:
    """Load and validate an Edition Profile."""
    if isinstance(source, EditionProfile):
        return source
    if isinstance(source, dict):
        data = source
    else:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EditionProfileSchemaError(
                f"cannot read Edition Profile: {exc}") from exc
    data = _mapping(data, "Edition Profile")
    schema = data.get("schema")
    if schema != SCHEMA_EDITION_PROFILE:
        raise EditionProfileSchemaError(
            f"unsupported Edition Profile schema: {schema!r}")
    if data.get("category_policy_version") != CATEGORY_POLICY_VERSION:
        raise EditionProfileSchemaError("unsupported category policy version")

    raw_book = _mapping(data.get("book"), "book")
    sha256 = _string(raw_book, "sha256").casefold()
    if not _SHA256.fullmatch(sha256):
        raise EditionProfileSchemaError(
            "book.sha256 must contain 64 hexadecimal characters")
    book = BookIdentity(
        sha256=sha256,
        path=_string(raw_book, "path", required=False),
        title=_string(raw_book, "title", required=False),
        language=_string(raw_book, "language", required=False),
    )

    documents: list[DocumentOverride] = []
    document_keys: set[str] = set()
    for raw in _list(data.get("documents", []), "documents"):
        record = _mapping(raw, "document override")
        href = _string(record, "href")
        if href in document_keys:
            raise EditionProfileSchemaError(
                f"duplicate document override: {href}")
        document_keys.add(href)
        note, updated_at = _metadata(record)
        documents.append(DocumentOverride(
            href, _category(record), note, updated_at))

    blocks: list[BlockOverride] = []
    block_keys: set[tuple[str, str]] = set()
    for raw in _list(data.get("blocks", []), "blocks"):
        record = _mapping(raw, "block override")
        block_id = _string(record, "block_id")
        href = _string(record, "href")
        key = (href, block_id)
        if key in block_keys:
            raise EditionProfileSchemaError(
                f"duplicate block override: {href}#{block_id}")
        block_keys.add(key)
        note, updated_at = _metadata(record)
        blocks.append(BlockOverride(
            block_id=block_id,
            href=href,
            xpath=_string(record, "xpath"),
            fingerprint=_string(record, "fingerprint"),
            category=_category(record),
            note=note,
            updated_at=updated_at,
        ))

    ranges: list[RangeOverride] = []
    range_keys: set[str] = set()
    per_block_ranges: dict[tuple[str, str], list[tuple[int, int]]] = {}
    raw_ranges = _list(data.get("ranges", []), "ranges")
    for raw in raw_ranges:
        record = _mapping(raw, "range override")
        range_id = _string(record, "range_id")
        if range_id in range_keys:
            raise EditionProfileSchemaError(
                f"duplicate range override: {range_id}")
        range_keys.add(range_id)
        block_id = _string(record, "block_id")
        href = _string(record, "href")
        start = _integer(record, "start")
        end = _integer(record, "end")
        if start < 0 or end <= start:
            raise EditionProfileSchemaError(
                f"invalid range override bounds: {range_id}")
        key = (href, block_id)
        previous = per_block_ranges.setdefault(key, [])
        if any(start < other_end and end > other_start
               for other_start, other_end in previous):
            raise EditionProfileSchemaError(
                f"overlapping range overrides: {href}#{block_id}")
        previous.append((start, end))
        note, updated_at = _metadata(record)
        ranges.append(RangeOverride(
            range_id=range_id,
            block_id=block_id,
            href=href,
            xpath=_string(record, "xpath"),
            block_fingerprint=_string(record, "block_fingerprint"),
            start=start,
            end=end,
            text_fingerprint=_string(record, "text_fingerprint"),
            category=_category(record),
            note=note,
            updated_at=updated_at,
        ))

    ignored = _list(data.get("ignored_annotations", []),
                    "ignored_annotations")
    if any(not isinstance(item, dict) for item in ignored):
        raise EditionProfileSchemaError(
            "ignored_annotations entries must be objects")
    return EditionProfile(
        book=book,
        documents=tuple(documents),
        blocks=tuple(blocks),
        ranges=tuple(ranges),
        created_at=str(data.get("created_at") or ""),
        segnatura_version=str(data.get("segnatura_version") or ""),
        ignored_annotations=tuple(dict(item) for item in ignored),
    )


def create_edition_profile_payload(
        book: dict[str, Any], document_annotations: Iterable[dict[str, Any]],
        block_annotations: Iterable[dict[str, Any]], *, created_at: str,
        segnatura_version: str,
        range_annotations: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Convert local review annotations into the Edition Profile schema.

    ``mixed`` can guide range-level review but cannot itself define an
    operational extraction policy. It remains visible in
    ``ignored_annotations`` and is never applied silently.
    """
    documents: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    ranges: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []

    def metadata(record: dict[str, Any]) -> dict[str, str]:
        return {
            "note": str(record.get("note") or ""),
            "updated_at": str(record.get("updated_at") or ""),
        }

    for record in document_annotations:
        label = str(record.get("label") or "")
        if label not in EDITION_PROFILE_CATEGORIES:
            ignored.append({
                "scope": "document", "href": str(record.get("href") or ""),
                "label": label, "reason": "non_operational_label",
            })
            continue
        documents.append({
            "href": str(record.get("href") or ""),
            "category": label,
            **metadata(record),
        })
    for record in block_annotations:
        label = str(record.get("label") or "")
        if label not in EDITION_PROFILE_CATEGORIES:
            ignored.append({
                "scope": "block",
                "href": str(record.get("href") or ""),
                "block_id": str(record.get("block_id") or ""),
                "label": label, "reason": "non_operational_label",
            })
            continue
        blocks.append({
            "block_id": str(record.get("block_id") or ""),
            "href": str(record.get("href") or ""),
            "xpath": str(record.get("xpath") or ""),
            "fingerprint": str(record.get("fingerprint") or ""),
            "category": label,
            **metadata(record),
        })
    for record in range_annotations:
        label = str(record.get("label") or "")
        if label not in EDITION_PROFILE_CATEGORIES:
            ignored.append({
                "scope": "range",
                "range_id": str(record.get("range_id") or ""),
                "block_id": str(record.get("block_id") or ""),
                "label": label,
                "reason": "non_operational_label",
            })
            continue
        ranges.append({
            "range_id": str(record.get("range_id") or ""),
            "block_id": str(record.get("block_id") or ""),
            "href": str(record.get("href") or ""),
            "xpath": str(record.get("xpath") or ""),
            "block_fingerprint": str(
                record.get("block_fingerprint") or ""),
            "start": int(record.get("start", -1)),
            "end": int(record.get("end", -1)),
            "text_fingerprint": str(record.get("text_fingerprint") or ""),
            "category": label,
            **metadata(record),
        })
    documents.sort(key=lambda item: item["href"])
    blocks.sort(key=lambda item: (item["href"], item["xpath"],
                                  item["block_id"]))
    ranges.sort(key=lambda item: (item["href"], item["block_id"],
                                  item["start"], item["end"]))
    return {
        "schema": SCHEMA_EDITION_PROFILE,
        "created_at": created_at,
        "segnatura_version": segnatura_version,
        "category_policy_version": CATEGORY_POLICY_VERSION,
        "book": {
            "sha256": str(book.get("sha256") or ""),
            "path": str(book.get("path") or ""),
            "title": str(book.get("title") or ""),
            "language": str(book.get("language") or ""),
        },
        "documents": documents,
        "blocks": blocks,
        "ranges": ranges,
        "ignored_annotations": ignored,
    }


def apply_edition_profile(
        result: AnalisiApparati, epub: Path | str,
        edition_profile: Path | str | dict[str, Any] | EditionProfile) \
        -> AnalisiApparati:
    """Apply verified human-approved categories after classification."""
    from .apparati import AnalisiApparati

    profile = load_edition_profile(edition_profile)
    actual_sha256 = file_sha256(epub)
    if actual_sha256 != profile.book.sha256:
        raise EditionProfileMismatchError(
            "Edition Profile EPUB fingerprint mismatch: the profile targets "
            "a different "
            "file or edition")

    document_hrefs = {section.href for section in result.analisi.libro.sezioni}
    for override in profile.documents:
        if override.href not in document_hrefs:
            raise EditionProfileMismatchError(
                f"Edition Profile document not found: {override.href}")

    indexed_blocks = {
        (item.esito_base.documento.href, item.esito_base.blocco.id): item
        for item in result.blocchi
    }
    for override in profile.blocks:
        item = indexed_blocks.get((override.href, override.block_id))
        if item is None:
            raise EditionProfileMismatchError(
                f"Edition Profile block not found: "
                f"{override.href}#{override.block_id}")
        block = item.esito_base.blocco
        if block.xpath != override.xpath:
            raise EditionProfileMismatchError(
                f"Edition Profile XPath mismatch: "
                f"{override.href}#{override.block_id}")
        if block.fingerprint != override.fingerprint:
            raise EditionProfileMismatchError(
                f"Edition Profile block fingerprint mismatch: "
                f"{override.href}#{override.block_id}")

    ranges_by_block: dict[tuple[str, str], list[RangeOverride]] = {}
    for override in profile.ranges:
        item = indexed_blocks.get((override.href, override.block_id))
        if item is None:
            raise EditionProfileMismatchError(
                f"Edition Profile range block not found: "
                f"{override.href}#{override.block_id}")
        block = item.esito_base.blocco
        if block.xpath != override.xpath:
            raise EditionProfileMismatchError(
                f"Edition Profile range XPath mismatch: {override.range_id}")
        if block.fingerprint != override.block_fingerprint:
            raise EditionProfileMismatchError(
                f"Edition Profile range block fingerprint mismatch: "
                f"{override.range_id}")
        if override.end > len(block.testo):
            raise EditionProfileMismatchError(
                f"Edition Profile range is outside its block: "
                f"{override.range_id}")
        selected = block.testo[override.start:override.end]
        if _text_fingerprint(selected) != override.text_fingerprint:
            raise EditionProfileMismatchError(
                f"Edition Profile range text fingerprint mismatch: "
                f"{override.range_id}")
        ranges_by_block.setdefault(
            (override.href, override.block_id), []).append(override)

    document_overrides = {item.href: item for item in profile.documents}
    block_overrides = {
        (item.href, item.block_id): item for item in profile.blocks
    }
    corrected = []
    for item in result.blocchi:
        href = item.esito_base.documento.href
        key = (href, item.esito_base.blocco.id)
        override = block_overrides.get(key) or document_overrides.get(href)
        if override is None:
            corrected.append(item)
            continue
        internal_category = to_internal(override.category)
        corrected.append(replace(
            item,
            categoria=internal_category,
            confidenza=1.0,
            fonte="edition_profile",
            prove=list(item.prove) + [
                f"Edition Profile manual override: {override.category}"
            ],
        ))
    return AnalisiApparati(
        result.analisi, corrected, result.statistiche,
        range_overrides={
            key: tuple(sorted(values, key=lambda item: item.start))
            for key, values in ranges_by_block.items()
        },
    )


__all__ = [
    "SCHEMA_EDITION_PROFILE", "CATEGORY_POLICY_VERSION",
    "EDITION_PROFILE_CATEGORIES", "BookIdentity", "DocumentOverride",
    "BlockOverride", "RangeOverride", "EditionProfile",
    "EditionProfileError", "EditionProfileSchemaError",
    "EditionProfileMismatchError", "load_edition_profile",
    "create_edition_profile_payload", "apply_edition_profile",
]
