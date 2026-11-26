import json
import zipfile

import pytest

from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.products import upsert_product
from shop.core.transfer import TransferError, export_package, import_package, read_manifest
from shop.db.migrate import connect


def _seed(conn):
    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    customer_id = add_customer(conn, "Khach test", default_markup_pct=10)
    invoice_id = create_invoice(conn, customer_id)
    add_line(conn, invoice_id, "BUN01", qty=2, markup_pct=10)
    finalize_invoice(conn, invoice_id)
    conn.commit()
    return customer_id


def test_export_package_writes_a_zip_with_manifest_and_database(conn, tmp_path):
    _seed(conn)
    photos_dir = tmp_path / "supplier_invoices"
    photos_dir.mkdir()
    (photos_dir / "1-hoadon.jpg").write_bytes(b"fake-jpeg-bytes")

    archive = export_package(conn, tmp_path / "export.shopdata", photos_dir)

    assert archive.exists()
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        assert "manifest.json" in names
        assert "shop.sqlite" in names
        assert "supplier_invoices/1-hoadon.jpg" in names

    manifest = read_manifest(archive, current_schema_version=conn.execute("PRAGMA user_version").fetchone()[0])
    assert manifest.products == 1
    assert manifest.customers == 1
    assert manifest.invoices == 1


def test_read_manifest_rejects_a_package_from_a_newer_app_version(conn, tmp_path):
    _seed(conn)
    archive = export_package(conn, tmp_path / "export.shopdata", tmp_path / "no-photos")
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]

    with pytest.raises(TransferError, match="MỚI HƠN"):
        read_manifest(archive, current_schema_version=current_version - 1)


def test_read_manifest_rejects_a_corrupt_file(tmp_path):
    bad = tmp_path / "broken.shopdata"
    bad.write_bytes(b"not a zip file")
    with pytest.raises(TransferError):
        read_manifest(bad, current_schema_version=99)


def test_read_manifest_rejects_a_missing_file(tmp_path):
    with pytest.raises(TransferError):
        read_manifest(tmp_path / "does-not-exist.shopdata", current_schema_version=99)


def test_import_package_replaces_the_database_and_overwrites_same_named_photos(conn, tmp_path):
    # Import is a full replace, not a merge: a local "1-hoadon.jpg" left
    # from an unrelated invoice #1 on THIS machine must not keep showing
    # once the package's own (different) invoice #1 is now the data of
    # record -- so a same-named photo in the package must win.
    customer_id = _seed(conn)
    export_photos = tmp_path / "export-photos"
    export_photos.mkdir()
    (export_photos / "1-hoadon.jpg").write_bytes(b"from-the-export")
    archive = export_package(conn, tmp_path / "export.shopdata", export_photos)
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]

    dest_db = tmp_path / "live" / "shop.sqlite"
    dest_db.parent.mkdir(parents=True)
    dest_photos = tmp_path / "live" / "supplier_invoices"
    dest_photos.mkdir()
    (dest_photos / "1-hoadon.jpg").write_bytes(b"unrelated-local-invoice-1-photo")
    (dest_photos / "2-hoadon.jpg").write_bytes(b"local-only-not-in-the-package")

    manifest = import_package(archive, current_version, dest_db, dest_photos)

    assert manifest.customers == 1
    imported = connect(dest_db)
    try:
        row = imported.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
        assert row == ("Khach test",)
    finally:
        imported.close()

    assert (dest_photos / "1-hoadon.jpg").read_bytes() == b"from-the-export"  # package wins
    assert (dest_photos / "2-hoadon.jpg").read_bytes() == b"local-only-not-in-the-package"  # untouched: not in the package


def test_export_package_carries_the_source_machine_and_bot_sync_settings(conn, tmp_path):
    _seed(conn)
    archive = export_package(
        conn, tmp_path / "export.shopdata", tmp_path / "no-photos",
        bot_sync_url="https://example.workers.dev", bot_sync_secret="s3cr3t",
    )
    manifest = read_manifest(archive, current_schema_version=conn.execute("PRAGMA user_version").fetchone()[0])
    assert manifest.source_machine  # platform.node() -- whatever it is, just non-empty
    assert manifest.bot_sync_url == "https://example.workers.dev"
    assert manifest.bot_sync_secret == "s3cr3t"


def test_manifest_fields_default_to_empty_string_when_absent_from_an_older_package(tmp_path):
    bare = tmp_path / "bare.shopdata"
    with zipfile.ZipFile(bare, "w") as z:
        z.writestr("manifest.json", json.dumps({"exported_at": "x", "schema_version": 1, "products": 0, "customers": 0, "invoices": 0}))
        z.writestr("shop.sqlite", b"not-really-sqlite-but-unused-by-read_manifest")
    manifest = read_manifest(bare, current_schema_version=99)
    assert manifest.source_machine == ""
    assert manifest.bot_sync_url == ""
    assert manifest.bot_sync_secret == ""


def test_import_package_rejects_a_newer_schema_without_touching_the_destination(conn, tmp_path):
    _seed(conn)
    archive = export_package(conn, tmp_path / "export.shopdata", tmp_path / "no-photos")

    dest_db = tmp_path / "live" / "shop.sqlite"
    dest_db.parent.mkdir(parents=True)
    dest_db.write_bytes(b"original-untouched-bytes")

    with pytest.raises(TransferError):
        import_package(archive, current_schema_version=0, db_path=dest_db, photos_dir=tmp_path / "live" / "supplier_invoices")

    assert dest_db.read_bytes() == b"original-untouched-bytes"
