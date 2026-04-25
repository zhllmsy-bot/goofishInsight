#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib import request

import openviking as ov
from mcp.server.fastmcp import FastMCP


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openviking-mcp")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "resource"


def sanitize_agent_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", value)
    return cleaned or "codexmcpserver"


def build_markdown(title: str, tags: list[str], content: str) -> str:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [title.strip(), f"timestamp: {timestamp}"]
    if tags:
        lines.append(f"tags: {', '.join(tags)}")
    lines.extend(["", content.strip()])
    return "\n".join(lines).strip()


def build_resource_uri(account: str, title: str, explicit_uri: str = "") -> str:
    if explicit_uri:
        return explicit_uri
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    slug = slugify(title)
    return (
        "viking://resources/"
        f"{account}/turn-summaries/"
        f"{now.strftime('%Y/%m/%d')}/{stamp}-{slug}.md"
    )


@dataclass(frozen=True)
class ServerConfig:
    upstream_url: str
    api_key: str
    account: str
    user: str
    agent: str
    host: str
    port: int
    transport: str


def parse_args() -> ServerConfig:
    parser = argparse.ArgumentParser(
        description="OpenViking MCP server for search and text resource ingestion."
    )
    parser.add_argument(
        "--upstream-url",
        default=os.getenv("OV_SERVER_URL", "http://127.0.0.1:1933"),
        help="OpenViking HTTP server base URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OV_API_KEY", ""),
        help="API key for the upstream OpenViking server.",
    )
    parser.add_argument(
        "--account",
        default=os.getenv("OV_ACCOUNT", "codex-goofish"),
        help="OpenViking account header.",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("OV_USER", "codex"),
        help="OpenViking user header.",
    )
    parser.add_argument(
        "--agent",
        default=os.getenv("OV_AGENT", "codex-mcp-server"),
        help="OpenViking agent header.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OV_HOST", "0.0.0.0"),
        help="Bind host for the MCP server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OV_PORT", "2033")),
        help="Bind port for the MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default=os.getenv("OV_TRANSPORT", "streamable-http"),
        help="MCP transport mode.",
    )
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Missing OV_API_KEY / --api-key for upstream OpenViking auth.")
    return ServerConfig(
        upstream_url=args.upstream_url.rstrip("/"),
        api_key=args.api_key,
        account=args.account,
        user=args.user,
        agent=args.agent,
        host=args.host,
        port=args.port,
        transport=args.transport,
    )


@contextmanager
def open_client(config: ServerConfig, *, agent_suffix: str = "") -> Iterator[Any]:
    raw_agent_id = config.agent if not agent_suffix else f"{config.agent}{agent_suffix}"
    agent_id = sanitize_agent_id(raw_agent_id)
    client = ov.SyncHTTPClient(
        url=config.upstream_url,
        api_key=config.api_key,
        account=config.account,
        user=config.user,
        agent_id=agent_id,
        timeout=120.0,
    )
    client.initialize()
    try:
        yield client
    finally:
        client.close()


def probe_upstream_health(config: ServerConfig) -> dict[str, Any]:
    headers = {
        "X-API-Key": config.api_key,
        "X-OpenViking-Account": config.account,
        "X-OpenViking-User": config.user,
        "X-OpenViking-Agent": config.agent,
    }
    req = request.Request(
        f"{config.upstream_url}/health",
        headers=headers,
        method="GET",
    )
    with request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_server(config: ServerConfig) -> FastMCP:
    mcp = FastMCP(
        name="openviking-mcp",
        instructions=(
            "OpenViking MCP server for semantic search and text resource ingestion. "
            "Use search/read to inspect stored context and add_text_resource to persist "
            "important summaries as markdown resources."
        ),
        host=config.host,
        port=config.port,
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool()
    async def search(
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.2,
        target_uri: str = "",
    ) -> str:
        """
        Search OpenViking for relevant resources or memories.

        Args:
            query: Semantic search query.
            top_k: Maximum number of results to return.
            score_threshold: Minimum similarity score.
            target_uri: Optional URI scope.
        """

        def _search_sync() -> str:
            with open_client(config, agent_suffix="search") as client:
                results = client.search(
                    query=query,
                    target_uri=target_uri,
                    limit=max(1, min(top_k, 20)),
                    score_threshold=score_threshold,
                )
                items: list[dict[str, Any]] = []
                candidates = list(results.resources[:top_k]) + list(results.memories[:top_k])
                for resource in candidates:
                    preview = ""
                    try:
                        preview = client.read(resource.uri, limit=500)
                    except Exception:
                        try:
                            preview = client.abstract(resource.uri)
                        except Exception:
                            preview = ""
                    items.append(
                        {
                            "uri": resource.uri,
                            "score": round(resource.score, 4),
                            "preview": preview[:500],
                        }
                    )
                return json.dumps(
                    {
                        "query": query,
                        "target_uri": target_uri,
                        "count": len(items),
                        "results": items,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

        return await asyncio.to_thread(_search_sync)

    @mcp.tool()
    async def read(
        uri: str,
        level: str = "overview",
        limit: int = 4000,
    ) -> str:
        """
        Read a resource from OpenViking.

        Args:
            uri: OpenViking URI to read.
            level: One of abstract, overview, or read.
            limit: Character limit applied to read mode.
        """

        def _read_sync() -> str:
            with open_client(config, agent_suffix="read") as client:
                mode = level.strip().lower()
                if mode == "abstract":
                    return client.abstract(uri)
                if mode == "overview":
                    return client.overview(uri)
                if mode == "read":
                    return client.read(uri, limit=max(1, limit))
                raise ValueError("level must be one of: abstract, overview, read")

        return await asyncio.to_thread(_read_sync)

    @mcp.tool()
    async def add_resource(
        resource_path: str,
        target_uri: str = "",
    ) -> str:
        """
        Add a URL or a server-local file path into OpenViking.

        Args:
            resource_path: URL or file path visible to the MCP server host.
            target_uri: Optional final URI in OpenViking.
        """

        def _add_sync() -> str:
            with open_client(config, agent_suffix="add-resource") as client:
                path = resource_path
                if not path.startswith("http"):
                    resolved = Path(path).expanduser()
                    if not resolved.exists():
                        return json.dumps(
                            {"status": "error", "message": f"file not found: {resolved}"},
                            ensure_ascii=False,
                        )
                    path = str(resolved)
                result = client.add_resource(path=path, to=target_uri or None, wait=True)
                return json.dumps(
                    {
                        "status": "success",
                        "target_uri": target_uri,
                        "result": result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

        return await asyncio.to_thread(_add_sync)

    @mcp.tool()
    async def add_text_resource(
        title: str,
        content: str,
        target_uri: str = "",
        tags: str = "",
    ) -> str:
        """
        Persist a markdown text blob as an OpenViking resource.

        Args:
            title: Resource title.
            content: Markdown or plain text content.
            target_uri: Optional final URI. Defaults to a dated turn-summaries path.
            tags: Optional comma-separated tags.
        """

        def _add_text_sync() -> str:
            tag_list = [item.strip() for item in tags.split(",") if item.strip()]
            markdown = build_markdown(title=title, tags=tag_list, content=content)
            resource_uri = build_resource_uri(config.account, title, explicit_uri=target_uri)

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                prefix="openviking-mcp-",
                delete=False,
                encoding="utf-8",
            ) as handle:
                handle.write(markdown)
                temp_path = Path(handle.name)

            try:
                with open_client(config, agent_suffix="add-text") as client:
                    result = client.add_resource(
                        path=str(temp_path),
                        to=resource_uri,
                        wait=True,
                    )
                return json.dumps(
                    {
                        "status": "success",
                        "resource_uri": resource_uri,
                        "result": result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            finally:
                temp_path.unlink(missing_ok=True)

        return await asyncio.to_thread(_add_text_sync)

    @mcp.resource("openviking://status")
    def status_resource() -> str:
        health = probe_upstream_health(config)
        return json.dumps(
            {
                "mcp": {
                    "host": config.host,
                    "port": config.port,
                    "transport": config.transport,
                },
                "upstream": {
                    "url": config.upstream_url,
                    "health": health,
                },
            },
            ensure_ascii=False,
            indent=2,
        )

    return mcp


def main() -> None:
    config = parse_args()
    logger.info("Starting OpenViking MCP server")
    logger.info("  upstream: %s", config.upstream_url)
    logger.info("  endpoint: http://%s:%s/mcp", config.host, config.port)
    mcp = create_server(config)
    if config.transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
