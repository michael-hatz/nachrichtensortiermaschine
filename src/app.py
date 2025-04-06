from flask import Flask, render_template, request, send_file
import os
import subprocess
import configparser
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
from werkzeug.utils import secure_filename

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
    crontab_content = subprocess.check_output(['crontab', '-l'], text=True)
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
    # Get the new content from the forms and save them
    config_content = request.form.get('config', '')  # Use .get() to avoid KeyError
    feeds_content = request.form.get('feeds', '')
    filter_content = request.form.get('filter', '')
    killfile_content = request.form.get('killfile', '')  # Added killfile handling

    write_file('/app/data/config.cfg', config_content)
    write_file('/app/data/feeds.cfg', feeds_content)
    write_file('/app/data/filter.txt', filter_content)
    write_file('/app/data/killfile.txt', killfile_content)  # Save killfile content

    # Save the crontab
    crontab_content = request.form.get('crontab', '')
    with open('/tmp/crontab', 'w') as crontab_file:
        crontab_file.write(crontab_content)
    subprocess.run(['crontab', '/tmp/crontab'])

    return "Changes saved!"

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

        # Provide feedback to the user
        return (
            f"OPML imported successfully! "
            f"Added: {len(added_feeds)}, Updated: {len(updated_feeds)}, Skipped: {len(skipped_feeds)}"
        )

def read_file(file_path):
    """Read the content of a file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def write_file(file_path, content):
    """Write content to a file."""
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
