"""Mette insieme i voti dei segnali e produce ruolo, confidenza, prove.

Le tre proprieta' che distinguono questo da un mucchio di euristiche dentro un
`if`, e che sono il motivo per cui vale la pena farne una libreria:

1. **la decisione porta con se' il perche'** — `prove` elenca i segnali che hanno
   votato, in parole leggibili. Si puo' sempre chiedere «perche' hai deciso
   cosi'?» e ottenere una risposta;
2. **la confidenza e' dichiarata**, quindi si sa dove non fidarsi. Sotto una
   soglia il ruolo diventa `incerto`, che e' un'informazione, non un fallimento;
3. **la correzione umana vince su tutto** e resta: `override` ha peso infinito.

Nessun segnale decide da solo. E' misurato: `epub:type` compare nel 4% dei libri
veri, il grafo dei link riconosce le note in circa un terzo, il vocabolario tace
quando il titolo manca.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import ruoli as R
from . import segnali as S
from .epub_safety import EpubSafetyLimits
from .lettura import Libro, leggi

# Sotto questa confidenza il ruolo si dichiara incerto invece di indovinare.
SOGLIA_INCERTO = 0.34
# Se il ruolo piu' votato e' `corpo` ma con poco margine, si tiene comunque
# `corpo`: e' il caso di gran lunga piu' frequente e sbagliarlo costa di piu'.


@dataclass
class Esito:
    href: str
    indice: int
    titolo: str | None
    caratteri: int
    ruolo: str
    confidenza: float
    prove: list[str] = field(default_factory=list)
    punteggi: dict = field(default_factory=dict)
    override: bool = False
    voti: list[dict] = field(default_factory=list)

    @property
    def nome(self) -> str:
        return self.href.rsplit("/", 1)[-1]

    @property
    def cercabile(self) -> bool:
        """Alias compatibile: usa `include_as_main_text` nel nuovo codice."""
        return self.include_as_main_text

    @property
    def uso(self) -> str:
        return R.uso(self.ruolo)

    @property
    def include_as_main_text(self) -> bool:
        return self.ruolo in R.CERCABILI

    def __repr__(self) -> str:
        return (f"<{self.nome} {self.ruolo} {self.confidenza:.0%} "
                f"{self.caratteri} car.>")


@dataclass
class Analisi:
    libro: Libro
    sezioni: list[Esito] = field(default_factory=list)
    errori_segnali: list[str] = field(default_factory=list)

    @property
    def errore(self):
        return self.libro.errore

    def per_ruolo(self) -> dict[str, list[Esito]]:
        out = defaultdict(list)
        for s in self.sezioni:
            out[s.ruolo].append(s)
        return dict(out)

    def caratteri_per_ruolo(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for s in self.sezioni:
            out[s.ruolo] += s.caratteri
        return dict(out)

    def incerte(self) -> list[Esito]:
        """Le sezioni su cui il classificatore non si sbilancia: sono quelle da
        far vedere a una persona, e sono poche per costruzione."""
        return [s for s in self.sezioni
                if s.ruolo == R.INCERTO or s.confidenza < 0.5]

    def da_indicizzare(self, includi_note: bool = False) -> list[Esito]:
        """Sezioni incluse dalla politica standard, nell'ordine dello spine."""
        usi = {R.TESTO_PRINCIPALE}
        if includi_note:
            usi.add(R.SU_RICHIESTA)
        return [s for s in self.sezioni if s.uso in usi]


def analizza(percorso: Path | str, override: dict[str, str] | None = None,
             limiti_sicurezza: EpubSafetyLimits | None = None) -> Analisi:
    """Legge un EPUB e assegna un ruolo a ogni sezione.

    `override`: {href o nome del file: ruolo} — le correzioni umane, che vincono
    su qualunque segnale e non vengono mai discusse.
    """
    libro = leggi(percorso, limiti_sicurezza=limiti_sicurezza)
    a = Analisi(libro=libro)
    if libro.errore:
        return a

    voti: dict[str, list[S.Voto]] = defaultdict(list)
    voti_spiegabili: dict[str, list[dict]] = defaultdict(list)
    for segnale in S.TUTTI:
        try:
            for v in segnale(libro):
                voti[v.href].append(v)
                voti_spiegabili[v.href].append({
                    "segnale": segnale.__name__.removeprefix("da_"),
                    "ruolo": v.ruolo,
                    "presente": 1.0,
                    "peso_legacy": v.peso,
                    "conferma": v.conferma,
                    "prova": v.prova,
                })
        except Exception as e:                    # un segnale rotto non ferma gli altri
            a.errori_segnali.append(f"{segnale.__name__}: {e}")

    override = {k.rsplit("/", 1)[-1]: v for k, v in (override or {}).items()}

    for s in libro.sezioni:
        punteggi: dict[str, float] = defaultdict(float)
        prove: dict[str, list[str]] = defaultdict(list)
        sostenuti: set[str] = set()          # ruoli affermati da un segnale vero
        for v in voti.get(s.href, []):
            punteggi[v.ruolo] += v.peso
            prove[v.ruolo].append(v.prova)
            if not v.conferma:
                sostenuti.add(v.ruolo)
        # un ruolo tenuto in piedi dalle sole conferme non esiste: la posizione
        # rafforza chi ha gia' altri argomenti, non ne inventa
        for ruolo in [r for r in punteggi if r not in sostenuti]:
            del punteggi[ruolo]
            prove.pop(ruolo, None)

        forzato = override.get(s.nome) or override.get(s.href)
        if forzato:
            a.sezioni.append(Esito(s.href, s.indice, s.titolo, s.caratteri,
                                   forzato, 1.0, ["corretto a mano"],
                                   dict(punteggi), override=True,
                                   voti=list(voti_spiegabili.get(s.href, []))))
            continue

        if not punteggi:
            # nessun segnale ha parlato. Una sezione con del testo vero e' quasi
            # sempre corpo: e' il caso piu' frequente, e va detto con poca
            # confidenza invece che dichiarare `incerto` su mezzo libro.
            ruolo = R.CORPO if s.caratteri > 1500 else R.INCERTO
            a.sezioni.append(Esito(s.href, s.indice, s.titolo, s.caratteri,
                                   ruolo, 0.30 if ruolo == R.CORPO else 0.0,
                                   ["nessun segnale"], {},
                                   voti=list(voti_spiegabili.get(s.href, []))))
            continue

        ordinati = sorted(punteggi.items(), key=lambda x: -x[1])
        ruolo, punti = ordinati[0]
        totale = sum(punteggi.values())
        conf = punti / totale if totale else 0.0
        prove_esito = prove.get(ruolo, [])
        if conf < SOGLIA_INCERTO and ruolo != R.CORPO:
            ruolo = R.INCERTO
            riepilogo = ", ".join(
                f"{candidato}={valore:.2f}"
                for candidato, valore in ordinati[:3])
            prove_esito = [
                f"segnali in conflitto sotto la soglia di confidenza: "
                f"{riepilogo}"
            ]
        a.sezioni.append(Esito(s.href, s.indice, s.titolo, s.caratteri, ruolo,
                               round(conf, 3), prove_esito,
                               {k: round(v, 2) for k, v in ordinati},
                               voti=list(voti_spiegabili.get(s.href, []))))
    return a
