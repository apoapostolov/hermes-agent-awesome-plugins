"""Trash-button backend tests.

The provider row's trash button deletes KEY #1 while the provider still holds
more than one key. That only works if the removed VALUE reaches the backend:
library.env and the Hermes .env feed every pool on each poll, so a pool shrink
on its own is undone by the next read. These tests drive the real `/config`
handler and assert the stored state afterwards, including a control run that
omits `remove_keys` and shows the key coming back.

Run: python tests_trash_keys.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tests_logout import _load_api


def _seed(tmp_path: Path, apply_env: bool):
    pa = _load_api(tmp_path)
    pa.HERMES_HOME = tmp_path
    # TOMBSTONE_PATH is computed at import time from PLUGIN_ROOT, so pointing
    # PLUGIN_ROOT at tmp is not enough: without this the run writes fingerprints
    # into the real plugin tree and the control case below is pre-poisoned.
    pa.TOMBSTONE_PATH = tmp_path / "removed.json"
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")
    pa.CONFIG_PATH.write_text(
        json.dumps(
            {
                "providers": {
                    "opencode": {
                        "enabled": True,
                        "pool": ["k1", "k2", "k3"],
                        "pool_index": 2,
                    }
                },
                "order": ["opencode"],
                "apply_hermes_env": apply_env,
            }
        ),
        encoding="utf-8",
    )
    pa.LIBRARY_PATH.write_text(
        "OPENCODE_GO_API_KEY=k1\nOPENCODE_GO_API_KEY_2=k2\nOPENCODE_GO_API_KEY_3=k3\n",
        encoding="utf-8",
    )
    pa.HERMES_ENV.write_text(
        "OPENCODE_GO_API_KEY=k1\nOPENCODE_GO_API_KEY_2=k2\nOPENCODE_GO_API_KEY_3=k3\n",
        encoding="utf-8",
    )
    return pa


def _delete_first_key(pa, with_remove_keys: bool):
    kwargs = dict(
        providers={"opencode": pa.ProviderConfig(pool=["k2", "k3"], pool_index=1)},
        order=["opencode"],
    )
    if with_remove_keys:
        kwargs["remove_keys"] = {"opencode": ["k1"]}
    pa.update_config(pa.ConfigUpdate(**kwargs))


def test_first_key_delete_keeps_provider_and_purges_key(tmp_path: Path) -> None:
    pa = _seed(tmp_path, apply_env=True)
    _delete_first_key(pa, with_remove_keys=True)

    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    opencode = saved["providers"]["opencode"]
    assert opencode["pool"] == ["k2", "k3"], opencode["pool"]
    assert opencode["pool_index"] == 1
    assert opencode.get("enabled") is True, "a partial save must not disable the row"
    assert "opencode" in saved["order"]

    library = pa._parse_env_map(pa.LIBRARY_PATH)
    assert "k1" not in library.values(), f"deleted key still in library: {library}"
    assert sorted(library.values()) == ["k2", "k3"]

    tombs = pa._load_tombstones()
    assert pa._fingerprint("k1") in tombs, "deleted key was not tombstoned"

    # apply_hermes_env: the pool is re-applied, so the deleted key also leaves
    # the runtime carriers instead of sitting in PRIMARY.
    env = pa._parse_env_map(pa.HERMES_ENV)
    assert env.get("OPENCODE_GO_API_KEY") == "k2", env.get("OPENCODE_GO_API_KEY")
    assert env.get("OPENCODE_GO_API_KEY_2") == "k3"
    assert "OPENCODE_GO_API_KEY_3" not in env, "stale numbered carrier survived"
    assert "k1" not in env.values()

    # The next poll is where a key used to come back.
    cfg = pa.get_config()
    assert cfg["providers"]["opencode"]["pool"] == ["k2", "k3"], cfg["providers"]["opencode"]["pool"]


def test_control_without_remove_keys_resurrects_the_key(tmp_path: Path) -> None:
    """Control run: the same pool shrink without remove_keys must bring k1 back,
    or the check above proves nothing."""
    pa = _seed(tmp_path, apply_env=False)
    _delete_first_key(pa, with_remove_keys=False)

    cfg = pa.get_config()
    assert "k1" in cfg["providers"]["opencode"]["pool"], cfg["providers"]["opencode"]["pool"]


def test_last_key_still_deletes_the_provider(tmp_path: Path) -> None:
    pa = _seed(tmp_path, apply_env=False)
    pa.CONFIG_PATH.write_text(
        json.dumps(
            {
                "providers": {"opencode": {"enabled": True, "pool": ["k1"], "pool_index": 0}},
                "order": ["opencode"],
            }
        ),
        encoding="utf-8",
    )
    body = pa.ConfigUpdate(remove=["opencode"], order=[], remove_keys={"opencode": ["k1"]})
    pa.update_config(body)

    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "opencode" not in (saved.get("providers") or {})
    assert "opencode" not in (saved.get("order") or [])
    assert "k1" not in pa._parse_env_map(pa.LIBRARY_PATH).values()


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp())
    for name, fn in (
        ("purge", test_first_key_delete_keeps_provider_and_purges_key),
        ("control", test_control_without_remove_keys_resurrects_the_key),
        ("last-key", test_last_key_still_deletes_the_provider),
    ):
        d = root / name
        d.mkdir()
        fn(d)
    print("trash keys: first-key purge + resurrection control + last-key delete PASS")
