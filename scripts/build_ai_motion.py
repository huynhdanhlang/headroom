"""Build only a complete, clean, native-compatible AI Motion overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

UPSTREAM_BASE = "63c5df8a39c4c515a0b9b714050e530df8efeb7a"
BASE_IMAGE = "ghcr.io/headroomlabs-ai/headroom:code-63c5df8@sha256:dad48358f61d7f56bbc2ed0b59f240644aa762b65a853fe1a4cc921941700760"
SITE_PACKAGES = "/usr/local/lib/python3.13/site-packages/"
NATIVE_INPUTS = {"pyproject.toml", "uv.lock", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml"}


def validate_overlay(changes, copied):
    for status, path in changes:
        if path in NATIVE_INPUTS or path.startswith(("crates/", "headroom/_core")):
            raise ValueError(f"A native/dependency base rebuild is required for {path}")
        if not path.startswith("headroom/"):
            continue
        if status not in {"A", "M"}:
            raise ValueError(f"A base rebuild is required for removed/renamed runtime file {path}")
        if path not in copied:
            raise ValueError(f"Image recipe omits changed runtime file {path}")


def copied_sources(recipe):
    lines = [
        line.strip()
        for line in recipe.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if any(line.endswith(chr(92)) or "<<" in line for line in lines):
        raise ValueError("Use explicit single-line Docker instructions with the pinned base")
    instructions = [line.split(None, 1) for line in lines]
    stages = [parts for parts in instructions if parts[0].upper() == "FROM"]
    if stages != [["FROM", BASE_IMAGE]]:
        raise ValueError("Image recipe must use one stage with the exact pinned base")
    copied = set()
    for line, instruction in zip(lines, instructions, strict=True):
        if instruction[0].upper() != "COPY":
            continue
        parts = shlex.split(line)
        if len(parts) != 3 or not parts[1].startswith("headroom/"):
            raise ValueError("Use explicit single-file runtime COPY instructions")
        if parts[2] != SITE_PACKAGES + parts[1]:
            raise ValueError(f"Incorrect overlay destination for {parts[1]}")
        copied.add(parts[1])
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments])

    if git("status", "--porcelain", "--untracked-files=all").strip():
        raise SystemExit(
            "Commit or remove working-tree changes before building a revision-labeled image"
        )
    revision = git("rev-parse", "HEAD").decode().strip()
    recipe = root / "docker/Dockerfile.ai-motion"
    copied = copied_sources(recipe.read_text())
    changes = [
        line.split("\t", 1)
        for line in git("diff", "--name-status", "--no-renames", UPSTREAM_BASE, revision)
        .decode()
        .splitlines()
    ]
    validate_overlay(changes, copied)
    hashes = {}
    for path in sorted(copied):
        committed = git("show", f"{revision}:{path}")
        if (root / path).read_bytes() != committed:
            raise SystemExit(f"Working-tree bytes differ from the committed overlay: {path}")
        hashes[path] = hashlib.sha256(committed).hexdigest()
    tag = args.tag or f"headroom-amv:{revision[:12]}"
    command = [
        "docker",
        "--context",
        "default",
        "build",
        "-f",
        str(recipe),
        "--build-arg",
        f"FORK_COMMIT={revision}",
        "-t",
        tag,
        str(root),
    ]
    print(
        json.dumps({"commit": revision, "image": tag, "sourceHashes": hashes}, indent=2), flush=True
    )
    if not args.check_only:
        environment = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
                "BUILDX_BUILDER",
                "BUILDKIT_HOST",
            }
        }
        environment["BUILDX_BUILDER"] = "default"
        subprocess.run(command, env=environment, check=True)


if __name__ == "__main__":
    main()
