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


def test_local_native_base_accepts_only_the_verified_image_id():
    module = guard()
    expected = "sha256:" + "a" * 64
    module.validate_base_image_id(expected + "\n", expected)
    with pytest.raises(ValueError, match="does not match"):
        module.validate_base_image_id("sha256:" + "b" * 64, expected)


@pytest.mark.parametrize("expected", ["", "headroom:latest", "sha256:abc"])
def test_local_native_base_rejects_an_unpinned_expected_id(expected):
    with pytest.raises(ValueError, match="full sha256"):
        guard().validate_base_image_id("sha256:" + "a" * 64, expected)


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
    assert "headroom/proxy/gateway_responses.py" in sources


def test_guard_pins_integrated_upstream_source_and_native_image():
    module = guard()
    assert module.UPSTREAM_BASE == "3675d4839f35bac37c647408c0ef42c6721c368f"
    assert module.BASE_IMAGE == "ai-motion-headroom-native:4c7acba5-tls-3675d4839f35"
    assert (
        module.BASE_IMAGE_ID
        == "sha256:10b4f171b53b372c12ccdbdc2f4b55b488b3b0ff95612c744ff39021d61ff999"
    )
    assert module.SITE_PACKAGES == "/usr/local/lib/python3.13/site-packages/"
