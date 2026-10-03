from flask import Flask, render_template, request, send_file, jsonify, Response
import os
import subprocess
import configparser
import hashlib
import hmac
import io
import re
import secrets
import shutil
import smtplib
import socket
import tempfile
import threading
from urllib.parse import urlparse
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException
from imap_tools import MailBox
from imap_tools.errors import MailboxLoginError
import readlater

app = Flask(__name__)
UPLOAD_FOLDER = '/app/data/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DEFAULTS_FOLDER = '/app/defaults/'  # pristine copies of the data files, see dockerfile
CONFIG_PATH = '/app/data/config.cfg'
DATA_FILES = ['config.cfg', 'feeds.cfg', 'filter.txt', 'killfile.txt']
PASSWORD_FILE = '/app/data/web-password.txt'
CRONTAB_PATH = '/etc/cron.d/myjobs'

# ---------- Login and CSRF protection ----------

def load_web_password():
    """Password for the web interface: NSM_WEB_PASSWORD, or a random one that is generated on
    the first start, stored in the data volume and printed to the container log."""
    password = os.environ.get('NSM_WEB_PASSWORD', '').strip()
    if password:
        return password
    try:
        with open(PASSWORD_FILE, 'r', encoding='utf-8') as f:
            password = f.read().strip()
    except FileNotFoundError:
        pass
    if not password:
        password = secrets.token_urlsafe(18)
        fd = os.open(PASSWORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(password + '\n')
    print(f"Web interface login: user '{WEB_USER}', password in {PASSWORD_FILE}: {password}", flush=True)
    return password

WEB_USER = os.environ.get('NSM_WEB_USER', 'admin').strip() or 'admin'
WEB_PASSWORD = load_web_password()
# Derived from the password, so it is the same in every worker and survives restarts
CSRF_TOKEN = hmac.new(WEB_PASSWORD.encode(), b'nsm-csrf', hashlib.sha256).hexdigest()
# Secret of the read-later bookmarklet; it only allows saving links, so it may sit in a bookmark
READLATER_TOKEN = hmac.new(WEB_PASSWORD.encode(), b'nsm-readlater', hashlib.sha256).hexdigest()[:32]

@app.before_request
def require_login():
    if request.path == '/save':
        return  # the bookmarklet authenticates with READLATER_TOKEN instead
    auth = request.authorization
    if not (auth and auth.type == 'basic'
            and hmac.compare_digest((auth.username or '').encode(), WEB_USER.encode())
            and hmac.compare_digest((auth.password or '').encode(), WEB_PASSWORD.encode())):
        return Response('Login required', 401, {'WWW-Authenticate': 'Basic realm="Nachrichtensortiermaschine", charset="UTF-8"'})
    # Browsers send Basic Auth credentials along with requests from other sites too,
    # so every state-changing request must carry the token from the page
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), CSRF_TOKEN):
            return 'Invalid or missing CSRF token. Please reload the page.', 403

@app.context_processor
def inject_csrf_token():
    return {'csrf_token': CSRF_TOKEN}

# ---------- Read later ----------

MAX_URL_LENGTH = 2000
_worker_lock = threading.Lock()
_worker_state = {'running': False, 'again': False}

def start_readlater_worker():
    """Process the read-later queue in the background right away instead of waiting for the
    cronjob. While a run is going on, another one is started after it, so a link saved in the
    meantime isn't left until the next cron run."""
    with _worker_lock:
        if _worker_state['running']:
            _worker_state['again'] = True
            return
        _worker_state['running'] = True
    threading.Thread(target=_readlater_worker, daemon=True).start()

def _readlater_worker():
    while True:
        try:
            subprocess.run(['python3', '/app/pocket-ersatz.py', '--queue-only'])
        except Exception as e:
            print(f"Read-later run failed: {e}", flush=True)
        with _worker_lock:
            if not _worker_state['again']:
                _worker_state['running'] = False
                return
            _worker_state['again'] = False

def queue_link(url, title=None):
    """Validate and queue a link; returns (ok, message)."""
    url = (url or '').strip()
    if urlparse(url).scheme.lower() not in ('http', 'https') or not urlparse(url).netloc:
        return False, 'Only http(s) links can be saved.'
    if len(url) > MAX_URL_LENGTH:
        return False, 'The link is too long.'
    title = re.sub(r'\s+', ' ', title or '').strip()[:300] or None
    db = readlater.open_db()
    try:
        added = readlater.add(db, url, title)
    finally:
        db.close()
    start_readlater_worker()
    return True, 'Saved, the article will be mailed shortly.' if added else 'Already in the queue.'

def bookmarklet():
    """javascript: link that saves the current page; opens /save in a small popup
    (or in the same tab if popups are blocked)."""
    target = f"{request.host_url}save?token={READLATER_TOKEN}"
    return ("javascript:(function(){var u='" + target + "&url='+encodeURIComponent(location.href)"
            "+'&title='+encodeURIComponent(document.title);"
            "if(!window.open(u,'nsm-save','width=440,height=260'))location.href=u;})();")

@app.route('/save', methods=['GET'])
def save_readlater():
    """Target of the bookmarklet: /save?token=...&url=...&title=..."""
    if not hmac.compare_digest(request.args.get('token', ''), READLATER_TOKEN):
        ok, message = False, 'Invalid token. Please drag the bookmarklet from the web interface into your bookmarks again.'
        status = 403
    else:
        ok, message = queue_link(request.args.get('url'), request.args.get('title'))
        status = 200 if ok else 400
    return render_template('saved.html', ok=ok, message=message, url=request.args.get('url', ''),
                           title=request.args.get('title', '')), status

@app.route('/api/readlater', methods=['GET'])
def readlater_list():
    db = readlater.open_db()
    try:
        return jsonify(readlater.recent(db))
    finally:
        db.close()

@app.route('/api/readlater', methods=['POST'])
def readlater_add():
    data = request.get_json(force=True, silent=True) or {}
    ok, message = queue_link(data.get('url'), data.get('title'))
    return jsonify({'ok': ok, 'message': message}), 200 if ok else 400

# ---------- Crontab validation ----------

CRON_SCRIPTS = r'(?:nsm|pocket-ersatz|archive-sort|pocket-mailer|pocket-mailer-epub)\.py'
CRON_LINE = re.compile(
    r'^(?:[0-9*/,-]+\s+){5}root\s+'
    r'(?:'
    r'(?:/opt/venv/bin/)?python3\s+/app/' + CRON_SCRIPTS + r'(?:\s+--[a-z-]+(?:=[\w./-]+)?)*(?:\s+>>\s*/app/[\w.-]+\.log\s+2>&1)?'
    r'|rm -r /tmp/\*'
    r'|pkill -f (?:/usr/local/bin/geckodriver|/opt/firefox/)'
    r')\s*;?\s*$'
)

def invalid_crontab_lines(content):
    """Return the lines that are not a schedule for one of the app's scripts or maintenance jobs.
    The jobs run as root, so a free-form crontab would allow running any command."""
    return [line for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith('#') and not CRON_LINE.match(line.strip())]

def ensure_data_files():
    """Copy the default data files into /app/data if they are missing (e.g. an empty volume
    hides the files the image put there)."""
    for name in DATA_FILES:
        target = os.path.join(UPLOAD_FOLDER, name)
        source = os.path.join(DEFAULTS_FOLDER, name)
        if not os.path.exists(target) and os.path.exists(source):
            shutil.copyfile(source, target)

def needs_setup():
    """True if config.cfg has no real mail account yet (missing or still the example values)."""
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding='utf-8')
    host = config.get('IMAP', 'imapHost', fallback='').strip().lower()
    return not host or host.endswith('example.com')

@app.route('/')
def index():
    ensure_data_files()
    # Read the contents of the files with utf-8 encoding
    config_content = read_file('/app/data/config.cfg')
    feeds_content = read_file('/app/data/feeds.cfg')
    filter_content = read_file('/app/data/filter.txt')
    killfile_content = read_file('/app/data/killfile.txt')  # Added killfile handling

    # Read the crontab
    try:
        # Read the cron job file directly
        with open(CRONTAB_PATH, 'r') as f:
            crontab_content = f.read()
    except FileNotFoundError:
        # Handle the case where the cron job file does not exist
        crontab_content = "No cron jobs found."

    return render_template(
        'index.html',
        config=config_content,
        feeds=feeds_content,
        filter=filter_content,
        killfile=killfile_content,  # Pass killfile content to the template
        crontab=crontab_content,  # Pass crontab content to the template
        bookmarklet=bookmarklet(),
        needs_setup=needs_setup()
    )

@app.route('/', methods=['POST'])
def save():
    # Get the new content from the forms
    config_content = request.form.get('config', '')
    feeds_content = request.form.get('feeds', '')
    filter_content = request.form.get('filter', '')
    killfile_content = request.form.get('killfile', '')
    crontab_content = request.form.get('crontab', '').replace('\r\n', '\n').replace('\r', '\n')
    # cron ignores the last job if the file does not end with a newline
    if crontab_content and not crontab_content.endswith('\n'):
        crontab_content += '\n'

    # Helper to normalize line endings for comparison
    def normalize(content):
        return content.replace('\r\n', '\n').replace('\r', '\n')

    # Check the crontab before saving anything, so a rejected save changes nothing
    try:
        with open(CRONTAB_PATH, 'r') as f:
            crontab_changed = normalize(f.read()) != crontab_content
    except FileNotFoundError:
        crontab_changed = bool(crontab_content)
    bad_lines = invalid_crontab_lines(crontab_content) if crontab_changed else []
    if bad_lines:
        return jsonify({'error': 'Crontab not saved, nothing was saved. Only schedules for the '
                                 'scripts in /app are allowed, e.g. "58 * * * * root /opt/venv/bin/python3 '
                                 '/app/nsm.py". Rejected lines: ' + ' | '.join(bad_lines)}), 400

    # Save config.cfg if changed
    try:
        current_config = normalize(read_file('/app/data/config.cfg'))
    except FileNotFoundError:
        current_config = ""
    if current_config != normalize(config_content):
        write_file('/app/data/config.cfg', config_content)

    # Save feeds.cfg if changed
    try:
        current_feeds = normalize(read_file('/app/data/feeds.cfg'))
    except FileNotFoundError:
        current_feeds = ""
    created_folders, folder_error = [], None
    if current_feeds != normalize(feeds_content):
        write_file('/app/data/feeds.cfg', feeds_content)
        created_folders, folder_error = create_missing_feed_folders()

    # Save filter.txt if changed
    try:
        current_filter = normalize(read_file('/app/data/filter.txt'))
    except FileNotFoundError:
        current_filter = ""
    if current_filter != normalize(filter_content):
        write_file('/app/data/filter.txt', filter_content)

    # Save killfile.txt if changed
    try:
        current_killfile = normalize(read_file('/app/data/killfile.txt'))
    except FileNotFoundError:
        current_killfile = ""
    if current_killfile != normalize(killfile_content):
        write_file('/app/data/killfile.txt', killfile_content)

    # Save crontab if changed
    try:
        with open(CRONTAB_PATH, 'r') as f:
            current_crontab = normalize(f.read())
    except FileNotFoundError:
        current_crontab = ""
    if current_crontab != crontab_content:
        with open(CRONTAB_PATH, 'w') as crontab_file:
            crontab_file.write(crontab_content)
        os.chmod(CRONTAB_PATH, 0o644)  # Ensure correct permissions

    return jsonify({'created_folders': created_folders, 'folder_error': folder_error})

@app.route('/fetch-feeds', methods=['POST'])
def fetch_feeds():
    try:
        subprocess.run(['python3', '/app/nsm.py'], check=True)
        return "Feeds fetched successfully!"
    except subprocess.CalledProcessError as e:
        return f"Error fetching feeds: {e}", 500

@app.route('/send-txt', methods=['POST'])
def send_txt():
    try:
        subprocess.run(['python3', '/app/pocket-mailer.py'], check=True)
        return "TXT emails sent successfully!"
    except subprocess.CalledProcessError as e:
        return f"Error sending TXT emails: {e}", 500

@app.route('/send-epub', methods=['POST'])
def send_epub():
    try:
        subprocess.run(['python3', '/app/pocket-mailer-epub.py'], check=True)
        return "EPUB emails sent successfully!"
    except subprocess.CalledProcessError as e:
        return f"Error sending EPUB emails: {e}", 500

def generate_download(script, filename, download_name, mimetype, extra_args=()):
    """Run a mailer script with --no-mail in a temp dir and return the generated file."""
    workdir = tempfile.mkdtemp()
    try:
        subprocess.run(['python3', script, '--no-mail', *extra_args], cwd=workdir, check=True)
        with open(os.path.join(workdir, filename), 'rb') as f:
            data = io.BytesIO(f.read())
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"Error generating {download_name}: {e}", 500
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return send_file(data, as_attachment=True, download_name=download_name, mimetype=mimetype)

@app.route('/download-txt', methods=['GET'])
def download_txt():
    return generate_download('/app/pocket-mailer.py', 'nachrichtensortiermaschine.txt',
                             f"nachrichtensortiermaschine-{date.today():%Y%m%d}.txt", 'text/plain')

@app.route('/download-epub', methods=['GET'])
def download_epub():
    """EPUB of the read-later folder, or with ?folder=...&folder=... of the chosen folders,
    or with ?all=1 of all folders; &unread=1 limits it to unread mails."""
    args, name = [], "Leseliste"
    if request.args.get('all') == '1':
        args.append('--all-folders')
    else:
        for folder in request.args.getlist('folder'):
            args.append(f'--folder={folder}')  # "=" so folder names starting with "-" aren't options
    if args and request.args.get('unread') == '1':
        args.append('--unread')
        name = "Ungelesen"
    return generate_download('/app/pocket-mailer-epub.py', 'Leseliste.epub',
                             f"{name}-{date.today():%Y%m%d}.epub", 'application/epub+zip', args)

def create_missing_folders(mailbox, names):
    """Create and subscribe the folders that don't exist yet; returns the created names.
    "INBOX" is case-insensitive in IMAP, so "Inbox/x" and "INBOX/x" are the same folder."""
    folders = mailbox.folder.list()
    delim = next((f.delim for f in folders if f.delim), '/')

    def key(name):
        head, sep, rest = name.partition(delim)
        return (head.upper() if head.upper() == 'INBOX' else head) + sep + rest

    existing = {key(folder.name) for folder in folders}
    created = []
    for name in dict.fromkeys(n.strip() for n in names):
        if name and key(name) not in existing:
            mailbox.folder.create(name)
            mailbox.folder.subscribe(name, True)
            existing.add(key(name))
            created.append(name)
    return created

def create_missing_feed_folders():
    """Create the IMAP folders referenced by imap-mailbox in feeds.cfg that don't exist yet.

    Returns (created folder names, error message or None). A failing IMAP connection
    must not break saving, so errors are reported instead of raised.
    """
    feeds = configparser.ConfigParser()
    feeds.read('/app/data/feeds.cfg', encoding='utf-8')
    wanted = {feeds[section].get('imap-mailbox', 'INBOX').strip() for section in feeds.sections()}
    wanted.discard('')
    config = configparser.ConfigParser()
    config.read('/app/data/config.cfg')
    created = []
    try:
        imap = config['IMAP']
        with MailBox(imap['imapHost'], timeout=15).login(imap['imapUser'], imap['imapPasscode'], initial_folder=None) as mailbox:
            created = create_missing_folders(mailbox, sorted(wanted))
    except Exception as e:
        return created, str(e)
    return created, None

# ---------- Setup wizard ----------

def check_imap(host, user, password):
    """Log in the way the scripts do (IMAP over SSL, port 993) and describe the mailbox:
    folder names, the folder separator, the inbox's spelling and the trash folder (if flagged)."""
    with MailBox(host, timeout=15).login(user, password, initial_folder=None) as mailbox:
        folders = mailbox.folder.list()
    inbox = next((f for f in folders if f.name.upper() == 'INBOX'), None)
    trash = next((f.name for f in folders if '\\trash' in (flag.lower() for flag in f.flags)), '')
    return {
        'folders': sorted(f.name for f in folders),
        'delim': ((inbox or folders[0]).delim if folders else None) or '/',
        'inbox': inbox.name if inbox else 'INBOX',
        'trash': trash,
    }

def check_smtp(host, port, user, password):
    """Log in the way the scripts do (SMTP with STARTTLS)."""
    with smtplib.SMTP(host, int(port), timeout=15) as server:
        server.starttls()
        server.login(user, password)

@app.route('/api/setup/test', methods=['POST'])
def setup_test():
    """Test the IMAP or SMTP login entered in the setup wizard."""
    data = request.get_json(force=True)
    try:
        if data.get('kind') == 'imap':
            return jsonify({'ok': True, **check_imap(data['host'], data['user'], data['password'])})
        check_smtp(data['host'], data.get('port') or 587, data['user'], data['password'])
        return jsonify({'ok': True})
    except (MailboxLoginError, smtplib.SMTPAuthenticationError):
        return jsonify({'ok': False, 'error': 'Login failed. Please check login and password.'})
    except socket.gaierror:
        return jsonify({'ok': False, 'error': f"Server {data.get('host')} not found."})
    except (socket.timeout, ConnectionRefusedError):
        return jsonify({'ok': False, 'error': f"No answer from {data.get('host')}. Please check server and port."})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e) or type(e).__name__})

def set_ini_values(text, updates):
    """Set {section: {key: value}} in the INI text, keeping comments, order and key spelling.
    Missing keys are appended to their section, missing sections to the end."""
    lines = text.splitlines()
    pending = {section: dict(values) for section, values in updates.items()}
    section, section_end = None, {}
    for i, line in enumerate(lines):
        header = re.match(r'^\s*\[(.+)\]\s*$', line)
        if header:
            section = header.group(1).strip()
            section_end[section] = i + 1
            continue
        if section is None:
            continue
        if line.strip():
            section_end[section] = i + 1
        kv = re.match(r'^(\s*)([^=:\s][^=:]*?)(\s*[=:]\s*)(.*?)\s*$', line)
        if kv and section in pending:
            for key in list(pending[section]):
                if key.lower() == kv.group(2).lower():
                    lines[i] = kv.group(1) + kv.group(2) + kv.group(3) + pending[section].pop(key)
    # insert from the bottom up so earlier positions stay valid
    for section in sorted((s for s in pending if s in section_end), key=section_end.get, reverse=True):
        lines[section_end[section]:section_end[section]] = [f"{key} = {value}" for key, value in pending[section].items()]
    for section, values in pending.items():
        if section not in section_end:
            lines += ['', f'[{section}]'] + [f"{key} = {value}" for key, value in values.items()]
    return '\n'.join(lines) + '\n'

def ini_value(value):
    """Make a wizard value safe for config.cfg: one line, and "%" escaped for configparser's
    interpolation, which the scripts use when reading the file."""
    return re.sub(r'[\r\n]+', '', str(value)).strip().replace('%', '%%')

@app.route('/api/setup', methods=['POST'])
def setup_save():
    """Write the mail settings from the setup wizard into config.cfg."""
    data = request.get_json(force=True)
    try:
        imap, smtp, folders = data['imap'], data['smtp'], data['folders']
        updates = {
            'IMAP': {'imapHost': imap['host'], 'imapUser': imap['user'], 'imapPasscode': imap['password']},
            'SMTP': {'port': smtp['port'], 'smtp_server': smtp['host'], 'sender_email': smtp['user'],
                     'receiver_email': smtp['receiver'], 'password': smtp['password']},
            'Mailings': {'unread_folder': folders['unread']},
            'options': {'filterfolder': folders['filter']},
        }
        readlater = data.get('readlater')
        if readlater:
            updates['IMAP-Artikelpostfach'] = {'imapHost': readlater['imap_host'], 'imapUser': readlater['user'],
                                               'imapPasscode': readlater['password']}
            updates['SMTP-Artikelpostfach'] = {'port': readlater['smtp_port'], 'smtp_server': readlater['smtp_host'],
                                               'sender_email': readlater['user'], 'receiver_email': smtp['receiver'],
                                               'password': readlater['password']}
        updates = {section: {key: ini_value(value) for key, value in values.items()} for section, values in updates.items()}
    except (KeyError, TypeError) as e:
        return jsonify({'error': f'Missing value: {e}'}), 400

    ensure_data_files()
    try:
        current = read_file(CONFIG_PATH)
    except FileNotFoundError:
        current = ''
    write_file(CONFIG_PATH, set_ini_values(current, updates))

    # The read-later and filter folders must exist, or the scripts fail on them
    created, folder_error = [], None
    try:
        with MailBox(imap['host'], timeout=15).login(imap['user'], imap['password'], initial_folder=None) as mailbox:
            created = create_missing_folders(mailbox, [folders['unread'], folders['filter']])
    except Exception as e:
        folder_error = str(e)
    return jsonify({'created_folders': created, 'folder_error': folder_error})

@app.route('/api/folders', methods=['GET'])
def list_folders():
    """List the IMAP folders of the feed mailbox (used for folder suggestions in the GUI)."""
    config = configparser.ConfigParser()
    config.read('/app/data/config.cfg')
    try:
        imap = config['IMAP']
        with MailBox(imap['imapHost'], timeout=15).login(imap['imapUser'], imap['imapPasscode'], initial_folder=None) as mailbox:
            return jsonify(sorted(folder.name for folder in mailbox.folder.list()))
    except Exception as e:
        return jsonify({'error': str(e)}), 502

@app.route('/export-opml', methods=['GET'])
def export_opml():
    """Export feeds.cfg as an OPML file."""
    feeds_path = '/app/data/feeds.cfg'
    opml_path = '/app/data/feeds.opml'

    # Parse feeds.cfg
    config = configparser.ConfigParser()
    config.read(feeds_path)

    # Create OPML structure
    opml = Element('opml')
    opml.set('version', '1.0')
    head = SubElement(opml, 'head')
    title = SubElement(head, 'title')
    title.text = 'Exported Feeds'
    body = SubElement(opml, 'body')

    for section in config.sections():
        outline = SubElement(body, 'outline')
        outline.set('text', section)
        outline.set('title', section)
        outline.set('xmlUrl', config[section]['url'])
        outline.set('fulltext', config[section].get('fulltext', 'False'))
        outline.set('active', config[section].get('active', 'True'))
        outline.set('imap-mailbox', config[section].get('imap-mailbox', 'INBOX'))

    # Write OPML to file
    tree = ElementTree(opml)
    tree.write(opml_path, encoding='utf-8', xml_declaration=True)

    return send_file(opml_path, as_attachment=True, download_name='feeds.opml')

@app.route('/import-opml', methods=['POST'])
def import_opml():
    """Import an OPML file and update feeds.cfg."""
    print("Request files:", request.files)  # Debug: Log request files

    if 'file' not in request.files:
        print("No file part in request.")  # Debug: Log missing file
        return "No file part", 400

    file = request.files['file']
    if file.filename == '':
        print("No selected file.")  # Debug: Log empty filename
        return "No selected file", 400

    # Parse in memory: the upload must never be written to /app/data, where a file called
    # e.g. config.cfg would replace the configuration. defusedxml blocks entity attacks.
    try:
        root = SafeET.fromstring(file.read())
    except (SafeET.ParseError, DefusedXmlException) as e:
        print(f"Error parsing OPML file: {e}")
        return "Invalid OPML file", 400

    # Update feeds.cfg
    config = configparser.ConfigParser()
    feeds_path = '/app/data/feeds.cfg'
    config.read(feeds_path)

    added_feeds = []
    updated_feeds = []
    skipped_feeds = []

    for outline in root.findall(".//outline"):
        if not outline.get('xmlUrl', '').strip():
            continue  # a category folder, not a feed
        # One line, no brackets: anything else could break or inject sections into feeds.cfg
        section = re.sub(r'[\[\]\r\n]+', ' ', outline.get('title') or outline.get('text') or 'Unnamed Feed').strip() or 'Unnamed Feed'
        new_feed = {key: re.sub(r'[\r\n]+', '', value).strip() for key, value in {
            'url': outline.get('xmlUrl', ''),
            'fulltext': outline.get('fulltext', 'False'),
            'active': outline.get('active', 'True'),
            'imap-mailbox': outline.get('imap-mailbox', 'INBOX')
        }.items()}

        if section in config:
            # Check if the feed is identical
            existing_feed = dict(config[section])
            if existing_feed == new_feed:
                skipped_feeds.append(section)
            else:
                config[section] = new_feed
                updated_feeds.append(section)
        else:
            config[section] = new_feed
            added_feeds.append(section)

    # Debug: Log the updated feeds.cfg content
    print("Updated feeds.cfg content:")
    for section in config.sections():
        print(f"[{section}]")
        for key, value in config[section].items():
            print(f"{key} = {value}")

    # Save updated feeds.cfg
    try:
        with open(feeds_path, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        print(f"feeds.cfg successfully updated at {feeds_path}")
    except Exception as e:
        print(f"Error writing to feeds.cfg: {e}")
        return "Error updating feeds.cfg", 500

    created_folders, folder_error = create_missing_feed_folders()
    folder_note = ""
    if created_folders:
        folder_note = f" Created mail folders: {', '.join(created_folders)}"
    elif folder_error:
        folder_note = f" Could not check mail folders: {folder_error}"

    # Provide feedback to the user
    return (
        f"OPML imported successfully! "
        f"Added: {len(added_feeds)}, Updated: {len(updated_feeds)}, Skipped: {len(skipped_feeds)}"
        f"{folder_note}"
    )

def read_file(file_path):
    """Read the content of a file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def write_file(file_path, content):
    """Write content to a file with Unix line endings (browsers submit CRLF)."""
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)  # production: gunicorn, see dockerfile
