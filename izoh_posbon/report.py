import json
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Iterable

import xlsxwriter


ACTION_NAMES = {
    "review": "Tekshiruv",
    "delete": "O'chirish",
    "ban": "Bloklash",
}


def _reason_text(raw: str) -> str:
    try:
        reasons = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return raw or ""
    return "; ".join(
        str(item.get("detail") or item.get("code") or "")
        for item in reasons
        if isinstance(item, dict)
    )


def build_excel_report(
    events: Iterable[Dict[str, Any]], chat_title: str, generated_at: datetime
) -> bytes:
    rows = list(events)
    output = BytesIO()
    workbook = xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
            # Telegram'dan kelgan `=...` matn Excel formulaga aylanmasin.
            "strings_to_formulas": False,
            "strings_to_urls": False,
        },
    )
    workbook.set_properties(
        {
            "title": "Izoh Posbon moderatsiya hisoboti",
            "subject": chat_title,
            "author": "Izoh Posbon Bot",
        }
    )
    sheet = workbook.add_worksheet("Spam hisoboti")
    sheet.hide_gridlines(2)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(6)
    sheet.freeze_panes(7, 0)

    title = workbook.add_format(
        {"font_name": "Arial", "font_size": 15, "bold": True, "font_color": "#172033"}
    )
    meta = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "italic": True, "font_color": "#5B6475"}
    )
    metric_label = workbook.add_format(
        {"font_name": "Arial", "bold": True, "font_color": "#334155"}
    )
    metric_value = workbook.add_format(
        {"font_name": "Arial", "bold": True, "font_color": "#0F766E", "num_format": "#,##0"}
    )
    date_format = workbook.add_format(
        {"font_name": "Arial", "num_format": "yyyy-mm-dd hh:mm", "valign": "vcenter"}
    )
    text_format = workbook.add_format({"font_name": "Arial", "valign": "vcenter"})
    wrap_format = workbook.add_format(
        {"font_name": "Arial", "valign": "top", "text_wrap": True}
    )

    sheet.write(1, 0, "Izoh Posbon moderatsiya hisoboti", title)
    sheet.write(2, 0, "Guruh:", meta)
    sheet.write(2, 1, chat_title, meta)
    sheet.write(2, 4, "Yaratilgan:", meta)
    sheet.write_datetime(2, 5, generated_at, date_format)

    deletions = sum(1 for row in rows if row.get("action") == "delete")
    bans = sum(1 for row in rows if row.get("action") == "ban")
    average = round(sum(int(row.get("score") or 0) for row in rows) / len(rows), 1) if rows else 0
    metrics = [
        ("Jami hodisa", len(rows)),
        ("O'chirish", deletions),
        ("Bloklash", bans),
        ("O'rtacha risk", average),
    ]
    for index, (label, value) in enumerate(metrics):
        column = index * 2
        sheet.write(4, column, label, metric_label)
        sheet.write_number(4, column + 1, value, metric_value)

    headers = [
        "Sana",
        "Guruh",
        "User ID",
        "Ism",
        "Username",
        "Xabar ID",
        "Risk ball",
        "Qaror",
        "Sabablar",
        "Xabar",
    ]
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                datetime.fromtimestamp(int(row["created_at"])),
                row.get("chat_title") or chat_title,
                str(row.get("user_id") or ""),
                row.get("full_name") or "",
                ("@" + row["username"]) if row.get("username") else "",
                str(row.get("message_id") or ""),
                int(row.get("score") or 0),
                ACTION_NAMES.get(str(row.get("action")), str(row.get("action") or "")),
                _reason_text(str(row.get("reasons_json") or "")),
                row.get("message_text") or "",
            ]
        )

    first_row = 6
    last_row = first_row + len(table_rows)
    sheet.add_table(
        first_row,
        0,
        last_row,
        len(headers) - 1,
        {
            "name": "SpamEventsTable",
            "style": "Table Style Medium 2",
            "columns": [{"header": header} for header in headers],
            "data": table_rows,
        },
    )
    if table_rows:
        sheet.conditional_format(
            first_row + 1,
            6,
            last_row,
            6,
            {"type": "3_color_scale", "min_color": "#DCFCE7", "mid_color": "#FEF3C7", "max_color": "#FECACA"},
        )
        sheet.set_row(first_row, 24)
        for row_number in range(first_row + 1, last_row + 1):
            sheet.set_row(row_number, 34)

    sheet.set_column("A:A", 18, date_format)
    sheet.set_column("B:B", 22, text_format)
    sheet.set_column("C:C", 16, text_format)
    sheet.set_column("D:D", 22, text_format)
    sheet.set_column("E:E", 20, text_format)
    sheet.set_column("F:F", 13, text_format)
    sheet.set_column("G:G", 11, text_format)
    sheet.set_column("H:H", 13, text_format)
    sheet.set_column("I:I", 42, wrap_format)
    sheet.set_column("J:J", 50, wrap_format)
    workbook.close()
    return output.getvalue()
