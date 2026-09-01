import subprocess
import sys
import unittest
from pathlib import Path


class ComparisonExampleTest(unittest.TestCase):
    def test_generated_comparison_example_runs_and_filters_apparatus(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "examples" / "compare_extraction.py")],
            cwd=root, check=True, capture_output=True, text=True,
        )

        naive, remainder = completed.stdout.split(
            "=== Segnatura extraction (work text only) ===", 1)
        filtered, excluded = remainder.split("Visible strings excluded:", 1)
        self.assertIn("Contents", naive)
        self.assertIn("Copyright 2026 Example Press", naive)
        self.assertIn("Mara opened the workshop", filtered)
        self.assertNotIn("Copyright 2026 Example Press", filtered)
        self.assertNotIn("All rights reserved", filtered)
        self.assertIn("Contents; Copyright;", excluded)


if __name__ == "__main__":
    unittest.main()
