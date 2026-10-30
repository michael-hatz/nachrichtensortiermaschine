# -*- coding: utf-8 -*-
"""Plain text extraction from the article mails, shared by the txt and EPUB exports."""

import re
from bs4 import BeautifulSoup, NavigableString

BLOCK_TAGS = ["p", "div", "li", "blockquote", "tr", "td", "th", "dd", "dt", "pre", "figcaption",
              "section", "article", "header", "footer", "aside", "h1", "h2", "h3", "h4", "h5", "h6"]
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
HEADING_MARK = "## "  # prefix of heading lines in the text, like a Markdown heading


def html_to_text(html):
    """Return the text of the HTML with paragraphs separated by a blank line and <br> as a
    single line break. Headings get their own paragraph starting with HEADING_MARK.
    Line breaks in the HTML source and inline elements (links, bold, ...) don't break the text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    # Whitespace in the source is insignificant, like in a browser
    for node in soup.find_all(string=True):
        if type(node) is NavigableString:
            node.replace_with(re.sub(r"\s+", " ", str(node)))
    for heading in soup.find_all(HEADING_TAGS):
        if heading.get_text(strip=True):
            heading.insert(0, HEADING_MARK)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(BLOCK_TAGS):
        block.insert_before("\n\n")
        block.insert_after("\n\n")
    lines = [line.strip() for line in soup.get_text().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def paragraphs(text):
    """Split text into paragraphs (separated by blank lines).
    Returns a list of (is_heading, lines); the HEADING_MARK is removed from headings."""
    result = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        is_heading = lines[0].startswith(HEADING_MARK)
        if is_heading:
            lines[0] = lines[0][len(HEADING_MARK):].strip()
        result.append((is_heading, [line for line in lines if line]))
    return result
