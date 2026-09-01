"""Deterministic operational categories used by extraction and Edition Profiles.

The editorial classifier retains its fine-grained internal roles. This module
maps those roles to the five operational categories exposed by the extraction
API. Optional LLM review deliberately lives in :mod:`segnatura.audit` and
never participates in this production path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ruoli as R
from .classifica import Analisi, analizza
from .classifica_blocchi import EsitoBlocco, classifica_blocchi
from .epub_safety import EpubSafetyLimits


TESTO = "testo"
NOTA = "nota"
BIBLIOGRAFIA = "bibliografia"
INDICE = "indice"
PARATESTO = "paratesto"
CATEGORIE = (TESTO, NOTA, BIBLIOGRAFIA, INDICE, PARATESTO)


def categoria_da_ruolo(ruolo: str) -> str:
    if ruolo in {R.CORPO, R.SOGLIA, R.APPENDICE}:
        return TESTO
    if ruolo == R.NOTA:
        return NOTA
    if ruolo == R.BIBLIOGRAFIA:
        return BIBLIOGRAFIA
    if ruolo in {R.INDICE_ANALITICO, R.SOMMARIO}:
        return INDICE
    if ruolo == R.PARATESTO:
        return PARATESTO
    return TESTO


def categoria_da_esito(esito: EsitoBlocco) -> str:
    """Return the operational category without discarding policy metadata."""
    if esito.include_as_main_text:
        return TESTO
    return categoria_da_ruolo(esito.ruolo)


def uso(categoria: str) -> str:
    if categoria == TESTO:
        return R.TESTO_PRINCIPALE
    if categoria == NOTA:
        return R.SU_RICHIESTA
    return R.ESCLUSO


@dataclass
class EsitoApparato:
    esito_base: EsitoBlocco
    categoria: str
    confidenza: float
    fonte: str
    prove: list[str] = field(default_factory=list)

    @property
    def uso(self) -> str:
        return uso(self.categoria)

    @property
    def include_as_main_text(self) -> bool:
        return self.categoria == TESTO


@dataclass
class StatisticheApparati:
    blocchi: int = 0
    fase: str = "completata"


@dataclass
class AnalisiApparati:
    analisi: Analisi
    blocchi: list[EsitoApparato]
    statistiche: StatisticheApparati
    range_overrides: dict[tuple[str, str], tuple[object, ...]] = field(
        default_factory=dict)

    @property
    def errore(self):
        return self.analisi.errore

    def prepara_ingestione(self):
        from .ingestione import prepara_ingestione
        return prepara_ingestione(self)

    def da_indicizzare(self, includi_note: bool = False):
        return self.prepara_ingestione().da_indicizzare(includi_note)


def classifica_apparati_deterministica(
        analisi: Analisi,
        base: list[EsitoBlocco] | None = None) -> AnalisiApparati:
    """Map the complete deterministic block classification to API categories."""
    risultati = list(base or classifica_blocchi(analisi))
    blocchi = [EsitoApparato(
        esito_base=esito,
        categoria=categoria_da_esito(esito),
        confidenza=esito.confidenza,
        fonte=esito.fonte,
        prove=list(esito.prove),
    ) for esito in risultati]
    return AnalisiApparati(
        analisi,
        blocchi,
        StatisticheApparati(blocchi=len(blocchi)),
    )


def analizza_apparati(
        percorso,
        override_documenti: dict[str, str] | None = None,
        override_blocchi: dict[str, str] | None = None,
        modello_blocchi=None,
        edition_profile=None,
        safety_limits: EpubSafetyLimits | None = None) -> AnalisiApparati:
    """Run deterministic extraction and apply an optional Edition Profile."""
    analisi = analizza(percorso, override_documenti, safety_limits)
    base = classifica_blocchi(
        analisi, modello=modello_blocchi, override=override_blocchi)
    risultato = classifica_apparati_deterministica(analisi, base)
    if edition_profile is not None:
        from .edition_profile import apply_edition_profile
        risultato = apply_edition_profile(
            risultato, percorso, edition_profile)
    return risultato


__all__ = [
    "TESTO", "NOTA", "BIBLIOGRAFIA", "INDICE", "PARATESTO", "CATEGORIE",
    "EsitoApparato", "StatisticheApparati", "AnalisiApparati",
    "categoria_da_ruolo", "categoria_da_esito", "uso",
    "classifica_apparati_deterministica", "analizza_apparati",
]
