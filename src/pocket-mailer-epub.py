#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox, AND
import argparse
import os
import re
import io
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from PIL import Image, ImageDraw, ImageFont
from mailtext import html_to_text, paragraphs
import common

# E-Mail Configuration
config = common.load_config()
imapHost = config['IMAP']['imapHost']
imapUser = config['IMAP']['imapUser']
imapPasscode = config['IMAP']['imapPasscode']
Eingangsordner = config['Mailings']['unread_folder']
smtp_config = config['SMTP']
receiver_email = smtp_config['receiver_email']

# EPUB Settings
dateiname = "Leseliste.epub"
buchtitel = "Leseliste"
autor = "Michael"
verlag = "Nachrichtensortiermaschine"

# Tolino-safe CSS (NO fixed sizes!)
TOLINO_CSS = """
body {
    font-family: serif;
    line-height: 1.4;
    margin: 0;
}
h2 {
    font-size: 1.15em;
    line-height: 1.2;
    margin: 1.2em 0 0.5em 0;
    text-align: left;
    page-break-after: avoid;
}
h1 {
    font-size: 1.4em;
    line-height: 1.2;
    margin: 0 0 1em 0;
    text-align: left;
    page-break-after: avoid;
}
p {
    margin: 0 0 0.8em 0;
    text-indent: 0;
}
nav ol {
    list-style: none;
    padding: 0;
}
nav ol ol {
    padding-left: 1.2em;
    margin-top: 0.6em;
}
nav li {
    margin: 0 0 0.6em 0;
}
nav a {
    text-decoration: none;
}
div.cover {
    margin: 0;
    padding: 0;
    text-align: center;
}
div.cover img {
    height: 100%;
    max-width: 100%;
}
"""

# Characters that are not allowed in XML 1.0 (control chars except tab/newline/cr)
XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def xml_text(text):
    """Escape text for use inside XHTML/XML and drop illegal control characters."""
    return escape(XML_ILLEGAL.sub("", text or ""), quote=True)


def xhtml_page(title, body, epub_type=""):
    """Wrap body in a minimal, valid EPUB 3 XHTML document."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="de" lang="de">
<head>
<title>{xml_text(title)}</title>
<link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body{f' epub:type="{epub_type}"' if epub_type else ''}>
{body}
</body>
</html>
"""


def load_font(names, size):
    """Load the first available TrueType font from names, fall back to Pillow's default."""
    for name in names:
        for folder in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", ""):
            try:
                return ImageFont.truetype(os.path.join(folder, name), size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def create_cover(title, subtitle, footer, article_count):
    """Render a generic, e-ink friendly cover (3:4, high contrast) and return it as JPEG bytes."""
    width, height = 1200, 1600
    background = (27, 34, 48)
    accent = (224, 164, 88)
    text_color = (244, 239, 230)
    muted = (160, 168, 184)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    # Subtle vertical gradient for depth
    for y in range(height):
        shade = int(12 * y / height)
        draw.line([(0, y), (width, y)], fill=(background[0] + shade, background[1] + shade, background[2] + shade))

    margin = 110

    # Stylised newspaper columns in the upper part
    column_top, column_bottom = 230, 640
    column_gap = 40
    column_width = (width - 2 * margin - 2 * column_gap) // 3
    for col in range(3):
        x0 = margin + col * (column_width + column_gap)
        draw.rectangle([x0, column_top, x0 + column_width, column_top + 22], fill=muted)
        y = column_top + 60
        line = 0
        while y < column_bottom:
            # vary line length a little so it looks like text
            length = column_width if (line + col) % 5 != 4 else int(column_width * 0.6)
            draw.rectangle([x0, y, x0 + length, y + 8], fill=(70, 80, 100))
            y += 30
            line += 1

    # Accent bar
    draw.rectangle([margin, 740, margin + 160, 756], fill=accent)

    # Title
    title_font = load_font(["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf"], 150)
    draw.text((margin - 6, 800), title, font=title_font, fill=text_color)

    # Subtitle (date)
    subtitle_font = load_font(["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"], 64)
    draw.text((margin, 1000), subtitle, font=subtitle_font, fill=accent)

    # Article count
    info_font = load_font(["DejaVuSans.ttf", "LiberationSans-Regular.ttf"], 44)
    count_text = f"{article_count} Artikel" if article_count != 1 else "1 Artikel"
    draw.text((margin, 1100), count_text, font=info_font, fill=muted)

    # Footer
    draw.line([(margin, height - 210), (width - margin, height - 210)], fill=muted, width=2)
    footer_font = load_font(["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"], 40)
    draw.text((margin, height - 170), footer.upper(), font=footer_font, fill=text_color)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def text_to_paragraphs(text):
    """Turn extracted plain text into XHTML paragraphs and subheadings; single line breaks become <br/>."""
    return "\n".join(
        ("<h2>{}</h2>" if is_heading else "<p>{}</p>").format("<br/>".join(xml_text(line) for line in lines))
        for is_heading, lines in paragraphs(text)
    )


def write_epub(filename, groups, book_title):
    """Write a clean EPUB 3 file (with EPUB 2 NCX fallback).

    groups is a list of (group_title, [(title, body_xhtml), ...]). A group with a title gets its
    own chapter page and its articles become sub-chapters in the table of contents; articles of a
    group without title (None) are top-level chapters."""
    uid = f"urn:uuid:{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    modified = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    subtitle = datetime.now().strftime("%d.%m.%Y")
    full_title = f"{book_title} {subtitle}"

    cover_jpg = create_cover(book_title, subtitle, verlag, sum(len(articles) for _, articles in groups))

    # toc: list of (file name, title, [(file name, title), ...] of sub-chapters)
    # chapter_files: every content page in reading order as (file name, title, page body)
    toc = []
    chapter_files = []
    for group_title, articles in groups:
        # the group page (if any) comes first, followed by its articles
        first = len(chapter_files) + (1 if group_title is None else 2)
        pages = [(f"chap{i:03d}.xhtml", title, f"<h1>{xml_text(title)}</h1>\n{body}")
                 for i, (title, body) in enumerate(articles, start=first)]
        if group_title is None:
            toc.extend((name, title, []) for name, title, _ in pages)
        else:
            group_name = f"chap{first - 1:03d}.xhtml"
            article_list = "\n".join(f'  <li><a href="{name}">{xml_text(title)}</a></li>' for name, title, _ in pages)
            chapter_files.append((group_name, group_title, f"<h1>{xml_text(group_title)}</h1>\n<ol>\n{article_list}\n</ol>"))
            toc.append((group_name, group_title, [(name, title) for name, title, _ in pages]))
        chapter_files.extend(pages)

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    manifest_items = "\n".join(
        f'    <item id="chap{i:03d}" href="{name}" media-type="application/xhtml+xml"/>'
        for i, (name, _, _) in enumerate(chapter_files, start=1)
    )
    spine_items = "\n".join(
        f'    <itemref idref="chap{i:03d}"/>' for i in range(1, len(chapter_files) + 1)
    )
    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="de">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{uid}</dc:identifier>
    <dc:title>{xml_text(full_title)}</dc:title>
    <dc:creator>{xml_text(autor)}</dc:creator>
    <dc:publisher>{xml_text(verlag)}</dc:publisher>
    <dc:language>de</dc:language>
    <dc:date>{now.strftime("%Y-%m-%d")}</dc:date>
    <meta property="dcterms:modified">{modified}</meta>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
{manifest_items}
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover" linear="yes"/>
    <itemref idref="nav"/>
{spine_items}
  </spine>
  <guide>
    <reference type="cover" title="Cover" href="cover.xhtml"/>
    <reference type="toc" title="Inhaltsverzeichnis" href="nav.xhtml"/>
    <reference type="text" title="Beginn" href="{chapter_files[0][0] if chapter_files else 'nav.xhtml'}"/>
  </guide>
</package>
"""

    # NCX navPoints; playOrder must follow the reading order, which is the order of chapter_files
    play_order = {name: i for i, (name, _, _) in enumerate(chapter_files, start=1)}

    def nav_point(name, title, children, indent):
        pad = " " * indent
        inner = "".join("\n" + nav_point(n, t, [], indent + 2) for n, t in children)
        return f"""{pad}<navPoint id="navpoint-{play_order[name]}" playOrder="{play_order[name]}">
{pad}  <navLabel><text>{xml_text(title)}</text></navLabel>
{pad}  <content src="{name}"/>{inner}
{pad}</navPoint>"""

    nav_points = "\n".join(nav_point(name, title, children, 4) for name, title, children in toc)
    depth = 2 if any(children for _, _, children in toc) else 1
    toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="de">
  <head>
    <meta name="dtb:uid" content="{uid}"/>
    <meta name="dtb:depth" content="{depth}"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{xml_text(full_title)}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""

    def nav_item(name, title, children):
        item = f'      <li><a href="{name}">{xml_text(title)}</a>'
        if children:
            sub = "\n".join(f'          <li><a href="{n}">{xml_text(t)}</a></li>' for n, t in children)
            item += f"\n        <ol>\n{sub}\n        </ol>\n      "
        return item + "</li>"

    nav_list = "\n".join(nav_item(name, title, children) for name, title, children in toc)
    nav_xhtml = xhtml_page("Inhaltsverzeichnis", f"""<nav epub:type="toc" id="toc">
    <h1>Inhaltsverzeichnis</h1>
    <ol>
{nav_list}
    </ol>
  </nav>""")

    cover_xhtml = xhtml_page(full_title, '<div class="cover"><img src="cover.jpg" alt="Cover"/></div>', "cover")

    with zipfile.ZipFile(filename, "w") as epub:
        # mimetype must be the first entry and stored uncompressed
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/style.css", TOLINO_CSS, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/cover.jpg", cover_jpg, compress_type=zipfile.ZIP_STORED)
        epub.writestr("OEBPS/cover.xhtml", cover_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        for name, title, body in chapter_files:
            page = xhtml_page(title, body)
            epub.writestr(f"OEBPS/{name}", page, compress_type=zipfile.ZIP_DEFLATED)

def sendeanhang(to, subject, body, filename):
    """Send an email with the EPUB file as an attachment."""
    # Create the email message
    message = MIMEMultipart()
    message['Subject'] = subject

    # Attach the EPUB file
    with open(filename, 'rb') as attachment:
        obj = MIMEBase('application', 'octet-stream')
        obj.set_payload(attachment.read())
        encoders.encode_base64(obj)
        obj.add_header('Content-Disposition', f"attachment; filename={filename}")
        message.attach(obj)

    # Send the email
    common.send_mail(smtp_config, message)
    print("YOUR MAIL HAS BEEN SENT SUCCESSFULLY")

def mail_to_chapter(nachricht):
    """Return (title, body_xhtml) for a mail, or None if it has no content."""
    emailinhalt = ""

    # Try to process the HTML part
    if nachricht.html:
        try:
            emailinhalt = html_to_text(nachricht.html)
            print(f"HTML: {nachricht.subject} ({len(emailinhalt.split())} Wörter)")
        except Exception as e:
            print(f"Error processing HTML content: {e}")

    # Fallback to plain text if HTML is empty or fails
    if not emailinhalt and nachricht.text:
        emailinhalt = nachricht.text.strip()
        print(f"Text: {nachricht.subject} ({len(emailinhalt.split())} Wörter)")

    # Skip emails with no content
    if not emailinhalt:
        print(f"Warning: No content found for email {nachricht.subject}")
        return None

    return (nachricht.subject or "Ohne Titel", text_to_paragraphs(emailinhalt))


# Folders that are never part of "all folders": not selectable or not reading material
SKIPPED_FOLDER_FLAGS = {"\\noselect", "\\nonexistent", "\\trash", "\\junk", "\\sent", "\\drafts"}

def main():
    common.setup_logging("pocket-mailer-epub")
    parser = argparse.ArgumentParser(description="Build an EPUB from the mails in the read-later folder (or other folders).")
    parser.add_argument("--no-mail", action="store_true", help="only create the file, don't send it (used for downloads)")
    parser.add_argument("--folder", action="append", default=[],
                        help="IMAP folder to include, may be repeated; the book gets one chapter per folder")
    parser.add_argument("--all-folders", action="store_true", help="include all folders of the mailbox, one chapter each")
    parser.add_argument("--unread", action="store_true", help="only include unread mails (and don't mark them read)")
    args = parser.parse_args()

    # Process emails and add content to the EPUB
    book_title = buchtitel
    if args.folder or args.all_folders:
        # One chapter per folder with the mails as sub-chapters. This is a look into the mailbox,
        # so it must not change the read state of the mails.
        book_title = "Ungelesen" if args.unread else buchtitel
        criteria = AND(seen=False) if args.unread else AND(all=True)
        groups = []
        with MailBox(imapHost).login(imapUser, imapPasscode, initial_folder=None) as mailbox:
            if args.all_folders:
                folders = [f.name for f in mailbox.folder.list()
                           if not SKIPPED_FOLDER_FLAGS & {flag.lower() for flag in f.flags}]
            else:
                folders = list(dict.fromkeys(args.folder))  # drop duplicates, keep order
            for folder in folders:
                mailbox.folder.set(folder)
                chapters = [chapter for nachricht in mailbox.fetch(criteria, mark_seen=False, bulk=True)
                            if (chapter := mail_to_chapter(nachricht))]
                if chapters:
                    groups.append((folder, chapters))
        empty_text = "Keine ungelesenen Mails gefunden." if args.unread else "In den gewählten Ordnern sind keine Mails."
    else:
        # Default: the read-later folder as a flat list of articles
        with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
            chapters = [chapter for nachricht in mailbox.fetch(mark_seen=False, bulk=True) if (chapter := mail_to_chapter(nachricht))]
        groups = [(None, chapters)] if chapters else []
        empty_text = "In der Leseliste sind aktuell keine Artikel."

    # An empty table of contents is invalid EPUB, so add a placeholder chapter
    if not groups:
        groups = [(None, [("Keine Artikel", f"<p>{xml_text(empty_text)}</p>")])]

    # Create the EPUB file
    write_epub(dateiname, groups, book_title)

    # Send the EPUB file as an email attachment (--no-mail: only create the file, used for downloads)
    if not args.no_mail:
        sendeanhang(receiver_email, "Export", "This is an automatic export of your read-later folder from Nachrichtensortiermaschine", dateiname)
    print("done")


if __name__ == "__main__":
    main()
