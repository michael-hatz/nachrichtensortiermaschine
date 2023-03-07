#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""IMAP2EPUB
Erhalte ein ePub bzw. eine Textdatei per Mail mit allen deinen für's Später-Lesen gespeicherten Artikeln. Auf diese Weise kann man z.B. auch automatisch den Amazon Kindle befüllen.

Installation
* Installiert Python 3 und alle importierten Pakete
* Tragt im Kopf die Serveradresse eures Postfaches, den auszulesenden Ordner und die Adresse eures SMTP-Servers sowie die Zieladresse ein
* Ungetestet: Amazon Kindles können per Mail bespielt werden. Wenn ihr eure individuelle Adresse hier eintragt, müssten die ePubs im Kindle ankommen
"""

import markdownify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import xml2epub
import os
from datetime import date

#Konfiguration IMAP-Eingangsserver 
imapHost = "imap.example.com"
imapUser = "deinwunderbarespostfachindemdudeinemailsliest@example.com"
imapPasscode = "passwort"
Eingangsordner = "Inbox/artikel_unread" #hier IMAP-Ordner auswhlen, in dem die Eingangsmails liegen
  
#Konfiguration SMTP
port = 587  # For starttls
smtp_server = "smtp.example.com"
sender_email = "absender@example.com"
receiver_email = "empfaenger@example.com"
password = "passwort"

#epub-Einstellungen
dateiname = "Leseliste.epub"

book = xml2epub.Epub("Leseliste", creator='Michael', language='de', publisher='Nachrichtensortiermaschine')

###############################

def sendeanhang(to, subject, body, filename):
    # Nachrichtenobjekt erstellen
    message = MIMEMultipart()
 
    # Absender und Titel der Mail definieren
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = "Epub-Mailing"
 
    # Anhang dran
    file = "Leseliste.epub"
    attachment = open(file,'rb')
    
    obj = MIMEBase('application','octet-stream')
    obj.set_payload((attachment).read())
    encoders.encode_base64(obj)
    obj.add_header('Content-Disposition',"attachment; filename= "+file)
    message.attach(obj)
    my_message = message.as_string()

    #Mail Senden
    email_session = smtplib.SMTP(smtp_server, port)
    email_session.starttls()
    email_session.login(sender_email,password)
    email_session.sendmail(sender_email,receiver_email,my_message)
    email_session.quit()
    print("YOUR MAIL HAS BEEN SENT SUCCESSFULLY")
    
#hier wird epub erstellt
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        #emailinhalt auch von html news und newslettern auslesen und uebergeben
        chapter0 = xml2epub.create_chapter_from_string(nachricht.html, title=nachricht.subject)
        book.add_chapter(chapter0)
path = os.getcwd()
book.create_epub(path)
sendeanhang(receiver_email , "Export" , "Hallo" , "Leseliste.epub")