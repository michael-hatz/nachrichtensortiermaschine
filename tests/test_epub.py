import os
import shutil
import zipfile


def test_write_epub(epub, tmp_path):
    groups = [
        (None, [("Erster Artikel", epub.text_to_paragraphs("Absatz eins\n\nAbsatz <zwei> & drei"))]),
        ("INBOX/Technik", [("Zweiter Artikel", "<p>Text</p>"), ("Dritter Artikel", "<p>Mehr</p>")]),
    ]
    path = tmp_path / "test.epub"
    epub.write_epub(str(path), groups, "Leseliste")

    with zipfile.ZipFile(path) as z:
        first = z.infolist()[0]
        # EPUB requirement: "mimetype" first and uncompressed
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        assert z.testzip() is None

    # CI runs epubcheck on this file
    if os.environ.get("EPUB_OUT"):
        shutil.copyfile(path, os.environ["EPUB_OUT"])
