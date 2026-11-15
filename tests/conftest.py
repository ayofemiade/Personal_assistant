import os
import tempfile

# isolate every test run from the real database, and pin "today" (Thursday 12 Nov 2026)
os.environ["MOYO_DATA_DIR"] = tempfile.mkdtemp(prefix="moyo-test-")
os.environ["MOYO_TODAY"] = "2026-11-12"

import pytest  # noqa: E402

from moyo import cloud, db  # noqa: E402

cloud.api_key = lambda *a, **k: None  # tests must never call the real Gemini/Groq APIs
os.environ["MOYO_NO_BACKGROUND"] = "1"

from moyo import google_api  # noqa: E402

google_api.connected = lambda: False  # …or touch the real Google account (tests opt in with monkeypatch)

from moyo import social  # noqa: E402

social.ig_connected = lambda: False
social.tt_connected = lambda: False


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init(c)
    yield c
    c.close()
