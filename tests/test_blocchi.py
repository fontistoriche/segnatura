import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from segnatura import ruoli as R
from segnatura.blocchi import Blocco, estrai_blocchi
from segnatura.classifica import Analisi, Esito, analizza
from segnatura.classifica_blocchi import classifica_blocchi
from segnatura.lettura import Libro, Sezione
from segnatura.modello import ClassificatoreLineare, Esempio, Predizione
from segnatura.ruoli import (APPENDICE, BIBLIOGRAFIA, CORPO,
                             INDICE_ANALITICO, NOTA, PARATESTO, SOGLIA,
                             SOMMARIO)
from segnatura.ruoli import per_titolo
from segnatura.segnali import da_dichiarazioni


class BlocchiTest(unittest.TestCase):
    def _classifica_documento(self, documento, esito_documento, totale=12):
        sezioni = [
            Sezione(f"dummy-{i}.xhtml", i, testo="", blocchi=[])
            for i in range(totale)
        ]
        sezioni[documento.indice] = documento
        esiti = [
            Esito(s.href, s.indice, s.titolo, s.caratteri, CORPO, .75)
            for s in sezioni
        ]
        esiti[documento.indice] = esito_documento
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=sezioni), esiti,
        )
        return classifica_blocchi(analisi)[0]

    def test_confine_dom_footnotes_non_si_fonde_con_il_testo_precedente(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
          <div class="index"><ul><li>Alfa, 1, 2</li><li>Beta, 3</li></ul>
            <div class="footnotes"><p>1. Nota editoriale.</p></div>
          </div>
        </body></html>'''

        blocchi = estrai_blocchi(raw, "indice.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertEqual("Alfa, 1, 2 Beta, 3", blocchi[0].testo)
        self.assertNotIn("footnotes", blocchi[0].marcatori_dom)
        self.assertEqual("1. Nota editoriale.", blocchi[1].testo)
        self.assertIn("footnotes", blocchi[1].marcatori_dom)

    def test_classi_fnote_numerate_separano_le_note_dal_corpo(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
          <h2>Capitolo</h2><p class="indent">Testo principale.</p>
          <p class="fnote"><a id="fn_1">1</a>. Prima nota.</p>
          <p class="fnote1"><a id="fn_2">2</a>. Seconda nota.</p>
        </body></html>'''

        blocchi = estrai_blocchi(raw, "cap.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertEqual("Capitolo Testo principale.", blocchi[0].testo)
        self.assertEqual("1 . Prima nota. 2 . Seconda nota.", blocchi[1].testo)
        self.assertNotIn("fnote", blocchi[0].marcatori_dom)
        self.assertIn("fnote", blocchi[1].marcatori_dom)

    def test_classe_xfootnote_separa_la_nota_locale_dal_corpo(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
          <h2>Capitolo</h2><p>Testo con richiamo <a class="footnote-link"
          href="#n1">1</a>.</p>
          <div class="xfootnote" id="n1"><p>1. Nota locale.</p></div>
        </body></html>'''

        blocchi = estrai_blocchi(raw, "cap.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertIn("Testo con richiamo", blocchi[0].testo)
        self.assertNotIn("xfootnote", blocchi[0].marcatori_dom)
        self.assertEqual("1. Nota locale.", blocchi[1].testo)
        self.assertIn("xfootnote", blocchi[1].marcatori_dom)

    def test_footnote_numerata_indesign_separa_le_note_dal_corpo(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
          <div><p>Testo principale con richiamo.</p>
          <div class="footnote-036"><p class="note_pie_di_pagina">
          1. Prima nota.</p></div>
          <div class="footnote-035"><p class="note_pie_di_pagina_sotto">
          2. Seconda nota.</p></div></div>
        </body></html>'''

        blocchi = estrai_blocchi(raw, "cap.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertEqual("Testo principale con richiamo.", blocchi[0].testo)
        self.assertEqual("1. Prima nota. 2. Seconda nota.", blocchi[1].testo)
        self.assertNotIn("footnote-036", blocchi[0].marcatori_dom)
        self.assertIn("footnote-036", blocchi[1].marcatori_dom)

    def test_classi_fn_prevalgono_sul_bodymatter_ereditato(self):
        raw = b'''<html xmlns:epub="http://www.idpf.org/2007/ops"><body>
          <section epub:type="bodymatter"><p class="indent">Corpo.</p>
          <p class="fn_t">1. Prima nota.</p>
          <p class="fn">2. Seconda nota.</p></section>
          </body></html>'''
        blocchi = estrai_blocchi(raw, "cap.xhtml")
        documento = Sezione(
            "cap.xhtml", 0, testo=" ".join(x.testo for x in blocchi),
            blocchi=blocchi,
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("cap.xhtml", 0, "Capitolo", documento.caratteri,
                   CORPO, 1.0)],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual([CORPO, NOTA], [x.ruolo for x in esiti])
        self.assertEqual("struttura", esiti[1].fonte)
        self.assertIn("fn_t", esiti[1].blocco.marcatori_dom)

    def test_heading_noteh_apre_un_apparato_note_locale(self):
        raw = b'''<html><body>
          <h2>Capitolo 1</h2><p>Testo principale.</p>
          <div><h2 class="noteh">N OTE</h2>
          <p class="note"><a href="#r1">1</a>. Nota locale.</p></div>
        </body></html>'''
        blocchi = estrai_blocchi(raw, "cap.xhtml")
        documento = Sezione(
            "cap.xhtml", 0, testo=" ".join(x.testo for x in blocchi),
            blocchi=blocchi,
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("cap.xhtml", 0, "Capitolo 1", documento.caratteri,
                   CORPO, 1.0)],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual([CORPO, NOTA, NOTA], [x.ruolo for x in esiti])
        self.assertIn("noteh", esiti[1].blocco.marcatori_dom)
        self.assertEqual("struttura", esiti[1].fonte)
        self.assertEqual("struttura", esiti[2].fonte)

    def test_lista_annidata_conserva_testo_del_li_genitore_in_ordine(self):
        raw = b'''<html><body><ul><li>Voce principale:
          <ul><li>sottovoce, 12, 18</li></ul>testo successivo.
          </li></ul></body></html>'''

        blocchi = estrai_blocchi(raw, "indice.xhtml")

        self.assertEqual(1, len(blocchi))
        self.assertEqual(
            "Voce principale: sottovoce, 12, 18 testo successivo.",
            blocchi[0].testo,
        )
        self.assertEqual(3, blocchi[0].n_elementi)
        self.assertEqual(3, len(blocchi[0].frammenti_dom))

    def test_note_conclusive_e_testo_di_soglia_non_apparato(self):
        self.assertEqual((SOGLIA, "note conclusive"),
                         per_titolo("Note conclusive", "it"))

    def test_note_e_riferimenti_precede_la_bibliografia_ulteriore(self):
        self.assertEqual((NOTA, "note"), per_titolo("N OTE", "it"))
        self.assertEqual(
            (NOTA, "note e riferimenti bibliografici"),
            per_titolo("N OTE E RIFERIMENTI BIBLIOGRAFICI", "it"),
        )
        self.assertEqual(
            BIBLIOGRAFIA,
            per_titolo("ULTERIORI RIFERIMENTI BIBLIOGRAFICI", "it")[0],
        )
        self.assertEqual(
            SOMMARIO, per_titolo("P IANO DEL CAPITOLO 7", "it")[0])

    def test_elenco_illustrazioni_e_abbreviazioni_hanno_ruoli_propri(self):
        self.assertEqual(
            SOMMARIO, per_titolo("Elenco delle illustrazioni", "it")[0])
        self.assertEqual(
            INDICE_ANALITICO, per_titolo("Abbreviazioni", "it")[0])
        self.assertEqual(
            SOMMARIO, per_titolo("List of figures", "en")[0])
        self.assertEqual(
            INDICE_ANALITICO, per_titolo("List of abbreviations", "en")[0])

    def test_classe_biblio_con_suffisso_identifica_la_bibliografia(self):
        self.assertEqual(
            (BIBLIOGRAFIA, "biblio-1sp"),
            R.per_marcatori_dom(("testo", "biblio-1sp")),
        )

    def test_catalogo_editore_e_collana_diretta_sono_firme_di_backlist(self):
        self.assertTrue(R.paratesto_backlist((
            "Gli ebook della casa. Il catalogo Fanucci Editore.",
        )))
        self.assertTrue(R.paratesto_backlist((
            "Mimesis Spinoziana. Collana diretta da tre studiosi.",
        )))
        self.assertFalse(R.paratesto_backlist((
            "Il capitolo studia la formazione storica del catalogo.",
        )))

    def test_prosa_interna_breve_senza_segnali_resta_testo(self):
        testo = "La voce geografica descrive il paese e la sua storia. " * 14
        blocco = Blocco(
            "b", "voce.xhtml", 0, "/section[1]", testo, "sezione",
            titolo="Orotelli", n_elementi=3,
        )
        documento = Sezione(
            "voce.xhtml", 7, titolo="Orotelli", testo=testo,
            blocchi=[blocco],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 7, documento.titolo, len(testo),
                  R.INCERTO, 0.0, ["nessun segnale"]),
        )

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("forma_locale", esito.fonte)

    def test_sinossi_in_file_promozionale_non_diventa_corpo(self):
        testo = "Una nuova avventura ricca di mistero e di emozioni. " * 18
        blocco = Blocco(
            "b", "Biblio-promo004.xhtml", 0, "/div[1]", testo, "prosa",
            n_elementi=5,
        )
        documento = Sezione(
            blocco.href, 8, testo=testo, blocchi=[blocco],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 8, None, len(testo), R.INCERTO, 0.0,
                  ["nessun segnale"]),
        )

        self.assertNotEqual(CORPO, esito.ruolo)
        self.assertEqual("documento", esito.fonte)

    def test_pagina_iniziale_composita_seguita_dal_corpo_resta_testo(self):
        testo = (
            "A Elizabeth. Una frase d'epigrafe completa. "
            "Viaggiare fa lavorare l'immaginazione. "
            "Il viaggio che ci e dato e interamente immaginario. "
            "Uomini, bestie, citta e cose: e tutto inventato. " * 4
        )
        blocco = Blocco(
            "b", "apertura.xhtml", 0, "/body[1]", testo, "prosa",
            n_elementi=10,
        )
        documento = Sezione(
            "apertura.xhtml", 1, testo=testo, blocchi=[blocco],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 1, None, len(testo), PARATESTO, .6,
                  ["in testa al libro e molto breve"]),
            totale=20,
        )

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_ulteriori_letture_discorsive_restano_appendice(self):
        testo = "Per approfondire questo tema consiglio alcune opere. " * 80
        blocco = Blocco(
            "b", "appendice.xhtml", 0, "/section[1]", testo, "sezione",
            titolo="Ulteriori letture", n_elementi=10,
        )
        documento = Sezione(
            "appendice.xhtml", 10, titolo="Appendice A - Ulteriori letture",
            testo=testo, blocchi=[blocco],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 10, documento.titolo, len(testo),
                  APPENDICE, 1.0, ["titolo contiene appendice"]),
        )

        self.assertEqual(APPENDICE, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_note_su_un_argomento_dentro_introduzione_restano_testo(self):
        testo = "Gli apici distinguono le stringhe e richiedono attenzione. " * 14
        blocco = Blocco(
            "b", "intro.xhtml", 0, "/section[1]", testo, "sezione",
            titolo="Note sugli apici", n_elementi=3,
        )
        documento = Sezione(
            "intro.xhtml", 3, titolo="Introduzione", testo=testo,
            blocchi=[blocco],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 3, documento.titolo, len(testo),
                  SOGLIA, 1.0, ["titolo contiene introduzione"]),
        )

        self.assertEqual(SOGLIA, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_gruppi_bibliografici_disambiguano_annotazioni_e_fonti(self):
        titolo = "Annotazioni e fonti"
        target = Blocco(
            "target", "fonti.xhtml", 0, "/section[1]",
            "L'autore presenta e commenta estesamente le fonti adottate. " * 25,
            "sezione", titolo=titolo, n_elementi=5,
        )
        voce_1 = Blocco(
            "v1", "fonti.xhtml", 1, "/p[2]", "Rossi, Opera, 1998.",
            "prosa", titolo=titolo, marcatori_dom=("biblio",),
        )
        voce_2 = Blocco(
            "v2", "fonti.xhtml", 2, "/p[3]", "Bianchi, Studio, 2002.",
            "prosa", titolo=titolo, marcatori_dom=("biblio-1sp",),
        )
        documento = Sezione(
            "fonti.xhtml", 9, titolo=titolo,
            testo=" ".join(x.testo for x in (target, voce_1, voce_2)),
            blocchi=[target, voce_1, voce_2],
        )
        esito = self._classifica_documento(
            documento,
            Esito(documento.href, 9, titolo, documento.caratteri,
                  NOTA, 1.0, ["titolo contiene annotazioni"]),
        )

        self.assertEqual(BIBLIOGRAFIA, esito.ruolo)
        self.assertEqual("struttura_documento", esito.fonte)

    def test_heading_e_semantica_locale_separano_i_blocchi(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:epub="http://www.idpf.org/2007/ops"><body>
          <h1>Capitolo</h1><p>Testo principale.</p>
          <aside epub:type="footnote"><p>Una nota.</p></aside>
          </body></html>'''

        blocchi = estrai_blocchi(raw, "cap.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertEqual("Capitolo", blocchi[0].titolo)
        self.assertIn("footnote", blocchi[1].epub_type)
        self.assertNotEqual(blocchi[0].id, blocchi[1].id)

    def test_modello_lineare_impara_e_si_serializza(self):
        esempi = [
            Esempio({"forma=prosa": 1, "log_caratteri": 1}, CORPO),
            Esempio({"forma=prosa": 1, "log_caratteri": .9}, CORPO),
            Esempio({"ruolo_titolo=nota": 1, "densita_link": 1}, NOTA),
            Esempio({"ruolo_titolo=nota": 1, "densita_link": .8}, NOTA),
        ]
        modello = ClassificatoreLineare()
        metriche = modello.addestra(esempi, epoche=120, tasso=.12)
        previsione = modello.predici({"ruolo_titolo=nota": 1, "densita_link": .9})

        self.assertEqual(NOTA, previsione.ruolo)
        self.assertEqual(1.0, metriche["accuratezza_training"])
        self.assertTrue(previsione.contributi)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "modello.json"
            modello.salva(file)
            caricato = ClassificatoreLineare.carica(file)
            self.assertEqual(previsione.ruolo,
                             caricato.predici({"ruolo_titolo=nota": 1,
                                              "densita_link": .9}).ruolo)
            self.assertEqual(1, json.loads(file.read_text())["versione"])

    def test_dichiarazione_sul_blocco_prevale_sul_documento(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "misto.epub"
            with zipfile.ZipFile(epub, "w") as z:
                z.writestr("META-INF/container.xml", """
                  <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                    <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
                  </container>""")
                z.writestr("OEBPS/content.opf", """
                  <package version="3.0" xmlns="http://www.idpf.org/2007/opf">
                    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                      <dc:title>Misto</dc:title><dc:language>it</dc:language>
                    </metadata><manifest><item id="c" href="cap.xhtml"
                    media-type="application/xhtml+xml"/></manifest>
                    <spine><itemref idref="c"/></spine></package>""")
                z.writestr("OEBPS/cap.xhtml", """
                  <html xmlns="http://www.w3.org/1999/xhtml"
                  xmlns:epub="http://www.idpf.org/2007/ops">
                  <head><title>Titolo tecnico</title>
                    <style>body { color: black; }</style></head><body>
                    <h1>Capitolo</h1><p>Testo principale abbastanza lungo.</p>
                    <aside epub:type="footnote"><p>Nota incorporata.</p></aside>
                  </body></html>""")

            a = analizza(epub)
            blocchi = classifica_blocchi(a)

        self.assertNotIn("Titolo tecnico", a.libro.sezioni[0].testo)
        self.assertNotIn("color", a.libro.sezioni[0].testo)
        self.assertEqual(
            "Capitolo Testo principale abbastanza lungo. Nota incorporata.",
            a.libro.sezioni[0].testo,
        )
        self.assertEqual(CORPO, blocchi[0].ruolo)
        self.assertEqual(NOTA, blocchi[1].ruolo)
        self.assertEqual("dichiarazione", blocchi[1].fonte)

    def test_classi_editoriali_esplicite_sono_indizi_strutturali(self):
        casi = [
            (b'''<html><body><div class="footnote"><p>Nota lunga.</p></div>
                 </body></html>''', NOTA, "footnote"),
            (b'''<html><body><div class="preface"><p>Contesto storico.</p></div>
                 </body></html>''', SOGLIA, "preface"),
            (b'''<html><body><div class="occhiello"><h1>Titolo del libro</h1>
                 </div></body></html>''', PARATESTO, "occhiello"),
        ]
        for raw, ruolo, marcatore in casi:
            with self.subTest(marcatore=marcatore):
                blocco = estrai_blocchi(raw, "x.xhtml")[0]
                documento = Sezione("x.xhtml", 0, testo=blocco.testo,
                                    blocchi=[blocco])
                analisi = Analisi(
                    Libro(Path("x.epub"), sezioni=[documento]),
                    [Esito("x.xhtml", 0, None, blocco.caratteri, CORPO, .3)],
                )

                esito = classifica_blocchi(analisi)[0]

                self.assertEqual(ruolo, esito.ruolo)
                self.assertEqual("struttura", esito.fonte)
                self.assertEqual(
                    1.0, esito.feature[f"marcatore_dom={marcatore}"])

    def test_classi_composte_del_frontespizio_sono_paratesto(self):
        casi = (
            "autore-frontespizio",
            "titolo-frontespizio1",
            "titolo-frontespizio-lib",
        )
        for indice, marcatore in enumerate(casi):
            with self.subTest(marcatore=marcatore):
                blocco = Blocco(
                    f"f{indice}", "front.xhtml", indice, f"/p[{indice + 1}]",
                    "AMBROGIO BORSANI" if indice == 0 else "SICILIA",
                    "sezione", marcatori_dom=("story", marcatore),
                )
                documento = Sezione(
                    "front.xhtml", 2, testo=blocco.testo, blocchi=[blocco])
                analisi = Analisi(
                    Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
                    [Esito(documento.href, 2, None, blocco.caratteri,
                           CORPO, .2)],
                )

                esito = classifica_blocchi(analisi)[0]

                self.assertEqual(PARATESTO, esito.ruolo)
                self.assertEqual("struttura", esito.fonte)

    def test_classi_bib_numerate_identificano_la_bibliografia(self):
        blocco = Blocco(
            "b", "bibliografica.xhtml", 0, "/p[1]",
            "ROSSI, Opera, Editore, Milano, 2001.", "prosa",
            titolo="Selezione bibliografica", marcatori_dom=("bib1",),
        )
        documento = Sezione(
            "bibliografica.xhtml", 8, testo=blocco.testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 8, None, blocco.caratteri, CORPO, .3)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(BIBLIOGRAFIA, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_dedica_dom_conserva_ruolo_ma_resta_indicizzabile(self):
        testo = ("Alla mia nipotina Gwenola Guyot per i suoi tredici anni "
                 "Meudon, 25 febbraio 2001")
        blocco = Blocco(
            "d", "dedication.xhtml", 0, "/p[1]", testo, "prosa",
            marcatori_dom=("calibre", "dedica1"),
        )
        documento = Sezione(
            "dedication.xhtml", 3, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 3, None, blocco.caratteri, CORPO, .3)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertTrue(esito.include_as_main_text)

    def test_classe_dedication_conserva_ruolo_e_uso_testuale(self):
        blocco = Blocco(
            "d", "p004_dedication.xhtml", 0, "/p[1]", "A mamma Iride",
            "prosa", marcatori_dom=("calibre3", "dedication", "calibre17"),
        )
        documento = Sezione(
            blocco.href, 3, testo=blocco.testo, blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(
                documento.href, 3, None, blocco.caratteri, CORPO, .75,
            )],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertTrue(esito.include_as_main_text)

    def test_sinossi_editoriale_iniziale_senza_heading_e_paratesto(self):
        titolo = "LA VIA DELLA SETA"
        sinossi = (
            titolo + " Samarcanda e Chang'an sono tappe celebri. "
            "Come arrivarono fin qui gli antichi romani? Cosa sapevano i "
            "cinesi dell'Europa? In questo libro l'autrice ricostruisce "
            "dieci secoli di storia attraverso le scoperte archeologiche. "
            + "Presentazione editoriale. " * 8
        )
        blocco = Blocco("s", "abstract.xhtml", 0, "/p[1]", sinossi,
                        "prosa")
        documento = Sezione("abstract.xhtml", 0, testo=sinossi,
                            blocchi=[blocco])
        corpo_testo = "Testo del capitolo. " * 200
        corpo = Blocco("c", "cap.xhtml", 0, "/p[1]", corpo_testo, "prosa")
        capitolo = Sezione("cap.xhtml", 1, titolo="Capitolo 1",
                           testo=corpo_testo, blocchi=[corpo])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", titolo="La via della seta",
                  sezioni=[documento, capitolo]),
            [Esito(documento.href, 0, None, documento.caratteri,
                   PARATESTO, .75),
             Esito(capitolo.href, 1, capitolo.titolo, capitolo.caratteri,
                   CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_sottotitolo_parte_non_trasforma_bibliografia_in_corpo(self):
        blocco = Blocco("b", "bib.xhtml", 0, "/h2[1]", "Parte seconda",
                        "sezione", titolo="Parte seconda", livello_titolo=2)
        documento = Sezione("bib.xhtml", 0, testo="Parte seconda",
                            blocchi=[blocco])
        libro = Libro(Path("x.epub"), lingua="it", sezioni=[documento])
        analisi = Analisi(libro, [Esito("bib.xhtml", 0, "Bibliografia", 100,
                                       BIBLIOGRAFIA, 1.0)])

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(BIBLIOGRAFIA, esito.ruolo)
        self.assertEqual("documento", esito.fonte)
        self.assertEqual("document-role-inheritance", esito.rule_id)

    def test_ruolo_debole_del_documento_non_contamina_un_xhtml_misto(self):
        corpo = Blocco("c", "misto.xhtml", 0, "/h2[1]", "4.1 Analisi",
                       "sezione", titolo="4.1 Analisi")
        senza_titolo = Blocco("t", "misto.xhtml", 1, "/p[2]",
                              "Testo del capitolo.", "prosa")
        note = Blocco("n", "misto.xhtml", 2, "/h2[2]",
                      "Note 1. Rossi, Opera, 1998.", "sezione",
                      titolo="Note")
        documento = Sezione(
            "misto.xhtml", 0,
            testo=" ".join(x.testo for x in (corpo, senza_titolo, note)),
            blocchi=[corpo, senza_titolo, note],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("misto.xhtml", 0, "4.1 Analisi", documento.caratteri,
                   NOTA, 1.0, ["piu' file la richiamano"],
                   voti=[{"segnale": "grafo", "ruolo": NOTA}])],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual([CORPO, CORPO, NOTA], [x.ruolo for x in esiti])
        self.assertEqual("documento_misto", esiti[1].fonte)
        self.assertEqual("mixed-document-local-text", esiti[1].rule_id)

    def test_file_omogeneo_di_note_puo_ancora_ereditare_il_grafo(self):
        blocchi = [
            Blocco(str(i), "note.xhtml", i, f"/p[{i + 1}]",
                   f"{i + 1}. Nota.", "prosa") for i in range(2)
        ]
        documento = Sezione(
            "note.xhtml", 0, testo=" ".join(x.testo for x in blocchi),
            blocchi=blocchi,
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("note.xhtml", 0, None, documento.caratteri, NOTA, 1.0,
                   ["richiami reciproci"],
                   voti=[{"segnale": "grafo", "ruolo": NOTA}])],
        )

        self.assertEqual(
            [NOTA, NOTA], [x.ruolo for x in classifica_blocchi(analisi)])

    def test_tabelle_numeriche_non_trasformano_prosa_lunga_in_indice(self):
        testo = "Il clima varia secondo latitudine e altitudine. " * 100
        blocco = Blocco("c", "clima.xhtml", 0, "/p[1]", testo, "misto",
                        n_elementi=6)
        documento = Sezione("clima.xhtml", 0, testo=testo,
                            blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(
                "clima.xhtml", 0, "Il clima", len(testo),
                INDICE_ANALITICO, .76,
                ["molte righe brevi e numeri"],
                voti=[{"segnale": "forma", "ruolo": INDICE_ANALITICO,
                       "conferma": False}],
            )],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("forma_locale", esito.fonte)
        self.assertEqual("weak-index-not-propagated", esito.rule_id)

    def test_dedica_nominale_breve_resta_indicizzabile(self):
        blocco = Blocco("d", "d.xhtml", 0, "/p[1]", "A Justine", "prosa")
        documento = Sezione("d.xhtml", 0, testo=blocco.testo,
                            blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("d.xhtml", 0, None, blocco.caratteri,
                   PARATESTO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)

    def test_dedica_a_un_gruppo_con_elenco_resta_indicizzabile(self):
        testo = ("Agli adolescenti della mia tribù: Alejandro, Andrea, "
                 "Nicole, Sabrina, Aristotelis e Achilleas")
        blocco = Blocco("d", "d.xhtml", 0, "/p[1]", testo, "prosa")
        documento = Sezione("d.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("d.xhtml", 0, None, blocco.caratteri, PARATESTO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)

    def test_promozione_editoriale_finale_diventa_paratesto(self):
        corpo = Blocco("c", "x.xhtml", 0, "/p[1]", "Testo " * 400,
                       "prosa")
        promo = Blocco(
            "p", "x.xhtml", 1, "/p[2]",
            "Ti è piaciuto questo libro? Vuoi scoprire nuovi autori? "
            "Iscriverti alla nostra newsletter. Seguici su Facebook.",
            "prosa",
        )
        documento = Sezione(
            "x.xhtml", 0, testo=corpo.testo + " " + promo.testo,
            blocchi=[corpo, promo],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("x.xhtml", 0, None, documento.caratteri, CORPO, .75)],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual(CORPO, esiti[0].ruolo)
        self.assertEqual(PARATESTO, esiti[1].ruolo)
        self.assertEqual("struttura", esiti[1].fonte)

    def test_promozione_sociale_inglese_finale_diventa_paratesto(self):
        corpo = Blocco(
            "c", "promo.xhtml", 0, "/p[1]", "Body text. " * 300,
            "prosa",
        )
        promo = Blocco(
            "p", "promo.xhtml", 1, "/p[2]",
            "Like us on Facebook. Watch us on YouTube. "
            "Subscribe to our newsletter. Shop online.",
            "prosa", posizione=1.0,
        )
        documento = Sezione(
            "promo.xhtml", 9, testo=corpo.testo + " " + promo.testo,
            blocchi=[corpo, promo],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en",
                  sezioni=[Sezione(f"c{i}.xhtml", i) for i in range(9)]
                  + [documento]),
            [Esito(f"c{i}.xhtml", i, None, 1000, CORPO, .75)
             for i in range(9)]
            + [Esito("promo.xhtml", 9, None, documento.caratteri,
                     CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[-1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_scheda_promozionale_finale_con_url_diventa_paratesto(self):
        corpo = Blocco("c", "promo.xhtml", 0, "/p[1]", "Testo " * 300,
                       "prosa")
        promo = Blocco(
            "p", "promo.xhtml", 1, "/p[2]",
            "Avventure di piccole terre. Leggete qui la scheda del romanzo "
            "http://www.editore.example",
            "prosa", posizione=1.0,
        )
        documento = Sezione(
            "promo.xhtml", 9, testo=corpo.testo + " " + promo.testo,
            blocchi=[corpo, promo],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it",
                  sezioni=[Sezione(f"c{i}.xhtml", i) for i in range(9)]
                  + [documento]),
            [Esito(f"c{i}.xhtml", i, None, 1000, CORPO, .75)
             for i in range(9)]
            + [Esito("promo.xhtml", 9, None, documento.caratteri,
                     CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[-1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_rimando_breve_alla_raccolta_prima_del_frontespizio_e_paratesto(self):
        rimando = Blocco(
            "r", "fronte.xhtml", 0, "/p[1]",
            "Questi racconti fanno parte della più ampia raccolta",
            "prosa",
        )
        titolo = Blocco(
            "t", "fronte.xhtml", 1, "/h1[1]",
            "Avventure di piccole terre", "sezione",
            titolo="Avventure di piccole terre",
            marcatori_dom=("titolo-frontespizio-lib",),
        )
        documento = Sezione(
            "fronte.xhtml", 1, testo=rimando.testo + " " + titolo.testo,
            blocchi=[rimando, titolo],
        )
        corpo_testo = "Testo principale. " * 400
        corpo = Blocco("c", "capitolo.xhtml", 0, "/p[1]", corpo_testo,
                       "prosa")
        capitolo = Sezione("capitolo.xhtml", 2, testo=corpo_testo,
                           blocchi=[corpo])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it",
                  sezioni=[Sezione("cover.xhtml", 0), documento, capitolo]),
            [Esito("cover.xhtml", 0, None, 0, PARATESTO, 1.0),
             Esito(documento.href, 1, None, documento.caratteri, CORPO, .2),
             Esito(capitolo.href, 2, "Capitolo", capitolo.caratteri,
                   CORPO, .75)],
        )

        esiti = [x for x in classifica_blocchi(analisi)
                 if x.documento.href == documento.href]

        self.assertEqual([PARATESTO, PARATESTO], [x.ruolo for x in esiti])
        self.assertTrue(all(x.fonte == "struttura" for x in esiti))

    def test_url_senza_invito_promozionale_non_diventa_paratesto(self):
        corpo = Blocco("c", "x.xhtml", 0, "/p[1]", "Testo " * 300,
                       "prosa")
        citazione = Blocco(
            "u", "x.xhtml", 1, "/p[2]",
            "La fonte del documento e' disponibile su "
            "https://archivio.example/documento.",
            "prosa", posizione=1.0,
        )
        documento = Sezione(
            "x.xhtml", 0, testo=corpo.testo + " " + citazione.testo,
            blocchi=[corpo, citazione],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("x.xhtml", 0, None, documento.caratteri, CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[-1]

        self.assertEqual(CORPO, esito.ruolo)

    def test_crediti_editore_non_sono_ringraziamenti_cercabili(self):
        corpo = Blocco("c", "x.xhtml", 0, "/p[1]", "Body " * 300,
                       "prosa")
        crediti = Blocco(
            "e", "x.xhtml", 1, "/p[2]",
            "Publisher's Acknowledgments Acquisitions Editor: A. Rossi. "
            "Copy Editor: B. Bianchi. Production Editor: C. Verdi.",
            "prosa", titolo="Publisher's Acknowledgments",
        )
        documento = Sezione(
            "x.xhtml", 0, testo=corpo.testo + " " + crediti.testo,
            blocchi=[corpo, crediti],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en", sezioni=[documento]),
            [Esito("x.xhtml", 0, None, documento.caratteri, CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertFalse(esito.include_as_main_text)

    def test_referenze_fotografiche_finali_sono_paratesto_protetto(self):
        corpo = Blocco(
            "c", "capitolo.xhtml", 0, "/p[1]", "Testo " * 2_000, "prosa",
        )
        crediti = Blocco(
            "f", "crediti.xhtml", 0, "/section[1]",
            "REFERENZE FOTOGRAFICHE Archivio Fabbri: nn. 1, 2, 3. "
            "Museo di Treviri: n. 4. Collezione privata: nn. 5, 6.",
            "sezione", titolo="REFERENZE FOTOGRAFICHE",
        )
        documento_corpo = Sezione(
            corpo.href, 0, titolo="Capitolo", testo=corpo.testo,
            blocchi=[corpo],
        )
        documento_crediti = Sezione(
            crediti.href, 1, titolo=crediti.titolo, testo=crediti.testo,
            blocchi=[crediti],
        )
        analisi = Analisi(
            Libro(
                Path("x.epub"), lingua="it",
                sezioni=[documento_corpo, documento_crediti],
            ),
            [Esito(
                documento_corpo.href, 0, documento_corpo.titolo,
                documento_corpo.caratteri, CORPO, .75,
            ), Esito(
                documento_crediti.href, 1, documento_crediti.titolo,
                documento_crediti.caratteri, INDICE_ANALITICO, .55,
            )],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual((PARATESTO, "referenze fotografiche"),
                         per_titolo(crediti.titolo, "it"))
        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertEqual(.99, esito.confidenza)
        self.assertFalse(esito.include_as_main_text)

    def test_eula_finale_e_paratesto_legale(self):
        corpo = Blocco("c", "x.xhtml", 0, "/p[1]", "Body " * 300,
                       "prosa")
        eula = Blocco(
            "e", "eula.xhtml", 0, "/section[1]",
            "END USER LICENSE AGREEMENT Go to www.example.com/eula.",
            "sezione", titolo="END USER LICENSE AGREEMENT",
        )
        doc_corpo = Sezione("x.xhtml", 0, testo=corpo.testo,
                            blocchi=[corpo])
        doc_eula = Sezione("eula.xhtml", 1, titolo=eula.titolo,
                           testo=eula.testo, blocchi=[eula])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en",
                  sezioni=[doc_corpo, doc_eula]),
            [Esito("x.xhtml", 0, None, doc_corpo.caratteri, CORPO, .75),
             Esito("eula.xhtml", 1, eula.titolo, doc_eula.caratteri,
                   CORPO, .55)],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertFalse(esito.include_as_main_text)

    def test_biografia_eredita_intestazione_xhtml_precedente(self):
        heading = Blocco(
            "h", "bio-title.xhtml", 0, "/h1[1]", "Notizie sull'autrice",
            "titolo", titolo="Notizie sull'autrice",
        )
        bio = Blocco(
            "b", "bio.xhtml", 0, "/p[1]",
            "L'autrice è nata nel 1977 e ha pubblicato numerosi romanzi. "
            * 20,
            "prosa",
        )
        doc_heading = Sezione(
            "bio-title.xhtml", 0, titolo="Notizie sull'autrice",
            testo=heading.testo, blocchi=[heading],
        )
        doc_bio = Sezione(
            "bio.xhtml", 1, testo=bio.testo, blocchi=[bio],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it",
                  sezioni=[doc_heading, doc_bio]),
            [Esito("bio-title.xhtml", 0, "Notizie sull'autrice",
                   heading.caratteri, PARATESTO, .85),
             Esito("bio.xhtml", 1, None, bio.caratteri, CORPO, .55)],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)
        self.assertFalse(esito.include_as_main_text)

    def test_epigrafe_conserva_il_ruolo_ma_resta_indicizzabile(self):
        blocco = Blocco("e", "e.xhtml", 0, "/p[1]",
                        "Tutto cio che e sottoposto alla forza. Simone Weil",
                        "prosa")
        documento = Sezione("e.xhtml", 0, titolo="Epigrafe",
                            testo=blocco.testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("e.xhtml", 0, "Epigrafe", blocco.caratteri,
                   PARATESTO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)

    def test_epigrafe_dom_con_firma_e_un_vincolo_testuale(self):
        testo = ("Se tu vuoi un amico, addomesticami! "
                 "ANTOINE DE SAINT-EXUPÉRY, Il Piccolo Principe.")
        blocco = Blocco(
            "e", "estratti.xhtml", 0, "/p[1]", testo, "prosa",
            marcatori_dom=("dedication", "extract", "signature"),
        )
        documento = Sezione("estratti.xhtml", 0, testo=testo,
                            blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("estratti.xhtml", 0, None, blocco.caratteri,
                   CORPO, .3)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_colophon_grafico_allineato_a_destra_e_epigrafe_testuale(self):
        testo = "O Germania, udendo i discorsi si ride. Bertolt Brecht"
        blocco = Blocco(
            "e", "esergo.xhtml", 0, "/p[1]", testo, "prosa",
            marcatori_dom=("calibre", "colophon", "righttext", "right"),
        )
        documento = Sezione("esergo.xhtml", 0, testo=testo,
                            blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("esergo.xhtml", 0, None, blocco.caratteri,
                   CORPO, .2)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_colophon_grafico_non_scavalca_documento_bibliografico_forte(self):
        testo = "Rossi, Opera, Roma 1998. Bianchi, Saggio, Milano 2001."
        blocco = Blocco(
            "b", "bib.xhtml", 0, "/p[1]", testo, "prosa",
            titolo="Bibliografia", marcatori_dom=("colophon", "bib"),
        )
        documento = Sezione("bib.xhtml", 8, titolo="Bibliografia",
                            testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("bib.xhtml", 8, "Bibliografia", blocco.caratteri,
                   BIBLIOGRAFIA, 1.0)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(BIBLIOGRAFIA, esito.ruolo)
        self.assertNotIn("colophon", " ".join(esito.prove).casefold())

    def test_titlepage_decorativo_dentro_un_capitolo_non_espelle_la_battuta(self):
        corpo = Blocco("c", "c.xhtml", 0, "/p[1]", "Testo del capitolo.",
                       "prosa")
        battuta = Blocco("b", "c.xhtml", 1, "/p[2]",
                         "Cosa vuoi fare della tua vita?", "prosa",
                         marcatori_dom=("part", "titlepage2"))
        documento = Sezione("c.xhtml", 0,
                            testo=corpo.testo + " " + battuta.testo,
                            blocchi=[corpo, battuta])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("c.xhtml", 0, "Capitolo 1", documento.caratteri,
                   CORPO, .75)],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual(CORPO, esiti[1].ruolo)
        self.assertNotEqual("struttura", esiti[1].fonte)

    def test_titlepage_decorativo_su_xhtml_fuso_non_espelle_prosa_lunga(self):
        testo = "EPILOGO " + ("Il racconto continua normalmente. " * 80)
        blocco = Blocco(
            "e", "epilogo.xhtml", 0, "/h1[1]", testo, "sezione",
            titolo="EPILOGO", marcatori_dom=("calibre", "titlepage"),
        )
        documento = Sezione(
            "epilogo.xhtml", 8, titolo="Epilogo", testo=testo,
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("epilogo.xhtml", 8, "Epilogo", blocco.caratteri,
                   CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertTrue(esito.include_as_main_text)
        self.assertNotEqual("struttura", esito.fonte)

    def test_singleton_iniziale_uguale_al_titolo_del_libro_e_occhiello(self):
        testo = "LA FRONTIERA PROIBITA"
        blocco = Blocco("h", "htp01.xhtml", 0, "/h1[1]", testo,
                        "sezione", titolo=testo)
        documento = Sezione("htp01.xhtml", 1, titolo=testo, testo=testo,
                            blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", titolo="La frontiera proibita",
                  sezioni=[Sezione("cover.xhtml", 0), documento]
                           + [Sezione(f"c{i}.xhtml", i) for i in range(2, 10)]),
            [Esito("htp01.xhtml", 1, testo, blocco.caratteri,
                   PARATESTO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertFalse(esito.include_as_main_text)
        self.assertEqual("struttura", esito.fonte)

    def test_heading_isolato_fra_documenti_di_corpo_e_un_divisore_narrativo(self):
        prima = Blocco("a", "a.xhtml", 0, "/p[1]", "Prima parte " * 100,
                       "prosa")
        titolo = Blocco("t", "t.xhtml", 0, "/div[1]", "Il secondo giorno",
                        "sezione", titolo="Il secondo giorno", livello_titolo=1)
        dopo = Blocco("z", "z.xhtml", 0, "/p[1]", "Seconda parte " * 100,
                      "prosa")
        documenti = [
            Sezione("a.xhtml", 0, testo=prima.testo, blocchi=[prima]),
            Sezione("t.xhtml", 1, titolo=titolo.titolo, testo=titolo.testo,
                    blocchi=[titolo]),
            Sezione("z.xhtml", 2, testo=dopo.testo, blocchi=[dopo]),
        ]
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=documenti),
            [
                Esito("a.xhtml", 0, None, prima.caratteri, CORPO, .75),
                Esito("t.xhtml", 1, titolo.titolo, titolo.caratteri,
                      PARATESTO, .60),
                Esito("z.xhtml", 2, None, dopo.caratteri, CORPO, .75),
            ],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_f01_title_iniziale_propaga_paratesto_ai_suoi_heading(self):
        raw = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
          <h1 class="title">L'Umanista Informatico</h1>
          <h3 class="title1">Fabio Brivio</h3>
        </body></html>'''
        blocchi = estrai_blocchi(raw, "OEBPS/f01_title.xhtml")
        frontespizio = Sezione(
            "OEBPS/f01_title.xhtml", 2, titolo="L'Umanista Informatico",
            testo=" ".join(x.testo for x in blocchi),
            paragrafi=[x.testo for x in blocchi], blocchi=blocchi,
        )
        libro = Libro(
            Path("x.epub"),
            sezioni=[Sezione("cover.xhtml", 0), Sezione("vuota.xhtml", 1),
                     frontespizio]
            + [Sezione(f"c{i}.xhtml", i) for i in range(3, 12)],
        )

        analisi = Analisi(
            libro,
            [Esito(
                sezione.href, sezione.indice, sezione.titolo,
                sezione.caratteri,
                PARATESTO if sezione is frontespizio else CORPO,
                1.0 if sezione is frontespizio else .2,
            ) for sezione in libro.sezioni],
        )
        esiti = classifica_blocchi(analisi)

        self.assertEqual(2, len(esiti))
        self.assertTrue(all(x.ruolo == PARATESTO for x in esiti))

    def test_frontespizio_breve_di_appendice_introduce_il_testo_successivo(self):
        titolo = Blocco(
            "t", "d.xhtml", 0, "/h1[1]",
            "I discendenti della famiglia nel Seicento", "sezione",
            titolo="I discendenti della famiglia nel Seicento",
        )
        autore = Blocco(
            "u", "d.xhtml", 1, "/h2[1]", "di Aldo Cecconi", "sezione",
            titolo="di Aldo Cecconi",
        )
        corpo = Blocco("c", "c.xhtml", 0, "/p[1]", "Testo " * 300,
                       "prosa")
        divisore = Sezione(
            "d.xhtml", 0,
            titolo=f"{titolo.titolo} {autore.titolo}",
            testo=f"{titolo.testo} {autore.testo}",
            blocchi=[titolo, autore],
        )
        seguito = Sezione("c.xhtml", 1, testo=corpo.testo, blocchi=[corpo])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[divisore, seguito]),
            [
                Esito("d.xhtml", 0, divisore.titolo, divisore.caratteri,
                      PARATESTO, .60),
                Esito("c.xhtml", 1, None, seguito.caratteri, CORPO, .75),
            ],
        )

        esiti = classifica_blocchi(analisi)

        self.assertEqual([CORPO, CORPO], [x.ruolo for x in esiti[:2]])
        self.assertTrue(all(x.fonte == "struttura_testuale"
                            for x in esiti[:2]))

    def test_divisore_puo_usare_il_titolo_toc_del_documento(self):
        prima = Blocco("a", "a.xhtml", 0, "/p[1]", "Prima " * 200,
                       "prosa")
        # Il caso reale usa un normale <p>; il titolo strutturale arriva dal
        # TOC e non dal markup locale.
        divisore = Blocco(
            "d", "d.xhtml", 0, "/p[1]",
            "Shopping Immagine di Margherita Bianchini", "prosa",
        )
        dopo = Blocco("z", "z.xhtml", 0, "/p[1]", "Dopo " * 200,
                      "prosa")
        documenti = [
            Sezione("a.xhtml", 0, testo=prima.testo, blocchi=[prima]),
            Sezione("d.xhtml", 1, titolo="Shopping", testo=divisore.testo,
                    blocchi=[divisore]),
            Sezione("z.xhtml", 2, testo=dopo.testo, blocchi=[dopo]),
        ]
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=documenti),
            [
                Esito("a.xhtml", 0, None, prima.caratteri, CORPO, .75),
                Esito("d.xhtml", 1, "Shopping", divisore.caratteri,
                      PARATESTO, .60),
                Esito("z.xhtml", 2, None, dopo.caratteri, CORPO, .75),
            ],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_heading_discorsivo_rivela_un_documento_misto(self):
        heading = Blocco(
            "h", "m.xhtml", 0, "/h2[1]", "DUE ANALISI SOCIO-STORICHE",
            "titolo", titolo="DUE ANALISI SOCIO-STORICHE", livello_titolo=2,
        )
        prosa = Blocco("p", "m.xhtml", 1, "/p[1]", "Testo " * 500,
                       "prosa", titolo=heading.titolo, livello_titolo=2)
        documento = Sezione(
            "m.xhtml", 0, titolo=heading.titolo,
            testo=heading.testo + " " + prosa.testo,
            blocchi=[heading, prosa],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(
                "m.xhtml", 0, heading.titolo, documento.caratteri, NOTA, .60,
                voti=[{"segnale": "grafo", "ruolo": NOTA,
                       "conferma": False}],
            )],
        )

        esiti = classifica_blocchi(analisi)

        self.assertTrue(all(x.ruolo == CORPO for x in esiti))
        self.assertTrue(all(x.fonte == "documento_misto" for x in esiti))

    def test_trama_e_sinossi_sono_intestazioni_editoriali_esatte(self):
        self.assertTrue(R.paratesto_editoriale_esatto(("Trama",)))
        self.assertTrue(R.paratesto_editoriale_esatto(("Sinossi",)))
        self.assertFalse(R.paratesto_editoriale_esatto(("La trama del tempo",)))

    def test_titoli_generici_non_catturano_sezioni_discorsive(self):
        self.assertEqual((None, None), per_titolo("Fonti di errore", "it"))
        self.assertEqual((BIBLIOGRAFIA, "fonti"), per_titolo("Fonti", "it"))
        self.assertEqual((BIBLIOGRAFIA, "fonti bibliografiche"),
                         per_titolo("Fonti bibliografiche", "it"))
        self.assertEqual((NOTA, "nota al testo"),
                         per_titolo("Nota al testo.", "it"))
        self.assertEqual((None, None), per_titolo("Nota sulla dittatura", "it"))
        self.assertEqual((SOGLIA, "nota editoriale"),
                         per_titolo("Nota editoriale", "it"))
        self.assertEqual((BIBLIOGRAFIA, "nota bibliografica"),
                         per_titolo("Nota bibliografica", "it"))

    def test_epilogo_in_documento_bibliografico_forte_resta_bibliografia(self):
        testo = "Epilogo Rossi, Opera, Roma 1998. Bianchi, Saggio, 2001."
        blocco = Blocco("b", "bib.xhtml", 0, "/h2[1]", testo, "sezione",
                        titolo="Epilogo", marcatori_dom=("bib", "bib1"))
        documento = Sezione("bib.xhtml", 8, titolo="Nota bibliografica",
                            testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("bib.xhtml", 8, "Nota bibliografica", blocco.caratteri,
                   BIBLIOGRAFIA, 1.0)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(BIBLIOGRAFIA, esito.ruolo)

    def test_nota_al_testo_prevale_sulle_firme_legali_interne(self):
        testo = ("Nota al testo. La citazione è tratta dall'edizione Einaudi. "
                 "© Editore musicale. Tutti i diritti riservati. Riprodotto "
                 "su autorizzazione dell'editore.")
        blocco = Blocco("n", "nota.xhtml", 0, "/h1[1]", testo, "sezione",
                        titolo="Nota al testo.")
        documento = Sezione("nota.xhtml", 0, titolo=blocco.titolo,
                            testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("nota.xhtml", 0, blocco.titolo, blocco.caratteri,
                   CORPO, .3)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(NOTA, esito.ruolo)
        self.assertEqual("titolo", esito.fonte)
        self.assertEqual("block-title-role", esito.rule_id)

    def test_modello_lineare_espone_un_rule_id_specifico(self):
        text = "Un passaggio discorsivo ordinario abbastanza esteso. " * 20
        block = Blocco("b", "chapter.xhtml", 0, "/p[1]", text, "prosa")
        document = Sezione(
            "chapter.xhtml", 5, titolo=None, testo=text, blocchi=[block],
        )
        analysis = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[document]),
            [Esito("chapter.xhtml", 5, None, block.caratteri, CORPO, .75)],
        )

        class FixedModel:
            def predici(self, feature):
                return Predizione(
                    NOTA, .91, {NOTA: .91, CORPO: .09},
                    [("forma=prosa", .4)],
                )

        result = classifica_blocchi(analysis, modello=FixedModel())[0]

        self.assertEqual(NOTA, result.ruolo)
        self.assertEqual("modello", result.fonte)
        self.assertEqual("linear-model", result.rule_id)

    def test_contextual_rules_see_raw_title_role_before_fallback_suppression(self):
        text = "Epilogo Rossi, Opera, Roma 1998. Bianchi, Saggio, 2001."
        block = Blocco("b", "bib.xhtml", 0, "/h2[1]", text, "sezione",
                       titolo="Epilogo")
        document = Sezione(
            "bib.xhtml", 8, titolo="Nota bibliografica", testo=text,
            blocchi=[block],
        )
        analysis = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[document]),
            [Esito("bib.xhtml", 8, "Nota bibliografica", block.caratteri,
                   BIBLIOGRAFIA, 1.0)],
        )
        seen = []

        def capture(context):
            seen.append(context.block_title_role)
            return None

        with patch(
                "segnatura.classifica_blocchi.match_contextual_rule",
                side_effect=capture):
            result = classifica_blocchi(analysis)[0]

        self.assertEqual([SOGLIA], seen)
        self.assertEqual(BIBLIOGRAFIA, result.ruolo)
        self.assertEqual("document-role-inheritance", result.rule_id)

    def test_avvertenza_editoriale_lunga_resta_indicizzabile(self):
        blocco = Blocco("a", "a.xhtml", 0, "/p[1]", "Testo " * 300,
                        "prosa", titolo="AVVERTENZA DELL'EDITORE")
        documento = Sezione(
            "a.xhtml", 0, titolo=blocco.titolo, testo=blocco.testo,
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("a.xhtml", 0, blocco.titolo, blocco.caratteri,
                   PARATESTO, .85)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertTrue(esito.include_as_main_text)

    def test_backlist_finale_non_diventa_nota_numerata(self):
        corpo = Blocco("c", "c.xhtml", 0, "/p[1]", "Corpo " * 500,
                       "prosa")
        backlist = Blocco(
            "b", "b.xhtml", 0, "/p[1]",
            "SCIENZA E IDEE Ultimi volumi pubblicati 181. Titolo 182. Titolo",
            "prosa", n_elementi=20,
        )
        documenti = [
            Sezione("c.xhtml", 0, testo=corpo.testo, blocchi=[corpo]),
            Sezione("b.xhtml", 1, testo=backlist.testo, blocchi=[backlist]),
        ]
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=documenti),
            [
                Esito("c.xhtml", 0, None, corpo.caratteri, CORPO, .75),
                Esito("b.xhtml", 1, None, backlist.caratteri, NOTA, .60),
            ],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_sommario_linkato_senza_heading_semantico_resta_indice(self):
        testo = "Indice Avvertenza Libro primo Libro secondo Libro terzo"
        blocco = Blocco("i", "i.xhtml", 0, "/body[1]", testo, "sezione",
                        n_elementi=6, n_link=5)
        documento = Sezione("i.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito("i.xhtml", 0, None, blocco.caratteri, CORPO, .40)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(SOMMARIO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_file_indice_di_soli_link_senza_incipit_resta_indice(self):
        testo = " ".join(f"Titolo del capitolo {i}" for i in range(15))
        blocco = Blocco("i", "_0090_indice_01.xhtml", 0, "/body[1]",
                        testo, "prosa", n_elementi=15, n_link=15)
        documento = Sezione(
            "_0090_indice_01.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, None, blocco.caratteri,
                   CORPO, .2)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(SOMMARIO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_didascalia_in_xhtml_singleton_resta_testo(self):
        testo = ("Reazione violenta dei nazisti all'annuncio dell'armistizio: "
                 "il colonnello proclama lo stato d'assedio a Napoli.")
        blocco = Blocco(
            "d", "tavola_13.xhtml", 0, "/div[1]/p[1]", testo, "prosa",
            marcatori_dom=("story4", "didascalia"),
        )
        documento = Sezione(
            "tavola_13.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, None, blocco.caratteri,
                   PARATESTO, .75, ["occhiello o divisore"])],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)
        self.assertTrue(esito.include_as_main_text)

    def test_testo_nota_apre_un_confine_dopo_il_corpo(self):
        raw = b"""<html><body><div>
          <p class="paragrafo">Corpo con richiamo <a href="#n1" id="r1">1</a>.</p>
          <div class="note"><div class="testo_nota">
            <p><a href="#r1" id="n1">1</a> Rossi, Opera, 1998.</p>
          </div></div>
        </div></body></html>"""

        blocchi = estrai_blocchi(raw, "capitolo.xhtml")

        self.assertEqual(2, len(blocchi))
        self.assertIn("Corpo con richiamo", blocchi[0].testo)
        self.assertEqual(NOTA, R.per_marcatori_dom(
            blocchi[1].marcatori_dom)[0])

    def test_divisore_interno_senza_titolo_toc_resta_testo(self):
        prima = Blocco("a", "a.xhtml", 0, "/p[1]", "Corpo " * 500,
                       "prosa")
        divisore = Blocco("d", "d.xhtml", 0, "/p[1]",
                          "Dall'Africa al Mediterraneo", "prosa")
        dopo = Blocco("b", "b.xhtml", 0, "/p[1]", "Corpo " * 500,
                      "prosa")
        documenti = [
            Sezione("a.xhtml", 0, testo=prima.testo, blocchi=[prima]),
            Sezione("d.xhtml", 1, testo=divisore.testo, blocchi=[divisore]),
            Sezione("b.xhtml", 2, testo=dopo.testo, blocchi=[dopo]),
        ]
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=documenti),
            [
                Esito("a.xhtml", 0, None, prima.caratteri, CORPO, .75),
                Esito("d.xhtml", 1, None, divisore.caratteri,
                      PARATESTO, 1.0, ["occhiello o divisore"]),
                Esito("b.xhtml", 2, None, dopo.caratteri, CORPO, .75),
            ],
        )

        esito = classifica_blocchi(analisi)[1]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_ancora_senza_href_non_conta_come_link(self):
        raw = b"""<html><body><p class="titolo_sezione">
          <a id="toc-anchor"></a>Dall'Africa al Mediterraneo
        </p></body></html>"""

        blocco = estrai_blocchi(raw, "parte.xhtml")[0]

        self.assertEqual(0, blocco.n_link)

    def test_numero_ornamentale_occhiello_e_paratesto_strutturale(self):
        blocco = Blocco(
            "n", "occhiello.xhtml", 0, "/p[1]", "242", "prosa",
            marcatori_dom=("occhiello_n",),
        )
        documento = Sezione(
            "occhiello.xhtml", 0, titolo="Occhiello", testo="242",
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, documento.titolo, 3,
                   PARATESTO, 1.0)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_note_calibre_numerate_aprono_confine_senza_classe_semantica(self):
        raw = b"""<html><body>
          <div class="calibre_3">Corpo con rinvii
            <a href="#n1" id="r1">[1]</a>
            <a href="#n2" id="r2">[2]</a>
            <a href="#n3" id="r3">[3]</a>
          </div>
          <div class="calibre_6">
            <a href="#r1" id="n1">[1]</a> Prima nota.
            <a href="#r2" id="n2">[2]</a> Seconda nota.
            <a href="#r3" id="n3">[3]</a> Terza nota.
          </div>
        </body></html>"""

        blocchi = estrai_blocchi(raw, "index_split_012.html")

        self.assertEqual(2, len(blocchi))
        self.assertIn("Corpo con rinvii", blocchi[0].testo)
        self.assertTrue(R.apparato_note_numerate_linkate(
            blocchi[1].testo, blocchi[1].n_link))

        documento = Sezione(
            "index_split_012.html", 0,
            testo=" ".join(x.testo for x in blocchi), blocchi=blocchi,
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, None, documento.caratteri,
                   CORPO, .75)],
        )
        esiti = classifica_blocchi(analisi)

        self.assertEqual(CORPO, esiti[0].ruolo)
        self.assertEqual(NOTA, esiti[1].ruolo)
        self.assertEqual("struttura", esiti[1].fonte)

    def test_blockquote_numerati_non_si_fondono_col_colophon(self):
        raw = b"""<html><body>
          <p>FINITO DI STAMPARE NEL GENNAIO 2011</p>
          <p>Printed in Italy</p>
          <blockquote><a href="#r1">[1]</a> Prima nota.</blockquote>
          <blockquote><a href="#r2">[2]</a> Seconda nota.</blockquote>
          <blockquote><a href="#r3">[3]</a> Terza nota.</blockquote>
          <p>Testo successivo.</p>
        </body></html>"""

        blocchi = estrai_blocchi(raw, "finale.xhtml")

        self.assertEqual(3, len(blocchi))
        self.assertEqual("prosa", blocchi[0].forma)
        self.assertEqual("citazione", blocchi[1].forma)
        self.assertEqual("prosa", blocchi[2].forma)
        self.assertTrue(R.apparato_note_numerate_linkate(
            blocchi[1].testo, blocchi[1].n_link))
        self.assertNotIn("FINITO DI STAMPARE", blocchi[1].testo)
        self.assertEqual("Testo successivo.", blocchi[2].testo)

    def test_index_split_calibre_non_e_un_nome_di_navigazione(self):
        testo = " ".join(f"Titolo collegato {i}" for i in range(15))
        blocco = Blocco(
            "b", "index_split_012.html", 0, "/div[1]", testo, "prosa",
            n_elementi=15, n_link=15,
        )
        documento = Sezione(
            "index_split_012.html", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, None, len(testo), CORPO, .75)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(CORPO, esito.ruolo)

    def test_copyright_senza_heading_usa_firme_legali_congiunte(self):
        testo = ("In copertina: un mosaico. © 2014 REA Edizioni. "
                 "La Casa Editrice resta a disposizione degli aventi diritto.")
        blocco = Blocco("c", "c.xhtml", 0, "/body[1]", testo, "sezione")
        documento = Sezione("c.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento,
                  Sezione("b.xhtml", 1, testo="Corpo " * 500)]),
            [
                Esito("c.xhtml", 0, None, blocco.caratteri, CORPO, .40),
                Esito("b.xhtml", 1, None, 3000, CORPO, .75),
            ],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_copyright_and_info_finale_e_paratesto(self):
        testo = ("Copyright and Info 2016 - © All rights reserved "
                 "ART AND FOOD OF ITALY Rome - Italy example.test")
        blocco = Blocco(
            "c", "part0017.html", 0, "/h1[1]", testo, "sezione",
            titolo="Copyright and Info",
        )
        documento = Sezione(
            "part0017.html", 16, titolo="Copyright and Info",
            testo=testo, blocchi=[blocco],
        )
        sezioni = [Sezione(f"c{i}.html", i) for i in range(16)] + [documento]
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=sezioni),
            [Esito(x.href, x.indice, x.titolo, x.caratteri,
                   CORPO, .2) for x in sezioni],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertFalse(esito.include_as_main_text)

    def test_colophon_tipografico_senza_copyright_resta_paratesto(self):
        testo = ("FINITO DI STAMPARE NEL GENNAIO 2011 DA L.E.G.O. S.P.A. "
                 "STABILIMENTO DI LAVIS. Printed in Italy. "
                 "Registr. Trib. di Milano. Direttore responsabile: Rossi.")
        blocco = Blocco("c", "finale.xhtml", 0, "/p[1]", testo, "prosa")
        documento = Sezione(
            "finale.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(documento.href, 0, None, len(testo), CORPO, .4)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_elenco_toc_con_copyright_e_first_edition_non_e_colophon(self):
        testo = ("Cover image Title page Copyright Preface to the second "
                 "edition Preface to the first edition Acknowledgments")
        self.assertFalse(R.paratesto_legale((testo,)))

    def test_bodymatter_dentro_un_toc_raggruppa_link_non_corpo(self):
        blocco = Blocco(
            "toc", "toc.xhtml", 0, "/section[1]",
            "Chapter 1 Chapter 2 Chapter 3", "prosa",
            titolo="Table of Contents", epub_type={"bodymatter"}, n_link=3,
        )
        documento = Sezione(
            "toc.xhtml", 0, titolo="Table of Contents", testo=blocco.testo,
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en", sezioni=[documento]),
            [Esito("toc.xhtml", 0, "Table of Contents", blocco.caratteri,
                   SOMMARIO, .95)],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(SOMMARIO, esito.ruolo)
        self.assertNotEqual("dichiarazione", esito.fonte)

    def test_risorsa_esterna_isolata_non_eredita_il_sommario(self):
        blocco = Blocco(
            "r", "toc.xhtml", 0, "/h3[1]",
            "To view the Cheat Sheet, go to www.example.com and search.",
            "sezione", titolo="To view the Cheat Sheet", n_link=1,
        )
        documento = Sezione(
            "toc.xhtml", 0, titolo="Table of Contents", testo=blocco.testo,
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en", sezioni=[documento]),
            [Esito(
                "toc.xhtml", 0, "Table of Contents", blocco.caratteri,
                SOMMARIO, .95, ["landmarks: toc"],
                voti=[{"segnale": "dichiarazioni", "ruolo": SOMMARIO}],
            )],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("struttura_testuale", esito.fonte)

    def test_titolo_senza_link_nel_file_toc_e_paratesto(self):
        blocco = Blocco(
            "t", "toc.xhtml", 0, "/h1[1]", "The Book Title",
            "sezione", titolo="The Book Title", n_link=0,
        )
        documento = Sezione(
            "toc.xhtml", 0, titolo="v", testo=blocco.testo,
            blocchi=[blocco],
        )
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="en", sezioni=[documento]),
            [Esito(
                "toc.xhtml", 0, "v", blocco.caratteri, SOMMARIO, .95,
                ["landmarks: toc"],
                voti=[{"segnale": "dichiarazioni", "ruolo": SOMMARIO}],
            )],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(PARATESTO, esito.ruolo)
        self.assertEqual("struttura", esito.fonte)

    def test_indice_senza_titolo_con_voci_brevi_resta_indice(self):
        testo = " ".join(f"Voce {i}, 12, 18" for i in range(400))
        blocco = Blocco("i", "x.xhtml", 0, "/p[1]", testo, "prosa",
                        n_elementi=400)
        documento = Sezione("x.xhtml", 0, testo=testo, blocchi=[blocco])
        analisi = Analisi(
            Libro(Path("x.epub"), lingua="it", sezioni=[documento]),
            [Esito(
                "x.xhtml", 0, None, len(testo), INDICE_ANALITICO, 1.0,
                ["voci brevi con molti numeri"],
                voti=[{"segnale": "forma", "ruolo": INDICE_ANALITICO,
                       "conferma": False}],
            )],
        )

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(INDICE_ANALITICO, esito.ruolo)
        self.assertEqual("documento", esito.fonte)

    def test_override_umano_del_blocco_vince_sulla_dichiarazione(self):
        blocco = Blocco("b", "x.xhtml", 0, "/aside[1]", "Testo", "prosa",
                        epub_type={"footnote"})
        documento = Sezione("x.xhtml", 0, testo="Testo", blocchi=[blocco])
        analisi = Analisi(Libro(Path("x.epub"), sezioni=[documento]),
                          [Esito("x.xhtml", 0, None, 5, NOTA, 1.0)])

        esito = classifica_blocchi(analisi, override={"b": CORPO})[0]

        self.assertEqual(CORPO, esito.ruolo)
        self.assertEqual("correzione", esito.fonte)

    def test_semantica_locale_dominante_descrive_un_file_di_note(self):
        blocchi = [Blocco(str(i), "n.xhtml", i, f"/aside[{i}]", "Nota",
                          "prosa", epub_type={"footnote"}) for i in range(3)]
        documento = Sezione("n.xhtml", 0, testo="Note", blocchi=blocchi)

        voti = da_dichiarazioni(Libro(Path("x.epub"), sezioni=[documento]))

        self.assertTrue(any(v.ruolo == NOTA for v in voti))

    def test_i_voti_deterministici_restano_feature_separate(self):
        blocco = Blocco("b", "n.xhtml", 0, "/p[1]", "Una nota", "prosa")
        documento = Sezione("n.xhtml", 0, testo="Una nota", blocchi=[blocco])
        esito_documento = Esito(
            "n.xhtml", 0, "Note", 8, NOTA, 1.0,
            voti=[{"segnale": "grafo", "ruolo": NOTA,
                   "peso_legacy": 3.5, "conferma": False}],
        )
        analisi = Analisi(Libro(Path("x.epub"), sezioni=[documento]),
                          [esito_documento])

        esito = classifica_blocchi(analisi)[0]

        self.assertEqual(1.0, esito.feature["segnale_grafo=nota"])
        self.assertFalse(any("peso_legacy" in nome for nome in esito.feature))


if __name__ == "__main__":
    unittest.main()
