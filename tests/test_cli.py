import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from segnatura import __version__
from segnatura.apparati import analizza_apparati
from segnatura.edition_profile import (create_edition_profile_payload,
                                       file_sha256)
from segnatura.cli import main
from segnatura.tools_cli import edition_profile_main
from tests.test_edition_profile import create_epub


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.epub = self.root / "book.epub"
        create_epub(self.epub)

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(list(arguments))
        return result, stdout.getvalue(), stderr.getvalue()

    def test_units_json_is_emitted_to_stdout(self):
        result, stdout, stderr = self.run_cli(
            str(self.epub), "--format", "units-json")

        self.assertEqual(0, result)
        self.assertEqual("", stderr)
        payload = json.loads(stdout)
        self.assertEqual("segnatura-extraction-1", payload["schema"])
        self.assertEqual("Edition Profile Test", payload["book"]["title"])
        self.assertGreater(len(payload["units"]), 0)

    def test_output_option_writes_the_requested_file(self):
        output = self.root / "extraction.txt"
        result, stdout, stderr = self.run_cli(
            str(self.epub), "--output", str(output))

        self.assertEqual(0, result)
        self.assertEqual("", stdout)
        self.assertIn(f"Wrote {output}", stderr)
        self.assertIn("The first passage of the work", output.read_text(
            encoding="utf-8"))

    def test_edition_profile_option_changes_extraction(self):
        analysis = analizza_apparati(self.epub)
        href = analysis.blocchi[0].esito_base.documento.href
        payload = create_edition_profile_payload(
            {
                "sha256": file_sha256(self.epub),
                "path": self.epub.name,
                "title": "Edition Profile Test",
                "language": "en",
            },
            [{"href": href, "label": "index"}],
            [],
            created_at="2026-08-30T00:00:00+00:00",
            segnatura_version=__version__,
        )
        profile = self.root / "book.segnatura.json"
        profile.write_text(json.dumps(payload), encoding="utf-8")

        result, stdout, _ = self.run_cli(
            str(self.epub), "--edition-profile", str(profile),
            "--format", "units-json")

        self.assertEqual(0, result)
        self.assertEqual([], json.loads(stdout)["units"])

        result, stdout, _ = self.run_cli(
            str(self.epub), "--edition-profile", str(profile),
            "--category", "index", "--format", "units-json")

        self.assertEqual(0, result)
        units = json.loads(stdout)["units"]
        self.assertGreater(len(units), 0)
        self.assertEqual({"index"}, {item["category"] for item in units})

        result, stdout, _ = self.run_cli(
            str(self.epub), "--edition-profile", str(profile),
            "--category", "all", "--format", "units-json")

        self.assertEqual(0, result)
        all_units = json.loads(stdout)["units"]
        self.assertEqual(units, all_units)

    def test_invalid_input_exits_with_a_cli_error(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = main([str(self.root / "missing.epub")])

        self.assertEqual(2, result)
        self.assertIn("segnatura: error:", stderr.getvalue())

    def test_version_flag_reports_the_package_version(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as caught:
            main(["--version"])

        self.assertEqual(0, caught.exception.code)
        self.assertEqual(f"segnatura {__version__}\n", stdout.getvalue())

    def test_edition_profile_command_uses_current_root_when_omitted(self):
        with patch("segnatura.tools_cli.Path.cwd",
                   return_value=self.root), patch(
                       "segnatura.gold_app.run") as run:
            result = edition_profile_main(["--no-browser"])

        self.assertEqual(0, result)
        self.assertEqual(self.root, run.call_args.args[0])
        self.assertEqual(8766, run.call_args.kwargs["port"])


if __name__ == "__main__":
    unittest.main()
