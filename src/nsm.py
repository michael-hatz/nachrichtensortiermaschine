import feedparser
from imap_tools import MailBox
from imap_tools.errors import ImapToolsError
import imaplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import requests
import time
import csv
import os
import trafilatura
from bs4 import BeautifulSoup, NavigableString
import re
import difflib
import markdown
import signal
import fcntl
import sys
import traceback
import html as html_lib
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode
import nh3
import common
import feeddb


#global values
feedliste = common.load_feeds()
db_file_path = common.DB_PATH
legacy_tsv_path = common.data_path("urls.tsv")  # pre-SQLite list of mailed URLs, imported once

#E-Mail-Configuration
config = common.load_config()
imapHost = config['IMAP']['imapHost']
imapUser = config['IMAP']['imapUser']
imapPasscode = config['IMAP']['imapPasscode']
filterfolder = config['options']['filterfolder']
# SMTP is only used for the error mails, the articles are stored via IMAP
sender_email = config['SMTP']['sender_email']
receiver_email = config['SMTP']['receiver_email']

FIRST_RUN_ITEMS = 10    # a newly subscribed feed only mails its newest entries
REQUEST_TIMEOUT = 60    # seconds for feed/article downloads and IMAP connections
FEED_TIMEOUT = 600      # max. seconds per feed, so a hanging feed can't block the others
ERROR_MAIL_INTERVAL = 24  # hours; a feed that keeps failing is reported at most this often


class FeedTimeout(Exception):
    pass


def _feed_timeout(signum, frame):
    raise FeedTimeout(f"Feed took longer than {FEED_TIMEOUT} seconds")

def load_killfile():
    """Load the killfile.txt into a list of phrases (paragraphs separated by blank lines)."""
    with open(common.KILLFILE_PATH, "r", encoding="utf-8") as file:
        # Blank lines may contain spaces or \r (textarea in the web interface sends \r\n)
        paragraphs = [p.strip() for p in re.split(r"\r?\n\s*\n", file.read()) if p.strip()]
    phrases = []
    for paragraph in paragraphs:
        phrases.append(paragraph)
        # Single lines of a multi-line block may show up as separate paragraphs in the article
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if len(lines) > 1:
            phrases.extend(lines)
    return phrases


URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
WORD_PATTERN = re.compile(r"\w+")
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "div", "td", "th",
              "dd", "dt", "figcaption", "pre", "section", "article", "header", "footer", "aside"}
KILL_MIN_WORDS = 5       # below this, a phrase must match exactly (word by word)
KILL_MIN_RUN = 3         # only runs of at least this many identical words count as a match
KILL_MATCH_RATIO = 0.85  # share of words that must match for a fuzzy match
KILL_REST_RATIO = 0.2    # remove the whole paragraph if less than this share of words is left


def _words(text):
    """Return (lowercase word, start, end) for every word outside of URLs."""
    urls = [m.span() for m in URL_PATTERN.finditer(text)]
    words = []
    for m in WORD_PATTERN.finditer(text):
        if any(a <= m.start() < b for a, b in urls):
            continue
        words.append((m.group().lower(), m.start(), m.end()))
    return words


def _find_kill_spans(block_words, phrase_words):
    """Return (first, last) word indices in the block matched by the phrase, or None."""
    b, p = block_words, phrase_words
    shorter = min(len(b), len(p))
    if shorter == 0:
        return None
    if shorter < KILL_MIN_WORDS:
        if len(b) < KILL_MIN_WORDS:
            # Short paragraphs are only removed if they are exactly a killfile phrase
            return (0, len(b) - 1) if b == p else None
        # Short phrase: exact word sequence inside the paragraph
        for i in range(len(b) - len(p) + 1):
            if b[i:i + len(p)] == p:
                return (i, i + len(p) - 1)
        return None
    # Cheap pre-check before the expensive comparison
    if len(set(b) & set(p)) < KILL_MATCH_RATIO * len(set(b if len(b) <= len(p) else p)):
        return None
    matcher = difflib.SequenceMatcher(None, b, p, autojunk=False)
    runs = [m for m in matcher.get_matching_blocks() if m.size >= KILL_MIN_RUN]
    matched = sum(m.size for m in runs)
    if matched < KILL_MATCH_RATIO * shorter:
        return None
    first, last = runs[0].a, runs[-1].a + runs[-1].size - 1
    if last - first + 1 > 1.5 * len(p) + KILL_MIN_WORDS:
        return None  # matches scattered over a much longer paragraph
    return (first, last)


def _cut_ranges(block, ranges):
    """Remove the character ranges (relative to the block text) from the block's text nodes."""
    offset = 0
    for node in [s for s in block.find_all(string=True) if type(s) is NavigableString]:
        text = str(node)
        node_start, node_end = offset, offset + len(text)
        offset = node_end
        new_text = text
        for start, end in sorted(ranges, reverse=True):
            a, b = max(start, node_start) - node_start, min(end, node_end) - node_start
            if a < b:
                new_text = new_text[:a] + new_text[b:]
        if new_text != text:
            node.replace_with(new_text)
    # Drop inline elements (links, bold, ...) that became empty
    for tag in reversed(block.find_all(True)):
        if tag.name not in ("img", "br") and not tag.find("img") and not tag.get_text(strip=True):
            tag.decompose()


def filter_killfile(content, killfile):
    """
    Remove all killfile phrases from the HTML content.
    The comparison works paragraph by paragraph on words only, so it ignores case,
    whitespace, punctuation, quotes, URLs and inline formatting/links, and tolerates
    small differences in the text.
    """
    soup = BeautifulSoup(content, "html.parser")
    phrases = [[w for w, _, _ in _words(phrase)] for phrase in killfile]
    phrases = [p for p in phrases if p]
    if not phrases:
        return str(soup)

    # Innermost block elements; without any, treat the whole content as one block
    blocks = [tag for tag in soup.find_all(BLOCK_TAGS) if not tag.find(BLOCK_TAGS)] or [soup]

    for block in blocks:
        text = "".join(s for s in block.find_all(string=True) if type(s) is NavigableString)
        words = _words(text)
        if not words:
            continue
        block_words = [w for w, _, _ in words]
        covered = [False] * len(words)
        for phrase_words in phrases:
            span = _find_kill_spans(block_words, phrase_words)
            if span:
                for i in range(span[0], span[1] + 1):
                    covered[i] = True
        if not any(covered):
            continue
        if covered.count(False) < KILL_REST_RATIO * len(words):
            block.decompose()
            continue
        # Turn covered word runs into character ranges, including adjacent punctuation/quotes
        ranges = []
        i = 0
        while i < len(words):
            if not covered[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(words) and covered[j + 1]:
                j += 1
            start, end = words[i][1], words[j][2]
            while start > 0 and not text[start - 1].isspace() and not text[start - 1].isalnum():
                start -= 1
            while end < len(text) and not text[end].isspace() and not text[end].isalnum():
                end += 1
            ranges.append((start, end))
            i = j + 1
        _cut_ranges(block, ranges)
        if not _words(block.get_text()) and not block.find("img"):
            block.decompose()

    return str(soup)

def preprocess_links(content):
    """
    Ensure spaces are preserved around <a> tags in the HTML content.
    """
    soup = BeautifulSoup(content, "html.parser")

    for a_tag in soup.find_all("a"):
        # Add a space before the link if a word runs directly into it
        before = a_tag.previous_sibling
        if isinstance(before, str) and before and before[-1].isalnum():
            a_tag.insert_before(" ")
        # Add a space after the link if a word runs directly into it (not before punctuation)
        after = a_tag.next_sibling
        if isinstance(after, str) and after and after[0].isalnum():
            a_tag.insert_after(" ")

    return str(soup)

class MailSendError(Exception):
    """The mail server couldn't be reached or refused the mail; the article itself is fine."""


class ArticleStore:
    """Puts the articles of one feed straight into their IMAP folder (IMAP APPEND), or into
    the filterfolder if the subject contains a filter keyword. Logs in on the first article,
    so feeds without new entries don't open a connection."""

    def __init__(self, folder):
        self.folder = folder
        self.filter = load_filter()
        self.mailbox = None

    def store(self, message, subject):
        folder = self.folder
        betreff = subject.lower()
        matched = [element for element in self.filter if element in betreff]
        if matched:
            print("Matched element:", ", ".join(matched))
            folder = filterfolder
        try:
            if self.mailbox is None:
                self.mailbox = MailBox(imapHost, timeout=REQUEST_TIMEOUT).login(
                    imapUser, imapPasscode, initial_folder=None)
            self.mailbox.append(message.as_bytes(), folder)
        except (ImapToolsError, imaplib.IMAP4.error, OSError) as e:
            self.close()
            raise MailSendError(f"Mail could not be stored in {folder}: {e}") from e

    def close(self):
        if self.mailbox is not None:
            try:
                self.mailbox.logout()
            except Exception:
                pass
            self.mailbox = None


def load_filter():
    """Lowercased subject keywords from filter.txt."""
    with open(common.FILTER_PATH, "r", encoding="utf-8") as file:
        # an empty keyword would match every subject
        return [line.strip().lower() for line in file if line.strip()]


def is_http_url(url):
    return urlparse(url).scheme.lower() in ("http", "https")


def sanitize_html(content):
    """Remove scripts, event handlers, non-http(s) links and tracking pixels from HTML
    that comes from feeds or web pages."""
    content = nh3.clean(content, url_schemes={"http", "https", "mailto"},
                        link_rel="noopener noreferrer")
    soup = BeautifulSoup(content, "html.parser")
    for img in soup.find_all("img"):
        if img.get("width") in ("0", "1") or img.get("height") in ("0", "1"):
            img.decompose()
    return str(soup)


def html_to_text(content):
    """Plain text version of the HTML: line breaks only at <br> and between block elements."""
    soup = BeautifulSoup(content, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(BLOCK_TAGS):
        block.insert_after("\n\n")
    lines = [" ".join(line.split()) for line in soup.get_text().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def create_email(artikel_url, artikel_titel, artikel_content, store):
    # Content comes from feeds/web pages: sanitize first, then filter the killfile phrases
    artikel_content = sanitize_html(artikel_content)
    killfile = load_killfile()
    artikel_content = filter_killfile(artikel_content, killfile)

    # Define the email message
    artikel_titel = " ".join(str(artikel_titel or "").split()) or "Kein Titel"
    message = MIMEMultipart("alternative")
    message["Subject"] = artikel_titel
    message["From"] = sender_email
    message["To"] = receiver_email
    # with SMTP the server added these, APPEND stores the message as it is
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()

    plain_content = html_to_text(artikel_content)
    laengetext = len(plain_content.split())

    # Build HTML email
    titel_html = html_lib.escape(artikel_titel)
    url_html = html_lib.escape(artikel_url)
    if is_http_url(artikel_url):
        url_html = f'<a href="{url_html}">{url_html}</a>'
    html = (
        f"<p>====================<br>Titel: {titel_html}<br>URL: {url_html}<br>"
        f"Länge: {laengetext} Wörter<br>====================</p>\n{artikel_content}"
    )
    text = (
        f"====================\nTitel: {artikel_titel}\nURL: {artikel_url}\n"
        f"Länge: {laengetext} Wörter\n====================\n\n{plain_content}"
    )

    # Attach parts
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)

    # archive-sort.py moves read articles back to this folder
    message["X-Special-Header"] = store.folder
    store.store(message, artikel_titel)

def open_seen_db():
    """Open the database of mailed URLs, importing an old urls.tsv on first use."""
    db = feeddb.open_db()
    if os.path.exists(legacy_tsv_path):
        with open(legacy_tsv_path, newline="", encoding="utf-8") as file:
            urls = [row['URL'] for row in csv.DictReader(file, delimiter='\t') if row.get('URL')]
        with db:
            db.executemany("INSERT OR IGNORE INTO seen_urls (url) VALUES (?)", [(url,) for url in urls])
        os.rename(legacy_tsv_path, legacy_tsv_path + ".migrated")
        print(f"Imported {len(urls)} URLs from {legacy_tsv_path}")
    return db

# Tracking parameters that don't change the article
TRACKING_PARAMS = re.compile(r"^(?:utm_.*|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|wt_mc|wt_zmc)$", re.I)

def normalize_url(url):
    """The URL without tracking parameters and fragment, so the same article linked with
    different utm_* parameters is recognized."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    params = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in params if not TRACKING_PARAMS.match(k)]
    # rebuild the query only if needed, urlencode may change the encoding
    query = urlencode(kept) if len(kept) != len(params) else parts.query
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))

def seen_keys(entry, feed_url):
    """Keys under which an entry is remembered in seen_urls: the normalized link and the
    entry's id/GUID (scoped to the feed, since GUIDs are only unique within a feed)."""
    keys = [normalize_url(entry.link)]
    if entry.get('id'):
        keys.append(f"guid:{feed_url}:{entry.id}")
    return keys

def is_seen(db, entry, feed_url):
    # the raw link too: older versions stored it unnormalized
    keys = seen_keys(entry, feed_url) + [entry.link]
    placeholders = ",".join("?" * len(keys))
    return db.execute(f"SELECT 1 FROM seen_urls WHERE url IN ({placeholders})", keys).fetchone() is not None

def new_entries(feed, db, feed_url):
    """Return the feed entries that haven't been mailed yet.

    On the first run of a feed (none of its links are known) only the newest
    FIRST_RUN_ITEMS entries are returned and the rest is marked as seen, so
    subscribing to a feed with a long history doesn't send its whole archive.
    """
    entries = [entry for entry in feed.entries if entry.get('link')]
    fresh = [entry for entry in entries if not is_seen(db, entry, feed_url)]
    if len(fresh) == len(entries) and len(entries) > FIRST_RUN_ITEMS:
        print(f"First run of feed with {len(entries)} entries, mailing only the newest {FIRST_RUN_ITEMS}")
        # Feeds are sorted newest first; if not, sort by date where available
        if all(entry.get('published_parsed') for entry in entries):
            entries.sort(key=lambda entry: entry.published_parsed, reverse=True)
        mark_seen(db, feed_url, entries[FIRST_RUN_ITEMS:])
        fresh = entries[:FIRST_RUN_ITEMS]
    # the same article twice in the feed (e.g. with different tracking parameters)
    unique = {}
    for entry in fresh:
        unique.setdefault(normalize_url(entry.link), entry)
    return list(unique.values())

def mark_seen(db, feed_url, entries, sent=False):
    """Remember entries as handled and commit right away, so an error later in the run doesn't
    resend them. sent: whether they were actually mailed (for the status page)."""
    with db:
        db.executemany("INSERT OR IGNORE INTO seen_urls (url, feed, sent) VALUES (?, ?, ?)",
                       [(key, feed_url, int(sent)) for entry in entries for key in seen_keys(entry, feed_url)])

def fetch_feed(url):
    """Download and parse a feed; raise if it can't be fetched or parsed."""
    #diese Nutzung von Feedparser ist, weil einige Seiten den Feedparser direkt blocken, bzw. requests ohne header
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed could not be parsed: {feed.get('bozo_exception')}")
    return feed

def process_entries(feed, url, db, send_entry):
    """Mail every new entry; an error in one entry doesn't stop the others.

    Returns a list of (entry link, error) for the entries that failed. Failed
    entries are marked as seen too, so a broken article is reported only once
    and not retried on every run.
    """
    failed = []
    for entry in new_entries(feed, db, url):
        print(entry.link)
        try:
            send_entry(entry)
        except FeedTimeout:
            # the article that hangs would otherwise time out the feed on every run
            mark_seen(db, url, [entry])
            raise FeedTimeout(f"Feed took longer than {FEED_TIMEOUT} seconds, stopped at article {entry.link}")
        except MailSendError:
            # not the article's fault: keep it unseen so it is sent on the next run
            raise
        except Exception as e:
            print(f"Error in entry {entry.link}: {e}")
            failed.append((entry.link, traceback.format_exc()))
            mark_seen(db, url, [entry])
            continue
        mark_seen(db, url, [entry], sent=True)
    return failed

MAX_REDIRECT_PAGES = 3  # max. interstitial "you are being redirected" pages to follow
REDIRECT_PAGE_MAX_TEXT = 500  # longer pages are real content, not redirect notices

def find_page_redirect(html):
    """Return the target of a meta-refresh or JavaScript redirect page, or None."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        text = tag.get_text()
        tag.decompose()
        m = re.search(r"""window\.location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""", text)
        if m and len(soup.get_text(strip=True)) <= REDIRECT_PAGE_MAX_TEXT:
            return m.group(1)
    if len(soup.get_text(strip=True)) > REDIRECT_PAGE_MAX_TEXT:
        return None
    meta = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    if meta:
        m = re.search(r"url\s*=\s*['\"]?([^'\"]+)", meta.get("content", ""), re.I)
        if m:
            return m.group(1)
    return None

def download_page(url):
    """Return (html bytes, final url) of a page, or (None, url) if it can't be fetched.
    Uses a browser User-Agent, since some sites (e.g. spektrum.de) block trafilatura's default one."""
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        print(f"Download failed for {url}: {e}")
        return None, url
    if not response.ok:
        print(f"Download failed for {url}: HTTP {response.status_code}")
        return None, response.url
    return response.content, response.url

def fetch_article(url):
    """Download an article, following redirect notice pages (e.g. follow.it tracking links).
    Returns (html, final_url)."""
    html, url = download_page(url)
    for _ in range(MAX_REDIRECT_PAGES):
        target = find_page_redirect(html) if html else None
        if not target:
            break
        target = requests.compat.urljoin(url, target)
        if not is_http_url(target):
            break
        html, url = download_page(target)
    return html, url

def full_text2(url, store, db):
    def send_entry(entry):
        text_trafilatura, article_url = fetch_article(entry.link)
        h = trafilatura.extract(text_trafilatura, include_comments=False, include_links=True, include_formatting=True)
        title = entry.get('title', entry.link)
        if h is not None:
            artikel_content = markdown.markdown(h)  # Convert to Markdown
            artikel_content = preprocess_links(artikel_content)  # Preprocess links
            create_email(article_url, title, artikel_content, store)
        else:
            print(f"Content extraction failed for {article_url}")
            create_email(article_url, title, "Content could not be extracted.", store)

    return process_entries(fetch_feed(url), url, db, send_entry)

def read_rss_feed(url, store, db):
    def send_entry(entry):
        content = "kein Content in Feed"
        if entry.get('content') and hasattr(entry.content[0], 'value'):
            content = entry.content[0].value
        elif entry.get('summary'):
            content = entry.summary

        if entry.get('media_content') and entry.media_content[0].get('url'):
            x = entry.media_content[0]['url']
            if is_http_url(x):
                content = content + f'<br><br><img src="{html_lib.escape(x)}" width="800">'

        content = preprocess_links(content)  # Preprocess links
        title = entry.get('title', entry.link)
        create_email(entry.link, title, content, store)

    return process_entries(fetch_feed(url), url, db, send_entry)

def errormailer(textexception, subject="Fehler bei Skriptausführung"):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message.attach(MIMEText(textexception, "plain"))
    message.attach(MIMEText(f"<pre>{html_lib.escape(textexception)}</pre>", "html"))
    common.send_mail(config['SMTP'], message)



def process_feed(section_dict, db):
    """Process one feed and return a list of (entry link or None, error) that occurred."""
    if section_dict.get('active') == "False":
        return []
    print(section_dict['imap-mailbox'])
    store = ArticleStore(section_dict['imap-mailbox'])
    try:
        if section_dict.get('fulltext') == "True":
            return full_text2(section_dict['url'], store, db)
        return read_rss_feed(section_dict['url'], store, db)
    finally:
        store.close()

def feed_error_due(db, section, feed_failed):
    """Remember whether the feed itself failed in this run and return whether its error should
    be mailed: on the first failure, then at most every ERROR_MAIL_INTERVAL hours while it keeps
    failing. Returns (due, failing_since)."""
    row = db.execute("SELECT failing_since, last_mailed FROM feed_errors WHERE feed = ?", (section,)).fetchone()
    with db:
        if not feed_failed:
            if row and row[0]:
                print(f"Feed {section} works again")
                # a new failure is reported right away, not ERROR_MAIL_INTERVAL after the old one
                db.execute("UPDATE feed_errors SET failing_since = NULL, last_mailed = NULL WHERE feed = ?", (section,))
            return False, None
        if not row:
            db.execute("INSERT INTO feed_errors (feed) VALUES (?)", (section,))
        db.execute("UPDATE feed_errors SET failing_since = COALESCE(failing_since, datetime('now', 'localtime')) "
                   "WHERE feed = ?", (section,))
    failing_since, last_mailed = db.execute(
        "SELECT failing_since, last_mailed FROM feed_errors WHERE feed = ?", (section,)).fetchone()
    due = last_mailed is None or db.execute(
        "SELECT ? <= datetime('now', 'localtime', ?)", (last_mailed, f"-{ERROR_MAIL_INTERVAL} hours")).fetchone()[0]
    return bool(due), failing_since

def mark_feed_error_mailed(db, sections):
    with db:
        db.executemany("UPDATE feed_errors SET last_mailed = datetime('now', 'localtime') WHERE feed = ?",
                       [(section,) for section in sections])

def format_feed_errors(section, section_dict, errors, failing_since=None):
    lines = [
        "====================",
        f"Feed: {section}",
        f"URL: {section_dict.get('url', 'N/A')}",
        f"Mailbox: {section_dict.get('imap-mailbox', 'N/A')}",
        f"Volltext: {section_dict.get('fulltext', 'N/A')}",
    ]
    if failing_since:
        lines.append(f"Feed fehlerhaft seit: {failing_since} (wird höchstens alle {ERROR_MAIL_INTERVAL} Stunden gemeldet)")
    lines.append("====================")
    for link, error in errors:
        lines.append(f"\nArtikel: {link}" if link else "\nFehler beim Feed:")
        lines.append(error)
    return "\n".join(lines)

def main():
    db = open_seen_db()
    signal.signal(signal.SIGALRM, _feed_timeout)
    failed_feeds = []
    for section in feedliste.sections():
        section_dict = dict(feedliste[section])
        signal.alarm(FEED_TIMEOUT)
        try:
            errors = process_feed(section_dict, db)
        except Exception as e:
            print(f"Error in section {section}: {e}")
            errors = [(None, traceback.format_exc())]
        finally:
            signal.alarm(0)
        # Errors of single articles are reported once (the article is marked as seen);
        # errors of the feed itself would repeat every run, so they are throttled
        article_errors = [(link, error) for link, error in errors if link]
        feed_errors = [(link, error) for link, error in errors if not link]
        if section_dict.get('active') != "False":
            # the last line of the traceback, the exception itself, is enough for the status page
            feeddb.record_run(db, section, "\n".join((error.strip().splitlines() or ["?"])[-1] for _, error in feed_errors) or None)
        due, failing_since = feed_error_due(db, section, bool(feed_errors))
        if not due:
            if feed_errors:
                print(f"Feed {section} still failing since {failing_since}, already reported")
            feed_errors = []
        if article_errors or feed_errors:
            report = format_feed_errors(section, section_dict, feed_errors + article_errors, failing_since)
            failed_feeds.append((section, report, bool(feed_errors)))

    if failed_feeds:
        names = ", ".join(section for section, _, _ in failed_feeds)
        subject = f"Fehler bei Skriptausführung: {len(failed_feeds)} Feed(s) - {names}"
        body = "\n\n".join(report for _, report, _ in failed_feeds)
        try:
            errormailer(body, subject)
            mark_feed_error_mailed(db, [section for section, _, feed_failed in failed_feeds if feed_failed])
        except Exception as e:
            print(f"Error mail could not be sent: {e}\n{body}")
    print("Fertig")
        
LOCK_PATH = common.data_path("nsm.lock")

if __name__ == "__main__":
    common.setup_logging("nsm")
    # Only one run at a time (cron and the web interface may start one). A second run
    # would mail the same new articles again, so it just stops.
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("nsm.py is already running, skipping this run")
        sys.exit(0)
    try:
        main()
    except Exception as e:
        print(e)
        e = str(e)
        errormailer(e)

