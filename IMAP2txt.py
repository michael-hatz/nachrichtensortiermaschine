#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""
IMAP2TXT
Erhalte ein ePub bzw. eine Textdatei per Mail mit allen deinen für's Später-Lesen gespeicherten Artikeln. Auf diese Weise kann man z.B. auch automatisch den Amazon Kindle befüllen.

Installation
* Installiert Python 3 und alle importierten Pakete
* Tragt im Kopf die Serveradresse eures Postfaches, den auszulesenden Ordner und die Adresse eures SMTP-Servers sowie die Zieladresse ein
"""

import markdownify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import pypandoc
 
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

###############################

def sendeanhang(to, subject, body, filename):
    # Nachrichtenobjekt erstellen
    message = MIMEMultipart()
 
    # Absender und Titel der Mail definieren
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = "Export"
 
    # Anhang dran
    file = "txt.txt"
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
    
#Mailbody lesen und alles in einen riesigen String packen
buchtext = ""
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        #emailinhalt auch von html news und newslettern auslesen und uebergeben
        emailinhalt = markdownify.markdownify(nachricht.html, heading_style="ATX")
        buchtext = emailinhalt + buchtext

#Pandoc und dann raussenden
pypandoc.convert_text(buchtext , 'plain' , 'markdown' , outputfile="txt.txt" , extra_args = ['--wrap=none'])
sendeanhang(receiver_email , "Export" , "Hallo" , "txt.txt")
print("done")