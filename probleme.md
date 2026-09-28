crontab /etc/cron.de/myjobs hat nicht gefeuert
cat -A /etc/cron.d/myjobs

apt-get update && apt-get install -y dos2unix
dos2unix /etc/cron.d/myjobs


ePub generierung wirft Probleme auf neueren Tolinos
gibt es eine Möglichkeit, die ePubs direkt in die Tolino Cloud zu schieben
füge Download für epub & txt im Interface ein
ändere das Interface zur Feedabonnierung von Text auf ein klickbares Interface
möglichkeit feeds per mail zu abonnieren
Wir schreiben gerade alle gescannten URLs in "urls.tsv". Ist das ok oder sollten wir lieber eine kleine Datenbank nehmen? 
Das killfile ist zu pedantisch beim Löschen. Wenn irgendwo noch eine URL etc. drin ist, löscht es nicht
ich schiebe gelesene Mails in INBOX/artikel_unread/_archive . Bitte richte einen cronjob ein, der die Artikel auf Basis ihres Headers wieder in den passenden Ordner schiebt