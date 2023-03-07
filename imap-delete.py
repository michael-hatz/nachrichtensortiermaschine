#!/usr/bin/env python3
#-*- coding: utf-8 -*-

from imap_tools import MailBox
from imap_tools import OR 
from datetime import date

#Konfiguration IMAP-Eingangsserver 
imapHost = "w00600c1.kasserver.com"
imapUser = "rss@erdx.de"
imapPasscode = "asd33l"

#konfiguration ordner, hier zu scannende IMAP-Ordner angeben 
tagesschau = "Inbox/Tagesschau" #hier IMAP-Ordner auswhlen, in dem die Eingangsmails liegen
hackernews = "INBOX/HackerNews"
heise = "INBOX/Heise"
swr = "INBOX/SWR"
rde = "INBOX/Reddit/_r_de"
rgeschichte = "INBOX/Reddit/_r_geschichte"
taz = "INBOX/taz"
guardian = "INBOX/Guardian"

#Filterliste, einfach alle Begriffe wie vorgegeben einfuegen
#achtung: Ist aktuell casesensitive
Filter = ["heise-Angebot" , "Brexit" , "Rishi Sunak" , "palestinian", "turkey" , "turkish" , "syrian" , "refugees" , "Europa-League" , "Europa League" , "Assad" , "Türkei" , "Migrant" , "Flüchtling" , "Champions League" , "Krypto" , "Kryptowährung" , "Trump" , "Fußball" , "Tesla" , "Tesla" , "FIFA", "DFB" , "Achtelfinale" , "Viertelfinale" , "soccer" , "Halbfinale" , "UEFA" , "Vorwahlen" , "AfD" , "Facebook" , "Palmer" , "Merz" , "Wagenknecht" , "Israel" , "israeli", "Palästinenser" , "Gaza" , "gaza" , "türkei" , "Ungarn" , "katar" , "quatar" , "Katar" , "qatar", "dubai" , "Dubai" , "Fussball" , "fussball" , "Weltmeisterschaft" , "Leichtathletik" , "Wintersport" , "Republikaner" , "Gas" , "gas" , "Twitter" , "TikTok" , "AirBnB" , "Zuckerberg" , "cryptocoin" , "AWS" , "Apple" , "apple" , "iphone" , "iPhone" , "Elektroauto" , "eAuto" , "eFuel" "VW" , "BMW" , "Volkswagen" , "Ford" , "Mercedes" , "Putin" , "Jetbrains" , "Instagram" , "airbnb" , "saudi" , "Saudi" , "freebsd" , "bitcoin" , "Bitcoin" , "etherium" , "Etherium" , "nft" , "NFT" , "Joomla" , "Cisco" , "TechStage" , "Techstage" , "cryptocurrency" , "MacOS" , "applewatch" , "ipad" , "iPad" , "1&1" , "blockchain" , "heise+" , "Heise-Angebot" , "heiseshow" , "TechStage" , "Liveblog" , "Energie" , "Inflation", "Polizei" , "Russland" , "Moskau" , "Ukraine" , "Brasilien" , "Corona" , "covid" , "Covid", "droht" , "Krypto", "AKW" , "Atomkraft" , "Intel" , "Lindner", "Syrien" , "midterms" , "Midterms" , "Biden" , "US-Gericht" , "Karstadt" , "Bolsonaro" , "Union" , "Bundesliga", "Klima" , "Erdogan" , "Schalke" , "Hurrikan" , "Wirbelsturm" , "Tornado" , "Ukraine" , "Russischer" , "Karneval" , "Fasnacht" , "Fasnet" , "Ahrtal" , "Honda" , "iCloud" , "GOP", "Desantis" , "Ted Cruz" , "Florida" , "Texas" , "co2" , "CO2" , "Nikon" , "Pentax" , "Canon" , "Zwischenwahlen" , "Georgia" , "Seenotrettung" , "US-Midterms" , "Repräsentantenhaus" , "Nordkorea" , "Kim Yong-Un" , "Iran" , "Bürgergeld", "Nationalelf" , "Nationalmannschaft" , "Strompreisbremse" , "Livestream"]


q3 = ""
q4 = ""
betreff = ""

#definiere für doppelungen
Doppelungen = []
heute = date.today()

def mailchecker(Eingangsordner):
    with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    
        for nachricht in mailbox.fetch(OR(subject=Filter), charset='utf-8', bulk=True, mark_seen=False):
            betreff = nachricht.subject
            if(any(element in betreff for element in Filter)):
                print("Gefiltert:")
                print(nachricht.uid)
                print(nachricht.subject)
                mailbox.move(nachricht.uid, 'Papierkorb')
            
def mailentdoppelung(Eingangsordner):
    
    with MailBox(imapHost).login(imapUser, imapPasscode, Eingangsordner) as mailbox:
    
        for nachricht in mailbox.fetch(OR(date=[heute]), charset='utf-8', bulk=True, mark_seen=False):
            if nachricht.subject in Doppelungen:
                print("Entdoppelt: ")
                print(nachricht.subject)
                mailbox.move(nachricht.uid, 'Papierkorb')
            else:
                Doppelungen.append(nachricht.subject)
        #del Doppelungen       
mailchecker(tagesschau)
mailchecker(hackernews)
mailchecker(swr)
mailchecker(rde)
mailchecker(heise)
mailchecker(taz)
mailchecker(guardian)
mailentdoppelung(swr)
mailentdoppelung(hackernews)
mailentdoppelung(rgeschichte)
mailentdoppelung(taz)
#mailentdoppelung(rde)
mailentdoppelung("INBOX/Frankreich")
mailchecker("INBOX/Frankreich")

print('fertig')
#stand aktuell
        # geht, wenn der mailbox move auskommentiert ist
        # sonst verschiebt der alle. irgendwas mit falscher mailbox move?
