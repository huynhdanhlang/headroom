"""Bounded local commands over the canonical memory handler, not a new store."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from headroom.memory.models import MemoryConflictError
from headroom.memory.storage_router import ProjectResolver, RequestContext
from headroom.proxy.identity import resolve_memory_identity
from headroom.proxy.loopback_guard import require_loopback_or_container_gateway, require_same_origin

if TYPE_CHECKING:
    from headroom.proxy.server import HeadroomProxy

_FIELDS = {
    "memory_search": {"query", "top_k", "include_related", "entities"},
    "memory_list": {"limit"},
    "memory_save": {"content", "importance", "facts", "entities"},
    "memory_update": {"memory_id", "new_content", "reason", "expected_content_hash"},
    "memory_delete": {"memory_id", "reason", "expected_content_hash"},
    "memory_feedback": {"text"},
}
_REQUIRED = {
    "memory_search": {"query"}, "memory_list": set(), "memory_save": {"content"},
    "memory_update": {"memory_id", "new_content", "reason", "expected_content_hash"},
    "memory_delete": {"memory_id", "reason", "expected_content_hash"}, "memory_feedback": {"text"},
}


def validate_command(payload: Any) -> tuple[str, dict]:
    """Reject identity selectors and all overflow before backend initialization."""
    if not isinstance(payload, dict) or set(payload) != {"tool", "arguments"}:
        raise ValueError("Invalid command")
    tool, args = payload["tool"], payload["arguments"]
    if not isinstance(tool, str) or tool not in _FIELDS or not isinstance(args, dict):
        raise ValueError("Invalid command")
    if set(args) - _FIELDS[tool] or not _REQUIRED[tool] <= set(args):
        raise ValueError("Invalid command arguments")
    for key, value in args.items():
        if key in {"top_k", "limit"}:
            valid = type(value) is int and 1 <= value <= 100
        elif key == "importance":
            valid = type(value) in (int, float) and 0 <= value <= 1
        elif key == "include_related":
            valid = type(value) is bool
        elif key in {"facts", "entities"}:
            valid = (isinstance(value, list) and len(value) <= 32
                     and all(isinstance(v, str) and 0 < len(v) <= 16384 for v in value))
        else:
            valid = isinstance(value, str) and 0 < len(value) <= 16384
        if not valid:
            raise ValueError("Invalid command arguments")
    return tool, dict(args)


def register_memory_commands(app: FastAPI, proxy: HeadroomProxy) -> None:
    @app.post("/v1/memory/tools", dependencies=[
        Depends(require_loopback_or_container_gateway), Depends(require_same_origin),
    ])
    async def memory_command(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Memory command body too large")
        try:
            tool, args = validate_command(json.loads(body))
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid memory command") from None
        user_id = resolve_memory_identity(request)
        context = RequestContext(headers=dict(request.headers), system_prompt="", base_user_id=user_id)
        if ProjectResolver().resolve(context) is None:
            raise HTTPException(400, "Trusted project scope required")
        if tool in {"memory_save", "memory_feedback"}:
            evidence = request.headers.get("x-headroom-evidence-id", "")
            if not evidence or len(evidence) > 512:
                raise HTTPException(400, "Authored event identity required")
            args["_evidence_key"] = evidence
        if tool == "memory_feedback" and request.headers.get("x-headroom-source") != "opencode-prompt":
            raise HTTPException(400, "Authored prompt source required")
        handler = proxy.memory_handler
        if handler is None or not handler.config.enabled:
            raise HTTPException(503, "Memory unavailable")
        try:
            result = await handler.execute_scoped_command(tool, args, user_id, context)
            return JSONResponse(result)
        except MemoryConflictError:
            raise HTTPException(409, "Memory owner/version conflict") from None
        except NotImplementedError:
            raise HTTPException(503, "Guarded memory operation unsupported") from None
        except Exception:
            # No private path/token/error detail is returned to the model.
            # CancelledError is BaseException and intentionally propagates.
            raise HTTPException(503, "Memory unavailable; durable success not confirmed") from None
