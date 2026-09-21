"""Essay clips extend the explicit inventory without opening the media directory."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_gallery import ValidationError, validate_blog_media, validate_media_inventory


@pytest.fixture
def catalog(tmp_path):
    def clip(identifier, prefix):
        result = {"id": identifier}
        for field, extension in (("video", "mp4"), ("poster", "jpg")):
            relative = f"{prefix}/{identifier}.{extension}"
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic inventory fixture")
            result[field] = relative
        return result
    records = {"baseline": clip("baseline", "media/libero"),
               "revised": clip("revised", "media/blog/libero")}
    data = {"schemaVersion": 1, "complete": True, "clips": records}
    (tmp_path / "data").mkdir()
    def save(value=None):
        (tmp_path / "data/libero-blog-media.json").write_text(json.dumps(data if value is None else value))
    save()
    return tmp_path, data, save


def test_complete_catalog_can_reuse_baseline_and_add_only_named_blog_assets(catalog):
    root, data, _ = catalog
    paths = validate_blog_media(root)
    assert paths == {clip[field] for clip in data["clips"].values() for field in ("video", "poster")}
    validate_media_inventory(root, paths)


@pytest.mark.parametrize("extra", ["media/blog/extra.mp4", "media/blog/libero/private.json", "media/libero/extra.jpg"])
def test_unlisted_files_are_rejected_even_beside_declared_blog_clips(catalog, extra):
    root, _, _ = catalog
    path = root / extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unlisted")
    with pytest.raises(ValidationError, match="missing or unlisted"):
        validate_media_inventory(root, validate_blog_media(root))


@pytest.mark.parametrize("complete", [False, None, "true", 1])
def test_incomplete_export_cannot_allow_any_clip(catalog, complete):
    root, original, save = catalog
    data = deepcopy(original)
    data["complete"] = complete
    save(data)
    with pytest.raises(ValidationError, match="not complete"):
        validate_blog_media(root)


@pytest.mark.parametrize("field,relative", [
    ("video", "/media/blog/revised.mp4"),
    ("video", "media/blog/../libero/baseline.mp4"),
    ("video", "https://example.invalid/video.mp4"),
    ("video", "media/blog/libero/revised.mp4?download=1"),
    ("poster", "media/blog/libero/revised.mp4"),
    ("poster", "media/blog/libero/missing.jpg"),
])
def test_unsafe_missing_or_mistyped_asset_is_rejected(catalog, field, relative):
    root, data, save = catalog
    data["clips"]["revised"][field] = relative
    save()
    with pytest.raises(ValidationError):
        validate_blog_media(root)


def test_symlink_cannot_become_an_allowed_blog_asset(catalog):
    root, data, _ = catalog
    target = root / data["clips"]["revised"]["video"]
    target.unlink()
    target.symlink_to(root / data["clips"]["baseline"]["video"])
    with pytest.raises(ValidationError, match="Unsafe"):
        validate_blog_media(root)


def test_absent_catalog_does_not_whitelist_existing_blog_files(catalog):
    root, _, _ = catalog
    (root / "data/libero-blog-media.json").unlink()
    assert validate_blog_media(root) == set()
    with pytest.raises(ValidationError, match="missing or unlisted"):
        validate_media_inventory(root, set())


def test_optional_release_media_does_not_relax_blog_inventory(catalog):
    root, _, _ = catalog
    paths = validate_blog_media(root)
    remote = "media/robocasa/remote.mp4"
    validate_media_inventory(root, paths | {remote}, {remote})
    with pytest.raises(ValidationError, match="missing or unlisted"):
        validate_media_inventory(root, paths | {remote})
    (root / "media/blog/extra.mp4").write_bytes(b"extra")
    with pytest.raises(ValidationError, match="missing or unlisted"):
        validate_media_inventory(root, paths | {remote}, {remote})
