import unittest

from segnatura.lettura import Collegamento, Libro, Sezione
from segnatura.ruoli import CORPO, NOTA
from segnatura.segnali import da_grafo


def sezione(href, caratteri=4_000, titolo=None):
    return Sezione(href=href, indice=0, testo="x" * caratteri, titolo=titolo)


def collega(fonte, destinazione, coppie):
    for i in range(coppie):
        fonte.collegamenti.append(
            Collegamento(f"r{i}", destinazione.href, f"n{i}"))
        destinazione.collegamenti.append(
            Collegamento(f"n{i}", fonte.href, f"r{i}"))
        fonte.link_esterni.append(destinazione.href)
        destinazione.link_esterni.append(fonte.href)


class GrafoTest(unittest.TestCase):
    def test_link_interno_senza_backlink_non_e_una_nota(self):
        s = sezione("capitolo.xhtml")
        s.id_presenti = {f"n{i}" for i in range(20)}
        s.link_interni = set(s.id_presenti)
        s.collegamenti = [Collegamento(f"r{i}", s.href, f"n{i}")
                          for i in range(20)]

        self.assertFalse(any(v.ruolo == CORPO for v in da_grafo(Libro("x", sezioni=[s]))))

    def test_coppie_interne_esatte_riconoscono_note_in_fondo(self):
        s = sezione("capitolo.xhtml")
        for i in range(4):
            s.collegamenti.extend([
                Collegamento(f"r{i}", s.href, f"n{i}"),
                Collegamento(f"n{i}", s.href, f"r{i}"),
            ])

        voti = da_grafo(Libro("x", sezioni=[s]))

        self.assertEqual(4, len(s.coppie_interne_reciproche))
        self.assertTrue(any(v.ruolo == CORPO and "backlink" in v.prova
                            for v in voti))

    def test_file_note_per_capitolo_con_reciprocita_esatta(self):
        capitolo = sezione("capitolo.xhtml", caratteri=20_000)
        note = sezione("ftn01.xhtml", caratteri=1_500)
        collega(capitolo, note, 5)

        voti = da_grafo(Libro("x", sezioni=[capitolo, note]))

        self.assertTrue(any(v.href == note.href and v.ruolo == NOTA for v in voti))
        self.assertTrue(any(v.href == capitolo.href and v.ruolo == CORPO for v in voti))

    def test_nome_ftn_permette_anche_una_sola_coppia_esatta(self):
        capitolo = sezione("capitolo.xhtml", caratteri=20_000)
        note = sezione("libro_ftn01.xhtml", caratteri=500)
        collega(capitolo, note, 1)

        voti = da_grafo(Libro("x", sezioni=[capitolo, note]))

        self.assertTrue(any(v.href == note.href and v.ruolo == NOTA for v in voti))

    def test_coppia_ambigua_con_titolo_non_viene_forzata(self):
        capitolo = sezione("capitolo.xhtml", caratteri=20_000)
        indice = sezione("elenco.xhtml", caratteri=1_500,
                         titolo="Elenco delle voci")
        collega(capitolo, indice, 8)

        voti = da_grafo(Libro("x", sezioni=[capitolo, indice]))

        self.assertFalse(any(v.href == indice.href and v.ruolo == NOTA for v in voti))

    def test_quota_ritorni_arrotonda_per_eccesso(self):
        destinazione = sezione("note.xhtml")
        fonti = [sezione(f"c{i}.xhtml") for i in range(3)]
        for fonte in fonti:
            fonte.link_esterni.append(destinazione.href)
        destinazione.link_esterni.append(fonti[0].href)

        voti = da_grafo(Libro("x", sezioni=fonti + [destinazione]))

        self.assertFalse(any(v.href == destinazione.href and v.ruolo == NOTA
                             for v in voti))

    def test_apparati_reciproci_non_trasformano_il_corpo_in_note(self):
        corpo = sezione("testo_02.xhtml", caratteri=45_000,
                        titolo="Gli italiani visti da dentro")
        note = sezione("note_01.xhtml", caratteri=9_000)
        indice = sezione("indice_analitico_01.xhtml", caratteri=16_000)
        sommario = sezione("indice_01.xhtml", caratteri=400)
        collega(note, corpo, 6)
        collega(indice, corpo, 20)
        sommario.link_esterni.append(corpo.href)

        voti = da_grafo(Libro("x", lingua="it",
                              sezioni=[corpo, note, indice, sommario]))

        self.assertFalse(any(v.href == corpo.href and v.ruolo == NOTA
                             for v in voti))

    def test_indice_esplicito_non_diventa_nota_per_il_grafo(self):
        indice = sezione("name-index.xhtml", caratteri=8_000)
        capitoli = [sezione(f"capitolo-{i}.xhtml", caratteri=20_000)
                    for i in range(3)]
        for capitolo in capitoli:
            collega(capitolo, indice, 5)

        voti = da_grafo(Libro("x", sezioni=capitoli + [indice]))

        self.assertFalse(any(v.href == indice.href and v.ruolo == NOTA
                             for v in voti))


if __name__ == "__main__":
    unittest.main()
