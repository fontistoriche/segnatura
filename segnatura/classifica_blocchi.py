"""Classificazione dei blocchi: vincoli certi, modello opzionale, fallback.

Le dichiarazioni locali (`epub:type`/ARIA) sono vincoli e non vengono annullate
dal modello. In loro assenza il modello addestrato puo' prevalere; senza modello
si eredita prudentemente il ruolo del documento, conservando la provenienza
della decisione.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ruoli as R
from .block_rules import (BlockRuleThresholds, ContextualRuleContext,
                          DEFAULT_THRESHOLDS, MarginalRuleContext,
                          RuleDecision, match_contextual_rule,
                          match_marginal_rule)
from .blocchi import Blocco
from .classifica import Analisi
from .feature import feature_blocchi
from .lettura import Sezione
from .modello import ClassificatoreLineare

RE_NOME_NAVIGAZIONE = re.compile(
    r"(?:^|[_\-.])(index|indices?|indice|indici|toc)(?:[_\-.]|$)", re.I)


@dataclass
class EsitoBlocco:
    blocco: Blocco
    documento: Sezione
    ruolo: str
    confidenza: float
    fonte: str
    prove: list[str] = field(default_factory=list)
    probabilita: dict[str, float] = field(default_factory=dict)
    feature: dict[str, float] = field(default_factory=dict)
    rule_id: str = "fallback"

    @property
    def uso(self) -> str:
        if (self.fonte != "correzione" and self.ruolo == R.PARATESTO
                and not R.paratesto_crediti_editoriali(
                    (self.blocco.testo, self.blocco.titolo))
                and (R.paratesto_cercabile(
                    (self.documento.titolo, self.blocco.titolo),
                    self.blocco.epub_type, self.blocco.ruoli_aria)
                     or R.dedica_breve((self.blocco.testo,))
                     or R.dedica_dom_cercabile(
                         self.blocco.marcatori_dom)
                     or R.epigrafe_dom_cercabile(
                         self.blocco.marcatori_dom)
                     or self.fonte == "struttura_testuale")):
            return R.TESTO_PRINCIPALE
        return R.uso(self.ruolo)

    @property
    def include_as_main_text(self) -> bool:
        return self.uso == R.TESTO_PRINCIPALE


def _dichiarato(blocco: Blocco) -> tuple[str | None, str | None]:
    ruoli = []
    for tipo in blocco.epub_type:
        if tipo in R.DA_EPUB_TYPE:
            ruoli.append(R.DA_EPUB_TYPE[tipo])
    for aria in blocco.ruoli_aria:
        if aria in R.DA_ARIA:
            ruoli.append(R.DA_ARIA[aria])
    if not ruoli:
        return None, None
    conteggi = {ruolo: ruoli.count(ruolo) for ruolo in ruoli}
    massimo = max(conteggi.values())
    candidati = {ruolo for ruolo, n in conteggi.items() if n == massimo}
    # Le semantiche specifiche ereditano spesso anche il contenitore: un
    # ``footnote`` dentro ``chapter`` e un ``copyright-page`` dentro
    # ``introduction`` producono un pareggio. La vecchia iterazione sul set lo
    # risolveva in modo diverso fra processi. La precedenza e' ora fissa e fa
    # vincere la funzione locale specifica sul contenitore generico.
    priorita = (
        R.NOTA, R.BIBLIOGRAFIA, R.INDICE_ANALITICO, R.SOMMARIO,
        R.PARATESTO, R.SOGLIA, R.APPENDICE, R.CORPO,
    )
    ruolo = next((x for x in priorita if x in candidati),
                 sorted(candidati)[0])
    return ruolo, f"epub:type/ARIA locale dichiara {ruolo}"


def _strutturale(blocco: Blocco) -> tuple[str | None, str | None]:
    ruolo, marcatore = R.per_marcatori_dom(blocco.marcatori_dom)
    if ruolo:
        if marcatore == R.MARCATORE_NOTE_NUMERATE_LINKATE:
            return R.NOTA, "contenitore con sequenza [1] [2] [3] e backlink"
        return ruolo, f"classe/id DOM «{marcatore}» indica {ruolo}"
    if R.apparato_note_numerate_linkate(blocco.testo, blocco.n_link):
        return R.NOTA, "sequenza [1] [2] [3] con link di ritorno indica note"
    return None, None


def _from_rule(decision: RuleDecision, block: Blocco, document: Sezione,
               features: dict[str, float]) -> EsitoBlocco:
    return EsitoBlocco(
        block, document, decision.role, decision.confidence,
        decision.source, list(decision.evidence), feature=features,
        rule_id=decision.rule_id)


def classifica_blocchi(analisi: Analisi,
                       modello: ClassificatoreLineare | None = None,
                       soglia_modello: float = 0.45,
                       override: dict[str, str] | None = None,
                       thresholds: BlockRuleThresholds | None = None) \
        -> list[EsitoBlocco]:
    if analisi.errore:
        return []
    esiti_documento = {s.href: s for s in analisi.sezioni}
    ruoli_documento = {s.href: s.ruolo for s in analisi.sezioni}
    voti_documento = {s.href: s.voti for s in analisi.sezioni}
    ruoli_per_indice = {
        s.indice: ruoli_documento.get(s.href)
        for s in analisi.libro.sezioni
    }
    documenti_per_indice = {
        s.indice: s for s in analisi.libro.sezioni
    }
    override = override or {}
    thresholds = thresholds or DEFAULT_THRESHOLDS
    out = []
    for documento, blocco, feature in feature_blocchi(
            analisi.libro, ruoli_documento, voti_documento):
        forzato = (override.get(blocco.id)
                   or override.get(f"{documento.href}#{blocco.id}"))
        if forzato:
            out.append(EsitoBlocco(blocco, documento, forzato, 1.0,
                                   "correzione", ["corretto a mano"],
                                   feature=feature,
                                   rule_id="manual-override"))
            continue
        dichiarato, prova_dichiarazione = _dichiarato(blocco)
        strutturale, prova_struttura = _strutturale(blocco)
        _, marcatore_strutturale = R.per_marcatori_dom(
            blocco.marcatori_dom)
        # ``bodymatter`` e ``chapter`` sono spesso ereditati dal contenitore
        # di tutto l'XHTML. Una classe locale ``fn``/``footnote`` descrive
        # invece la funzione specifica del paragrafo e deve prevalere sul
        # contenitore generico, come gia' accade per epub:type="footnote".
        struttura_specifica_in_corpo = (
            dichiarato == R.CORPO
            and strutturale not in {None, R.CORPO}
        )
        documento_precoce = esiti_documento[documento.href]
        ruolo_titolo_precoce, _ = R.per_titolo(
            documento_precoce.titolo, analisi.libro.lingua)
        # Dentro un vero file di sommario, ``bodymatter`` raggruppa i link ai
        # capitoli: non dichiara che quelle voci siano il corpo del libro.
        # Il titolo documentale esplicito del TOC governa quindi il gruppo.
        raggruppamento_in_sommario = (
            dichiarato == R.CORPO
            and documento_precoce.ruolo in {R.SOMMARIO, R.INDICE_ANALITICO}
            and ruolo_titolo_precoce == documento_precoce.ruolo
        )
        if (dichiarato and not struttura_specifica_in_corpo
                and not raggruppamento_in_sommario):
            out.append(EsitoBlocco(blocco, documento, dichiarato, 0.99,
                                   "dichiarazione", [prova_dichiarazione],
                                   feature=feature,
                                   rule_id="local-semantic-declaration"))
            continue

        # Alcune conversioni EPUB 2 riusano ``titlePage`` come stile grafico
        # per una battuta, una citazione o perfino l'intero XHTML di un
        # capitolo. Il token e' semantico soltanto quando descrive davvero una
        # pagina di titolo: non deve espellere prosa che il documento riconosce
        # gia' come corpo. La soglia copre anche i documenti fusi in un unico
        # blocco heading+prosa, dove ``len(blocchi)`` da solo non basta.
        falso_titlepage_in_corpo = (
            strutturale == R.PARATESTO
            and (marcatore_strutturale in {"titlepage", "title-page"}
                 or bool(re.fullmatch(
                     r"titlepage\d+", marcatore_strutturale or "")))
            and esiti_documento[documento.href].ruolo == R.CORPO
            and (len(documento.blocchi) > 1 or blocco.caratteri >= 600)
        )
        marcatori_locali = {
            str(x or "").strip().casefold() for x in blocco.marcatori_dom
        }
        dedication_con_epigrafe_testuale = (
            strutturale == R.PARATESTO
            and marcatore_strutturale == "dedication"
            and R.epigrafe_dom_cercabile(blocco.marcatori_dom)
        )
        epigrafe_con_colophon_decorativo = (
            strutturale == R.PARATESTO
            and marcatore_strutturale == "colophon"
            and blocco.caratteri <= 500
            and blocco.n_link == 0
            and bool({"righttext", "right"} & marcatori_locali)
            and "allcentro" not in marcatori_locali
        )
        colophon_decorativo_in_bibliografia = (
            strutturale == R.PARATESTO
            and marcatore_strutturale == "colophon"
            and esiti_documento[documento.href].ruolo == R.BIBLIOGRAFIA
            and esiti_documento[documento.href].confidenza >= .80
            and "bib" in marcatori_locali
        )
        falso_colophon = (epigrafe_con_colophon_decorativo
                           or colophon_decorativo_in_bibliografia)
        if (strutturale and not falso_titlepage_in_corpo
                and not falso_colophon
                and not dedication_con_epigrafe_testuale):
            out.append(EsitoBlocco(blocco, documento, strutturale, 0.95,
                                   "struttura", [prova_struttura],
                                   feature=feature,
                                   rule_id="local-structural-marker"))
            continue

        # Una nota editoriale di provenienza puo' introdurre la pagina
        # titolare della raccolta da cui il testo e' tratto. La frase e'
        # troppo generica per valere da sola: si richiedono insieme brevita'
        # e un blocco successivo con marcatore titolare esplicito nello stesso
        # XHTML. Vale anche nelle antologie, dove una pagina titolare interna
        # puo' legittimamente trovarsi lontano dai margini del volume.
        successivo = (
            documento.blocchi[blocco.indice + 1]
            if blocco.indice + 1 < len(documento.blocchi) else None
        )
        ruolo_successivo, _ = _strutturale(successivo) if successivo else (None, None)
        rimando_raccolta = (
            blocco.caratteri <= 300
            and blocco.n_link == 0
            and ruolo_successivo == R.PARATESTO
            and R.rimando_editoriale_a_raccolta((blocco.testo,))
        )
        if rimando_raccolta:
            out.append(EsitoBlocco(
                blocco, documento, R.PARATESTO, 0.98, "struttura",
                ["rimando editoriale breve seguito dalla pagina titolare "
                 "della raccolta"],
                feature=feature,
                rule_id="editorial-collection-reference",
            ))
            continue

        # In alcune esportazioni l'heading dell'apparato porta la classe
        # specifica ``noteh``, mentre i paragrafi successivi hanno soltanto la
        # classe generica ``note``. Il segmentatore conserva pero' su tutti
        # quei blocchi il titolo tipografico esatto ``N OTE``. La combinazione
        # fra heading strutturale precedente e titolo ereditato e' una prova
        # locale forte: propaga NOTA fino al prossimo heading, senza rendere
        # semanticamente significativa ogni classe CSS chiamata ``note``.
        titolo_norm = R.normalizza(blocco.titolo or "").strip()
        continuazione_noteh = (
            titolo_norm in {"nota", "note", "notes", "n ota", "n ote", "n otes"}
            and any(
                "noteh" in {
                    str(x or "").strip().casefold()
                    for x in precedente.marcatori_dom
                }
                for precedente in documento.blocchi[:blocco.indice]
                if (R.normalizza(precedente.titolo or "").strip()
                    == titolo_norm)
            )
        )
        if continuazione_noteh:
            out.append(EsitoBlocco(
                blocco, documento, R.NOTA, 0.95, "struttura",
                ["titolo ereditato da heading DOM «noteh»"],
                feature=feature,
                rule_id="inherited-note-heading",
            ))
            continue

        if epigrafe_con_colophon_decorativo:
            out.append(EsitoBlocco(
                blocco, documento, R.PARATESTO, 0.98,
                "struttura_testuale",
                ["colophon grafico con testo breve allineato a destra: epigrafe"],
                feature=feature,
                rule_id="decorative-colophon-epigraph",
            ))
            continue

        # Le tavole fuori testo vengono spesso spezzate in un XHTML per
        # immagine. Posizione, brevita' e singleton fanno allora sembrare la
        # didascalia un occhiello/paratesto, anche se l'editore ne dichiara la
        # funzione con un elemento o una classe esatti. E' contenuto
        # informativo ricercabile e resta testo; firme legali/editoriali non
        # sono coperte da questa regola.
        didascalia_testuale = (
            (blocco.forma == "didascalia"
             or bool({"didascalia", "caption", "figcaption"}
                     & marcatori_locali))
            and 10 <= blocco.caratteri <= 1_500
            and not R.paratesto_crediti_editoriali(
                (blocco.testo, blocco.titolo))
        )
        if didascalia_testuale:
            out.append(EsitoBlocco(
                blocco, documento, R.CORPO, 0.98,
                "struttura_testuale",
                ["elemento/classe DOM di didascalia: testo informativo"],
                feature=feature,
                rule_id="informative-caption",
            ))
            continue

        ruolo_titolo_preliminare, _ = R.per_titolo(
            blocco.titolo, analisi.libro.lingua)
        nome_generico_calibre = bool(re.match(
            r"^index[_\-.]+split[_\-.]*\d+\.(?:x?html?|htm)$",
            documento.nome,
            re.I,
        ))
        nome_navigazione = (
            bool(RE_NOME_NAVIGAZIONE.search(documento.nome))
            and not nome_generico_calibre
        )
        marginal = match_marginal_rule(MarginalRuleContext(
            book_title=analisi.libro.titolo,
            document_name=documento.nome,
            document_index=documento.indice,
            document_blocks=len(documento.blocchi),
            block_title=blocco.titolo,
            block_text=blocco.testo,
            block_characters=blocco.caratteri,
            block_links=blocco.n_link,
            block_elements=blocco.n_elementi,
            block_markers=frozenset(blocco.marcatori_dom),
            position=feature.get("posizione_libro", 0.0),
            preliminary_title_role=ruolo_titolo_preliminare,
            navigation_filename=nome_navigazione,
            thresholds=thresholds,
        ))
        if marginal is not None:
            out.append(_from_rule(marginal, blocco, documento, feature))
            continue

        ruolo_titolo_contestuale, frase = R.per_titolo(
            blocco.titolo, analisi.libro.lingua)
        documento_esito = esiti_documento[documento.href]
        ruolo_titolo_documento, _ = R.per_titolo(
            documento_esito.titolo, analisi.libro.lingua)
        documento_forte = (
            documento_esito.override
            or (ruolo_titolo_documento == documento_esito.ruolo
                and documento_esito.ruolo not in {R.CORPO, R.INCERTO})
            or (documento_esito.ruolo == R.PARATESTO
                and documento.indice <= 3
                and documento.caratteri < 700
                and R.nome_file_frontespizio(documento.nome))
            or any(
                voto.get("segnale") == "dichiarazioni"
                and voto.get("ruolo") == documento_esito.ruolo
                for voto in documento_esito.voti
            )
        )
        # Un XHTML puo' contenere la coda del capitolo e, in fondo, le note.
        # I segnali documentali di forma/grafo descrivono allora una parte
        # reale del file, ma non autorizzano a propagare quel ruolo a ogni
        # blocco. La presenza di heading testuali locali rende esplicita la
        # natura mista del contenitore. Titoli/semantiche forti del documento
        # continuano invece a governare apparati omogenei separati.
        def titolo_testuale_locale(x: Blocco) -> bool:
            ruolo_locale, _ = R.per_titolo(
                x.titolo, analisi.libro.lingua)
            if ruolo_locale in {R.CORPO, R.SOGLIA, R.APPENDICE}:
                return True
            titolo = (x.titolo or "").strip().casefold()
            # I vocabolari non possono elencare ogni heading numerato. La
            # forma 4.5.3 / 11.4 o "Azione 7" e' pero' una firma locale del
            # normale sviluppo di un capitolo, non di una nota ereditata.
            numerato = bool(
                re.match(r"^\d+(?:\.\d+)+\s+\S", titolo)
                or re.match(r"^(?:capitolo|chapter|azione)\s+\d+\b", titolo)
            )
            return numerato or ruolo_locale is None

        ha_titoli_testuali = any(
            titolo_testuale_locale(x) for x in documento.blocchi if x.titolo)
        documento_misto = (
            documento_esito.ruolo not in {R.CORPO, R.INCERTO}
            and not documento_forte and ha_titoli_testuali
        )
        sostegni_indice = {
            voto.get("segnale")
            for voto in documento_esito.voti
            if (voto.get("ruolo") == R.INDICE_ANALITICO
                and not voto.get("conferma"))
        }
        indice_formale_debole = (
            documento_esito.ruolo == R.INDICE_ANALITICO
            and not documento_forte
            and sostegni_indice == {"forma"}
        )
        media_locale = blocco.caratteri / max(1, blocco.n_elementi)
        indice_incompatibile_localmente = (
            indice_formale_debole
            and blocco.caratteri >= thresholds.weak_index_min_characters
            and media_locale >= thresholds.weak_index_min_characters_per_element
        )
        ruoli_strutturali_documento = tuple(
            _strutturale(x)[0] for x in documento.blocchi
        )
        documento_precedente = documenti_per_indice.get(documento.indice - 1)
        contextual = match_contextual_rule(ContextualRuleContext(
            document_role=documento_esito.ruolo,
            document_confidence=documento_esito.confidenza,
            document_strong=documento_forte,
            document_title=documento_esito.titolo,
            document_title_role=ruolo_titolo_documento,
            document_name=documento.nome,
            document_characters=documento.caratteri,
            document_block_shapes=tuple(
                (item.forma, item.caratteri) for item in documento.blocchi),
            previous_document_exists=documento_precedente is not None,
            previous_document_title=(documento_precedente.titolo
                                     if documento_precedente else None),
            previous_document_text=(documento_precedente.testo
                                    if documento_precedente else None),
            previous_document_characters=(documento_precedente.caratteri
                                          if documento_precedente else 0),
            next_document_role=ruoli_per_indice.get(documento.indice + 1),
            adjacent_document_roles=(
                ruoli_per_indice.get(documento.indice - 1),
                ruoli_per_indice.get(documento.indice + 1)),
            block_title=blocco.titolo,
            block_title_role=ruolo_titolo_contestuale,
            block_text=blocco.testo,
            block_form=blocco.forma,
            block_characters=blocco.caratteri,
            block_links=blocco.n_link,
            block_images=blocco.n_immagini,
            block_elements=blocco.n_elementi,
            position_book=feature.get("posizione_libro", 0.0),
            position_spine=feature.get("posizione_spine", 1.0),
            index_supports=frozenset(sostegni_indice),
            structural_document_roles=ruoli_strutturali_documento,
            thresholds=thresholds,
        ))
        # Le regole contestuali devono vedere il significato grezzo del titolo:
        # alcune lo usano per distinguere una sezione discorsiva da un apparato.
        # Soltanto dopo quel tentativo ne ricaviamo il valore di fallback, che
        # puo' essere soppresso per evitare che un heading testuale generico
        # scavalchi un ruolo documentale specifico.
        ruolo_titolo_fallback = ruolo_titolo_contestuale

        # "Parte seconda", "Capitolo 3" o "Epilogo" dentro una bibliografia
        # descrivono l'organizzazione dell'apparato, non lo trasformano in
        # corpo/soglia. Un titolo locale testuale non scavalca quindi un ruolo
        # documentale specifico; per soglie e appendici richiediamo inoltre una
        # firma documentale forte, per non propagare un semplice sospetto.
        titolo_testuale_in_apparato = (
            ruolo_titolo_fallback in {R.CORPO, R.SOGLIA, R.APPENDICE}
            and documento_esito.ruolo in {
                R.NOTA, R.BIBLIOGRAFIA, R.INDICE_ANALITICO, R.SOMMARIO,
            }
            and documento_esito.confidenza >= 0.5
            and not documento_misto
            and (ruolo_titolo_fallback == R.CORPO or documento_forte)
        )
        if titolo_testuale_in_apparato:
            ruolo_titolo_fallback = None
            frase = None
        if contextual is not None:
            out.append(_from_rule(contextual, blocco, documento, feature))
            continue

        previsione = modello.predici(feature) if modello else None
        if previsione and previsione.probabilita >= soglia_modello:
            prove = [f"modello: {nome} ({valore:+.3f})"
                     for nome, valore in previsione.contributi]
            if ruolo_titolo_fallback == previsione.ruolo:
                prove.insert(0, f"titolo contiene «{frase}»")
            out.append(EsitoBlocco(
                blocco, documento, previsione.ruolo,
                round(previsione.probabilita, 4), "modello", prove,
                previsione.probabilita_per_ruolo, feature,
                rule_id="linear-model",
            ))
            continue

        if ruolo_titolo_fallback:
            out.append(EsitoBlocco(
                blocco, documento, ruolo_titolo_fallback, 0.85, "titolo",
                [f"titolo «{blocco.titolo[:60]}» contiene «{frase}»"],
                feature=feature,
                rule_id="block-title-role",
            ))
            continue

        if indice_incompatibile_localmente:
            out.append(EsitoBlocco(
                blocco, documento, R.CORPO, 0.65, "forma_locale",
                [f"indice documentale non propagato: blocco discorsivo, "
                 f"{media_locale:.0f} caratteri per elemento"]
                + documento_esito.prove[:1],
                feature=feature,
                rule_id="weak-index-not-propagated",
            ))
        elif documento_misto:
            out.append(EsitoBlocco(
                blocco, documento, R.CORPO, 0.55, "documento_misto",
                ["ruolo documentale non propagato: XHTML con heading testuali"
                 ] + documento_esito.prove[:1],
                feature=feature,
                rule_id="mixed-document-local-text",
            ))
        else:
            out.append(EsitoBlocco(
                blocco, documento, documento_esito.ruolo,
                min(0.75, max(0.2, documento_esito.confidenza)), "documento",
                ["ruolo ereditato dal documento"] + documento_esito.prove[:1],
                feature=feature,
                rule_id="document-role-inheritance",
            ))
    return out
