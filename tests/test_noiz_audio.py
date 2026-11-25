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
from urllib import parse


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "noiz_audio.py"
SPEC = importlib.util.spec_from_file_location("noiz_audio", SCRIPT)
noiz = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(noiz)


class FakeResponse:
    def __init__(self, value):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.body = io.BytesIO(raw)
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()

    def read(self, size):
        return self.body.read(size)


class NoizAudioTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.request = self.root / "request.json"
        self.task = self.root / "task.json"
        self.output = self.root / "result.wav"

    def write_request(self, payload):
        self.request.write_text(json.dumps(payload), encoding="utf-8")

    def run_command(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = noiz.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_preview_is_offline_for_all_three_modes(self):
        requests = [
            {"kind": "effect", "prompt": "A ceramic cup taps a table.", "duration": 2},
            {"kind": "music", "prompt": "Gentle acoustic pop", "lyrics_prompt": "A bright morning"},
            {"kind": "cover", "source_audio_url": "https://example.com/source.mp3",
             "lyrics": "A new beginning", "style": "acoustic", "melody_adherence": "high"},
        ]
        for payload in requests:
            with self.subTest(kind=payload["kind"]):
                self.write_request(payload)
                with mock.patch.object(noiz, "open_request") as network:
                    code, output, _ = self.run_command(["preview", "--request", str(self.request)])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output)["kind"], payload["kind"])
                network.assert_not_called()

    def test_invalid_inputs_are_rejected_before_network(self):
        invalid = [
            {"kind": [], "prompt": "sound"},
            {"kind": "effect", "prompt": "sound", "duration": True},
            {"kind": "effect", "prompt": "sound", "duration": 31},
            {"kind": "music", "prompt": "pop", "lyrics": "words", "lyrics_prompt": "theme"},
            {"kind": "cover", "source_audio_url": "https://127.0.0.1/a.mp3", "lyrics": "words",
             "style": "pop", "melody_adherence": "high"},
            {"kind": "effect", "prompt": "sound", "api_key": "not-allowed"},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.write_request(payload)
                with mock.patch.object(noiz, "open_request") as network:
                    code, _, _ = self.run_command(["preview", "--request", str(self.request)])
                self.assertEqual(code, 1)
                network.assert_not_called()

    def test_effect_submits_form_and_saves_private_record(self):
        self.write_request({"kind": "effect", "prompt": "A small click.", "duration": 2, "output_format": "wav"})
        response = FakeResponse({"code": 0, "data": {"results": [{"file_url": "https://cdn.example.com/click.wav"}]}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", return_value=response
        ) as network:
            code, output, _ = self.run_command([
                "submit", "--request", str(self.request), "--task-file", str(self.task)
            ])
        self.assertEqual(code, 0)
        sent = network.call_args.args[0]
        self.assertEqual(sent.full_url, "https://noiz.ai/v1/text-to-sound")
        self.assertEqual(sent.get_header("Authorization"), "test-secret")
        self.assertEqual(parse.parse_qs(sent.data.decode())["duration"], ["2"])
        self.assertEqual(json.loads(output)["state"], "completed")
        saved = self.task.read_text()
        self.assertNotIn("test-secret", saved)
        self.assertNotIn("A small click", saved)
        self.assertEqual(stat.S_IMODE(self.task.stat().st_mode), 0o600)
        with mock.patch.object(noiz, "open_request") as network:
            code, output, _ = self.run_command(["status", "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["results"][0]["download_ready"])
        network.assert_not_called()

    def test_song_tracks_each_variant_and_queries_status(self):
        self.write_request({"kind": "music", "prompt": "Gentle pop", "lyrics_prompt": "A fresh start"})
        submission = FakeResponse({"code": 0, "data": {"results": [
            {"gen_product_id": "song-1"}, {"gen_product_id": "song-2"}
        ]}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", return_value=submission
        ) as network:
            code, _, _ = self.run_command(["submit", "--request", str(self.request), "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        self.assertEqual(network.call_args.args[0].full_url, "https://noiz.ai/v1/text-to-music")
        self.assertEqual(json.loads(self.task.read_text())["job_ids"], ["song-1", "song-2"])
        responses = [
            FakeResponse({"code": 0, "data": {"status": "succeeded", "audio_url": "https://cdn.example.com/one.mp3"}}),
            FakeResponse({"code": 0, "data": {"status": "processing"}}),
        ]
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", side_effect=responses
        ) as network:
            code, output, _ = self.run_command(["status", "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        self.assertEqual([x["download_ready"] for x in json.loads(output)["results"]], [True, False])
        self.assertEqual([call.args[0].full_url for call in network.call_args_list],
                         ["https://noiz.ai/v1/text-to-music/song-1", "https://noiz.ai/v1/text-to-music/song-2"])
        self.assertNotIn("cdn.example.com", output)

    def test_cover_uses_authorized_source_url_and_task_status(self):
        self.write_request({"kind": "cover", "source_audio_url": "https://example.com/source.mp3",
                            "lyrics": "New words", "style": "acoustic", "melody_adherence": "main_melody"})
        submission = FakeResponse({"code": 0, "data": {"task_id": "cover-123"}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", return_value=submission
        ) as network:
            code, _, _ = self.run_command(["submit", "--request", str(self.request), "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        sent = network.call_args.args[0]
        self.assertEqual(sent.full_url, "https://noiz.ai/v1/text-to-music/cover")
        self.assertEqual(parse.parse_qs(sent.data.decode())["source_audio_url"], ["https://example.com/source.mp3"])
        self.assertNotIn("source.mp3", self.task.read_text())
        response = FakeResponse({"code": 0, "data": {"stage": "done", "results": [
            {"status": "succeeded", "audio_url": "https://cdn.example.com/cover.mp3"}
        ]}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", return_value=response
        ) as network:
            code, output, _ = self.run_command(["status", "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["stage"], "done")
        self.assertTrue(network.call_args.args[0].full_url.endswith("/text-to-music/cover/cover-123"))

    def test_timeout_keeps_unconfirmed_record_and_never_retries(self):
        self.write_request({"kind": "effect", "prompt": "A door closes."})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", side_effect=TimeoutError()
        ) as network:
            code, _, err = self.run_command(["submit", "--request", str(self.request), "--task-file", str(self.task)])
        self.assertEqual(code, 1)
        network.assert_called_once()
        self.assertIn("勿自动重复提交", err)
        self.assertEqual(json.loads(self.task.read_text())["state"], "submission_unconfirmed")
        with mock.patch.object(noiz, "open_request") as network:
            code, _, _ = self.run_command(["status", "--task-file", str(self.task)])
        self.assertEqual(code, 1)
        network.assert_not_called()

    def test_existing_task_file_is_not_overwritten(self):
        self.write_request({"kind": "effect", "prompt": "A door closes."})
        self.task.write_text("keep this")
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(noiz, "open_request") as network:
            code, _, _ = self.run_command(["submit", "--request", str(self.request), "--task-file", str(self.task)])
        self.assertEqual(code, 1)
        self.assertEqual(self.task.read_text(), "keep this")
        network.assert_not_called()

    def test_download_sends_no_api_key_and_preserves_existing_output(self):
        self.task.write_text(json.dumps({"provider": "Noiz", "kind": "effect", "state": "completed",
                                         "result_urls": ["https://cdn.example.com/effect.wav"]}))
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            noiz, "open_request", return_value=FakeResponse(b"audio-bytes")
        ) as network:
            code, _, _ = self.run_command(["download", "--task-file", str(self.task), "--output", str(self.output)])
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), b"audio-bytes")
        self.assertIsNone(network.call_args.args[0].get_header("Authorization"))
        with mock.patch.object(noiz, "open_request") as network:
            code, _, _ = self.run_command(["download", "--task-file", str(self.task), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), b"audio-bytes")
        network.assert_not_called()

    def test_download_rejects_nonpublic_result_url(self):
        self.task.write_text(json.dumps({"provider": "Noiz", "kind": "effect", "state": "completed",
                                         "result_urls": ["https://127.0.0.1/private"]}))
        with mock.patch.object(noiz, "open_request") as network:
            code, _, _ = self.run_command(["download", "--task-file", str(self.task), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertFalse(self.output.exists())
        network.assert_not_called()

    def test_download_rejects_an_html_error_page(self):
        self.task.write_text(json.dumps({"provider": "Noiz", "kind": "effect", "state": "completed",
                                         "result_urls": ["https://cdn.example.com/expired"]}))
        response = FakeResponse(b"<html>expired</html>")
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        with mock.patch.object(noiz, "open_request", return_value=response):
            code, _, _ = self.run_command(["download", "--task-file", str(self.task), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertFalse(self.output.exists())

    def test_authorization_is_not_forwarded_through_redirects(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
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
            with mock.patch.object(noiz, "BASE", f"http://127.0.0.1:{server.server_port}"), mock.patch.dict(
                os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
            ):
                with self.assertRaises(noiz.ServiceError):
                    noiz.api_call("POST", "/start", "test-secret", b"prompt=test")
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual(seen, ["/start"])


if __name__ == "__main__":
    unittest.main()
