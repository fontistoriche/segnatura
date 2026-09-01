"""Segmentazione DOM degli XHTML in unita' semantiche verificabili.

Un file dello spine e' un contenitore editoriale, non necessariamente una sola
unita' di significato. Qui lo trasformiamo in blocchi abbastanza grandi da
essere classificati e revisionati, ma senza attraversare heading, cambi di
semantica dichiarata, liste, tabelle o limiti di dimensione.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from . import ruoli as R

TAG_IGNORATI = {"head", "script", "style", "nav", "svg"}
TAG_ATOMICI = {"p", "li", "dt", "dd", "pre", "table", "figcaption",
               "blockquote"}
TAG_TITOLI = {f"h{i}" for i in range(1, 7)}
TAG_CONTENITORI = {"body", "main", "article", "section", "aside", "div"}
MAX_CARATTERI_BLOCCO = 12_000


def _loc(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _attr(el, nome: str):
    for k, v in el.attrib.items():
        if _loc(k) == nome.lower():
            return v
    return None


def _epub_type(el) -> str | None:
    for k, v in el.attrib.items():
        if k == "epub:type" or (k.endswith("}type") and "idpf.org/2007/ops" in k):
            return v
    return None


def _testo_elemento(el) -> str:
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip()


def _forma(tag: str) -> str:
    if tag in TAG_TITOLI:
        return "titolo"
    if tag in {"li", "dt", "dd"}:
        return "voce_elenco"
    if tag == "table":
        return "tabella"
    if tag == "blockquote":
        return "citazione"
    if tag == "pre":
        return "codice"
    if tag == "figcaption":
        return "didascalia"
    return "prosa"


@dataclass
class FrammentoDOM:
    """Provenienza di un atomo normalizzato dentro il testo del blocco.

    Gli offset sono riferiti al testo normalizzato di :class:`Blocco`, mentre
    ``fingerprint`` identifica il testo dell'elemento DOM. Il chunker puo' cosi'
    cambiare budget senza usare l'identificatore del chunk come citazione.
    """
    xpath: str
    inizio_blocco: int
    fine_blocco: int
    fingerprint: str


@dataclass
class Blocco:
    """Unita' classificabile con provenienza stabile nel documento."""
    id: str
    href: str
    indice: int
    xpath: str
    testo: str
    forma: str
    titolo: str | None = None
    livello_titolo: int | None = None
    epub_type: set[str] = field(default_factory=set)
    ruoli_aria: set[str] = field(default_factory=set)
    n_elementi: int = 1
    n_link: int = 0
    n_immagini: int = 0
    posizione: float = 0.0
    marcatori_dom: tuple[str, ...] = ()
    frammenti_dom: tuple[FrammentoDOM, ...] = ()

    @property
    def caratteri(self) -> int:
        return len(self.testo)

    @property
    def fingerprint(self) -> str:
        normalizzato = re.sub(r"\s+", " ", self.testo).strip().casefold()
        return hashlib.sha256(normalizzato.encode("utf-8")).hexdigest()[:20]


@dataclass
class _Atomo:
    xpath: str
    testo: str
    forma: str
    titolo: str | None
    livello_titolo: int | None
    epub_type: frozenset[str]
    ruoli_aria: frozenset[str]
    marcatori_dom: tuple[str, ...]
    n_link: int
    n_immagini: int


def _ha_discendenti_atomici(el) -> bool:
    # I convertitori Calibre possono rappresentare ogni paragrafo come un
    # ``div`` fratello, senza alcun ``p``. Il contenitore padre non va allora
    # appiattito in un unico atomo: i figli sono confini di blocco reali anche
    # se al loro interno hanno soltanto ``span`` inline.
    return (any(_loc(x.tag) in TAG_ATOMICI | TAG_TITOLI for x in el.iter()
                if x is not el)
            or any(_loc(x.tag) in TAG_CONTENITORI for x in list(el)))


def _atomi(raw: bytes) -> list[_Atomo]:
    root = ET.fromstring(raw)
    out: list[_Atomo] = []
    titolo_corrente: str | None = None
    livello_corrente: int | None = None

    def visita(el, xpath: str, tipi: frozenset[str], aria: frozenset[str],
               marcatori: tuple[str, ...]):
        nonlocal titolo_corrente, livello_corrente
        tag = _loc(el.tag)
        if tag in TAG_IGNORATI:
            return
        nuovi_tipi = tipi | frozenset((_epub_type(el) or "").lower().split())
        ruolo = (_attr(el, "role") or "").lower().split()
        nuova_aria = aria | frozenset(x for x in ruolo if x.startswith("doc-"))
        locali = tuple(x.casefold() for x in
                       ((_attr(el, "class") or "").split()
                        + [_attr(el, "id") or ""]) if x)
        nuovi_marcatori = marcatori + locali
        # Il contenitore collettivo puo' dichiarare la propria funzione solo
        # attraverso la forma dei link, mentre ogni figlio contiene una nota
        # singola e non soddisfa piu' da solo la firma [1] [2] [3]. Il
        # marcatore sintetico conserva l'informazione durante la discesa DOM.
        link_elemento = sum(
            1 for x in el.iter()
            if _loc(x.tag) == "a" and _attr(x, "href")
        )
        if R.apparato_note_numerate_linkate(
                _testo_elemento(el), link_elemento):
            nuovi_marcatori += (R.MARCATORE_NOTE_NUMERATE_LINKATE,)

        atomico = tag in TAG_ATOMICI or tag in TAG_TITOLI
        if tag in {"li", "dt", "dd", "blockquote"} and _ha_discendenti_atomici(el):
            atomico = False
        if tag == "table":
            testo = _testo_elemento(el)
            if testo:
                out.append(_Atomo(xpath, testo, _forma(tag), titolo_corrente,
                                  livello_corrente, nuovi_tipi, nuova_aria,
                                  nuovi_marcatori,
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) == "a"
                                      and _attr(x, "href")),
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) in {"img", "image"})))
            return
        if atomico:
            testo = _testo_elemento(el)
            if testo:
                if tag in TAG_TITOLI:
                    titolo_corrente = testo
                    livello_corrente = int(tag[1])
                out.append(_Atomo(xpath, testo, _forma(tag), titolo_corrente,
                                  livello_corrente, nuovi_tipi, nuova_aria,
                                  nuovi_marcatori,
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) == "a"
                                      and _attr(x, "href")),
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) in {"img", "image"})))
            return

        if _ha_discendenti_atomici(el):
            # Un elemento non atomico puo' avere testo proprio oltre ai figli
            # atomici. E' tipico degli indici annidati:
            #   <li>voce principale<ul><li>sottovoce</li></ul></li>
            # Visitare soltanto i figli perde "voce principale". Conserviamo
            # i frammenti inline nel loro ordine e apriamo un atomo distinto
            # ogni volta che incontriamo un ramo di blocco.
            parti_inline: list[str] = [el.text or ""]
            link_inline = 0
            immagini_inline = 0
            frammento = 0

            def emetti_inline():
                nonlocal parti_inline, link_inline, immagini_inline, frammento
                testo = re.sub(r"\s+", " ", " ".join(parti_inline)).strip()
                if testo:
                    frammento += 1
                    out.append(_Atomo(
                        f"{xpath}/text()[{frammento}]", testo, _forma(tag),
                        titolo_corrente, livello_corrente, nuovi_tipi,
                        nuova_aria, nuovi_marcatori, link_inline,
                        immagini_inline,
                    ))
                parti_inline = []
                link_inline = 0
                immagini_inline = 0

            conteggi: dict[str, int] = {}
            for figlio in list(el):
                nome = _loc(figlio.tag)
                ramo_blocco = (
                    nome in (TAG_ATOMICI | TAG_TITOLI | TAG_CONTENITORI
                             | TAG_IGNORATI)
                    or _ha_discendenti_atomici(figlio)
                )
                if ramo_blocco:
                    emetti_inline()
                    conteggi[nome] = conteggi.get(nome, 0) + 1
                    visita(figlio, f"{xpath}/{nome}[{conteggi[nome]}]",
                           nuovi_tipi, nuova_aria, nuovi_marcatori)
                else:
                    parti_inline.append(" ".join(figlio.itertext()))
                    link_inline += sum(
                        1 for x in figlio.iter()
                        if _loc(x.tag) == "a" and _attr(x, "href"))
                    immagini_inline += sum(
                        1 for x in figlio.iter()
                        if _loc(x.tag) in {"img", "image"})
                parti_inline.append(figlio.tail or "")
            emetti_inline()
            return

        if tag in TAG_CONTENITORI and not _ha_discendenti_atomici(el):
            testo = _testo_elemento(el)
            if testo:
                out.append(_Atomo(xpath, testo, "prosa", titolo_corrente,
                                  livello_corrente, nuovi_tipi, nuova_aria,
                                  nuovi_marcatori,
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) == "a"
                                      and _attr(x, "href")),
                                  sum(1 for x in el.iter()
                                      if _loc(x.tag) in {"img", "image"})))
            return

        conteggi: dict[str, int] = {}
        figli = list(el)
        for figlio in figli:
            nome = _loc(figlio.tag)
            conteggi[nome] = conteggi.get(nome, 0) + 1
            visita(figlio, f"{xpath}/{nome}[{conteggi[nome]}]",
                   nuovi_tipi, nuova_aria, nuovi_marcatori)

    visita(root, f"/{_loc(root.tag)}[1]", frozenset(), frozenset(), ())
    return out


def _forma_gruppo(atomi: list[_Atomo]) -> str:
    forme = {a.forma for a in atomi if a.forma != "titolo"}
    if atomi and atomi[0].forma == "titolo":
        return "sezione"
    if len(forme) == 1:
        forma = next(iter(forme))
        return "elenco" if forma == "voce_elenco" else forma
    return "misto"


def _costruisci(href: str, indice: int, atomi: list[_Atomo]) -> Blocco:
    parti: list[str] = []
    frammenti: list[FrammentoDOM] = []
    cursore = 0
    for i, atomo in enumerate(atomi):
        if i:
            parti.append(" ")
            cursore += 1
        inizio = cursore
        parti.append(atomo.testo)
        cursore += len(atomo.testo)
        normalizzato = re.sub(r"\s+", " ", atomo.testo).strip().casefold()
        frammenti.append(FrammentoDOM(
            atomo.xpath, inizio, cursore,
            hashlib.sha256(normalizzato.encode("utf-8")).hexdigest()[:20],
        ))
    testo = "".join(parti)
    titolo = next((a.testo for a in atomi if a.forma == "titolo"),
                  atomi[0].titolo)
    livello = next((a.livello_titolo for a in atomi if a.forma == "titolo"),
                   atomi[0].livello_titolo)
    seme = f"{href}\0{atomi[0].xpath}\0{testo[:200]}"
    identificatore = hashlib.sha256(seme.encode("utf-8")).hexdigest()[:20]
    return Blocco(
        id=identificatore, href=href, indice=indice, xpath=atomi[0].xpath,
        testo=testo, forma=_forma_gruppo(atomi), titolo=titolo,
        livello_titolo=livello,
        epub_type=set().union(*(a.epub_type for a in atomi)),
        ruoli_aria=set().union(*(a.ruoli_aria for a in atomi)),
        n_elementi=len(atomi), n_link=sum(a.n_link for a in atomi),
        n_immagini=sum(a.n_immagini for a in atomi),
        marcatori_dom=tuple(dict.fromkeys(
            marcatore for atomo in atomi for marcatore in atomo.marcatori_dom
        )),
        frammenti_dom=tuple(frammenti),
    )


def estrai_blocchi(raw: bytes, href: str) -> list[Blocco]:
    """Segmenta un XHTML. Su markup rotto conserva almeno un blocco fallback."""
    try:
        atomi = _atomi(raw)
    except ET.ParseError:
        testo = html.unescape(re.sub(r"<[^>]+>", " ",
                                     raw.decode("utf-8", "replace")))
        testo = re.sub(r"\s+", " ", testo).strip()
        if not testo:
            return []
        return [Blocco(hashlib.sha256((href + testo[:200]).encode()).hexdigest()[:20],
                       href, 0, "/", testo, "misto")]
    if not atomi:
        return []

    gruppi: list[list[_Atomo]] = []
    corrente: list[_Atomo] = []
    caratteri = 0
    chiave_semantica = None
    for atomo in atomi:
        # Le semantiche dichiarate non vivono soltanto in epub:type/ARIA.
        # Molti EPUB 2 usano contenitori come ``class="footnotes"``: se un
        # chunk comincia nell'indice e termina dentro quel contenitore, unire
        # i marcatori fa prevalere la nota sull'intero blocco. Il ruolo DOM
        # riconosciuto entra quindi nella chiave e apre un confine reale;
        # classi puramente grafiche continuano a non spezzare nulla.
        ruolo_dom, _ = R.per_marcatori_dom(atomo.marcatori_dom)
        if (not ruolo_dom
                and R.apparato_note_numerate_linkate(
                    atomo.testo, atomo.n_link)):
            ruolo_dom = R.NOTA
        chiave = (atomo.epub_type, atomo.ruoli_aria, ruolo_dom)
        separa = bool(corrente) and (
            atomo.forma == "titolo"
            or chiave != chiave_semantica
            or caratteri + len(atomo.testo) > MAX_CARATTERI_BLOCCO
            or (atomo.forma != corrente[-1].forma
                and ({atomo.forma, corrente[-1].forma}
                     & {"tabella", "codice", "citazione"}))
        )
        if separa:
            gruppi.append(corrente)
            corrente, caratteri = [], 0
        if not corrente:
            chiave_semantica = chiave
        corrente.append(atomo)
        caratteri += len(atomo.testo)
    if corrente:
        gruppi.append(corrente)

    blocchi = [_costruisci(href, i, gruppo) for i, gruppo in enumerate(gruppi)]
    denominatore = max(1, len(blocchi) - 1)
    for i, blocco in enumerate(blocchi):
        blocco.posizione = i / denominatore
    return blocchi
