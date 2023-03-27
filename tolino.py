#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""
## IMAP2tolino.py
Lade automatisch ein ePub der für's Später-Lesen gespeicherten Artikeln in die Tolino Cloud.

Ein etwas wackeliges Skript - Tolino bietet keine verfügbare API für den Upload an und auch nicht wie Amazon eine simple Mailadresse zum befüllen der Reader. Von daher benutzen wir eine Webautomatisierung, um uns automatisiert durch das Tolino-Webinterface zu klicken und die Datei hochzuladen. 

Installation
* Installiert Python 3 und alle importierten Pakete
* Ich nutze hier Selenium in Kombination mit dem Chromedriver, daher wird Google Chrome bzw. Chromium benötigt
* Gebt oben die Daten für euer Postfach und den Ordner, in dem ihr eure auszulesenden Mails lagert
* Tragt unten im Selenium-Skript eure eigenen Logindaten für die Tolino Cloud ein
* Ich nutze "MeineBuchhandlung" und das Skript klickt auch entsprechend. Wenn ihr andere Anbieter nutzt, müsst ihr schauen, wie das geht. Ich empfehle hier dann mit Selenium IDE selbst im Browser den Clickstream zu erstellen (ist einfacher als es klingt, ihr klickt euch einfach nur durch den Loginprozess) und diesen dann als Python zu exportieren und hier einzufügen.
* Das Skript wird ein Browserfenster öffnen.
* Es ist von den Timings her darauf ausgelegt, dass es auf einem für das Surfen doch etwas schnarchigen Raspberry Pi 4 läuft. Ich habe die Timings daher ganz bewusst lange gesetzt - wenn ihr das Skript auf anderen Geräten laufen lassen wollt, dann könnt ihr diese senken. Da mein Raspi aber eh stetig läuft, aber nicht wirklich zum aktiven Arbeiten benutzt wird, darf sich mein Skript hier gerne etwas Zeit lassen.
* Am Ende muss eine Datei ausgewählt werden und das macht jetzt wirklich jedes Betriebssystem anders oder ich habe den Trick noch nicht gefunden. Auf jeden Fall läuft das Skript so nur unter Linux.
* Bei mir läuft das Skript einmal am Tag.
* Wenn man die Skripte auf einem Raspberry Pi laufen lässt, bitte alle Anleitungen im Internet ignorieren, die einen anweisen den Cronjob mit "sudo crontab -e" einzurichten. Auf die Weise würde das Skript als root laufen, was aber nicht klappen wird. "crontab -e" lässt das Skript auf dem aktuellen User laufen, was korrekt ist.
* Der Cronjob benötigt ein DISPLAY=0 !!!!
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from imap_tools import MailBox
import xml2epub
import os
from datetime import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pyautogui
 
#Konfiguration IMAP-Eingangsserver 
imapHost = "imap.example.com"
imapUser = "mail@example.com"
imapPasscode = "passwort"
Eingangsordner = "Inbox/artikel_unread" #hier IMAP-Ordner auswhlen, in dem die Eingangsmails liegen
  
#epub-Einstellungen
dateiname = "Leseliste.epub"
datum = datetime.today().strftime('%Y-%m-%d')
name = datum + " Leseliste"
book = xml2epub.Epub(name, creator='Michael Hatz', language='de', publisher='Nachrichtensortiermaschine')

###############################

def uploadtolino():
    print("starte selenium")
    driver = webdriver.Chrome()
    
    # Test name: doof
    # Step # | name | target | value
    # 1 | open | /library/index.html | 
    driver.get("https://webreader.mytolino.com/library/index.html")
    time.sleep(30)
    # 2 | setWindowSize | 1601x1227 | 
    driver.set_window_size(1601, 1227)
    print("geht")
    time.sleep(5)
    # 3 | click | css=.\_11zc1ea:nth-child(1) > .\_1ri68zh | 
    driver.find_element(By.CSS_SELECTOR, ".\\_11zc1ea:nth-child(1) > .\\_1ri68zh").click()
    time.sleep(5)
    # 4 | click | css=.\_11zc1ea:nth-child(6) .\_fcef1e | 
    driver.find_element(By.CSS_SELECTOR, ".\\_11zc1ea:nth-child(6) .\\_fcef1e").click()
    time.sleep(5)
    # 5 | click | css=.\_vb2dg0 .\_nbleso | 
    driver.find_element(By.CSS_SELECTOR, ".\\_vb2dg0 .\\_nbleso").click()
    time.sleep(5)
    # 6 | runScript | window.scrollTo(0,0) | 
    driver.execute_script("window.scrollTo(0,0)")
    time.sleep(5)
    # 7 | click | id=login-email | 
    driver.find_element(By.ID, "login-email").click()
    time.sleep(5)
    
    driver.find_element(By.ID, "login-email").send_keys("ich@habedielogindatenimskriptnochnichtangepasstundsolltediestun.de")
    time.sleep(5)
   
    driver.find_element(By.ID, "login-password").send_keys("passwort")
    time.sleep(5)
    # 10 |  click | css=.btn-primary | 
    driver.find_element(By.CSS_SELECTOR, ".btn-primary").click()
    time.sleep(5)
    # 11 | click | css=.\_8ag69r > .\_nbleso | 
    driver.find_element(By.CSS_SELECTOR, ".\\_8ag69r > .\\_nbleso").click()
    time.sleep(5)
    # 12 | click | css=.\_1ot1t5f:nth-child(1) > .\_1ri68zh > .\_abw475 | 
    driver.find_element(By.CSS_SELECTOR, ".\\_1ot1t5f:nth-child(1) > .\\_1ri68zh > .\\_abw475").click()
    time.sleep(5)
    # 13 | click | css=.\_y4tlgh | 
    driver.find_element(By.CSS_SELECTOR, ".\\_y4tlgh").click()
    time.sleep(5)
    # 14 | click | css=.\_z1ovxu:nth-child(3) .\_abw475 | 
    driver.find_element(By.CSS_SELECTOR, ".\\_z1ovxu:nth-child(3) .\\_abw475").click()
    time.sleep(5)

#hier den Pfad zum Skript angeben!
    
    pyautogui.write(r"C:\Leseliste.epub")
    #time.sleep(5)
    pyautogui.press("enter")
    print("done")
    time.sleep(120)
    driver.quit()
  
#Mailbody lesen und alles in einen riesigen String packen

with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    for nachricht in mailbox.fetch(bulk=True):
        #emailinhalt auch von html news und newslettern auslesen und uebergeben
        chapter0 = xml2epub.create_chapter_from_string(nachricht.html, title=nachricht.subject)
        book.add_chapter(chapter0)
path = os.getcwd()
book.create_epub(path, epub_name="Leseliste")

uploadtolino()