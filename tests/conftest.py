"""The tests run inside the Docker image (see .github/workflows/ci.yml), where the
scripts live in /app and read their defaults from /app/data, just like in production."""
import importlib.util
import os
import sys

import pytest

APP_DIR = os.environ.get("NSM_APP_DIR", "/app")
sys.path.insert(0, APP_DIR)
# app.py would otherwise generate a password file in /app/data on import
os.environ.setdefault("NSM_WEB_PASSWORD", "test")


def load_script(name):
    """Import a script whose file name isn't a valid module name (e.g. pocket-mailer-epub.py)."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(APP_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def nsm():
    import nsm
    return nsm


@pytest.fixture(scope="session")
def app_module():
    import app
    return app


@pytest.fixture(scope="session")
def epub():
    return load_script("pocket-mailer-epub")
