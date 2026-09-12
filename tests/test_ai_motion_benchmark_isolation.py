"""The standalone benchmark must not inherit live CCR/Headroom state."""

import importlib.util
import os
from pathlib import Path


def test_benchmark_uses_fresh_local_state_without_mutating_parent(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/benchmark_ai_motion.py"
    spec = importlib.util.spec_from_file_location("amv_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = {
        "HEADROOM_CCR_BACKEND": "redis",
        "HEADROOM_CCR_REDIS_URL": "redis://fixture",
        "HEADROOM_WORKSPACE_DIR": "/live",
        "HEADROOM_CONFIG_DIR": "/live/config",
        "PATH": "/bin",
        "PYTHONPATH": "/outside",
    }
    child = module.isolated_environment(tmp_path, Path("/source"), original)
    assert child["HEADROOM_CCR_BACKEND"] == "memory"
    assert child["HEADROOM_WORKSPACE_DIR"] == str(tmp_path / "state")
    assert child["HEADROOM_CONFIG_DIR"] == str(tmp_path / "config")
    assert "HEADROOM_CCR_REDIS_URL" not in child
    assert child["HEADROOM_BEACON"] == "off"
    assert child["DO_NOT_TRACK"] == "1"
    assert child["PYTHONPATH"].split(os.pathsep)[0] == str(Path("/source"))
    assert original["HEADROOM_CCR_BACKEND"] == "redis"
