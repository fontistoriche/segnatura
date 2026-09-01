import tempfile
import unittest
import zipfile
from pathlib import Path

from segnatura import EpubExtractionError, extract
from segnatura.epub_safety import (EpubSafetyError, EpubSafetyLimits,
                                   SafeEpubArchive)
from segnatura.lettura import (Libro, _normalizza_data_pubblicazione,
                               assegna_famiglie, leggi)


def _scrivi_epub(percorso: Path, metadata: str, corpo: str | None = None,
                 extra: dict[str, str | bytes] | None = None) -> None:
    corpo = corpo or """
        <html xmlns="http://www.w3.org/1999/xhtml"><body>
          <h1>Chapter</h1><p>Readable work text for the test fixture.</p>
        </body></html>"""
    with zipfile.ZipFile(percorso, "w") as z:
        z.writestr("META-INF/container.xml", """
            <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
            </container>""")
        z.writestr("OEBPS/content.opf", f"""
            <package version="3.0" xmlns="http://www.idpf.org/2007/opf">
              <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:title>Metadata Test</dc:title><dc:language>en</dc:language>
                {metadata}
              </metadata>
              <manifest><item id="c" href="chapter.xhtml"
                media-type="application/xhtml+xml"/></manifest>
              <spine><itemref idref="c"/></spine>
            </package>""")
        z.writestr("OEBPS/chapter.xhtml", corpo)
        for nome, contenuto in (extra or {}).items():
            z.writestr(nome, contenuto)


class LetturaTest(unittest.TestCase):
    def test_publication_date_rejects_placeholder_years(self):
        self.assertIsNone(_normalizza_data_pubblicazione(
            "0101-01-01T00:00:00+00:00"))

    def test_reads_multiple_epub3_creators_roles_and_publication_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "metadata.epub"
            _scrivi_epub(epub, """
                <dc:creator id="creator-a">Alice Example</dc:creator>
                <meta refines="#creator-a" property="role"
                  scheme="marc:relators">aut</meta>
                <meta refines="#creator-a" property="file-as">Example, Alice</meta>
                <dc:creator id="creator-b">Bruno Editor</dc:creator>
                <meta refines="#creator-b" property="role"
                  scheme="marc:relators">edt</meta>
                <dc:date>2024-02-29T10:20:30Z</dc:date>
            """)

            libro = leggi(epub)

            self.assertIsNone(libro.errore)
            self.assertEqual(
                [("Alice Example", ("aut",), "Example, Alice", "creator-a"),
                 ("Bruno Editor", ("edt",), None, "creator-b")],
                [(x.nome, x.ruoli, x.ordinamento, x.id_opf)
                 for x in libro.creatori],
            )
            self.assertEqual("2024-02-29", libro.data_pubblicazione)
            self.assertEqual("2024-02-29T10:20:30Z",
                             libro.data_pubblicazione_originale)

    def test_reads_epub2_creator_attributes_and_preserves_uncertain_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "metadata-epub2.epub"
            _scrivi_epub(epub, """
                <dc:creator xmlns:opf="http://www.idpf.org/2007/opf"
                  opf:role="aut" opf:file-as="Rossi, Ada">Ada Rossi</dc:creator>
                <dc:date>Spring 2020</dc:date>
            """)

            libro = leggi(epub)

            self.assertIsNone(libro.errore)
            self.assertEqual("Ada Rossi", libro.creatori[0].nome)
            self.assertEqual(("aut",), libro.creatori[0].ruoli)
            self.assertEqual("Rossi, Ada", libro.creatori[0].ordinamento)
            self.assertIsNone(libro.data_pubblicazione)
            self.assertEqual("Spring 2020",
                             libro.data_pubblicazione_originale)

    def test_rejects_unsafe_member_path_without_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "unsafe-path.epub"
            _scrivi_epub(epub, "", extra={"../escape.txt": "no"})

            libro = leggi(epub)

            self.assertIn("unsafe EPUB archive", libro.errore or "")
            self.assertEqual([], libro.sezioni)
            with self.assertRaises(EpubExtractionError):
                extract(epub)

    def test_rejects_oversized_and_deep_documents_with_custom_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            oversized = Path(tmp) / "oversized.epub"
            _scrivi_epub(oversized, "", corpo=(
                '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>'
                + ("x" * 2_000) + "</p></body></html>"))
            libro = leggi(oversized, limiti_sicurezza=EpubSafetyLimits(
                max_member_bytes=1_024))
            self.assertIn("advertises", libro.errore or "")
            self.assertEqual([], libro.sezioni)

            deep = Path(tmp) / "deep.epub"
            corpo = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                     + "<div>" * 12 + "text" + "</div>" * 12
                     + "</body></html>")
            _scrivi_epub(deep, "", corpo=corpo)
            libro = leggi(deep, limiti_sicurezza=EpubSafetyLimits(
                max_xml_depth=8))
            self.assertIn("exceeds depth 8", libro.errore or "")
            self.assertEqual([], libro.sezioni)

    def test_total_decompression_budget_counts_unique_cached_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "budget.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("a.txt", "a" * 8)
                archive.writestr("b.txt", "b" * 8)
            with zipfile.ZipFile(archive_path) as archive:
                safe = SafeEpubArchive(archive, EpubSafetyLimits(
                    max_member_bytes=10, max_total_read_bytes=12))
                self.assertEqual(b"a" * 8, safe.read("a.txt"))
                self.assertEqual(b"a" * 8, safe.read("a.txt"))
                with self.assertRaises(EpubSafetyError):
                    safe.read("b.txt")

    def test_rejects_member_count_and_xml_entity_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "members.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("a.txt", "a")
                archive.writestr("b.txt", "b")
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(EpubSafetyError):
                    SafeEpubArchive(archive, EpubSafetyLimits(max_members=1))

            epub = Path(tmp) / "entity.epub"
            _scrivi_epub(epub, "", corpo="""
                <!DOCTYPE html [<!ENTITY example "expanded">]>
                <html xmlns="http://www.w3.org/1999/xhtml"><body>
                  <p>&example;</p>
                </body></html>""")
            libro = leggi(epub)
            self.assertIn("entity declarations", libro.errore or "")
            self.assertEqual([], libro.sezioni)

    def test_xml_element_limit_is_enforced_by_streaming_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "elements.zip"
            document = "<root>" + "<item/>" * 100 + "</root>"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("many.xml", document)
            with zipfile.ZipFile(archive_path) as archive:
                safe = SafeEpubArchive(archive, EpubSafetyLimits(
                    max_xml_elements=20))
                with self.assertRaisesRegex(EpubSafetyError,
                                            "exceeds 20 elements"):
                    safe.read("many.xml", xml=True)

    def test_malformed_xhtml_keeps_the_existing_lexical_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "malformed.epub"
            _scrivi_epub(epub, "", corpo="<html><body><p>Readable fallback")

            libro = leggi(epub)

            self.assertIsNone(libro.errore)
            self.assertEqual(1, len(libro.sezioni))
            self.assertIn("Readable fallback", libro.sezioni[0].testo)

    def test_famiglie_dipendono_dalla_struttura_non_dalleditore(self):
        base = tuple(f"token={i}" for i in range(10))
        a = Libro(Path("a.epub"), editore="Editore A", impronta_epub="a",
                  impronta_strutturale=base)
        b = Libro(Path("b.epub"), editore="Editore B", impronta_epub="b",
                  impronta_strutturale=base + ("variante=1",))
        c = Libro(Path("c.epub"), editore="Editore A", impronta_epub="c",
                  impronta_strutturale=tuple(f"altro={i}" for i in range(10)))

        assegna_famiglie([a, b, c])

        self.assertEqual(a.famiglia_epub, b.famiglia_epub)
        self.assertNotEqual(a.famiglia_epub, c.famiglia_epub)

    def test_conserva_origine_destinazione_e_reciprocita_dei_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub = Path(tmp) / "minimo.epub"
            with zipfile.ZipFile(epub, "w") as z:
                z.writestr("META-INF/container.xml", """
                    <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                      <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
                    </container>""")
                z.writestr("OEBPS/content.opf", """
                    <package version="3.0" xmlns="http://www.idpf.org/2007/opf">
                      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                        <dc:title>Minimo</dc:title><dc:language>it</dc:language>
                        <dc:publisher>Editore</dc:publisher>
                        <meta name="calibre:series" content="Tascabili"/>
                        <meta name="generator" content="Pipeline 2.4"/>
                      </metadata>
                      <manifest><item id="c" href="cap.xhtml"
                        media-type="application/xhtml+xml"/></manifest>
                      <spine><itemref idref="c"/></spine>
                    </package>""")
                z.writestr("OEBPS/cap.xhtml", """
                    <html xmlns="http://www.w3.org/1999/xhtml"><body>
                      <p>Testo<a id="r1" href="#n1">1</a></p>
                      <aside id="n1">Nota <a href="#r1">indietro</a></aside>
                    </body></html>""")

            libro = leggi(epub)
            sezione = libro.sezioni[0]

            self.assertIsNone(libro.errore)
            self.assertEqual("Editore", libro.editore)
            self.assertEqual("Tascabili", libro.collana)
            self.assertEqual("Pipeline 2.4", libro.generatore)
            self.assertTrue(libro.impronta_epub)
            self.assertTrue(libro.famiglia_epub)
            self.assertEqual(2, len(sezione.collegamenti))
            self.assertEqual({frozenset(("r1", "n1"))},
                             sezione.coppie_interne_reciproche)


if __name__ == "__main__":
    unittest.main()
