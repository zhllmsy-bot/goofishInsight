#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


W = 1800
H = 1080
BG = (16, 20, 28)
PANEL_BG = (28, 34, 46)
PANEL_BORDER = (72, 88, 116)
TITLE = (237, 242, 255)
TEXT = (194, 206, 226)
ACCENT = (76, 166, 255)


@dataclass
class Panel:
    x: int
    y: int
    w: int
    h: int
    title: str
    lines: list[str]


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Menlo.ttc" if mono else "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split(" ")
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_panel(draw: ImageDraw.ImageDraw, title_font: ImageFont.ImageFont, body_font: ImageFont.ImageFont, panel: Panel) -> None:
    x0, y0 = panel.x, panel.y
    x1, y1 = panel.x + panel.w, panel.y + panel.h

    draw.rounded_rectangle((x0, y0, x1, y1), radius=16, fill=PANEL_BG, outline=PANEL_BORDER, width=2)
    draw.rounded_rectangle((x0, y0, x1, y0 + 44), radius=16, fill=(35, 43, 58), outline=None)
    draw.rectangle((x0, y0 + 28, x1, y0 + 44), fill=(35, 43, 58), outline=None)

    draw.text((x0 + 14, y0 + 11), panel.title, font=title_font, fill=TITLE)

    y = y0 + 58
    line_gap = 8
    max_width = panel.w - 30

    for raw in panel.lines:
        wrapped = wrap_line(draw, f"- {raw}", body_font, max_width)
        for line in wrapped:
            if y > y1 - 24:
                return
            draw.text((x0 + 14, y), line, font=body_font, fill=TEXT)
            y += 18
        y += line_gap


def draw_page(page_title: str, route: str, subtitle: str, panels: Iterable[Panel], output_path: Path) -> None:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    h1 = load_font(42)
    h2 = load_font(22)
    h3 = load_font(19)
    body = load_font(16)
    mono = load_font(16, mono=True)

    draw.text((40, 28), page_title, font=h1, fill=TITLE)
    draw.text((42, 82), subtitle, font=h2, fill=TEXT)

    draw.rounded_rectangle((40, 114, 380, 154), radius=12, fill=(31, 64, 106), outline=(85, 149, 228), width=2)
    draw.text((56, 124), "Route", font=h3, fill=(183, 220, 255))
    draw.text((136, 124), route, font=mono, fill=(237, 247, 255))

    draw.line((40, 170, W - 40, 170), fill=(55, 67, 86), width=2)

    for panel in panels:
        draw_panel(draw, h3, body, panel)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def overview_panels() -> list[Panel]:
    return [
        Panel(
            x=40,
            y=190,
            w=320,
            h=850,
            title="Left Sidebar",
            lines=[
                "Brand card and terminal identity.",
                "Quick scope pills: actionable only vs all listings.",
                "Category tree and product drill-down list.",
                "Preference tags: freshness window, selected model/spec.",
                "Runtime status: auto refresh state, login state, last refresh time.",
            ],
        ),
        Panel(
            x=390,
            y=190,
            w=1368,
            h=150,
            title="Selection Panel",
            lines=[
                "Current model context and guidance message.",
                "Template-based attribute filters and chips.",
                "Quick switching for model/spec/template fields.",
            ],
        ),
        Panel(
            x=390,
            y=360,
            w=1368,
            h=185,
            title="Pricing Panel",
            lines=[
                "Safe buy / normal buy / market median price lines.",
                "Estimated profit range and margin percent.",
                "Reliability, seller sample count, and opportunity label.",
                "Dimension tags for the selected template slice.",
            ],
        ),
        Panel(
            x=390,
            y=565,
            w=1368,
            h=220,
            title="Listings Panel",
            lines=[
                "New listings grouped by buy / watch decision buckets.",
                "Per card: image, price, delta vs target line, model, title.",
                "Meta: region, seller identity, heartbeat state, seen time.",
                "Outbound links: open listing and open detail page.",
            ],
        ),
        Panel(
            x=390,
            y=805,
            w=674,
            h=235,
            title="Focus Panel",
            lines=[
                "Priority focus cards for immediate trading attention.",
                "Per card: safe/normal/market prices and profit expectation.",
                "Focus state, caption, required minimum profit, dimension tags.",
            ],
        ),
        Panel(
            x=1084,
            y=805,
            w=674,
            h=235,
            title="Reference Panel",
            lines=[
                "Two tabs: trend view and calibration view.",
                "Trend: mini charts, range labels, stale ratio, seller coverage.",
                "Calibration: listing anchor vs sold anchor and evidence count.",
                "Provides context validation before final buy decisions.",
            ],
        ),
    ]


def llm_ops_panels() -> list[Panel]:
    return [
        Panel(
            x=40,
            y=190,
            w=1720,
            h=120,
            title="Hero",
            lines=[
                "Page intent: trace inspection for prompts, responses, tokens.",
                "Trace switch status and total trace file count.",
            ],
        ),
        Panel(
            x=40,
            y=330,
            w=620,
            h=350,
            title="Trace List",
            lines=[
                "Recent LLM traces as compact selectable rows.",
                "Per row: trace id tail, model badge, status dot, latency, token pair.",
                "Selection drives detail view on the right side.",
            ],
        ),
        Panel(
            x=680,
            y=330,
            w=1080,
            h=350,
            title="Trace Detail",
            lines=[
                "Meta bar: provider, model, method, status, generated time.",
                "Token usage bar and latency bar for this trace.",
                "Message blocks: system / user / assistant content.",
                "Collapsible code blocks: headers, request payload, response payload, raw trace.",
            ],
        ),
        Panel(
            x=40,
            y=700,
            w=1720,
            h=120,
            title="Token Usage Summary",
            lines=[
                "KPI cards: total/input/output tokens, cached tokens.",
                "Second-pass requested/rescued/unresolved counts.",
                "High-confidence kept and filtered result counters.",
            ],
        ),
        Panel(
            x=40,
            y=840,
            w=850,
            h=200,
            title="Recent Usage Runs Table",
            lines=[
                "Recent batch files with domain and pipeline info.",
                "Columns: requests, sample count, input/output/total/cached tokens, generated time.",
            ],
        ),
        Panel(
            x=910,
            y=840,
            w=850,
            h=200,
            title="Worker Runs",
            lines=[
                "Recent worker/result run cards.",
                "Per card: pipeline, domain, provider/model, worker count, recent event summaries.",
            ],
        ),
    ]


def runtime_panels() -> list[Panel]:
    return [
        Panel(
            x=40,
            y=190,
            w=1720,
            h=120,
            title="Hero",
            lines=[
                "Current runtime headline and decision-first guidance.",
                "Meta pills: total units, online count, attention count, last refresh.",
            ],
        ),
        Panel(
            x=40,
            y=330,
            w=1720,
            h=120,
            title="Runtime Summary Cards",
            lines=[
                "Need attention count with stopped/degraded split.",
                "Running unit count and fixed 20-second refresh cadence.",
            ],
        ),
        Panel(
            x=40,
            y=470,
            w=1720,
            h=170,
            title="Action Center",
            lines=[
                "Top-priority non-running groups (up to 3 cards).",
                "Per card: failing checks, recommended action button, inline execution feedback.",
            ],
        ),
        Panel(
            x=40,
            y=660,
            w=1720,
            h=250,
            title="Service Control Grid",
            lines=[
                "All runtime groups with status badge and description.",
                "Per group: stats, check list, available control actions (start/restart/stop etc).",
                "Inline feedback for action success or failure.",
            ],
        ),
        Panel(
            x=40,
            y=930,
            w=1720,
            h=110,
            title="Activity Feed",
            lines=[
                "Recent operations in current session with result state and timestamp.",
                "Keeps execution memory for quick rollback/verification.",
            ],
        ),
    ]


def main() -> None:
    output_dir = Path("reports/dashboard-page-structures")
    draw_page(
        page_title="Dashboard Structure - Overview",
        route="/",
        subtitle="Buy-side market terminal page regions and displayed data",
        panels=overview_panels(),
        output_path=output_dir / "dashboard-overview-structure.png",
    )
    draw_page(
        page_title="Dashboard Structure - LLM DevOps",
        route="/llm-devops",
        subtitle="Trace and token analysis page regions and displayed data",
        panels=llm_ops_panels(),
        output_path=output_dir / "dashboard-llm-devops-structure.png",
    )
    draw_page(
        page_title="Dashboard Structure - Runtime Control",
        route="/runtime",
        subtitle="Runtime command center page regions and displayed data",
        panels=runtime_panels(),
        output_path=output_dir / "dashboard-runtime-structure.png",
    )


if __name__ == "__main__":
    main()
