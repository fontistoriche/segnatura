import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import segnatura
from segnatura import ExtractedBook, StructuredResponse, TokenSpan
from segnatura.cli import _render
from segnatura.llm import (OpenAICompatibleBackend, OpenAICompatibleConfig,
                           StructuredLLMBackend)
from segnatura.ingestione import prepara_ingestione
from segnatura.lettura import Creatore
from tests.test_ingestione import _risultato_sintetico


class PublicApiTest(unittest.TestCase):
    def setUp(self):
        analysis = _risultato_sintetico()
        analysis.analisi.libro.creatori = (
            Creatore("Alice Example", ("aut",), "Example, Alice", "a"),
            Creatore("Bruno Editor", ("edt",), id_opf="b"),
        )
        analysis.analisi.libro.data_pubblicazione = "2024-02-29"
        analysis.analisi.libro.data_pubblicazione_originale = \
            "2024-02-29T10:20:30Z"
        self.book = ExtractedBook(
            Path("synthetic.epub"), analysis, prepara_ingestione(analysis))

    def test_units_use_english_categories_and_keep_exact_source(self):
        units = self.book.units(categories={"work_text", "note"})

        self.assertEqual({"work_text", "note"}, {item.category for item in units})
        self.assertTrue(all(item.source["epub_sha256"] for item in units))
        self.assertTrue(all(item.source["start"]["xpath"] for item in units))
        self.assertTrue(all(self.book.verify_source(item.source) for item in units))

    def test_every_classified_category_can_be_requested_as_units(self):
        bibliography = self.book.units(categories={"bibliography"})
        all_units = self.book.units(categories="all")

        self.assertEqual(1, len(bibliography))
        self.assertEqual("bibliography", bibliography[0].category)
        self.assertIn("Rossi, Opera, 1998", bibliography[0].text)
        self.assertEqual(
            bibliography[0].text,
            self.book.text(categories={"bibliography"}),
        )
        self.assertEqual((), self.book.find_text("Rossi"))
        self.assertEqual(1, len(self.book.find_text(
            "Rossi", categories={"bibliography"})))
        self.assertEqual(1, len(self.book.find_text(
            "Rossi", categories="all")))
        records = self.book.rag_records(
            categories={"bibliography"}, max_tokens=30, min_tokens=1,
            overlap_tokens=4, context_tokens=70,
        )
        self.assertTrue(records)
        self.assertEqual(
            {"bibliography"},
            {item.metadata["category"] for item in records},
        )
        self.assertEqual(len(self.book.blocks()), len(all_units))
        self.assertEqual(
            {"work_text", "note", "bibliography"},
            {item.category for item in all_units},
        )
        self.assertEqual(
            {item.category for item in all_units},
            {item.metadata["category"] for item in self.book.rag_records(
                categories="all", max_tokens=30, min_tokens=1,
                overlap_tokens=4, context_tokens=70,
            )},
        )
        with self.assertRaisesRegex(ValueError, "unknown categories"):
            self.book.units(categories={"invented"})
        with self.assertRaisesRegex(ValueError, "iterable"):
            self.book.units(categories="bibliography")

    def test_top_level_stable_api_is_small_and_explicit(self):
        self.assertEqual({
            "__version__", "extract", "ExtractedBook", "ExtractionUnit",
            "ExtractionDocument", "ExtractionBlock",
            "Creator", "RAGRecord", "TextMatch", "Tokenizer", "TokenSpan",
            "StructuredLLMBackend", "StructuredResponse",
            "OpenAICompatibleConfig", "OpenAICompatibleBackend", "LLMError",
            "LLMUnavailableError", "InvalidLLMResponseError",
            "EpubExtractionError", "EpubSafetyLimits", "SCHEMA_RAG_RECORD",
            "EditionProfileError", "EditionProfileSchemaError",
            "EditionProfileMismatchError",
            "audit", "AuditBackend", "AuditConfig", "AuditFinding",
            "AuditCancelledError",
            "AuditCoverage", "AuditEstimate", "AuditValidationIssue",
            "AuditReport", "estimate_audit", "SCHEMA_AUDIT_REPORT",
            "AUDIT_PROMPT_VERSION",
        }, set(segnatura.__all__))
        self.assertFalse(hasattr(segnatura, "analizza"))
        self.assertFalse(hasattr(segnatura, "analizza_ibrido"))

    def test_public_inventory_exposes_all_documents_and_excluded_blocks(self):
        documents = self.book.documents(excerpt_characters=40)
        blocks = self.book.blocks()

        self.assertEqual(1, len(documents))
        self.assertEqual(sum(item.block_count for item in documents),
                         len(blocks))
        self.assertIn("bibliography", {item.category for item in blocks})
        self.assertLessEqual(len(documents[0].visible_text_excerpt), 47)
        self.assertTrue(all(item.xpath and item.fingerprint for item in blocks))

    def test_rag_records_identify_book_and_source(self):
        records = self.book.rag_records(
            categories={"work_text", "note"}, max_tokens=30, min_tokens=10,
            overlap_tokens=4, context_tokens=70)

        self.assertTrue(records)
        first = records[0].to_dict()
        self.assertEqual("segnatura-rag-record-1",
                         first["metadata"]["schema"])
        self.assertEqual("Libro", first["metadata"]["book"]["title"])
        self.assertEqual(["Alice Example"],
                         first["metadata"]["book"]["authors"])
        self.assertEqual("edt", first["metadata"]["book"]["creators"][1]
                         ["roles"][0])
        self.assertEqual("2024-02-29",
                         first["metadata"]["book"]["publication_date"])
        self.assertIn("href", first["metadata"]["source"])
        self.assertTrue(self.book.verify_source(first["metadata"]["source"]))
        self.assertNotIn("bibliography",
                         {item.metadata["category"] for item in records})

    def test_public_offset_tokenizer_contract_uses_english_names(self):
        class CharacterTokenizer:
            name = "characters"
            exact = True

            def spans(self, text):
                return [TokenSpan(index, index + 1)
                        for index in range(len(text)) if not text[index].isspace()]

        records = self.book.rag_records(
            categories={"work_text", "note"}, max_tokens=30, min_tokens=10,
            overlap_tokens=4, context_tokens=70,
            tokenizer=CharacterTokenizer())

        self.assertTrue(records)
        self.assertEqual("characters", records[0].metadata["tokenizer"])
        self.assertTrue(records[0].metadata["exact_token_count"])

    def test_units_json_uses_the_same_complete_book_metadata(self):
        payload = json.loads(_render(self.book, SimpleNamespace(
            format="units-json", category=None)))

        self.assertEqual(self.book.book_metadata(), payload["book"])
        self.assertEqual(["Alice Example"], payload["book"]["authors"])
        self.assertEqual("2024-02-29T10:20:30Z",
                         payload["book"]["publication_date_raw"])

    def test_literal_search_is_exhaustive_and_citable(self):
        matches = self.book.find_text("parola42")

        self.assertEqual(1, len(matches))
        self.assertEqual("parola42", matches[0].text)
        self.assertTrue(self.book.verify_source(matches[0].source))

    def test_openai_compatible_adapter_does_not_require_model_listing(self):
        calls = []

        def transport(method, url, payload, headers, timeout):
            calls.append((method, url, payload))
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

        backend = OpenAICompatibleBackend(OpenAICompatibleConfig(
            model="local-model", base_url="http://localhost:9999/v1",
            cache=None), transport=transport)
        response = backend.request_structured(
            {"value": 1}, "Return JSON", {"type": "json_object"}, "test-1")

        self.assertEqual({"ok": True}, response.data)
        self.assertEqual(1, len(calls))
        self.assertEqual("http://localhost:9999/v1/chat/completions", calls[0][1])
        self.assertIsInstance(backend, StructuredLLMBackend)

    def test_custom_backend_can_return_public_structured_response(self):
        response = StructuredResponse(
            data={"decisions": {}}, model="custom-provider")

        self.assertEqual({"decisions": {}}, response.data)
        self.assertEqual("custom-provider", response.model)

    def test_extraction_api_does_not_accept_an_llm_backend(self):
        with self.assertRaises(TypeError):
            segnatura.extract("missing.epub", llm=object())


if __name__ == "__main__":
    unittest.main()
