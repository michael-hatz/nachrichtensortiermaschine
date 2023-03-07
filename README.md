# Was ist die Nachrichtensortiermaschine?
Sie ist ein Set von 7 Python-Skripten in Kombination mit [RSS2Email](https://github.com/rss2email/rss2email), welches es ermöglicht, Nachrichten, Blogs, Newsletter und Informationen einfach, werbefrei und unaufgeregt zu lesen und zu filtern. Wenn alles eingerichtet ist, bekommt man alle Nachrichten als Volltext im eigenen E-Mail-Postfach. Themen, die einen nicht interessieren, werden gefiltert und alles, was man später in Ruhe auf dem Sofa lesen will, landet auf dem eBookreader.

# Warum E-Mail?

* E-Mail ist eine robuste Standardtechnik, die bleiben wird. Im Zweifelsfall können wir irgendwann im Altersheim E-Mails auf unseren Gehirnimplantaten empfangen
* Man hat eine schier unendliche Auswahl an möglichen Benutzeroberflächen und Geräten zur Verfügung. Bei einem RSS-Dienst gibt es meistens nur eine Weboberfläche und eine App, aber bei E-Mail ist man deutlich freier.
* E-Mail funktioniert überall. Ob Windows, Linux, MacOS, Android, iOS, Tablet, Webbrowser, Auto, Kühlschrank, C64 oder Sprachassistent
* E-Mail funktioniert auch offline nachdem man die Mails einmal heruntergeladen hat
* E-Mail besitzt eine integrierte "Teilen"-Funktion über die man einen Großteil der Menschen weltweit erreichen kann
* Selbstgehostetes E-Mail gehört dem User - kein Anbieter kann den Account sperren und alles ist in eigenen Händen
* E-Mail-Programme sind darauf ausgelegt, dass sie einem schnell einen Überblick über eine große Anzahl von Mails geben - perfekt, um einen Nachrichtenüberblick zu bekommen
* Eine E-Mail kann beliebige Inhalte enthalten - ist der Artikel hinter einer Paywall und du willst ihn trotzdem später in Ruhe lesen? Schick dir einfach selbst eine Mail mit dem Text. Ist es ein Zeitschriftenartikel? Mach ein Foto und schick es dir! Ist es ein YouTube-Video? Pack es in die Mail, schau es später! 
* E-Mail-Programme ermöglichen die Volltextsuche durch alle Inhalte der Mails. Da Mails nicht besonders groß sind, muss man sie auch nicht löschen und daher kann man sich so ein umfassendes Archiv aufbauen, in dem man alles wiederfindet.
* Es gibt eine Vielzahl an E-Mail-Programmen für verschiedene Zwecke und Geschmäcker. Du kannst schlecht sehen? Dann lass dir deine Mails vorlesen! Du willst alles im Terminal lesen? Dann mach es! Programm X ist doof? Dann nimm Programm Y!

# Komponenten
Die Nachrichtensortiermaschine besteht aktuell aus 7 Komponenten.

## pocket-ersatz.py
Der Ersatz für Pocket, Instapaper & Co: Sende eine Mail mit einem Link an eine E-Mail-Adresse und erhalte eine E-Mail mit dem Volltext des Links zurück. Auf Wunsch auch mit AI-gesteuerter Zusammenfassung und Verschlagwortung

## imap-delete.py
Der Spamfilter für Nachrichten: Keine Lust auf Nachrichten über Donald Trump? Filtere einfach alle Schlagzeilen, die "Trump" enthalten. Kein Interesse an Fußball? Weg damit! Kein Apple-Fan? Lösche einfach alle Nachrichten über das neue iPhone.

## IMAP2txt.py / IMAP2epub.py
Erhalte ein ePub bzw. eine Textdatei per Mail mit allen deinen für's Später-Lesen gespeicherten Artikeln. Auf diese Weise kann man z.B. auch automatisch den Amazon Kindle befüllen.

## tolino.py
Lade automatisch ein ePub der für's Später-Lesen gespeicherten Artikeln in die Tolino Cloud.

## elefantenbrieftraeger.py
Sende eine Mail an eine Mailadresse und der Inhalt dieser Mail wird auf Mastodon gepostet.

## mastodon-ordner.py
Verschiebe eine Mail in einen Ordner und das Skript erstellt daraus einen Toot und postet ihn.

## Bookmarklet
Ein Bookmarklet für den Browser, welches die aktuelle Seite als Link teilt und bereits eine voreingestellte Mailadresse enthält.

# Installation
## Eigenes Postfach
* Die Nachrichtensortiermaschine ist darauf ausgelegt, dass sie ein eigenes Postfach zur Verfügung hat. Natürlich kann man sie auch in seinem normalen Mailpostfach laufen lassen, aber ich übernehme keine Garantie für nichts.
* Ich arbeite mit diversen Unterordnern. So landen alle Mails der Tagesschau in einem Unterordner "Tagesschau". Das kann man am Besten direkt in RSS2Email konfigurieren - einfach in der Konfiguration ein "imap-mailbox = INBOX/Tagesschau" einfügen und schon legt RSS2Email alle Inhaltes des entsprechenden RSS-Feeds sauber in diesem Ordner ab.
* Das würde auch über eine Mailsortierregel je nach Absender gehen, aber in meinem Postfach greifen die Filterregeln für eingehende Mails nicht, wenn ein Tools Mails direkt per IMAP in die Ordner legt
* Ich verwende für das Später-Lesen-Skript ein eigenes Postfach. Es geht sicherlich auch mit einem und diversen Filtern, aber da mein Webhost mir mehrere hundert Postfächer anbietet, bin ich den einfacheren Weg gegangen
* Dies gilt auch für die Mastodon-Skripte.

## RSS2Email
Als Quelle für die meisten Mails dienen mir RSS-Feeds, die mir per RSS2Email als Mail zugesendet werden. Informationen zur Installation, Einrichtung etc. gibt es direkt drüben.

Mit https://www.blogtrottr.com gibt es auch einen (einfacher zu bedienenden, aber werbefinanzierten) Onlinedienst.

## Skripte
Die Skripte sind bewusst als Einzelskripte gehalten, damit sie übersichtlich bleiben und inhaltlich sowie zeitlich individuell gesteuert werden können. Wer keinen Mastodon-Account hat, der darf etwa einfach die entsprechenden Skripte ignorieren und wer keinen eReader besitzt, der benötigt die Skripte dazu nicht.

Die Skripte enthalten alle eine ausführliche Installationsanweisung. Bitte aufmerksam den Anfang des Skriptes lesen. 

### Hardware
Bei mir laufen die Skripte auf einem Raspberry Pi 4, welcher für diesen Einsatzzweck völlig überdimensioniert ist. Sie sind auch auf Windows 11 getestet, ich sehe aber wenig, was gegen andere Betriebssysteme sprechen sollte. Wichtig ist nur, dass man ein System hat, welches:

* idealerweise 24/7 läuft
* Internetzugang hat
* Python3 installiert hat
* die Möglichkeit bietet, zeitgesteuert Python-Skripte zu starten

Das sind im Endeffekt alle modernen Betriebssysteme und theoretisch sollte es sogar auf einem Android-Handy gehen. Bitte achtet beim 24/7-Betrieb der Geräte etwas auf den Stromverbrauch, sonst wird es teuer und die Erde verglüht.

### Crontab
Das Timing der Skriptausführung ist individuell je nach Geschmack und konsumierter Medien. Bei mir sieht der Crontab so aus:


RSS2Email läuft jede Stunde um Viertel vor und sendet dann die neuen Einträge der RSS-Feeds als Mails. 5 Minuten später startet imap-delete.py und schiebt die Mails mit den unerwünschten Themen in den Papierkorb. Einmal am Tag läuft das Skript, welches mit ein txt der ungelesenen Artikel mailt und ebenfalls einmal am Tag wird mein Tolino mit der jeweils aktuellen Leseliste befüllt. Zeitlich ist das so getimt, dass ich auf dem Heimweg im Bus die Nachrichten sichten kann, alles interessante in den Später-Lesen-Ordner verschiebe und dann gemütlich auf dem Sofa auf dem Tolino lesen kann. Das hat sich als höchst großartig erwiesen.

Wenn man die Skripte auf einem Raspberry Pi laufen lässt, bitte alle Anleitungen im Internet ignorieren, die einen anweisen den Cronjob mit "sudo crontab -e" einzurichten. Auf die Weise würde das Skript als root laufen, was aber nicht klappen wird. "crontab -e" lässt das Skript auf dem aktuellen User laufen, was korrekt ist.

Zum Timing und Planen der Cronjobs empfehle ich https://www.crontab.guru

# Disclaimer
Ich habe eigentlich keinerlei Ahnung von Python und vom Programmieren. Use at your own risk. Wenn jemand Verbesserungsvorschläge oder generelle Hinweise zum Programmierstil hat, immer her damit!

# Tipps & Tricks
* Morss.it ist ein hilfreiches Tool, um beschnittene RSS-Feeds zu vervollständigen
* Ich bin ein großer Fan davon in Outlook einen Suchordner anzulegen, der einem alle ungelesenen Mails anzeigt. Auf diese Weise kann man entweder gezielt bestimmte Ordner anzeigen oder alle ungelesenen Mails aus allen Ordnern durchforsten
* Die Kombination aus Outlook "QuickSteps" und Sondertasten auf der Tastatur hat sich auch als fruchtbar erwiesen - ich kann so z.B. eine Mail direkt per Tastendruck in den "Später Lesen"-Ordner verschieben oder eine Mail von dort ins Archiv packen oder alle Mails in einem Ordner direkt als gelesen markieren.
* Auf Android läuft hier als Mailapp K9-Mail, weil diese zum einen werbefrei und quelloffen ist, aber andererseits auch deutlich besser mit Unterordner zurecht kommt als die schrottigen vorinstallierten Mailapps
* Twitter hat keine RSS-Feeds, Nitter.it als alternatives Frontend hingegen schon
* Man sollte nicht nur auf RSS2Email setzen - gerade boomt das Genre der Newsletter und jede Menge kluger Köpfe schreiben jede Menge höchst interessante Newsletter. Diverse Seiten bieten regelmäßige, kurierte Zusammenfassungen ihrer Inhalte per Mail an. Und auch Seiten ohne RSS-Feeds lassen sich auf Änderungen überwachen.
* Logischerweise kann man sich beliebige (Text)inhalte per Mail zum späterlesen senden. Man kann einen Podcast oder ein Video durch Whisper jagen und ihn dann in Ruhe nachlesen. Man kann mit dem Handy ein Foto eines Zeitschriftenartikels oder einer Informationstafel senden. Grundsätzlich kann E-Mail auch eingebettetes Audio und Video, das ist aber stark vom jeweiligen E-Mail-Client abhängig und funktioniert natürlich nicht auf einem eBook-Reader
* Ich genieße die Möglichkeit zum Lesen auf dem eBook-Reader sehr. Es gibt wohl keine entspanntere Möglichkeit, längere Internetartikel zu lesen. Ich lege mich gemütlich auf's Sofa, habe direkt den Fokus auf den Text, keine nervige Werbung am Rand, keine bunten Grafiken mit weiterführenden, total irrelevanten weiteren Links und nichts weiteres, was einen ablenken könnte. Wer noch keinen eBook-Reader hat, bekommt von mir eine absolute Kaufempfehlung.
* Die ungelesenen Artikel können gesammelt als Textdatei exportiert werden - diesen Input kann man z.B. auch in eine Text2Speech-Engine packen, wenn man schlecht sieht oder beim Sport oder Autofahren einen individuellen Podcast wünscht.

