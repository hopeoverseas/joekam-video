#!/usr/bin/env python3
"""Preview and manage optional Noiz sound-effect and vocal-music tasks."""

import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib import error, parse, request


BASE = "https://noiz.ai/v1"
ROUTES = {"effect": "/text-to-sound", "music": "/text-to-music", "cover": "/text-to-music/cover"}
MAX_REQUEST = 256 * 1024
MAX_RESPONSE = 1024 * 1024
MAX_AUDIO = 200 * 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


class ServiceError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(req, timeout):
    return request.build_opener(NoRedirect()).open(req, timeout=timeout)


def public_https_url(value):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    try:
        parts = parse.urlsplit(value)
        host = (parts.hostname or "").casefold()
        if (parts.scheme != "https" or not host or parts.username or parts.password or parts.fragment
                or host == "localhost" or host.endswith(".localhost") or "." not in host
                or parts.port not in (None, 443)):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


def required_text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须是非空文字，最多 {limit} 字符。")


def prepare(path):
    path = Path(path)
    if path.stat().st_size > MAX_REQUEST:
        raise ValueError("请求文件过大。")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("请求文件必须是 JSON 对象。")
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in ROUTES:
        raise ValueError("kind 必须是 effect、music 或 cover。")
    fields_by_kind = {
        "effect": {"prompt", "duration", "output_format"},
        "music": {"prompt", "lyrics", "lyrics_prompt", "title", "tags", "negative_tags",
                  "vocal_gender", "reference_audio_url"},
        "cover": {"source_audio_url", "lyrics", "music_description", "style", "melody_adherence",
                  "title", "vocal_gender"},
    }
    unknown = set(payload) - fields_by_kind[kind] - {"kind"}
    if unknown:
        raise ValueError("不支持的请求字段：" + ", ".join(sorted(unknown)))
    fields = {key: value for key, value in payload.items() if key != "kind"}
    if kind == "effect":
        required_text(fields.get("prompt"), "prompt", 500)
        if "duration" in fields and (type(fields["duration"]) is not int or not 1 <= fields["duration"] <= 30):
            raise ValueError("音效 duration 必须是 1 至 30 的整数秒。")
        if fields.get("output_format", "wav") not in ("wav", "mp3"):
            raise ValueError("output_format 必须是 wav 或 mp3。")
        fields.setdefault("output_format", "wav")
    elif kind == "music":
        required_text(fields.get("prompt"), "prompt", 1500)
        choices = [name for name in ("lyrics", "lyrics_prompt") if name in fields]
        if len(choices) != 1:
            raise ValueError("歌曲需要 lyrics 或 lyrics_prompt，且只能选择一个。")
        required_text(fields[choices[0]], choices[0], 5000)
    else:
        if not public_https_url(fields.get("source_audio_url")):
            raise ValueError("翻唱需要可由服务访问的 HTTPS source_audio_url。")
        required_text(fields.get("lyrics"), "lyrics", 5000)
        if fields.get("melody_adherence") not in ("high", "main_melody"):
            raise ValueError("melody_adherence 必须是 high 或 main_melody。")
        if not any(name in fields for name in ("music_description", "style")):
            raise ValueError("翻唱需要 music_description 或 style。")
    limits = {"title": 80, "tags": 50, "negative_tags": 50, "style": 50, "music_description": 1500}
    for name, limit in limits.items():
        if name in fields:
            required_text(fields[name], name, limit)
    if "vocal_gender" in fields and fields["vocal_gender"] not in ("Male", "Female"):
        raise ValueError("vocal_gender 必须是 Male 或 Female。")
    if "reference_audio_url" in fields and not public_https_url(fields["reference_audio_url"]):
        raise ValueError("reference_audio_url 需要可由服务访问的 HTTPS 地址。")
    body = parse.urlencode(fields).encode("utf-8")
    summary = {"kind": kind, "fields": sorted(fields), "uses_reference_audio":
               "source_audio_url" in fields or "reference_audio_url" in fields}
    return kind, body, summary


def api_key():
    key = os.environ.get("NOIZ_API_KEY", "")
    if not key or key != key.strip() or "\r" in key or "\n" in key:
        raise ValueError("请通过环境变量 NOIZ_API_KEY 提供服务密钥。")
    return key


def api_call(method, path, key, body=None):
    headers = {"Authorization": key}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        timeout = 45
        if method == "POST":
            timeout = {ROUTES["cover"]: 300, ROUTES["music"]: 180}.get(path, 120)
        with open_request(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ServiceError(f"服务返回 HTTP {code}。") from None
    except (error.URLError, TimeoutError, OSError):
        raise ServiceError("连接失败或超时。") from None
    if len(raw) > MAX_RESPONSE:
        raise ServiceError("服务响应过大。")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError("服务没有返回有效的 JSON。") from None
    if not isinstance(result, dict) or type(result.get("code")) is not int or result["code"] != 0:
        raise ServiceError("服务未确认请求成功，请检查服务控制台。")
    if not isinstance(result.get("data"), dict):
        raise ServiceError("服务响应缺少任务数据。")
    return result["data"]


def record_bytes(record):
    return (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def create_record(path, record):
    data = record_bytes(record)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return data


def update_record(path, expected, record):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise ValueError("任务记录发生变化，未覆盖它。")
    fd, temporary = tempfile.mkstemp(prefix=".noiz-task-", dir=path.parent)
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


def safe_id(value):
    if type(value) is int and value >= 0:
        value = str(value)
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ServiceError("服务响应缺少有效的任务编号。")
    return value


def submit(kind, body, path, key):
    record = {"provider": "Noiz", "kind": kind, "state": "submission_unconfirmed",
              "request_sha256": hashlib.sha256(body).hexdigest(),
              "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    expected = create_record(path, record)
    try:
        data = api_call("POST", ROUTES[kind], key, body)
        if kind == "effect":
            results = data.get("results")
            if not isinstance(results, list):
                raise ServiceError("服务未返回音效结果。")
            urls = [item.get("file_url") for item in results if isinstance(item, dict)
                    and not item.get("error") and public_https_url(item.get("file_url"))]
            if not urls:
                raise ServiceError("服务未返回可下载的音效地址。")
            updated = dict(record, state="completed", result_urls=urls)
            identifiers = len(urls)
        elif kind == "music":
            results = data.get("results")
            if not isinstance(results, list) or not results:
                raise ServiceError("服务未返回歌曲任务。")
            ids = [safe_id(item.get("gen_product_id")) for item in results if isinstance(item, dict)
                   and item.get("gen_product_id") is not None]
            if not ids:
                raise ServiceError("服务未返回歌曲任务编号。")
            updated = dict(record, state="submitted", job_ids=ids)
            identifiers = len(ids)
        else:
            task_id = safe_id(data.get("task_id"))
            updated = dict(record, state="submitted", task_id=task_id)
            identifiers = 1
        try:
            update_record(path, expected, updated)
        except (OSError, ValueError):
            if kind == "music":
                print("服务已返回任务编号：" + ", ".join(ids), file=sys.stderr)
            elif kind == "cover":
                print("服务已返回任务编号：" + task_id, file=sys.stderr)
            raise
    except (ServiceError, OSError, ValueError):
        print("提交结果可能未知；先检查任务记录和服务控制台，勿自动重复提交。", file=sys.stderr)
        raise
    return {"kind": kind, "state": updated["state"], "count": identifiers, "task_file": str(path)}


def load_record(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RESPONSE:
        raise ValueError("任务记录不存在或不可用。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("provider") != "Noiz"
            or not isinstance(data.get("kind"), str) or data["kind"] not in ROUTES):
        raise ValueError("不是有效的任务记录。")
    if data.get("state") == "submission_unconfirmed":
        raise ValueError("提交结果未确认；请先检查服务控制台，勿自动重复提交。")
    return data


def results_for(record):
    kind = record["kind"]
    if kind == "effect":
        urls = record.get("result_urls")
        if record.get("state") != "completed" or not isinstance(urls, list) or not urls:
            raise ValueError("音效记录没有可用结果。")
        return [{"status": "succeeded", "audio_url": value} for value in urls], None
    if record.get("state") != "submitted":
        raise ValueError("任务记录状态不可查询。")
    key = api_key()
    if kind == "music":
        ids = record.get("job_ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError("歌曲任务记录缺少编号。")
        return [api_call("GET", ROUTES[kind] + "/" + safe_id(value), key) for value in ids], None
    data = api_call("GET", ROUTES[kind] + "/" + safe_id(record.get("task_id")), key)
    results = data.get("results", [])
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise ServiceError("服务返回的翻唱结果格式无效。")
    return results, data.get("stage")


def status(record):
    results, stage = results_for(record)
    return {"kind": record["kind"], "stage": stage,
            "results": [{"variant": i + 1, "status": item.get("status", "unknown"),
                         "download_ready": item.get("status") == "succeeded"
                         and public_https_url(item.get("audio_url"))}
                        for i, item in enumerate(results)]}


def download(record, variant, destination):
    results, _ = results_for(record)
    if variant < 1 or variant > len(results):
        raise ValueError("结果序号不存在。")
    selected = results[variant - 1]
    url = selected.get("audio_url")
    if selected.get("status") != "succeeded" or not public_https_url(url):
        raise ValueError("该结果尚未就绪，或下载地址不可用。")
    if os.path.lexists(destination):
        raise ValueError("输出文件已存在，未覆盖。")
    fd, temporary = tempfile.mkstemp(prefix=".noiz-audio-", dir=destination.parent)
    try:
        req = request.Request(url, method="GET")
        with os.fdopen(fd, "wb") as output:
            try:
                with open_request(req, timeout=120) as response:
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
                    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
                        raise ServiceError("下载地址返回了文本，而不是音频文件。")
                    total = 0
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_AUDIO:
                            raise ServiceError("音频文件超过下载大小限制。")
                        output.write(block)
            except error.HTTPError as exc:
                code = exc.code
                exc.close()
                raise ServiceError(f"下载返回 HTTP {code}。") from None
            except (error.URLError, TimeoutError, OSError):
                raise ServiceError("音频下载失败或超时。") from None
            if not total:
                raise ServiceError("服务返回了空音频文件。")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"output": str(destination), "bytes": total}


def main(argv=None):
    parser = argparse.ArgumentParser(description="预览和管理可选的音效、歌曲及翻唱任务。")
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("--request", required=True)
    send = commands.add_parser("submit")
    send.add_argument("--request", required=True)
    send.add_argument("--task-file", required=True)
    check = commands.add_parser("status")
    check.add_argument("--task-file", required=True)
    get = commands.add_parser("download")
    get.add_argument("--task-file", required=True)
    get.add_argument("--variant", type=int, default=1)
    get.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("preview", "submit"):
            kind, body, summary = prepare(args.request)
            result = summary if args.command == "preview" else submit(kind, body, Path(args.task_file), api_key())
        else:
            record = load_record(Path(args.task_file))
            result = status(record) if args.command == "status" else download(record, args.variant, Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ServiceError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
