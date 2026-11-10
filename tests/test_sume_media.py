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


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sume_media.py"
SPEC = importlib.util.spec_from_file_location("sume_media", SCRIPT)
sume = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sume)


class FakeResponse:
    def __init__(self, payload=None):
        self.body = json.dumps(payload or {}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.body[:limit]


class SumeMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.request_file = self.root / "request.json"
        self.task_file = self.root / "task.json"
        self.write_request({"model": "seedance-2.5", "prompt": "A cup turns slowly.", "duration": 5})

    def write_request(self, payload):
        self.request_file.write_text(json.dumps(payload))

    def run_command(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sume.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_preview_is_offline_and_rejects_a_lone_last_frame(self):
        with mock.patch.object(sume, "open_request") as network:
            code, out, _ = self.run_command(["preview", "--kind", "video", "--request", str(self.request_file)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["model"], "seedance-2.5")
            self.write_request({"model": "seedance-2.5", "end_image_url": "https://example.com/end.png"})
            code, _, _ = self.run_command(["preview", "--kind", "video", "--request", str(self.request_file)])
            self.assertEqual(code, 1)
        network.assert_not_called()

    def test_submit_records_one_job_without_saving_the_key(self):
        response = FakeResponse({"data": {"job": {"id": "job_123", "status": "queued"}}})
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(
            sume, "open_request", return_value=response
        ) as network:
            code, out, _ = self.run_command([
                "submit", "--kind", "video", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["job_id"], "job_123")
        self.assertEqual(network.call_count, 1)
        req = network.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.sume.com/v1/video-router/generate")
        self.assertEqual(json.loads(req.data)["mode"], "async")
        headers = {key.casefold(): value for key, value in req.header_items()}
        saved = self.task_file.read_text()
        self.assertEqual(headers["idempotency-key"], json.loads(saved)["idempotency_key"])
        self.assertNotIn("test-secret", saved)
        self.assertEqual(stat.S_IMODE(self.task_file.stat().st_mode), 0o600)

    def test_timeout_and_resume_use_the_same_idempotency_key_and_body(self):
        seen = []

        def fake(req, timeout):
            headers = {key.casefold(): value for key, value in req.header_items()}
            seen.append((req.data, headers["idempotency-key"]))
            if len(seen) == 1:
                raise TimeoutError()
            return FakeResponse({"data": {"request_id": "job_recovered"}})

        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(sume, "open_request", side_effect=fake):
            first, _, _ = self.run_command([
                "submit", "--kind", "video", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
            self.assertEqual(json.loads(self.task_file.read_text())["state"], "submission_unconfirmed")
            second, _, _ = self.run_command([
                "resume", "--request", str(self.request_file), "--task-file", str(self.task_file), "--confirm-same-workspace"
            ])
        self.assertEqual((first, second), (1, 0))
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(json.loads(self.task_file.read_text())["job_id"], "job_recovered")

    def test_resume_refuses_changed_request_before_network(self):
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(
            sume, "open_request", side_effect=TimeoutError()
        ):
            code, _, _ = self.run_command([
                "submit", "--kind", "video", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(code, 1)
        self.write_request({"model": "seedance-2.5", "prompt": "Different prompt."})
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(sume, "open_request") as network:
            code, _, _ = self.run_command([
                "resume", "--request", str(self.request_file), "--task-file", str(self.task_file), "--confirm-same-workspace"
            ])
        self.assertEqual(code, 1)
        network.assert_not_called()

    def test_existing_task_record_is_not_overwritten(self):
        self.task_file.write_text("keep this")
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(sume, "open_request") as network:
            code, _, _ = self.run_command([
                "submit", "--kind", "video", "--request", str(self.request_file), "--task-file", str(self.task_file)
            ])
        self.assertEqual(code, 1)
        self.assertEqual(self.task_file.read_text(), "keep this")
        network.assert_not_called()

    def test_catalog_and_result_use_fixed_api_paths(self):
        response = FakeResponse({"data": {"status": "COMPLETED"}})
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(
            sume, "open_request", return_value=response
        ) as network:
            code, _, _ = self.run_command(["catalog", "--kind", "image"])
            self.assertEqual(code, 0)
            self.assertEqual(network.call_args.args[0].full_url, "https://api.sume.com/v1/image-router/models")
            code, _, _ = self.run_command(["result", "--job-id", "job_123"])
            self.assertEqual(code, 0)
            self.assertEqual(network.call_args.args[0].full_url, "https://api.sume.com/v1/jobs/job_123/result")

    def test_upload_sends_bytes_without_the_service_key(self):
        image = self.root / "image.png"
        image.write_bytes(b"example-image")
        data = {
            "upload_method": "PUT",
            "upload_url": "https://storage.example.com/signed?token=private",
            "public_url": "https://media.sume.com/assets/asset_1/source.png",
            "asset_id": "asset_1",
            "upload_headers": {"content-type": "image/png", "content-length": str(image.stat().st_size)},
        }
        seen = []

        def fake(req, timeout):
            headers = {key.casefold(): value for key, value in req.header_items()}
            if req.get_method() == "POST":
                seen.append(("POST", headers, json.loads(req.data)))
                return FakeResponse({"data": data})
            seen.append(("PUT", headers, req.data.read()))
            return FakeResponse()

        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(sume, "open_request", side_effect=fake):
            code, out, _ = self.run_command(["upload", "--file", str(image)])
        self.assertEqual(code, 0)
        self.assertEqual([item[0] for item in seen], ["POST", "PUT"])
        self.assertEqual(seen[0][1]["authorization"], "Bearer test-secret")
        self.assertNotIn("authorization", seen[1][1])
        self.assertEqual(seen[1][2], b"example-image")
        self.assertNotIn("token=private", out)
        self.assertEqual(json.loads(out)["asset_id"], "asset_1")

    def test_upload_rejects_unexpected_authorization_header(self):
        image = self.root / "image.png"
        image.write_bytes(b"x")
        data = {
            "upload_method": "PUT",
            "upload_url": "https://storage.example.com/signed",
            "public_url": "https://media.sume.com/assets/a/source.png",
            "upload_headers": {"authorization": "unexpected", "content-type": "image/png", "content-length": "1"},
        }
        with mock.patch.dict(os.environ, {"SUME_API_KEY": "test-secret"}), mock.patch.object(
            sume, "open_request", return_value=FakeResponse({"data": data})
        ) as network:
            code, _, _ = self.run_command(["upload", "--file", str(image)])
        self.assertEqual(code, 1)
        self.assertEqual(network.call_count, 1)

    def test_upload_streams_the_file_without_authentication_to_storage(self):
        image = self.root / "image.png"
        image.write_bytes(b"streamed-media")
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_PUT(self):
                length = int(self.headers["Content-Length"])
                seen.append((self.headers.get("Authorization"), self.rfile.read(length)))
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        data = {
            "upload_method": "PUT",
            "upload_url": f"http://127.0.0.1:{server.server_port}/upload",
            "public_url": "https://media.sume.com/assets/a/source.png",
            "asset_id": "asset_a",
            "upload_headers": {"content-type": "image/png", "content-length": str(image.stat().st_size)},
        }
        try:
            with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}), mock.patch.object(
                sume, "api_call", return_value={"data": data}
            ), mock.patch.object(sume, "safe_upload_url", return_value=True):
                result = sume.upload_file(image, "image/png", "test-secret")
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual(result["asset_id"], "asset_a")
        self.assertEqual(seen, [(None, b"streamed-media")])

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
            with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}), mock.patch.object(
                sume, "BASE", f"http://127.0.0.1:{server.server_port}"
            ):
                with self.assertRaises(sume.ServiceError):
                    sume.api_call("GET", "/start", "test-secret")
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.assertEqual(seen, ["/start"])


if __name__ == "__main__":
    unittest.main()
