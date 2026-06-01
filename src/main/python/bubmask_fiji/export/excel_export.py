#!/usr/bin/env python3
"""Write a simple Excel bubble table from a BubMask measurement CSV."""

from __future__ import annotations

import argparse
import csv
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


OUTPUT_COLUMNS = [
    ("bubble_id", "Bubble ID"),
    ("measurement_status", "Status"),
    ("equivalent_diameter_calibrated", "Diameter"),
    ("diameter_unit", "Unit"),
    ("equivalent_diameter_px", "Diameter px"),
    ("area_px", "Area px"),
    ("centroid_x_px", "X px"),
    ("centroid_y_px", "Y px"),
    ("score", "Score"),
    ("calibration_status", "Calibration"),
    ("calibration_source", "Calibration source"),
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def cell_ref(col_idx: int, row_idx: int) -> str:
    letters = ""
    value = col_idx
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_idx}"


def number_or_text(value: str) -> tuple[str, str]:
    text = "" if value is None else str(value).strip()
    if text == "":
        return "inlineStr", ""
    try:
        float(text)
    except ValueError:
        return "inlineStr", text
    return "n", text


def sheet_xml(rows: list[dict[str, str]]) -> str:
    table_rows: list[list[str]] = [[header for _field, header in OUTPUT_COLUMNS]]
    for row in rows:
        out = []
        for field, _header in OUTPUT_COLUMNS:
            value = row.get(field, "")
            if field == "measurement_status" and value:
                value = "bubble"
            out.append(value)
        table_rows.append(out)

    xml_rows = []
    for row_idx, row in enumerate(table_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            cell_type, text = number_or_text(value)
            ref = cell_ref(col_idx, row_idx)
            if row_idx == 1 or cell_type == "inlineStr":
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(text))}</t></is></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{escape(str(text))}</v></c>')
        xml_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetData>'
        + "".join(xml_rows)
        + '</sheetData></worksheet>'
    )


def workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Bubble measurements" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def core_xml() -> str:
    stamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>BubMask-Fiji</dc:creator>'
        '<cp:lastModifiedBy>BubMask-Fiji</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
        '</cp:coreProperties>'
    )


def write_xlsx(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '</Types>'
        ))
        archive.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>'
        ))
        archive.writestr("docProps/core.xml", core_xml())
        archive.writestr("xl/workbook.xml", workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ))
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a BubMask Excel bubble table from measurement CSV.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-xlsx", required=True)
    args = parser.parse_args(argv)
    write_xlsx(load_csv(Path(args.input_csv).expanduser().resolve()), Path(args.output_xlsx).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
