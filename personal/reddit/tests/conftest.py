"""Keep worker and shared coordination state inside each test sandbox."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reddit import coordination, maintenance, login


@pytest.fixture(autouse=True)
def isolated_workers(tmp_path, monkeypatch):
    login.PENDING["home"] = ""
    monkeypatch.setattr(coordination, "shared_root", lambda: tmp_path / "shared-budget")
    monkeypatch.setattr(coordination, "MIN_INTERVAL", 0)
    monkeypatch.setattr(maintenance, "start", lambda *a, **kw: None)
    yield
    login.PENDING["home"] = ""
