import contextlib
import email.policy
import email.parser
import http.server
import importlib.util
import io
import json
import os
import stat
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock
from urllib import parse


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "noiz_voice.py"
SPEC = importlib.util.spec_from_file_location("noiz_voice", SCRIPT)
voice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice)


class FakeResponse:
    def __init__(self, value, content_type="application/json"):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.body = io.BytesIO(raw)
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()

    def read(self, size):
        return self.body.read(size)


def wave_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x00\x00" * 80)
    return buffer.getvalue()


def parts_of(sent):
    header = "Content-Type: " + sent.get_header("Content-type") + "\r\nMIME-Version: 1.0\r\n\r\n"
    message = email.parser.BytesParser(policy=email.policy.default).parsebytes(header.encode() + sent.data)
    if not message.is_multipart():
        raise AssertionError("Expected a multipart request")
    return {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}


class NoizVoiceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.request = self.root / "request.json"
        self.task = self.root / "task.json"
        self.output = self.root / "voice.wav"
        self.sample = self.root / "sample.wav"
        self.sample.write_bytes(wave_bytes())

    def write_request(self, value):
        self.request.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def run_command(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = voice.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def speech_request(self):
        return {"kind": "speech", "voice_id": "voice-123", "text": "欢迎了解产品。", "output_format": "wav"}

    def test_preview_for_speech_and_clone_is_offline_and_hides_content(self):
        requests = [self.speech_request(), {"kind": "clone", "audio_path": "sample.wav", "consent": True}]
        for payload in requests:
            with self.subTest(kind=payload["kind"]):
                self.write_request(payload)
                with mock.patch.object(voice, "open_request") as network:
                    code, output, _ = self.run_command(["preview", "--request", str(self.request)])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output)["kind"], payload["kind"])
                self.assertNotIn("欢迎了解产品", output)
                self.assertNotIn("sample.wav", output)
                network.assert_not_called()

    def test_invalid_requests_never_contact_service(self):
        requests = [
            {"kind": "clone", "audio_path": "sample.wav"},
            {"kind": "clone", "audio_path": "sample.wav", "consent": False},
            {"kind": "clone", "audio_path": "sample.wav", "voice_url": "https://example.com/a.wav", "consent": True},
            {"kind": "clone", "voice_url": "https://127.0.0.1/a.wav", "consent": True},
            {"kind": "speech", "voice_id": "abc", "text": "  "},
            {"kind": "speech", "voice_id": "abc", "text": "hello", "speed": True},
            {"kind": "speech", "voice_id": "abc", "text": "hello", "output_format": "ogg"},
            {"kind": "speech", "voice_id": "abc", "text": "hello", "api_key": "private"},
        ]
        for payload in requests:
            with self.subTest(payload=payload):
                self.write_request(payload)
                with mock.patch.object(voice, "open_request") as network:
                    code, _, _ = self.run_command(["preview", "--request", str(self.request)])
                self.assertEqual(code, 1)
                network.assert_not_called()

    def test_oversized_or_symlinked_reference_is_rejected(self):
        big = self.root / "large.wav"
        with big.open("wb") as sample:
            sample.truncate(voice.MAX_REFERENCE + 1)
        link = self.root / "link.wav"
        link.symlink_to(self.sample)
        for path in (big, link):
            with self.subTest(path=path.name):
                self.write_request({"kind": "clone", "audio_path": str(path), "consent": True})
                with mock.patch.object(voice, "open_request") as network:
                    code, _, _ = self.run_command(["preview", "--request", str(self.request)])
                self.assertEqual(code, 1)
                network.assert_not_called()

    def test_voice_list_uses_account_and_provider_parameters(self):
        response = FakeResponse({"code": 0, "data": {"total_count": 1, "voices": [
            {"voice_id": "built-in-1", "display_name": "Narrator", "voice_type": "built-in", "url": "private"}
        ]}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", return_value=response
        ) as network:
            code, output, _ = self.run_command(["voices", "--type", "built-in", "--limit", "5"])
        self.assertEqual(code, 0)
        sent = network.call_args.args[0]
        self.assertEqual(parse.urlsplit(sent.full_url).path, "/v1/voices")
        self.assertEqual(parse.parse_qs(parse.urlsplit(sent.full_url).query)["voice_type"], ["built-in"])
        self.assertEqual(sent.get_header("Authorization"), "test-secret")
        self.assertEqual(json.loads(output)["voices"][0]["voice_id"], "built-in-1")
        self.assertNotIn("private", output)
        self.assertNotIn("test-secret", output)

    def test_clone_uploads_authorized_local_file_and_saves_voice_id(self):
        self.write_request({"kind": "clone", "audio_path": "sample.wav", "consent": True,
                            "display_name": "My recording", "denoise": True})
        response = FakeResponse({"code": 0, "data": {"voice_id": "cloned-123"}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", return_value=response
        ) as network:
            code, output, _ = self.run_command([
                "clone", "--request", str(self.request), "--task-file", str(self.task)
            ])
        self.assertEqual(code, 0)
        sent = network.call_args.args[0]
        self.assertEqual(sent.full_url, "https://noiz.ai/v1/voices")
        self.assertEqual(sent.get_header("Authorization"), "test-secret")
        parts = parts_of(sent)
        self.assertEqual(parts["file"].get_payload(decode=True), self.sample.read_bytes())
        self.assertEqual(parts["file"].get_filename(), "voice-sample.wav")
        self.assertEqual(parts["denoise"].get_content().strip(), "true")
        self.assertNotIn("consent", parts)
        self.assertEqual(json.loads(output)["voice_id"], "cloned-123")
        saved = self.task.read_text()
        self.assertEqual(json.loads(saved)["state"], "completed")
        self.assertNotIn("test-secret", saved)
        self.assertNotIn("sample.wav", saved)
        self.assertEqual(stat.S_IMODE(self.task.stat().st_mode), 0o600)

    def test_clone_can_use_an_authorized_public_url(self):
        self.write_request({"kind": "clone", "voice_url": "https://example.com/authorized.wav?token=private",
                            "consent": True})
        response = FakeResponse({"code": 0, "data": {"voice_id": "custom-1"}})
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", return_value=response
        ) as network:
            code, _, _ = self.run_command(["clone", "--request", str(self.request), "--task-file", str(self.task)])
        self.assertEqual(code, 0)
        parts = parts_of(network.call_args.args[0])
        self.assertNotIn("file", parts)
        self.assertEqual(parts["voice_url"].get_content().strip(), "https://example.com/authorized.wav?token=private")
        self.assertNotIn("token=private", self.task.read_text())

    def test_speech_sends_multipart_and_streams_wav_without_saving_text(self):
        self.write_request(self.speech_request())
        audio = wave_bytes()
        response = FakeResponse(audio, "audio/wav")
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", return_value=response
        ) as network:
            code, output, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(self.output)
            ])
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), audio)
        self.assertEqual(json.loads(output)["bytes"], len(audio))
        sent = network.call_args.args[0]
        self.assertEqual(sent.full_url, "https://noiz.ai/v1/text-to-speech")
        parts = parts_of(sent)
        self.assertEqual(parts["text"].get_payload(decode=True).decode(), "欢迎了解产品。")
        self.assertEqual(parts["voice_id"].get_content().strip(), "voice-123")
        saved = self.task.read_text()
        self.assertEqual(json.loads(saved)["state"], "completed")
        self.assertNotIn("欢迎了解产品", saved)
        self.assertNotIn("test-secret", saved)
        self.assertEqual(stat.S_IMODE(self.task.stat().st_mode), 0o600)

    def test_speech_can_save_mp3(self):
        payload = self.speech_request()
        payload["output_format"] = "mp3"
        self.write_request(payload)
        output_path = self.root / "voice.mp3"
        audio = b"ID3" + bytes(30)
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", return_value=FakeResponse(audio, "audio/mpeg")
        ):
            code, _, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(output_path)
            ])
        self.assertEqual(code, 0)
        self.assertEqual(output_path.read_bytes(), audio)

    def test_rejects_html_and_wrong_audio_format_without_output(self):
        self.write_request(self.speech_request())
        for index, response in enumerate([FakeResponse(b"<html>expired</html>", "text/html"),
                                          FakeResponse(b"ID3" + bytes(30), "audio/mpeg")]):
            with self.subTest(index=index):
                task = self.root / f"task-{index}.json"
                with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
                    voice, "open_request", return_value=response
                ):
                    code, _, _ = self.run_command([
                        "speak", "--request", str(self.request), "--task-file", str(task), "--output", str(self.output)
                    ])
                self.assertEqual(code, 1)
                self.assertFalse(self.output.exists())
                self.assertEqual(json.loads(task.read_text())["state"], "submission_unconfirmed")

    def test_timeout_leaves_unconfirmed_task_without_retry(self):
        self.write_request(self.speech_request())
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", side_effect=TimeoutError()
        ) as network:
            code, _, err = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(self.output)
            ])
        self.assertEqual(code, 1)
        self.assertIn("勿自动重复提交", err)
        network.assert_called_once()
        self.assertFalse(self.output.exists())
        self.assertEqual(json.loads(self.task.read_text())["state"], "submission_unconfirmed")

    def test_existing_task_or_output_never_triggers_network(self):
        self.write_request(self.speech_request())
        self.output.write_bytes(b"do not replace")
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(voice, "open_request") as network:
            code, _, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(self.output)
            ])
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), b"do not replace")
        self.assertFalse(self.task.exists())
        network.assert_not_called()
        self.output.unlink()
        self.task.write_text("do not replace")
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(voice, "open_request") as network:
            code, _, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(self.output)
            ])
        self.assertEqual(code, 1)
        self.assertEqual(self.task.read_text(), "do not replace")
        network.assert_not_called()

    def test_task_and_output_cannot_be_the_same_path(self):
        self.write_request(self.speech_request())
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(voice, "open_request") as network:
            code, _, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.output), "--output", str(self.output)
            ])
        self.assertEqual(code, 1)
        self.assertFalse(self.output.exists())
        network.assert_not_called()

    def test_output_created_during_request_is_not_overwritten(self):
        self.write_request(self.speech_request())
        def competing_output(*args, **kwargs):
            self.output.write_bytes(b"new user file")
            return FakeResponse(wave_bytes(), "audio/wav")
        with mock.patch.dict(os.environ, {"NOIZ_API_KEY": "test-secret"}), mock.patch.object(
            voice, "open_request", side_effect=competing_output
        ):
            code, _, _ = self.run_command([
                "speak", "--request", str(self.request), "--task-file", str(self.task), "--output", str(self.output)
            ])
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), b"new user file")
        self.assertEqual(json.loads(self.task.read_text())["state"], "submission_unconfirmed")

    def test_no_authorization_forwarding_on_redirect(self):
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
            with mock.patch.object(voice, "BASE", f"http://127.0.0.1:{server.server_port}"), mock.patch.dict(
                os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1", "NOIZ_API_KEY": "test-secret"}
            ):
                with self.assertRaises(voice.ServiceError):
                    voice.list_voices("built-in", 0, 10)
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith("/voices?"))

    def test_clone_then_speak_over_local_http(self):
        seen = []
        audio = wave_bytes()
        sample = self.sample.read_bytes()
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                size = int(self.headers["Content-Length"])
                body = self.rfile.read(size)
                header = "Content-Type: " + self.headers["Content-Type"] + "\r\nMIME-Version: 1.0\r\n\r\n"
                message = email.parser.BytesParser(policy=email.policy.default).parsebytes(header.encode() + body)
                parts = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True)
                         for p in message.iter_parts()}
                seen.append((self.path, self.headers.get("Authorization"), parts))
                if self.path == "/voices":
                    result = json.dumps({"code": 0, "data": {"voice_id": "local-clone"}}).encode()
                    content_type = "application/json"
                else:
                    result = audio
                    content_type = "audio/wav"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(result)))
                self.end_headers()
                self.wfile.write(result)
            def log_message(self, format, *args):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with mock.patch.object(voice, "BASE", f"http://127.0.0.1:{server.server_port}"), mock.patch.dict(
                os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1", "NOIZ_API_KEY": "test-secret"}
            ):
                self.write_request({"kind": "clone", "audio_path": "sample.wav", "consent": True})
                code, output, _ = self.run_command([
                    "clone", "--request", str(self.request), "--task-file", str(self.task)
                ])
                self.assertEqual(code, 0)
                self.write_request({"kind": "speech", "voice_id": json.loads(output)["voice_id"],
                                    "text": "Hello", "output_format": "wav"})
                code, _, _ = self.run_command([
                    "speak", "--request", str(self.request), "--task-file", str(self.root / "speech.json"),
                    "--output", str(self.output)
                ])
                self.assertEqual(code, 0)
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual([item[0] for item in seen], ["/voices", "/text-to-speech"])
        self.assertEqual([item[1] for item in seen], ["test-secret", "test-secret"])
        self.assertEqual(seen[0][2]["file"], sample)
        self.assertEqual(seen[1][2]["voice_id"], b"local-clone")
        self.assertEqual(self.output.read_bytes(), audio)


if __name__ == "__main__":
    unittest.main()
