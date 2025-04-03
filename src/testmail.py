import configparser
import smtplib
from imap_tools import MailBox
from imap_tools import OR
from imap_tools import A, H
from datetime import date
import os
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

#global values
script_directory = os.path.dirname(os.path.abspath(__file__))

print(script_directory)

feedliste = configparser.ConfigParser()
feeddir =  os.path.join(script_directory, "/app/data/feeds.cfg")
feedliste.read(feeddir)
csv_file_path =  os.path.join(script_directory , "/app/data/urls.tsv")
print(csv_file_path)

#E-Mail-Configuration
config = configparser.ConfigParser()
configpath = os.path.join(script_directory , "/app/data/config.cfg")
config.read(configpath)
mail_dict = dict(config)

imapHost = mail_dict['IMAP']['imapHost']
imapUser = mail_dict['IMAP']['imapUser']
imapPasscode = mail_dict['IMAP']['imapPasscode']
  
#Konfiguration SMTP
port = mail_dict['SMTP']['port']
smtp_server = mail_dict['SMTP']['smtp_server']
sender_email = mail_dict['SMTP']['sender_email']
receiver_email = mail_dict['SMTP']['receiver_email']
password = mail_dict['SMTP']['password']

message = MIMEMultipart("alternative")
try:
    message["Subject"] = "TEST"
except AttributeError:
    article.title = "Kein Titel"
    message["Subject"] = article.link

message["From"] = sender_email
message["To"] = receiver_email

text = "text"
html = "html"

part1 = MIMEText(text, "plain")
part2 = MIMEText(html, "html")
message.attach(part1)
message.attach(part2)
# Add the special header
message['X-Special-Header'] = mailbox
#absenden mail
context = ssl.create_default_context()
with smtplib.SMTP(smtp_server, port) as server:
    server.starttls(context=context)
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, message.as_string())
