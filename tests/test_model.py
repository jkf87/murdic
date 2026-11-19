import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huggingface_hub.errors import LocalEntryNotFoundError

from dictate import model


def repo_listing(sizes):
    return SimpleNamespace(siblings=[SimpleNamespace(rfilename=name, size=size) for name, size in sizes.items()])


LISTING = {"config.json": 2, "weights.npz": 1000, "README.md": 5}


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.config = Path(self.folder.name) / "murdic"

    def tearDown(self):
        self.folder.cleanup()

    def test_marked_local_copy_is_used_without_network(self):
        target = model.model_dir(self.config)
        target.mkdir(parents=True)
        (target / model.MARKER).write_text("pinned\n")
        with patch.object(model, "snapshot_download", side_effect=AssertionError("network used")):
            self.assertEqual(model.resolve(self.config), str(target))

    def test_hugging_face_cache_is_reused(self):
        with patch.object(model, "snapshot_download", return_value="/cache/snapshot") as cached:
            self.assertEqual(model.resolve(self.config), "/cache/snapshot")
        cached.assert_called_once_with(model.DEFAULT_MODEL, local_files_only=True)

    def test_download_reports_progress_and_marks_complete(self):
        target = model.model_dir(self.config)
        progress = []

        def fake_snapshot(repo, **kwargs):
            if kwargs.get("local_files_only"):
                raise LocalEntryNotFoundError("not cached")
            self.assertEqual(kwargs["revision"], model.REVISION)
            self.assertEqual(kwargs["allow_patterns"], model.FILES)
            # Byte bars as huggingface_hub drives them: 400 bytes, then 600 more.
            bar = kwargs["tqdm_class"](total=1000, unit="B", file=io.StringIO())
            bar.update(400)
            bar.update(600)
            bar.close()
            folder = Path(kwargs["local_dir"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "config.json").write_text("{}")
            (folder / "weights.npz").write_bytes(b"0" * 1000)
            return str(folder)

        with patch.object(model, "snapshot_download", side_effect=fake_snapshot), \
                patch.object(model, "HfApi") as api:
            api.return_value.model_info.return_value = repo_listing(LISTING)
            self.assertEqual(model.resolve(self.config, progress.append), str(target))
        self.assertTrue((target / model.MARKER).is_file())
        self.assertTrue(any(0.3 < value < 1.0 for value in progress), progress)  # intermediate byte fractions
        self.assertEqual(progress[-1], 1.0)
        self.assertEqual(progress, sorted(progress))

    def test_failed_download_is_a_korean_model_error_without_marker(self):
        def broken(repo, **kwargs):
            if kwargs.get("local_files_only"):
                raise LocalEntryNotFoundError("not cached")
            raise OSError("connection reset")

        with patch.object(model, "snapshot_download", side_effect=broken), \
                patch.object(model, "HfApi") as api:
            api.return_value.model_info.return_value = repo_listing(LISTING)
            with self.assertRaises(model.ModelError) as caught:
                model.resolve(self.config)
        self.assertIn("다시 받기", str(caught.exception))
        self.assertFalse((model.model_dir(self.config) / model.MARKER).exists())

    def test_refetch_discards_the_murdic_copy_before_downloading(self):
        target = model.model_dir(self.config)
        target.mkdir(parents=True)
        (target / model.MARKER).write_text("old\n")
        (target / "weights.npz").write_bytes(b"damaged")
        calls = []

        def fake_snapshot(repo, **kwargs):
            calls.append(kwargs)
            self.assertFalse((target / "weights.npz").exists())
            Path(kwargs["local_dir"]).mkdir(parents=True, exist_ok=True)
            (target / "config.json").write_text("{}")
            (target / "weights.npz").write_bytes(b"0" * 1000)
            return str(target)

        with patch.object(model, "snapshot_download", side_effect=fake_snapshot), \
                patch.object(model, "HfApi") as api:
            api.return_value.model_info.return_value = repo_listing(LISTING)
            model.resolve(self.config, refetch=True)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("local_files_only", calls[0])
        self.assertTrue((target / model.MARKER).is_file())

    def test_serve_reports_model_error_as_an_event_when_offline(self):
        # HF_HOME moves the Hugging Face cache away; HOME stays put because the dev Python finds numpy in the user site.
        with tempfile.TemporaryDirectory() as hub_home:
            env = dict(os.environ, HF_HOME=hub_home, HF_HUB_OFFLINE="1")
            run = subprocess.run([sys.executable, "-m", "dictate", "--config-dir", str(Path(hub_home) / "murdic"), "serve"],
                                 input="", capture_output=True, text=True, env=env, timeout=120)
        events = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual([event["event"] for event in events], ["model_error"])
        self.assertIn("다시 받기", events[0]["message"])


if __name__ == "__main__":
    unittest.main()
