import pytest

SIGNUP = "Melden Sie sich jetzt für unseren kostenlosen Newsletter an und verpassen Sie nichts mehr"


def test_empty_killfile_keeps_content(nsm):
    assert nsm.filter_killfile("<p>Hallo Welt</p>", []) == "<p>Hallo Welt</p>"


def test_paragraph_matching_a_phrase_is_removed(nsm):
    html = f"<p>Der eigentliche Artikel.</p><p>{SIGNUP}</p>"
    assert nsm.filter_killfile(html, [SIGNUP]) == "<p>Der eigentliche Artikel.</p>"


def test_match_ignores_case_punctuation_and_links(nsm):
    html = ('<p>Der eigentliche Artikel.</p>'
            '<p>„MELDEN Sie sich jetzt für unseren <a href="https://x.example/nl">kostenlosen Newsletter</a> an, '
            'und verpassen Sie nichts mehr!“</p>')
    assert nsm.filter_killfile(html, [SIGNUP]) == "<p>Der eigentliche Artikel.</p>"


def test_small_differences_are_tolerated(nsm):
    # one word missing
    html = "<p>Melden Sie sich jetzt für unseren kostenlosen Newsletter an und verpassen Sie nichts</p>"
    assert nsm.filter_killfile(html, [SIGNUP]) == ""


def test_phrase_is_cut_out_of_a_longer_paragraph(nsm):
    article = ("Die Stadt hat am Montag beschlossen, den Radweg entlang des Flusses bis zum "
               "Sommer auszubauen und dafür zwei Fahrspuren zu sperren.")
    html = f"<p>{article} {SIGNUP}.</p>"
    result = nsm.filter_killfile(html, [SIGNUP])
    assert "Radweg" in result
    assert "Newsletter" not in result


def test_short_phrase_matches_exact_words_only(nsm):
    html = "<p>Anzeige</p><p>Die Anzeigen im Schaufenster waren schon lange kaputt.</p>"
    assert nsm.filter_killfile(html, ["Anzeige"]) == "<p>Die Anzeigen im Schaufenster waren schon lange kaputt.</p>"


def test_unrelated_text_is_kept(nsm):
    html = "<p>Ein ganz anderer Absatz über das Wetter in Hamburg und an der Küste.</p>"
    assert nsm.filter_killfile(html, [SIGNUP]) == html


@pytest.mark.xfail(strict=True, reason="a paragraph that is (almost) only a killfile phrase is "
                   "removed as a whole, including its images")
def test_images_survive(nsm):
    html = f'<p>{SIGNUP}<img src="https://x.example/a.jpg"/></p>'
    assert "<img" in nsm.filter_killfile(html, [SIGNUP])
