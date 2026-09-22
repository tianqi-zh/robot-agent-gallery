"""Small shared checks and hash-verified media access for the essay."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

PRIVATE_KEYS = {
    "auth", "authorization", "authentication", "credentials", "credential", "apikey",
    "accesstoken", "refreshtoken", "idtoken", "bearertoken", "secret", "password",
    "thread", "threads", "threadid", "conversation", "conversations", "conversationid",
    "codexhome", "workspace", "workspacedir", "rawlogs", "rawevents", "reasoning",
    "reasoningcontent", "chainofthought", "transcript", "stdout", "stderr", "prompt",
    "systemprompt", "messages", "oauth", "authorizationheader", "eventlog", "codexevents",
}


class ValidationError(Exception):
    """An exported asset does not satisfy the publication contract."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Cannot read JSON {path.name}: {exc}") from exc


def public_metadata(value, location="data"):
    """Check public JSON without printing potentially private values in errors."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            require(normalized not in PRIVATE_KEYS, f"Private metadata key at {location}")
            public_metadata(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            public_metadata(child, f"{location}[{index}]")
    elif isinstance(value, str):
        require(not re.search(r"(?:^|[\s\"'=])/(?:home|playpen|tmp|Users|root|mnt|private)/", value),
                f"Machine-local path at {location}")
        require(not value.startswith(("/", "file:", "\\\\")) and not re.match(r"^[A-Za-z]:[\\/]", value),
                f"Absolute local path at {location}")
        require(not re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", value), f"Possible secret at {location}")
        require(not any(marker in value.lower() for marker in ("auth.json", "codex_home", "codex-events.jsonl")),
                f"Private artifact reference at {location}")
    elif type(value) is float:
        require(math.isfinite(value), f"Non-finite metadata number at {location}")


def local_asset(root, relative, label, *, allow_missing=False):
    require(isinstance(relative, str) and relative, f"Missing {label} path")
    path = PurePosixPath(relative)
    require(path.as_posix() == relative and not path.is_absolute() and ".." not in path.parts and "\\" not in relative
            and ":" not in relative and "?" not in relative and "#" not in relative,
            f"{label} must be a plain repository-relative path")
    require(path.parts[0] in {"media", "assets"}, f"{label} must be a public media asset")
    candidate = root.joinpath(*path.parts)
    require(allow_missing or candidate.is_file(), f"Missing {label}: {relative}")
    require(not any(parent.is_symlink() for parent in (candidate, *candidate.parents))
            and candidate.resolve().is_relative_to(root.resolve()),
            f"Unsafe {label}: {relative}")
    return candidate


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MediaResolver:
    """Use local exports or download only the essay's fingerprinted assets.

    An explicit media_root is strictly offline. Otherwise existing checkout
    assets remain usable; missing assets are cached from the configured Hugging Face repository.
    Cached files are checked on every use, just like local files.
    """

    def __init__(self, root, *, media_root=None, cache_root=None):
        self.root = Path(root).resolve()
        self.media_root = Path(media_root).resolve() if media_root is not None else None
        self.cache_root = Path(cache_root) if cache_root is not None else self.root / '.gallery-cache/blog-media'
        self._base_url = None

    def _media_url(self, relative):
        if self._base_url is None:
            config = read_json(self.root / 'gallery-hosting.json')
            base = config.get('mediaBaseUrl', '')
            parsed = urlsplit(base)
            require(parsed.scheme == 'https' and parsed.netloc == 'huggingface.co'
                    and not parsed.query and not parsed.fragment and base.endswith('/')
                    and re.fullmatch(r'/(?:datasets|spaces)/[^/]+/[^/]+/resolve/[^/]+/', parsed.path),
                    'Invalid Hugging Face mediaBaseUrl in gallery-hosting.json')
            self._base_url = base
        return self._base_url + quote(relative, safe='/')

    @staticmethod
    def _verify(path, expected_size, expected_digest, label):
        require(path.stat().st_size == expected_size and sha256(path) == expected_digest,
                f'{label} hash/size mismatch')
        return path

    def resolve(self, relative, kind, expected_size, expected_digest, *, label=None):
        label = label or kind
        require(type(expected_size) is int and expected_size > 0, f'{label}: invalid byte count')
        require(isinstance(expected_digest, str) and re.fullmatch('[0-9a-f]{64}', expected_digest),
                f'{label}: invalid SHA-256')
        source_root = self.media_root if self.media_root is not None else self.root
        local = local_asset(source_root, relative, kind, allow_missing=self.media_root is None)
        if local.is_file():
            return self._verify(local, expected_size, expected_digest, label)

        cached = local_asset(self.cache_root, relative, kind, allow_missing=True)
        if cached.is_file():
            return self._verify(cached, expected_size, expected_digest, label)

        url = self._media_url(relative)
        cached.parent.mkdir(parents=True, exist_ok=True)
        # A bounded temporary download never replaces a verified cache entry.
        temporary = None
        try:
            request = Request(url, headers={'User-Agent': 'AgentAsPolicy-BlogValidator/1.0'})
            with urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(
                    dir=cached.parent, prefix='.download-', delete=False) as stream:
                temporary = Path(stream.name)
                received = 0
                while chunk := response.read(min(1024 * 1024, expected_size - received + 1)):
                    received += len(chunk)
                    require(received <= expected_size, f'{label} hash/size mismatch')
                    stream.write(chunk)
            self._verify(temporary, expected_size, expected_digest, label)
            temporary.replace(cached)
            return cached
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
