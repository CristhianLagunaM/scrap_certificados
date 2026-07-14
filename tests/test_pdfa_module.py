import zipfile

from app import app, extract_zip_safely


def test_extract_zip_safely_keeps_only_valid_pdfs(tmp_path):
    zip_path = tmp_path / "entrada.zip"
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("docs/uno.pdf", b"%PDF-1.4\n%EOF\n")
        archive.writestr("docs/dos.txt", b"hola")
        archive.writestr("../afuera.pdf", b"%PDF-1.4\n%EOF\n")

    pdfs, ignored = extract_zip_safely(zip_path, extract_dir)

    assert ignored == 2
    assert [pdf.relative_to(extract_dir).as_posix() for pdf in pdfs] == ["docs/uno.pdf"]
    assert (extract_dir / "docs" / "uno.pdf").exists()
    assert not (tmp_path / "afuera.pdf").exists()


def test_pdfa_view_renders():
    client = app.test_client()

    response = client.get("/pdfa")

    assert response.status_code == 200
    assert b"PDF/A" in response.data
