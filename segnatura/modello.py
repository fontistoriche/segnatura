"""Piccolo classificatore lineare multiclasse, addestrabile senza dipendenze.

E' una regressione softmax sparsa allenata con SGD. I pesi sono serializzati in
JSON e ogni previsione espone i contributi delle feature, quindi il modello e'
ispezionabile e versionabile insieme alle annotazioni.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Esempio:
    feature: dict[str, float]
    ruolo: str
    peso: float = 1.0


@dataclass
class Predizione:
    ruolo: str
    probabilita: float
    probabilita_per_ruolo: dict[str, float]
    contributi: list[tuple[str, float]] = field(default_factory=list)


class ClassificatoreLineare:
    versione = 1

    def __init__(self, ruoli: list[str] | None = None):
        self.ruoli = list(ruoli or [])
        self.pesi: dict[str, dict[str, float]] = {r: {} for r in self.ruoli}
        self.bias: dict[str, float] = {r: 0.0 for r in self.ruoli}
        self.feature_viste: set[str] = set()
        self.temperatura: float = 1.0

    def _punteggi(self, feature: dict[str, float]) -> dict[str, float]:
        return {ruolo: self.bias.get(ruolo, 0.0) + sum(
            self.pesi.get(ruolo, {}).get(nome, 0.0) * valore
            for nome, valore in feature.items()) for ruolo in self.ruoli}

    def probabilita(self, feature: dict[str, float]) -> dict[str, float]:
        if not self.ruoli:
            return {}
        punteggi = self._punteggi(feature)
        temperatura = max(0.05, self.temperatura)
        punteggi = {r: v / temperatura for r, v in punteggi.items()}
        massimo = max(punteggi.values())
        esponenziali = {r: math.exp(v - massimo) for r, v in punteggi.items()}
        totale = sum(esponenziali.values())
        return {r: v / totale for r, v in esponenziali.items()}

    def predici(self, feature: dict[str, float], n_contributi: int = 6) -> Predizione:
        probabilita = self.probabilita(feature)
        if not probabilita:
            raise ValueError("il modello non e' addestrato")
        ordinati = sorted(probabilita.items(), key=lambda x: -x[1])
        ruolo, confidenza = ordinati[0]
        alternativa = ordinati[1][0] if len(ordinati) > 1 else ruolo
        contributi = []
        for nome, valore in feature.items():
            delta = (self.pesi[ruolo].get(nome, 0.0)
                     - self.pesi[alternativa].get(nome, 0.0)) * valore
            if delta:
                contributi.append((nome, round(delta, 5)))
        contributi.sort(key=lambda x: -abs(x[1]))
        return Predizione(ruolo, confidenza, dict(ordinati),
                          contributi[:n_contributi])

    def addestra(self, esempi: list[Esempio], epoche: int = 100,
                 tasso: float = 0.08, regolarizzazione: float = 0.0005,
                 seme: int = 42) -> dict:
        if not esempi:
            raise ValueError("nessun esempio annotato")
        self.ruoli = sorted({e.ruolo for e in esempi})
        self.pesi = {r: {} for r in self.ruoli}
        self.bias = {r: 0.0 for r in self.ruoli}
        self.feature_viste = {f for e in esempi for f in e.feature}
        frequenze = Counter(e.ruolo for e in esempi)
        massimo = max(frequenze.values())
        peso_classe = {r: math.sqrt(massimo / n) for r, n in frequenze.items()}
        rng = random.Random(seme)
        dati = list(esempi)
        perdita = 0.0
        for epoca in range(epoche):
            rng.shuffle(dati)
            eta = tasso / math.sqrt(1.0 + epoca * 0.08)
            perdita = 0.0
            for esempio in dati:
                prob = self.probabilita(esempio.feature)
                perdita -= math.log(max(1e-12, prob[esempio.ruolo]))
                moltiplicatore = esempio.peso * peso_classe[esempio.ruolo]
                for ruolo in self.ruoli:
                    errore = (prob[ruolo] - (1.0 if ruolo == esempio.ruolo else 0.0))
                    errore *= moltiplicatore
                    self.bias[ruolo] -= eta * errore
                    pesi = self.pesi[ruolo]
                    for nome, valore in esempio.feature.items():
                        vecchio = pesi.get(nome, 0.0)
                        nuovo = vecchio - eta * (errore * valore
                                                 + regolarizzazione * vecchio)
                        if abs(nuovo) > 1e-12:
                            pesi[nome] = nuovo
        corretti = sum(self.predici(e.feature).ruolo == e.ruolo for e in esempi)
        return {"esempi": len(esempi), "ruoli": dict(frequenze),
                "feature": len(self.feature_viste),
                "perdita_media": round(perdita / len(esempi), 6),
                "accuratezza_training": round(corretti / len(esempi), 6)}

    def calibra(self, esempi: list[Esempio]) -> dict:
        """Sceglie una temperatura su dati separati minimizzando la log-loss."""
        if not esempi:
            return {"temperatura": self.temperatura, "log_loss": None}
        candidati = [0.5 + i * 0.05 for i in range(51)]
        migliore = (float("inf"), self.temperatura)
        originale = self.temperatura
        for temperatura in candidati:
            self.temperatura = temperatura
            perdita = -sum(math.log(max(1e-12,
                                         self.probabilita(e.feature).get(e.ruolo, 1e-12)))
                           for e in esempi) / len(esempi)
            if perdita < migliore[0]:
                migliore = (perdita, temperatura)
        self.temperatura = migliore[1]
        return {"temperatura": round(self.temperatura, 4),
                "log_loss": round(migliore[0], 6),
                "temperatura_precedente": originale}

    def salva(self, percorso: Path | str):
        dati = {"versione": self.versione, "ruoli": self.ruoli,
                "bias": self.bias, "pesi": self.pesi,
                "feature": sorted(self.feature_viste),
                "temperatura": self.temperatura}
        Path(percorso).write_text(json.dumps(dati, ensure_ascii=False,
                                             separators=(",", ":")),
                                  encoding="utf-8")

    @classmethod
    def carica(cls, percorso: Path | str) -> "ClassificatoreLineare":
        dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
        if dati.get("versione") != cls.versione:
            raise ValueError(f"versione modello non supportata: {dati.get('versione')}")
        modello = cls(dati["ruoli"])
        modello.bias = {k: float(v) for k, v in dati["bias"].items()}
        modello.pesi = {r: {k: float(v) for k, v in pesi.items()}
                        for r, pesi in dati["pesi"].items()}
        modello.feature_viste = set(dati.get("feature", []))
        modello.temperatura = float(dati.get("temperatura", 1.0))
        return modello
