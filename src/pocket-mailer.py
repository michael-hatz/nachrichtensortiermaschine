#!/usr/bin/env python3
#-*- coding: utf-8 -*-

from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import os
import sys
from mailtext import html_to_text
import common

common.setup_logging("pocket-mailer")

#E-Mail-Configuration
config = common.load_config()
imapHost = config['IMAP']['imapHost']
imapUser = config['IMAP']['imapUser']
imapPasscode = config['IMAP']['imapPasscode']
Eingangsordner = config['Mailings']['unread_folder']
smtp_config = config['SMTP-Artikelpostfach']
receiver_email = smtp_config['receiver_email']

###############################

def sendeanhang(to, subject, body, filename):
    # Nachrichtenobjekt erstellen
    message = MIMEMultipart()
 
    # Titel der Mail definieren
    message['Subject'] = "Export"
 
    # Anhang dran
    file = "nachrichtensortiermaschine.txt"
    with open(file, 'rb') as attachment:
        obj = MIMEBase('application','octet-stream')
        obj.set_payload(attachment.read())
    encoders.encode_base64(obj)
    obj.add_header('Content-Disposition',"attachment; filename= "+file)
    message.attach(obj)

    #Mail Senden
    common.send_mail(smtp_config, message)
    print("YOUR MAIL HAS BEEN SENT SUCCESSFULLY")
    
# Mailbody lesen und alles in einen riesigen String packen
buchtext = ""
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(mark_seen=False, bulk=True):
        emailinhalt = ""

        # Try to process the HTML part
        if nachricht.html:
            try:
                emailinhalt = html_to_text(nachricht.html)
                print(f"HTML: {nachricht.subject} ({len(emailinhalt.split())} Wörter)")
            except Exception as e:
                print(f"Error processing HTML content: {e}")

        # Fallback to plain text if HTML is empty or fails
        if not emailinhalt and nachricht.text:
            emailinhalt = nachricht.text.strip()
            print(f"Text: {nachricht.subject} ({len(emailinhalt.split())} Wörter)")

        # Skip emails with no content
        if not emailinhalt:
            print(f"Warning: No content found for email {nachricht.subject}")
            continue

        # Append the processed content to the book text
        buchtext = emailinhalt.strip() + "\n\n" + buchtext.strip()

#Datei schreiben und dann raussenden
with open("nachrichtensortiermaschine.txt", "w", encoding="utf-8") as f:
    f.write(buchtext)
# --no-mail: nur Datei erzeugen (Download über das Webinterface)
if "--no-mail" not in sys.argv:
    sendeanhang(receiver_email , "Export" , "this is an automatic export of your read later folder from Nachrichtensortiermaschine" , "nachrichtensortiermaschine.txt")
print("done")

#aktueller stand
#das produziert ein plaintext und sendet es an die angegebene Mailaddi

#To Do:
# - die epubs sind vllig unformatiert und wackelig wie sau, funktionieren nicht richtig im reader
# - recherche, welche infos ein ePub genau braucht
# - sind gewissermassen gezippte HTML-Dateien, brauchen eine Metadateninformation