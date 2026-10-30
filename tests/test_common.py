import logging
import sys
from email.mime.text import MIMEText

import common


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.args = (host, port, timeout)

    def starttls(self, context):
        pass

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, sender, receiver, message):
        FakeSMTP.sent.append((self.args, sender, receiver, message))

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def test_send_mail_uses_the_section_and_a_timeout(monkeypatch):
    monkeypatch.setattr(common.smtplib, "SMTP", FakeSMTP)
    smtp = {"smtp_server": "smtp.example", "port": "587", "sender_email": "a@example.com",
            "receiver_email": "b@example.com", "password": "pw"}
    message = MIMEText("Hallo")
    message["Subject"] = "Test"
    common.send_mail(smtp, message)
    args, sender, receiver, raw = FakeSMTP.sent[-1]
    assert args == ("smtp.example", 587, common.SMTP_TIMEOUT)
    assert (sender, receiver) == ("a@example.com", "b@example.com")
    assert "From: a@example.com" in raw and "Date: " in raw and "Message-ID: " in raw


def test_setup_logging_writes_prints_to_the_log(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    try:
        common.setup_logging("testlog")
        print("Zeile eins")
        print("Teil", end="")
        print(" zwei")
        print("Fehler", file=sys.stderr)
    finally:
        for handler in logging.getLogger("testlog").handlers:
            handler.close()
    text = (tmp_path / "testlog.log").read_text(encoding="utf-8")
    assert "INFO Zeile eins" in text
    assert "INFO Teil zwei" in text
    assert "ERROR Fehler" in text


def test_load_feeds_keeps_percent_in_urls(tmp_path):
    path = tmp_path / "feeds.cfg"
    path.write_text("[Suche]\nurl = https://x.example/rss?q=a%20b\n", encoding="utf-8")
    assert dict(common.load_feeds(str(path))["Suche"]) == {"url": "https://x.example/rss?q=a%20b"}
