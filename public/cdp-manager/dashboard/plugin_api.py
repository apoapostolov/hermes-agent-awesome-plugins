"""CDP Manager plugin backend — mounted at /api/plugins/cdp-manager/.

The renderer (desktop/plugin.js) calls these routes via ctx.rest so it can
launch / stop / recheck CDP ports through one Python process, instead of
each dialog open spawning its own Chrome.

A supervisor thread (cdp_core.ensure_supervisor) runs for the lifetime of
the backend: it keeps health fresh, starts the managed port when down, and
force-reboots it after repeated launch failures.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

# Load the sibling cdp_core by path: this file is imported via
# spec_from_file_location under a synthetic module name, so plain
# `import cdp_core` would only work by sys.path luck.
import importlib.util as _ilu
import pathlib as _pl

_spec = _ilu.spec_from_file_location(
    "cdp_manager_core", str(_pl.Path(__file__).resolve().parent.parent / "cdp_core.py")
)
cdp_core = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(cdp_core)

log = logging.getLogger(__name__)
router = APIRouter()


class PortsBody(BaseModel):
    ports: list[int]


class PreferredBody(BaseModel):
    port: int | None = None


class PortBody(BaseModel):
    port: int
    mode: str | None = None  # 'headful' | 'headless'


class PollBody(BaseModel):
    seconds: int


class ModeBody(BaseModel):
    port: int
    mode: str  # 'headful' | 'headless'


# Supervisor: starts the managed port on backend boot ("on hermes launch")
# and keeps checking health on its own tick afterwards.
cdp_core.ensure_supervisor()


@router.get("/health")
def health():
    """Cheap cached snapshot for the statusbar chip. The supervisor thread
    already probes all ports every tick, so this is rarely a fresh probe."""
    return cdp_core.health()


@router.get("/status")
def status():
    cfg = cdp_core.load_config()
    modes = {str(p): cfg.get(f"mode_{p}") or "headful" for p in cfg["ports"]}
    return {
        "ports": cfg["ports"],
        "preferredPort": cfg.get("preferredPort"),
        "chromePath": cfg["chromePath"],
        "userDataDir": cfg["userDataDir"],
        "pollSeconds": int(cfg.get("pollSeconds") or 0),
        "modes": modes,
        "results": cdp_core.probe_all(),
    }


@router.post("/mode")
def mode(body: ModeBody):
    """Save the launch mode (headful/headless) for a port. Used by the next
    launch, including supervisor auto-starts."""
    m = "headless" if body.mode == "headless" else "headful"
    cdp_core.mutate_config(lambda c: c.update({f"mode_{int(body.port)}": m}))
    return {"ok": True, "port": int(body.port), "mode": m}


@router.post("/poll")
def poll(body: PollBody):
    seconds = max(0, min(3600, int(body.seconds)))
    cdp_core.mutate_config(lambda c: c.update(pollSeconds=seconds))
    return {"ok": True, "pollSeconds": seconds}


@router.post("/probe")
def probe(body: PortsBody):
    cdp_core.invalidate_health()
    return {"ok": True, "results": cdp_core.probe_all(body.ports)}


@router.post("/launch")
def launch(body: PortBody):
    out = cdp_core.launch(body.port, mode=body.mode)
    cdp_core.invalidate_health()
    return out


@router.post("/stop")
def stop(body: PortBody):
    out = cdp_core.stop(body.port)
    cdp_core.invalidate_health()
    return out


@router.post("/preferred")
def preferred(body: PreferredBody):
    """Set (or clear) the managed port. Wire name stays preferredPort so the
    `cdp` tool payloads do not break; the UI calls it managed."""
    return cdp_core.set_preferred(body.port)


@router.post("/ports")
def ports(body: PortsBody):
    return cdp_core.update_ports(body.ports)
