"""
## mastodon-ordner.py
Verschiebe eine Mail in einen Ordner und das Skript erstellt daraus einen Toot und postet ihn.

Installation
* Installiert Python 3 und alle importierten Pakete
* Erstellt euch ein Mastodon-API-Secret. Klingt kompliziert, ist es aber nicht, Anleitung siehe hier [LIIIIIINK]
* Nun legt dieses Skript sowie die zwei generierten Dateien in den gleichen Ordner ab
* Tragt die entsprechenden Daten (Login/Secret) oben im Kopf ein
* Tragt die Daten eures Postfaches und den auszulesenden Ordner ein (im Standard INBOX/Mastodon)
* Definiert einen Cronjob, der regelmäßig das Skript ausführt

Was passiert nun? 
* Ihr verschiebt eine Mail in den Ordner
* Das Skript durchsucht die Mail nach Links und nimmt den 1. Link, den es findet. Bei RSS2Email-Mails und meinem ReadLater-Skript ist dies immer der Link zum Artikel. Vorsicht: Bei Newslettern und anderen Mails ist das nicht der Fall!
* Nun nimmt das Skript den Betreff der Mail, kombiniert ihn mit dem Link und erstellt einen Toot mit dem Inhalt Betreffzeile + Link
* Dieser wird nun veröffentlicht
"""

from imap_tools import MailBox
import re
from mastodon import Mastodon

#Konfiguration IMAP-Eingangsserver 
imapHost = "imap.example.com"
imapUser = "mail@example.com"
imapPasscode = "passwort"
Eingangsordner = "INBOX/Mastodon" #hier IMAP-Ordner auswhlen, in den die zu trötenden Mail liegen
Archivordner = "INBOX/artikel_unread/_archive"

#Login Mastodon
mastodon = Mastodon(client_id = 'hier .secret',)
mastodon.log_in(
    'login@mastodon.server',
    'passwort-für-server',
    to_file = 'name_usercred.secret'
)

#Tootlogik
mastodon = Mastodon(access_token = 'name_usercred.secret')

with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(charset='utf-8', bulk=True, limit=1):
        emailinhalt = nachricht.text or nachricht.html
        nachrichtid = nachricht.uid
        #regex durchsucht inhalt der Mails nach URLs
        regex = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+' 
        match = re.findall(regex, emailinhalt)
        #print(match)
        match = ''.join(match[0])
        if match[-1] == ">":
            match = match[:-1]
        print(match)
        betreff = nachricht.subject
        toot = betreff + " " + str(match)        
        print(toot)
        mastodon.status_post(status=toot)
        print(nachrichtid)
#auch hier wieder grob gepfuscht - aus irgendeinem Grund haut er einen Fehler bei mehr als einer
#nachricht im Ordner. Die fehlerwerfende Mail bleibt aber erhalten und funktioniert
#beim nächsten Lauf. Was erschreckenderweise bei einem regelmäßigen Cronjob als Buffer dient
#und unerwartet total gut ist - daher ist das Limit der abzurufenden Mails auf 1 gesetzt :)
        mailbox.move(nachrichtid, Archivordner)
