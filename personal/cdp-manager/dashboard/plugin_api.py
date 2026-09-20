"""CDP Manager plugin backend — mounted at /api/plugins/cdp-manager/.

The renderer (desktop/plugin.js) calls these routes via ctx.rest so it can
launch / stop / recheck CDP ports through one Python process, instead of
each dialog open spawning its own Chrome.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

import cdp_core

log = logging.getLogger(__name__)
router = APIRouter()


class PortsBody(BaseModel):
    ports: list[int]


class PreferredBody(BaseModel):
    port: int | None = None


class PortBody(BaseModel):
    port: int


@router.get("/status")
def status():
    cfg = cdp_core.load_config()
    return {
        "ports": cfg["ports"],
        "preferredPort": cfg.get("preferredPort"),
        "chromePath": cfg["chromePath"],
        "userDataDir": cfg["userDataDir"],
        "results": cdp_core.probe_all(),
    }


@router.post("/probe")
def probe(body: PortsBody):
    return {"ok": True, "results": cdp_core.probe_all(body.ports)}


@router.post("/launch")
def launch(body: PortBody):
    return cdp_core.launch(body.port)


@router.post("/stop")
def stop(body: PortBody):
    return cdp_core.stop(body.port)


@router.post("/preferred")
def preferred(body: PreferredBody):
    return cdp_core.set_preferred(body.port)


@router.post("/ports")
def ports(body: PortsBody):
    return cdp_core.update_ports(body.ports)
