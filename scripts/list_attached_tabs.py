from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    cdp_url: str = "http://127.0.0.1:9222",
    only_goofish: bool = False,
) -> None:
    try:
        with urlopen(f"{cdp_url}/json/list", timeout=3) as response:
            tabs = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        typer.echo(
            json.dumps(
                {
                    "cdp_url": cdp_url,
                    "status": "unavailable",
                    "message": "Attached Chrome is not running or remote debugging is not enabled.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    rows = []
    for tab in tabs:
        url = tab.get("url", "")
        is_goofish = "goofish.com" in url
        if only_goofish and not is_goofish:
            continue
        rows.append(
            {
                "id": tab.get("id"),
                "type": tab.get("type"),
                "title": tab.get("title"),
                "url": url,
                "is_goofish": is_goofish,
            }
        )

    typer.echo(
        json.dumps(
            {
                "cdp_url": cdp_url,
                "tab_count": len(rows),
                "goofish_tab_count": sum(1 for row in rows if row["is_goofish"]),
                "tabs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
