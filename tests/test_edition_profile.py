import json
import hashlib
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from segnatura.apparati import analizza_apparati
from segnatura.edition_profile import (
    SCHEMA_EDITION_PROFILE,
    EditionProfileMismatchError,
    EditionProfileSchemaError,
    create_edition_profile_payload,
    file_sha256,
    load_edition_profile,
)


def create_epub(path: Path) -> None:
    container = '''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    opf = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">edition-profile-test</dc:identifier>
    <dc:title>Edition Profile Test</dc:title><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml"
    media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>'''
    chapter = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title></head>
<body><section><h1>Chapter one</h1><p>The first passage of the work.</p></section>
<section><h2>Second section</h2><p>The second passage of the work.</p></section>
</body></html>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


class EditionProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.epub = self.root / "book.epub"
        create_epub(self.epub)
        self.base = analizza_apparati(self.epub)
        self.assertGreaterEqual(len(self.base.blocchi), 1)
        self.first = self.base.blocchi[0]

    def tearDown(self):
        self.temp.cleanup()

    def payload(self) -> dict:
        block = self.first.esito_base.blocco
        href = self.first.esito_base.documento.href
        return {
            "schema": SCHEMA_EDITION_PROFILE,
            "created_at": "2026-08-26T00:00:00+00:00",
            "segnatura_version": "0.12.0",
            "category_policy_version": 1,
            "book": {
                "sha256": file_sha256(self.epub),
                "path": "book.epub",
                "title": "Edition Profile Test",
                "language": "en",
            },
            "documents": [{
                "href": href,
                "category": "bibliography",
                "note": "document correction",
                "updated_at": "",
            }],
            "blocks": [{
                "block_id": block.id,
                "href": href,
                "xpath": block.xpath,
                "fingerprint": block.fingerprint,
                "category": "note",
                "note": "block correction wins",
                "updated_at": "",
            }],
            "ignored_annotations": [],
        }

    def test_manual_mod_is_applied_last_and_preserves_fine_roles(self):
        original_roles = [item.esito_base.ruolo for item in self.base.blocchi]
        result = analizza_apparati(
            self.epub, edition_profile=self.payload())
        self.assertEqual("nota", result.blocchi[0].categoria)
        self.assertEqual("edition_profile", result.blocchi[0].fonte)
        for item in result.blocchi[1:]:
            self.assertEqual("bibliografia", item.categoria)
            self.assertEqual("edition_profile", item.fonte)
        self.assertEqual(
            original_roles,
            [item.esito_base.ruolo for item in result.blocchi],
        )

    def test_epub_hash_mismatch_is_rejected(self):
        payload = self.payload()
        payload["book"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(EditionProfileMismatchError,
                                    "fingerprint mismatch"):
            analizza_apparati(self.epub, edition_profile=payload)

    def test_changed_block_fingerprint_is_rejected(self):
        payload = self.payload()
        payload["blocks"][0]["fingerprint"] = "changed"
        with self.assertRaisesRegex(EditionProfileMismatchError,
                                    "block fingerprint mismatch"):
            analizza_apparati(self.epub, edition_profile=payload)

    def test_range_override_splits_one_block_without_losing_text(self):
        payload = self.payload()
        payload["documents"] = []
        payload["blocks"] = []
        block = self.first.esito_base.blocco
        href = self.first.esito_base.documento.href
        selected = "first passage"
        start = block.testo.index(selected)
        end = start + len(selected)
        fingerprint = hashlib.sha256(
            re.sub(r"\s+", " ", selected).strip().casefold().encode("utf-8")
        ).hexdigest()[:20]
        payload["ranges"] = [{
            "range_id": "range-1",
            "block_id": block.id,
            "href": href,
            "xpath": block.xpath,
            "block_fingerprint": block.fingerprint,
            "start": start,
            "end": end,
            "text_fingerprint": fingerprint,
            "category": "note",
            "note": "embedded note",
            "updated_at": "",
        }]

        result = analizza_apparati(self.epub, edition_profile=payload)
        package = result.prepara_ingestione()
        split = [item for item in package.unita if item.blocco_id == block.id]

        self.assertEqual(block.testo, "".join(item.testo for item in split))
        self.assertEqual(["testo", "nota", "testo"],
                         [item.categoria for item in split])
        self.assertEqual(selected, split[1].testo)
        self.assertEqual("edition_profile_range", split[1].fonte)
        self.assertTrue(all(package.verifica_ancora(item.ancora)
                            for item in split))
        self.assertTrue(package.copertura.valida)

    def test_range_override_rejects_changed_text_and_overlap(self):
        payload = self.payload()
        payload["documents"] = []
        payload["blocks"] = []
        block = self.first.esito_base.blocco
        href = self.first.esito_base.documento.href
        common = {
            "block_id": block.id, "href": href, "xpath": block.xpath,
            "block_fingerprint": block.fingerprint,
            "text_fingerprint": "wrong", "category": "note",
        }
        payload["ranges"] = [{
            **common, "range_id": "range-1", "start": 0, "end": 4,
        }]
        with self.assertRaisesRegex(EditionProfileMismatchError,
                                    "range text fingerprint mismatch"):
            analizza_apparati(self.epub, edition_profile=payload)

        payload["ranges"] = [
            {**common, "range_id": "range-1", "start": 0, "end": 5},
            {**common, "range_id": "range-2", "start": 4, "end": 8},
        ]
        with self.assertRaisesRegex(EditionProfileSchemaError, "overlapping"):
            load_edition_profile(payload)

    def test_unknown_schema_and_category_are_rejected(self):
        payload = self.payload()
        payload["schema"] = "future-schema"
        with self.assertRaises(EditionProfileSchemaError):
            load_edition_profile(payload)
        payload = self.payload()
        payload["blocks"][0]["category"] = "mixed"
        with self.assertRaises(EditionProfileSchemaError):
            load_edition_profile(payload)

    def test_mixed_review_label_is_audited_not_applied(self):
        payload = create_edition_profile_payload(
            {
                "sha256": file_sha256(self.epub), "path": "book.epub",
                "title": "Edition Profile Test", "language": "en",
            },
            [],
            [{
                "block_id": "b", "href": "OEBPS/chapter.xhtml",
                "xpath": "/html/body/p", "fingerprint": "f",
                "label": "mixed",
            }],
            created_at="now", segnatura_version="0.12.0",
        )
        self.assertEqual([], payload["documents"])
        self.assertEqual([], payload["blocks"])
        self.assertEqual(1, len(payload["ignored_annotations"]))
        # The generated document is still structurally valid and loadable.
        loaded = load_edition_profile(payload)
        self.assertEqual(1, len(loaded.ignored_annotations))

    def test_edition_profile_can_be_loaded_from_json_file(self):
        path = self.root / "book.segnatura.json"
        path.write_text(json.dumps(self.payload()), encoding="utf-8")
        loaded = load_edition_profile(path)
        self.assertEqual(file_sha256(self.epub), loaded.book.sha256)
        self.assertEqual("note", loaded.blocks[0].category)

    def test_old_schema_is_rejected_before_publication(self):
        payload = self.payload()
        payload["schema"] = "unsupported-profile-schema"
        with self.assertRaises(EditionProfileSchemaError):
            load_edition_profile(payload)


if __name__ == "__main__":
    unittest.main()
