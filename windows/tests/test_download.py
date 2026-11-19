"""First-run downloader: resume, checksum and cancellation against a local HTTP server."""
import hashlib
import http.server
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from murdic_win import download  # noqa: E402

PAYLOAD = bytes(range(256)) * 9000   # about 2.3 MB, several chunks
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    honour_range = True
    agents = []

    def do_GET(self):
        Handler.agents.append(self.headers.get("User-Agent"))
        start = 0
        header = self.headers.get("Range")
        if header and self.honour_range:
            start = int(header.split("=")[1].rstrip("-"))
            self.send_response(206)
        else:
            self.send_response(200)
        body = PAYLOAD[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/file.bin"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dest = Path(self.folder.name) / "file.bin"
        Handler.honour_range = True

    def tearDown(self):
        self.folder.cleanup()

    def test_full_download_with_progress(self):
        seen = []
        download.fetch(self.url, self.dest, len(PAYLOAD), SHA, lambda d, t: seen.append((d, t)))
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertEqual(seen[-1], (len(PAYLOAD), len(PAYLOAD)))
        self.assertTrue(Handler.agents[-1].startswith("murdic/"))

    def test_resume_from_part(self):
        part = self.dest.with_name("file.bin.part")
        part.write_bytes(PAYLOAD[:1_000_000])
        download.fetch(self.url, self.dest, len(PAYLOAD), SHA)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertFalse(part.exists())

    def test_server_without_range_restarts(self):
        Handler.honour_range = False
        self.dest.with_name("file.bin.part").write_bytes(PAYLOAD[:500_000])
        download.fetch(self.url, self.dest, len(PAYLOAD), SHA)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_checksum_mismatch_is_rejected(self):
        with self.assertRaises(download.DownloadError):
            download.fetch(self.url, self.dest, len(PAYLOAD), "0" * 64)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest.with_name("file.bin.part").exists())

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(download.Cancelled):
            download.fetch(self.url, self.dest, len(PAYLOAD), SHA, cancel=cancel)
        self.assertFalse(self.dest.exists())

    def test_model_manifest(self):
        self.assertEqual([name for name, _, _ in download.MODEL_FILES],
                         ["config.json", "tokenizer.json", "vocabulary.txt", "model.bin"])
        self.assertTrue(all(len(sha) == 64 for _, _, sha in download.MODEL_FILES))
        self.assertEqual(len(download.MODEL_REVISION), 40)


if __name__ == "__main__":
    unittest.main()
