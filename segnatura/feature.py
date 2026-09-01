"""Feature spiegabili per la classificazione dei blocchi.

Niente embedding e niente lessico del corpo del libro: le feature descrivono
struttura, forma, posizione e intestazioni, cosi' il modello non impara che un
argomento o un autore equivalgono a un ruolo editoriale.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from . import ruoli as R
from .blocchi import Blocco
from .lettura import Libro, Sezione

RE_ANNO = re.compile(r"\b(1[5-9]\d{2}|20[0-4]\d)\b")
RE_CIT = re.compile(r"\b(cfr|ibid|ibidem|op\. cit|art\. cit|vol|pp|p\.|ed\.|"
                    r"trad|a cura di|works cited|references)\b", re.I)
RE_NUMERO_INIZIALE = re.compile(r"^\s*\[?\d{1,4}[\].)\s]")
RE_TOKEN = re.compile(r"[a-z0-9']+")


def _uno(feature: dict[str, float], famiglia: str, valore) -> None:
    if valore is not None and str(valore):
        feature[f"{famiglia}={valore}"] = 1.0


def _token_feature(feature: dict[str, float], famiglia: str, testo: str,
                   massimo: int = 10):
    for token in RE_TOKEN.findall(R.normalizza(testo).strip())[:massimo]:
        if len(token) > 1:
            feature[f"{famiglia}:{token}"] = 1.0


def estrai_feature(libro: Libro, documento: Sezione, blocco: Blocco,
                   indice_documento: int, documenti: int,
                   indice_globale: int, blocchi_totali: int,
                   ruolo_documento: str | None = None,
                   voti_documento: list[dict] | None = None) -> dict[str, float]:
    """Restituisce un vettore sparso con valori piccoli e nomi leggibili."""
    testo = blocco.testo
    parole = re.findall(r"\w+", testo, re.UNICODE)
    n_parole = max(1, len(parole))
    n_elementi = max(1, blocco.n_elementi)
    f: dict[str, float] = {
        "log_caratteri": min(1.5, math.log1p(blocco.caratteri) / 9.5),
        "log_elementi": min(1.5, math.log1p(n_elementi) / 5.0),
        "posizione_documento": blocco.posizione,
        "posizione_libro": indice_globale / max(1, blocchi_totali - 1),
        "posizione_spine": indice_documento / max(1, documenti - 1),
        "densita_link": min(1.5, blocco.n_link / n_parole * 20),
        "densita_immagini": min(1.5, blocco.n_immagini / n_elementi),
        "densita_numeri": min(1.5, sum(c.isdigit() for c in testo)
                              / max(1, len(testo)) * 12),
        "anni_per_elemento": min(1.5, len(RE_ANNO.findall(testo)) / n_elementi),
        "citazioni_per_elemento": min(1.5, len(RE_CIT.findall(testo))
                                      / n_elementi),
        "quota_maiuscole": min(1.0, sum(c.isupper() for c in testo)
                               / max(1, sum(c.isalpha() for c in testo))),
        "ha_titolo": 1.0 if blocco.titolo else 0.0,
        "linear_no": 0.0 if documento.linear else 1.0,
        "inizia_con_numero": 1.0 if RE_NUMERO_INIZIALE.search(testo) else 0.0,
    }
    _uno(f, "forma", blocco.forma)
    _uno(f, "lingua", (libro.lingua or "?").split("-")[0].lower())
    _uno(f, "livello_titolo", blocco.livello_titolo)
    _uno(f, "ruolo_documento", ruolo_documento)
    # I cinque giudizi deterministici restano colonne separate. Il modello
    # impara quanto fidarsi di ciascuno; non riceve il vecchio peso scelto a
    # mano, percio' `grafo dice nota` non vale automaticamente 3.5 volte altro.
    for voto in voti_documento or []:
        segnale = voto.get("segnale")
        ruolo = voto.get("ruolo")
        if segnale and ruolo:
            suffisso = ":conferma" if voto.get("conferma") else ""
            f[f"segnale_{segnale}={ruolo}{suffisso}"] = 1.0
    if f["posizione_spine"] <= 0.1:
        f["zona_posizionale=inizio"] = 1.0
    elif f["posizione_spine"] >= 0.88:
        f["zona_posizionale=fine"] = 1.0
    else:
        f["zona_posizionale=centro"] = 1.0
    for tipo in blocco.epub_type:
        _uno(f, "epub_type", tipo)
        if tipo in R.DA_EPUB_TYPE:
            _uno(f, "ruolo_dichiarato", R.DA_EPUB_TYPE[tipo])
    for ruolo in blocco.ruoli_aria:
        _uno(f, "aria", ruolo)
        if ruolo in R.DA_ARIA:
            _uno(f, "ruolo_dichiarato", R.DA_ARIA[ruolo])
    ruolo_dom, marcatore_dom = R.per_marcatori_dom(blocco.marcatori_dom)
    if ruolo_dom:
        _uno(f, "segnale_struttura", ruolo_dom)
        _uno(f, "marcatore_dom", marcatore_dom)
    if blocco.titolo:
        ruolo_titolo, _ = R.per_titolo(blocco.titolo, libro.lingua)
        _uno(f, "ruolo_titolo", ruolo_titolo)
        _token_feature(f, "titolo", blocco.titolo)
    _token_feature(f, "nome_file", Path(documento.nome).stem, massimo=6)
    return f


def feature_blocchi(libro: Libro, ruoli_documento: dict[str, str] | None = None,
                    voti_documento: dict[str, list[dict]] | None = None):
    """Itera `(documento, blocco, feature)` nell'ordine di lettura."""
    ruoli_documento = ruoli_documento or {}
    voti_documento = voti_documento or {}
    totale = sum(len(d.blocchi) for d in libro.documenti)
    righe = []
    globale = 0
    for i, documento in enumerate(libro.documenti):
        for blocco in documento.blocchi:
            feature = estrai_feature(
                libro, documento, blocco, i, len(libro.documenti),
                globale, totale, ruoli_documento.get(documento.href),
                voti_documento.get(documento.href),
            )
            righe.append((documento, blocco, feature))
            globale += 1
    # Il contesto e' ancora una feature leggibile, non una correzione nascosta:
    # il modello puo' imparare che una lista dopo "Bibliografia" e' diversa da
    # una lista dentro un capitolo, e il contributo restera' ispezionabile.
    for i, (documento, blocco, feature) in enumerate(righe):
        if i:
            doc_prec, prec, _ = righe[i - 1]
            _uno(feature, "forma_precedente", prec.forma)
            feature["stesso_documento_precedente"] = \
                1.0 if doc_prec.href == documento.href else 0.0
            ruolo, _ = R.per_titolo(prec.titolo, libro.lingua)
            _uno(feature, "ruolo_titolo_precedente", ruolo)
        if i + 1 < len(righe):
            doc_succ, succ, _ = righe[i + 1]
            _uno(feature, "forma_successiva", succ.forma)
            feature["stesso_documento_successivo"] = \
                1.0 if doc_succ.href == documento.href else 0.0
            ruolo, _ = R.per_titolo(succ.titolo, libro.lingua)
            _uno(feature, "ruolo_titolo_successivo", ruolo)
        yield documento, blocco, feature
