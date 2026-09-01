"""I segnali. Ognuno guarda una cosa sola e vota, con un peso e una prova.

Nessuno decide da solo: e' misurato che nessuno basta. Su 109 libri veri,
`epub:type` compare nel 4% e il grafo dei link riconosce le note in circa un
terzo. Il vocabolario dei titoli copre molto ma dipende dalla lingua e tace
quando il titolo manca. Sommandoli si arriva lontano; presi uno per uno, no.

Ogni segnale restituisce una lista di `Voto(sezione_href, ruolo, peso, prova)`.
`classifica.py` li somma. La `prova` e' una stringa leggibile, e serve a poter
sempre rispondere alla domanda «perche' hai deciso cosi'?».
"""
from __future__ import annotations

import re
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from . import ruoli as R
from .lettura import Libro, Sezione


@dataclass(frozen=True)
class Voto:
    href: str
    ruolo: str
    peso: float
    prova: str
    conferma: bool = False
    """Un voto di sola CONFERMA rafforza un ruolo gia' sostenuto da altro, ma non
    puo' stabilirlo da solo.

    Serve perche' la posizione, presa sul serio, fa danni: alla prima prova 197
    sezioni erano state dichiarate «bibliografia» solo perche' stavano in fondo al
    libro — cioe' gli ultimi capitoli di ogni volume, 1,6 milioni di caratteri,
    buttati fuori dall'indice. «In fondo» c'e' la bibliografia, ma c'e' anche
    l'ultimo capitolo."""


# ---------------------------------------------------------------------------
# 1. Dichiarazioni dell'editore: epub:type e ruoli ARIA.
#    Quando ci sono sono certe, e valgono in qualunque lingua. Rare: 4% dei file.
# ---------------------------------------------------------------------------
def da_dichiarazioni(libro: Libro) -> list[Voto]:
    voti = []
    for s in libro.sezioni:
        conteggio: Counter = Counter()
        for v in s.epub_type_documento:
            if v in R.DA_EPUB_TYPE:
                conteggio[R.DA_EPUB_TYPE[v]] += 1
        for v in s.ruoli_aria_documento:
            if v in R.DA_ARIA:
                conteggio[R.DA_ARIA[v]] += 1
        # Un file di sole note spesso marca ogni `aside`, non il `body`. Se una
        # stessa dichiarazione copre almeno il 70% dei blocchi, e non ci sono
        # ruoli locali concorrenti, puo' descrivere il documento. Nel capitolo
        # misto (corpo + qualche footnote) questa condizione non scatta.
        ruoli_blocchi = []
        for blocco in s.blocchi:
            locali = {R.DA_EPUB_TYPE[v] for v in blocco.epub_type
                      if v in R.DA_EPUB_TYPE and v != "noteref"}
            locali |= {R.DA_ARIA[v] for v in blocco.ruoli_aria
                       if v in R.DA_ARIA and v != "doc-noteref"}
            if len(locali) == 1:
                ruoli_blocchi.append(next(iter(locali)))
        if (s.blocchi and len(ruoli_blocchi) / len(s.blocchi) >= 0.7
                and len(set(ruoli_blocchi)) == 1):
            conteggio[ruoli_blocchi[0]] += len(ruoli_blocchi)
        for ruolo, n in conteggio.items():
            # `noteref` marca i RICHIAMI, che stanno nel corpo: una sezione piena
            # di richiami e' il testo, non le note. Le note hanno `footnote`.
            voti.append(Voto(s.href, ruolo, 6.0 if n > 2 else 5.0,
                             f"epub:type/ARIA dichiara {ruolo}"))
        if (not conteggio and
                ({"noteref"} & s.epub_type
                 or {"doc-noteref"} & s.ruoli_aria)):
            voti.append(Voto(s.href, R.CORPO, 2.0,
                             "contiene richiami di nota (noteref)"))
    for ruolo, href in libro.landmarks.items():
        if ruolo == "bodymatter":
            voti.append(Voto(href, R.CORPO, 3.0, "landmarks: qui comincia il testo"))
        elif ruolo in R.DA_EPUB_TYPE:
            voti.append(Voto(href, R.DA_EPUB_TYPE[ruolo], 3.0,
                             f"landmarks: {ruolo}"))
    return voti


# ---------------------------------------------------------------------------
# 2. Il grafo dei link: riconosce le NOTE, e solo quelle.
#    Una nota ha un richiamo che punta a lei e un ritorno che riporta indietro.
#    E' una firma topologica: non dipende dalla lingua. Non vede la bibliografia,
#    che non e' puntata da nessuno.
# ---------------------------------------------------------------------------
MIN_SORGENTI = 3          # quante sezioni diverse devono puntare alla stessa
QUOTA_RITORNI = 0.6       # frazione di quelle a cui la sezione ripunta
MIN_COPPIE = 4            # coppie richiamo/backlink nello stesso documento
MIN_COPPIE_SEPARATE = 4   # coppie per riconoscere un apparato per capitolo
RE_NOME_NOTE = re.compile(
    r"(?:^|[_\-.])(ftn\d*|footnotes?|endnotes?|notes?)(?:[_\-.]|$)", re.I)
RE_NOME_INDICE = re.compile(
    r"(?:^|[_\-.])(index|indices?|indice|indici|toc)(?:[_\-.]|$)", re.I)
RE_NOME_BIBLIOGRAFIA = re.compile(
    r"(?:^|[_\-.])(bibliograph(?:y|ie|ia)|references?)(?:[_\-.]|$)", re.I)


def _ruolo_apparato_esplicito(sezione: Sezione,
                              lingua: str | None) -> str | None:
    """Ruolo non narrativo dichiarato senza inferirlo dal grafo.

    Il grafo documento-documento non sa orientare da solo una relazione
    reciproca: note e indice analitico puntano al corpo, ma puntano anche fra
    loro. Prima di contare le sorgenti scartiamo quindi gli apparati che
    l'editore ha gia' reso riconoscibili nel titolo, nelle dichiarazioni o nel
    nome del file. I ``noteref`` locali non entrano qui: descrivono il richiamo
    dentro un capitolo, non il documento che lo contiene.
    """
    dichiarati = {
        R.DA_EPUB_TYPE[token]
        for token in sezione.epub_type_documento
        if token in R.DA_EPUB_TYPE
    }
    dichiarati |= {
        R.DA_ARIA[token]
        for token in sezione.ruoli_aria_documento
        if token in R.DA_ARIA
    }
    if len(dichiarati) == 1:
        return next(iter(dichiarati))
    ruolo_titolo, _ = R.per_titolo(sezione.titolo, lingua)
    if ruolo_titolo:
        return ruolo_titolo
    if RE_NOME_NOTE.search(sezione.nome):
        return R.NOTA
    if RE_NOME_INDICE.search(sezione.nome):
        return R.INDICE_ANALITICO
    if RE_NOME_BIBLIOGRAFIA.search(sezione.nome):
        return R.BIBLIOGRAFIA
    return None


def _coppie_reciproche(fonte: Sezione, destinazione: Sezione) -> int:
    """Quante coppie di ancore fanno davvero fonte:A ↔ destinazione:B."""
    andata = {(c.origine_id, c.destinazione_id)
              for c in fonte.collegamenti
              if c.destinazione_href == destinazione.href
              and c.origine_id and c.destinazione_id}
    ritorno = {(c.origine_id, c.destinazione_id)
               for c in destinazione.collegamenti
               if c.destinazione_href == fonte.href
               and c.origine_id and c.destinazione_id}
    return sum(1 for origine, arrivo in andata
               if (arrivo, origine) in ritorno)


def da_grafo(libro: Libro) -> list[Voto]:
    voti = []
    per_href = {s.href: s for s in libro.sezioni}
    sorgenti: dict[str, set] = defaultdict(set)
    uscenti: dict[str, set] = defaultdict(set)
    for s in libro.sezioni:
        for t in s.link_esterni:
            sorgenti[t].add(s.href)
            uscenti[s.href].add(t)

    ruoli_espliciti = {
        s.href: _ruolo_apparato_esplicito(s, libro.lingua)
        for s in libro.sezioni
    }
    ruoli_da_escludere_come_sorgenti = R.NON_CERCABILI | {R.NOTA}

    for bersaglio, tutte_le_sorgenti in sorgenti.items():
        destinazione = per_href[bersaglio]
        # Un indice o una bibliografia bidirezionale possono avere la stessa
        # topologia delle note. Se il bersaglio e' gia' esplicito, il grafo non
        # ha motivo di contraddire quel segnale piu' informativo.
        if ruoli_espliciti[bersaglio] in R.NON_CERCABILI:
            continue
        # Contano soltanto sorgenti che possono essere testo. Senza questo
        # orientamento, la terna note + indice analitico + sommario fa apparire
        # ogni capitolo come una sezione di note richiamata da tre documenti.
        chi = {
            href for href in tutte_le_sorgenti
            if ruoli_espliciti[href] not in ruoli_da_escludere_come_sorgenti
        }
        if not chi:
            continue
        if len(chi) >= MIN_SORGENTI:
            ritorni = uscenti[bersaglio] & chi
            richiesti = max(2, math.ceil(len(chi) * QUOTA_RITORNI))
            if len(ritorni) < richiesti:
                # `ceil` e' intenzionale: 60% di tre significa due, non uno.
                continue
            peso = 3.5 if len(chi) >= 8 else 2.5
            voti.append(Voto(
                bersaglio, R.NOTA, peso,
                f"{len(chi)} sezioni la richiamano, {len(ritorni)} ritorni",
            ))
            for h in chi:
                voti.append(Voto(h, R.CORPO, 0.8,
                                 "richiama una sezione di note"))
            continue

        # Alcuni editori creano un file di note distinto per ogni capitolo. Con
        # una o due sorgenti la topologia a livello di documenti e' simmetrica:
        # da sola non puo' dire quale lato contenga le note. La orientiamo solo
        # quando esistono coppie di ancore esattamente reciproche e l'apparato e'
        # senza titolo (oppure si dichiara nota), piu' piccolo e piu' denso di
        # link del testo. In assenza di questi vincoli e' un rimando ambiguo.
        coppie = {h: _coppie_reciproche(per_href[h], destinazione) for h in chi}
        totale_coppie = sum(coppie.values())
        caratteri_fonti = sum(per_href[h].caratteri for h in chi) or 1
        densita_fonti = totale_coppie / caratteri_fonti
        densita_destinazione = totale_coppie / max(1, destinazione.caratteri)
        ruolo_titolo, _ = R.per_titolo(destinazione.titolo, libro.lingua)
        orientabile = not destinazione.titolo or ruolo_titolo == R.NOTA
        nome_note = bool(RE_NOME_NOTE.search(destinazione.nome))
        minimo_coppie = 1 if nome_note or ruolo_titolo == R.NOTA \
            else MIN_COPPIE_SEPARATE
        if (totale_coppie < minimo_coppie
                or not all(coppie.values())
                or not orientabile
                or destinazione.caratteri >= caratteri_fonti
                or densita_destinazione < densita_fonti * 1.5):
            continue
        voti.append(Voto(
            bersaglio, R.NOTA, 3.5 if nome_note or ruolo_titolo == R.NOTA else 2.5,
            f"{totale_coppie} coppie richiamo/backlink esatte con "
            f"{len(chi)} sezione/i",
        ))
        for h in chi:
            voti.append(Voto(h, R.CORPO, 0.8,
                             "richiama un apparato di note per capitolo"))

    # Note in fondo allo stesso capitolo: qui la semplice presenza di un link
    # verso un id non basta. Si contano esclusivamente coppie A↔B reciproche.
    for s in libro.sezioni:
        coppie = s.coppie_interne_reciproche
        if len(coppie) >= MIN_COPPIE:
            voti.append(Voto(s.href, R.CORPO, 1.2,
                             f"{len(coppie)} coppie richiamo/backlink interne: "
                             "porta le note in fondo"))
    return voti


# ---------------------------------------------------------------------------
# 3. Il titolo. Banale, e quando c'e' e' il segnale piu' forte.
# ---------------------------------------------------------------------------
def da_titolo(libro: Libro) -> list[Voto]:
    voti = []
    for s in libro.sezioni:
        ruolo, frase = R.per_titolo(s.titolo, libro.lingua)
        if not ruolo:
            continue
        # un titolo dal TOC o da un <h1> vale piu' di uno indovinato altrove
        peso = 3.5 if s.origine_titolo in ("TOC", "h1") else 2.5
        voti.append(Voto(s.href, ruolo, peso,
                         f"titolo «{s.titolo[:40]}» contiene «{frase}»"))
    return voti


# ---------------------------------------------------------------------------
# 4. La forma del contenuto. Non dice cosa il testo significa: dice com'e' fatto.
#    Serve per bibliografia e indice analitico, che nessun altro segnale vede.
# ---------------------------------------------------------------------------
RE_ANNO = re.compile(r"\b(1[5-9]\d{2}|20[0-4]\d)\b")
RE_CIT = re.compile(r"\b(cfr|ibid|ibidem|op\. cit|art\. cit|vol|pp|p\.|ed\.|"
                    r"trad|a cura di)\b", re.I)
RE_NUM = re.compile(r"\b\d+\b")
RE_DIDASCALIA = re.compile(
    r"(?:^|\s)(?:f\s*ig(?:ura)?|figure|abbildung|tavola)\.?\s*\d"
    r"|\btavola\b|\b(?:foto|photo|photograph|fotografia)\b",
    re.I,
)
RE_FIRMA_EDITORIALE_BREVE = re.compile(
    r"(?:\b(?:isbn|copyright|editore|edizioni|publisher|verlag)\b|"
    r"www\.|https?://|\u00a9|all rights reserved)",
    re.I,
)


def da_forma(libro: Libro) -> list[Voto]:
    voti = []
    for s in libro.sezioni:
        ps = [p for p in s.paragrafi if p]
        if len(ps) < 8 or s.caratteri < 400:
            continue
        media = sum(len(p) for p in ps) / len(ps)
        anni = len(RE_ANNO.findall(s.testo)) / max(1, len(ps))
        cit = len(RE_CIT.findall(s.testo)) / max(1, len(ps))
        numeri = len(RE_NUM.findall(s.testo)) / max(1, len(ps))
        corti = sum(1 for p in ps if len(p) < 90) / len(ps)

        # Bibliografia: voci brevi e ripetute, molte date e marche di
        # citazione. La preposizione comune ``in`` non e' una marca: nei testi
        # storici produceva falsi positivi ogni volta che comparivano anche
        # molti anni. Le bibliografie essenziali prive di ``cfr.``, ``pp.`` o
        # simili restano riconoscibili quando le voci sono davvero brevi e
        # quasi tutte datate.
        bibliografia_con_marche = (
            media < 320 and anni > 0.45 and cit > 0.55
        )
        bibliografia_a_voci_brevi = (
            media < 180 and anni > 0.65 and corti > 0.25
        )
        if bibliografia_con_marche or bibliografia_a_voci_brevi:
            voti.append(Voto(s.href, R.BIBLIOGRAFIA, 2.5,
                             f"voci di {media:.0f} car., {anni:.1f} anni e "
                             f"{cit:.1f} marche di citazione per voce"))
        # indice analitico: righe brevissime, tantissimi numeri di pagina
        elif corti > 0.75 and numeri > 1.6 and media < 110:
            voti.append(Voto(s.href, R.INDICE_ANALITICO, 2.5,
                             f"{corti:.0%} righe sotto 90 car., "
                             f"{numeri:.1f} numeri per riga"))
        # note: paragrafi brevi e numerati progressivamente
        elif media < 400 and corti > 0.4 and _numerazione_progressiva(ps):
            voti.append(Voto(s.href, R.NOTA, 2.0,
                             "paragrafi brevi con numerazione progressiva"))
        # testo discorsivo: e' il caso normale, e va detto perche' fa da contrappeso
        elif media > 450:
            voti.append(Voto(s.href, R.CORPO, 1.5,
                             f"paragrafi discorsivi, {media:.0f} car. di media"))
    return voti


def _numerazione_progressiva(paragrafi: list[str], minimo: int = 6) -> bool:
    """I paragrafi cominciano con 1, 2, 3...? E' la firma di un elenco di note."""
    numeri = []
    for p in paragrafi:
        m = re.match(r"^\[?(\d{1,4})[\]\.\)\s]", p)
        if m:
            numeri.append(int(m.group(1)))
    if len(numeri) < minimo:
        return False
    crescenti = sum(1 for a, b in zip(numeri, numeri[1:]) if b == a + 1)
    return crescenti >= len(numeri) * 0.6


# ---------------------------------------------------------------------------
# 5. La posizione nello spine, e `linear="no"`.
#    Gratis, indipendente dalla lingua, e da sola non decide mai niente: pesa poco
#    apposta. La bibliografia sta in fondo, il copyright all'inizio — ma «in fondo»
#    c'e' anche l'ultimo capitolo.
# ---------------------------------------------------------------------------
def da_posizione(libro: Libro) -> list[Voto]:
    voti = []
    n = len(libro.sezioni)
    if n < 4:
        return voti
    for s in libro.sezioni:
        q = s.indice / (n - 1)
        testo = s.testo or ""
        ruolo_testo_breve, frase_testo_breve = R.per_titolo(
            testo if s.caratteri < 700 else None, libro.lingua)
        testo_normalizzato = R.normalizza(testo).strip()
        frase_normalizzata = R.normalizza(frase_testo_breve or "").strip()
        intestazione_testuale = (
            ruolo_testo_breve in {R.CORPO, R.SOGLIA, R.APPENDICE}
            and bool(frase_normalizzata)
            and (testo_normalizzato == frase_normalizzata
                 or testo_normalizzato.startswith(frase_normalizzata + " "))
        )
        didascalia = bool(RE_DIDASCALIA.search(testo))
        nome_frontespizio_iniziale = (
            s.indice <= 3
            and s.caratteri < 700
            and R.nome_file_frontespizio(s.nome)
        )
        # Una frase breve e autonoma nel frontmatter e' verosimilmente
        # un'epigrafe o una citazione. Mantenerla e' coerente con la politica
        # conservativa: in caso di dubbio il testo non viene perso. Le firme
        # editoriali impediscono che ISBN, URL e colophon passino da qui.
        frase_breve = (
            20 <= s.caratteri <= 300
            and len(testo.split()) >= 4
            and bool(re.search(
                r"(?:[^\W\d_]{2}\.|[!?\u2026])(?:\s|$)", testo,
                re.I,
            ))
            and not RE_FIRMA_EDITORIALE_BREVE.search(testo)
        )
        contenuto_breve = (
            didascalia or frase_breve
            or intestazione_testuale
        )
        if not s.linear:
            voti.append(Voto(s.href, R.NOTA, 1.0,
                             'spine linear="no": materiale ausiliario'))
        if nome_frontespizio_iniziale:
            voti.append(Voto(
                s.href, R.PARATESTO, 2.0,
                "nome convenzionale di frontespizio nelle prime posizioni",
            ))
        elif q <= 0.08 and s.caratteri < 3000 and not contenuto_breve:
            # Nel margine iniziale una sezione breve e priva di firme positive
            # di contenuto e' normalmente frontespizio, collana o biografia.
            voti.append(Voto(s.href, R.PARATESTO, 1.2,
                             "in testa al libro e molto breve"))
        elif (s.caratteri < 700 and len(s.paragrafi) <= 2
              and not contenuto_breve
              and ((s.titolo
                    and R.normalizza(s.testo).strip()
                    == R.normalizza(s.titolo).strip())
                   or (not s.titolo and s.caratteri < 200))):
            # Occhielli e pagine di divisione fra le parti sono davvero un
            # titolo e nient'altro. La sola brevita', o la presenza di un
            # titolo seguito da contenuto, non basta: epigrafi, didascalie e
            # brevi passaggi dell'opera possono occupare un XHTML autonomo.
            voti.append(Voto(s.href, R.PARATESTO, 0.8,
                             f"sezione di {s.caratteri} caratteri: occhiello o divisore"))
        if q >= 0.88:
            voti.append(Voto(s.href, R.BIBLIOGRAFIA, 0.6, "in fondo al libro",
                             conferma=True))
            voti.append(Voto(s.href, R.INDICE_ANALITICO, 0.4, "in fondo al libro",
                             conferma=True))
    return voti


TUTTI = (da_dichiarazioni, da_grafo, da_titolo, da_forma, da_posizione)
