#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import xml2epub
import os
from bs4 import BeautifulSoup
import configparser

# Global values
script_directory = os.path.dirname(os.path.abspath(__file__))

# E-Mail Configuration
config = configparser.ConfigParser()
configpath = os.path.join(script_directory, "/app/data/config.cfg")
config.read(configpath)
mail_dict = dict(config)

imapHost = mail_dict['IMAP']['imapHost']
imapUser = mail_dict['IMAP']['imapUser']
imapPasscode = mail_dict['IMAP']['imapPasscode']
Eingangsordner = mail_dict['Mailings']['unread_folder']

# SMTP Configuration
port = mail_dict['SMTP']['port']
smtp_server = mail_dict['SMTP']['smtp_server']
sender_email = mail_dict['SMTP']['sender_email']
receiver_email = mail_dict['SMTP']['receiver_email']
password = mail_dict['SMTP']['password']

# EPUB Settings
dateiname = "Leseliste.epub"
book = xml2epub.Epub("Leseliste", creator='Michael', language='de', publisher='Nachrichtensortiermaschine')

###############################

def sendeanhang(to, subject, body, filename):
    """Send an email with the EPUB file as an attachment."""
    # Create the email message
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = subject

    # Attach the EPUB file
    with open(filename, 'rb') as attachment:
        obj = MIMEBase('application', 'octet-stream')
        obj.set_payload(attachment.read())
        encoders.encode_base64(obj)
        obj.add_header('Content-Disposition', f"attachment; filename={filename}")
        message.attach(obj)

    # Send the email
    email_session = smtplib.SMTP(smtp_server, port)
    email_session.starttls()
    email_session.login(sender_email, password)
    email_session.sendmail(sender_email, receiver_email, message.as_string())
    email_session.quit()
    print("YOUR MAIL HAS BEEN SENT SUCCESSFULLY")

# Process emails and add content to the EPUB
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        emailinhalt = ""

        # Try to process the HTML part
        if nachricht.html:
            try:
                # Use BeautifulSoup to clean and extract text from HTML
                soup = BeautifulSoup(nachricht.html, "html.parser")
                emailinhalt = soup.get_text(separator="\n").strip()
                print(f"Extracted HTML content: {emailinhalt}")  # Debug: Log HTML content
            except Exception as e:
                print(f"Error processing HTML content: {e}")

        # Fallback to plain text if HTML is empty or fails
        if not emailinhalt and nachricht.text:
            emailinhalt = nachricht.text.strip()
            print(f"Fallback to plain text content: {emailinhalt}")  # Debug: Log plain text content

        # Skip emails with no content
        if not emailinhalt:
            print(f"Warning: No content found for email {nachricht.subject}")
            continue

        # Add the email content as a chapter to the EPUB
        chapter = xml2epub.create_chapter_from_string(emailinhalt, title=nachricht.subject)
        book.add_chapter(chapter)

# Create the EPUB file
path = os.getcwd()
book.create_epub(path)

# Send the EPUB file as an email attachment
sendeanhang(receiver_email, "Export", "This is an automatic export of your read-later folder from Nachrichtensortiermaschine", dateiname)
print("done")