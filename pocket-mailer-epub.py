#!/usr/bin/env python3
#-*- coding: utf-8 -*-

import markdownify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import xml2epub
import os
from datetime import date
import configparser
 
#global values
script_directory = os.path.dirname(os.path.abspath(__file__))

#E-Mail-Configuration
config = configparser.ConfigParser()
configpath = os.path.join(script_directory , "/app/data/config.cfg")
config.read(configpath)
mail_dict = dict(config)

imapHost = mail_dict['IMAP']['imapHost']
imapUser = mail_dict['IMAP']['imapUser']
imapPasscode = mail_dict['IMAP']['imapPasscode']
Eingangsordner = mail_dict['Mailings']['unread_folder']
  
#Konfiguration SMTP
port = mail_dict['SMTP']['port']
smtp_server = mail_dict['SMTP']['smtp_server']
sender_email = mail_dict['SMTP']['sender_email']
receiver_email = mail_dict['SMTP']['receiver_email']
password = mail_dict['SMTP']['password']

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
    
#Mailbody lesen und alles in einen riesigen String packen

with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        #emailinhalt auch von html news und newslettern auslesen und uebergeben
        chapter0 = xml2epub.create_chapter_from_string(nachricht.html, title=nachricht.subject)
        book.add_chapter(chapter0)
path = os.getcwd()
book.create_epub(path)

#Pandoc und dann raussenden
#pypandoc.convert_text(buchtext , 'plain' , 'markdown' , outputfile="txt.txt" , extra_args = ['--wrap=none'])
sendeanhang(receiver_email , "Export" , "Hallo" , "Leseliste.epub")
#print("done")

#aktueller stand
#das produziert ein plaintext und sendet es an die angegebene Mailaddi

#To Do:
# - die epubs sind vllig unformatiert und wackelig wie sau, funktionieren nicht richtig im reader
# - recherche, welche infos ein ePub genau braucht
# - sind gewissermassen gezippte HTML-Dateien, brauchen eine Metadateninformation