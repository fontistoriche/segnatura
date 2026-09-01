import unittest
from pathlib import Path
from unittest.mock import patch

from segnatura import ruoli as R
from segnatura.classifica import analizza
from segnatura.lettura import Libro, Sezione
from segnatura.segnali import Voto


def signal(name, role, weight, evidence):
    def evaluate(book):
        return [Voto(book.sezioni[0].href, role, weight, evidence)]
    evaluate.__name__ = name
    return evaluate


class DocumentClassificationTest(unittest.TestCase):
    def analyze_with(self, *signals):
        section = Sezione("text.xhtml", 0, testo="x" * 900)
        book = Libro(Path("book.epub"), sezioni=[section])
        with patch("segnatura.classifica.leggi", return_value=book), \
                patch("segnatura.classifica.S.TUTTI", signals):
            return analizza(book.percorso).sezioni[0]

    def test_uncertain_result_explains_the_conflict_not_a_discarded_role(self):
        result = self.analyze_with(
            signal("note_signal", R.NOTA, 1.0, "note evidence"),
            signal("bibliography_signal", R.BIBLIOGRAFIA, 1.0,
                   "bibliography evidence"),
            signal("paratext_signal", R.PARATESTO, 1.0,
                   "paratext evidence"),
        )

        self.assertEqual(R.INCERTO, result.ruolo)
        self.assertEqual(1, len(result.prove))
        self.assertIn("segnali in conflitto", result.prove[0])
        self.assertNotIn("note evidence", result.prove)

    def test_certain_result_keeps_the_winning_role_evidence(self):
        result = self.analyze_with(
            signal("note_signal", R.NOTA, 3.0, "note evidence"),
            signal("bibliography_signal", R.BIBLIOGRAFIA, 1.0,
                   "bibliography evidence"),
        )

        self.assertEqual(R.NOTA, result.ruolo)
        self.assertEqual(["note evidence"], result.prove)


if __name__ == "__main__":
    unittest.main()
