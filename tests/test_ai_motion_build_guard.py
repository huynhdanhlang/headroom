"""Reject incomplete maintenance images before invoking Docker."""

import importlib.util
from pathlib import Path

import pytest


def guard():
    path = Path(__file__).resolve().parents[1] / "scripts/build_ai_motion.py"
    if not path.exists():
        pytest.fail("Maintained image coverage validator is missing")
    spec = importlib.util.spec_from_file_location("amv_build_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_changed_runtime_files_must_be_copied():
    module = guard()
    changes = [("M", "headroom/proxy/server.py"), ("M", "headroom/transforms/content_router.py")]
    with pytest.raises(ValueError, match="content_router"):
        module.validate_overlay(changes, {"headroom/proxy/server.py"})
    module.validate_overlay(changes, {name for _, name in changes})


@pytest.mark.parametrize(
    "path",
    ["pyproject.toml", "uv.lock", "Cargo.toml", "Cargo.lock", "crates/headroom-py/src/lib.rs"],
)
def test_dependency_and_native_changes_require_a_new_base(path):
    with pytest.raises(ValueError, match="base rebuild"):
        guard().validate_overlay([("M", path)], {path})


def test_deleted_runtime_file_cannot_survive_as_stale_base_code():
    with pytest.raises(ValueError, match="base rebuild"):
        guard().validate_overlay([("D", "headroom/obsolete.py")], set())


def test_docs_and_tests_do_not_require_runtime_overlay():
    guard().validate_overlay([("M", "FORK.md"), ("A", "tests/test_example.py")], set())


def test_recipe_requires_exact_base_and_destination():
    module = guard()
    recipe = (
        "FROM "
        + module.BASE_IMAGE
        + "\nCOPY headroom/proxy/server.py /usr/local/lib/python3.13/site-packages/headroom/proxy/server.py\n"
    )
    assert module.copied_sources(recipe) == {"headroom/proxy/server.py"}
    with pytest.raises(ValueError, match="pinned base"):
        module.copied_sources(recipe.replace(module.BASE_IMAGE, "headroom:latest"))
    with pytest.raises(ValueError, match="destination"):
        module.copied_sources(recipe.replace("site-packages/headroom", "site-packages/other"))


@pytest.mark.parametrize(
    "second_stage", ["FROM python:3.13", "FROM\tpython:3.13", "from python:3.13"]
)
def test_later_stage_cannot_discard_verified_base_and_overlay(second_stage):
    module = guard()
    recipe = f"FROM {module.BASE_IMAGE}\nCOPY headroom/proxy/server.py /usr/local/lib/python3.13/site-packages/headroom/proxy/server.py\n{second_stage}\n"
    with pytest.raises(ValueError, match="pinned base"):
        module.copied_sources(recipe)


def test_actual_maintenance_recipe_is_supported():
    module = guard()
    path = Path(__file__).resolve().parents[1] / "docker/Dockerfile.ai-motion"
    sources = module.copied_sources(path.read_text())
    assert "headroom/transforms/content_router.py" in sources


def test_guard_pins_integrated_upstream_source_and_native_image():
    module = guard()
    assert module.UPSTREAM_BASE == "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"
    assert module.BASE_IMAGE == (
        "ghcr.io/headroomlabs-ai/headroom:code-bc21c93@"
        "sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d"
    )
    assert module.SITE_PACKAGES == "/usr/local/lib/python3.13/site-packages/"
