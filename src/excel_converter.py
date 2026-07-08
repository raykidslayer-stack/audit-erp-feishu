from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def prepare_audit_upload_file(source_path: Path, order_date: str) -> Path:
    target_path = source_path.parent / f"\u6bcf\u65e5\u8ba2\u5355_{order_date.replace('-', '')}.csv"
    if source_path.suffix.lower() == ".csv":
        if source_path.resolve() != target_path.resolve():
            target_path.write_bytes(source_path.read_bytes())
        return target_path

    if source_path.suffix.lower() != ".xlsx":
        raise RuntimeError(f"Unsupported ERP export file type: {source_path}")

    _xlsx_first_sheet_to_csv(source_path, target_path)
    return target_path


def _xlsx_first_sheet_to_csv(source_path: Path, target_path: Path) -> None:
    with zipfile.ZipFile(source_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name = _first_sheet_path(archive)
        rows = list(_iter_sheet_rows(archive, sheet_name, shared_strings))

    width = max((len(row) for row in rows), default=0)
    with target_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        for row in rows:
            writer.writerow(row + [""] * (width - len(row)))


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    for item in root.findall("a:si", _NS):
        parts = [node.text or "" for node in item.findall(".//a:t", _NS)]
        strings.append("".join(parts))
    return strings


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    first_sheet = workbook.find("a:sheets/a:sheet", _NS)
    if first_sheet is None:
        raise RuntimeError("ERP xlsx has no worksheet.")

    rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    if not rel_id:
        raise RuntimeError("ERP xlsx first worksheet has no relationship id.")

    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"]
            return "xl/" + target.lstrip("/")
    raise RuntimeError("Cannot resolve ERP xlsx first worksheet.")


def _iter_sheet_rows(
    archive: zipfile.ZipFile, sheet_name: str, shared_strings: list[str]
) -> list[list[str]]:
    root = ElementTree.fromstring(archive.read(sheet_name))
    for row in root.findall(".//a:sheetData/a:row", _NS):
        values: list[str] = []
        for cell in row.findall("a:c", _NS):
            column_index = _column_index(cell.attrib.get("r", ""))
            while len(values) < column_index:
                values.append("")
            values.append(_cell_text(cell, shared_strings))
        yield values


def _cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//a:t", _NS))

    value = cell.find("a:v", _NS)
    if value is None or value.text is None:
        return ""

    text = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(text)]
        except (ValueError, IndexError):
            return text
    return text


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        return 0
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1
