import unittest
from collections import Counter

from segnatura import ruoli as R
from segnatura.classifica import Analisi, Esito
from segnatura.lettura import Libro, Sezione
from segnatura.ruoli import APPENDICE, BIBLIOGRAFIA, CORPO, NOTA, SOGLIA
from segnatura.segnali import da_dichiarazioni, da_forma, da_posizione, da_titolo


def esito(ruolo):
    return Esito("x.xhtml", 0, None, 100, ruolo, 1.0)


class PoliticaTest(unittest.TestCase):
    def test_ruolo_e_uso_sono_distinti(self):
        prefazione = esito(SOGLIA)
        note = esito(NOTA)
        bibliografia = esito(BIBLIOGRAFIA)

        self.assertEqual(SOGLIA, prefazione.ruolo)
        self.assertEqual(R.TESTO_PRINCIPALE, prefazione.uso)
        self.assertTrue(prefazione.include_as_main_text)
        self.assertEqual(R.SU_RICHIESTA, note.uso)
        self.assertEqual(R.ESCLUSO, bibliografia.uso)

    def test_analisi_applica_la_politica_senza_cambiare_i_ruoli(self):
        sezioni = [esito(CORPO), esito(SOGLIA), esito(APPENDICE),
                   esito(NOTA), esito(BIBLIOGRAFIA)]
        analisi = Analisi(Libro("x"), sezioni)

        self.assertEqual(3, len(analisi.da_indicizzare()))
        self.assertEqual(4, len(analisi.da_indicizzare(includi_note=True)))

    def test_titolo_copyright_prevale_sulla_forma_bibliografica(self):
        voci = [f"Rossi, Opera, 20{i:02d}, vol. 1, pp. 1-10" for i in range(10)]
        bersaglio = Sezione(
            "copyright.xhtml", 3, titolo="Copyright", origine_titolo="TOC",
            testo=" ".join(voci), paragrafi=voci,
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(3)] + [bersaglio])
        punteggi = Counter()
        for segnale in (da_titolo, da_forma, da_posizione):
            for voto in segnale(libro):
                if voto.href == bersaglio.href:
                    punteggi[voto.ruolo] += voto.peso

        self.assertGreater(punteggi[R.PARATESTO], punteggi[R.BIBLIOGRAFIA])

    def test_copyright_and_info_e_un_titolo_editoriale_esatto(self):
        ruolo, frase = R.per_titolo("Copyright and Info", "it")

        self.assertEqual(R.PARATESTO, ruolo)
        self.assertEqual("copyright and info", frase)

    def test_dichiarazione_editoriale_prevale_sul_titolo(self):
        s = Sezione("x.xhtml", 0, titolo="Chapter 1", origine_titolo="TOC",
                    epub_type={"bibliography"},
                    epub_type_documento={"bibliography"})
        libro = Libro("x", lingua="en", sezioni=[s])
        punteggi = Counter()
        for segnale in (da_dichiarazioni, da_titolo):
            for voto in segnale(libro):
                punteggi[voto.ruolo] += voto.peso

        self.assertGreater(punteggi[R.BIBLIOGRAFIA], punteggi[R.CORPO])

    def test_abstract_epub_e_aria_sono_paratesto_editoriale(self):
        casi = (
            {"epub_type_documento": {"abstract"}},
            {"ruoli_aria_documento": {"doc-abstract"}},
        )
        for attributi in casi:
            with self.subTest(attributi=attributi):
                sezione = Sezione(
                    "Trama.xhtml", 0,
                    testo="Sinossi editoriale e biografia dell'autore.",
                    **attributi,
                )
                voti = da_dichiarazioni(Libro("x", sezioni=[sezione]))

                self.assertTrue(any(
                    voto.ruolo == R.PARATESTO for voto in voti
                ))

    def test_titlepage_numerato_e_un_marcatore_di_frontespizio(self):
        ruolo, marcatore = R.per_marcatori_dom(
            ("calibre", "titlepage1", "titlepage2")
        )

        self.assertEqual(R.PARATESTO, ruolo)
        self.assertEqual("titlepage2", marcatore)

    def test_preposizione_in_e_anni_non_fanno_una_bibliografia(self):
        paragrafi = [
            (f"Nel {1650 + i} visse in Roma e lavorò in una corte europea, "
             "dove continuò i propri studi e incontrò numerosi protagonisti "
             "della vita politica e culturale del tempo.")
            for i in range(12)
        ]
        sezione = Sezione(
            "capitolo.xhtml", 5, testo="\n".join(paragrafi),
            paragrafi=paragrafi,
        )
        libro = Libro("x", sezioni=[sezione])

        voti = [v for v in da_forma(libro)
                if v.ruolo == R.BIBLIOGRAFIA]

        self.assertEqual([], voti)

    def test_bibliografia_senza_titolo_a_voci_brevi_resta_riconoscibile(self):
        paragrafi = [
            f"Rossi, Titolo dell'opera {i}, Roma, {1990 + i}."
            for i in range(12)
        ]
        sezione = Sezione(
            "fonti.xhtml", 5, testo="\n".join(paragrafi),
            paragrafi=paragrafi,
        )
        libro = Libro("x", sezioni=[sezione])

        voti = [v for v in da_forma(libro)
                if v.ruolo == R.BIBLIOGRAFIA]

        self.assertEqual(1, len(voti))

    def test_autori_e_un_titolo_editoriale_esatto_multilingue(self):
        for titolo in ("Autori", "Authors", "Autoren", "Auteurs", "Autores"):
            with self.subTest(titolo=titolo):
                ruolo, _ = R.per_titolo(titolo)
                self.assertEqual(R.PARATESTO, ruolo)

        ruolo, _ = R.per_titolo("Autori e lettori nella modernità")
        self.assertIsNone(ruolo)

    def test_formule_editoriali_dentro_un_titolo_saggistico_non_sono_paratesto(self):
        self.assertEqual(
            (None, None),
            R.per_titolo(
                "3. Il libro di larga circolazione: repertorio e caratteristiche materiali",
                "it",
            ),
        )
        self.assertEqual(
            (None, None),
            R.per_titolo(
                "1. L'autore, lo stampatore-libraio e il ricorso alla privativa",
                "it",
            ),
        )
        self.assertEqual(R.PARATESTO, R.per_titolo("Il libro", "it")[0])
        self.assertEqual(R.PARATESTO, R.per_titolo("L'autore", "it")[0])

    def test_biografia_e_un_titolo_editoriale_esatto_multilingue(self):
        for titolo in ("Biografia", "Biography", "Biografie", "Biographie"):
            with self.subTest(titolo=titolo):
                ruolo, _ = R.per_titolo(titolo)
                self.assertEqual(R.PARATESTO, ruolo)

    def test_notizie_sull_autrice_e_paratesto_multilingue(self):
        for titolo in (
            "Notizie sull’autrice", "About the authors",
            "Über die Autorin", "À propos de l’autrice",
            "Sobre la autora",
        ):
            with self.subTest(titolo=titolo):
                ruolo, _ = R.per_titolo(titolo)
                self.assertEqual(R.PARATESTO, ruolo)

    def test_iniziale_del_nome_non_fa_un_epigrafe(self):
        frontespizio = Sezione(
            "title.xhtml", 2,
            testo=("Juan J. Linz Sistemi totalitari e regimi autoritari "
                   "Introduzione di Alessandro Campi Editore"),
            paragrafi=["Juan J. Linz Sistemi totalitari e regimi autoritari "
                       "Introduzione di Alessandro Campi Editore"],
        )
        libro = Libro("x", sezioni=[Sezione("cover.xhtml", 0),
                                    Sezione("collana.xhtml", 1), frontespizio]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(3, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == frontespizio.href and v.ruolo == R.PARATESTO]

        self.assertEqual(1, len(voti))

    def test_f01_title_iniziale_e_frontespizio_anche_in_spine_corto(self):
        frontespizio = Sezione(
            "OEBPS/f01_title.xhtml", 2, titolo="l'Umanista Informatico",
            testo="l'Umanista Informatico Fabio Brivio",
            paragrafi=["l'Umanista Informatico", "Fabio Brivio"],
        )
        libro = Libro(
            "x",
            sezioni=[Sezione("cover.xhtml", 0), Sezione("vuota.xhtml", 1),
                     frontespizio]
            + [Sezione(f"c{i}.xhtml", i) for i in range(3, 12)],
        )

        voti = [v for v in da_posizione(libro)
                if v.href == frontespizio.href and v.ruolo == R.PARATESTO]

        self.assertEqual(1, len(voti))
        self.assertIn("nome convenzionale", voti[0].prova)

    def test_sezione_breve_in_prosa_non_diventa_un_occhiello(self):
        epigrafe = Sezione(
            "epigrafe.xhtml", 3,
            testo=("Una citazione abbastanza lunga. " * 12),
            paragrafi=["Una citazione.", "Autore 2, 9", "Seconda citazione.",
                       "Indicazione della fonte."],
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(3)]
                      + [epigrafe]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(4, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == epigrafe.href and v.ruolo == R.PARATESTO]

        self.assertEqual([], voti)

    def test_didascalia_breve_senza_titolo_non_diventa_paratesto(self):
        didascalia = Sezione(
            "figura.xhtml", 8, testo="Fig. 4.1. Porta Magica (Foto Rossi)",
            paragrafi=["Fig. 4.1. Porta Magica (Foto Rossi)"],
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(8)]
                      + [didascalia]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(9, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == didascalia.href and v.ruolo == R.PARATESTO]

        self.assertEqual([], voti)

    def test_epigrafe_breve_dopo_frontespizio_non_diventa_paratesto(self):
        epigrafe = Sezione(
            "epigrafe.xhtml", 2, testo="La materia torna idea. Autore",
            paragrafi=["La materia torna idea. Autore"],
        )
        libro = Libro("x", sezioni=[Sezione("cover.xhtml", 0),
                                    Sezione("title.xhtml", 1), epigrafe]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(3, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == epigrafe.href and v.ruolo == R.PARATESTO]

        self.assertEqual([], voti)

    def test_occhiello_breve_rimane_paratesto(self):
        occhiello = Sezione(
            "parte.xhtml", 3, testo="LIBRO TERZO",
            paragrafi=["LIBRO TERZO"], titolo="LIBRO TERZO",
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(3)]
                      + [occhiello]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(4, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == occhiello.href and v.ruolo == R.PARATESTO]

        self.assertEqual(1, len(voti))

    def test_titolo_breve_seguito_da_contenuto_non_e_un_occhiello(self):
        sezione = Sezione(
            "luoghi.xhtml", 8, titolo="III Dove",
            testo="III Dove\nRoma\nCastel Sant'Angelo\nPalazzo Corsini",
            paragrafi=["III Dove", "Roma, Castel Sant'Angelo, Palazzo Corsini"],
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(8)]
                      + [sezione]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(9, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == sezione.href and v.ruolo == R.PARATESTO]

        self.assertEqual([], voti)

    def test_titolo_di_parte_senza_markup_resta_testo(self):
        parte = Sezione(
            "parte.xhtml", 8,
            testo="Parte seconda Nozioni e campi di ricerca",
            paragrafi=["Parte seconda Nozioni e campi di ricerca"],
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(8)]
                      + [parte]
                      + [Sezione(f"c{i}.xhtml", i) for i in range(9, 20)])

        voti = [v for v in da_posizione(libro)
                if v.href == parte.href and v.ruolo == R.PARATESTO]

        self.assertEqual([], voti)

    def test_url_editoriale_isolato_resta_paratesto(self):
        sito = Sezione(
            "fine.xhtml", 18, testo="www.editore.example",
            paragrafi=["www.editore.example"],
        )
        libro = Libro("x", sezioni=[Sezione(f"c{i}.xhtml", i)
                                    for i in range(18)] + [sito]
                      + [Sezione("ultimo.xhtml", 19)])

        voti = [v for v in da_posizione(libro)
                if v.href == sito.href and v.ruolo == R.PARATESTO]

        self.assertEqual(1, len(voti))


if __name__ == "__main__":
    unittest.main()
