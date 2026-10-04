"""Launch the pinned memory MCP image in the Codex session's host project scope.

Uses host stdlib only. No project/secret mounts or second memory store. Omit
Codex's MCP `cwd` override so every new project session supplies its own cwd.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def docker_command(image: str, proxy_url: str, project: Path) -> list[str]:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("An installed immutable Docker image ID is required")
    project = project.resolve()
    if project == Path("/") or not project.is_dir():
        raise ValueError("Trusted existing project cwd required")
    return ["/usr/bin/docker", "run", "--rm", "-i", "--network", "host", "--read-only",
            "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m",
            "--label", "headroom.component=codex-memory-mcp", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint", "python", image, "-m", "headroom.memory.proxy_mcp",
            "--proxy-url", proxy_url, "--project-root", str(project)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--proxy-url", default="http://127.0.0.1:4444")
    args = parser.parse_args()
    command = docker_command(args.image, args.proxy_url, Path.cwd())
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
