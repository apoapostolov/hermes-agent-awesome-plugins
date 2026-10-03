from __future__ import annotations

import sys
import types
from pathlib import Path

PERSONAL_API = Path(__file__).with_name("dashboard") / "plugin_api.py"


def test_source_never_loads_lifestyle() -> None:
    src = PERSONAL_API.read_text(encoding="utf-8")
    assert "Never read C:/git/lifestyle/.env." in src
    assert src.count("C:/git/lifestyle") == 1
    assert "for p in [HERMES_HOME / \".env\"]" not in src
    assert "_merge_env_file(LIBRARY_PATH)" in src
    assert "_merge_env_file(HERMES_ENV)" in src
    # control: a string we know is absent must report absent
    assert "THIS_PATH_DOES_NOT_EXIST_XYZ" not in src


def _stub_host_modules() -> None:
    fastapi = types.ModuleType("fastapi")

    class APIRouter:
        def get(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        post = get

    fastapi.APIRouter = APIRouter
    sys.modules["fastapi"] = fastapi

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, exclude_unset=False):
            return dict(self.__dict__)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


def test_library_then_hermes(tmp_path: Path) -> None:
    _stub_host_modules()
    sys.path.insert(0, str(PERSONAL_API.parent))
    import plugin_api as pa  # type: ignore

    lib = tmp_path / "library.env"
    hermes = tmp_path / ".env"
    lifestyle = tmp_path / "lifestyle.env"
    lib.write_text("TAVILY_API_KEY=from-library\nSHARED=lib-value\n", encoding="utf-8")
    hermes.write_text("SHARED=hermes-wins\nDEEPSEEK_API_KEY=from-hermes\n", encoding="utf-8")
    lifestyle.write_text("TAVILY_API_KEY=from-lifestyle\nSHARED=lifestyle\n", encoding="utf-8")

    pa.LIBRARY_PATH = lib
    pa.HERMES_ENV = hermes
    pa._env_cache.clear()
    pa._env_loaded = False
    pa._load_env_files()

    assert pa._env_cache["TAVILY_API_KEY"] == "from-library"
    assert pa._env_cache["SHARED"] == "hermes-wins"
    assert pa._env_cache["DEEPSEEK_API_KEY"] == "from-hermes"
    assert "from-lifestyle" not in pa._env_cache.values()


if __name__ == "__main__":
    test_source_never_loads_lifestyle()
    test_library_then_hermes(Path(__import__("tempfile").mkdtemp()))
    print("env store: source + load-order PASS")
