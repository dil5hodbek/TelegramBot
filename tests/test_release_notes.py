import tempfile
import unittest
from pathlib import Path

from izoh_posbon.release_notes import deployment_fingerprint, render_update_notice


class ReleaseNotesTests(unittest.TestCase):
    def test_fingerprint_changes_when_code_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            source = package / "sample.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            first = deployment_fingerprint(package)
            source.write_text("VALUE = 2\n", encoding="utf-8")
            second = deployment_fingerprint(package)
        self.assertNotEqual(first, second)

    def test_notice_lists_changes_and_escapes_html(self) -> None:
        notice = render_update_notice(
            "abcdef1234567890",
            version="test<1>",
            changes=("Birinchi o'zgarish", "Xavfli <matn>"),
        )
        self.assertIn("abcdef123456", notice)
        self.assertIn("test&lt;1&gt;", notice)
        self.assertIn("• Birinchi o&#x27;zgarish", notice)
        self.assertIn("Xavfli &lt;matn&gt;", notice)


if __name__ == "__main__":
    unittest.main()
