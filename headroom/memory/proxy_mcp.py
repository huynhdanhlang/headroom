"""Client-owned MCP tools over the running proxy's canonical project memory.

No database, embedder, or model is loaded here. The proxy owns durable memory;
the MCP host owns session scope and tool execution.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from headroom.proxy.memory_commands import validate_command

_TEXT = {"type": "string", "minLength": 1, "maxLength": 16384}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": 100}
_STRINGS = {"type": "array", "maxItems": 32, "items": _TEXT}
_DEFINITIONS = [
    ("memory_search", "Recall relevant project background. Current instructions and permissions take precedence.",
     ["query"], {"query": _TEXT, "top_k": _LIMIT, "entities": _STRINGS, "include_related": {"type": "boolean"}}),
    ("memory_list", "List current project memories with exact IDs/hashes for guarded correction or forget.",
     [], {"limit": _LIMIT}),
    ("memory_save", "Persist useful user-approved project knowledge. Report remembered only after durable success.",
     ["content"], {"content": _TEXT, "facts": _STRINGS, "entities": _STRINGS,
                   "importance": {"type": "number", "minimum": 0, "maximum": 1}}),
    ("memory_update", "Correct a specific memory after reading its current ID/hash. Never infer replacement from similarity.",
     ["memory_id", "new_content", "expected_content_hash", "reason"],
     {"memory_id": _TEXT, "new_content": _TEXT, "expected_content_hash": _TEXT, "reason": _TEXT}),
    ("memory_delete", "Only on explicit user forget: remove exact current ID/hash from recall. History remains; this is not a purge.",
     ["memory_id", "expected_content_hash", "reason"],
     {"memory_id": _TEXT, "expected_content_hash": _TEXT, "reason": _TEXT}),
]
_MAX_BODY = 65536
_MAX_RESPONSE = 262144
logger = logging.getLogger("headroom.memory.proxy_mcp")


def _endpoint(proxy_url: str) -> str:
    parsed = urlsplit(proxy_url)
    if (parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Memory MCP requires a local credential-free proxy root URL")
    return proxy_url.rstrip("/") + "/v1/memory/tools"


def _project(path: str) -> str:
    if not path or not Path(path).is_absolute():
        raise ValueError("Trusted project scope unavailable")
    project = Path(path).resolve()
    if project == Path("/"):
        raise ValueError("Trusted project scope unavailable")
    return str(project)


def _error(message: str) -> CallToolResult:
    return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])


def create_proxy_memory_server(proxy_url: str, project_root: str, client: httpx.AsyncClient) -> Server:
    endpoint, startup_project = _endpoint(proxy_url), _project(project_root)
    server = Server("headroom-memory")
    session_key = uuid4().hex

    @server.list_tools()
    async def list_tools():
        return [Tool(name=name, description=description,
                     inputSchema={"type": "object", "properties": properties,
                                  "required": required, "additionalProperties": False})
                for name, description, required, properties in _DEFINITIONS]

    async def current_project() -> str:
        context = server.request_context
        params = context.session.client_params
        if params is None or params.capabilities.roots is None:
            # Codex starts stdio MCP in its session cwd when no explicit cwd is
            # configured. The host launcher forwards that trusted startup cwd.
            return startup_project
        async with asyncio.timeout(1):
            roots = (await context.session.list_roots()).roots
        # Never choose an arbitrary workspace, nor fall back after root failure.
        if len(roots) != 1:
            raise ValueError("Trusted single-project scope unavailable")
        uri = urlsplit(str(roots[0].uri))
        if uri.scheme != "file" or uri.netloc not in {"", "localhost"} or uri.query or uri.fragment:
            raise ValueError("Trusted local project scope unavailable")
        return _project(unquote(uri.path))

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        try:
            if name not in {entry[0] for entry in _DEFINITIONS}:
                raise ValueError("Unknown memory tool")
            validate_command({"tool": name, "arguments": arguments})
            args = dict(arguments)
            if name == "memory_search":
                args.setdefault("top_k", 3)
            elif name == "memory_list":
                args.setdefault("limit", 20)
            body = json.dumps({"tool": name, "arguments": args}, ensure_ascii=False, allow_nan=False).encode()
            if len(body) > _MAX_BODY:
                raise ValueError("Memory arguments too large")
            project = await current_project()
            headers = {"content-type": "application/json", "x-headroom-cwd": quote(project, safe=""),
                       "x-headroom-memory-tools": "client", "x-headroom-client": "codex",
                       "x-headroom-evidence-id": f"codex-mcp:{session_key}:{server.request_context.request_id}"}
            # Bound the complete operation, not only each individual socket read.
            async with asyncio.timeout(4):
                async with client.stream("POST", endpoint, content=body, headers=headers) as response:
                    if response.status_code == 409:
                        return _error("Memory owner/version conflict; reload this project's current ID/hash before retrying.")
                    if response.status_code != 200:
                        return _error("Memory unavailable; durable success not confirmed.")
                    output = bytearray()
                    async for chunk in response.aiter_bytes():
                        output.extend(chunk)
                        if len(output) > _MAX_RESPONSE:
                            return _error("Memory result too large; retry with a smaller limit.")
            result = json.loads(output)
            if not isinstance(result, dict) or result.get("status") not in {
                "saved", "superseded", "forgotten", "updated", "found", "ok",
            }:
                return _error("Memory unavailable; durable success not confirmed.")
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))])
        except ValueError:
            return _error("Invalid memory arguments or trusted project scope unavailable; no confirmed write.")
        except (httpx.HTTPError, TimeoutError):
            logger.warning("Memory MCP request unavailable; durable success not confirmed")
            return _error("Memory unavailable; durable success not confirmed.")
        except Exception:
            logger.warning("Memory MCP operation failed; durable success not confirmed")
            return _error("Memory unavailable; durable success not confirmed.")
        # Cancellation propagates: never convert interrupted writes into success.

    return server


async def _run(proxy_url: str, project_root: str) -> None:
    async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
        server = create_proxy_memory_server(proxy_url, project_root, client)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-url", required=True)
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    asyncio.run(_run(args.proxy_url, args.project_root))


if __name__ == "__main__":
    main()
