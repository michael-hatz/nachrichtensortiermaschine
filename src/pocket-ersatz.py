

"""Der Ersatz für Pocket, Instapaper & Co: Sende eine Mail mit einem Link an eine E-Mail-Adresse und erhalte eine E-Mail mit dem Volltext des Links zurück. Auf Wunsch auch mit AI-gesteuerter Zusammenfassung und Verschlagwortung.

Installation:
* Installiert Python 3 und alle importierten Pakete
* Ich benutze ein separates Postfach, an das ich die Mails sende. Es geht grundsätzlich auch mit einem Postfach. Dann könnt ihr den auszulesenden Ordner "INBOX" anpassen, aber dann müsst ihr herausfinden, wie man Mails automatisch in den entsprechenden Ordner sendet. Sollte mit Filterregeln gehen, aber das schränkt dann andere Mailarten ein. Stellt ihr etwa ein, dass alle Mails, welche von eurer eigenen Mailadresse stemmen, direkt in den auszulesenden Ordner sortiert werden, verhindert ihr z.B. dass ihr einfach hinter einer Paywall liegende Texte kopieren und an euch selbst mailen könnt
* Oben die IMAP-Adresse und die Logindaten, die Empfängeradresse in die config.cfg eintragen
* Wenn Ihr einen OpenAI-API-Schlüssel habt, dann tragt ihn ein. Auf die Weise bekommt ihr eine automatisierte Zusammenfassung mit Schlagwörtern. Ich für mich hab es deaktiviert, weil zu teuer
* Nun einen Cronjob einrichten, welcher regelmäßig ausgeführt wird. Das Skript loggt sich dann in das Postfach ein, liest den Link, zieht den Volltext, erstellt eine AI-gestützte Zusammenfassung, verschlagwortet alles und sendet euch das alles per Mail an die gewählte Adresse ein
* Bei mir läuft das Skript alle 0 Minuten, was den Traffic etwas begrenzt und da es sich um ein "SpäterLesen"-Skript handelt, ist Hektik hier auch absolut nicht angebracht.
* Wenn man die Skripte auf einem Raspberry Pi laufen lässt, bitte alle Anleitungen im Internet ignorieren, die einen anweisen den Cronjob mit "sudo crontab -e" einzurichten. Auf die Weise würde das Skript als root laufen, was aber nicht klappen wird. "crontab -e" lässt das Skript auf dem aktuellen User laufen, was korrekt ist.
"""

import configparser
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
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
import time
import sys

script_directory = os.path.dirname(os.path.abspath(__file__))
geckodriver_path = "/usr/local/bin/geckodriver"  # specify the path to your geckodriver

#E-Mail-Configuration
config = configparser.ConfigParser()
configpath = os.path.join(script_directory , "/app/data/config.cfg")
config.read(configpath)
mail_dict = dict(config)

imapHost = mail_dict['IMAP-Artikelpostfach']['imapHost']
imapUser = mail_dict['IMAP-Artikelpostfach']['imapUser']
imapPasscode = mail_dict['IMAP-Artikelpostfach']['imapPasscode']
Eingangsordner = mail_dict['IMAP-Artikelpostfach']['Eingangsordner']
#Konfiguration SMTP
port = mail_dict['SMTP-Artikelpostfach']['port']
smtp_server = mail_dict['SMTP-Artikelpostfach']['smtp_server']
sender_email = mail_dict['SMTP-Artikelpostfach']['sender_email']
receiver_email = mail_dict['SMTP-Artikelpostfach']['receiver_email']
password = mail_dict['SMTP-Artikelpostfach']['password']


#setup selenium
addon_path1 = r"/app/istilldontcareaboutcookies-1.1.4.xpi"
addon_path2 = r"/app/bypass-paywalls-firefox.xpi"

firefox_options = Options()
firefox_options.add_argument("--headless")
firefox_options.add_argument('--no-sandbox')
firefox_options.add_argument("--profile")
firefox_options.add_argument("/dev/null")
firefox_options.add_argument("--purgecaches")
firefox_options.add_argument('--disable-dev-shm-usage')
firefox_options.binary_location = "/usr/local/bin/firefox"

driver_service = webdriver.FirefoxService(executable_path=geckodriver_path)
driver = webdriver.Firefox(options=firefox_options, service=driver_service)
driver.install_addon(addon_path1)
driver.install_addon(addon_path2)



#OpenAI API-Key
ai.api_key = mail_dict['options']['openai-key']

def getarticleandsendmail(artikel): 
    
#trifalatura
    driver.vars = {}
    print(artikel)
    driver.get(artikel)
    print("versuche artikel zu laden")
    time.sleep(5)
    page_source = driver.page_source
    #print(page_source)
    #url = trafilatura.fetch_url(artikel)
    h = trafilatura.extract(page_source, include_comments=False, include_formatting=True)
    #print(h)
#titel extrahieren
    #soup = BeautifulSoup(url, 'html.parser')
    #titeldesdokuments = soup.title.string
    #print("zeile 92")
    titeldesdokuments = driver.title
    #print("zeile 94")
    driver.quit()
    ## 20.12.22: Hier hackt es gerade leicht, da Trafilatura eben einen extrahierten text liefert
    
    heruntergeladenertextinhtml = markdown.markdown(h)
    #print("zeile 99")
    laengetext = len(h.split()) #berechnet wortanzahl
    laengetextstr = str(laengetext)

#AI-Krams
    try:
        anfrage = "Write a summary of this article in 5 bulletpoints. Put a * in front of each bulletpoint. Make two linebreaks after each bulletpoint. Write the summary in German. Also add 5 Tags based on the article. Put two ## in front of each tag  " + heruntergeladenertextinhtml 
        response = ai.Completion.create(
        engine="text-curie-001",
        prompt=anfrage,
        temperature=0.3,
        max_tokens=709,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
        )
        zusammenfassung = response.choices[0].text
    except:
        zusammenfassung = ""    
#definiere nachricht
    message = MIMEMultipart("alternative")
    message["Subject"] = titeldesdokuments
    message["From"] = sender_email
    message["To"] = receiver_email
# hier zusammensetzung der mail, das kann man sicherlich noch verbessern
    text = "\n\n====================\n\n <br>Titel: " + titeldesdokuments + " \n\n<br>URL: " + '<a href="' + artikel + '">' + artikel + '</a>' + "\n\n <br>Länge: " + laengetextstr + " Wörter" + "\n\n\n" + zusammenfassung + "n\n <br>====================\n\n\n<br>" + heruntergeladenertextinhtml
    html = "\n\n====================\n\n <br>Titel: " + titeldesdokuments + " \n\n<br>URL: " + '<a href="' + artikel + '">' + artikel + '</a>' + "\n\n <br>Länge: " + laengetextstr + " Wörter" + "\n\n\n" + zusammenfassung + "\n\n <br>====================\n\n\n<br>" + heruntergeladenertextinhtml

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
    print("Mail gesendet")
    
#durchsuche Mail
with MailBox(imapHost).login(imapUser, imapPasscode, 'INBOX') as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        emailinhalt = nachricht.text or nachricht.html
        #mailbox.delete(nachricht.uid)
        mailbox.move(nachricht.uid, 'Archiv')
        print(emailinhalt)
        #regex durchsucht inhalt der Mails nach URLs
        regex = r'<?http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+>?'
        matches = re.findall(regex, emailinhalt)
        print(matches)
        #aktiviere pro Mail die Volltextmailingfunktion 
        for m in matches:
            m = m.strip('<>')
            getarticleandsendmail(m)
        print("m erledigt")
        sys.exit()
