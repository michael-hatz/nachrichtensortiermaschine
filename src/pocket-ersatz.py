from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from imap_tools import MailBox
import trafilatura
from bs4 import BeautifulSoup
import markdown
import html as html_lib
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.firefox.options import Options
import time
import sys
import argparse
import fcntl
import readlater
import common

geckodriver_path = "/usr/local/bin/geckodriver"  # specify the path to your geckodriver

#E-Mail-Configuration
config = common.load_config()
imapHost = config['IMAP-Artikelpostfach']['imapHost']
imapUser = config['IMAP-Artikelpostfach']['imapUser']
imapPasscode = config['IMAP-Artikelpostfach']['imapPasscode']
Eingangsordner = config['IMAP-Artikelpostfach']['Eingangsordner']
smtp_config = config['SMTP-Artikelpostfach']


#setup selenium
addon_path1 = r"/app/istilldontcareaboutcookies-1.1.4.xpi"
addon_path2 = r"/app/bypass-paywalls-firefox.xpi"

firefox_options = Options()
firefox_options.add_argument("--headless")
firefox_options.add_argument('--no-sandbox')
#firefox_options.add_argument("--profile")
#firefox_options.add_argument("/dev/null")
firefox_options.add_argument("--purgecaches")
firefox_options.add_argument('--disable-dev-shm-usage')
firefox_options.binary_location = "/usr/local/bin/firefox"

driver = None

# Max. Laufzeit pro Durchgang: Der Cronjob beendet Firefox um :15, pocket-ersatz startet um :36.
# Was nicht mehr in die Zeit passt, bleibt in der Warteschlange und kommt beim nächsten Lauf dran.
MAX_RUNTIME = 30 * 60  # Sekunden

def start_driver():
    driver_service = webdriver.FirefoxService(executable_path=geckodriver_path)
    d = webdriver.Firefox(options=firefox_options, service=driver_service)
    d.set_page_load_timeout(60)
    d.install_addon(addon_path1)
    d.install_addon(addon_path2)
    return d



def getarticleandsendmail(artikel, fallback_title=None):
    
#trifalatura
    driver.vars = {}
    print(artikel)
    driver.get(artikel)
    print("versuche artikel zu laden")
    time.sleep(5)
    page_source = driver.page_source
    #print(page_source)
    #url = trafilatura.fetch_url(artikel)
    h = trafilatura.extract(page_source, include_comments=False, include_formatting=True)
    #print(h)
#titel extrahieren
    #soup = BeautifulSoup(url, 'html.parser')
    #titeldesdokuments = soup.title.string
    #print("zeile 92")
    titeldesdokuments = driver.title or fallback_title or artikel
    if h is None:
        raise ValueError(f"Kein Artikeltext gefunden auf {artikel}")
    #print("zeile 94")
    ## 20.12.22: Hier hackt es gerade leicht, da Trafilatura eben einen extrahierten text liefert
    
    heruntergeladenertextinhtml = markdown.markdown(h)
    #print("zeile 99")
    laengetext = len(h.split()) #berechnet wortanzahl
    laengetextstr = str(laengetext)

#definiere nachricht
    message = MIMEMultipart("alternative")
    message["Subject"] = titeldesdokuments
# hier zusammensetzung der mail: Textteil mit dem Markdown von trafilatura, HTML-Teil escaped
    text = ("====================\n\nTitel: " + titeldesdokuments + "\nURL: " + artikel
            + "\nLänge: " + laengetextstr + " Wörter\n\n====================\n\n" + h)
    titel_html = html_lib.escape(titeldesdokuments)
    url_html = html_lib.escape(artikel)
    html = ("====================<br>Titel: " + titel_html + "<br>URL: " + '<a href="' + url_html + '">' + url_html + '</a>'
            + "<br>Länge: " + laengetextstr + " Wörter<br>====================<br><br>" + heruntergeladenertextinhtml)

    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)

#absenden mail
    common.send_mail(smtp_config, message)
    print("Mail gesendet")
    
LOCK_PATH = common.data_path("pocket-ersatz.lock")
ARCHIVE_FOLDER = "Archiv"  # processed mails of the Artikelpostfach


def fetch_and_send(url, title=None):
    """Load the article in Firefox and mail it. Firefox is started on first use and
    restarted after an error, since it may hang or have crashed."""
    global driver
    if driver is None:
        driver = start_driver()
    try:
        getarticleandsendmail(url, title)
    except Exception:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None
        raise


def time_left(start):
    return time.monotonic() - start < MAX_RUNTIME


def process_queue(start):
    """Links saved via the web interface / bookmarklet. A failed link stays in the queue
    and is retried on the next runs, up to readlater.MAX_ATTEMPTS times."""
    db = readlater.open_db()
    tried = set()
    while time_left(start):
        item = readlater.next_pending(db, tried)
        if item is None:
            break
        item_id, url, title = item
        tried.add(item_id)
        try:
            fetch_and_send(url, title)
            readlater.mark_done(db, item_id)
        except Exception as e:
            print("Fehler bei " + url + ": " + str(e))
            readlater.mark_failed(db, item_id, e)
    db.close()


def process_mailbox():
    """Links mailed to the Artikelpostfach. They are only put into the queue here, so a link
    that fails is retried like the ones from the web interface; the mail is archived only once
    its links are queued."""
    regex = r'<?http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+>?'
    db = readlater.open_db()
    try:
        with MailBox(imapHost).login(imapUser, imapPasscode, 'INBOX') as mailbox:
            # Without the archive folder the mails would stay in the inbox and their links
            # would be queued (and mailed) again on every run
            if not mailbox.folder.exists(ARCHIVE_FOLDER):
                mailbox.folder.create(ARCHIVE_FOLDER)
            for nachricht in mailbox.fetch(bulk=True):
                emailinhalt = nachricht.text or nachricht.html or ""
                print("Mail: " + str(nachricht.subject))
                #regex durchsucht inhalt der Mails nach URLs
                matches = [m.strip('<>') for m in re.findall(regex, emailinhalt)]
                print(matches)
                for m in matches:
                    readlater.add(db, m)
                mailbox.move(nachricht.uid, ARCHIVE_FOLDER)
    finally:
        db.close()


parser = argparse.ArgumentParser(description="Fetch read-later articles with Firefox and mail them.")
parser.add_argument("--queue-only", action="store_true",
                    help="only process the links saved via the web interface, not the Artikelpostfach")
args = parser.parse_args()
common.setup_logging("pocket-ersatz")

# Only one run at a time (cron and the web interface may start one); a second one waits
with open(LOCK_PATH, "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    # Max. Laufzeit zählt ab hier, nicht ab dem Warten auf den Lock
    start = time.monotonic()
    try:
        if not args.queue_only:
            try:
                process_mailbox()
            except Exception as e:
                print("Fehler beim Artikelpostfach: " + str(e))
        process_queue(start)
    finally:
        # Firefox + geckodriver immer beenden, auch bei Fehlern oder sys.exit()
        if driver is not None:
            driver.quit()
