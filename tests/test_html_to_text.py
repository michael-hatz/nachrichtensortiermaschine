import pytest


@pytest.fixture(scope="module")
def mailtext():
    import mailtext
    return mailtext


def test_nsm_paragraphs_and_line_breaks(nsm):
    html = "<p>Erster   Absatz<br>zweite Zeile</p><p>Zweiter <b>Absatz</b></p>"
    assert nsm.html_to_text(html) == "Erster Absatz\nzweite Zeile\n\nZweiter Absatz"


def test_nsm_collapses_blank_lines(nsm):
    assert nsm.html_to_text("<div><p>A</p></div><div></div><div><p>B</p></div>") == "A\n\nB"


def test_mailtext_source_line_breaks_are_insignificant(mailtext):
    html = "<p>Ein Satz,\n   der im Quelltext\numgebrochen ist.</p>"
    assert mailtext.html_to_text(html) == "Ein Satz, der im Quelltext umgebrochen ist."


def test_mailtext_headings_are_marked(mailtext):
    text = mailtext.html_to_text("<h2>Titel</h2><p>Text</p>")
    assert text == mailtext.HEADING_MARK + "Titel\n\nText"
    assert mailtext.paragraphs(text) == [(True, ["Titel"]), (False, ["Text"])]


def test_mailtext_drops_scripts_and_styles(mailtext):
    html = "<style>p{color:red}</style><script>alert(1)</script><p>Inhalt</p>"
    assert mailtext.html_to_text(html) == "Inhalt"
