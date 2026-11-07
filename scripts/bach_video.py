#!/usr/bin/env python3
"""Preview, submit, and inspect optional Bach video-generation tasks."""

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from urllib import error, parse, request


ENDPOINT = "https://api-gen-na.bach.art/api/vdr/video/v2"
MAX_RESPONSE_BYTES = 1024 * 1024


class ServiceError(Exception):
    """The provider did not return a usable response."""


def http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parts = parse.urlsplit(value)
        return parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        return False


def finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def prepare(path):
    """Validate request structure without making a network call."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("请求文件必须是 JSON 对象。")
    model = payload.get("model_name", "Bach-1.0-Pro")
    if not isinstance(model, str) or model.casefold() != "bach-1.0-pro":
        raise ValueError("此工具只处理 Bach-1.0-Pro。")
    spec = payload.get("input")
    if not isinstance(spec, dict):
        raise ValueError("请求需要 input 对象。")
    task = spec.get("task", "t2v")
    if not isinstance(task, str) or task.casefold() not in ("t2v", "i2v", "r2v"):
        raise ValueError("input.task 必须是 t2v、i2v 或 r2v。")
    task = task.casefold()
    prompt = spec.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 6500:
        raise ValueError("input.prompt 必须是非空文字，最多 6500 字符。")
    duration = spec.get("duration", 5)
    if not finite_number(duration) or not 5 <= duration <= 16:
        raise ValueError("input.duration 必须在 5 至 16 秒之间。")
    resolution = spec.get("resolution", "1080p")
    if not isinstance(resolution, str) or resolution.casefold() not in ("1080p", "4k"):
        raise ValueError("input.resolution 必须是 1080p 或 4k。")
    aspect = spec.get("aspect_ratio", "auto" if task == "i2v" else "16:9")
    if not isinstance(aspect, str) or aspect.casefold() not in (
        "4:3", "3:4", "16:9", "9:16", "21:9", "1:1", "auto"
    ):
        raise ValueError("input.aspect_ratio 不是服务支持的比例。")
    if "generate_audio" in spec and not isinstance(spec["generate_audio"], bool):
        raise ValueError("input.generate_audio 必须是布尔值。")
    if "seed" in spec and (
        not isinstance(spec["seed"], int)
        or isinstance(spec["seed"], bool)
        or not 1 <= spec["seed"] <= 100000
    ):
        raise ValueError("input.seed 必须是 1 至 100000 的整数。")

    counts = {"image": 0, "video": 0, "audio": 0}
    if task == "i2v":
        frames = [spec.get("image_url"), spec.get("end_image_url")]
        if not any(frame is not None for frame in frames):
            raise ValueError("i2v 至少需要首帧或尾帧 URL。")
        if any(frame is not None and not http_url(frame) for frame in frames):
            raise ValueError("首尾帧需要 HTTP 或 HTTPS URL。")
    if task == "r2v":
        refs = spec.get("reference_inputs")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 12:
            raise ValueError("r2v 需要 1 至 12 个参考素材。")
        for item in refs:
            if not isinstance(item, dict) or item.get("type") not in counts or not http_url(item.get("url")):
                raise ValueError("每个参考素材需要有效的 type 和 HTTP(S) URL。")
            counts[item["type"]] += 1
            if "start_time" in item and (not finite_number(item["start_time"]) or item["start_time"] < 0):
                raise ValueError("参考素材 start_time 不能小于零。")
        if not counts["image"] and not counts["video"]:
            raise ValueError("r2v 至少需要一张图片或一个视频参考。")
        if counts["image"] > 9 or counts["video"] > 3 or counts["audio"] > 3:
            raise ValueError("参考素材数量超过当前服务限制。")

    ignored = []
    if task == "t2v":
        ignored = [key for key in ("image_url", "end_image_url", "reference_inputs") if key in spec]
    elif task == "i2v" and "reference_inputs" in spec:
        ignored = ["reference_inputs"]
    elif task == "r2v":
        ignored = [key for key in ("image_url", "end_image_url") if key in spec]
    summary = {
        "model": model,
        "task": task,
        "duration_seconds": duration,
        "resolution": resolution,
        "effective_aspect_ratio": "auto" if task == "i2v" else aspect,
        "generate_audio": spec.get("generate_audio", True),
        "reference_counts": counts,
        "ignored_inputs": ignored,
    }
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return body, summary


def api_key():
    key = os.environ.get("BACH_API_KEY", "")
    if not key or "\n" in key or "\r" in key:
        raise ValueError("请通过环境变量 BACH_API_KEY 提供有效的服务密钥。")
    return key


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(req, timeout):
    return request.build_opener(NoRedirect()).open(req, timeout=timeout)


def call_api(method, url, key, body=None):
    req = request.Request(
        url,
        data=body,
        method=method,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with open_request(req, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except error.HTTPError as exc:
        status_code = exc.code
        exc.close()
        raise ServiceError("服务返回 HTTP " + str(status_code) + "。") from None
    except (error.URLError, TimeoutError, OSError):
        raise ServiceError("连接失败或超时。") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ServiceError("服务响应过大。")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError("服务没有返回有效的 JSON。") from None
    if not isinstance(result, dict) or result.get("code") != 200 or not isinstance(result.get("data"), dict):
        raise ServiceError("服务未确认请求成功，请检查服务控制台。")
    return result


def reserve_record(path, body):
    record = {
        "provider": "Bach 1.0 Pro",
        "state": "submission_unconfirmed",
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "task_id": None,
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    return record


def replace_record(path, record):
    fd, temporary = tempfile.mkstemp(prefix=".bach-task-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview", help="检查请求，不访问网络")
    preview.add_argument("--request", required=True, type=Path)
    submit = commands.add_parser("submit", help="提交请求，可能产生费用")
    submit.add_argument("--request", required=True, type=Path)
    submit.add_argument("--task-file", required=True, type=Path)
    status = commands.add_parser("status", help="查询已提交任务")
    source = status.add_mutually_exclusive_group(required=True)
    source.add_argument("--task-file", type=Path)
    source.add_argument("--task-id")
    args = parser.parse_args(argv)

    try:
        if args.command == "preview":
            _, summary = prepare(args.request)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if args.command == "submit":
            body, _ = prepare(args.request)
            key = api_key()
            record = reserve_record(args.task_file, body)
            try:
                result = call_api("POST", ENDPOINT, key, body)
                task_id = result["data"].get("task_id")
                if not isinstance(task_id, str) or not task_id.strip():
                    raise ServiceError("服务响应缺少任务编号。")
                record.update(state="submitted", task_id=task_id)
                try:
                    replace_record(args.task_file, record)
                except OSError:
                    print("任务已创建，任务编号：" + task_id + "；记录文件保存失败。", file=sys.stderr)
                    raise
            except (ServiceError, OSError):
                print("提交结果可能未知；请检查任务记录及服务控制台，勿自动重复提交。", file=sys.stderr)
                raise
            print(json.dumps({"task_id": task_id, "status": result["data"].get("status"), "task_file": str(args.task_file)}, ensure_ascii=False))
            return 0
        if args.task_file:
            record = json.loads(args.task_file.read_text(encoding="utf-8"))
            task_id = record.get("task_id") if isinstance(record, dict) else None
        else:
            task_id = args.task_id
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("没有可查询的任务编号；请先核对服务控制台。")
        result = call_api("GET", ENDPOINT + "/" + parse.quote(task_id, safe=""), api_key())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ServiceError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
