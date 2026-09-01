"""Canonical operational categories shared by every public surface."""
from __future__ import annotations

WORK_TEXT = "work_text"
NOTE = "note"
BIBLIOGRAPHY = "bibliography"
INDEX = "index"
PARATEXT = "paratext"

PUBLIC_CATEGORIES = (WORK_TEXT, NOTE, BIBLIOGRAPHY, INDEX, PARATEXT)

INTERNAL_TO_PUBLIC = {
    "testo": WORK_TEXT,
    "nota": NOTE,
    "bibliografia": BIBLIOGRAPHY,
    "indice": INDEX,
    "paratesto": PARATEXT,
}
PUBLIC_TO_INTERNAL = {public: internal
                      for internal, public in INTERNAL_TO_PUBLIC.items()}


def to_public(category: str) -> str:
    try:
        return INTERNAL_TO_PUBLIC[category]
    except KeyError as exc:
        raise ValueError(f"unknown internal category: {category!r}") from exc


def to_internal(category: str) -> str:
    try:
        return PUBLIC_TO_INTERNAL[category]
    except KeyError as exc:
        raise ValueError(f"unknown public category: {category!r}") from exc


__all__ = [
    "WORK_TEXT", "NOTE", "BIBLIOGRAPHY", "INDEX", "PARATEXT",
    "PUBLIC_CATEGORIES", "INTERNAL_TO_PUBLIC", "PUBLIC_TO_INTERNAL",
    "to_public", "to_internal",
]
