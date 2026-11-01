"""Pinned-archive download: retries a dropped connection, fails fast on 4xx."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import prepare_ffmpeg_source as source  # noqa: E402


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DownloadTests(unittest.TestCase):
    def test_retries_transient_reset(self):
        """The nyarch-gnome failure: TLS handshake reset mid-download."""
        attempts = []

        def urlopen(url, timeout=None):
            attempts.append(url)
            if len(attempts) == 1:
                raise ConnectionResetError(104, 'Connection reset by peer')
            return _Response(b'archive')

        with patch.object(source.urllib.request, 'urlopen', urlopen), \
                patch.object(source.time, 'sleep') as sleep:
            self.assertEqual(source.download('https://example.invalid/f.tar.xz'), b'archive')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleep.call_count, 1)

    def test_gives_up_after_the_last_attempt(self):
        def urlopen(url, timeout=None):
            raise OSError(104, 'Connection reset by peer')

        with patch.object(source.urllib.request, 'urlopen', urlopen), \
                patch.object(source.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                source.download('https://example.invalid/f.tar.xz')
        self.assertEqual(sleep.call_count, source.ATTEMPTS - 1)

    def test_missing_archive_is_not_retried(self):
        def urlopen(url, timeout=None):
            raise source.urllib.error.HTTPError(url, 404, 'Not Found', {}, None)

        with patch.object(source.urllib.request, 'urlopen', urlopen), \
                patch.object(source.time, 'sleep') as sleep:
            with self.assertRaises(source.urllib.error.HTTPError):
                source.download('https://example.invalid/f.tar.xz')
        self.assertEqual(sleep.call_count, 0)


if __name__ == '__main__':
    unittest.main()
