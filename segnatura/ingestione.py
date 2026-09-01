"""Uscita produttiva: testo ordinato, copertura, chunk e citazioni stabili.

La classificazione lavora su blocchi abbastanza grandi da riconoscerne il
ruolo. L'indicizzazione ha esigenze diverse: finestre piccole per il recupero,
contesto piu' grande per la risposta e riferimenti che non cambino insieme al
budget dei token. Questo modulo e' il ponte fra i due livelli.

Gli identificatori dei chunk NON sono citazioni. Una citazione e' sempre un
``IntervalloSorgente`` riferito all'EPUB, all'XHTML e agli elementi DOM; il
chunk puo' quindi essere ricostruito con un budget diverso senza perdere il
punto del libro a cui rimanda.
"""
from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Iterable, Protocol

from . import ruoli as R
from .apparati import AnalisiApparati, NOTA, TESTO, uso as uso_categoria
from .blocchi import Blocco, FrammentoDOM
from .categories import to_internal


SCHEMA_INGESTIONE = "segnatura-ingestione-2"
SCHEMA_CHUNK = "segnatura-chunk-small-to-big-2"


def _fingerprint(testo: str, lunghezza: int = 24) -> str:
    normalizzato = re.sub(r"\s+", " ", testo).strip().casefold()
    return hashlib.sha256(normalizzato.encode("utf-8")).hexdigest()[:lunghezza]


def _id(*parti: object, lunghezza: int = 24) -> str:
    materiale = "\0".join(str(x) for x in parti)
    return hashlib.sha256(materiale.encode("utf-8")).hexdigest()[:lunghezza]


def _impronta_file(percorso: Path | str, ripiego: str | None = None) -> str:
    file = Path(percorso)
    if file.is_file():
        h = hashlib.sha256()
        with file.open("rb") as stream:
            for pezzo in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(pezzo)
        return h.hexdigest()
    return hashlib.sha256(
        (ripiego or str(percorso)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class PuntoSorgente:
    """Posizione in un elemento DOM normalizzato.

    ``offset`` e' espresso in caratteri nel testo normalizzato dell'elemento,
    non nel file XML grezzo. Il fingerprint impedisce di applicare in silenzio
    l'offset a un EPUB differente.
    """
    epub_fingerprint: str
    href: str
    xpath: str
    offset: int
    fingerprint_elemento: str
    contesto: str = ""


@dataclass(frozen=True)
class IntervalloSorgente:
    inizio: PuntoSorgente
    fine: PuntoSorgente
    fingerprint_testo: str
    citazione: str

    def __post_init__(self):
        if self.inizio.epub_fingerprint != self.fine.epub_fingerprint:
            raise ValueError("un intervallo non puo' attraversare due EPUB")
        if self.inizio.href != self.fine.href:
            raise ValueError("un intervallo non puo' attraversare due XHTML")


@dataclass(frozen=True)
class MappaFrammento:
    xpath: str
    inizio_unita: int
    fine_unita: int
    fingerprint: str
    # Character offset at which this mapped slice begins in the original
    # normalized DOM element. It is zero for ordinary, unsplit units.
    source_start: int = 0


@dataclass(frozen=True)
class UnitaSorgente:
    """Decisione classificata con testo e provenienza, prima del chunking."""
    id: str
    ordine: int
    blocco_id: str
    href: str
    titolo: str | None
    testo: str
    categoria: str
    uso: str
    confidenza: float
    fonte: str
    prove: tuple[str, ...]
    ancora: IntervalloSorgente
    frammenti: tuple[MappaFrammento, ...]

    @property
    def include_as_main_text(self) -> bool:
        return self.uso == R.TESTO_PRINCIPALE

    @property
    def caratteri(self) -> int:
        return len(self.testo)


@dataclass(frozen=True)
class EsclusioneCopertura:
    unita_id: str
    href: str
    categoria: str
    caratteri: int
    fonte: str
    prove: tuple[str, ...]


@dataclass(frozen=True)
class CoperturaDocumento:
    href: str
    caratteri_xhtml: int
    caratteri_classificati: int
    caratteri_testo_principale: int
    caratteri_note: int
    caratteri_esclusi: int
    scarto_normalizzazione: int
    caratteri_ignorati_non_visibili: int
    anomalia: str | None
    percentuale_testo_principale: float
    per_categoria: dict[str, int]


@dataclass(frozen=True)
class RapportoCopertura:
    caratteri_xhtml: int
    caratteri_classificati: int
    caratteri_testo_principale: int
    caratteri_note: int
    caratteri_esclusi: int
    caratteri_ignorati_non_visibili: int
    percentuale_testo_principale: float
    percentuale_con_note: float
    documenti: tuple[CoperturaDocumento, ...]
    esclusioni: tuple[EsclusioneCopertura, ...]
    per_categoria: dict[str, int]
    per_motivo_esclusione: dict[str, int]
    anomalie_documenti: tuple[str, ...] = ()
    unita_duplicate: tuple[str, ...] = ()
    errori: tuple[str, ...] = ()

    @property
    def caratteri_contabilizzati(self) -> int:
        return (self.caratteri_testo_principale + self.caratteri_note
                + self.caratteri_esclusi)

    @property
    def valida(self) -> bool:
        return (not self.errori and not self.anomalie_documenti
                and not self.unita_duplicate
                and self.caratteri_contabilizzati
                == self.caratteri_classificati)


@dataclass(frozen=True)
class IntervalloToken:
    inizio: int
    fine: int


class Tokenizzatore(Protocol):
    """Adattatore del tokenizer scelto dall'applicazione chiamante.

    Gli intervalli devono riferirsi agli indici dei caratteri della stringa
    Python ricevuta, essere ordinati, non sovrapposti e non contenere i token
    speciali privi di testo. In pratica un tokenizer Hugging Face ``fast`` va
    invocato con ``return_offsets_mapping=True`` e
    ``add_special_tokens=False``.
    """
    nome: str
    esatto: bool

    def intervalli(self, testo: str) -> list[IntervalloToken]: ...


class TokenizzatoreSemplice:
    """Tokenizzatore Unicode deterministico, in attesa di quello dell'embedding.

    E' intenzionalmente dichiarato ``esatto=False``: i budget sono corretti
    strutturalmente ma diventeranno esatti per il modello soltanto collegando
    il suo tokenizer tramite il protocollo sopra.
    """
    nome = "semplice-unicode-v1"
    esatto = False
    _RE = re.compile(r"\w+(?:['’]\w+)*|[^\w\s]", re.UNICODE)

    def intervalli(self, testo: str) -> list[IntervalloToken]:
        return [IntervalloToken(m.start(), m.end())
                for m in self._RE.finditer(testo)]


@dataclass(frozen=True)
class ConfigurazioneChunking:
    """Politica scelta dall'utilizzatore, mai dedotta da Segnatura."""
    massimo_token_piccolo: int
    minimo_token_piccolo: int
    overlap_token: int
    budget_contesto: int
    includi_note: bool = False
    categories: tuple[str, ...] | None = None

    def __post_init__(self):
        if self.massimo_token_piccolo <= 0:
            raise ValueError("massimo_token_piccolo deve essere positivo")
        if not 0 <= self.minimo_token_piccolo <= self.massimo_token_piccolo:
            raise ValueError("minimo_token_piccolo fuori intervallo")
        if not 0 <= self.overlap_token < self.massimo_token_piccolo:
            raise ValueError("overlap_token deve essere minore del chunk")
        if self.budget_contesto < self.massimo_token_piccolo:
            raise ValueError("il contesto big non puo' essere minore del child")


@dataclass(frozen=True)
class ParteSequenza:
    unita_id: str
    inizio: int
    fine: int


@dataclass(frozen=True)
class SequenzaIndicizzabile:
    """Regione massima entro cui un chunker esterno puo' scegliere i tagli.

    Due sequenze diverse non devono mai essere unite: fra loro cambia almeno
    uno fra XHTML, ruolo operativo, inclusione o continuita' di lettura. Dentro
    la sequenza, invece, il chiamante decide liberamente budget e tokenizer.
    ``confini_frammento`` e ``inizi_frammento`` sono punti DOM preferibili,
    non tagli obbligatori.
    """
    id: str
    href: str
    categoria: str
    uso: str
    testo: str
    unita_ids: tuple[str, ...]
    parti: tuple[ParteSequenza, ...]
    confini_frammento: tuple[int, ...]
    inizi_frammento: tuple[int, ...]

    @property
    def confini_unita(self) -> tuple[int, ...]:
        """Fini delle unita' sorgente interne, utili come tagli preferiti."""
        return tuple(x.fine for x in self.parti[:-1])

    @property
    def caratteri(self) -> int:
        return len(self.testo)


@dataclass(frozen=True)
class PassaggioIndicizzabile:
    """Intervallo model-agnostic scelto dal chiamante e ancorato alla fonte."""
    id: str
    sequenza_id: str
    testo: str
    categoria: str
    uso: str
    confidenza: float
    fonti: tuple[str, ...]
    prove: tuple[str, ...]
    unita_ids: tuple[str, ...]
    inizio_sequenza: int
    fine_sequenza: int
    ancora: IntervalloSorgente


@dataclass(frozen=True)
class ChunkIndicizzabile:
    id: str
    ordine: int
    sequenza_id: str
    testo: str
    token: int
    categoria: str
    uso: str
    confidenza: float
    fonti: tuple[str, ...]
    prove: tuple[str, ...]
    unita_ids: tuple[str, ...]
    inizio_sequenza: int
    fine_sequenza: int
    ancora: IntervalloSorgente
    precedente_id: str | None = None
    successivo_id: str | None = None


@dataclass(frozen=True)
class ContestoEspanso:
    chunk_origine_id: str
    sequenza_id: str
    testo: str
    token: int
    categoria: str
    uso: str
    confidenza: float
    fonti: tuple[str, ...]
    prove: tuple[str, ...]
    unita_ids: tuple[str, ...]
    inizio_sequenza: int
    fine_sequenza: int
    ancora: IntervalloSorgente


@dataclass(frozen=True)
class StatisticheChunking:
    unita_indicizzate: int
    sequenze: int
    chunk: int
    caratteri_sorgente_unici: int
    caratteri_emessi_con_overlap: int
    caratteri_sorgente_coperti: int
    buchi_caratteri: int
    token_emessi: int
    attraversamenti_ruolo: int
    tokenizer: str
    token_esatti: bool

    @property
    def valida(self) -> bool:
        return self.buchi_caratteri == 0 and self.attraversamenti_ruolo == 0


@dataclass
class PianoChunking:
    epub_fingerprint: str
    configurazione: ConfigurazioneChunking
    chunk: tuple[ChunkIndicizzabile, ...]
    sequenze: tuple[SequenzaIndicizzabile, ...]
    unita: tuple[UnitaSorgente, ...]
    statistiche: StatisticheChunking
    _tokenizzatore: Tokenizzatore = field(repr=False, compare=False)

    def per_id(self, chunk_id: str) -> ChunkIndicizzabile:
        for voce in self.chunk:
            if voce.id == chunk_id:
                return voce
        raise KeyError(chunk_id)

    def espandi(self, chunk_id: str,
                budget_token: int | None = None) -> ContestoEspanso:
        """Espande un child nella stessa sequenza senza attraversare ruoli."""
        child = self.per_id(chunk_id)
        sequenza = next(x for x in self.sequenze
                        if x.id == child.sequenza_id)
        budget = budget_token or self.configurazione.budget_contesto
        if budget < child.token:
            raise ValueError("il budget big e' minore del chunk di origine")
        token = _intervalli_token(self._tokenizzatore, sequenza.testo)
        if not token:
            raise ValueError("sequenza senza token")
        sinistra = next((i for i, t in enumerate(token)
                         if t.fine > child.inizio_sequenza), 0)
        destra = bisect_left(
            [t.inizio for t in token], child.fine_sequenza)
        destra = max(sinistra + 1, destra)
        presenti = destra - sinistra
        extra = max(0, budget - presenti)
        prima = min(sinistra, extra // 2)
        dopo = min(len(token) - destra, extra - prima)
        residuo = extra - prima - dopo
        if residuo:
            aggiunta = min(sinistra - prima, residuo)
            prima += aggiunta
            residuo -= aggiunta
        if residuo:
            dopo += min(len(token) - destra - dopo, residuo)
        inizio = token[sinistra - prima].inizio
        fine = token[destra + dopo - 1].fine
        inizio, fine = _rifila(sequenza.testo, inizio, fine)
        testo = sequenza.testo[inizio:fine]
        unita_ids = _unita_intersecate(sequenza, inizio, fine)
        unita = {x.id: x for x in self.unita}
        confidenza, fonti, prove = _audit_unita(unita, unita_ids)
        ancora = _ancora_sequenza(
            self.epub_fingerprint, sequenza, unita, inizio, fine, testo)
        return ContestoEspanso(
            child.id, sequenza.id, testo,
            len(_intervalli_token(self._tokenizzatore, testo)),
            sequenza.categoria, sequenza.uso, confidenza, fonti, prove,
            unita_ids,
            inizio, fine, ancora,
        )

    def to_dict(self, includi_testo: bool = True) -> dict:
        statistiche = asdict(self.statistiche)
        statistiche["valida"] = self.statistiche.valida
        dati = {
            "schema": SCHEMA_CHUNK,
            "epub_fingerprint": self.epub_fingerprint,
            "configurazione": asdict(self.configurazione),
            "statistiche": statistiche,
            "chunk": [asdict(x) for x in self.chunk],
        }
        if not includi_testo:
            for voce in dati["chunk"]:
                voce.pop("testo", None)
        return dati

    def salva(self, percorso: Path | str,
              includi_testo: bool = True) -> Path:
        destinazione = Path(percorso)
        destinazione.write_text(
            json.dumps(self.to_dict(includi_testo), ensure_ascii=False,
                       indent=2),
            encoding="utf-8",
        )
        return destinazione


@dataclass
class PacchettoIngestione:
    epub_fingerprint: str
    libro: str | None
    unita: tuple[UnitaSorgente, ...]
    copertura: RapportoCopertura
    _sequenze_cache: dict[frozenset[str], tuple[SequenzaIndicizzabile, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False)
    _sequenze_per_id: dict[str, SequenzaIndicizzabile] = field(
        default_factory=dict, init=False, repr=False, compare=False)
    _unita_per_id: dict[str, UnitaSorgente] = field(
        default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._unita_per_id = {item.id: item for item in self.unita}

    def da_indicizzare(self, includi_note: bool = False) \
            -> list[UnitaSorgente]:
        categorie = {TESTO, NOTA} if includi_note else {TESTO}
        return self.units_for_categories(categorie)

    def units_for_categories(
            self, categories: Iterable[str]) -> list[UnitaSorgente]:
        """Return source units whose operational category was requested."""
        selected = frozenset(categories)
        return [item for item in self.unita if item.categoria in selected]

    def sequences_for_categories(
            self, categories: Iterable[str]) \
            -> tuple[SequenzaIndicizzabile, ...]:
        """Build ordered hard-boundary sequences for selected categories."""
        key = frozenset(categories)
        cached = self._sequenze_cache.get(key)
        if cached is None:
            cached = _sequenze(self.units_for_categories(key))
            self._sequenze_cache[key] = cached
            self._sequenze_per_id.update({item.id: item for item in cached})
        return cached

    def sequenze_indicizzabili(
            self, includi_note: bool = False) \
            -> tuple[SequenzaIndicizzabile, ...]:
        """Restituisce regioni ordinate che un chunker non deve mai unire.

        Questa e' l'uscita model-agnostic principale per chi costruisce un
        indice: Segnatura decide ruolo, ordine, provenienza e confini duri;
        l'applicazione decide i tagli interni con il proprio tokenizer.
        """
        categorie = {TESTO, NOTA} if includi_note else {TESTO}
        return self.sequences_for_categories(categorie)

    def passaggio(self, sequenza_id: str, inizio: int,
                  fine: int) -> PassaggioIndicizzabile:
        """Converte un taglio esterno in testo classificato con ancora EPUB."""
        if not self._sequenze_per_id:
            self.sequences_for_categories(
                {item.categoria for item in self.unita})
        sequenza = self._sequenze_per_id.get(sequenza_id)
        if sequenza is None:
            raise KeyError(sequenza_id)
        return _passaggio_sequenza(self, sequenza, inizio, fine)

    def ancora_per_intervallo(self, sequenza_id: str, inizio: int,
                              fine: int) -> IntervalloSorgente:
        """Forma breve di :meth:`passaggio` per chi conserva solo l'ancora."""
        return self.passaggio(sequenza_id, inizio, fine).ancora

    def crea_chunk(
            self, configurazione: ConfigurazioneChunking, *,
            tokenizzatore: Tokenizzatore) -> PianoChunking:
        """Funzione opzionale: politica e tokenizer appartengono al chiamante."""
        return crea_chunk(
            self, configurazione, tokenizzatore=tokenizzatore)

    def risolvi_ancora(self, ancora: IntervalloSorgente,
                       verifica_fingerprint: bool = True) -> str:
        """Rilegge un intervallo senza dipendere dall'esistenza del chunk.

        Una citazione salvata ieri continua quindi a funzionare dopo un nuovo
        chunking. Se l'EPUB e' cambiato, impronta e fingerprint fanno fallire
        esplicitamente la risoluzione invece di puntare al testo sbagliato.
        """
        if ancora.inizio.epub_fingerprint != self.epub_fingerprint:
            raise ValueError("la citazione appartiene a un altro EPUB")
        frammenti = []
        for unita in self.unita:
            if unita.href != ancora.inizio.href:
                continue
            for frammento in unita.frammenti:
                frammenti.append((
                    unita,
                    frammento,
                    unita.testo[frammento.inizio_unita:
                                frammento.fine_unita],
                ))
        indice_inizio = next((
            i for i, (_, f, text) in enumerate(frammenti)
            if f.xpath == ancora.inizio.xpath
            and f.fingerprint == ancora.inizio.fingerprint_elemento
            and f.source_start <= ancora.inizio.offset
            < f.source_start + len(text)
        ), None)
        indice_fine = next((
            i for i, (_, f, text) in enumerate(frammenti)
            if i >= (indice_inizio or 0)
            and f.xpath == ancora.fine.xpath
            and f.fingerprint == ancora.fine.fingerprint_elemento
            and f.source_start < ancora.fine.offset
            <= f.source_start + len(text)
        ), None)
        if indice_inizio is None or indice_fine is None:
            raise ValueError("elementi DOM della citazione non trovati")
        parti = []
        for i in range(indice_inizio, indice_fine + 1):
            testo = frammenti[i][2]
            if i == indice_inizio:
                testo = testo[
                    ancora.inizio.offset - frammenti[i][1].source_start:]
            if i == indice_fine:
                limite = (ancora.fine.offset
                          - frammenti[i][1].source_start)
                if i == indice_inizio:
                    limite -= (ancora.inizio.offset
                               - frammenti[i][1].source_start)
                testo = testo[:limite]
            parti.append(testo)
        risolto = " ".join(x for x in parti if x)
        if (verifica_fingerprint
                and _fingerprint(risolto) != ancora.fingerprint_testo):
            raise ValueError("il testo della citazione non coincide piu'")
        return risolto

    def verifica_ancora(self, ancora: IntervalloSorgente) -> bool:
        try:
            self.risolvi_ancora(ancora)
            return True
        except ValueError:
            return False

    def to_dict(self, includi_testo: bool = True) -> dict:
        copertura = asdict(self.copertura)
        copertura["caratteri_contabilizzati"] = (
            self.copertura.caratteri_contabilizzati)
        copertura["valida"] = self.copertura.valida
        dati = {
            "schema": SCHEMA_INGESTIONE,
            "epub_fingerprint": self.epub_fingerprint,
            "libro": self.libro,
            "copertura": copertura,
            "unita": [asdict(x) for x in self.unita],
            "sequenze": [
                {
                    "id": x.id,
                    "href": x.href,
                    "categoria": x.categoria,
                    "uso": x.uso,
                    "unita_ids": list(x.unita_ids),
                    "parti": [asdict(p) for p in x.parti],
                    "confini_frammento": list(x.confini_frammento),
                    "inizi_frammento": list(x.inizi_frammento),
                    "caratteri": x.caratteri,
                }
                for x in self.sequenze_indicizzabili(True)
            ],
        }
        if not includi_testo:
            for voce in dati["unita"]:
                voce.pop("testo", None)
        return dati

    def salva(self, percorso: Path | str,
              includi_testo: bool = True) -> Path:
        destinazione = Path(percorso)
        destinazione.write_text(
            json.dumps(self.to_dict(includi_testo), ensure_ascii=False,
                       indent=2),
            encoding="utf-8",
        )
        return destinazione


def _frammenti_blocco(blocco: Blocco) -> tuple[MappaFrammento, ...]:
    if blocco.frammenti_dom:
        return tuple(MappaFrammento(
            x.xpath, x.inizio_blocco, x.fine_blocco, x.fingerprint)
            for x in blocco.frammenti_dom)
    return (MappaFrammento(
        blocco.xpath, 0, len(blocco.testo), _fingerprint(blocco.testo, 20)),)


def _punto(unita: UnitaSorgente, epub_fingerprint: str,
           offset: int, finale: bool = False) -> PuntoSorgente:
    offset = max(0, min(len(unita.testo), offset))
    frammenti = unita.frammenti
    if finale:
        candidati = [x for x in frammenti if x.inizio_unita < offset]
        frammento = candidati[-1] if candidati else frammenti[0]
    else:
        candidati = [x for x in frammenti if x.fine_unita > offset]
        frammento = candidati[0] if candidati else frammenti[-1]
    locale = frammento.source_start + max(
        0, min(frammento.fine_unita - frammento.inizio_unita,
               offset - frammento.inizio_unita))
    contesto = unita.testo[max(0, offset - 45):min(len(unita.testo), offset + 45)]
    return PuntoSorgente(
        epub_fingerprint, unita.href, frammento.xpath, locale,
        frammento.fingerprint, contesto,
    )


def _intervallo_unita(unita: UnitaSorgente, epub_fingerprint: str,
                      inizio: int, fine: int,
                      testo: str | None = None) -> IntervalloSorgente:
    inizio, fine = _rifila(unita.testo, inizio, fine)
    contenuto = testo if testo is not None else unita.testo[inizio:fine]
    citazione = re.sub(r"\s+", " ", contenuto).strip()[:180]
    return IntervalloSorgente(
        _punto(unita, epub_fingerprint, inizio),
        _punto(unita, epub_fingerprint, fine, finale=True),
        _fingerprint(contenuto), citazione,
    )


def _unita_da_esito(esito, ordine: int,
                     epub_fingerprint: str) -> UnitaSorgente:
    blocco = esito.esito_base.blocco
    frammenti = _frammenti_blocco(blocco)
    seme = (
        epub_fingerprint, blocco.href, frammenti[0].xpath,
        frammenti[-1].xpath, frammenti[-1].fine_unita,
        _fingerprint(blocco.testo),
    )
    unita_id = _id(*seme)
    provvisoria = UnitaSorgente(
        unita_id, ordine, blocco.id, blocco.href, blocco.titolo,
        blocco.testo, esito.categoria, esito.uso, esito.confidenza,
        esito.fonte, tuple(esito.prove),
        # Sostituita immediatamente sotto: serve per costruire la dataclass
        # senza rendere opzionale un dato che nell'API e' obbligatorio.
        IntervalloSorgente(
            PuntoSorgente(epub_fingerprint, blocco.href, frammenti[0].xpath,
                          0, frammenti[0].fingerprint),
            PuntoSorgente(epub_fingerprint, blocco.href, frammenti[-1].xpath,
                          frammenti[-1].fine_unita - frammenti[-1].inizio_unita,
                          frammenti[-1].fingerprint),
            _fingerprint(blocco.testo),
            re.sub(r"\s+", " ", blocco.testo).strip()[:180],
        ),
        frammenti,
    )
    return provvisoria


def _slice_fragments(unit: UnitaSorgente, start: int,
                     end: int) -> tuple[MappaFrammento, ...]:
    fragments = []
    for fragment in unit.frammenti:
        intersection_start = max(start, fragment.inizio_unita)
        intersection_end = min(end, fragment.fine_unita)
        if intersection_start < intersection_end:
            fragments.append(MappaFrammento(
                fragment.xpath,
                intersection_start - start,
                intersection_end - start,
                fragment.fingerprint,
                fragment.source_start
                + intersection_start - fragment.inizio_unita,
            ))
    return tuple(fragments)


def _slice_unit(unit: UnitaSorgente, start: int, end: int, *,
                category: str, order: int,
                range_id: str | None,
                epub_fingerprint: str) -> UnitaSorgente:
    text = unit.testo[start:end]
    fragments = _slice_fragments(unit, start, end)
    if not text or not fragments:
        raise ValueError("Edition Profile range produced an empty source unit")
    evidence = unit.prove
    source = unit.fonte
    confidence = unit.confidenza
    if range_id is not None:
        source = "edition_profile_range"
        confidence = 1.0
        evidence = evidence + (
            f"Edition Profile range override: {range_id} -> {category}",)
    provisional = replace(
        unit,
        id=_id(unit.id, start, end, category),
        ordine=order,
        testo=text,
        categoria=category,
        uso=uso_categoria(category),
        confidenza=confidence,
        fonte=source,
        prove=evidence,
        frammenti=fragments,
    )
    return replace(
        provisional,
        ancora=_intervallo_unita(
            provisional, epub_fingerprint, 0, len(text), text),
    )


def _apply_range_overrides(
        units: tuple[UnitaSorgente, ...], result: AnalisiApparati,
        epub_fingerprint: str) -> tuple[UnitaSorgente, ...]:
    if not result.range_overrides:
        return units
    split_units: list[UnitaSorgente] = []
    for unit in units:
        overrides = result.range_overrides.get((unit.href, unit.blocco_id), ())
        if not overrides:
            split_units.append(replace(unit, ordine=len(split_units)))
            continue
        cursor = 0
        for override in overrides:
            if cursor < override.start:
                split_units.append(_slice_unit(
                    unit, cursor, override.start,
                    category=unit.categoria, order=len(split_units),
                    range_id=None, epub_fingerprint=epub_fingerprint,
                ))
            split_units.append(_slice_unit(
                unit, override.start, override.end,
                category=to_internal(override.category),
                order=len(split_units), range_id=override.range_id,
                epub_fingerprint=epub_fingerprint,
            ))
            cursor = override.end
        if cursor < len(unit.testo):
            split_units.append(_slice_unit(
                unit, cursor, len(unit.testo),
                category=unit.categoria, order=len(split_units),
                range_id=None, epub_fingerprint=epub_fingerprint,
            ))
    return tuple(split_units)


def _rapporto_copertura(risultato: AnalisiApparati,
                        unita: tuple[UnitaSorgente, ...]) \
        -> RapportoCopertura:
    per_categoria: dict[str, int] = {}
    per_motivo: dict[str, int] = {}
    esclusioni = []
    per_href: dict[str, list[UnitaSorgente]] = {}
    for voce in unita:
        per_categoria[voce.categoria] = (
            per_categoria.get(voce.categoria, 0) + voce.caratteri)
        per_href.setdefault(voce.href, []).append(voce)
        if voce.uso == R.ESCLUSO:
            chiave = f"{voce.categoria}:{voce.fonte}"
            per_motivo[chiave] = per_motivo.get(chiave, 0) + voce.caratteri
            esclusioni.append(EsclusioneCopertura(
                voce.id, voce.href, voce.categoria, voce.caratteri,
                voce.fonte, voce.prove,
            ))

    documenti = []
    ignorati_non_visibili = 0
    anomalie_documenti = []
    per_sezione = {x.href: x for x in risultato.analisi.libro.sezioni}
    tutti_href = list(per_sezione)
    for href in per_href:
        if href not in per_sezione:
            tutti_href.append(href)
    for href in tutti_href:
        voci = per_href.get(href, [])
        categorie: dict[str, int] = {}
        for voce in voci:
            categorie[voce.categoria] = (
                categorie.get(voce.categoria, 0) + voce.caratteri)
        classificati = sum(x.caratteri for x in voci)
        principale = sum(x.caratteri for x in voci
                         if x.uso == R.TESTO_PRINCIPALE)
        note = sum(x.caratteri for x in voci if x.uso == R.SU_RICHIESTA)
        esclusi = classificati - principale - note
        xhtml = per_sezione[href].caratteri if href in per_sezione else 0
        scarto = xhtml - classificati
        sezione = per_sezione.get(href)
        ignorati = (max(0, scarto) if sezione is not None and not voci
                    and sezione.n_immagini > 0 else 0)
        ignorati_non_visibili += ignorati
        # Il testo del documento ha uno spazio normalizzato fra atomi; le
        # lunghezze delle unita' classificate, sommate, non includono invece
        # i separatori fra unita'. Nei TOC molto segmentati la differenza e'
        # quindi esattamente ``numero_unita - 1`` e non indica testo perso.
        tolleranza = max(64, round(xhtml * .01), max(0, len(voci) - 1))
        anomalia = None
        if abs(scarto) > tolleranza and not ignorati:
            anomalia = (
                f"{href}: scarto di {scarto} caratteri fra XHTML e blocchi")
            anomalie_documenti.append(anomalia)
        documenti.append(CoperturaDocumento(
            href, xhtml, classificati, principale, note, esclusi,
            scarto, ignorati, anomalia,
            round(principale / max(1, classificati), 6), categorie,
        ))
    if ignorati_non_visibili:
        per_motivo["ignorato_non_visibile:documento_solo_immagine"] = (
            ignorati_non_visibili)

    classificati = sum(x.caratteri for x in unita)
    principale = sum(x.caratteri for x in unita
                     if x.uso == R.TESTO_PRINCIPALE)
    note = sum(x.caratteri for x in unita if x.uso == R.SU_RICHIESTA)
    esclusi = classificati - principale - note
    counts = Counter(x.id for x in unita)
    duplicati = tuple(sorted(item for item, count in counts.items()
                              if count > 1))
    errori = []
    if any(not x.testo for x in unita):
        errori.append("una o piu' unita' sono prive di testo")
    if any(not x.frammenti for x in unita):
        errori.append("una o piu' unita' sono prive di provenienza DOM")
    return RapportoCopertura(
        sum(x.caratteri for x in risultato.analisi.libro.sezioni),
        classificati, principale, note, esclusi, ignorati_non_visibili,
        round(principale / max(1, classificati), 6),
        round((principale + note) / max(1, classificati), 6),
        tuple(documenti), tuple(esclusioni), per_categoria, per_motivo,
        tuple(anomalie_documenti), duplicati, tuple(errori),
    )


def prepara_ingestione(risultato: AnalisiApparati) -> PacchettoIngestione:
    """Converte l'analisi ufficiale nel contratto unico di indicizzazione."""
    libro = risultato.analisi.libro
    impronta = _impronta_file(libro.percorso, libro.impronta_epub)
    unita = tuple(_unita_da_esito(esito, i, impronta)
                  for i, esito in enumerate(risultato.blocchi))
    unita = _apply_range_overrides(unita, risultato, impronta)
    copertura = _rapporto_copertura(risultato, unita)
    return PacchettoIngestione(impronta, libro.titolo, unita, copertura)


def _sequenze(unita: list[UnitaSorgente]) -> tuple[SequenzaIndicizzabile, ...]:
    gruppi: list[list[UnitaSorgente]] = []
    corrente: list[UnitaSorgente] = []
    for voce in unita:
        continua = (corrente
                    and voce.ordine == corrente[-1].ordine + 1
                    and voce.href == corrente[-1].href
                    and voce.categoria == corrente[-1].categoria
                    and voce.uso == corrente[-1].uso)
        if corrente and not continua:
            gruppi.append(corrente)
            corrente = []
        corrente.append(voce)
    if corrente:
        gruppi.append(corrente)

    out = []
    for gruppo in gruppi:
        parti_testo = []
        parti = []
        fini, inizi = [], []
        cursore = 0
        for i, voce in enumerate(gruppo):
            if i:
                parti_testo.append("\n\n")
                cursore += 2
            inizio = cursore
            parti_testo.append(voce.testo)
            cursore += len(voce.testo)
            parti.append(ParteSequenza(voce.id, inizio, cursore))
            for frammento in voce.frammenti:
                inizi.append(inizio + frammento.inizio_unita)
                fini.append(inizio + frammento.fine_unita)
        testo = "".join(parti_testo)
        identificatore = _id(
            gruppo[0].ancora.inizio.epub_fingerprint,
            gruppo[0].href, gruppo[0].categoria,
            gruppo[0].id, gruppo[-1].id,
        )
        out.append(SequenzaIndicizzabile(
            identificatore, gruppo[0].href, gruppo[0].categoria,
            gruppo[0].uso, testo, tuple(x.id for x in gruppo),
            tuple(parti), tuple(sorted(set(fini))),
            tuple(sorted(set(inizi))),
        ))
    return tuple(out)


def _rifila(testo: str, inizio: int, fine: int) -> tuple[int, int]:
    inizio = max(0, min(len(testo), inizio))
    fine = max(inizio, min(len(testo), fine))
    while inizio < fine and testo[inizio].isspace():
        inizio += 1
    while fine > inizio and testo[fine - 1].isspace():
        fine -= 1
    return inizio, fine


def _unita_intersecate(sequenza: SequenzaIndicizzabile,
                       inizio: int, fine: int) -> tuple[str, ...]:
    return tuple(x.unita_id for x in sequenza.parti
                 if x.fine > inizio and x.inizio < fine)


def _intervallo_nell_unita(unita: UnitaSorgente,
                           inizio: int, fine: int) -> tuple[int, int]:
    return max(0, inizio), min(len(unita.testo), fine)


def _ancora_sequenza(epub_fingerprint: str,
                     sequenza: SequenzaIndicizzabile,
                     unita: dict[str, UnitaSorgente],
                     inizio: int, fine: int, testo: str) \
        -> IntervalloSorgente:
    parti = [x for x in sequenza.parti
             if x.fine > inizio and x.inizio < fine]
    if not parti:
        raise ValueError("intervallo senza unita' sorgente")
    prima, ultima = parti[0], parti[-1]
    unita_prima, unita_ultima = unita[prima.unita_id], unita[ultima.unita_id]
    inizio_locale, _ = _intervallo_nell_unita(
        unita_prima, inizio - prima.inizio, fine - prima.inizio)
    _, fine_locale = _intervallo_nell_unita(
        unita_ultima, inizio - ultima.inizio, fine - ultima.inizio)
    return IntervalloSorgente(
        _punto(unita_prima, epub_fingerprint, inizio_locale),
        _punto(unita_ultima, epub_fingerprint, fine_locale, finale=True),
        _fingerprint(testo), re.sub(r"\s+", " ", testo).strip()[:180],
    )


def _passaggio_sequenza(pacchetto: PacchettoIngestione,
                        sequenza: SequenzaIndicizzabile,
                        inizio: int, fine: int) -> PassaggioIndicizzabile:
    if (not isinstance(inizio, int) or not isinstance(fine, int)
            or inizio < 0 or fine > len(sequenza.testo)
            or inizio >= fine):
        raise ValueError("intervallo fuori dalla sequenza")
    inizio, fine = _rifila(sequenza.testo, inizio, fine)
    if inizio >= fine:
        raise ValueError("intervallo privo di testo")
    testo = sequenza.testo[inizio:fine]
    unita_ids = _unita_intersecate(sequenza, inizio, fine)
    per_unita = pacchetto._unita_per_id
    confidenza, fonti, prove = _audit_unita(per_unita, unita_ids)
    ancora = _ancora_sequenza(
        pacchetto.epub_fingerprint, sequenza, per_unita,
        inizio, fine, testo,
    )
    identificatore = _id(
        pacchetto.epub_fingerprint, sequenza.id,
        ancora.inizio.xpath, ancora.inizio.offset,
        ancora.fine.xpath, ancora.fine.offset,
        ancora.fingerprint_testo,
    )
    return PassaggioIndicizzabile(
        identificatore, sequenza.id, testo, sequenza.categoria,
        sequenza.uso, confidenza, fonti, prove, unita_ids,
        inizio, fine, ancora,
    )


def _audit_unita(per_unita: dict[str, UnitaSorgente],
                 unita_ids: tuple[str, ...]) \
        -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    coinvolte = [per_unita[x] for x in unita_ids]
    if not coinvolte:
        raise ValueError("intervallo senza unita' sorgente")
    return (
        min(x.confidenza for x in coinvolte),
        tuple(dict.fromkeys(x.fonte for x in coinvolte)),
        tuple(dict.fromkeys(
            prova for unita in coinvolte for prova in unita.prove)),
    )


def _intervalli_token(tokenizzatore: Tokenizzatore,
                      testo: str) -> list[IntervalloToken]:
    """Valida il contratto di offset prima che influenzi tagli e citazioni."""
    if not isinstance(getattr(tokenizzatore, "nome", None), str):
        raise TypeError("il tokenizzatore deve dichiarare un nome")
    if not isinstance(getattr(tokenizzatore, "esatto", None), bool):
        raise TypeError("il tokenizzatore deve dichiarare esatto come bool")
    intervalli = list(tokenizzatore.intervalli(testo))
    fine_precedente = 0
    for i, intervallo in enumerate(intervalli):
        if not isinstance(intervallo, IntervalloToken):
            raise TypeError(
                f"offset token {i} non e' un IntervalloToken")
        if (intervallo.inizio < 0 or intervallo.fine > len(testo)
                or intervallo.inizio >= intervallo.fine):
            raise ValueError(f"offset token {i} fuori dal testo")
        if i and intervallo.inizio < fine_precedente:
            raise ValueError(f"offset token {i} sovrapposto o non ordinato")
        fine_precedente = intervallo.fine
    return intervalli


def _fine_semantica(sequenza: SequenzaIndicizzabile,
                    token: list[IntervalloToken], inizio_token: int,
                    fine_token: int, minimo_token: int) -> int:
    """Preferisce la fine di un atomo DOM senza superare il budget."""
    if fine_token >= len(token):
        return len(token)
    minimo = min(len(token), inizio_token + minimo_token)
    if minimo >= fine_token:
        return fine_token
    minimo_char = token[minimo - 1].fine
    massimo_char = token[fine_token - 1].fine
    candidati = [x for x in sequenza.confini_frammento
                 if minimo_char <= x <= massimo_char]
    if not candidati:
        return fine_token
    confine = candidati[-1]
    # Numero di token che terminano entro il confine scelto.
    return max(inizio_token + 1,
               bisect_right([x.fine for x in token], confine))


def _copertura_unica(sequenze: tuple[SequenzaIndicizzabile, ...],
                     chunks: list[ChunkIndicizzabile]) -> tuple[int, int]:
    coperti = 0
    totale = 0
    per_seq: dict[str, list[tuple[int, int]]] = {}
    for chunk in chunks:
        per_seq.setdefault(chunk.sequenza_id, []).append(
            (chunk.inizio_sequenza, chunk.fine_sequenza))
    for sequenza in sequenze:
        intervalli = sorted(per_seq.get(sequenza.id, []))
        fusi: list[list[int]] = []
        for inizio, fine in intervalli:
            if not fusi or inizio > fusi[-1][1]:
                fusi.append([inizio, fine])
            else:
                fusi[-1][1] = max(fusi[-1][1], fine)
        for parte in sequenza.parti:
            totale += parte.fine - parte.inizio
            for inizio, fine in fusi:
                coperti += max(0, min(parte.fine, fine)
                               - max(parte.inizio, inizio))
    return totale, coperti


def crea_chunk(
        pacchetto: PacchettoIngestione,
        configurazione: ConfigurazioneChunking, *,
        tokenizzatore: Tokenizzatore) -> PianoChunking:
    """Crea child senza scegliere modello, tokenizer o budget al posto dell'app."""
    config = configurazione
    tokenizer = tokenizzatore
    if config.categories is None:
        indicizzabili = pacchetto.da_indicizzare(config.includi_note)
        sequenze = pacchetto.sequenze_indicizzabili(config.includi_note)
    else:
        indicizzabili = pacchetto.units_for_categories(config.categories)
        sequenze = pacchetto.sequences_for_categories(config.categories)
    per_unita = pacchetto._unita_per_id
    chunks: list[ChunkIndicizzabile] = []
    for sequenza in sequenze:
        token = _intervalli_token(tokenizer, sequenza.testo)
        if not token:
            continue
        inizio_token = 0
        while inizio_token < len(token):
            fine_massima = min(
                len(token), inizio_token + config.massimo_token_piccolo)
            fine_token = _fine_semantica(
                sequenza, token, inizio_token, fine_massima,
                config.minimo_token_piccolo)
            if fine_token <= inizio_token:
                fine_token = min(len(token), inizio_token + 1)
            inizio = token[inizio_token].inizio
            fine = token[fine_token - 1].fine
            inizio, fine = _rifila(sequenza.testo, inizio, fine)
            testo = sequenza.testo[inizio:fine]
            unita_ids = _unita_intersecate(sequenza, inizio, fine)
            confidenza, fonti, prove = _audit_unita(
                per_unita, unita_ids)
            ancora = _ancora_sequenza(
                pacchetto.epub_fingerprint, sequenza, per_unita,
                inizio, fine, testo)
            chunks.append(ChunkIndicizzabile(
                _id(pacchetto.epub_fingerprint, sequenza.id,
                    ancora.inizio.xpath, ancora.inizio.offset,
                    ancora.fine.xpath, ancora.fine.offset,
                    ancora.fingerprint_testo),
                len(chunks), sequenza.id, testo,
                len(_intervalli_token(tokenizer, testo)), sequenza.categoria,
                sequenza.uso, confidenza, fonti, prove, unita_ids,
                inizio, fine, ancora,
            ))
            if fine_token >= len(token):
                break
            prossimo = max(inizio_token + 1,
                           fine_token - config.overlap_token)
            inizio_token = prossimo

    # I vicini sono utili per audit e UI, ma l'espansione usa la sequenza
    # sorgente e non concatena chunk sovrapposti.
    con_vicini = []
    for i, chunk in enumerate(chunks):
        precedente = (chunks[i - 1].id if i and
                      chunks[i - 1].sequenza_id == chunk.sequenza_id else None)
        successivo = (chunks[i + 1].id if i + 1 < len(chunks) and
                      chunks[i + 1].sequenza_id == chunk.sequenza_id else None)
        con_vicini.append(replace(
            chunk, precedente_id=precedente, successivo_id=successivo))
    totale, coperti = _copertura_unica(sequenze, con_vicini)
    attraversamenti = sum(
        1 for chunk in con_vicini
        if len({per_unita[x].categoria for x in chunk.unita_ids}) > 1)
    statistiche = StatisticheChunking(
        len(indicizzabili), len(sequenze), len(con_vicini), totale,
        sum(len(x.testo) for x in con_vicini), coperti,
        max(0, totale - coperti), sum(x.token for x in con_vicini),
        attraversamenti, tokenizer.nome, tokenizer.esatto,
    )
    return PianoChunking(
        pacchetto.epub_fingerprint, config, tuple(con_vicini), sequenze,
        pacchetto.unita, statistiche, tokenizer,
    )
