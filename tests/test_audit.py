import tempfile
import unittest
import zipfile
from pathlib import Path

from segnatura import (AuditCancelledError, AuditConfig, StructuredResponse,
                       audit, estimate_audit, extract)
from segnatura.llm import InvalidLLMResponseError
from tests.test_edition_profile import create_epub


def create_multi_document_epub(
        path: Path, documents: int = 3,
        passage_repetitions: int = 1) -> None:
    container = '''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    manifest = "".join(
        f'<item id="d{i}" href="d{i}.xhtml" '
        'media-type="application/xhtml+xml"/>'
        for i in range(documents))
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(documents))
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier>audit-many-documents</dc:identifier>
    <dc:title>Audit batches</dc:title><dc:language>en</dc:language>
  </metadata><manifest>{manifest}</manifest><spine>{spine}</spine>
</package>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        for i in range(documents):
            passage = (f"Complete work passage number {i}. "
                       * passage_repetitions)
            archive.writestr(
                f"OEBPS/d{i}.xhtml",
                '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                f'<title>Document {i}</title></head><body><h1>Heading {i}</h1>'
                f'<p>{passage}</p></body></html>')


class RecordingBackend:
    def __init__(self, invalid_target: bool = False):
        self.calls = []
        self.invalid_target = invalid_target

    def request_structured(self, input_data, system_prompt, schema,
                           prompt_version):
        self.calls.append((input_data, prompt_version, schema))
        if input_data["audit_pass"] == "book_overview":
            findings = []
        else:
            block = input_data["blocks"][0]
            findings = [{
                "kind": "category_change",
                "scope": "block",
                "href": block["href"],
                "block_id": ("missing" if self.invalid_target
                             else block["block_id"]),
                "proposed_category": "note",
                "severity": "warning",
                "confidence": 0.87,
                "explanation": "The passage behaves like an editorial note.",
                "evidence": ["The block is set apart from the main passage."],
            }] if len(self.calls) == 2 else []
        return StructuredResponse(
            data={"findings": findings}, model="audit-test-model",
            network_attempts=1,
        )


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.epub = Path(self.temp.name) / "book.epub"
        create_epub(self.epub)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_audit_covers_every_deterministic_block_without_applying(self):
        before = extract(self.epub)
        categories_before = [item.category for item in before.blocks()]
        backend = RecordingBackend()

        report = audit(
            self.epub, backend=backend,
            config=AuditConfig(max_blocks_per_batch=1),
        )
        after = extract(self.epub)

        self.assertTrue(report.coverage.complete)
        self.assertEqual(report.coverage.blocks_total,
                         report.coverage.blocks_submitted)
        self.assertEqual(report.coverage.documents_total,
                         report.coverage.documents_submitted)
        self.assertEqual(1 + report.coverage.blocks_total, report.calls)
        self.assertEqual(report.calls, len(backend.calls))
        self.assertEqual(
            categories_before,
            [item.category for item in after.blocks()],
        )
        self.assertEqual(1, len(report.findings))
        finding = report.findings[0]
        self.assertEqual("work_text", finding.current_category)
        self.assertEqual("note", finding.proposed_category)
        self.assertTrue(finding.xpath)
        self.assertTrue(finding.fingerprint)
        self.assertTrue(finding.can_create_edition_profile_override)
        self.assertEqual("segnatura-audit-report-2",
                         report.to_dict()["schema"])

    def test_audit_accepts_an_already_extracted_book(self):
        book = extract(self.epub)
        report = audit(
            book, backend=RecordingBackend(),
            config=AuditConfig(max_blocks_per_batch=1),
        )

        self.assertTrue(report.coverage.complete)
        self.assertEqual(book.epub_sha256, report.book["epub_sha256"])

    def test_every_detail_call_receives_complete_text_and_final_category(self):
        backend = RecordingBackend()

        report = audit(
            self.epub, backend=backend,
            config=AuditConfig(max_blocks_per_batch=1),
        )

        detail_calls = [call[0] for call in backend.calls
                        if call[0]["audit_pass"] == "complete_block_review"]
        overview = backend.calls[0][0]
        submitted = [block for call in detail_calls for block in call["blocks"]]
        self.assertEqual(report.coverage.documents_total,
                         len(overview["documents"]))
        self.assertTrue(all("documents" not in call for call in detail_calls))
        self.assertIn("epub_types", overview["documents"][0])
        self.assertNotIn("epub_type", overview["documents"][0])
        self.assertEqual(report.coverage.blocks_total, len(submitted))
        self.assertTrue(all(block["text"] for block in submitted))
        self.assertTrue(all(block["deterministic_category"]
                            in {"work_text", "note", "bibliography",
                                "index", "paratext"}
                            for block in submitted))
        self.assertTrue(all(block["classification_rule"] != "fallback"
                            for block in submitted))

    def test_unknown_target_is_discarded_without_losing_batch_coverage(self):
        report = audit(
            self.epub, backend=RecordingBackend(invalid_target=True),
            config=AuditConfig(max_blocks_per_batch=1),
        )

        self.assertTrue(report.coverage.complete)
        self.assertEqual(0, len(report.findings))
        self.assertEqual(1, len(report.validation_issues))
        self.assertIn("target does not exist",
                      report.validation_issues[0].reason)
        self.assertEqual(1, report.to_dict()["statistics"][
            "discarded_findings"])

    def test_valid_finding_survives_invalid_sibling_in_same_response(self):
        class MixedBackend:
            def __init__(self):
                self.detail_calls = 0

            def request_structured(self, input_data, *args):
                if input_data["audit_pass"] == "book_overview":
                    return StructuredResponse(
                        data={"findings": []}, model="mixed")
                self.detail_calls += 1
                if self.detail_calls > 1:
                    return StructuredResponse(
                        data={"findings": []}, model="mixed")
                block = input_data["blocks"][0]
                base = {
                    "kind": "category_change", "scope": "block",
                    "href": block["href"], "proposed_category": "note",
                    "severity": "warning", "confidence": .9,
                    "explanation": "A valid observable disagreement.",
                    "evidence": ["The block is set apart."],
                }
                return StructuredResponse(data={"findings": [
                    {**base, "block_id": block["block_id"]},
                    {**base, "block_id": "foreign-id"},
                ]}, model="mixed")

        report = audit(
            self.epub, backend=MixedBackend(),
            config=AuditConfig(max_blocks_per_batch=1))

        self.assertEqual(1, len(report.findings))
        self.assertEqual(1, len(report.validation_issues))
        self.assertTrue(report.coverage.complete)

    def test_structurally_invalid_response_still_aborts_the_audit(self):
        class InvalidEnvelope:
            def request_structured(self, *args):
                return StructuredResponse(data={}, model="broken")

        with self.assertRaisesRegex(InvalidLLMResponseError,
                                    "findings array"):
            audit(self.epub, backend=InvalidEnvelope())

    def test_estimate_matches_actual_calls_without_contacting_backend(self):
        book = extract(self.epub)
        config = AuditConfig(max_blocks_per_batch=1)
        estimate = estimate_audit(book, config=config)
        backend = RecordingBackend()

        report = audit(self.epub, backend=backend, config=config)

        self.assertEqual(1, estimate.overview_calls)
        self.assertEqual(len(book.blocks()), estimate.block_review_calls)
        self.assertEqual(report.calls, estimate.total_calls)
        self.assertEqual(sum(len(item.text) for item in book.blocks()),
                         estimate.text_characters)
        self.assertGreater(estimate.estimated_input_characters,
                           estimate.text_characters)

    def test_progress_reports_completed_calls_and_cancellation_stops_audit(self):
        backend = RecordingBackend()
        updates = []

        with self.assertRaises(AuditCancelledError):
            audit(
                self.epub, backend=backend,
                config=AuditConfig(max_blocks_per_batch=1),
                progress=lambda current, total, phase:
                updates.append((current, total, phase)),
                cancelled=lambda: bool(updates),
            )

        estimate = estimate_audit(
            self.epub, config=AuditConfig(max_blocks_per_batch=1))
        self.assertEqual(
            [(1, estimate.total_calls, "book_overview")], updates)
        self.assertEqual(1, len(backend.calls))

    def test_overview_is_batched_and_coverage_tracks_distinct_documents(self):
        epub = Path(self.temp.name) / "many.epub"
        create_multi_document_epub(epub)
        config = AuditConfig(
            max_documents_per_overview_batch=2,
            max_overview_characters_per_batch=100_000,
        )
        estimate = estimate_audit(epub, config=config)
        backend = RecordingBackend()

        report = audit(epub, backend=backend, config=config)
        overviews = [call[0] for call in backend.calls
                     if call[0]["audit_pass"] == "book_overview"]

        self.assertEqual(2, estimate.overview_calls)
        self.assertEqual(2, len(overviews))
        self.assertEqual([1, 2], [item["overview_batch_index"]
                                  for item in overviews])
        self.assertTrue(all(item["overview_batch_count"] == 2
                            for item in overviews))
        self.assertTrue(all(len(item["documents"]) <= 2
                            for item in overviews))
        overview_calls = [call for call in backend.calls
                          if call[0]["audit_pass"] == "book_overview"]
        for _, _, schema in overview_calls:
            scopes = schema["json_schema"]["schema"]["properties"][
                "findings"]["items"]["properties"]["scope"]["enum"]
            self.assertEqual(["document"], scopes)
        submitted = {document["href"] for item in overviews
                     for document in item["documents"]}
        self.assertEqual(report.coverage.documents_total, len(submitted))
        self.assertEqual(report.calls, estimate.total_calls)
        self.assertEqual(2, estimate.largest_overview_documents)
        self.assertLessEqual(
            estimate.largest_overview_input_characters,
            config.max_overview_characters_per_batch)
        self.assertLessEqual(
            estimate.largest_overview_input_characters,
            estimate.estimated_input_characters)

    def test_invalid_batch_limits_fail_before_any_network_call(self):
        backend = RecordingBackend()
        with self.assertRaises(ValueError):
            AuditConfig(max_blocks_per_batch=0)
        with self.assertRaises(ValueError):
            AuditConfig(max_documents_per_overview_batch=0)
        with self.assertRaises(ValueError):
            AuditConfig(max_overview_characters_per_batch=999)
        self.assertEqual([], backend.calls)

    def test_single_oversized_overview_fails_before_network(self):
        epub = Path(self.temp.name) / "oversized.epub"
        create_multi_document_epub(
            epub, documents=1, passage_repetitions=300)
        backend = RecordingBackend()

        with self.assertRaisesRegex(
                ValueError, "reduce document_excerpt_characters"):
            audit(
                epub, backend=backend,
                config=AuditConfig(
                    document_excerpt_characters=5_000,
                    max_overview_characters_per_batch=1_000,
                ),
            )

        self.assertEqual([], backend.calls)


if __name__ == "__main__":
    unittest.main()
