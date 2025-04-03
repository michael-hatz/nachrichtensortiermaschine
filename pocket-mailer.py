#!/usr/bin/env python3
#-*- coding: utf-8 -*-

import markdownify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import pypandoc
import os
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
port = mail_dict['SMTP-Artikelpostfach']['port']
smtp_server = mail_dict['SMTP-Artikelpostfach']['smtp_server']
sender_email = mail_dict['SMTP-Artikelpostfach']['sender_email']
receiver_email = mail_dict['SMTP-Artikelpostfach']['receiver_email']
password = mail_dict['SMTP-Artikelpostfach']['password']

###############################

def sendeanhang(to, subject, body, filename):
    # Nachrichtenobjekt erstellen
    message = MIMEMultipart()
 
    # Absender und Titel der Mail definieren
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = "Export"
 
    # Anhang dran
    file = "nachrichtensortiermaschine.txt"
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
buchtext = ""
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        #emailinhalt auch von html news und newslettern auslesen und uebergeben
        emailinhalt = markdownify.markdownify(nachricht.html, heading_style="ATX")
        buchtext = emailinhalt + buchtext

#Pandoc und dann raussenden
pypandoc.convert_text(buchtext , 'plain' , 'markdown' , outputfile="nachrichtensortiermaschine.txt" , extra_args = ['--wrap=none'])
sendeanhang(receiver_email , "Export" , "this is an automatic export of your read later folder from Nachrichtensortiermaschine" , "nachrichtensortiermaschine.txt")
print("done")

#aktueller stand
#das produziert ein plaintext und sendet es an die angegebene Mailaddi

#To Do:
# - die epubs sind vllig unformatiert und wackelig wie sau, funktionieren nicht richtig im reader
# - recherche, welche infos ein ePub genau braucht
# - sind gewissermassen gezippte HTML-Dateien, brauchen eine Metadateninformation