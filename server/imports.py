"""Parse CSV and XLSX guest lists without extracting untrusted archive files."""
import csv
import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
MAX_UNCOMPRESSED_BYTES = 5 * 1024 * 1024
MAX_ZIP_ENTRIES = 64

ALIASES = {
    "guest_name": {"guest_name", "name", "guest", "guest_or_family_name", "guest_family_name"},
    "guest_phone": {"guest_phone", "phone", "whatsapp", "whatsapp_number", "phone_number"},
    "custom_note": {"custom_note", "note", "personal_note", "message"},
}

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _normalise_header(value):
    value = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    for canonical, aliases in ALIASES.items():
        if value in aliases:
            return canonical
    return value


def _normalise_rows(rows):
    if not rows:
        raise ValueError("The spreadsheet has no header row or guest rows.")
    headers = [_normalise_header(value) for value in rows[0]]
    if "guest_name" not in headers:
        raise ValueError("Add a guest_name column. Optional columns: guest_phone, custom_note.")
    if len(headers) != len(set(headers)):
        raise ValueError("The spreadsheet contains duplicate column headers.")
    name_index = headers.index("guest_name")
    phone_index = headers.index("guest_phone") if "guest_phone" in headers else None
    note_index = headers.index("custom_note") if "custom_note" in headers else None
    guests = []
    for row_number, values in enumerate(rows[1:], start=2):
        if not any(str(value or "").strip() for value in values):
            continue
        def cell(index):
            return str(values[index] or "").strip() if index is not None and index < len(values) else ""

        guest_name = cell(name_index)
        if not guest_name:
            raise ValueError(f"Row {row_number} is missing a guest name.")
        if len(guest_name) > 100:
            raise ValueError(f"Guest name on row {row_number} is longer than 100 characters.")
        phone = cell(phone_index)
        if len(phone) > 40:
            raise ValueError(f"Phone number on row {row_number} is too long.")
        note = cell(note_index)
        if len(note) > 1000:
            raise ValueError(f"Personal note on row {row_number} is longer than 1000 characters.")
        guests.append({"guest_name": guest_name, "guest_phone": phone, "custom_note": note})
        if len(guests) > MAX_ROWS:
            raise ValueError(f"A maximum of {MAX_ROWS} guest rows can be imported at a time.")
    if not guests:
        raise ValueError("No guest rows were found beneath the header.")
    return guests


def _parse_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV files must use UTF-8 encoding.") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), dialect))
    except csv.Error as exc:
        raise ValueError("Could not read this CSV file.") from exc
    return _normalise_rows(rows)


def _column_index(reference):
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _xlsx_rows(content):
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("This is not a valid .xlsx spreadsheet.") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or sum(item.file_size for item in entries) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("This Excel spreadsheet is too large to process safely.")
        names = {item.filename for item in entries}
        if "xl/workbook.xml" not in names:
            raise ValueError("This is not a valid .xlsx spreadsheet.")
        try:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            sheet = workbook.find(f"{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet")
            if sheet is None:
                raise ValueError("The Excel spreadsheet has no worksheet.")
            relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target = next(
                rel.attrib["Target"] for rel in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
                if rel.attrib.get("Id") == relationship_id
            )
            sheet_path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
            if not sheet_path.startswith("xl/worksheets/") or sheet_path not in names:
                raise ValueError("The first Excel worksheet could not be found.")
            shared_strings = []
            if "xl/sharedStrings.xml" in names:
                shared_xml = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = [
                    "".join(text.text or "" for text in item.iter(f"{{{MAIN_NS}}}t"))
                    for item in shared_xml.findall(f"{{{MAIN_NS}}}si")
                ]
            root = ElementTree.fromstring(archive.read(sheet_path))
        except (KeyError, StopIteration, ElementTree.ParseError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise ValueError("Could not read the first Excel worksheet.") from exc

    rows = []
    for row_element in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        cells = {}
        for cell in row_element.findall(f"{{{MAIN_NS}}}c"):
            index = _column_index(cell.attrib.get("r", "A"))
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            value = value_node.text if value_node is not None else ""
            cell_type = cell.attrib.get("t")
            if cell_type == "s" and value:
                try:
                    value = shared_strings[int(value)]
                except (IndexError, ValueError) as exc:
                    raise ValueError("The Excel spreadsheet contains an invalid shared string.") from exc
            elif cell_type == "inlineStr":
                inline = cell.find(f"{{{MAIN_NS}}}is")
                value = "".join(text.text or "" for text in inline.iter(f"{{{MAIN_NS}}}t")) if inline is not None else ""
            cells[index] = value or ""
        if cells:
            values = [""] * (max(cells) + 1)
            for index, value in cells.items():
                values[index] = value
            rows.append(values)
    return rows


def parse_guest_file(filename, content):
    """Return normalized guest rows from a UTF-8 CSV or first-sheet XLSX file."""
    if not isinstance(content, bytes) or not content:
        raise ValueError("Choose a non-empty CSV or .xlsx file.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("The guest spreadsheet must be 2 MB or smaller.")
    extension = (filename or "").lower().rsplit(".", 1)[-1]
    if extension == "csv":
        return _parse_csv(content)
    if extension == "xlsx":
        return _normalise_rows(_xlsx_rows(content))
    raise ValueError("Upload a .csv or .xlsx file.")
