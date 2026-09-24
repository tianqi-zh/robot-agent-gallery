"""Keep the original LIBERO publisher from replacing a shared Space."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from huggingface_hub.errors import RepositoryNotFoundError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_benchmend.py"
SPEC = importlib.util.spec_from_file_location("benchmend_publish", SCRIPT)
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def test_shared_space_stops_before_any_remote_mutation(monkeypatch):
    api = Mock()
    api.repo_info.return_value = SimpleNamespace(siblings=[
        SimpleNamespace(rfilename=name)
        for name in sorted(publish.SPACE_PUBLIC_FILES | {
            "data/gallery.json", "gallery/robotwin_nvidia10/index.html",
            "media/robotwin_nvidia10/recording.mp4",
        })
    ])
    monkeypatch.setattr(publish, "HfApi", lambda: api)
    monkeypatch.setattr(publish, "validate_dataset", lambda root: ([{}], {"episodes.json"}))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(ValueError, match="LIBERO-only interface over shared Space benchmend/gallery"):
        publish.main()

    assert [call[0] for call in api.mock_calls] == ["repo_info"]
    api.repo_info.assert_called_once_with("benchmend/gallery", repo_type="space", files_metadata=True)


@pytest.mark.parametrize("files", [
    {},  # Existing empty repo.
    {"README.md": "readme", ".gitattributes": "attributes",
     "style.css": "114adf441e9032febb46bc056b2a8bb651075f0d"},  # New HF template.
    {name: "existing" for name in publish.SPACE_PUBLIC_FILES},
])
def test_original_space_and_initial_template_are_allowed(files):
    info = SimpleNamespace(sha="previous", siblings=[
        SimpleNamespace(rfilename=name, blob_id=blob) for name, blob in files.items()
    ])
    api = Mock()
    api.repo_info.return_value = info
    assert publish.check_space_inventory(api, "benchmend/gallery") is info


@pytest.mark.parametrize("status", [401, 403, 404])
def test_only_a_missing_space_allows_creation(status):
    api = Mock()
    error = RepositoryNotFoundError("Space lookup failed", response=httpx.Response(
        status, request=httpx.Request("GET", "https://huggingface.co/api/spaces/benchmend/gallery"),
    ))
    api.repo_info.side_effect = error
    if status == 404:
        assert publish.check_space_inventory(api, "benchmend/gallery") is None
    else:
        with pytest.raises(RepositoryNotFoundError) as raised:
            publish.check_space_inventory(api, "benchmend/gallery")
        assert raised.value is error


def test_unknown_template_stylesheet_is_rejected():
    api = Mock()
    api.repo_info.return_value = SimpleNamespace(siblings=[
        SimpleNamespace(rfilename="style.css", blob_id="collaborator-stylesheet"),
    ])
    with pytest.raises(ValueError, match="Unexpected style.css"):
        publish.check_space_inventory(api, "benchmend/gallery")
