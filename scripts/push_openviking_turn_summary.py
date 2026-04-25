#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_CONFIG_PATH = Path.home() / ".codex" / "openviking-goofish.env"
DEFAULT_LOG_PATH = Path.home() / ".codex" / "openviking-goofish-log.jsonl"


@dataclass
class OpenVikingConfig:
    base_url: str
    mcp_url: str
    api_key: str
    account: str
    user: str
    agent: str
    log_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push a Codex turn summary into OpenViking."
    )
    parser.add_argument("--summary", help="Summary text. If omitted, read from stdin.")
    parser.add_argument(
        "--config-path",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to an env-style config file.",
    )
    parser.add_argument(
        "--transport",
        choices=["mcp", "api"],
        default=os.environ.get("OPENVIKING_TRANSPORT", "mcp"),
        help="Upload transport. Defaults to MCP.",
    )
    parser.add_argument(
        "--role",
        default="assistant",
        help="Message role to store in the session.",
    )
    parser.add_argument(
        "--title",
        default="Codex turn summary",
        help="Short title to prefix into the stored summary.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Optional tag to include in the stored summary.",
    )
    parser.add_argument(
        "--resource-uri",
        help="Optional target resource URI. Defaults to a dated path under turn-summaries.",
    )
    parser.add_argument(
        "--debug-uri",
        help="Optional URI to query via /api/v1/debug/vector/count after upload.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def get_config(config_path: Path) -> OpenVikingConfig:
    file_values = load_env_file(config_path)

    def resolve(name: str, default: str | None = None) -> str:
        value = os.environ.get(name) or file_values.get(name) or default
        if value is None or value == "":
            raise SystemExit(f"Missing required config: {name}")
        return value

    log_path = Path(
        os.environ.get("OPENVIKING_LOG_PATH")
        or file_values.get("OPENVIKING_LOG_PATH")
        or str(DEFAULT_LOG_PATH)
    )

    return OpenVikingConfig(
        base_url=resolve("OPENVIKING_BASE_URL", "http://127.0.0.1:1933").rstrip("/"),
        mcp_url=resolve("OPENVIKING_MCP_URL", "http://127.0.0.1:2033/mcp"),
        api_key=resolve("OPENVIKING_API_KEY"),
        account=resolve("OPENVIKING_ACCOUNT", "codex-goofish"),
        user=resolve("OPENVIKING_USER", "codex"),
        agent=resolve("OPENVIKING_AGENT", "codex-main"),
        log_path=log_path,
    )


def build_summary(title: str, tags: list[str], summary: str) -> str:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        title.strip(),
        f"timestamp: {timestamp}",
    ]
    if tags:
        lines.append(f"tags: {', '.join(tags)}")
    lines.extend(
        [
            "",
            summary.strip(),
        ]
    )
    return "\n".join(lines).strip()


def http_json(
    config: OpenVikingConfig,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{config.base_url}{path}"
    data = None
    headers = {
        "x-api-key": config.api_key,
        "X-OpenViking-Account": config.account,
        "X-OpenViking-User": config.user,
        "X-OpenViking-Agent": config.agent,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as resp:
            body = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SystemExit(f"{method} {path} failed: {exc}") from exc

    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def http_multipart(
    config: OpenVikingConfig,
    path: str,
    file_name: str,
    file_bytes: bytes,
) -> Any:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                "Content-Disposition: form-data; name=\"file\"; "
                f"filename=\"{file_name}\"\r\n"
            ).encode("utf-8"),
            b"Content-Type: text/markdown\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}\r\n".encode("utf-8"),
            b"Content-Disposition: form-data; name=\"telemetry\"\r\n\r\n",
            b"false\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    req = request.Request(
        f"{config.base_url}{path}",
        data=body,
        headers={
            "x-api-key": config.api_key,
            "X-OpenViking-Account": config.account,
            "X-OpenViking-User": config.user,
            "X-OpenViking-Agent": config.agent,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req) as resp:
            body = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {path} failed: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SystemExit(f"POST {path} failed: {exc}") from exc

    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def append_log(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_mcp_modules() -> tuple[Any, Any]:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        return ClientSession, streamablehttp_client
    except ImportError:
        pass

    venv_root = Path.home() / ".codex" / "openviking-mcp-client-venv" / "lib"
    for site_packages in sorted(venv_root.glob("python*/site-packages")):
        if str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            return ClientSession, streamablehttp_client
        except ImportError:
            continue

    raise SystemExit(
        "MCP client dependency not found. Install mcp into ~/.codex/openviking-mcp-client-venv "
        "or rerun with --transport api."
    )


def read_summary(args: argparse.Namespace) -> str:
    if args.summary:
        return args.summary.strip()
    data = sys.stdin.read().strip()
    if not data:
        raise SystemExit("No summary provided via --summary or stdin.")
    return data


def unwrap_result(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload and "status" in payload:
        return payload["result"]
    return payload


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "codex-turn-summary"


def build_resource_uri(config: OpenVikingConfig, title: str) -> str:
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    slug = slugify(title)
    return (
        "viking://resources/"
        f"{config.account}/turn-summaries/"
        f"{now.strftime('%Y/%m/%d')}/{stamp}-{slug}.md"
    )


def parse_mcp_tool_result(result: Any) -> Any:
    parts = getattr(result, "content", None) or []
    text_parts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            text_parts.append(text)
    if not text_parts:
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured
        return {}
    joined = "\n".join(text_parts).strip()
    if not joined:
        return {}
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {"raw": joined}


async def mcp_add_text_resource(
    config: OpenVikingConfig,
    title: str,
    tags: list[str],
    content: str,
    resource_uri: str,
) -> Any:
    ClientSession, streamablehttp_client = load_mcp_modules()
    headers = {
        "x-api-key": config.api_key,
        "X-OpenViking-Account": config.account,
        "X-OpenViking-User": config.user,
        "X-OpenViking-Agent": config.agent,
    }
    async with streamablehttp_client(config.mcp_url, headers=headers) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "add_text_resource",
                {
                    "title": title,
                    "content": content,
                    "target_uri": resource_uri,
                    "tags": ",".join(tags),
                },
            )
            return parse_mcp_tool_result(result)


def main() -> None:
    args = parse_args()
    config = get_config(Path(args.config_path))
    raw_summary = read_summary(args)
    content = build_summary(args.title, args.tag, raw_summary)
    resource_uri = args.resource_uri or build_resource_uri(config, args.title)
    result: dict[str, Any]
    if args.transport == "mcp":
        resource = asyncio.run(
            mcp_add_text_resource(
                config=config,
                title=args.title,
                tags=args.tag,
                content=raw_summary,
                resource_uri=resource_uri,
            )
        )
        if resource.get("status") != "success":
            raise SystemExit(f"MCP upload failed: {resource}")
        result = {
            "resource_uri": resource.get("resource_uri", resource_uri),
            "account": config.account,
            "user": config.user,
            "agent": config.agent,
            "status": resource.get("status"),
            "errors": resource.get("errors"),
            "queue_status": resource.get("result", {}).get("queue_status"),
            "transport": "mcp",
        }
    else:
        file_name = Path(parse.urlparse(resource_uri).path).name or "codex-turn-summary.md"
        upload = unwrap_result(
            http_multipart(
                config,
                "/api/v1/resources/temp_upload",
                file_name=file_name,
                file_bytes=content.encode("utf-8"),
            )
        )
        temp_file_id = upload.get("temp_file_id")
        temp_path = upload.get("temp_path") or upload.get("path")
        if not temp_file_id and not temp_path:
            raise SystemExit(f"Unexpected temp upload response: {upload}")

        resource_payload: dict[str, Any] = {
            "to": resource_uri,
            "reason": "Codex turn summary upload",
            "instruction": (
                "Store this markdown summary as a searchable Codex turn summary."
            ),
            "wait": True,
            "timeout": 60,
            "telemetry": False,
        }
        if temp_file_id:
            resource_payload["temp_file_id"] = temp_file_id
        else:
            resource_payload["temp_path"] = temp_path

        resource = unwrap_result(
            http_json(
                config,
                "POST",
                "/api/v1/resources",
                payload=resource_payload,
            )
        )
        result = {
            "resource_uri": resource_uri,
            "account": config.account,
            "user": config.user,
            "agent": config.agent,
            "status": resource.get("status"),
            "errors": resource.get("errors"),
            "queue_status": resource.get("queue_status"),
            "transport": "api",
        }

    debug_uri = parse.quote(result["resource_uri"], safe="")
    result["resource_vector_count"] = unwrap_result(
        http_json(
            config,
            "GET",
            f"/api/v1/debug/vector/count?uri={debug_uri}",
        )
    )
    if args.debug_uri and args.debug_uri != resource_uri:
        debug_uri = parse.quote(args.debug_uri, safe="")
        result["debug_vector_count"] = unwrap_result(
            http_json(
                config,
                "GET",
                f"/api/v1/debug/vector/count?uri={debug_uri}",
            )
        )

    append_log(
        config.log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "title": args.title,
            "tags": args.tag,
            "summary_preview": raw_summary[:240],
            **result,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
