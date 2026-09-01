import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from segnatura import ruoli as R
from segnatura.apparati import (BIBLIOGRAFIA, AnalisiApparati,
                                EsitoApparato, StatisticheApparati,
                                categoria_da_ruolo, uso)
from segnatura.blocchi import Blocco, estrai_blocchi
from segnatura.classifica import Analisi, Esito
from segnatura.classifica_blocchi import EsitoBlocco
from segnatura.ingestione import (ConfigurazioneChunking,
                                  IntervalloToken, TokenizzatoreSemplice,
                                  prepara_ingestione)
from segnatura.lettura import Libro, Sezione
from segnatura.ruoli import CORPO, NOTA


def _risultato_sintetico():
    corpo = " ".join(f"parola{i}" for i in range(180))
    seguito = " ".join(f"seguito{i}" for i in range(120))
    nota = " ".join(f"nota{i}" for i in range(70))
    raw = f'''<html xmlns="http://www.w3.org/1999/xhtml"><body><main>
      <h1>Capitolo primo</h1><p>{corpo}</p>
      <h2>Seconda parte</h2><p>{seguito}</p>
      <div class="footnotes"><p>1. {nota}</p></div>
      <div class="bibliography"><p>Rossi, Opera, 1998.</p></div>
    </main></body></html>'''.encode()
    blocchi = estrai_blocchi(raw, "capitolo.xhtml")
    documento = Sezione(
        "capitolo.xhtml", 0,
        testo=" ".join(x.testo for x in blocchi),
        paragrafi=[x.testo for x in blocchi], blocchi=blocchi,
    )
    libro = Libro(Path("libro-non-presente.epub"), titolo="Libro",
                  impronta_epub="struttura", sezioni=[documento])
    analisi = Analisi(libro, [Esito(
        documento.href, 0, "Capitolo primo", documento.caratteri,
        CORPO, .9,
    )])
    esiti = []
    for blocco in blocchi:
        marcatori = set(blocco.marcatori_dom)
        if "footnotes" in marcatori:
            ruolo, fonte = NOTA, "struttura"
        elif "bibliography" in marcatori:
            ruolo, fonte = R.BIBLIOGRAFIA, "struttura"
        else:
            ruolo, fonte = CORPO, "documento"
        base = EsitoBlocco(
            blocco, documento, ruolo, .95, fonte, [f"ruolo {ruolo}"],
        )
        categoria = categoria_da_ruolo(ruolo)
        esiti.append(EsitoApparato(
            base, categoria, .95, fonte, [f"categoria {categoria}"],
        ))
    return AnalisiApparati(
        analisi, esiti, StatisticheApparati(blocchi=len(esiti)))


class IngestioneTest(unittest.TestCase):
    tokenizzatore = TokenizzatoreSemplice()

    def test_copertura_contabilizza_ogni_unita_e_motivo(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())

        self.assertTrue(pacchetto.copertura.valida)
        self.assertEqual(
            pacchetto.copertura.caratteri_classificati,
            pacchetto.copertura.caratteri_contabilizzati,
        )
        self.assertEqual(2, len(pacchetto.da_indicizzare()))
        self.assertEqual(3, len(pacchetto.da_indicizzare(includi_note=True)))
        self.assertIn("bibliografia:struttura",
                      pacchetto.copertura.per_motivo_esclusione)
        self.assertEqual(1, len(pacchetto.copertura.documenti))
        manifest = pacchetto.to_dict(includi_testo=False)
        self.assertEqual("segnatura-ingestione-2", manifest["schema"])
        self.assertTrue(manifest["copertura"]["valida"])
        self.assertEqual(2, len(manifest["sequenze"]))
        self.assertNotIn("testo", manifest["unita"][0])

    def test_copertura_tollera_i_separatori_di_un_toc_segmentato(self):
        blocchi = [
            Blocco(str(i), "toc.xhtml", i, f"/li[{i + 1}]", f"Voce {i}",
                   "voce_elenco")
            for i in range(100)
        ]
        documento = Sezione(
            "toc.xhtml", 0, testo=" ".join(x.testo for x in blocchi),
            blocchi=blocchi,
        )
        analisi = Analisi(
            Libro(Path("toc.epub"), impronta_epub="toc", sezioni=[documento]),
            [Esito("toc.xhtml", 0, "Sommario", documento.caratteri,
                   CORPO, .9)],
        )
        esiti = []
        for blocco in blocchi:
            base = EsitoBlocco(blocco, documento, CORPO, .9, "documento")
            esiti.append(EsitoApparato(
                base, "testo", .9, "documento", ["voce del sommario"],
            ))
        risultato = AnalisiApparati(
            analisi, esiti, StatisticheApparati(blocchi=len(esiti)))

        copertura = prepara_ingestione(risultato).copertura

        self.assertTrue(copertura.valida)
        self.assertEqual(99, copertura.documenti[0].scarto_normalizzazione)

    def test_small_to_big_non_attraversa_ruolo(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        piano = pacchetto.crea_chunk(ConfigurazioneChunking(
            massimo_token_piccolo=30, minimo_token_piccolo=12,
            overlap_token=5, budget_contesto=70, includi_note=True,
        ), tokenizzatore=self.tokenizzatore)

        self.assertTrue(piano.statistiche.valida)
        self.assertEqual(0, piano.statistiche.attraversamenti_ruolo)
        self.assertEqual({"testo", "nota"},
                         {x.categoria for x in piano.chunk})
        self.assertNotIn(BIBLIOGRAFIA, {x.categoria for x in piano.chunk})
        self.assertTrue(piano.to_dict()["statistiche"]["valida"])
        for chunk in piano.chunk:
            categorie = {
                x.categoria for x in pacchetto.unita
                if x.id in chunk.unita_ids
            }
            self.assertEqual({chunk.categoria}, categorie)

    def test_ancora_sopravvive_al_ridisegno_dei_chunk(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        primo = pacchetto.crea_chunk(ConfigurazioneChunking(
            massimo_token_piccolo=35, minimo_token_piccolo=15,
            overlap_token=5, budget_contesto=80,
        ), tokenizzatore=self.tokenizzatore)
        ancora_vecchia = primo.chunk[0].ancora
        testo_vecchio = pacchetto.risolvi_ancora(ancora_vecchia)

        secondo = pacchetto.crea_chunk(ConfigurazioneChunking(
            massimo_token_piccolo=22, minimo_token_piccolo=10,
            overlap_token=3, budget_contesto=60,
        ), tokenizzatore=self.tokenizzatore)

        self.assertNotEqual(
            [x.id for x in primo.chunk], [x.id for x in secondo.chunk])
        self.assertTrue(pacchetto.verifica_ancora(ancora_vecchia))
        self.assertEqual(testo_vecchio,
                         pacchetto.risolvi_ancora(ancora_vecchia))

    def test_espansione_restituisce_contesto_grande_stessa_sorgente(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        piano = pacchetto.crea_chunk(ConfigurazioneChunking(
            massimo_token_piccolo=25, minimo_token_piccolo=10,
            overlap_token=4, budget_contesto=65,
        ), tokenizzatore=self.tokenizzatore)
        child = piano.chunk[len(piano.chunk) // 2]
        grande = piano.espandi(child.id)

        self.assertGreaterEqual(grande.token, child.token)
        self.assertLessEqual(grande.token, 65)
        self.assertEqual(child.categoria, grande.categoria)
        self.assertEqual(child.sequenza_id, grande.sequenza_id)
        self.assertGreater(grande.confidenza, 0)
        self.assertTrue(grande.fonti)
        self.assertTrue(grande.prove)
        self.assertTrue(pacchetto.verifica_ancora(grande.ancora))

    def test_sequenze_pubbliche_sono_confini_duri_model_agnostic(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())

        principali = pacchetto.sequenze_indicizzabili()
        con_note = pacchetto.sequenze_indicizzabili(includi_note=True)

        self.assertEqual(1, len(principali))
        self.assertEqual(2, len(con_note))
        self.assertEqual({"testo", "nota"},
                         {x.categoria for x in con_note})
        for sequenza in con_note:
            unita = [x for x in pacchetto.unita
                     if x.id in sequenza.unita_ids]
            self.assertEqual({sequenza.href}, {x.href for x in unita})
            self.assertEqual({sequenza.categoria},
                             {x.categoria for x in unita})
            self.assertTrue(all(0 < x <= len(sequenza.testo)
                                for x in sequenza.confini_frammento))

    def test_category_selection_also_builds_excluded_sequences_and_chunks(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())

        units = pacchetto.units_for_categories({BIBLIOGRAFIA})
        sequences = pacchetto.sequences_for_categories({BIBLIOGRAFIA})
        plan = pacchetto.crea_chunk(ConfigurazioneChunking(
            massimo_token_piccolo=30, minimo_token_piccolo=1,
            overlap_token=4, budget_contesto=70,
            categories=(BIBLIOGRAFIA,),
        ), tokenizzatore=self.tokenizzatore)

        self.assertEqual(1, len(units))
        self.assertEqual(1, len(sequences))
        self.assertTrue(plan.chunk)
        self.assertEqual(
            {BIBLIOGRAFIA}, {item.categoria for item in plan.chunk})

    def test_sequenze_are_built_once_and_passage_lookup_is_constant_time(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        import segnatura.ingestione as ingestione
        unit_map = pacchetto._unita_per_id

        with patch.object(ingestione, "_sequenze",
                          wraps=ingestione._sequenze) as build:
            sequences = pacchetto.sequenze_indicizzabili(True)
            pacchetto.sequenze_indicizzabili(True)
            for _ in range(20):
                pacchetto.passaggio(sequences[0].id, 0, 8)

        self.assertEqual(1, build.call_count)
        self.assertIs(unit_map, pacchetto._unita_per_id)
        self.assertEqual(len(pacchetto.unita), len(unit_map))

    def test_chunker_esterno_ottiene_passaggio_e_ancora_da_caratteri(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        sequenza = pacchetto.sequenze_indicizzabili()[0]
        inizio = sequenza.inizi_frammento[0]
        fine = sequenza.confini_frammento[1]

        passaggio = pacchetto.passaggio(sequenza.id, inizio, fine)

        self.assertEqual(sequenza.testo[inizio:fine], passaggio.testo)
        self.assertEqual(sequenza.categoria, passaggio.categoria)
        self.assertGreater(passaggio.confidenza, 0)
        self.assertTrue(passaggio.fonti)
        self.assertTrue(passaggio.prove)
        self.assertEqual(passaggio.ancora,
                         pacchetto.ancora_per_intervallo(
                             sequenza.id, inizio, fine))
        self.assertEqual(passaggio.testo,
                         pacchetto.risolvi_ancora(passaggio.ancora))

    def test_passaggio_puo_attraversare_unita_ma_non_la_sequenza(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        sequenza = pacchetto.sequenze_indicizzabili()[0]
        self.assertEqual(2, len(sequenza.parti))
        inizio = sequenza.parti[0].fine - 20
        fine = sequenza.parti[1].inizio + 40

        passaggio = pacchetto.passaggio(sequenza.id, inizio, fine)
        risolto = pacchetto.risolvi_ancora(passaggio.ancora)

        self.assertEqual(2, len(passaggio.unita_ids))
        self.assertEqual(" ".join(passaggio.testo.split()),
                         " ".join(risolto.split()))

    def test_passaggio_rifiuta_intervalli_invalidi_o_altre_sequenze(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())
        sequenza = pacchetto.sequenze_indicizzabili()[0]

        with self.assertRaises(ValueError):
            pacchetto.passaggio(sequenza.id, -1, 10)
        with self.assertRaises(ValueError):
            pacchetto.passaggio(sequenza.id, 10, 10)
        with self.assertRaises(KeyError):
            pacchetto.passaggio("inesistente", 0, 10)

    def test_chunking_richiede_policy_e_tokenizer_espliciti(self):
        pacchetto = prepara_ingestione(_risultato_sintetico())

        with self.assertRaises(TypeError):
            pacchetto.crea_chunk()  # type: ignore[call-arg]

    def test_offset_token_non_validi_falliscono_esplicitamente(self):
        class TokenizzatoreRotto:
            nome = "rotto"
            esatto = True

            def intervalli(self, testo):
                return [IntervalloToken(5, 10), IntervalloToken(8, 12)]

        pacchetto = prepara_ingestione(_risultato_sintetico())
        config = ConfigurazioneChunking(
            massimo_token_piccolo=30, minimo_token_piccolo=12,
            overlap_token=5, budget_contesto=70,
        )

        with self.assertRaisesRegex(ValueError, "sovrapposto"):
            pacchetto.crea_chunk(
                config, tokenizzatore=TokenizzatoreRotto())


if __name__ == "__main__":
    unittest.main()
