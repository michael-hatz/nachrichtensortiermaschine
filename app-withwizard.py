import os
from flask import Flask, render_template, request, redirect, url_for
import xml.etree.ElementTree as ET

app = Flask(__name__)

# Ensure the app directory exists for config files
if not os.path.exists('/app/data'):
    os.makedirs('/app/data')

# Initialize a dictionary to store wizard inputs temporarily
wizard_data = {
    "imap": {},
    "smtp": {},
    "feeds": [],
    "filter": []
}

# --- Original config editing routes ---
@app.route('/config', methods=['GET', 'POST'])
def edit_config():
    if request.method == 'POST':
        # Save the edited config file
        with open('/app/data/config.cfg', 'w') as f:
            f.write(request.form['config'])
        with open('/app/data/feeds.cfg', 'w') as f:
            f.write(request.form['feeds'])
        with open('/app/data/filter.txt', 'w') as f:
            f.write(request.form['filter'])
        return redirect(url_for('edit_config'))
    
    # Load the existing config files
    with open('/app/data/config.cfg', 'r') as f:
        config = f.read()
    with open('/app/data/feeds.cfg', 'r') as f:
        feeds = f.read()
    with open('/app/data/filter.txt', 'r') as f:
        filter_text = f.read()
    
    return render_template('edit_config.html', config=config, feeds=feeds, filter_text=filter_text)


# --- New wizard routes for first-time installation ---
@app.route('/wizard', methods=['GET', 'POST'])
def wizard():
    if request.method == 'POST':
        # Step 1: IMAP configuration
        if 'imap_host' in request.form:
            wizard_data['imap'] = {
                "imapHost": request.form['imap_host'],
                "imapUser": request.form['imap_user'],
                "imapPasscode": request.form['imap_passcode'],
                "Eingangsordner": request.form['eingangsordner']
            }
            return redirect(url_for('smtp_setup'))

        # Step 2: SMTP configuration
        elif 'smtp_host' in request.form:
            wizard_data['smtp'] = {
                "smtp_server": request.form['smtp_host'],
                "sender_email": request.form['sender_email'],
                "receiver_email": request.form['receiver_email'],
                "password": request.form['smtp_pass']
            }
            return redirect(url_for('feed_setup'))

        # Step 3: Feed configuration
        elif 'feed_url' in request.form:
            feed = {
                "url": request.form['feed_url'],
                "fulltext": request.form.get('fulltext', 'False'),
                "active": request.form.get('active', 'True'),
                "imap-mailbox": request.form['imap_mailbox']
            }
            wizard_data['feeds'].append(feed)
            return redirect(url_for('feed_setup'))

        # Step 4: Filter configuration
        elif 'filter_line' in request.form:
            wizard_data['filter'].append(request.form['filter_line'])
            return redirect(url_for('finish_wizard'))

    return render_template('wizard_step1.html')


@app.route('/smtp', methods=['GET', 'POST'])
def smtp_setup():
    return render_template('wizard_step2.html')


@app.route('/feeds', methods=['GET', 'POST'])
def feed_setup():
    if request.method == 'POST' and 'finish_feeds' in request.form:
        return redirect(url_for('filter_setup'))
    
    return render_template('wizard_step3.html', feeds=wizard_data['feeds'])


@app.route('/filters', methods=['GET', 'POST'])
def filter_setup():
    return render_template('wizard_step4.html')


@app.route('/finish', methods=['GET', 'POST'])
def finish_wizard():
    # Generate config.cfg
    config_content = f"""
    [IMAP]
    imapHost = {wizard_data['imap']['imapHost']}
    imapUser = {wizard_data['imap']['imapUser']}
    imapPasscode = {wizard_data['imap']['imapPasscode']}

    [IMAP-Artikelpostfach]
    imapHost = mailserver.example.com
    imapUser = artikelpostfach@example.com
    imapPasscode = password
    Eingangsordner = "INBOX"

    [Mailings]
    unread_folder = Inbox/artikel_unread

    [SMTP]
    smtp_server = {wizard_data['smtp']['smtp_server']}
    sender_email = {wizard_data['smtp']['sender_email']}
    receiver_email = {wizard_data['smtp']['receiver_email']}
    password = {wizard_data['smtp']['password']}

    [SMTP-Artikelpostfach]
    smtp_server = smtp.example.com
    sender_email = artikelpostfach@example.com
    receiver_email = empfänger@example.com
    password = fff

    [options]
    filterfolder = Papierkorb
    """
    
    with open('/app/data/config.cfg', 'w') as f:
        f.write(config_content)

    # Generate feeds.cfg
    feeds_content = ""
    for feed in wizard_data['feeds']:
        feeds_content += f"""
        [feed.{feed['url']}]
        url = {feed['url']}
        fulltext = {feed['fulltext']}
        active = {feed['active']}
        imap-mailbox = {feed['imap-mailbox']}
        """
    
    with open('/app/data/feeds.cfg', 'w') as f:
        f.write(feeds_content)

    # Generate filter.txt
    filter_content = "\n".join(wizard_data['filter'])

    with open('/app/data/filter.txt', 'w') as f:
        f.write(filter_content)

    return "Configuration complete! Files generated."


# Helper to parse OPML files
def parse_opml(opml_file):
    tree = ET.parse(opml_file)
    root = tree.getroot()
    
    feeds = []
    for outline in root.findall('.//outline'):
        feed_url = outline.attrib.get('xmlUrl')
        if feed_url:
            feed = {
                "url": feed_url,
                "fulltext": "False",
                "active": "True",
                "imap-mailbox": "INBOX"
            }
            feeds.append(feed)
    return feeds


# Handle OPML file upload
@app.route('/upload_opml', methods=['POST'])
def upload_opml():
    if 'opml_file' not in request.files:
        return redirect(request.url)
    
    file = request.files['opml_file']
    if file.filename.endswith('.opml'):
        feeds = parse_opml(file)
        wizard_data['feeds'].extend(feeds)
        return redirect(url_for('feed_setup'))

    return "Invalid file format. Please upload an OPML file."


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

