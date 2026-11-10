#!/usr/bin/env python3
"""Use the optional Sume image and video APIs."""

import argparse
import datetime
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from urllib import error, parse, request


BASE = "https://api.sume.com"
MAX_RESPONSE = 1024 * 1024
MAX_UPLOAD = 2 * 1024 * 1024 * 1024
ROUTES = {"image": "/v1/image-router", "video": "/v1/video-router"}


class ServiceError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(req, timeout):
    return request.build_opener(NoRedirect()).open(req, timeout=timeout)


def api_key():
    key = os.environ.get("SUME_API_KEY", "")
    if not key or key != key.strip() or "\r" in key or "\n" in key:
        raise ValueError("请通过环境变量 SUME_API_KEY 提供有效的服务密钥。")
    return key


def https_url(value):
    if not isinstance(value, str):
        return False
    try:
        parts = parse.urlsplit(value)
        return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False


def prepare(kind, path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("请求文件必须是 JSON 对象。")
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("请求需要非空的 model。")
    prompt = payload.get("prompt")
    if kind == "image" and (not isinstance(prompt, str) or not prompt.strip()):
        raise ValueError("图片请求需要非空的 prompt。")
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
        raise ValueError("prompt 必须是非空文字。")
    if payload.get("mode", "async") != "async" or "webhook_url" in payload:
        raise ValueError("此客户端只处理不带回调的异步任务。")
    if "duration" in payload and (
        not isinstance(payload["duration"], int) or isinstance(payload["duration"], bool)
    ):
        raise ValueError("duration 必须是整数；可用范围取决于所选模型。")
    single = ("image_url", "end_image_url", "video_url", "audio_url", "mask_url")
    multiple = ("image_urls", "reference_image_urls", "reference_video_urls", "reference_audio_urls")
    for field in single:
        if field in payload and not https_url(payload[field]):
            raise ValueError(field + " 需要可访问的 HTTPS 地址。")
    for field in multiple:
        if field in payload and (
            not isinstance(payload[field], list)
            or not payload[field]
            or any(not https_url(item) for item in payload[field])
        ):
            raise ValueError(field + " 需要非空的 HTTPS 地址列表。")
    if kind == "video" and "end_image_url" in payload and "image_url" not in payload:
        raise ValueError("视频尾帧需要同时提供首帧。")
    normalized = dict(payload)
    normalized.setdefault("mode", "async")
    body = json.dumps(normalized, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    summary = {
        "kind": kind,
        "model": model,
        "mode": "async",
        "duration": payload.get("duration"),
        "resolution": payload.get("resolution"),
        "aspect_ratio": payload.get("aspect_ratio"),
        "reference_counts": {field: len(payload[field]) for field in multiple if field in payload},
    }
    return body, summary


def api_call(method, path, key, body=None, idempotency=None):
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if idempotency is not None:
        headers["Idempotency-Key"] = idempotency
    req = request.Request(BASE + path, data=body, method=method, headers=headers)
    try:
        with open_request(req, timeout=45) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ServiceError("服务返回 HTTP " + str(code) + "。") from None
    except (error.URLError, TimeoutError, OSError):
        raise ServiceError("连接失败或超时。") from None
    if len(raw) > MAX_RESPONSE:
        raise ServiceError("服务响应过大。")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError("服务没有返回有效的 JSON。") from None
    if not isinstance(result, dict) or "data" not in result:
        raise ServiceError("服务未确认请求成功，请检查服务控制台。")
    return result


def record_bytes(record):
    return (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def create_record(path, record):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    data = record_bytes(record)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return data


def update_record(path, expected, record):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise ValueError("任务记录发生变化，未覆盖它。")
    fd, temporary = tempfile.mkstemp(prefix=".sume-task-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(record_bytes(record))
            output.flush()
            os.fsync(output.fileno())
        if path.is_symlink() or path.read_bytes() != expected:
            raise ValueError("任务记录发生变化，未覆盖它。")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def job_id_from_result(result):
    data = result.get("data")
    if not isinstance(data, dict):
        raise ServiceError("服务响应缺少任务数据。")
    job = data.get("job")
    job_id = job.get("id") if isinstance(job, dict) else None
    job_id = job_id or data.get("job_id") or data.get("request_id")
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", job_id):
        raise ServiceError("服务响应缺少有效的任务编号。")
    return job_id


def submit_request(kind, body, task_file, key, existing=None):
    if existing is None:
        record = {
            "provider": "Sume",
            "kind": kind,
            "state": "submission_unconfirmed",
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "idempotency_key": uuid.uuid4().hex,
            "job_id": None,
            "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        expected = create_record(task_file, record)
    else:
        expected, record = existing
    try:
        result = api_call("POST", ROUTES[kind] + "/generate", key, body, record["idempotency_key"])
        job_id = job_id_from_result(result)
        updated = dict(record, state="submitted", job_id=job_id)
        try:
            update_record(task_file, expected, updated)
        except (OSError, ValueError):
            print("任务已创建，任务编号：" + job_id + "；记录文件未更新。", file=sys.stderr)
            raise
    except (ServiceError, OSError, ValueError):
        print("提交结果可能未知；先检查任务记录、工作区和服务控制台，勿自动重复提交。", file=sys.stderr)
        raise
    return {"job_id": job_id, "task_file": str(task_file)}


def safe_upload_url(value):
    if not https_url(value):
        return False
    parts = parse.urlsplit(value)
    if parts.fragment:
        return False
    host = parts.hostname.casefold()
    if host == "localhost" or host.endswith(".localhost") or "." not in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    try:
        return parts.port in (None, 443)
    except ValueError:
        return False


def upload_file(path, content_type, key):
    if not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type or ""):
        raise ValueError("请提供有效的媒体 MIME 类型。")
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_UPLOAD:
            raise ValueError("上传文件必须是非空普通文件，且不能超过 2 GiB。")
        body = json.dumps({"content_type": content_type, "size_bytes": before.st_size, "filename": path.name}, ensure_ascii=False).encode("utf-8")
        result = api_call("POST", "/v1/files/generate-upload-url", key, body)
        data = result.get("data")
        if not isinstance(data, dict):
            raise ServiceError("服务未返回上传信息。")
        upload_url, public_url = data.get("upload_url"), data.get("public_url")
        if not safe_upload_url(upload_url) or not https_url(public_url) or parse.urlsplit(public_url).hostname.casefold() != "media.sume.com":
            raise ServiceError("服务返回的素材地址不符合安全要求。")
        if data.get("upload_method") != "PUT" or not isinstance(data.get("upload_headers"), dict):
            raise ServiceError("服务返回的上传方式不受支持。")
        headers = {}
        for name, value in data["upload_headers"].items():
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]+", name) or not isinstance(value, str) or "\r" in value or "\n" in value:
                raise ServiceError("服务返回的上传头无效。")
            if name.casefold() in ("authorization", "x-api-key", "proxy-authorization", "cookie", "host", "connection", "transfer-encoding"):
                raise ServiceError("服务返回了不允许的上传头。")
            headers[name] = value
        lower = {name.casefold(): value for name, value in headers.items()}
        if lower.get("content-type", "").casefold() != content_type.casefold() or lower.get("content-length") != str(before.st_size):
            raise ServiceError("上传头与本地文件不一致。")
        current = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
            raise ValueError("文件在准备上传时发生变化。")
        try:
            req = request.Request(upload_url, data=source, method="PUT", headers=headers)
            with open_request(req, timeout=90) as response:
                response.read(1024)
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ServiceError("素材上传返回 HTTP " + str(code) + "。") from None
        except (error.URLError, TimeoutError, OSError, ValueError):
            raise ServiceError("素材上传失败或结果未确认。") from None
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("文件在上传期间发生变化，请核对服务端素材。")
        return {"asset_id": data.get("asset_id"), "public_url": public_url}


def read_record(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("任务记录不存在或不是普通文件。")
    raw = path.read_bytes()
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("provider") != "Sume":
        raise ValueError("任务记录不属于此服务。")
    return raw, record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="查询当前账号可用模型")
    catalog.add_argument("--kind", choices=tuple(ROUTES), required=True)
    preview = commands.add_parser("preview", help="离线检查请求")
    preview.add_argument("--kind", choices=tuple(ROUTES), required=True)
    preview.add_argument("--request", type=Path, required=True)
    submit = commands.add_parser("submit", help="提交任务，可能产生费用")
    submit.add_argument("--kind", choices=tuple(ROUTES), required=True)
    submit.add_argument("--request", type=Path, required=True)
    submit.add_argument("--task-file", type=Path, required=True)
    resume = commands.add_parser("resume", help="恢复未确认的提交")
    resume.add_argument("--request", type=Path, required=True)
    resume.add_argument("--task-file", type=Path, required=True)
    resume.add_argument("--confirm-same-workspace", action="store_true", required=True)
    upload = commands.add_parser("upload", help="上传用户授权的本地素材")
    upload.add_argument("--file", type=Path, required=True)
    upload.add_argument("--content-type")
    for action in ("status", "result"):
        command = commands.add_parser(action, help="查询任务" if action == "status" else "读取生成结果")
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--task-file", type=Path)
        source.add_argument("--job-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "preview":
            _, summary = prepare(args.kind, args.request)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if args.command == "catalog":
            result = api_call("GET", ROUTES[args.kind] + "/models", api_key())
        elif args.command == "upload":
            content_type = args.content_type or mimetypes.guess_type(args.file.name)[0]
            result = upload_file(args.file, content_type, api_key())
        elif args.command == "submit":
            body, _ = prepare(args.kind, args.request)
            result = submit_request(args.kind, body, args.task_file, api_key())
        elif args.command == "resume":
            raw, record = read_record(args.task_file)
            kind = record.get("kind")
            if kind not in ROUTES or record.get("state") != "submission_unconfirmed" or record.get("job_id") is not None:
                raise ValueError("该任务不处于可恢复的未确认状态。")
            idem = record.get("idempotency_key")
            if not isinstance(idem, str) or not re.fullmatch(r"[a-f0-9]{32}", idem):
                raise ValueError("任务记录缺少有效的请求标识。")
            body, _ = prepare(kind, args.request)
            if hashlib.sha256(body).hexdigest() != record.get("request_sha256"):
                raise ValueError("请求内容已改变；不会重发原任务。")
            result = submit_request(kind, body, args.task_file, api_key(), existing=(raw, record))
        else:
            if args.task_file:
                _, record = read_record(args.task_file)
                job_id = record.get("job_id")
            else:
                job_id = args.job_id
            if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", job_id):
                raise ValueError("没有可查询的有效任务编号。")
            result = api_call("GET", "/v1/jobs/" + parse.quote(job_id, safe="") + "/" + args.command, api_key())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ServiceError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
