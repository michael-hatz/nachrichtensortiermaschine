#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""
Der Spamfilter für Nachrichten: Keine Lust auf Nachrichten über Donald Trump? Filtere einfach alle Schlagzeilen, die "Trump" enthalten. Kein Interesse an Fußball? Weg damit! Kein Apple-Fan? Lösche einfach alle Nachrichten über das neue iPhone.

Dieses Skript ist ... eigentlich unnötig. Man könnte seine Funktionalität auch mit den in jedem Postfach eingebauten Filterregeln umsetzen. RSS2Email hat aber im Standard eine nervige Eigenschaft: Natürlich kann man dort auch ein Sendmail definieren, aber wenn man von heimischen IP-Adressen Mails an Gmail & Co versendet, dann landet man häufig im Spam und man fummelt sich eine Filterregel zusammen, die je nach Betreff/Absender die Mails in Unterordner sortiert. Und wenn man die sinnvollere in RSS2Email IMAP-Funktion benutzt, um Mails direkt per IMAP in Unterordner zu schieben, dann greift (zumindestens bei meinem Mailanbieter) die Eingangsprüfung gerade nicht. 

Dieses Skript macht daher zwei Dinge: 

1) Es verschiebt alle Mails, deren Betreffzeile Begriffe aus der Filterliste enthält. Wenn Ihr wollt, könnt ihr auch durch eine einfache Anpassung einstellen, dass der gesamte Text gelöscht wird, das ist aber meiner Erfahrung nach etwas zu extrem. 
2) RSS2Email hat das Problem, dass Änderungen in RSS-Feeds ab und an als doppelte oder gar vier-, fünf- oder sechsfache Mail ankommen. Manche Anbieter sind leider mit ihren RSS-Feeds bei Änderungen nicht so exakt (Looking at you, SWR!). Dieses Skript schaut ganz stumpf, ob es in einem Ordner mehrere Mails mit dem gleichen Titel und Datum gibt und löscht eine. Auf die Weise hat man immer nur eine Meldung im Postfach

Installation
* Installiert Python 3 und alle importierten Pakete
* Ich liefere meine Filterliste mit, diese ist aber sehr individuell auf mich zugeschnitten, höchst politisch und es macht Sinn, dass ihr die kurz prüft und eure eigene erstellt. So bin ich seit Jahren Android-Nutzer und interessiere mich daher absolut nicht für Apple-Geräte, daher filtere ich alles entsprechende raus, da ich eh kein iPhone kaufen werde. Wenn Ihr aber die großen Apple-Jünger seid, dann wäre das natürlich schlecht für euch. Tragt einfach eure Begriffe oder Phrasen in die Liste ein und haltet euch an das vorgegebene Format.
* Das exakte Setup hängt von eurer individuellen Konfiguration ab: Je nachdem, wie ihr euer Postfach eingerichtet habt und in welchen Ordnern ihr filtern wollt.  Im Kern könnt ihr oben eure zu filternden Ordner definieren (der tagesschau = "INBOX/Tagesschau" sagt z.B. , dass es im Ordner INBOX einen Unterordner Tagesschau gibt. Ruft man dann unten mit mailchecker(tagesschau) die Filterfunktion auf, werden die entsprechenden Mails im Ordner gefiltert.
* Das Setup ist nicht perfekt, funktioniert aber. Ich habe hier alles absichtlich nach Ordnern aufgebaut und filtere nicht alle Ordner gleichzeitig, um möglichst flexibel zu bleiben.
* Wer will, kann sich mit 1-2 kleinen Änderungen auch mehrere Filterlisten definieren und z.B. alle Apple-Nachrichten von allen Seiten bis auf einer filtern
* Oben dann die Logindaten für euer Postfach angeben.
* Wenn Ihr Probleme mit doppelten Nachrichten habt, dann ruft für diesen RSS-Feed / Ordner die Funktion mailchecker() auf
* Bei mir läuft das Skript 5 Minuten nach der RSS2Email-Ausführung. Bis dann ist RSS2Email fertig, die Mails liegen in den Ordnern und können gefiltert werden.
* Wenn man die Skripte auf einem Raspberry Pi laufen lässt, bitte alle Anleitungen im Internet ignorieren, die einen anweisen den Cronjob mit "sudo crontab -e" einzurichten. Auf die Weise würde das Skript als root laufen, was aber nicht klappen wird. "crontab -e" lässt das Skript auf dem aktuellen User laufen, was korrekt ist.
"""

from imap_tools import MailBox
from imap_tools import OR 
from datetime import date

#Konfiguration IMAP-Eingangsserver 
imapHost = "example.com"
imapUser = "deinwunderbarespostfachindemdudeinemailsliest@example.com"
imapPasscode = "passwort"

#konfiguration ordner, hier zu scannende IMAP-Ordner angeben
#hier IMAP-Ordner auswhlen, in dem die Eingangsmails liegen
#das ist natürlich individuell auf meine Ordnerstruktur zugeschnitten, aber wer die Skripte zum Laufen bekommt, bekommt das auch angepasst
tagesschau = "Inbox/Tagesschau" 
hackernews = "INBOX/HackerNews"
heise = "INBOX/Heise"
swr = "INBOX/SWR"
rde = "INBOX/Reddit/_r_de"
rgeschichte = "INBOX/Reddit/_r_geschichte"
taz = "INBOX/taz"
guardian = "INBOX/Guardian"

#Filterliste, einfach alle Begriffe wie vorgegeben einfuegen
#Klaut euch gerne Teile meiner Filterliste, aber passt sie auf jeden Fall auf eure Bedürfnisse an
#Achtung: Ist aktuell casesensitive
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