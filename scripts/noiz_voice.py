#!/usr/bin/env python3
"""Prepare optional Noiz speech and consented voice-cloning requests."""

import argparse
import datetime
import hashlib
import http.client
import ipaddress
import json
import math
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from urllib import error, parse, request


BASE = "https://noiz.ai/v1"
MAX_REQUEST = 128 * 1024
MAX_JSON = 1024 * 1024
MAX_REFERENCE = 25 * 1024 * 1024
MAX_AUDIO = 200 * 1024 * 1024
MEDIA_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}


class ServiceError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(req, timeout):
    return request.build_opener(NoRedirect()).open(req, timeout=timeout)


def public_https_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    try:
        parts = parse.urlsplit(value)
        host = (parts.hostname or "").casefold()
        if (parts.scheme != "https" or not host or "." not in host or parts.username or parts.password
                or parts.fragment or host == "localhost" or host.endswith(".localhost")
                or parts.port not in (None, 443)):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


def text_value(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须是非空文字，最多 {limit} 字符。")


def reference_info(path):
    suffix = path.suffix.lower()
    if suffix not in MEDIA_TYPES or path.is_symlink():
        raise ValueError("参考音频须为 WAV、MP3 或 M4A 文件，且不能是符号链接。")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_REFERENCE:
        raise ValueError("参考音频须为非空文件，且不超过 25 MiB。")
    return info


def prepare(path):
    path = Path(path)
    if path.stat().st_size > MAX_REQUEST:
        raise ValueError("请求文件过大。")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("kind") not in ("speech", "clone"):
        raise ValueError("请求 kind 必须是 speech 或 clone。")
    kind = payload["kind"]
    allowed = {
        "speech": {"kind", "text", "voice_id", "output_format", "speed", "target_lang", "trim_silence"},
        "clone": {"kind", "audio_path", "voice_url", "display_name", "denoise", "language", "consent"},
    }
    unknown = set(payload) - allowed[kind]
    if unknown:
        raise ValueError("不支持的请求字段：" + ", ".join(sorted(unknown)))
    fields = {key: value for key, value in payload.items() if key not in ("kind", "audio_path", "consent")}
    reference = None
    if kind == "speech":
        text_value(fields.get("text"), "text", 5000)
        text_value(fields.get("voice_id"), "voice_id", 200)
        if any(ord(c) < 32 or ord(c) == 127 for c in fields["voice_id"]):
            raise ValueError("voice_id 不能包含控制字符。")
        fields.setdefault("output_format", "wav")
        if fields["output_format"] not in ("wav", "mp3"):
            raise ValueError("output_format 必须是 wav 或 mp3。")
        if "speed" in fields:
            value = fields["speed"]
            try:
                valid_speed = type(value) in (int, float) and math.isfinite(value) and value > 0
            except OverflowError:
                valid_speed = False
            if not valid_speed:
                raise ValueError("speed 必须是大于 0 的有限数字。")
        if "trim_silence" in fields and type(fields["trim_silence"]) is not bool:
            raise ValueError("trim_silence 必须是布尔值。")
        if "target_lang" in fields:
            text_value(fields["target_lang"], "target_lang", 100)
    else:
        if payload.get("consent") is not True:
            raise ValueError("克隆前需取得声音本人授权，并将 consent 设为 true。")
        if ("audio_path" in payload) == ("voice_url" in payload):
            raise ValueError("克隆请求须且只能提供 audio_path 或 voice_url。")
        if "audio_path" in payload:
            text_value(payload["audio_path"], "audio_path", 4096)
            reference = Path(payload["audio_path"])
            if not reference.is_absolute():
                reference = path.parent / reference
            reference_info(reference)
        elif not public_https_url(fields["voice_url"]):
            raise ValueError("voice_url 须是服务可访问的 HTTPS 地址。")
        for name in ("display_name", "language"):
            if name in fields:
                text_value(fields[name], name, 200)
        if "denoise" in fields and type(fields["denoise"]) is not bool:
            raise ValueError("denoise 必须是布尔值。")
    return kind, fields, reference


def read_reference(path):
    before = reference_info(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise ValueError("参考音频发生变化，请重新确认。")
        data = source.read(MAX_REFERENCE + 1)
        after = os.fstat(source.fileno())
    if (len(data) != before.st_size or len(data) > MAX_REFERENCE
            or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)):
        raise ValueError("参考音频读取期间发生变化，请重新确认。")
    suffix = path.suffix.lower()
    return "voice-sample" + suffix, MEDIA_TYPES[suffix], data


def multipart(fields, file_part=None):
    boundary = "joekam-" + secrets.token_hex(20)
    marker = boundary.encode("ascii")
    chunks = []
    for name, value in fields.items():
        encoded = str(value).lower() if type(value) is bool else str(value)
        chunks.extend([b"--" + marker + b"\r\n", f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                       encoded.encode("utf-8"), b"\r\n"])
    if file_part is not None:
        filename, media_type, data = file_part
        chunks.extend([b"--" + marker + b"\r\n",
                       f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                       f"Content-Type: {media_type}\r\n\r\n".encode(), data, b"\r\n"])
    chunks.append(b"--" + marker + b"--\r\n")
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def api_key():
    key = os.environ.get("NOIZ_API_KEY", "")
    if not key or key != key.strip() or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ValueError("请通过环境变量 NOIZ_API_KEY 提供服务密钥。")
    return key


def request_for(method, path, key, body=None, content_type=None):
    headers = {"Authorization": key}
    if content_type:
        headers["Content-Type"] = content_type
    return request.Request(BASE + path, data=body, headers=headers, method=method)


def service_open(req):
    try:
        return open_request(req, timeout=120)
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ServiceError(f"服务返回 HTTP {code}。") from None
    except (error.URLError, TimeoutError, OSError):
        raise ServiceError("连接失败或超时。") from None


def json_response(req):
    try:
        with service_open(req) as response:
            raw = response.read(MAX_JSON + 1)
    except (TimeoutError, OSError, http.client.HTTPException):
        raise ServiceError("读取服务响应失败或超时。") from None
    if len(raw) > MAX_JSON:
        raise ServiceError("服务响应过大。")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError("服务没有返回有效的 JSON。") from None
    if (not isinstance(payload, dict) or type(payload.get("code")) is not int or payload["code"] != 0
            or not isinstance(payload.get("data"), dict)):
        raise ServiceError("服务未确认请求成功，请检查服务控制台。")
    return payload["data"]


def record_bytes(record):
    return (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def create_record(path, kind):
    record = {"provider": "Noiz", "kind": kind, "state": "submission_unconfirmed",
              "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    data = record_bytes(record)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return record, data


def update_record(path, expected, record):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise ValueError("任务记录发生变化，未覆盖它。")
    fd, temporary = tempfile.mkstemp(prefix=".noiz-voice-record-", dir=path.parent)
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


def list_voices(voice_type, skip, limit):
    if skip < 0 or not 1 <= limit <= 100:
        raise ValueError("skip 须为非负数，limit 须为 1 至 100。")
    query = parse.urlencode({"voice_type": voice_type, "skip": skip, "limit": limit})
    data = json_response(request_for("GET", "/voices?" + query, api_key()))
    if not isinstance(data.get("voices"), list):
        raise ServiceError("服务响应缺少声音列表。")
    voices = []
    for voice in data["voices"]:
        if isinstance(voice, dict) and isinstance(voice.get("voice_id"), str):
            voices.append({name: voice.get(name) for name in ("voice_id", "display_name", "voice_type")})
    return {"voices": voices, "total_count": data.get("total_count"), "skip": skip, "limit": limit}


def clone(fields, reference, task_path):
    file_part = read_reference(reference) if reference else None
    body, content_type = multipart(fields, file_part)
    key = api_key()
    record, original = create_record(task_path, "clone")
    data = json_response(request_for("POST", "/voices", key, body, content_type))
    voice_id = data.get("voice_id")
    if (not isinstance(voice_id, str) or not voice_id.strip() or len(voice_id) > 200
            or any(ord(c) < 32 or ord(c) == 127 for c in voice_id)):
        raise ServiceError("服务响应缺少声音 ID，请检查服务控制台。")
    record.update({"state": "completed", "voice_id": voice_id})
    update_record(task_path, original, record)
    return {"state": "completed", "voice_id": voice_id}


def valid_audio_header(prefix, output_format):
    if output_format == "wav":
        return len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE"
    return prefix.startswith(b"ID3") or (len(prefix) >= 2 and prefix[0] == 0xff and prefix[1] & 0xe0 == 0xe0)


def speak(fields, task_path, destination):
    if task_path.resolve() == destination.resolve():
        raise ValueError("任务记录和音频输出必须使用不同文件。")
    if destination.exists() or destination.is_symlink():
        raise ValueError("输出文件已存在，未覆盖它。")
    if destination.suffix.lower() != "." + fields["output_format"]:
        raise ValueError("输出文件扩展名须与 output_format 一致。")
    if not destination.parent.is_dir():
        raise ValueError("输出目录不存在。")
    body, content_type = multipart(fields)
    key = api_key()
    record, original = create_record(task_path, "speech")
    fd, temporary = tempfile.mkstemp(prefix=".noiz-voice-audio-", dir=destination.parent)
    try:
        digest = hashlib.sha256()
        size = 0
        prefix = b""
        with os.fdopen(fd, "wb") as output:
            req = request_for("POST", "/text-to-speech", key, body, content_type)
            try:
                with service_open(req) as response:
                    media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    permitted = {"", "application/octet-stream", "audio/wav", "audio/x-wav", "audio/wave",
                                 "audio/vnd.wave", "audio/mpeg", "audio/mp3"}
                    if media not in permitted:
                        raise ServiceError("服务没有返回音频内容。")
                    while True:
                        chunk = response.read(128 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_AUDIO:
                            raise ServiceError("音频响应过大。")
                        if len(prefix) < 12:
                            prefix = (prefix + chunk)[:12]
                        output.write(chunk)
                        digest.update(chunk)
            except (TimeoutError, OSError, http.client.HTTPException):
                raise ServiceError("读取音频失败或超时。") from None
            if not valid_audio_header(prefix, fields["output_format"]):
                raise ServiceError("返回内容与请求的音频格式不符。")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
        record.update({"state": "completed", "audio_sha256": digest.hexdigest(), "bytes": size})
        update_record(task_path, original, record)
        return {"state": "completed", "bytes": size, "output": str(destination)}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    voices = commands.add_parser("voices", help="List voices available to the configured account")
    voices.add_argument("--type", choices=("built-in", "custom"), default="built-in")
    voices.add_argument("--skip", type=int, default=0)
    voices.add_argument("--limit", type=int, default=10)
    preview = commands.add_parser("preview", help="Validate a request without network access")
    preview.add_argument("--request", required=True)
    for action in ("clone", "speak"):
        command = commands.add_parser(action)
        command.add_argument("--request", required=True)
        command.add_argument("--task-file", required=True)
        if action == "speak":
            command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "voices":
            result = list_voices(args.type, args.skip, args.limit)
        else:
            kind, fields, reference = prepare(args.request)
            if args.command == "preview":
                result = {"kind": kind, "fields": sorted(fields), "uses_local_audio": reference is not None}
            else:
                expected = "clone" if args.command == "clone" else "speech"
                if kind != expected:
                    raise ValueError(f"{args.command} 需要 kind 为 {expected} 的请求。")
                task_path = Path(args.task_file)
                if args.command == "clone":
                    result = clone(fields, reference, task_path)
                else:
                    result = speak(fields, task_path, Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ServiceError) as exc:
        print(str(exc), file=sys.stderr)
        if args.command in ("clone", "speak") and Path(args.task_file).exists():
            print("若任务记录显示 submission_unconfirmed，勿自动重复提交；先检查记录和服务控制台。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
