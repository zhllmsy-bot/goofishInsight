from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import typer

from goofish_insight.settings import get_settings

app = typer.Typer(no_args_is_help=True)


def probe_cdp(cdp_url: str) -> dict | None:
    try:
        with urlopen(f"{cdp_url}/json/version", timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def resolve_chrome_path(chrome_path: Path | None) -> Path:
    if chrome_path is not None:
        return chrome_path
    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    if sys.platform.startswith("win"):
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    for command_name in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(command_name)
        if resolved:
            return Path(resolved)
    raise typer.BadParameter("Chrome not found. Please provide --chrome-path explicitly.")


@app.command()
def main(
    profile_key: str = "chrome-attached",
    port: int = 9222,
    chrome_path: Path | None = None,
    start_url: str = "https://www.goofish.com/",
    wait_seconds: int = 15,
) -> None:
    cdp_url = f"http://127.0.0.1:{port}"
    existing = probe_cdp(cdp_url)
    if existing:
        typer.echo(json.dumps({"cdp_url": cdp_url, "status": "already_running"}, ensure_ascii=False))
        return

    resolved_chrome_path = resolve_chrome_path(chrome_path)

    settings = get_settings()
    profile_dir = settings.browser_profile_dir / profile_key
    profile_dir.mkdir(parents=True, exist_ok=True)

    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

    command = [
        str(resolved_chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--new-window",
        start_url,
    ]
    subprocess.Popen(command, creationflags=creationflags)

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        version = probe_cdp(cdp_url)
        if version:
            typer.echo(
                json.dumps(
                    {
                        "cdp_url": cdp_url,
                        "status": "started",
                        "profile_dir": str(profile_dir),
                        "web_socket_debugger_url": version.get("webSocketDebuggerUrl"),
                    },
                    ensure_ascii=False,
                )
            )
            return
        time.sleep(1)

    raise RuntimeError(f"CDP endpoint not ready after {wait_seconds}s: {cdp_url}")


if __name__ == "__main__":
    app()
