import contextlib
import http.server
import importlib.util
import io
import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bach_video.py"
SPEC = importlib.util.spec_from_file_location("bach_video", SCRIPT)
bach = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bach)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.body[:limit]


class BachVideoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.request_file = self.root / "request.json"
        self.task_file = self.root / "task.json"
        self.write_request({"task": "t2v", "prompt": "A cup rotates on a table."})

    def write_request(self, spec):
        self.request_file.write_text(json.dumps({"model_name": "Bach-1.0-Pro", "input": spec}))

    def run_command(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = bach.main(args)
        return result, out.getvalue(), err.getvalue()

    def test_preview_is_offline_and_reports_effective_frame_ratio(self):
        self.write_request({
            "task": "i2v", "prompt": "Move toward the final frame.",
            "image_url": "https://example.com/start.png", "aspect_ratio": "9:16",
        })
        with mock.patch.object(bach, "open_request") as network:
            result, out, _ = self.run_command(["preview", "--request", str(self.request_file)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out)["effective_aspect_ratio"], "auto")
        network.assert_not_called()

    def test_audio_only_reference_fails_before_network(self):
        self.write_request({
            "task": "r2v", "prompt": "A scene.",
            "reference_inputs": [{"type": "audio", "url": "https://example.com/voice.mp3"}],
        })
        with mock.patch.object(bach, "open_request") as network:
            result, _, _ = self.run_command(["preview", "--request", str(self.request_file)])
        self.assertEqual(result, 1)
        network.assert_not_called()

    def test_reference_video_and_audio_offsets_reach_submission(self):
        refs = [
            {"type": "image", "url": "https://example.com/product.png"},
            {"type": "video", "url": "https://example.com/camera.mp4", "start_time": 1.5},
            {"type": "audio", "url": "https://example.com/ambience.mp3", "start_time": 0.5},
        ]
        self.write_request({"task": "r2v", "prompt": "Use the reference assets.", "reference_inputs": refs})
        response = FakeResponse({"code": 200, "data": {"task_id": "task-123", "status": "TASK_PENDING"}})
        with mock.patch.dict(os.environ, {"BACH_API_KEY": "test-secret"}), mock.patch.object(
            bach, "open_request", return_value=response
        ) as network:
            result, _, _ = self.run_command([
                "submit", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(result, 0)
        network.assert_called_once()
        self.assertEqual(json.loads(network.call_args.args[0].data)["input"]["reference_inputs"], refs)

    def test_negative_reference_offsets_fail_before_network(self):
        for media_type, url in (("video", "https://example.com/clip.mp4"),
                                ("audio", "https://example.com/voice.mp3")):
            with self.subTest(media_type=media_type):
                self.write_request({
                    "task": "r2v", "prompt": "A scene.",
                    "reference_inputs": [
                        {"type": "image", "url": "https://example.com/product.png"},
                        {"type": media_type, "url": url, "start_time": -0.1},
                    ],
                })
                with mock.patch.object(bach, "open_request") as network:
                    result, _, err = self.run_command(["preview", "--request", str(self.request_file)])
                self.assertEqual(result, 1)
                self.assertIn("start_time", err)
                network.assert_not_called()

    def test_submit_saves_task_id_without_key(self):
        response = FakeResponse({"code": 200, "data": {"task_id": "task-123", "status": "TASK_PENDING"}})
        with mock.patch.dict(os.environ, {"BACH_API_KEY": "test-secret"}), mock.patch.object(
            bach, "open_request", return_value=response
        ) as network:
            result, out, _ = self.run_command([
                "submit", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out)["task_id"], "task-123")
        self.assertEqual(network.call_count, 1)
        sent = network.call_args.args[0]
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(sent.full_url, bach.ENDPOINT)
        self.assertEqual(json.loads(sent.data)["input"]["task"], "t2v")
        saved = self.task_file.read_text()
        self.assertEqual(json.loads(saved)["task_id"], "task-123")
        self.assertNotIn("test-secret", saved)
        self.assertEqual(stat.S_IMODE(self.task_file.stat().st_mode), 0o600)

    def test_timeout_does_not_retry_and_preserves_uncertain_record(self):
        with mock.patch.dict(os.environ, {"BACH_API_KEY": "test-secret"}), mock.patch.object(
            bach, "open_request", side_effect=TimeoutError()
        ) as network:
            result, _, err = self.run_command([
                "submit", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(result, 1)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(json.loads(self.task_file.read_text())["state"], "submission_unconfirmed")
        self.assertIn("勿自动重复提交", err)

    def test_existing_record_is_never_overwritten_or_submitted(self):
        self.task_file.write_text("keep this")
        with mock.patch.dict(os.environ, {"BACH_API_KEY": "test-secret"}), mock.patch.object(
            bach, "open_request"
        ) as network:
            result, _, _ = self.run_command([
                "submit", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(result, 1)
        self.assertEqual(self.task_file.read_text(), "keep this")
        network.assert_not_called()

    def test_status_queries_the_existing_id_without_changing_record(self):
        initial = json.dumps({"task_id": "task/123"})
        self.task_file.write_text(initial)
        response = FakeResponse({"code": 200, "data": {"task_id": "task/123", "status": "TASK_SUCCEEDED", "video_url": "https://example.com/result.mp4"}})
        with mock.patch.dict(os.environ, {"BACH_API_KEY": "test-secret"}), mock.patch.object(
            bach, "open_request", return_value=response
        ) as network:
            result, out, _ = self.run_command(["status", "--task-file", str(self.task_file)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out)["data"]["status"], "TASK_SUCCEEDED")
        self.assertEqual(network.call_args.args[0].get_method(), "GET")
        self.assertTrue(network.call_args.args[0].full_url.endswith("/task%2F123"))
        self.assertEqual(self.task_file.read_text(), initial)

    def test_authorization_is_not_forwarded_through_redirects(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/other")
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                with self.assertRaises(bach.ServiceError):
                    bach.call_api("GET", f"http://127.0.0.1:{server.server_port}/start", "test-secret")
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual(seen, ["/start"])


if __name__ == "__main__":
    unittest.main()
