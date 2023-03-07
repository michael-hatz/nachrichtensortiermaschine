#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""Der Ersatz für Pocket, Instapaper & Co: Sende eine Mail mit einem Link an eine E-Mail-Adresse und erhalte eine E-Mail mit dem Volltext des Links zurück. Auf Wunsch auch mit AI-gesteuerter Zusammenfassung und Verschlagwortung.

Installation:
* Installiert Python 3 und alle importierten Pakete
* Ich benutze ein separates Postfach, an das ich die Mails sende. Es geht grundsätzlich auch mit einem Postfach. Dann könnt ihr den auszulesenden Ordner "INBOX" anpassen, aber dann müsst ihr herausfinden, wie man Mails automatisch in den entsprechenden Ordner sendet. Sollte mit Filterregeln gehen, aber das schränkt dann andere Mailarten ein. Stellt ihr etwa ein, dass alle Mails, welche von eurer eigenen Mailadresse stemmen, direkt in den auszulesenden Ordner sortiert werden, verhindert ihr z.B. dass ihr einfach hinter einer Paywall liegende Texte kopieren und an euch selbst mailen könnt
* Oben die IMAP-Adresse und die Logindaten für dieses Postfach eintragen
* Dann die Empfängeradresse eintragen
* Wenn Ihr einen OpenAI-API-Schlüssel habt, dann tragt ihn ein. Auf die Weise bekommt ihr eine automatisierte Zusammenfassung mit Schlagwörtern.
* Nun einen Cronjob einrichten, welcher regelmäßig ausgeführt wird. Das Skript loggt sich dann in das Postfach ein, liest den Link, zieht den Volltext, erstellt eine AI-gestützte Zusammenfassung, verschlagwortet alles und sendet euch das alles per Mail an die gewählte Adresse ein
* Bei mir läuft das Skript alle 10 Minuten, was den Traffic etwas begrenzt und da es sich um ein "SpäterLesen"-Skript handelt, ist Hektik hier auch absolut nicht angebracht.
* Wenn man die Skripte auf einem Raspberry Pi laufen lässt, bitte alle Anleitungen im Internet ignorieren, die einen anweisen den Cronjob mit "sudo crontab -e" einzurichten. Auf die Weise würde das Skript als root laufen, was aber nicht klappen wird. "crontab -e" lässt das Skript auf dem aktuellen User laufen, was korrekt ist.
"""


import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from imap_tools import MailBox
import trafilatura
from bs4 import BeautifulSoup
import markdown
import openai as ai

#Konfiguration IMAP-Eingangsserver, an den die zu speichernden Artikel gesendet werden 
imapHost = "example.com"
imapUser = "eingangsartikel@example.com"
imapPasscode = "passwort"
Eingangsordner = "INBOX" #hier IMAP-Ordner auswählen, in dem die Eingangsmails liegen
  
#Konfiguration SMTP
port = 587  # For starttls
smtp_server = "example.com"
sender_email = "eingangsartikel@example.com"
receiver_email = "deinwunderbarespostfachindemdudeinemailsliest@example.com"
password = "passwort"

#OpenAI API-Key
ai.api_key = ''
 
def getarticleandsendmail(artikel): 
    
    #trifalatura
    url = trafilatura.fetch_url(artikel)
    h = trafilatura.extract(url, include_comments=False, include_metadata=True, include_formatting=True)
    
    #titel extrahieren
    soup = BeautifulSoup(url, 'html.parser')
    titeldesdokuments = soup.title.string
           
      
    heruntergeladenertextinhtml = markdown.markdown(h)
    laengetext = len(h.split()) #berechnet wortanzahl
    laengetextstr = str(laengetext)

#AI-Krams
    try:
        anfrage = "Write a summary of this article in 5 bulletpoints. Put a * in front of each bulletpoint. Make two linebreaks after each bulletpoint. Write the summary in German. Also add 5 Tags based on the article. Put two ## in front of each tag  " + heruntergeladenertextinhtml 
        response = ai.Completion.create(
        #die Engine-Wahl für OpenAI ist entscheidend, curie ist bezahlbar, gpt-3 ist teuer, liefert auf den Prompt gute Ergebnisse und ChatGPT ist ungetestet
        engine="text-davinci-003", 
        prompt=anfrage,
        temperature=0.3,
        max_tokens=709,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
        )
        zusammenfassung = response.choices[0].text
    except:
        zusammenfassung = "Fehler bei der Generierung der Zusammenfassung" #einfach auskommentieren, wenn man nix generieren will oder die funktion ganz löschen   
#definiere nachricht
    message = MIMEMultipart("alternative")
    message["Subject"] = titeldesdokuments
    message["From"] = sender_email
    message["To"] = receiver_email
# hier zusammensetzung der mail, das kann man sicherlich noch verbessern
    text = "\n\n====================\n\n Titel: " + titeldesdokuments + " \n\nURL: " + artikel + "\n\n Länge: " + laengetextstr + " Wörter" + "\n\n\n" + zusammenfassung + "\n\n ====================\n\n\n" + h
    html = "\n\n====================\n\n<br>Titel:<br> " + titeldesdokuments + " \n\n<br>URL: " + artikel + "\n\n <br>Länge: " + laengetextstr + " Wörter" + "\n\n\n<br><br>" + zusammenfassung + "\n\n<br> ====================\n\n\n<br>" + heruntergeladenertextinhtml

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
    
#durchsuche Mail
with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch():
        emailinhalt = nachricht.text or nachricht.html
        mailbox.delete(nachricht.uid)
        print(emailinhalt)
        #regex durchsucht inhalt der Mails nach URLs
        regex = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+' 
        match = re.findall(regex, emailinhalt)
        #aktiviere pro Mail die Volltextmailingfunktion 
        for m in match:
            getarticleandsendmail(m)
