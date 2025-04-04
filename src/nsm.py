import feedparser
import configparser
import smtplib
from imap_tools import MailBox
from imap_tools import OR
from imap_tools import A, H
from datetime import date
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import time
import pandas as pd
import os
import trafilatura
from bs4 import BeautifulSoup
import markdown


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
filterfolder = mail_dict['options']['filterfolder']
  
#Konfiguration SMTP
port = mail_dict['SMTP']['port']
smtp_server = mail_dict['SMTP']['smtp_server']
sender_email = mail_dict['SMTP']['sender_email']
receiver_email = mail_dict['SMTP']['receiver_email']
password = mail_dict['SMTP']['password']

def load_killfile():
    """Load the killfile.txt into a list of strings."""
    killfile_path = os.path.join(script_directory, "/app/data/killfile.txt")
    with open(killfile_path, "r", encoding="utf-8") as file:
        return [line.strip() for line in file]

def filter_killfile(content, killfile):
    """Remove strings in killfile from the content."""
    for phrase in killfile:
        content = content.replace(phrase, "")
    return content

def create_email(artikel_url, artikel_titel, artikel_content, mailbox):
    # Load killfile and filter content
    killfile = load_killfile()
    artikel_content = filter_killfile(artikel_content, killfile)

    # Define the email message
    message = MIMEMultipart("alternative")
    try:
        message["Subject"] = artikel_titel
    except AttributeError:
        artikel_titel = "Kein Titel"
        message["Subject"] = artikel_url

    message["From"] = sender_email
    message["To"] = receiver_email

    text = artikel_content
    html = artikel_content

    # Calculate length
    html = str(html)
    text = str(text)
    laengetext = len(html.split())
    laengetextstr = str(laengetext)

    # Build HTML email
    html = (
        f"\n\n====================\n\n<br>Titel: {artikel_titel} \n\n<br>URL: "
        f'<a href="{artikel_url}">{artikel_url}</a>'
        f"\n\n <br>Länge: {laengetextstr} Wörter\n\n\n"
        f"\n\n<br> ====================\n\n\n<br>{html}"
    )
    text = (
        f"\n\n====================\n\n<br>Titel: {artikel_titel} \n\n<br>URL: "
        f'<a href="{artikel_url}">{artikel_url}</a>'
        f"\n\n <br>Länge: {laengetextstr} Wörter\n\n\n"
        f"\n\n<br> ====================\n\n\n<br>{text}"
    )

    # Attach parts
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)

    # Add header and send email
    message["X-Special-Header"] = mailbox
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, port) as server:
        server.starttls(context=context)
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())

def mailsort(header):
    time.sleep(10) #ist hier, damit die Mails Zeit haben anzukommen 
    with MailBox(imapHost).login(imapUser, imapPasscode, initial_folder='INBOX') as mailbox:
    # nur mails mit special header suchen
        emails_with_special_header = mailbox.fetch(A(header=[H("X-Special-Header" , value=header)]), charset='utf-8', bulk=True, mark_seen=False)

        # Print the subject of matching emails
        for email in emails_with_special_header:
            mailbox.move(email.uid, header)   

def mailchecker(Eingangsordner):
    #öffne Filterliste
    file_path = os.path.join(script_directory , "/app/data/filter.txt")
    filter = []
    with open(file_path, "r", encoding="ISO-8859-1") as file:
        for line in file:
            filter.append(line.strip())
    
    filterlower = [element.lower() for element in filter]

    with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
          #hier ist der ort, um in die abfrage auch noch den Check nach Mailheader aufzunehmen, damit nur RSS-Mails gefiltert werden  
        for nachricht in mailbox.fetch(OR(subject=filter), charset='utf-8', bulk=True, mark_seen=False):
            betreff = nachricht.subject
            betreff = betreff.lower()

            if(any(element in betreff for element in filterlower)):
                for element in filterlower:
                    if element in betreff:
                        print("Matched element:", element)
  
                
                mailbox.move(nachricht.uid, filterfolder)

def full_text2(url, mailbox, seen_urls):
    
    feed = feedparser.parse(url)
    for entry in feed.entries:
        
# ist neue URL bereits in Dataframe?
        if entry.link not in seen_urls['URL'].values:
            print(entry.link)
            text_trafilatura = trafilatura.fetch_url(entry.link)
            new_data = pd.DataFrame({'URL': [entry.link]})
            seen_urls = pd.concat([seen_urls, new_data], ignore_index=True)
            print("new_data:" , new_data)                
            entry.content = [{'type': 'text/plain', 'language': None, 'base': '', 'value': 'Test'}]
            if entry.content is not None and not isinstance(entry.content, Exception):
            # Code to execute if text_trafilatura is not None and not an error
                h = trafilatura.extract(text_trafilatura, include_comments=False, include_links=True, include_formatting=True)              
                if h is not None:
                    entry.content = markdown.markdown(h)
                    #entry.content.value = markdown.markdown(h)
                    create_email(entry.link, entry.title, entry.content, mailbox)
                else:
                    print("h war leer")
            else:
            # Code to execute if text_trafilatura is None or an error
                print("Text konnte nicht abgerufen werden oder None")
            #trifalatura
    seen_urls.to_csv(csv_file_path, sep='\t', index=False)  

def read_rss_feed(url, mailbox, seen_urls):
    #print("read_rss_feed" , url)
    #diese Nutzung von Feedparser ist, weil einige Seiten den Feedparser direkt blocken, bzw. requests ohne header
    feed = feedparser.parse(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).content)
    
    for entry in feed.entries:
    # Check if the new URL is already in the DataFrame
        if entry.link not in seen_urls['URL'].values:
            # Create a new DataFrame with the new URL
            new_data = pd.DataFrame({'URL': [entry.link]})
            #print("new_data:" , new_data)
            # Concatenate the new DataFrame with the existing one
            seen_urls = pd.concat([seen_urls, new_data], ignore_index=True)
            content = "kein Content in Feed"
            #title = getattr(entry, 'title', entry.link)
            if hasattr(entry, 'content'):
                content = entry.content
                if hasattr(content[0], 'value'):
                    content = content[0].value
                    #print("hat content.value")


            else:
                content = entry.summary
            #print(entry)
            if hasattr(entry, 'media_content'):
                x = entry.media_content[0]['url']
                print("hat media_content")
                content = content + '<br><br><img src="' + x + '" width="800">'
                print(content)
            if hasattr(entry, 'title'):
                title = entry.title
            else:
                title = entry.link          
                    
            create_email(entry.link, title, content, mailbox)
    seen_urls.to_csv(csv_file_path, sep='\t', index=False)

def errormailer(textexception):
    message = MIMEMultipart("alternative")
    message["Subject"] = "Fehler bei Skriptausführung"
    message["From"] = sender_email
    message["To"] = receiver_email
    text = textexception
    html = textexception
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)
#absenden mail
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, port) as server:
        server.starttls(context=context)
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())



def main():
    
    for section in feedliste.sections():
        seen_urls = pd.read_csv(csv_file_path, sep='\t')
        section_dict = dict(feedliste[section])
        #print(section_dict['fulltext'])
        print(section_dict['imap-mailbox'])
        if section_dict['active'] != "False":
            if section_dict['fulltext'] == "True":
                full_text2(section_dict['url'], section_dict['imap-mailbox'], seen_urls)
            else:
                read_rss_feed(section_dict['url'], section_dict['imap-mailbox'], seen_urls)
            mailsort(section_dict['imap-mailbox'])
            mailchecker(section_dict['imap-mailbox'])
        else:
            pass    
    
    print("Fertig")
        
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
        e = str(e)
        errormailer(e)


"""
#2024-01-01 Aktueller Stand: 


Bugs:
    * bestimmte Spezialfeeds wie der von Mastodon gehen aktuell nur begrenzt. Ursache dafür ist, dass diese Feeds arg merkwürdig zusammengesetzt sind
    * aktuell: Ist größtenteils gefixt, außer wie bei Verrückte Geschichte, wenn Bildbeschreibung und Text und Bild zusammenkommen
    
To Do:
    * prints aufräumen,

Ideen:
     * backup aller Links in die Wayback Machine von Archive.org
     * Summary
     * Tags?
     * verbessere print-statements
     * Idee: Option für Bilder
     * Filterfunktion verbessern
     * Support von externen Filterlisten wie uBlock sie hat
     * Filtern der Feeds auf der Basis des Headers, so dass man das auch in normalen Postfächern nutzen kann            
     """
