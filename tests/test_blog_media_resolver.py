"""Offline integrity checks for public media downloads."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from blog_validation import MediaResolver, ValidationError


class BlogMediaResolverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'blog'
        self.root.mkdir()
        self.config = self.root / 'gallery-hosting.json'
        self.config.write_text(json.dumps({
            'space': 'Alan0928/robot-agent-gallery',
            'galleryUrl': 'https://alan0928-robot-agent-gallery.static.hf.space/',
            'mediaBaseUrl': 'https://huggingface.co/datasets/Alan0928/robot-agent-gallery/resolve/' + 'a' * 40 + '/',
        }))
        self.relative = 'media/libero/example.mp4'
        self.payload = b'synthetic media bytes'
        self.digest = sha256(self.payload).hexdigest()
        self.resolver = MediaResolver(self.root)
        self.request = patch('blog_validation.urlopen')
        self.urlopen = self.request.start()
        self.addCleanup(self.request.stop)
        self.urlopen.side_effect = lambda *args, **kwargs: BytesIO(self.payload)

    def resolve(self, resolver=None):
        return (resolver or self.resolver).resolve(self.relative, 'video', len(self.payload), self.digest)

    def test_download_is_verified_and_cached(self):
        cached = self.resolve()
        self.assertEqual(cached.read_bytes(), self.payload)
        self.assertTrue(cached.is_relative_to(self.root / '.gallery-cache/blog-media'))
        self.assertEqual(self.urlopen.call_args.args[0].full_url,
                         'https://huggingface.co/datasets/Alan0928/robot-agent-gallery/resolve/' + 'a' * 40 + '/' + self.relative)
        self.assertEqual(self.resolve(), cached)
        self.urlopen.assert_called_once()

    def test_space_media_remains_supported(self):
        base = 'https://huggingface.co/spaces/Alan0928/robot-agent-gallery/resolve/main/'
        self.config.write_text(json.dumps({'mediaBaseUrl': base}))
        self.assertEqual(self.resolve().read_bytes(), self.payload)
        self.assertEqual(self.urlopen.call_args.args[0].full_url, base + self.relative)

    def test_cache_tampering_fails_without_redownload(self):
        cached = self.resolve()
        cached.write_bytes(b'x' * len(self.payload))
        with self.assertRaisesRegex(ValidationError, 'hash/size mismatch'):
            self.resolve()
        self.urlopen.assert_called_once()

    def test_local_export_needs_no_hosting_config_or_network(self):
        media_root = self.root.parent / 'export'
        video = media_root / self.relative
        video.parent.mkdir(parents=True)
        video.write_bytes(self.payload)
        self.config.unlink()
        self.assertEqual(self.resolve(MediaResolver(self.root, media_root=media_root)), video)
        self.urlopen.assert_not_called()

    def test_explicit_media_root_never_downloads_missing_file(self):
        with self.assertRaisesRegex(ValidationError, 'Missing video'):
            self.resolve(MediaResolver(self.root, media_root=self.root.parent / 'missing'))
        self.urlopen.assert_not_called()

    def test_local_tampering_fails_without_network(self):
        video = self.root / self.relative
        video.parent.mkdir(parents=True)
        video.write_bytes(b'x' * len(self.payload))
        with self.assertRaisesRegex(ValidationError, 'hash/size mismatch'):
            self.resolve()
        self.urlopen.assert_not_called()

    def test_traversal_and_noncanonical_paths_never_download(self):
        for relative in ['media/../../outside.mp4', '/media/video.mp4', 'media//video.mp4',
                         'media/./video.mp4', 'media/video.mp4?token=x', 'media\\video.mp4']:
            with self.subTest(relative=relative), self.assertRaises(ValidationError):
                self.resolver.resolve(relative, 'video', len(self.payload), self.digest)
        self.urlopen.assert_not_called()

    def test_cache_symlink_is_rejected_before_writing(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        cache = self.root / '.gallery-cache'
        cache.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, 'Unsafe'):
            self.resolve()
        self.assertEqual(list(outside.iterdir()), [])
        self.urlopen.assert_not_called()

    def test_local_parent_symlink_is_rejected(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (self.root / 'media').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, 'Unsafe'):
            self.resolve()
        self.urlopen.assert_not_called()

    def test_corrupt_or_oversized_download_leaves_no_cache_file(self):
        for payload in [b'x' * len(self.payload), self.payload + b'overflow', b'short']:
            self.urlopen.side_effect = lambda *args, body=payload, **kwargs: BytesIO(body)
            with self.subTest(payload=payload), self.assertRaisesRegex(ValidationError, 'hash/size mismatch'):
                self.resolve()
            self.assertEqual([p for p in (self.root / '.gallery-cache').rglob('*') if p.is_file()], [])

    def test_invalid_hosting_origin_fails_before_network(self):
        for base in ['http://huggingface.co/spaces/a/b/resolve/main/',
                     'https://huggingface.co.evil.test/spaces/a/b/resolve/main/',
                     'https://huggingface.co/spaces/a/b/resolve/main/?x=1',
                     'https://huggingface.co/datasets/a/b/blob/main/',
                     'https://huggingface.co.evil.test/datasets/a/b/resolve/main/',
                     'http://huggingface.co/datasets/a/b/resolve/main/']:
            self.config.write_text(json.dumps({'mediaBaseUrl': base}))
            with self.subTest(base=base), self.assertRaisesRegex(ValidationError, 'mediaBaseUrl'):
                self.resolve(MediaResolver(self.root))
        self.urlopen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
