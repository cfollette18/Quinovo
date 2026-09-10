"""Hermes dashboard backend for Quinovo. Proxies the local kernel HTTP surface."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

DEFAULT_URL = "http://127.0.0.1:8791"


def _base() -> str:
    return os.environ.get("QUINOVO_URL", DEFAULT_URL).rstrip("/")


def _get(path: str) -> dict:
    url = _base() + path
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise HTTPException(
            503,
            f"Quinovo is not reachable at {_base()}. Start it with: quinovo serve",
        ) from exc


@router.get("/health")
def health() -> dict:
    try:
        body = _get("/healthz")
        return {"ok": True, "url": _base(), "ontology": body.get("ontology")}
    except HTTPException:
        return {"ok": False, "url": _base()}


@router.get("/graph")
def graph() -> JSONResponse:
    return JSONResponse(_get("/graph.json"))


@router.get("/embed")
def embed() -> dict:
    return {"url": _base() + "/"}
