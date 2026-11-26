from PIL import Image

from shop.core.supplier_invoices import render_pdf_first_page


def test_render_pdf_first_page(tmp_path):
    pdf = tmp_path / "scan.pdf"
    Image.new("RGB", (400, 600), "white").save(pdf, "PDF")
    out = tmp_path / "scan.png"
    assert render_pdf_first_page(pdf, out) == 1
    with Image.open(out) as img:
        assert img.size[1] > img.size[0] > 0


def test_hangve_pdf_is_rendered_kept_and_sent_back_as_sharp_image(conn, tmp_path, monkeypatch):
    import shop.core.supplier_invoices as si

    pdf = tmp_path / "in.pdf"
    Image.new("RGB", (400, 600), "white").save(pdf, "PDF")
    sent = []

    def fake_request(url, secret, path, body=None, timeout=60.0):
        if path.startswith("/sync/photo-blob"):
            return pdf.read_bytes()
        sent.append((path, body))
        return b"{}"

    monkeypatch.setattr(si, "_worker_request", fake_request)
    monkeypatch.setattr(
        si,
        "fetch_sync_json",
        lambda *a, **k: {
            "photos": [
                {
                    "key": "photo:0001761000900000-p1",
                    "note": "pdf test",
                    "mime": "application/pdf",
                    "blob": "photoblob:0001761000900000-p1",
                    "reply_chat_id": "555",
                    "reply_to_message_id": 77,
                }
            ]
        },
    )
    photos_dir = tmp_path / "photos"
    assert si.sync_photos_from_bot(conn, "https://w.test", "secret", photos_dir) == 1

    invoice = si.list_invoices(conn)[0]
    assert (photos_dir / invoice["photo_filename"]).exists()
    assert list(photos_dir.glob("*-telegram.pdf"))  # original PDF kept
    (path, body), = sent
    assert path == "/hangve/reply" and body["chat_id"] == "555" and body["reply_to_message_id"] == 77
    assert body["imageBase64"]
