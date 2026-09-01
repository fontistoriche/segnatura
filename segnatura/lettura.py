"""Apertura di un EPUB: spine, documenti, testo. Nessuna interpretazione.

Qui dentro non si decide niente su cosa una sezione *sia* — si legge e basta.
L'interpretazione sta in `segnali.py` e `classifica.py`, e tenerle separate serve
a poter provare i segnali uno per uno senza rileggere gli zip ogni volta.

Non si usa `ebooklib`: serve accesso ai byte grezzi degli XHTML per cercare
`epub:type`, gli `id` e i link, che ebooklib non espone.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date as CalendarDate
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .blocchi import Blocco, estrai_blocchi
from .epub_safety import (EpubSafetyError, EpubSafetyLimits,
                          SafeEpubArchive)

RE_TAG = re.compile(rb"<[^>]+>")
RE_A = re.compile(rb'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', re.I)
RE_ID = re.compile(rb'\bid\s*=\s*["\']([^"\']+)["\']', re.I)
RE_EPUB_TYPE = re.compile(rb'epub:type\s*=\s*["\']([^"\']+)["\']', re.I)
RE_ROLE = re.compile(rb'\brole\s*=\s*["\'](doc-[^"\']+)["\']', re.I)
RE_H = re.compile(rb"<h([1-6])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
RE_P = re.compile(rb"<p\b[^>]*>(.*?)</p\s*>", re.I | re.S)
RE_NAV = re.compile(rb"<nav\b.*?</nav\s*>", re.I | re.S)
RE_CLASS = re.compile(rb'\bclass\s*=\s*["\']([^"\']+)["\']', re.I)
RE_CSS_CLASS = re.compile(rb'\.([a-z_-][a-z0-9_-]*)', re.I)
RE_CSS_PROP = re.compile(rb'([a-z-]{3,})\s*:', re.I)


@dataclass(frozen=True)
class Collegamento:
    """Un arco fra due ancore, conservato senza interpretarlo.

    Gli href senza frammento restano rappresentabili (`destinazione_id=None`).
    `origine_id` e' l'id dell'elemento link o del suo contenitore piu' vicino:
    serve a verificare che un richiamo e il suo backlink siano davvero reciproci.
    """
    origine_id: str | None
    destinazione_href: str
    destinazione_id: str | None = None


@dataclass(frozen=True)
class Creatore:
    """Creator metadata preserved without collapsing editorial roles."""

    nome: str
    ruoli: tuple[str, ...] = ()
    ordinamento: str | None = None
    id_opf: str | None = None


def _testo(raw: bytes) -> str:
    return RE_TAG.sub(b" ", raw).decode("utf-8", "replace")


def _pulisci(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _testo_visibile(raw: bytes) -> str:
    """Estrae il testo del contenuto, senza metadati o markup non visibile.

    ``_testo`` e' volutamente un fallback lessicale molto permissivo: usato
    sull'intero XHTML finiva pero' per contare anche ``<title>`` e CSS dentro
    ``<style>``. Il segmentatore a blocchi li esclude correttamente, facendo
    apparire come buchi di copertura del testo che un lettore non vedra' mai.
    """
    ignorati = {"head", "script", "style", "nav", "svg"}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Anche sul markup rotto evitiamo almeno i contenitori tecnici piu'
        # comuni prima di ricorrere alla rimozione lessicale dei tag.
        pulito = raw
        for tag in ignorati:
            pulito = re.sub(
                rb"<" + tag.encode("ascii") + rb"\b.*?</" +
                tag.encode("ascii") + rb"\s*>", b" ", pulito,
                flags=re.I | re.S,
            )
        return _pulisci(_testo(pulito))

    parti: list[str] = []

    def visita(elemento) -> None:
        if elemento.tag.rsplit("}", 1)[-1].lower() in ignorati:
            return
        if elemento.text:
            parti.append(elemento.text)
        for figlio in elemento:
            visita(figlio)
            # La coda appartiene al genitore ed e' visibile anche quando il
            # figlio (per esempio uno SVG inline) viene ignorato.
            if figlio.tail:
                parti.append(figlio.tail)

    visita(root)
    return _pulisci(" ".join(parti))


@dataclass
class Sezione:
    """Un documento dello spine, coi suoi dati grezzi e nient'altro."""
    href: str
    indice: int                       # posizione nello spine, 0-based
    linear: bool = True               # spine linear="no" = materiale ausiliario
    titolo: str | None = None         # dal TOC, oppure dal primo heading
    origine_titolo: str | None = None
    testo: str = ""
    paragrafi: list[str] = field(default_factory=list)
    epub_type: set[str] = field(default_factory=set)
    ruoli_aria: set[str] = field(default_factory=set)
    epub_type_documento: set[str] = field(default_factory=set)
    ruoli_aria_documento: set[str] = field(default_factory=set)
    id_presenti: set[str] = field(default_factory=set)
    link_esterni: list[str] = field(default_factory=list)   # verso altre sezioni
    link_interni: set[str] = field(default_factory=set)     # ancore nello stesso file
    collegamenti: list[Collegamento] = field(default_factory=list)
    blocchi: list[Blocco] = field(default_factory=list)
    n_immagini: int = 0

    @property
    def nome(self) -> str:
        return self.href.rsplit("/", 1)[-1]

    @property
    def caratteri(self) -> int:
        return len(self.testo)

    @property
    def coppie_interne_reciproche(self) -> set[frozenset[str]]:
        """Coppie di ancore A↔B nello stesso documento.

        La vecchia `link_interni` dice soltanto che un link colpisce un id
        esistente. Qui si pretende anche l'arco inverso: e' la differenza fra
        un rimando interno generico e la firma tipica richiamo/backlink.
        """
        archi = {(c.origine_id, c.destinazione_id) for c in self.collegamenti
                 if c.destinazione_href == self.href
                 and c.origine_id and c.destinazione_id
                 and c.origine_id != c.destinazione_id}
        return {frozenset((a, b)) for a, b in archi if (b, a) in archi}


@dataclass
class Libro:
    percorso: Path
    versione: str = "?"
    lingua: str | None = None
    editore: str | None = None
    collana: str | None = None
    generatore: str | None = None
    impronta_epub: str | None = None
    famiglia_epub: str | None = None
    impronta_strutturale: tuple[str, ...] = ()
    titolo: str | None = None
    sezioni: list[Sezione] = field(default_factory=list)
    landmarks: dict[str, str] = field(default_factory=dict)   # ruolo -> href
    errore: str | None = None
    creatori: tuple[Creatore, ...] = ()
    data_pubblicazione: str | None = None
    data_pubblicazione_originale: str | None = None

    @property
    def caratteri(self) -> int:
        return sum(s.caratteri for s in self.sezioni)

    @property
    def documenti(self) -> list[Sezione]:
        """Nome esplicito del nuovo modello; `sezioni` resta compatibile."""
        return self.sezioni


def _risolvi(base: str, href: str) -> str:
    h = href.split("#", 1)[0]
    if not h:
        return base
    parti = base.split("/")[:-1] + h.split("/")
    out: list[str] = []
    for p in parti:
        if p in ("", "."):
            continue
        if p == "..":
            if out:
                out.pop()
        else:
            out.append(p)
    return unquote("/".join(out))


def _loc(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _attr(el, nome: str):
    for k, v in el.attrib.items():
        if _loc(k) == nome.lower():
            return v
    return None


def _valore_meta(el) -> str | None:
    valore = _attr(el, "content") or (el.text or "")
    valore = valore.strip()
    return valore or None


def _normalizza_data_pubblicazione(valore: str) -> str | None:
    """Return an ISO calendar date/precision prefix when it is trustworthy."""
    valore = valore.strip()
    match = re.fullmatch(
        r"(\d{4})(?:-(\d{2})(?:-(\d{2})"
        r"(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?)?)?",
        valore,
    )
    if not match:
        return None
    anno, mese, giorno = match.groups()
    if int(anno) < 1000:
        return None
    if mese is None:
        return anno
    if giorno is None:
        if 1 <= int(mese) <= 12:
            return f"{anno}-{mese}"
        return None
    try:
        CalendarDate(int(anno), int(mese), int(giorno))
    except ValueError:
        return None
    return f"{anno}-{mese}-{giorno}"


def _metadati_bibliografici(pkg, libro: Libro) -> None:
    """Read creators and the publication date from EPUB 2 or EPUB 3 OPF."""
    creatori: list[dict[str, object]] = []
    per_id: dict[str, dict[str, object]] = {}
    raffinamenti: dict[str, list[tuple[str, str]]] = {}
    date_candidate: list[tuple[int, str]] = []

    for el in pkg.iter():
        nome = _loc(el.tag)
        valore = (el.text or "").strip()
        if nome == "creator" and valore:
            identificatore = _attr(el, "id")
            ruoli = tuple(dict.fromkeys(
                x.casefold() for x in (_attr(el, "role") or "").split()
                if x.strip()))
            record: dict[str, object] = {
                "nome": valore,
                "ruoli": list(ruoli),
                "ordinamento": (_attr(el, "file-as") or "").strip() or None,
                "identificatore": identificatore,
            }
            creatori.append(record)
            if identificatore and identificatore not in per_id:
                per_id[identificatore] = record
        elif nome == "date" and valore:
            evento = (_attr(el, "event") or "").casefold().strip()
            if evento in {"publication", "published", "issued"}:
                date_candidate.append((0, valore))
            elif not evento:
                date_candidate.append((1, valore))
        elif nome == "meta":
            proprieta = (_attr(el, "property") or "").casefold().strip()
            contenuto = _valore_meta(el)
            refines = (_attr(el, "refines") or "").strip()
            if refines.startswith("#") and contenuto:
                raffinamenti.setdefault(refines[1:], []).append(
                    (proprieta, contenuto))
            elif (proprieta in {"dcterms:issued", "publication-date"}
                  and contenuto):
                date_candidate.append((0, contenuto))

    for identificatore, valori in raffinamenti.items():
        record = per_id.get(identificatore)
        if record is None:
            continue
        for proprieta, valore in valori:
            if proprieta == "role":
                ruoli = record["ruoli"]
                if not isinstance(ruoli, list):
                    raise TypeError("creator roles must be stored as a list")
                for ruolo in valore.split():
                    normalizzato = ruolo.casefold()
                    if normalizzato and normalizzato not in ruoli:
                        ruoli.append(normalizzato)
            elif proprieta == "file-as" and not record["ordinamento"]:
                record["ordinamento"] = valore

    libro.creatori = tuple(Creatore(
        nome=str(record["nome"]),
        ruoli=tuple(str(x) for x in record["ruoli"]),
        ordinamento=(str(record["ordinamento"])
                     if record["ordinamento"] else None),
        id_opf=(str(record["identificatore"])
                if record["identificatore"] else None),
    ) for record in creatori)

    if date_candidate:
        _, originale = min(enumerate(date_candidate),
                            key=lambda item: (item[1][0], item[0]))[1]
        libro.data_pubblicazione_originale = originale
        libro.data_pubblicazione = _normalizza_data_pubblicazione(originale)


def _normalizza_nome_file(nome: str) -> str:
    """Riduce un nome a uno schema di template, non all'identita' del libro."""
    nome = unquote(nome).casefold()
    nome = re.sub(r"[0-9a-f]{12,}", "@", nome)
    nome = re.sub(r"\d+", "#", nome)
    nome = re.sub(r"[^a-zà-öø-ÿ#@._/-]+", "_", nome)
    return nome[:120]


def _chiudi_impronta(libro: Libro, token: set[str]) -> None:
    """Crea l'impronta della pipeline EPUB senza usare editore o contenuto."""
    ordinati = tuple(sorted(token))
    libro.impronta_strutturale = ordinati
    materiale = "\n".join(ordinati).encode("utf-8")
    libro.impronta_epub = hashlib.sha256(materiale).hexdigest()[:16]
    libro.famiglia_epub = libro.impronta_epub


def assegna_famiglie(libri: list[Libro], soglia: float = 0.72) -> None:
    """Raggruppa template simili senza usare il nome dell'editore.

    Una corrispondenza esatta e' troppo severa: nel corpus reale produrrebbe una
    famiglia per libro. Il Jaccard fra classi CSS, schemi dei nomi, proprieta'
    CSS e struttura OPF riconosce invece pipeline affini anche fra editori
    diversi, e separa collane dello stesso editore quando la struttura cambia.
    """
    validi = [l for l in libri if l.impronta_strutturale]
    parent = list(range(len(validi)))

    def trova(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def unisci(a: int, b: int) -> None:
        a, b = trova(a), trova(b)
        if a != b:
            parent[b] = a

    insiemi = [set(l.impronta_strutturale) for l in validi]
    for i, a in enumerate(insiemi):
        for j in range(i + 1, len(insiemi)):
            b = insiemi[j]
            if len(a & b) / max(1, len(a | b)) >= soglia:
                unisci(i, j)
    gruppi: dict[int, list[int]] = {}
    for i in range(len(validi)):
        gruppi.setdefault(trova(i), []).append(i)
    for membri in gruppi.values():
        id_stabili = sorted(validi[i].impronta_epub or "" for i in membri)
        famiglia = "fam-" + id_stabili[0]
        for i in membri:
            validi[i].famiglia_epub = famiglia


def _collegamenti(raw: bytes, href_documento: str,
                  documenti: set[str]) -> list[Collegamento]:
    """Estrae gli archi conservando origine e frammento di destinazione.

    Gli EPUB dovrebbero contenere XHTML ben formato. Se un editore consegna
    HTML non parseabile, il fallback regex mantiene il comportamento storico;
    semplicemente non inventa un'origine e quindi non puo' affermare una
    reciprocita' esatta.
    """
    out: list[Collegamento] = []

    def visita(el, id_antenato: str | None = None):
        origine = _attr(el, "id") or id_antenato
        if _loc(el.tag) == "a":
            destinazione = _attr(el, "href")
            if destinazione and not destinazione.startswith(
                    ("http://", "https://", "mailto:")):
                parte, separatore, frammento = destinazione.partition("#")
                destinazione_href = (_risolvi(href_documento, parte)
                                     if parte else href_documento)
                if destinazione_href in documenti:
                    out.append(Collegamento(
                        origine,
                        destinazione_href,
                        unquote(frammento) if separatore and frammento else None,
                    ))
        for figlio in el:
            visita(figlio, origine)

    try:
        visita(ET.fromstring(raw))
        return out
    except ET.ParseError:
        pass

    for h in RE_A.findall(raw):
        destinazione = h.decode("utf-8", "replace")
        if destinazione.startswith(("http://", "https://", "mailto:")):
            continue
        parte, separatore, frammento = destinazione.partition("#")
        destinazione_href = (_risolvi(href_documento, parte)
                             if parte else href_documento)
        if destinazione_href in documenti:
            out.append(Collegamento(
                None,
                destinazione_href,
                unquote(frammento) if separatore and frammento else None,
            ))
    return out


def _semantica_documento(raw: bytes) -> tuple[set[str], set[str]]:
    """Semantica applicata al documento, non a un discendente locale.

    Si considerano radice, body e l'eventuale unico contenitore principale. Un
    `aside epub:type="footnote"` dentro un capitolo non deve trasformare l'intero
    XHTML in una nota.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return set(), set()
    candidati = [root]
    body = next((e for e in root.iter() if _loc(e.tag) == "body"), None)
    if body is not None:
        candidati.append(body)
        figli = [e for e in list(body)
                 if _loc(e.tag) not in {"script", "style", "nav"}]
        if len(figli) == 1:
            candidati.append(figli[0])
    tipi, aria = set(), set()
    for el in candidati:
        for k, v in el.attrib.items():
            if k == "epub:type" or (k.endswith("}type")
                                     and "idpf.org/2007/ops" in k):
                tipi.update(v.lower().split())
        ruolo = (_attr(el, "role") or "").lower().split()
        aria.update(x for x in ruolo if x.startswith("doc-"))
    return tipi, aria


def _toc(z: SafeEpubArchive, manifest: dict, opf: str,
         ncx_id: str | None) -> dict:
    """href -> titolo. Si legge dal nav XHTML e dall'NCX, non da una libreria:
    i due formati convivono e nessuno dei due e' garantito."""
    mappa: dict[str, str] = {}
    # nav XHTML (EPUB 3, ma presente anche in molti file dichiarati 2.0)
    for href in manifest.values():
        if not href.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            raw = z.read(href, xml=True)
        except KeyError:
            continue
        if b"<nav" not in raw.lower():
            continue
        for blocco in RE_NAV.findall(raw):
            m = re.search(rb'epub:type\s*=\s*["\']([^"\']+)["\']', blocco, re.I)
            tipo = m.group(1).decode("utf-8", "replace").lower() if m else ""
            if "landmarks" in tipo:
                continue
            for a in re.finditer(rb'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                                 blocco, re.I | re.S):
                t = _pulisci(_testo(a.group(2)))
                if t:
                    mappa.setdefault(_risolvi(href, a.group(1).decode("utf-8", "replace")), t)
    if mappa:
        return mappa
    # NCX (EPUB 2)
    ncx = manifest.get(ncx_id) if ncx_id else None
    if not ncx:
        ncx = next((h for h in manifest.values() if h.lower().endswith(".ncx")), None)
    if ncx:
        try:
            root = ET.fromstring(z.read(ncx, xml=True))
        except (KeyError, ET.ParseError):
            return mappa
        for np in root.iter():
            if _loc(np.tag) != "navpoint":
                continue
            src = titolo = None
            for e in np.iter():
                if _loc(e.tag) == "content":
                    src = _attr(e, "src")
                elif _loc(e.tag) == "text" and e.text:
                    titolo = titolo or e.text.strip()
            if src and titolo:
                mappa.setdefault(_risolvi(ncx, src), titolo)
    return mappa


def _landmarks(z: SafeEpubArchive, manifest: dict) -> dict:
    """I landmarks dicono dove comincia il corpo del testo: `bodymatter`."""
    out = {}
    for href in manifest.values():
        if not href.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            raw = z.read(href, xml=True)
        except KeyError:
            continue
        if b"landmarks" not in raw.lower():
            continue
        for blocco in RE_NAV.findall(raw):
            if b"landmarks" not in blocco.lower():
                continue
            for a in re.finditer(
                    rb'<a\b[^>]*epub:type\s*=\s*["\']([^"\']+)["\'][^>]*href\s*=\s*["\']([^"\']+)["\']',
                    blocco, re.I):
                out[a.group(1).decode("utf-8", "replace").lower()] = \
                    _risolvi(href, a.group(2).decode("utf-8", "replace"))
    return out


def _fallimento_sicurezza(libro: Libro, errore: EpubSafetyError) -> Libro:
    libro.sezioni.clear()
    libro.landmarks.clear()
    libro.errore = f"unsafe EPUB archive: {errore}"
    return libro


def leggi(percorso: Path | str, *,
          limiti_sicurezza: EpubSafetyLimits | None = None) -> Libro:
    """Apre un EPUB e restituisce tutto il grezzo, senza interpretarlo."""
    percorso = Path(percorso)
    libro = Libro(percorso=percorso)
    try:
        z = zipfile.ZipFile(percorso)
    except (zipfile.BadZipFile, OSError) as e:
        libro.errore = f"non e' uno zip leggibile: {e}"
        return libro

    with z:
        try:
            archivio = SafeEpubArchive(z, limiti_sicurezza)
        except EpubSafetyError as e:
            return _fallimento_sicurezza(libro, e)
        try:
            root = ET.fromstring(archivio.read(
                "META-INF/container.xml", xml=True))
            opf = next(_attr(e, "full-path") for e in root.iter()
                       if _loc(e.tag) == "rootfile")
            pkg = ET.fromstring(archivio.read(opf, xml=True))
        except EpubSafetyError as e:
            return _fallimento_sicurezza(libro, e)
        except Exception as e:
            libro.errore = f"OPF illeggibile: {type(e).__name__}: {e}"
            return libro

        libro.versione = _attr(pkg, "version") or "?"
        _metadati_bibliografici(pkg, libro)
        impronta = {f"epub_version={libro.versione.split('.')[0]}",
                    f"opf_dir={_normalizza_nome_file(str(Path(opf).parent))}"}
        manifest, ncx_id, spine = {}, None, []
        for el in pkg.iter():
            n = _loc(el.tag)
            if n == "item":
                manifest[_attr(el, "id")] = _risolvi(opf, _attr(el, "href") or "")
            elif n == "spine":
                ncx_id = _attr(el, "toc")
            elif n == "itemref":
                spine.append((_attr(el, "idref"),
                              (_attr(el, "linear") or "yes").lower() != "no"))
            elif n in ("language", "publisher", "title") and (el.text or "").strip():
                setattr(libro, {"language": "lingua", "publisher": "editore",
                                "title": "titolo"}[n],
                        getattr(libro, {"language": "lingua", "publisher": "editore",
                                        "title": "titolo"}[n]) or el.text.strip())
            elif n == "meta":
                chiave = (_attr(el, "name") or _attr(el, "property") or "").casefold()
                valore = _valore_meta(el)
                if not valore:
                    continue
                if chiave in {"generator", "dcterms:generator"}:
                    libro.generatore = libro.generatore or valore
                elif (chiave in {"calibre:series", "series"}
                      or chiave.endswith(":belongs-to-collection")
                      or chiave == "belongs-to-collection"):
                    libro.collana = libro.collana or valore

        if libro.generatore:
            generatore = re.sub(r"\d+(?:\.\d+)*", "#",
                                libro.generatore.casefold())
            impronta.add(f"generator={generatore[:100]}")
        impronta.add(f"ha_ncx={bool(ncx_id)}")
        impronta.add(f"ha_nav={any('nav' in (k or '').casefold() for k in manifest)}")
        for nome in archivio.names():
            basso = nome.casefold()
            if basso.endswith((".xhtml", ".html", ".htm")):
                impronta.add(f"xhtml={_normalizza_nome_file(nome)}")
            elif basso.endswith(".css"):
                impronta.add(f"css_file={_normalizza_nome_file(nome)}")
                try:
                    css = archivio.read(nome)
                except KeyError:
                    continue
                except EpubSafetyError as e:
                    return _fallimento_sicurezza(libro, e)
                for classe in RE_CSS_CLASS.findall(css)[:300]:
                    impronta.add("css_class=" + classe.decode("utf-8", "replace").casefold())
                for prop in RE_CSS_PROP.findall(css)[:300]:
                    impronta.add("css_prop=" + prop.decode("ascii", "ignore").casefold())

        try:
            toc = _toc(archivio, manifest, opf, ncx_id)
            libro.landmarks = _landmarks(archivio, manifest)
        except EpubSafetyError as e:
            return _fallimento_sicurezza(libro, e)
        documenti = {manifest.get(i) for i, _ in spine} - {None}

        for i, (idref, linear) in enumerate(spine):
            href = manifest.get(idref)
            if not href:
                continue
            try:
                raw = archivio.read(href, xml=True)
            except KeyError:
                continue
            except EpubSafetyError as e:
                return _fallimento_sicurezza(libro, e)
            s = Sezione(href=href, indice=i, linear=linear)
            corpo = RE_NAV.sub(b" ", raw)      # i <nav> non sono contenuto

            for valore in RE_CLASS.findall(raw):
                for classe in valore.decode("utf-8", "replace").casefold().split():
                    if len(classe) <= 80:
                        impronta.add(f"html_class={classe}")

            s.testo = _testo_visibile(corpo)
            s.paragrafi = [t for t in (_pulisci(_testo(m)) for m in RE_P.findall(corpo)) if t]
            s.n_immagini = len(re.findall(rb"<img\b|<image\b", raw, re.I))
            s.blocchi = estrai_blocchi(corpo, href)
            s.id_presenti = {x.decode("utf-8", "replace") for x in RE_ID.findall(raw)}

            for v in RE_EPUB_TYPE.findall(corpo):
                s.epub_type |= set(v.decode("utf-8", "replace").lower().split())
            for v in RE_ROLE.findall(corpo):
                s.ruoli_aria.add(v.decode("utf-8", "replace").lower())
            s.epub_type_documento, s.ruoli_aria_documento = \
                _semantica_documento(corpo)

            s.collegamenti = _collegamenti(corpo, href, documenti)
            s.link_interni = {c.destinazione_id for c in s.collegamenti
                              if c.destinazione_href == href
                              and c.destinazione_id}
            s.link_esterni = [c.destinazione_href for c in s.collegamenti
                              if c.destinazione_href != href]

            s.titolo = toc.get(href)
            s.origine_titolo = "TOC" if s.titolo else None
            if not s.titolo:
                m = RE_H.search(corpo)
                if m:
                    s.titolo = _pulisci(_testo(m.group(2))) or None
                    s.origine_titolo = f"h{m.group(1).decode()}" if s.titolo else None
            libro.sezioni.append(s)

        _chiudi_impronta(libro, impronta)

    return libro
