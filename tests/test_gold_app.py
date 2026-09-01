import json
import io
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from segnatura.apparati import analizza_apparati
from segnatura.gold_app import SCHEMA_EXPORT, SessionStore, create_app
from segnatura.llm import (LLMError, OpenAICompatibleBackend,
                           StructuredResponse)
from tests.test_audit import RecordingBackend


def crea_epub(percorso: Path) -> None:
    container = '''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    opf = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">test</dc:identifier><dc:title>Libro di prova</dc:title>
    <dc:language>it</dc:language><dc:publisher>Editore locale</dc:publisher>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine><itemref idref="chapter"/></spine>
</package>'''
    chapter = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Capitolo</title>
<link rel="stylesheet" href="style.css"/></head><body><section>
<h1>Capitolo uno</h1><p>Questo è il testo originale della pagina.</p>
</section></body></html>'''
    with zipfile.ZipFile(percorso, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)
        archive.writestr("OEBPS/style.css", "body { color: #123; }")


class GoldAppTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.epub = self.root / "Autore" / "Libro" / "Libro.epub"
        self.epub.parent.mkdir(parents=True)
        crea_epub(self.epub)
        self.app = create_app(self.root)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def apri(self):
        response = self.client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"})
        self.assertEqual(200, response.status_code)
        return response.get_json()

    def test_web_tool_accepts_only_matching_loopback_host_and_origin(self):
        for host in ("localhost", "localhost:8765", "127.0.0.1:8765",
                     "[::1]:8765"):
            with self.subTest(host=host):
                response = self.client.get("/api/books", headers={"Host": host})
                self.assertEqual(200, response.status_code)
                self.assertEqual("same-origin", response.headers[
                    "Cross-Origin-Resource-Policy"])
                self.assertEqual("SAMEORIGIN", response.headers[
                    "X-Frame-Options"])

        for host in ("attacker.example", "127.0.0.1.attacker.example",
                     "127.0.0.1:invalid", "user@localhost:8765"):
            with self.subTest(host=host):
                response = self.client.get("/api/books", headers={"Host": host})
                self.assertEqual(400, response.status_code)

        rejected = self.client.post(
            "/api/open",
            json={"path": "Autore/Libro/Libro.epub"},
            headers={
                "Host": "127.0.0.1:8765",
                "Origin": "https://attacker.example",
            },
        )
        self.assertEqual(403, rejected.status_code)

        accepted = self.client.post(
            "/api/open",
            json={"path": "Autore/Libro/Libro.epub"},
            headers={
                "Host": "127.0.0.1:8765",
                "Origin": "http://127.0.0.1:8765",
            },
        )
        self.assertEqual(200, accepted.status_code)

    def test_review_state_is_session_only(self):
        opened = self.apri()
        document = opened["documents"][0]
        self.client.put(
            f"/api/books/{opened['id']}/annotations/document",
            json={"href": document["href"], "label": "note"},
        )
        self.assertTrue(self.client.get(
            f"/api/books/{opened['id']}/annotations").get_json()["documents"])

        restarted = create_app(self.root)
        restarted.config["TESTING"] = True
        client = restarted.test_client()
        reopened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        self.assertEqual({}, client.get(
            f"/api/books/{reopened['id']}/annotations").get_json()["documents"])
        self.assertFalse(any(self.root.rglob("*.sqlite*")))

    def test_catalogo_e_apertura_non_espongono_previsione(self):
        catalog = self.client.get("/api/books").get_json()
        self.assertEqual(1, len(catalog["books"]))
        opened = self.apri()
        self.assertEqual("Libro di prova", opened["title"])
        self.assertEqual("it", opened["language"])
        self.assertEqual(1, len(opened["documents"]))
        encoded = json.dumps(opened)
        self.assertNotIn("prediction", encoded)
        self.assertNotIn("categoria_predetta", encoded)
        first = opened["documents"][0]["blocks"][0]
        self.assertIn(first["deterministic_category"], {
            "work_text", "note", "bibliography", "index", "paratext"})
        self.assertFalse(opened["audit_available"])

    def test_epub_can_be_selected_from_disk_for_this_session(self):
        response = self.client.post(
            "/api/import",
            data={"epub": (io.BytesIO(self.epub.read_bytes()),
                            "Scelto dal disco.epub")},
            content_type="multipart/form-data",
        )
        self.assertEqual(201, response.status_code)
        selected = response.get_json()["book"]
        self.assertTrue(selected["selected_from_disk"])
        self.assertTrue(selected["path"].startswith("selected/"))
        catalog = self.client.get("/api/books").get_json()["books"]
        self.assertEqual(2, len(catalog))
        opened = self.client.post(
            "/api/open", json={"path": selected["path"]})
        self.assertEqual(200, opened.status_code)
        opened_payload = opened.get_json()
        self.assertEqual("Libro di prova", opened_payload["title"])
        document = opened_payload["documents"][0]
        self.client.put(
            f"/api/books/{opened_payload['id']}/annotations/document",
            json={"href": document["href"], "label": "work_text"},
        )
        exported = self.client.get(
            f"/api/books/{opened_payload['id']}/export")
        self.assertEqual(
            "0", exported.headers["X-Segnatura-Saved-Next-To-EPUB"])

    def test_disk_selection_rejects_non_epub_and_invalid_archives(self):
        wrong_extension = self.client.post(
            "/api/import",
            data={"epub": (io.BytesIO(b"text"), "not-an-epub.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(400, wrong_extension.status_code)
        invalid_archive = self.client.post(
            "/api/import",
            data={"epub": (io.BytesIO(b"not a zip"), "broken.epub")},
            content_type="multipart/form-data",
        )
        self.assertEqual(400, invalid_archive.status_code)

    def test_audit_llm_resta_separato_e_solo_le_decisioni_approvate_esportano(self):
        app = create_app(
            self.root, audit_backend=RecordingBackend(),
        )
        app.config["TESTING"] = True
        client = app.test_client()
        opened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        self.assertTrue(opened["audit_available"])
        self.assertIsNone(opened["audit_estimate"])
        estimate = client.get(
            f"/api/books/{opened['id']}/audit-estimate").get_json()
        self.assertGreaterEqual(estimate["total_calls"], 2)
        self.assertGreater(estimate["blocks"], 0)
        original_category = opened["documents"][0]["blocks"][0][
            "deterministic_category"]

        started = client.post(
            f"/api/books/{opened['id']}/audit")
        self.assertEqual(202, started.status_code)
        run = started.get_json()
        for _ in range(200):
            run = client.get(f"/api/audits/{run['run_id']}").get_json()
            if run["status"] != "running":
                break
            time.sleep(.01)
        self.assertEqual("completed", run["status"])
        self.assertTrue(run["report"]["coverage"]["complete"])
        finding = next(item for item in run["report"]["findings"]
                       if item["can_create_edition_profile_override"])

        # Merely running the LLM never creates a correction.
        no_export = client.get(f"/api/books/{opened['id']}/export")
        self.assertEqual(409, no_export.status_code)
        reopened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        self.assertEqual(
            original_category,
            reopened["documents"][0]["blocks"][0]["deterministic_category"],
        )

        accepted = client.put(
            f"/api/audits/{run['run_id']}/findings/{finding['id']}",
            json={"decision": "accepted"},
        )
        self.assertEqual(200, accepted.status_code)
        exported = client.get(
            f"/api/books/{opened['id']}/export").get_json()
        self.assertEqual(1, len(exported["blocks"]))
        self.assertEqual("note", exported["blocks"][0]["category"])

    def test_audit_reports_progress_and_can_be_cancelled(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingBackend(RecordingBackend):
            def request_structured(self, *args, **kwargs):
                entered.set()
                release.wait(2)
                return super().request_structured(*args, **kwargs)

        app = create_app(
            self.root, audit_backend=BlockingBackend(),
        )
        app.config["TESTING"] = True
        client = app.test_client()
        opened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        started = client.post(
            f"/api/books/{opened['id']}/audit").get_json()
        self.assertTrue(entered.wait(1))
        self.assertGreater(started["progress_total"], 0)
        self.assertEqual(0, started["progress_current"])

        stopping = client.post(
            f"/api/audits/{started['run_id']}/cancel")
        self.assertEqual(202, stopping.status_code)
        self.assertEqual("cancelling", stopping.get_json()["status"])
        release.set()

        run = stopping.get_json()
        for _ in range(200):
            run = client.get(
                f"/api/audits/{started['run_id']}").get_json()
            if run["status"] == "cancelled":
                break
            time.sleep(.01)
        self.assertEqual("cancelled", run["status"])
        self.assertEqual(1, run["progress_current"])

    def test_llm_configuration_is_session_only_and_hides_the_api_key(self):
        secret = "secret-value-that-must-not-be-stored"
        response = self.client.put("/api/llm/config", json={
            "provider": "openai_compatible",
            "base_url": "https://provider.example/v1",
            "model": "remote-model",
            "api_key": secret,
            "timeout": 120,
        })

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual({
            "configured": True,
            "provider": "OpenAI-compatible",
            "model": "remote-model",
            "timeout_per_call": 120.0,
        }, payload)
        self.assertNotIn(secret, json.dumps(payload))
        self.assertFalse(any(self.root.rglob("*.sqlite*")))
        self.assertFalse((self.root / ".segnatura").exists())

    def test_model_discovery_uses_draft_credentials_without_saving_them(self):
        secret = "temporary-discovery-secret"
        with patch.object(
                OpenAICompatibleBackend, "discover_models",
                return_value=["model-a", "model-b"]):
            response = self.client.post("/api/llm/models", json={
                "provider": "openai_compatible",
                "base_url": "https://provider.example/v1",
                "api_key": secret,
                "timeout": 30,
            })

        self.assertEqual(200, response.status_code)
        self.assertEqual(["model-a", "model-b"],
                         response.get_json()["models"])
        self.assertFalse(self.client.get(
            "/api/llm/config").get_json()["configured"])
        self.assertNotIn(secret, response.get_data(as_text=True))
        self.assertFalse(any(self.root.rglob("*.sqlite*")))
        self.assertFalse((self.root / ".segnatura").exists())

    def test_connection_probe_checks_structured_output_without_saving(self):
        result = StructuredResponse(
            data={"ok": True}, model="verified-model",
            network_attempts=1)
        with patch.object(
                OpenAICompatibleBackend, "request_structured",
                return_value=result) as request_structured:
            response = self.client.post("/api/llm/test", json={
                "provider": "openai_compatible",
                "base_url": "https://provider.example/v1",
                "model": "verified-model",
                "api_key": "temporary-test-secret",
                "timeout": 30,
            })

        self.assertEqual(200, response.status_code)
        self.assertEqual({
            "ok": True,
            "provider": "OpenAI-compatible",
            "model": "verified-model",
        }, response.get_json())
        self.assertFalse(self.client.get(
            "/api/llm/config").get_json()["configured"])
        self.assertFalse(request_structured.call_args.kwargs["retry_invalid"])

    def test_connection_errors_do_not_echo_draft_api_keys(self):
        secret = "draft-key-that-must-not-leak"
        with patch.object(
                OpenAICompatibleBackend, "discover_models",
                side_effect=LLMError(f"Authorization: Bearer {secret}")):
            response = self.client.post("/api/llm/models", json={
                "provider": "openai_compatible",
                "base_url": "https://provider.example/v1",
                "api_key": secret,
                "timeout": 30,
            })

        self.assertEqual(502, response.status_code)
        self.assertNotIn(secret, response.get_data(as_text=True))

    def test_multiple_audits_remain_distinct_in_chronological_history(self):
        app = create_app(
            self.root, audit_backend=RecordingBackend(),
        )
        app.config["TESTING"] = True
        client = app.test_client()
        opened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()

        run_ids = []
        for _ in range(2):
            run = client.post(
                f"/api/books/{opened['id']}/audit").get_json()
            run_ids.append(run["run_id"])
            for _ in range(200):
                run = client.get(f"/api/audits/{run['run_id']}").get_json()
                if run["status"] == "completed":
                    break
                time.sleep(.01)

        history = client.get(
            f"/api/books/{opened['id']}/audits").get_json()["audits"]
        self.assertEqual(run_ids, [item["run_id"] for item in history])
        self.assertTrue(all(item["status"] == "completed" for item in history))
        self.assertTrue(all(item["report"]["models"] == ["audit-test-model"]
                            for item in history))

    def test_worker_errors_are_redacted_before_display(self):
        class SecretFailureBackend:
            def request_structured(self, *args, **kwargs):
                raise RuntimeError(
                    "https://provider.example/v1?api_key=very-secret "
                    "Authorization: Bearer another-secret")

        app = create_app(
            self.root, audit_backend=SecretFailureBackend(),
        )
        app.config["TESTING"] = True
        client = app.test_client()
        opened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        run = client.post(f"/api/books/{opened['id']}/audit").get_json()
        for _ in range(200):
            run = client.get(f"/api/audits/{run['run_id']}").get_json()
            if run["status"] == "failed":
                break
            time.sleep(.01)

        self.assertEqual("failed", run["status"])
        self.assertNotIn("very-secret", run["error"])
        self.assertNotIn("another-secret", run["error"])
        self.assertIn("[redacted]", run["error"])

    def test_manual_annotation_wins_over_accepted_audit_suggestion(self):
        app = create_app(
            self.root, audit_backend=RecordingBackend(),
        )
        app.config["TESTING"] = True
        client = app.test_client()
        opened = client.post(
            "/api/open", json={"path": "Autore/Libro/Libro.epub"}
        ).get_json()
        block = opened["documents"][0]["blocks"][0]
        run = client.post(f"/api/books/{opened['id']}/audit").get_json()
        for _ in range(200):
            run = client.get(f"/api/audits/{run['run_id']}").get_json()
            if run["status"] != "running":
                break
            time.sleep(.01)
        finding = next(item for item in run["report"]["findings"]
                       if item["can_create_edition_profile_override"])
        client.put(
            f"/api/audits/{run['run_id']}/findings/{finding['id']}",
            json={"decision": "accepted"},
        )
        client.put(
            f"/api/books/{opened['id']}/annotations/block",
            json={"block_id": block["id"], "label": "bibliography",
                  "note": "manual decision"},
        )

        exported = client.get(
            f"/api/books/{opened['id']}/export").get_json()
        self.assertEqual("bibliography", exported["blocks"][0]["category"])

    def test_default_store_is_memory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(root)
            app.config["TESTING"] = True
            service = app.extensions["segnatura_gold"]
            self.assertIsInstance(service.store, SessionStore)
            self.assertFalse(any(root.rglob("*.sqlite*")))
            self.assertFalse((root / ".segnatura").exists())

    def test_edition_profile_interface_has_two_languages(self):
        home = self.client.get("/").get_data(as_text=True)
        self.assertIn('<html lang="en">', home)
        for language in ("en", "it"):
            self.assertIn(f'data-locale="{language}"', home)
        for language in ("es", "fr", "de"):
            self.assertNotIn(f'data-locale="{language}"', home)
        self.assertLess(home.index('data-locale="en"'),
                        home.index('data-locale="it"'))
        self.assertNotIn('Only on this computer', home)
        self.assertIn("Edition Profile", home)
        self.assertIn('id="export-book" class="primary export-action"', home)
        self.assertIn("disabled>Export profile", home)
        self.assertNotIn('<p class="panel-kicker"><span>01</span>', home)
        self.assertIn('id="llm-dialog" class="settings-dialog"', home)
        self.assertIn('id="open-llm-settings"', home)
        self.assertIn('id="load-llm-models"', home)
        self.assertIn('id="test-llm-config"', home)
        self.assertIn('id="llm-model-options"', home)
        self.assertIn('class="llm-advanced"', home)
        self.assertNotIn('id="llm-settings"', home)
        self.assertLess(home.index('id="manual-context"'),
                        home.index('id="manual-correction"'))
        self.assertLess(home.index('id="manual-correction"'),
                        home.index('</aside>'))
        self.assertIn('class="annotation card review-control-bar"', home)
        self.assertNotIn('class="annotation card profile-editor-row"', home)
        self.assertIn('id="change-book" class="quiet home-button"', home)
        self.assertIn('id="browse-epub"', home)
        self.assertIn('id="epub-file" type="file"', home)
        self.assertIn('data-i18n="home" hidden>Home</button>', home)
        self.assertLess(home.index('id="open-llm-settings"'),
                        home.index('id="change-book"'))
        self.assertLess(home.index('id="edition-profile-home"'),
                        home.index('class="welcome-workflow"'))
        self.assertNotIn('id="document-uncertain"', home)
        self.assertNotIn('id="block-uncertain"', home)
        self.assertIn('id="estimate-audit" class="quiet estimate-action"', home)
        self.assertNotIn('id="suggestion-list"', home)

        app_response = self.client.get("/static/app.js")
        try:
            app_script = app_response.get_data(as_text=True)
        finally:
            app_response.close()
        for language in ("it", "en"):
            self.assertIn(f"  {language}: {{", app_script)
        self.assertIn("storedLocale : 'en'", app_script)
        self.assertNotIn("'unsure'", app_script)
        self.assertNotIn("-uncertain", app_script)
        self.assertNotIn("formatTimeoutCeiling", app_script)
        self.assertIn("can_create_edition_profile_override", app_script)
        self.assertIn("labels: {work_text:'Testo'", app_script)
        self.assertIn("labels: {work_text:'Text'", app_script)
        self.assertIn("export: 'Esporta profilo'", app_script)
        self.assertIn("wholeDocument: 'Intera sezione EPUB'", app_script)
        self.assertIn("correzione non esportata", app_script)
        self.assertIn("beforeunload", app_script)
        self.assertIn("confirmLeavingBook", app_script)

    def test_render_originale_inietta_evidenziazione_e_blocca_script(self):
        opened = self.apri()
        block_id = opened["documents"][0]["blocks"][0]["id"]
        response = self.client.get(
            f"/epub/{opened['id']}/OEBPS/chapter.xhtml?block={block_id}")
        self.assertEqual(200, response.status_code)
        text = response.get_data(as_text=True)
        self.assertIn("Questo è il testo originale", text)
        self.assertIn("segnatura-target", text)
        self.assertIn("segnatura-range-preview", text)
        self.assertIn("segnatura-ranges", text)
        self.assertIn('"start": 0', text)
        self.assertIn("script-src 'nonce-", response.headers["Content-Security-Policy"])
        self.assertIn("charset=utf-8", response.content_type)
        css = self.client.get(f"/epub/{opened['id']}/OEBPS/style.css")
        self.assertEqual(b"body { color: #123; }", css.data)

    def test_session_annotations_export_next_to_epub_without_source_text(self):
        opened = self.apri()
        document = opened["documents"][0]
        block = document["blocks"][0]
        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/document",
            json={"href": document["href"], "label": "work_text",
                  "note": ""})
        self.assertEqual(200, response.status_code)
        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/block",
            json={"block_id": block["id"], "label": "work_text",
                  "note": "decisione manuale"})
        self.assertEqual(200, response.status_code)
        saved = self.client.get(
            f"/api/books/{opened['id']}/annotations").get_json()
        self.assertEqual("work_text", saved["documents"][document["href"]]["label"])
        self.assertEqual("certain", saved["blocks"][block["id"]]["certainty"])
        export_response = self.client.get(
            f"/api/books/{opened['id']}/export")
        self.assertEqual(
            "1", export_response.headers["X-Segnatura-Saved-Next-To-EPUB"])
        exported = export_response.get_json()
        self.assertEqual(SCHEMA_EXPORT, exported["schema"])
        self.assertEqual(1, len(exported["documents"]))
        self.assertEqual(1, len(exported["blocks"]))
        self.assertEqual("work_text", exported["blocks"][0]["category"])
        self.assertEqual(opened["sha256"], exported["book"]["sha256"])
        self.assertNotIn("Questo è il testo originale", json.dumps(exported))
        profile_path = self.epub.with_name("Libro.segnatura.json")
        self.assertTrue(profile_path.is_file())
        self.assertEqual(exported, json.loads(profile_path.read_text("utf-8")))

    def test_profile_endpoint_rejects_non_decisive_annotations(self):
        opened = self.apri()
        document = opened["documents"][0]
        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/document",
            json={"href": document["href"], "label": "unsure",
                  "note": "ambiguous"})
        self.assertEqual(400, response.status_code)
        self.assertIn("invalid Edition Profile label",
                      response.get_json()["error"])
        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/document",
            json={"href": document["href"], "label": "work_text",
                  "certainty": "certain"})
        self.assertEqual(400, response.status_code)
        self.assertIn("certainty is not supported",
                      response.get_json()["error"])

    def test_manual_range_is_exported_and_applied(self):
        opened = self.apri()
        block = opened["documents"][0]["blocks"][0]
        detail = self.client.get(
            f"/api/books/{opened['id']}/blocks/{block['id']}").get_json()
        selected = "testo originale"
        start = detail["text"].index(selected)
        end = start + len(selected)

        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/range",
            json={"block_id": block["id"], "start": start, "end": end,
                  "label": "note"})
        self.assertEqual(200, response.status_code)
        saved_range = response.get_json()["range"]

        saved = self.client.get(
            f"/api/books/{opened['id']}/annotations").get_json()
        self.assertEqual("note", saved["ranges"][
            saved_range["range_id"]]["label"])

        exported = self.client.get(
            f"/api/books/{opened['id']}/export").get_json()
        self.assertEqual(1, len(exported["ranges"]))
        self.assertEqual(selected, detail["text"][
            exported["ranges"][0]["start"]:exported["ranges"][0]["end"]])

        epub = self.root / opened["path"]
        profile_path = self.epub.with_name("Libro.segnatura.json")
        self.assertEqual(exported, json.loads(profile_path.read_text("utf-8")))
        applied = analizza_apparati(
            epub, edition_profile=profile_path).prepara_ingestione()
        split = [unit for unit in applied.unita
                 if unit.blocco_id == block["id"]]
        self.assertEqual(detail["text"], "".join(unit.testo for unit in split))
        self.assertIn("nota", {unit.categoria for unit in split})
        self.assertTrue(applied.copertura.valida)

        deleted = self.client.delete(
            f"/api/books/{opened['id']}/annotations/range/"
            f"{saved_range['range_id']}")
        self.assertEqual(200, deleted.status_code)
        self.assertEqual({}, self.client.get(
            f"/api/books/{opened['id']}/annotations").get_json()["ranges"])

    def test_rifiuta_path_esterni_ed_etichette_sconosciute(self):
        self.assertIn(
            self.client.post("/api/open", json={"path": "../fuori.epub"}).status_code,
            {400, 404},
        )
        opened = self.apri()
        block = opened["documents"][0]["blocks"][0]
        response = self.client.put(
            f"/api/books/{opened['id']}/annotations/block",
            json={"block_id": block["id"], "label": "corpo inventato"})
        self.assertEqual(400, response.status_code)
        traversal = self.client.get(
            f"/epub/{opened['id']}/OEBPS/%2E%2E/content.opf")
        self.assertEqual(404, traversal.status_code)

if __name__ == "__main__":
    unittest.main()
