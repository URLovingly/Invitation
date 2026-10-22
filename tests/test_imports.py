"""Guest spreadsheet parsing and upload preview tests."""
import io
import zipfile

import pytest

from server.imports import parse_guest_file


def xlsx_file(target="/xl/worksheets/sheet1.xml"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Guests" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Target="{target}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            '</Relationships>',
        )
        workbook.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<si><t>Guest Name</t></si><si><t>WhatsApp Number</t></si><si><t>Personal Note</t></si>'
            '<si><t>Rahul Sharma &amp; Family</t></si><si><t>9876543210</t></si>'
            '<si><t>Join us!</t></si></sst>',
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '<c r="C1" t="s"><v>2</v></c></row><row r="2"><c r="A2" t="s"><v>3</v></c>'
            '<c r="B2" t="s"><v>4</v></c><c r="C2" t="s"><v>5</v></c></row></sheetData></worksheet>',
        )
    return output.getvalue()


def test_parse_csv_with_optional_fields():
    guests = parse_guest_file(
        "guests.csv",
        b"Guest Name,WhatsApp Number,Personal Note\r\nRahul Sharma,9876543210,Join us!\r\n",
    )
    assert guests == [{"guest_name": "Rahul Sharma", "guest_phone": "9876543210", "custom_note": "Join us!"}]


def test_parse_xlsx_first_worksheet():
    guests = parse_guest_file("guests.xlsx", xlsx_file())
    assert guests == [{
        "guest_name": "Rahul Sharma & Family", "guest_phone": "9876543210", "custom_note": "Join us!"
    }]


@pytest.mark.parametrize(
    "filename,content,message",
    [
        ("guests.csv", b"phone,note\n123,Hello\n", "guest_name column"),
        ("guests.csv", b"guest_name\n\n", "No guest rows"),
        ("guests.csv", b"guest_name\n\n" + b"\n".join([b"Name"] * 501), "maximum of 500"),
        ("guests.xls", b"not supported", ".csv or .xlsx"),
        ("guests.xlsx", b"not a workbook", "valid .xlsx"),
    ],
)
def test_reject_invalid_guest_files(filename, content, message):
    with pytest.raises(ValueError, match=message):
        parse_guest_file(filename, content)


def test_reject_oversized_guest_file():
    with pytest.raises(ValueError, match="2 MB or smaller"):
        parse_guest_file("guests.csv", b"x" * (2 * 1024 * 1024 + 1))


def test_authenticated_preview_returns_guests_and_plan_capacity(api):
    from tests.conftest import create_event

    event = create_event(api, "free")
    studio = api.get("/studio")
    assert studio.status_code == 200
    assert b'Download CSV template' in studio.data
    assert b'Guest%20Name%2CWhatsApp%20Number%2CPersonal%20Note' in studio.data
    response = api.post(
        f"/api/events/{event['id']}/guest-import/preview",
        data={"file": (io.BytesIO(b"guest_name,guest_phone\nRahul,9876543210\n"), "guests.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["guests"][0]["guest_name"] == "Rahul"
    assert body["event"]["links_remaining"] == 5


def test_preview_rejects_invalid_file_and_other_customers(api, make_api):
    from tests.conftest import create_event

    event = create_event(api, "free")
    invalid = api.post(
        f"/api/events/{event['id']}/guest-import/preview",
        data={"file": (io.BytesIO(b"phone\n123\n"), "guests.csv")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400 and invalid.get_json()["error"] == "invalid_file"
    other = make_api("other@gmail.com")
    hidden = other.post(
        f"/api/events/{event['id']}/guest-import/preview",
        data={"file": (io.BytesIO(b"guest_name\nRahul\n"), "guests.csv")},
        content_type="multipart/form-data",
    )
    assert hidden.status_code == 404