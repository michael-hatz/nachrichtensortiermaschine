from flask import Flask, render_template, request, send_file, jsonify, Response
import os
import subprocess
import configparser
import fcntl
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
from urllib.parse import urlparse, urljoin
from datetime import date, datetime
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException
from imap_tools import MailBox
from imap_tools.errors import MailboxLoginError
import readlater
import common
import feeddb
import requests
import feedparser
from bs4 import BeautifulSoup

app = Flask(__name__)
UPLOAD_FOLDER = common.DATA_DIR
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DEFAULTS_FOLDER = '/app/defaults/'  # pristine copies of the data files, see dockerfile
CONFIG_PATH = common.CONFIG_PATH
DATA_FILES = ['config.cfg', 'feeds.cfg', 'filter.txt', 'killfile.txt']
PASSWORD_FILE = common.data_path('web-password.txt')
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

# ---------- Running the scripts ----------

# The scripts run as the unprivileged user nsm, like the cronjobs (see dockerfile)
SCRIPT_USER = common.SCRIPT_USER
# Files the web app creates in /app/data (database, locks, config) get group nsm from the
# setgid directory; group-writable so the scripts can write them too
os.umask(0o002)

def script_kwargs():
    """subprocess arguments to run the app's scripts as SCRIPT_USER if the web app runs as root."""
    env = {**os.environ, 'PYTHONUNBUFFERED': '1'}  # unbuffered for the live log
    if os.geteuid() != 0:
        return {'env': env}
    return {'user': SCRIPT_USER, 'group': SCRIPT_USER, 'extra_groups': [],
            'env': {**env, 'HOME': f'/home/{SCRIPT_USER}'}}

def run_script(args, **kwargs):
    """subprocess.run for the app's scripts, as SCRIPT_USER if the web app runs as root."""
    return subprocess.run(args, **script_kwargs(), **kwargs)

def script_workdir():
    """Temporary working directory the scripts can write their files to."""
    workdir = tempfile.mkdtemp()
    if os.geteuid() == 0:
        shutil.chown(workdir, SCRIPT_USER, SCRIPT_USER)
    return workdir

# ---------- Background jobs with live log ----------

JOBS = {
    'fetch-feeds': ('Fetch feeds', ['python3', '/app/nsm.py']),
    'send-txt': ('Send TXT', ['python3', '/app/pocket-mailer.py']),
    'send-epub': ('Send EPUB', ['python3', '/app/pocket-mailer-epub.py']),
}
JOB_MAX_LINES = 5000

class Job:
    """One run of a script; its output is kept in memory for the live log."""

    def __init__(self, name):
        self.name = name
        self.label, self.args = JOBS[name]
        self.lines = []
        self.dropped = 0  # lines removed from the start because of JOB_MAX_LINES
        self.started = date_time_now()
        self.finished = None
        self.returncode = None

    def run(self):
        workdir = script_workdir()
        try:
            proc = subprocess.Popen(self.args, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors='replace', bufsize=1, **script_kwargs())
            for line in proc.stdout:
                self.add_line(line.rstrip('\n'))
            self.returncode = proc.wait()
        except Exception as e:
            self.add_line(f'Could not run the script: {e}')
            self.returncode = -1
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            self.finished = date_time_now()

    def add_line(self, line):
        self.lines.append(line)
        excess = len(self.lines) - JOB_MAX_LINES
        if excess > 0:
            del self.lines[:excess]
            self.dropped += excess

    def state(self, since=0):
        """State and the output lines from line number since on."""
        start = max(since - self.dropped, 0)
        return {'name': self.name, 'label': self.label, 'running': self.finished is None,
                'returncode': self.returncode, 'started': self.started, 'finished': self.finished,
                'lines': self.lines[start:], 'next': self.dropped + len(self.lines)}

_jobs = {}
_jobs_lock = threading.Lock()

def date_time_now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def start_job(name):
    """Start the job unless it is already running; returns (job, started)."""
    with _jobs_lock:
        job = _jobs.get(name)
        if job and job.finished is None:
            return job, False
        job = _jobs[name] = Job(name)
    threading.Thread(target=job.run, daemon=True).start()
    return job, True

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
            run_script(['python3', '/app/pocket-ersatz.py', '--queue-only'])
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

# ---------- Feed status ----------

@app.route('/api/status', methods=['GET'])
def feed_status():
    """Per feed: last successful fetch, articles sent, current error (see feeddb)."""
    feeds = common.load_feeds()
    entries = [(section, feeds[section].get('url', ''), feeds[section].get('active', 'True') != 'False')
               for section in feeds.sections()]
    db = feeddb.open_db()
    try:
        return jsonify(feeddb.feed_overview(db, entries))
    finally:
        db.close()

# ---------- Feed discovery ----------

# not application/json: WordPress links its REST API that way
FEED_TYPES = {'application/rss+xml', 'application/atom+xml', 'application/feed+json', 'application/rdf+xml',
              'application/x-rss+xml', 'text/xml', 'application/xml'}
# tried if the page doesn't link a feed
COMMON_FEED_PATHS = ['/feed', '/rss', '/feed.xml', '/rss.xml', '/atom.xml', '/index.xml', '/feed/']
DISCOVERY_TIMEOUT = 15

def fetch_url(url):
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=DISCOVERY_TIMEOUT)
    response.raise_for_status()
    return response

def as_feed(response):
    """{'url', 'title'} if the response is a feed, else None."""
    parsed = feedparser.parse(response.content)
    if parsed.get('version') and (parsed.entries or parsed.feed.get('title')):
        return {'url': response.url, 'title': parsed.feed.get('title', '')}
    return None

def discover_feeds(url):
    """Feeds for a URL: the URL itself if it is a feed, else the feeds the page links with
    <link rel="alternate">, else feeds at the usual paths."""
    response = fetch_url(url)
    feed = as_feed(response)
    if feed:
        return [feed]
    found = []
    soup = BeautifulSoup(response.content, 'html.parser')
    for link in soup.find_all('link', href=True):
        rel = [r.lower() for r in (link.get('rel') or [])]
        if 'alternate' in rel and (link.get('type') or '').split(';')[0].strip().lower() in FEED_TYPES:
            href = urljoin(response.url, link['href'])
            if urlparse(href).scheme in ('http', 'https') and all(f['url'] != href for f in found):
                found.append({'url': href, 'title': (link.get('title') or '').strip()})
    if found:
        return found
    for path in COMMON_FEED_PATHS:
        try:
            feed = as_feed(fetch_url(urljoin(response.url, path)))
        except requests.RequestException:
            continue
        if feed:
            return [feed]
    return []

@app.route('/api/discover-feed', methods=['POST'])
def discover_feed():
    url = ((request.get_json(silent=True) or {}).get('url') or '').strip()
    if '://' not in url:
        url = 'https://' + url
    if urlparse(url).scheme not in ('http', 'https') or not urlparse(url).netloc:
        return jsonify({'error': 'Please enter a web address starting with http:// or https://.'}), 400
    try:
        feeds = discover_feeds(url)
    except requests.RequestException as e:
        return jsonify({'error': f'The page could not be loaded: {e}'}), 502
    if not feeds:
        return jsonify({'error': 'No feed found on this page.'}), 404
    return jsonify({'feeds': feeds})

# ---------- Logs ----------

LOG_NAMES = ['nsm', 'pocket-ersatz', 'archive-sort', 'pocket-mailer', 'pocket-mailer-epub']
LOG_TAIL_BYTES = 200_000  # roughly the last 2000 lines

@app.route('/api/logs/<name>', methods=['GET'])
def show_log(name):
    """The end of a script's log file (see common.setup_logging)."""
    if name not in LOG_NAMES:
        return 'Unknown log', 404
    path = os.path.join(common.LOG_DIR, f'{name}.log')
    try:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - LOG_TAIL_BYTES))
            data = f.read()
    except FileNotFoundError:
        return Response('No log yet, the script hasn\'t run since logging was set up.', mimetype='text/plain')
    text = data.decode('utf-8', errors='replace')
    if len(data) == LOG_TAIL_BYTES:
        text = text.split('\n', 1)[-1]  # drop the cut-off first line
    return Response(text, mimetype='text/plain')

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
    r'^(?:[0-9*/,-]+\s+){5}(?:'
    r'nsm\s+(?:/opt/venv/bin/)?python3\s+/app/' + CRON_SCRIPTS + r'(?:\s+--[a-z-]+(?:=[\w./-]+)?)*(?:\s+>>\s*/app/(?:data/)?[\w.-]+\.log\s+2>&1)?'
    r'|root\s+(?:rm -r /tmp/\*|pkill -f (?:/usr/local/bin/geckodriver|/opt/firefox/))'
    r')\s*;?\s*$'
)

def invalid_crontab_lines(content):
    """Return the lines that are not a schedule for one of the app's scripts (as user nsm) or
    maintenance jobs (as root). Cron runs the file as root, so a free-form crontab would allow
    running any command."""
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
    config_content = read_file(CONFIG_PATH)
    feeds_content = read_file(common.FEEDS_PATH)
    filter_content = read_file(common.FILTER_PATH)
    killfile_content = read_file(common.KILLFILE_PATH)  # Added killfile handling

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
                                 'scripts in /app are allowed, e.g. "58 * * * * nsm /opt/venv/bin/python3 '
                                 '/app/nsm.py". Rejected lines: ' + ' | '.join(bad_lines)}), 400

    # Save config.cfg if changed
    try:
        current_config = normalize(read_file(CONFIG_PATH))
    except FileNotFoundError:
        current_config = ""
    if current_config != normalize(config_content):
        write_file(CONFIG_PATH, config_content)

    # Save feeds.cfg if changed
    try:
        current_feeds = normalize(read_file(common.FEEDS_PATH))
    except FileNotFoundError:
        current_feeds = ""
    created_folders, folder_error = [], None
    if current_feeds != normalize(feeds_content):
        write_file(common.FEEDS_PATH, feeds_content)
        created_folders, folder_error = create_missing_feed_folders()

    # Save filter.txt if changed
    try:
        current_filter = normalize(read_file(common.FILTER_PATH))
    except FileNotFoundError:
        current_filter = ""
    if current_filter != normalize(filter_content):
        write_file(common.FILTER_PATH, filter_content)

    # Save killfile.txt if changed
    try:
        current_killfile = normalize(read_file(common.KILLFILE_PATH))
    except FileNotFoundError:
        current_killfile = ""
    if current_killfile != normalize(killfile_content):
        write_file(common.KILLFILE_PATH, killfile_content)

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

NSM_LOCK_PATH = common.data_path('nsm.lock')  # held by nsm.py while it runs

def nsm_running():
    with open(NSM_LOCK_PATH, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """The last run of every job (without output), e.g. to show a running job after a reload."""
    with _jobs_lock:
        return jsonify({name: {k: v for k, v in job.state().items() if k != 'lines'} for name, job in _jobs.items()})

@app.route('/api/jobs/<name>', methods=['POST'])
def run_job(name):
    """Start a script in the background; the page follows its output via GET."""
    if name not in JOBS:
        return jsonify({'error': 'Unknown job'}), 404
    with _jobs_lock:
        own_run = name in _jobs and _jobs[name].finished is None
    if name == 'fetch-feeds' and not own_run and nsm_running():
        return jsonify({'error': 'A feed run (cronjob) is already in progress. Its output is in the Logs tab.'}), 409
    job, started = start_job(name)
    return jsonify({**job.state(), 'already_running': not started})

@app.route('/api/jobs/<name>', methods=['GET'])
def job_state(name):
    with _jobs_lock:
        job = _jobs.get(name)
    if not job:
        return jsonify({'error': 'Not started yet'}), 404
    return jsonify(job.state(request.args.get('since', 0, type=int)))

def generate_download(script, filename, download_name, mimetype, extra_args=()):
    """Run a mailer script with --no-mail in a temp dir and return the generated file."""
    workdir = script_workdir()
    try:
        run_script(['python3', script, '--no-mail', *extra_args], cwd=workdir, check=True)
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
    feeds = common.load_feeds()
    wanted = {feeds[section].get('imap-mailbox', 'INBOX').strip() for section in feeds.sections()}
    wanted.discard('')
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
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
    with common.smtp_connection(host, port, user, password, timeout=15):
        pass

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
    config.read(CONFIG_PATH)
    try:
        imap = config['IMAP']
        with MailBox(imap['imapHost'], timeout=15).login(imap['imapUser'], imap['imapPasscode'], initial_folder=None) as mailbox:
            return jsonify(sorted(folder.name for folder in mailbox.folder.list()))
    except Exception as e:
        return jsonify({'error': str(e)}), 502

@app.route('/export-opml', methods=['GET'])
def export_opml():
    """Export feeds.cfg as an OPML file."""
    opml_path = common.data_path('feeds.opml')

    # Parse feeds.cfg
    config = common.load_feeds()

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
    feeds_path = common.FEEDS_PATH
    config = common.load_feeds(feeds_path)

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
