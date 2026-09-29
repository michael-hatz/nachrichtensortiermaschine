from flask import Flask, render_template, request, send_file, jsonify
import os
import subprocess
import configparser
import io
import shutil
import tempfile
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
from werkzeug.utils import secure_filename
from imap_tools import MailBox

app = Flask(__name__)
UPLOAD_FOLDER = '/app/data/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    # Read the contents of the files with utf-8 encoding
    config_content = read_file('/app/data/config.cfg')
    feeds_content = read_file('/app/data/feeds.cfg')
    filter_content = read_file('/app/data/filter.txt')
    killfile_content = read_file('/app/data/killfile.txt')  # Added killfile handling

    # Read the crontab
    try:
        # Read the cron job file directly
        with open('/etc/cron.d/myjobs', 'r') as f:
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
        crontab=crontab_content  # Pass crontab content to the template
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
        with open('/etc/cron.d/myjobs', 'r') as f:
            current_crontab = normalize(f.read())
    except FileNotFoundError:
        current_crontab = ""
    if current_crontab != crontab_content:
        with open('/etc/cron.d/myjobs', 'w') as crontab_file:
            crontab_file.write(crontab_content)
        os.chmod('/etc/cron.d/myjobs', 0o644)  # Ensure correct permissions

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

def generate_download(script, filename, download_name, mimetype):
    """Run a mailer script with --no-mail in a temp dir and return the generated file."""
    workdir = tempfile.mkdtemp()
    try:
        subprocess.run(['python3', script, '--no-mail'], cwd=workdir, check=True)
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
    return generate_download('/app/pocket-mailer-epub.py', 'Leseliste.epub',
                             f"Leseliste-{date.today():%Y%m%d}.epub", 'application/epub+zip')

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
            existing = {folder.name for folder in mailbox.folder.list()}
            for name in sorted(wanted - existing):
                mailbox.folder.create(name)
                mailbox.folder.subscribe(name, True)
                created.append(name)
    except Exception as e:
        return created, str(e)
    return created, None

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

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Debug: Log the uploaded file path
        print(f"Uploaded OPML file saved to: {file_path}")

        # Parse OPML file
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Error parsing OPML file: {e}")
            return "Invalid OPML file", 400

        # Debug: Log the parsed OPML structure
        print("Parsed OPML structure:")
        for outline in root.findall(".//outline"):
            print(outline.attrib)

        # Update feeds.cfg
        config = configparser.ConfigParser()
        feeds_path = '/app/data/feeds.cfg'
        config.read(feeds_path)

        added_feeds = []
        updated_feeds = []
        skipped_feeds = []

        for outline in root.findall(".//outline"):
            section = outline.get('title', outline.get('text', 'Unnamed Feed'))
            new_feed = {
                'url': outline.get('xmlUrl', ''),
                'fulltext': outline.get('fulltext', 'False'),
                'active': outline.get('active', 'True'),
                'imap-mailbox': outline.get('imap-mailbox', 'INBOX')
            }

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
    app.run(debug=True, host="0.0.0.0", port=5000)
