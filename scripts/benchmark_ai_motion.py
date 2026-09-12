"""Synthetic router benchmark; excludes LLM/network latency and startup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path


class Counter:
    def count_text(self, text):
        return max(1, len(text) // 4)


def isolated_environment(temporary, source_root, inherited):
    environment = {
        key: value for key, value in inherited.items() if not key.startswith("HEADROOM_")
    }
    environment.update(
        {
            "HEADROOM_WORKSPACE_DIR": str(temporary / "state"),
            "HEADROOM_CONFIG_DIR": str(temporary / "config"),
            "HEADROOM_SETTINGS_PATH": str(temporary / "config/runtime-env.json"),
            "HEADROOM_CCR_BACKEND": "memory",
            "HEADROOM_BEACON": "off",
            "DO_NOT_TRACK": "1",
            "XDG_CACHE_HOME": str(temporary / "cache"),
            "PYTHONPATH": str(source_root) + os.pathsep + inherited.get("PYTHONPATH", ""),
        }
    )
    return environment


def run_case(workers, requests, cached):
    from headroom.transforms.compression_policy import policy_default_payg
    from headroom.transforms.content_router import ContentRouter, ContentRouterConfig

    router = ContentRouter(ContentRouterConfig(lossless=False, enable_kompress=False))
    policy = replace(policy_default_payg(), toin_read_only=True)
    tokenizer = Counter()

    def execute(index):
        variant = 0 if cached else index
        payload = json.dumps(
            [
                {"id": i, "status": "ready", "value": i * 3, "path": f"module_{variant}_{i}.py"}
                for i in range(300)
            ]
        )
        messages = [
            {"role": "user", "content": "summarize records"},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "records", "content": payload}],
            },
        ]
        started = time.perf_counter()
        result = router.apply(
            messages, tokenizer, target_ratio=0.5, skip_kompress=True, compression_policy=policy
        )
        elapsed = (time.perf_counter() - started) * 1000
        digest = hashlib.sha256(json.dumps(result.messages, sort_keys=True).encode()).hexdigest()
        return elapsed, result.tokens_before, result.tokens_after, digest

    execute(0 if cached else -1)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(execute, range(requests)))
    elapsed = time.perf_counter() - started
    latencies = sorted(row[0] for row in results)
    return {
        "workers": workers,
        "requests": requests,
        "cached_payload": cached,
        "median_ms": round(statistics.median(latencies), 3),
        "p95_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3),
        "requests_per_second": round(requests / elapsed, 2),
        "estimated_tokens_before": sum(row[1] for row in results),
        "estimated_tokens_after": sum(row[2] for row in results),
        "output_digest": hashlib.sha256("".join(row[3] for row in results).encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 12])
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--case-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cached", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.requests <= 1000 or any(not 1 <= n <= 64 for n in args.workers):
        parser.error("requests must be 1..1000 and workers 1..64")
    source_root = Path(__file__).resolve().parents[1]
    if args.case_worker:
        if len(args.workers) != 1:
            parser.error("one worker count is required for a child case")
        with tempfile.TemporaryDirectory(prefix="headroom-benchmark-") as directory:
            temporary = Path(directory)
            for name in ["state", "config", "cache"]:
                (temporary / name).mkdir()
            environment = isolated_environment(temporary, source_root, os.environ)
            os.environ.clear()
            os.environ.update(environment)
            sys.path.insert(0, str(source_root))
            import headroom

            if not Path(headroom.__file__).resolve().is_relative_to(source_root / "headroom"):
                raise SystemExit("Benchmark imported a different source checkout")
            print(json.dumps(run_case(args.workers[0], args.requests, args.cached)))
        return
    results = []
    for workers in args.workers:
        for cached in [False, True]:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--case-worker",
                "--workers",
                str(workers),
                "--requests",
                str(args.requests),
            ]
            if cached:
                command.append("--cached")
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            results.append(json.loads(result.stdout))
    print(
        json.dumps(
            {"kind": "synthetic_router_only", "ccr_backend": "isolated-memory", "results": results},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
