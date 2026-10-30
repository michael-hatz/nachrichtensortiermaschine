from collections import defaultdict
from imap_tools import MailBox
import common

# Moves read articles from the archive folder back into their feed folder.
# nsm.py stores the target folder of every article in the X-Special-Header.

common.setup_logging("archive-sort")
config = common.load_config()

imapHost = config['IMAP']['imapHost']
imapUser = config['IMAP']['imapUser']
imapPasscode = config['IMAP']['imapPasscode']
archive_folder = config.get('Mailings', 'archive_folder', fallback='INBOX/artikel_unread/_archive')

with MailBox(imapHost).login(imapUser, imapPasscode) as mailbox:
    if not mailbox.folder.exists(archive_folder):
        print(f"Archivordner {archive_folder} existiert nicht")
        raise SystemExit
    mailbox.folder.set(archive_folder)

    targets = defaultdict(list)
    for nachricht in mailbox.fetch(headers_only=True, mark_seen=False, bulk=True):
        header = nachricht.headers.get('x-special-header')
        if not header:
            continue  # not an article from nsm.py, leave it where it is
        target = header[0].strip()
        if target and target != archive_folder:
            targets[target].append(nachricht.uid)

    for target, uids in targets.items():
        if not mailbox.folder.exists(target):
            print(f"Ordner {target} existiert nicht, {len(uids)} Mails bleiben im Archiv")
            continue
        mailbox.move(uids, target)
        print(f"{len(uids)} Mails nach {target} verschoben")
