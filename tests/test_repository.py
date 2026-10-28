"""Guards the HACS/hassfest requirements of the repository (without starting Home Assistant)."""

import json
import re
import struct
from pathlib import Path

import pytest

from custom_components.enbw_charging_stations.const import DOMAIN

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "custom_components"
INTEGRATION = COMPONENTS / DOMAIN

# Keys that hacs.json may contain according to the HACS documentation
HACS_KEYS = {
    "name",
    "content_in_root",
    "zip_release",
    "filename",
    "hide_default_branch",
    "country",
    "homeassistant",
    "hacs",
    "persistent_directory",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_exactly_one_integration_in_repo():
    dirs = [p for p in COMPONENTS.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert [p.name for p in dirs] == [DOMAIN]


def test_manifest_required_keys():
    manifest = _load(INTEGRATION / "manifest.json")
    for key in ("domain", "documentation", "issue_tracker", "codeowners", "name", "version"):
        assert manifest.get(key), f"manifest.json is missing '{key}'"
    assert manifest["domain"] == DOMAIN
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["codeowners"] and all(c.startswith("@") for c in manifest["codeowners"])
    assert re.fullmatch(r"https://github\.com/[^/]+/[^/]+", manifest["documentation"])
    assert re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues", manifest["issue_tracker"])
    assert "REPLACE_ME" not in json.dumps(manifest)


def test_manifest_keys_sorted_like_hassfest():
    keys = list(_load(INTEGRATION / "manifest.json"))
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_brand_icon_present_and_square():
    icon = INTEGRATION / "brand" / "icon.png"
    data = icon.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height


def test_hacs_json():
    hacs = _load(ROOT / "hacs.json")
    assert hacs.get("name")
    assert set(hacs) <= HACS_KEYS, f"unknown keys: {set(hacs) - HACS_KEYS}"
    # the service is Dutch: HACS then asks for 'country'
    assert hacs.get("country") == "NL"


@pytest.mark.parametrize("name", ["README.md", "LICENSE", "hacs.json"])
def test_root_files_exist(name):
    assert (ROOT / name).is_file()


def test_no_cache_or_build_artifacts_in_integration():
    for bad in (".ruff_cache", ".pytest_cache", ".mypy_cache"):
        assert not (INTEGRATION / bad).exists()


def _keys(data: dict, prefix: str = ""):
    for key, value in data.items():
        if isinstance(value, dict):
            yield from _keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def test_translations_in_sync():
    en = set(_keys(_load(INTEGRATION / "translations" / "en.json")))
    nl = set(_keys(_load(INTEGRATION / "translations" / "nl.json")))
    assert en == nl
