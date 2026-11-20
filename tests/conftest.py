"""Dựng PDF tối giản trong bộ nhớ cho các test biên (không cần thư viện ngoài)."""

import hashlib

import pytest


PASSWORD_PAD = bytes.fromhex(
    "28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A"
)
DOCUMENT_ID = bytes.fromhex("00112233445566778899aabbccddeeff")


def rc4(key, data):
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    i = j = 0
    result = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        result.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(result)


def build_pdf(pages, page_extra=b"", encryption=None):
    """pages: danh sách chuỗi ASCII, mỗi chuỗi là một trang ("" = trang trắng).

    encryption: None, "owner_only" (mật khẩu người dùng rỗng) hoặc "user_password".
    """
    owner_entry = rc4(hashlib.md5(b"owner" + PASSWORD_PAD[:27]).digest()[:5], PASSWORD_PAD)
    file_key = hashlib.md5(
        PASSWORD_PAD + owner_entry + (-4).to_bytes(4, "little", signed=True) + DOCUMENT_ID
    ).digest()[:5]

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages:
        content = b""
        if text:
            content = b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1") + b") Tj ET"
        content_number = len(objects) + 1
        if encryption == "owner_only":
            object_key = hashlib.md5(
                file_key + content_number.to_bytes(3, "little") + b"\x00\x00"
            ).digest()[:10]
            content = rc4(object_key, content)
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " + page_extra
            + b" /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_number
        )
        kids.append(len(objects))
    objects[1] = (
        b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % kid for kid in kids)
        + b"] /Count %d >>" % len(kids)
    )

    trailer_extra = b""
    if encryption is not None:
        user_entry = rc4(file_key, PASSWORD_PAD)
        if encryption == "user_password":
            user_entry = b"\x22" * 32
        objects.append(
            b"<< /Filter /Standard /V 1 /R 2 /O <" + owner_entry.hex().encode()
            + b"> /U <" + user_entry.hex().encode() + b"> /P -4 >>"
        )
        document_id = DOCUMENT_ID.hex().encode()
        trailer_extra = (
            b" /Encrypt %d 0 R /ID [<" % len(objects) + document_id
            + b"> <" + document_id + b">]"
        )

    output = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_offset = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R" % (len(objects) + 1) + trailer_extra
    output += b" >>\nstartxref\n%d\n%%%%EOF\n" % xref_offset
    return output


@pytest.fixture
def make_pdf():
    return build_pdf
