import json
import unittest
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

from izoh_posbon.report import build_excel_report


class ReportTests(unittest.TestCase):
    def test_excel_report_is_valid_and_escapes_formula_text(self) -> None:
        events = [
            {
                "created_at": 1_725_000_000,
                "chat_title": "Test guruhi",
                "user_id": 123456789,
                "full_name": "Spam User",
                "username": "spam_user",
                "message_id": 77,
                "score": 95,
                "action": "ban",
                "reasons_json": json.dumps(
                    [{"code": "adult_text", "points": 55, "detail": "18+ ibora"}]
                ),
                "message_text": '=HYPERLINK("https://evil.example", "click")',
            }
        ]
        result = build_excel_report(events, "Test guruhi", datetime(2026, 9, 11, 22, 0))
        self.assertTrue(result.startswith(b"PK"))
        with ZipFile(BytesIO(result)) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            worksheet = archive.read("xl/worksheets/sheet1.xml")
            self.assertNotIn(b"HYPERLINK(\"https://evil.example", worksheet)


if __name__ == "__main__":
    unittest.main()

