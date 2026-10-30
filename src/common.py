# -*- coding: utf-8 -*-
"""Paths, configuration, SMTP and logging shared by the scripts and the web app."""

import configparser
import logging
import os
import shutil
import smtplib
import sqlite3
import ssl
import sys
from email.utils import formatdate, make_msgid
from logging.handlers import RotatingFileHandler

DATA_DIR = os.environ.get("NSM_DATA_DIR", "/app/data")


def data_path(name):
    return os.path.join(DATA_DIR, name)


CONFIG_PATH = data_path("config.cfg")
FEEDS_PATH = data_path("feeds.cfg")
FILTER_PATH = data_path("filter.txt")
KILLFILE_PATH = data_path("killfile.txt")
DB_PATH = data_path("nsm.db")
LOG_DIR = data_path("logs")

SMTP_TIMEOUT = 60  # seconds
SCRIPT_USER = "nsm"  # the scripts run as this user, the web app as root (see dockerfile)


def connect_db():
    """Open the SQLite database (read-later queue, mailed articles, feed status)."""
    db = sqlite3.connect(DB_PATH, timeout=30)
    # SQLite creates the file with mode 644 regardless of the umask. If the web app (root)
    # creates it, the scripts couldn't write it, so hand it to the script user.
    if os.geteuid() == 0:
        try:
            shutil.chown(DB_PATH, SCRIPT_USER, SCRIPT_USER)
        except (LookupError, OSError):
            pass  # no such user outside the container
    return db


def load_config(path=CONFIG_PATH):
    """config.cfg as ConfigParser (with interpolation: "%" is written as "%%")."""
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    return config


def load_feeds(path=None):
    """feeds.cfg as ConfigParser, without interpolation: feed URLs often contain "%"
    (e.g. "%20"), and the web interface writes them unescaped."""
    feeds = configparser.ConfigParser(interpolation=None)
    feeds.read(path or FEEDS_PATH, encoding="utf-8")
    return feeds


def smtp_connection(host, port, user, password, timeout=SMTP_TIMEOUT):
    """Logged-in SMTP connection with STARTTLS, for use with "with"."""
    server = smtplib.SMTP(host, int(port), timeout=timeout)
    try:
        server.starttls(context=ssl.create_default_context())
        server.login(user, password)
    except BaseException:
        server.close()
        raise
    return server


def send_mail(smtp, message):
    """Send message via the SMTP section of config.cfg (e.g. config['SMTP']). From/To are
    taken from the section unless the message already has them."""
    if "From" not in message:
        message["From"] = smtp["sender_email"]
    if "To" not in message:
        message["To"] = smtp["receiver_email"]
    if "Date" not in message:
        message["Date"] = formatdate(localtime=True)
    if "Message-ID" not in message:
        message["Message-ID"] = make_msgid()
    with smtp_connection(smtp["smtp_server"], smtp["port"], smtp["sender_email"], smtp["password"]) as server:
        server.sendmail(smtp["sender_email"], smtp["receiver_email"], message.as_string())


# ---------- Logging ----------

LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3


class _LogWriter:
    """File-like object that writes to the original stream and logs every complete line."""

    def __init__(self, logger, level, stream):
        self.logger, self.level, self.stream = logger, level, stream
        self.buffer = ""

    def write(self, text):
        if self.stream:
            self.stream.write(text)
        self.buffer += text
        *lines, self.buffer = self.buffer.split("\n")
        for line in lines:
            if line.strip():
                self.logger.log(self.level, line)
        return len(text)

    def flush(self):
        if self.stream:
            self.stream.flush()

    def isatty(self):
        return False


def setup_logging(name):
    """Write everything the script prints (and uncaught tracebacks) with a timestamp to
    LOG_DIR/<name>.log as well, so the output of cronjobs isn't lost. The web interface
    shows these files."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(LOG_DIR, f"{name}.log"), maxBytes=LOG_MAX_BYTES,
                                      backupCount=LOG_BACKUPS, encoding="utf-8")
    except OSError as e:
        print(f"Logging to {LOG_DIR} not possible: {e}", file=sys.stderr)
        return
    handler.setFormatter(logging.Formatter("%(asctime)s [%(process)d] %(levelname)s %(message)s",
                                           "%Y-%m-%d %H:%M:%S"))
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    sys.stdout = _LogWriter(logger, logging.INFO, sys.__stdout__)
    sys.stderr = _LogWriter(logger, logging.ERROR, sys.__stderr__)
