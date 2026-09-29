crontab /etc/cron.de/myjobs hat nicht gefeuert
cat -A /etc/cron.d/myjobs

apt-get update && apt-get install -y dos2unix
dos2unix /etc/cron.d/myjobs


ePub generierung macht Probleme auf neueren Tolinos und v.a. das Inhaltsverzeichnis ist nicht sauber darstellbar. Wenn ich in Calibre das ePub reparieren lasse, dann geht es wieder
Gibt es eine Möglichkeit, die ePubs direkt per Buttonclick in die Tolino Cloud zu laden?
füge Downloadbutton für epub & txt im Interface ein direkt neben dem "Sende ePub" Button. Dieser soll das ePub generieren und direkt senden
Ändere das Interface zur Feedabonnierung vom aktuellen Textinterface auf ein klickbares Interface, in dem ich mit der Maus alles einstellen kann
Möglichkeit feeds per mail zu abonnieren
Wir schreiben gerade alle gescannten URLs in "urls.tsv". Ist das ok oder sollten wir lieber eine kleine Datenbank nehmen? 
Das killfile ist zu pedantisch beim Löschen. Wenn irgendwo noch eine URL etc. drin ist, löscht es nicht
ich schiebe gelesene Mails in INBOX/artikel_unread/_archive . Bitte richte einen cronjob ein, der die Artikel auf Basis ihres Headers wieder in den passenden Ordner schiebt


=======
Idee:

=======

Changelog: 
- cronjobs laufen auch weiter, wenn im Webinterface etwas editiert wurde
- Buttons im Webinterface zum Download von ePub & Txt
- Webinterface hat nun GUI zum Abonnieren von Feeds und zum Editieren der Konfiguration

