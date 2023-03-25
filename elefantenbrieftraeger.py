#!/usr/bin/python3
#-*- coding: utf-8 -*-
"""
## elefantenbrieftraeger.py
Sende eine Mail an eine Mailadresse und der Inhalt dieser Mail wird auf Mastodon gepostet.

Installation
* Installiert Python 3 und alle importierten Pakete
* Erstellt euch ein Mastodon-API-Secret. Klingt kompliziert, ist es aber nicht, Anleitung siehe hier [LIIIIIINK]
* Nun legt dieses Skript sowie die zwei generierten Dateien in den gleichen Ordner ab
* Tragt die entsprechenden Daten (Login/Secret) oben im Kopf ein
* Tragt die Daten eures Postfaches ein. Ich nutze hier ein eigenes Postfach, ihr könnt aber auch einen Unterordner eures bestehenden Postfaches nutzen.
* Ich empfehle dringend, dass ihr euch in eurem "Mastodon-Postfach" eine Whitelist anlegt und nur Mails von fest eingestellten Mailadressen akzeptiert. Das Skript tootet jede Mail, also auch jede Spammail!
* Nach dem Tooten wird die Mail kommentarlos gelöscht
* Ist die Mail länger als die Zeichenbegrenzung eurer Instanz, dann wird sie kommentarlos verworfen
* Bilder im Anhang werden als Bild dem Toot beigefügt"""

from mastodon import Mastodon
from imap_tools import MailBox

#Mastodon.create_app(
#    'pyelefantenbrieftraeger',
#    api_base_url = 'https://mastodon.social',
#    to_file = 'pyelefantenbrieftraeger_clientcred.secret'
#)

#Login Mastodon
mastodon = Mastodon(client_id = 'name_clientcred.secret',)
mastodon.log_in(
    'login@mastodonserver',
    'passwort',
    to_file = 'name_usercred.secret'
)

#Login Server
#Hinweis: Es lohnt sich das Postfach so einzustellen, dass nur bestimmte Mailadressen dorthin schreiben dürfen, um keine random Spammails zu mastodonieren
imapHost = "imap.example.com"
imapUser = "mastodon@example.com"
imapPasscode = "passwort"
Eingangsordner = "Inbox/TOOT" #hier IMAP-Ordner auswhlen, in dem die Eingangsmails liegen

#Tootlogik
mastodon = Mastodon(access_token = 'name_usercred.secret')

#Mails abrufen, Anhang checken, Posten

anhang = ""
with MailBox(imapHost).login(imapUser, imapPasscode, 'INBOX/TOOT') as mailbox:
   for nachricht in mailbox.fetch():
        for nachricht in mailbox.fetch():
            emailinhalt = nachricht.text or nachricht.html
        for att in nachricht.attachments:
            print(att.filename, att.content_type)
            with open(format(att.filename), 'wb') as f:           
                anhang = mastodon.media_post(att.payload, "image/jpeg")          
        mailbox.delete(nachricht.uid)
        mastodon.status_post(status=emailinhalt, media_ids=anhang)