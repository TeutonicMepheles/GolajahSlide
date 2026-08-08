#!/usr/bin/env python3
"""Build a fixed-stage HTML slide deck from the project's Markdown dialect.

The compiler intentionally uses only the Python standard library.  It keeps the
Markdown format deterministic enough for slide layout decisions while still
supporting the everyday primitives needed by this template: headings, lists,
tables, callouts, code, images and lightweight charts.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import struct
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "deck.html"
STAGE_WIDTH = 1920
STAGE_HEIGHT = 1080
EDITOR_SCHEMA_VERSION = "1.0"
SLIDE_SEPARATOR = re.compile(r"(?m)^---\s*$")
IMAGE_RE = re.compile(r'^!\[([^\]]*)\]\((\S+?)(?:\s+["\']([^"\']*)["\'])?\)\s*$')
DIRECTIVE_RE = re.compile(r"<!--\s*slide\s*(.*?)-->", re.I | re.S)
TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
LIST_RE = re.compile(r"^\s*([-*+] |\d+[.)] )(.*)$")
INLINE_TOKEN_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))")
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
REVEAL_KEY_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")


@dataclass
class Media:
    source: str
    output_source: str
    alt: str
    caption: str
    width: int | None = None
    height: int | None = None

    @property
    def ratio(self) -> float:
        if self.width and self.height:
            return self.width / self.height
        return 16 / 9


@dataclass
class Block:
    kind: str
    html: str
    text: str = ""
    meta: dict[str, object] = field(default_factory=dict)


@dataclass
class Slide:
    number: int
    slide_id: str
    kind: str
    title: str
    subtitle: str
    section: str
    layout_requested: str
    layout_resolved: str
    config: dict[str, str]
    media: list[Media]
    blocks: list[Block]
    raw_body: str
    editor_override: dict[str, object] = field(default_factory=dict)


class BuildMessages:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def warn(self, slide: int | None, message: str) -> None:
        prefix = f"P{slide}: " if slide else ""
        self.warnings.append(prefix + message)

    def error(self, slide: int | None, message: str) -> None:
        prefix = f"P{slide}: " if slide else ""
        self.errors.append(prefix + message)


def write_text_atomic(path: Path, source: str) -> None:
    """Replace a text artifact only after its complete contents reach disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        target_mode = 0o644
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, target_mode)
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    if value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_key_values(raw: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip().lower().replace("_", "-")] = parse_scalar(value)
    return values


def split_deck_source(source: str) -> tuple[dict[str, object], list[str]]:
    normalized = source.replace("\r\n", "\n").lstrip("\ufeff")
    deck: dict[str, object] = {}
    if normalized.startswith("---\n"):
        end = normalized.find("\n---", 4)
        if end != -1:
            deck = parse_key_values(normalized[4:end])
            normalized = normalized[end + 4 :].lstrip("\n")
    chunks = [chunk.strip() for chunk in SLIDE_SEPARATOR.split(normalized) if chunk.strip()]
    return deck, chunks


def clean_directive(chunk: str) -> tuple[dict[str, str], str]:
    match = DIRECTIVE_RE.search(chunk)
    config: dict[str, str] = {}
    if match:
        raw = match.group(1).strip()
        if raw.startswith(":"):
            raw = raw[1:].strip()
        parsed = parse_key_values(raw)
        config = {str(key): str(value) for key, value in parsed.items()}
        chunk = chunk[: match.start()] + chunk[match.end() :]
    return config, chunk.strip()


def pop_headings(chunk: str) -> tuple[str, str, str]:
    title = ""
    subtitle = ""
    remaining: list[str] = []
    for line in chunk.splitlines():
        if not title and line.startswith("# "):
            title = line[2:].strip()
        elif not subtitle and line.startswith("## "):
            subtitle = line[3:].strip()
        else:
            remaining.append(line)
    return title, subtitle, "\n".join(remaining).strip()


def read_svg_size(data: bytes) -> tuple[int, int] | None:
    text = data[:65536].decode("utf-8", errors="ignore")
    viewbox = re.search(r"viewBox\s*=\s*[\"']\s*[\d.+-]+[\s,]+[\d.+-]+[\s,]+([\d.]+)[\s,]+([\d.]+)", text, re.I)
    if viewbox:
        return max(1, round(float(viewbox.group(1)))), max(1, round(float(viewbox.group(2))))
    width = re.search(r"\bwidth\s*=\s*[\"']([\d.]+)", text, re.I)
    height = re.search(r"\bheight\s*=\s*[\"']([\d.]+)", text, re.I)
    if width and height:
        return max(1, round(float(width.group(1)))), max(1, round(float(height.group(1))))
    return None


def read_jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = struct.unpack(">H", data[index : index + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 <= len(data):
                height, width = struct.unpack(">HH", data[index + 3 : index + 7])
                return width, height
            break
        index += max(2, length)
    return None


def read_webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    kind = data[12:16]
    payload = data[20:]
    if kind == b"VP8X" and len(payload) >= 10:
        return int.from_bytes(payload[4:7], "little") + 1, int.from_bytes(payload[7:10], "little") + 1
    if kind == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
        bits = int.from_bytes(payload[1:5], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    marker = data.find(b"\x9d\x01\x2a")
    if marker != -1 and marker + 7 <= len(data):
        width, height = struct.unpack("<HH", data[marker + 3 : marker + 7])
        return width & 0x3FFF, height & 0x3FFF
    return None


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return read_svg_size(data)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        return read_jpeg_size(data)
    if suffix == ".webp":
        return read_webp_size(data)
    return None


def extract_media(body: str, source_dir: Path, output_dir: Path, messages: BuildMessages, slide_no: int) -> tuple[list[Media], str]:
    media: list[Media] = []
    kept: list[str] = []
    for line in body.splitlines():
        match = IMAGE_RE.match(line.strip())
        if not match:
            kept.append(line)
            continue
        alt, raw_source, caption = match.groups()
        if raw_source.startswith(("http://", "https://", "data:")):
            output_source = raw_source
            size = None
            messages.warn(slide_no, f"远程图片无法在构建期读取比例，将按 16:9 处理：{raw_source}")
        else:
            absolute = (source_dir / raw_source).resolve()
            if not absolute.exists():
                messages.error(slide_no, f"图片不存在：{raw_source}")
                size = None
            else:
                size = image_size(absolute)
                if not size:
                    messages.warn(slide_no, f"无法读取图片尺寸，将按 16:9 处理：{raw_source}")
            output_source = Path(os.path.relpath(absolute, output_dir)).as_posix()
        media.append(Media(raw_source, output_source, alt or "演示图片", caption or alt or "", *(size or (None, None))))
    return media, "\n".join(kept).strip()


def render_inline(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        pieces.append(html.escape(text[cursor : match.start()]))
        token = match.group(0)
        if token.startswith("`"):
            code = html.escape(token[1:-1]).replace("_", "_<wbr>")
            pieces.append(f"<code>{code}</code>")
        elif token.startswith("**"):
            pieces.append(f"<strong>{render_inline(token[2:-2])}</strong>")
        else:
            link = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token)
            if link:
                label, href = link.groups()
                pieces.append(f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>')
        cursor = match.end()
    pieces.append(html.escape(text[cursor:]))
    return "".join(pieces)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def render_table(lines: list[str]) -> Block:
    headers = split_table_row(lines[0])
    rows = [split_table_row(line) for line in lines[2:]]
    cols = max([len(headers), *[len(row) for row in rows]])
    headers += [""] * (cols - len(headers))
    normalized_rows = [row + [""] * (cols - len(row)) for row in rows]
    thead = "".join(f"<th>{render_inline(cell)}</th>" for cell in headers)
    tbody = "".join("<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>" for row in normalized_rows)
    markup = (
        '<article class="card table-card" data-visual-widget="table" tabindex="0">'
        '<div class="visual-widget-content" data-visual-content>'
        f'<table class="data-table" data-columns="{cols}" data-rows="{len(rows)}"><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>'
        "</div></article>"
    )
    return Block("table", markup, " ".join(headers + [cell for row in rows for cell in row]), {"rows": len(rows), "cols": cols})


def parse_chart(raw: str, messages: BuildMessages, slide_no: int) -> Block:
    config = parse_key_values(raw)
    chart_type = str(config.get("type", "bar")).lower()
    labels = [item.strip() for item in str(config.get("labels", "")).split("|") if item.strip()]
    try:
        values = [float(item.strip()) for item in str(config.get("values", "")).split("|") if item.strip()]
    except ValueError:
        values = []
    if not labels or len(labels) != len(values):
        messages.error(slide_no, "chart 的 labels 与 values 必须存在且数量一致")
        labels, values = ["示例"], [0.0]
    title = str(config.get("title", "数据图表"))
    unit = str(config.get("unit", ""))
    if chart_type not in {"bar", "line", "donut"}:
        messages.warn(slide_no, f"未知 chart type={chart_type}，已改用 bar")
        chart_type = "bar"
    svg = render_chart_svg(chart_type, labels, values, title, unit)
    markup = (
        '<figure class="card chart-card" data-visual-widget="image" tabindex="0">'
        f'<div class="visual-widget-content chart-content" data-visual-content>{svg}</div>'
        f'<figcaption>{html.escape(title)}</figcaption></figure>'
    )
    return Block("chart", markup, " ".join(labels), {"type": chart_type})


def render_chart_svg(chart_type: str, labels: list[str], values: list[float], title: str, unit: str) -> str:
    width, height = 1600, 610
    escaped_title = html.escape(title)
    if chart_type == "donut":
        total = sum(max(0, value) for value in values) or 1
        colors = ["#6F60E5", "#978CF0", "#BFB8F7", "#D8D3FB", "#4C3BC6", "#8173E8"]
        radius = 168
        circumference = 2 * math.pi * radius
        offset = 0.0
        rings: list[str] = []
        legend: list[str] = []
        for index, (label, value) in enumerate(zip(labels, values)):
            length = max(0, value) / total * circumference
            color = colors[index % len(colors)]
            rings.append(
                f'<circle cx="450" cy="325" r="{radius}" fill="none" stroke="{color}" stroke-width="62" '
                f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{-offset:.2f}" />'
            )
            legend.append(f'<rect x="860" y="{170 + index * 64}" width="24" height="24" rx="6" fill="{color}"/>'
                          f'<text x="902" y="{190 + index * 64}" font-size="28" fill="#111">{html.escape(label)} · {value:g}{html.escape(unit)}</text>')
            offset += length
        body = "".join(rings) + f'<text x="450" y="338" text-anchor="middle" font-size="42" font-weight="700" fill="#111">{total:g}{html.escape(unit)}</text>' + "".join(legend)
    else:
        left, top, plot_w, plot_h = 120, 130, 1360, 350
        maximum = max(max(values), 1)
        grid = []
        for tick in range(5):
            y = top + plot_h - plot_h * tick / 4
            value = maximum * tick / 4
            grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#E1E0E7" stroke-width="2"/>'
                        f'<text x="{left - 24}" y="{y + 9:.1f}" text-anchor="end" font-size="22" fill="#777">{value:g}</text>')
        body_parts = ["".join(grid)]
        slot = plot_w / max(1, len(values))
        points: list[tuple[float, float]] = []
        for index, (label, value) in enumerate(zip(labels, values)):
            x = left + slot * (index + .5)
            y = top + plot_h - plot_h * value / maximum
            points.append((x, y))
            body_parts.append(f'<text x="{x:.1f}" y="{top + plot_h + 48}" text-anchor="middle" font-size="24" fill="#555">{html.escape(label)}</text>')
            if chart_type == "bar":
                bar_w = min(132, slot * .58)
                bar_h = top + plot_h - y
                body_parts.append(f'<rect x="{x - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="14" fill="#6F60E5"/>'
                                  f'<text x="{x:.1f}" y="{y - 16:.1f}" text-anchor="middle" font-size="25" font-weight="700" fill="#4C3BC6">{value:g}{html.escape(unit)}</text>')
        if chart_type == "line":
            path = " ".join(("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}" for index, (x, y) in enumerate(points))
            body_parts.append(f'<path d="{path}" fill="none" stroke="#6F60E5" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>')
            for (x, y), value in zip(points, values):
                body_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="#fff" stroke="#6F60E5" stroke-width="7"/>'
                                  f'<text x="{x:.1f}" y="{y - 22:.1f}" text-anchor="middle" font-size="25" font-weight="700" fill="#4C3BC6">{value:g}{html.escape(unit)}</text>')
        body = "".join(body_parts)
    return (
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escaped_title}">'
        f'<text x="80" y="70" font-size="34" font-weight="700" fill="#111">{escaped_title}</text>{body}</svg>'
    )


def paragraph_block(parts: list[str], title: str | None = None) -> Block | None:
    if not parts and not title:
        return None
    content = "".join(parts)
    heading = f"<h3>{render_inline(title)}</h3>" if title else ""
    plain = re.sub(r"<[^>]+>", " ", content)
    return Block("section", f'<article class="card text-card section-card">{heading}{content}</article>', plain)


def parse_blocks(body: str, messages: BuildMessages, slide_no: int) -> list[Block]:
    lines = body.splitlines()
    blocks: list[Block] = []
    current_title: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_parts
        block = paragraph_block(current_parts, current_title)
        if block:
            blocks.append(block)
        current_title = None
        current_parts = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("### "):
            flush()
            current_title = stripped[4:].strip()
            i += 1
            continue
        if stripped.startswith("```"):
            flush()
            language = stripped[3:].strip().lower()
            i += 1
            fenced: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                fenced.append(lines[i])
                i += 1
            i += 1
            if language == "chart":
                blocks.append(parse_chart("\n".join(fenced), messages, slide_no))
            else:
                label = html.escape(language or "code")
                code = html.escape("\n".join(fenced))
                blocks.append(Block("code", f'<article class="card code-card"><span class="code-label">{label}</span><pre><code>{code}</code></pre></article>', "\n".join(fenced)))
            continue
        if i + 1 < len(lines) and "|" in stripped and TABLE_DIVIDER_RE.match(lines[i + 1]):
            flush()
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            blocks.append(render_table(table_lines))
            continue
        if stripped.startswith(">"):
            flush()
            quoted: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip()[1:].strip())
                i += 1
            label = "关键结论"
            callout_kind = "note"
            if quoted and re.fullmatch(r"\[![A-Za-z]+\]", quoted[0]):
                callout_kind = quoted.pop(0)[2:-1].lower()
                label = {"tip": "方法提示", "note": "补充说明", "warning": "风险提示", "quote": "关键结论", "question": "思考问题"}.get(callout_kind, "关键结论")
            quote_text = " ".join(quoted)
            blocks.append(Block("callout", f'<article class="card soft text-card callout-card callout-{html.escape(callout_kind)}"><strong>{label}</strong><p>{render_inline(quote_text)}</p></article>', quote_text))
            continue
        list_match = LIST_RE.match(line)
        if list_match:
            ordered = list_match.group(1)[0].isdigit()
            items: list[str] = []
            while i < len(lines):
                match = LIST_RE.match(lines[i])
                if not match or match.group(1)[0].isdigit() != ordered:
                    break
                items.append(match.group(2).strip())
                i += 1
            tag = "ol" if ordered else "ul"
            current_parts.append(f"<{tag}>" + "".join(f"<li>{render_inline(item)}</li>" for item in items) + f"</{tag}>")
            continue
        paragraph: list[str] = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line or next_line.startswith(("### ", "```", ">")) or LIST_RE.match(lines[i]):
                break
            if i + 1 < len(lines) and "|" in next_line and TABLE_DIVIDER_RE.match(lines[i + 1]):
                break
            paragraph.append(next_line)
            i += 1
        current_parts.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
    flush()
    return blocks


def bool_config(config: dict[str, str], key: str, default: bool) -> bool:
    value = config.get(key)
    if value is None:
        return default
    return value.lower() not in {"false", "no", "off", "0"}


def body_text_length(blocks: Iterable[Block]) -> int:
    return sum(len(re.sub(r"\s+", "", block.text)) for block in blocks if block.kind != "chart")


def slide_identifier(config: dict[str, str], number: int) -> str:
    authored = config.get("id", "").strip()
    if authored:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", authored).strip("-")
        if cleaned:
            return cleaned
    return f"p{number}"


def resolve_layout(kind: str, requested: str, media: list[Media], blocks: list[Block], messages: BuildMessages, slide_no: int) -> str:
    if kind in {"cover", "section"}:
        hero_allowed = {"hero-split", "hero-reverse", "hero-full"}
        if requested in {"", "auto", kind}:
            return "hero-split"
        if requested in hero_allowed:
            return requested
        messages.warn(slide_no, f"{kind} 页面不支持 layout={requested}，已改用 hero-split")
        return "hero-split"
    allowed = {"auto", "text", "split", "media", "gallery", "table", "chart"}
    if requested not in allowed:
        messages.warn(slide_no, f"layout={requested} 不受支持，已改用 auto")
        requested = "auto"
    text_length = body_text_length(blocks)
    charts = [block for block in blocks if block.kind == "chart"]
    if requested == "chart" and not charts:
        messages.warn(slide_no, "layout=chart 但页面没有 chart 代码块，已改用 auto")
        requested = "auto"
    if requested == "chart" or (requested == "auto" and charts):
        return "chart"
    if requested == "table":
        if not any(block.kind == "table" for block in blocks):
            messages.warn(slide_no, "layout=table 但页面没有 Markdown 表格，已改用 auto")
            requested = "auto"
        else:
            return "table"
    if requested == "text":
        return "text"
    if requested == "gallery":
        if not media:
            messages.warn(slide_no, "layout=gallery 但页面没有图片，已改用 auto")
            requested = "auto"
        else:
            return "gallery"
    if requested == "split":
        return "split"
    if requested == "media":
        if text_length > 96 or len(blocks) > 1:
            messages.warn(slide_no, "满幅图片页文字超过两行容量，已自动回退为图文左右布局")
            return "split"
        return "media"
    if not media:
        if len(blocks) == 1 and blocks[0].kind == "table":
            return "table"
        return "text"
    if len(media) >= 2:
        return "gallery"
    ratio = media[0].ratio
    if 1.35 <= ratio <= 2.2 and text_length <= 96 and len(blocks) <= 1:
        return "media"
    return "split"


def parse_slide(chunk: str, number: int, deck: dict[str, object], source_dir: Path, output_dir: Path, messages: BuildMessages) -> Slide:
    config, cleaned = clean_directive(chunk)
    title, subtitle, body = pop_headings(cleaned)
    kind = config.get("type", "content").lower()
    if kind not in {"cover", "section", "content"}:
        messages.warn(number, f"type={kind} 不受支持，已改用 content")
        kind = "content"
    if not title:
        messages.error(number, "页面缺少一级标题（# 标题）")
        title = f"未命名页面 {number}"
    media, body_without_media = extract_media(body, source_dir, output_dir, messages, number)
    blocks = parse_blocks(body_without_media, messages, number)
    requested = config.get("layout", "auto").lower()
    resolved = resolve_layout(kind, requested, media, blocks, messages, number)
    section = config.get("section", "") or str(deck.get("default-section", ""))
    return Slide(number, slide_identifier(config, number), kind, title, subtitle, section, requested, resolved, config, media, blocks, body_without_media)


def normalize_region(value: object, messages: BuildMessages, slide_no: int, name: str) -> dict[str, int] | None:
    if not isinstance(value, dict):
        messages.warn(slide_no, f"编辑器区域 {name} 不是对象，已忽略")
        return None
    try:
        x = round(float(value.get("x", 0)))
        y = round(float(value.get("y", 0)))
        width = round(float(value.get("width", value.get("w", 0))))
        height = round(float(value.get("height", value.get("h", 0))))
    except (TypeError, ValueError):
        messages.warn(slide_no, f"编辑器区域 {name} 含非数字坐标，已忽略")
        return None
    width = max(48, min(STAGE_WIDTH, width))
    height = max(48, min(STAGE_HEIGHT, height))
    x = max(0, min(STAGE_WIDTH - width, x))
    y = max(0, min(STAGE_HEIGHT - height, y))
    return {"x": x, "y": y, "width": width, "height": height}


def clamp_region_to_content(region: dict[str, int], content: dict[str, int]) -> dict[str, int]:
    width = max(48, min(content["width"], region["width"]))
    height = max(48, min(content["height"], region["height"]))
    x = max(content["x"], min(content["x"] + content["width"] - width, region["x"]))
    y = max(content["y"], min(content["y"] + content["height"] - height, region["y"]))
    return {"x": x, "y": y, "width": width, "height": height}


def normalize_typography(value: object, messages: BuildMessages, slide_no: int) -> dict[str, object] | None:
    if not isinstance(value, dict):
        messages.warn(slide_no, "编辑器 typography 不是对象，已忽略")
        return None
    result: dict[str, object] = {}
    if "lineHeight" in value:
        try:
            line_height = float(value["lineHeight"])
        except (TypeError, ValueError):
            messages.warn(slide_no, "正文行间距不是数字，已忽略")
        else:
            result["lineHeight"] = round(max(1.1, min(1.8, line_height)), 2)
    if "color" in value:
        color = str(value["color"]).strip()
        if HEX_COLOR_RE.fullmatch(color):
            if len(color) == 4:
                color = "#" + "".join(character * 2 for character in color[1:])
            result["color"] = color.upper()
        else:
            messages.warn(slide_no, f"正文颜色 {color!r} 不是 #RGB 或 #RRGGBB，已忽略")
    if "bold" in value:
        raw_bold = value["bold"]
        if isinstance(raw_bold, bool):
            result["bold"] = raw_bold
        elif isinstance(raw_bold, (int, float)):
            result["bold"] = raw_bold >= 600
        else:
            result["bold"] = str(raw_bold).strip().lower() in {"true", "yes", "on", "bold", "700"}
    return result or None


def normalize_animation(value: object, messages: BuildMessages, slide_no: int) -> dict[str, object] | None:
    if not isinstance(value, dict):
        messages.warn(slide_no, "编辑器 animation 不是对象，已忽略")
        return None
    mode = str(value.get("mode", "custom")).lower()
    if mode not in {"auto", "custom"}:
        messages.warn(slide_no, f"动画 mode={mode} 不受支持，已改用 auto")
        mode = "auto"
    raw_order = value.get("order", [])
    order: list[str] = []
    if isinstance(raw_order, list):
        for item in raw_order:
            key = str(item)
            if REVEAL_KEY_RE.fullmatch(key) and key not in order:
                order.append(key)
    elif raw_order:
        messages.warn(slide_no, "动画 order 必须是数组，已使用默认顺序")
    try:
        step_ms = round(float(value.get("stepMs", 120)))
    except (TypeError, ValueError):
        step_ms = 120
        messages.warn(slide_no, "动画 stepMs 不是数字，已使用 120ms")
    return {"mode": mode, "order": order[:64], "stepMs": max(40, min(600, step_ms))}


def load_layout_overrides(path: Path | None, messages: BuildMessages) -> dict[str, object]:
    if path is None:
        return {"schemaVersion": EDITOR_SCHEMA_VERSION, "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT}, "slides": {}}
    if not path.exists():
        messages.error(None, f"布局覆盖文件不存在：{path}")
        return {"schemaVersion": EDITOR_SCHEMA_VERSION, "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT}, "slides": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        messages.error(None, f"无法读取布局覆盖文件：{error}")
        return {"schemaVersion": EDITOR_SCHEMA_VERSION, "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT}, "slides": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("slides", {}), dict):
        messages.error(None, "布局覆盖文件必须包含 slides 对象")
        return {"schemaVersion": EDITOR_SCHEMA_VERSION, "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT}, "slides": {}}
    version = str(payload.get("schemaVersion", EDITOR_SCHEMA_VERSION))
    if version != EDITOR_SCHEMA_VERSION:
        messages.warn(None, f"布局覆盖 schemaVersion={version}，当前生成器为 {EDITOR_SCHEMA_VERSION}；将按兼容模式读取")
    return payload


def apply_layout_overrides(slides: list[Slide], payload: dict[str, object], messages: BuildMessages) -> list[str]:
    entries = payload.get("slides", {})
    if not isinstance(entries, dict):
        return []
    stage = payload.get("stage", {})
    try:
        source_width = float(stage.get("width", STAGE_WIDTH)) if isinstance(stage, dict) else STAGE_WIDTH
        source_height = float(stage.get("height", STAGE_HEIGHT)) if isinstance(stage, dict) else STAGE_HEIGHT
        if source_width <= 0 or source_height <= 0:
            raise ValueError
    except (TypeError, ValueError):
        messages.warn(None, "布局覆盖 stage 尺寸无效，已按 1920×1080 解释坐标")
        source_width, source_height = STAGE_WIDTH, STAGE_HEIGHT
    scale_x = STAGE_WIDTH / source_width
    scale_y = STAGE_HEIGHT / source_height
    if not math.isclose(scale_x, 1.0) or not math.isclose(scale_y, 1.0):
        messages.warn(None, f"布局覆盖基于 {source_width:g}×{source_height:g}，坐标已换算为 1920×1080")

    def scaled(value: object, factor: float) -> object:
        try:
            return float(value) * factor
        except (TypeError, ValueError):
            return value

    applied: list[str] = []
    for slide in slides:
        raw = entries.get(slide.slide_id)
        if raw is None:
            raw = entries.get(f"P{slide.number}")
        if not isinstance(raw, dict):
            continue
        override: dict[str, object] = {}
        requested = str(raw.get("layout", slide.layout_requested)).lower()
        resolved = resolve_layout(slide.kind, requested, slide.media, slide.blocks, messages, slide.number)
        if "layout" in raw:
            slide.layout_requested = requested
            slide.layout_resolved = resolved
            override["layout"] = resolved
        regions: dict[str, dict[str, int]] = {}
        raw_regions = raw.get("regions", {})
        if isinstance(raw_regions, dict):
            for name in ("content", "visual", "copy"):
                if name in raw_regions:
                    raw_region = raw_regions[name]
                    if isinstance(raw_region, dict) and (not math.isclose(scale_x, 1.0) or not math.isclose(scale_y, 1.0)):
                        raw_region = {
                            **raw_region,
                            "x": scaled(raw_region.get("x", 0), scale_x),
                            "y": scaled(raw_region.get("y", 0), scale_y),
                            "width": scaled(raw_region.get("width", raw_region.get("w", 0)), scale_x),
                            "height": scaled(raw_region.get("height", raw_region.get("h", 0)), scale_y),
                        }
                    normalized = normalize_region(raw_region, messages, slide.number, name)
                    if normalized:
                        regions[name] = normalized
        if "content" in regions:
            for name in ("visual", "copy"):
                if name in regions:
                    regions[name] = clamp_region_to_content(regions[name], regions["content"])
        if regions:
            override["regions"] = regions
        if "typography" in raw:
            typography = normalize_typography(raw.get("typography"), messages, slide.number)
            if typography:
                override["typography"] = typography
        if "animation" in raw:
            animation = normalize_animation(raw.get("animation"), messages, slide.number)
            if animation:
                override["animation"] = animation
        if override:
            override["title"] = slide.title
            override["sourcePage"] = f"P{slide.number}"
            slide.editor_override = override
            applied.append(slide.slide_id)
    known_keys = {slide.slide_id for slide in slides} | {f"P{slide.number}" for slide in slides}
    stale = sorted(str(key) for key in entries if str(key) not in known_keys)
    if stale:
        messages.warn(None, f"布局覆盖包含 {len(stale)} 个未匹配页面 ID：{', '.join(stale[:5])}")
    return applied


def visual_media(media: Media, fit: str = "contain", active: bool = True, panel_index: int | None = None) -> str:
    panel = f' data-media-panel="{panel_index}"' if panel_index is not None else ""
    active_class = " active" if active else ""
    caption = f"<figcaption>{html.escape(media.caption)}</figcaption>" if media.caption else ""
    return (
        f'<figure class="card media-figure visual-widget{active_class}" data-visual-widget="image" tabindex="0"{panel}>'
        '<div class="visual-widget-content" data-visual-content>'
        f'<img src="{html.escape(media.output_source, quote=True)}" alt="{html.escape(media.alt, quote=True)}" '
        f'style="object-fit:{html.escape(fit)}" draggable="false">'
        f'</div>{caption}</figure>'
    )


def render_copy(blocks: list[Block], class_name: str = "text-grid") -> str:
    if not blocks:
        return '<div class="empty-copy" aria-hidden="true"></div>'
    count = min(len(blocks), 7)
    focus = " focus-grid" if len(blocks) == 1 and blocks[0].kind in {"section", "callout"} else ""
    return f'<div class="{class_name} count-{count}{focus}">' + "".join(block.html for block in blocks) + "</div>"


def render_footer(slide: Slide, sections: list[str]) -> str:
    show_default = slide.kind == "content"
    if not bool_config(slide.config, "footer", show_default) or not sections:
        return ""
    cells = "".join(f'<span class="{"active" if name == slide.section else ""}">{html.escape(name)}</span>' for name in sections)
    return f'<footer class="section-footer" style="--section-count:{len(sections)}">{cells}</footer>'


def render_placeholder(label: str) -> str:
    return (
        '<figure class="visual-placeholder" aria-label="空白图片占位">'
        '<span class="placeholder-mark" aria-hidden="true"></span>'
        f'<figcaption>{html.escape(label)}<small>替换为项目自己的视觉素材</small></figcaption></figure>'
    )


def render_hero(slide: Slide, deck: dict[str, object]) -> str:
    kicker = str(deck.get("kicker", "")) if slide.kind == "cover" else (slide.section or "SECTION")
    meta_parts = [str(deck.get(key, "")) for key in ("author", "date") if deck.get(key)]
    meta = " · ".join(meta_parts)
    if slide.media:
        visual = visual_media(slide.media[0], slide.config.get("image-fit", "cover"))
    else:
        visual = render_placeholder("封面图占位" if slide.kind == "cover" else "章节图占位")
    return (
        f'<div class="hero-shell hero-{slide.kind} hero-layout-{slide.layout_resolved}"><div class="hero-copy reveal">'
        f'<p class="hero-kicker">{html.escape(kicker)}</p><h1>{render_inline(slide.title)}</h1>'
        f'<p class="hero-subtitle">{render_inline(slide.subtitle)}</p>'
        f'<p class="hero-meta">{html.escape(meta)}</p></div><div class="hero-visual reveal">{visual}</div></div>'
    )


def render_gallery(slide: Slide) -> str:
    fit = slide.config.get("image-fit", "contain")
    if len(slide.media) >= 3:
        buttons = "".join(f'<button type="button" class="{"active" if index == 0 else ""}" data-media-target="{index}" aria-label="查看图片 {index + 1}">{index + 1}</button>' for index in range(len(slide.media)))
        panels = "".join(visual_media(media, fit, index == 0, index) for index, media in enumerate(slide.media))
        gallery = f'<div class="media-tabs" data-media-tabs>{panels}<div class="media-tab-list">{buttons}</div></div>'
    else:
        gallery = '<div class="media-grid count-2">' + "".join(visual_media(media, fit) for media in slide.media) + "</div>"
    if slide.blocks:
        return f'<div class="gallery-layout"><div class="gallery-stage">{gallery}</div>{render_copy(slide.blocks, "gallery-copy")}</div>'
    return f'<div class="gallery-layout gallery-only"><div class="gallery-stage">{gallery}</div></div>'


def render_content(slide: Slide) -> str:
    fit = slide.config.get("image-fit", "contain")
    position = slide.config.get("image-position", "left").lower()
    if slide.layout_resolved == "text":
        return render_copy(slide.blocks)
    if slide.layout_resolved == "table":
        return '<div class="table-layout">' + "".join(block.html for block in slide.blocks) + "</div>"
    if slide.layout_resolved == "chart":
        charts = [block.html for block in slide.blocks if block.kind == "chart"]
        copy = [block for block in slide.blocks if block.kind != "chart"]
        return f'<div class="chart-layout"><div class="chart-stage">{"".join(charts)}</div>{render_copy(copy, "chart-copy")}</div>'
    if slide.layout_resolved == "gallery":
        return render_gallery(slide)
    if slide.layout_resolved == "media":
        media_html = visual_media(slide.media[0], fit) if slide.media else render_placeholder("内容图片占位")
        caption = render_copy(slide.blocks, "wide-copy")
        return f'<div class="wide-media-layout"><div class="wide-media-stage">{media_html}</div>{caption}</div>'
    media_html = visual_media(slide.media[0], fit) if slide.media else render_placeholder("内容图片占位")
    copy_html = render_copy(slide.blocks, "split-copy")
    reverse = " media-right" if position == "right" else ""
    ratio = slide.media[0].ratio if slide.media else 1.0
    shape = "portrait" if ratio < .72 else "square" if ratio < 1.35 else "landscape"
    return f'<div class="split-layout {shape}{reverse}"><div class="split-media">{media_html}</div>{copy_html}</div>'


def render_slide(slide: Slide, deck: dict[str, object], sections: list[str]) -> str:
    classes = f"slide {slide.kind}-slide layout-{slide.layout_resolved} density-{slide.config.get('density', str(deck.get('density', 'reading')))}"
    if slide.kind in {"cover", "section"}:
        inner = render_hero(slide, deck)
    else:
        subtitle = f'<p class="subtitle">{render_inline(slide.subtitle)}</p>' if slide.subtitle else ""
        inner = (
            f'<header class="slide-header reveal"><h1>{render_inline(slide.title)}</h1>{subtitle}</header>'
            f'<div class="content">{render_content(slide)}</div>{render_footer(slide, sections)}'
        )
    return (
        f'<section class="{classes}" data-title="{html.escape(slide.title, quote=True)}" '
        f'data-slide-id="{html.escape(slide.slide_id, quote=True)}" data-source-page="P{slide.number}" '
        f'data-slide-kind="{html.escape(slide.kind, quote=True)}" data-media-count="{len(slide.media)}" '
        f'data-block-count="{len(slide.blocks)}" data-text-length="{body_text_length(slide.blocks)}" '
        f'data-has-table="{str(any(block.kind == "table" for block in slide.blocks)).lower()}" '
        f'data-has-chart="{str(any(block.kind == "chart" for block in slide.blocks)).lower()}" '
        f'data-layout-requested="{html.escape(slide.layout_requested)}" '
        f'data-layout-resolved="{html.escape(slide.layout_resolved)}">{inner}</section>'
    )


def validate_slide(slide: Slide, density: str, messages: BuildMessages) -> None:
    limit = 760 if density == "reading" else 430
    length = body_text_length(slide.blocks)
    if length > limit:
        messages.warn(slide.number, f"正文约 {length} 字，超过 {density} 模式建议上限 {limit}；建议拆页")
    if len(slide.title) > 28:
        messages.warn(slide.number, "标题偏长，建议控制在 28 个中英文字符以内")
    if len(slide.subtitle) > 38:
        messages.warn(slide.number, "副标题偏长，建议控制在一行（约 38 字）")
    if len(slide.blocks) > 6:
        messages.warn(slide.number, f"页面包含 {len(slide.blocks)} 个内容块，建议拆为两页")
    for block in slide.blocks:
        if block.kind == "table" and int(block.meta.get("rows", 0)) > 8:
            messages.warn(slide.number, "表格超过 8 行，投影阅读性可能不足")
    if slide.layout_resolved == "media" and length > 96:
        messages.warn(slide.number, "满幅图片页说明文字可能超过两行")


def collect_sections(deck: dict[str, object], slides: list[Slide], messages: BuildMessages) -> list[str]:
    authored = deck.get("sections")
    if isinstance(authored, list):
        sections = [str(item) for item in authored]
    elif authored:
        sections = [item.strip() for item in str(authored).split("|") if item.strip()]
    else:
        sections = list(dict.fromkeys(slide.section for slide in slides if slide.section))
    if len(sections) > 7:
        messages.warn(None, f"章节导航共 {len(sections)} 项；建议合并到 7 项以内")
    return sections


def build(source_path: Path, output_path: Path, strict: bool = False, overrides_path: Path | None = None) -> int:
    messages = BuildMessages()
    if not TEMPLATE_PATH.exists():
        print(f"ERROR: template missing: {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR: cannot read Markdown source {source_path}: {error}", file=sys.stderr)
        return 2
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR: cannot read template {TEMPLATE_PATH}: {error}", file=sys.stderr)
        return 2
    deck, chunks = split_deck_source(source)
    if not chunks:
        print("ERROR: no slides found", file=sys.stderr)
        return 2
    slides = [parse_slide(chunk, index, deck, source_path.parent, output_path.parent, messages) for index, chunk in enumerate(chunks, 1)]
    seen_ids: set[str] = set()
    for slide in slides:
        if slide.slide_id in seen_ids:
            messages.error(slide.number, f"页面 id={slide.slide_id} 重复；编辑器覆盖要求每页 ID 唯一")
        seen_ids.add(slide.slide_id)
    resolved_overrides_path = overrides_path
    if resolved_overrides_path is None:
        automatic = source_path.with_suffix(".layout.json")
        if automatic.exists():
            resolved_overrides_path = automatic
    editor_payload = load_layout_overrides(resolved_overrides_path, messages)
    applied_overrides = apply_layout_overrides(slides, editor_payload, messages)
    density = str(deck.get("density", "reading")).lower()
    if density not in {"reading", "speaking"}:
        messages.warn(None, f"density={density} 不受支持，已使用 reading")
        density = "reading"
        deck["density"] = density
    for slide in slides:
        validate_slide(slide, slide.config.get("density", density), messages)
    sections = collect_sections(deck, slides, messages)
    rendered = "\n".join(render_slide(slide, deck, sections) for slide in slides)
    title = str(deck.get("title", slides[0].title))
    embedded_editor_config = {
        "schemaVersion": EDITOR_SCHEMA_VERSION,
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "deckTitle": title,
        "source": source_path.name,
        "slides": {slide.slide_id: slide.editor_override for slide in slides if slide.editor_override},
    }
    editor_json = json.dumps(embedded_editor_config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    replacements = {
        "{{DECK_TITLE}}": html.escape(title),
        "{{DECK_TITLE_ATTR}}": html.escape(title, quote=True),
        "{{DECK_TITLE_JSON}}": json.dumps(title, ensure_ascii=False).replace("<", "\\u003c"),
        "{{LANG}}": html.escape(str(deck.get("lang", "zh-CN")), quote=True),
        "{{SLIDES}}": rendered,
        "{{SLIDE_COUNT}}": str(len(slides)),
        "{{OUTPUT_FILENAME}}": html.escape(output_path.name, quote=True),
        "{{OUTPUT_FILENAME_JSON}}": json.dumps(output_path.name, ensure_ascii=False).replace("<", "\\u003c"),
        "{{SOURCE_FILENAME}}": html.escape(source_path.name, quote=True),
        "{{SOURCE_FILENAME_JSON}}": json.dumps(source_path.name, ensure_ascii=False).replace("<", "\\u003c"),
        "{{OVERRIDES_FILENAME}}": html.escape(source_path.with_suffix(".layout.json").name, quote=True),
        "{{OVERRIDES_FILENAME_JSON}}": json.dumps(source_path.with_suffix(".layout.json").name, ensure_ascii=False).replace("<", "\\u003c"),
        "{{EDITOR_CONFIG}}": editor_json,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    report = {
        "source": os.path.relpath(source_path, ROOT),
        "output": os.path.relpath(output_path, ROOT),
        "slides": len(slides),
        "layouts": {str(slide.number): slide.layout_resolved for slide in slides},
        "layoutOverrides": {
            "source": os.path.relpath(resolved_overrides_path, ROOT) if resolved_overrides_path else None,
            "appliedSlides": applied_overrides,
        },
        "warnings": messages.warnings,
        "errors": messages.errors,
    }
    report_path = output_path.with_suffix(".build.json")
    try:
        write_text_atomic(output_path, template)
        write_text_atomic(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except OSError as error:
        print(f"ERROR: cannot write build artifacts: {error}", file=sys.stderr)
        return 2
    for warning in messages.warnings:
        print(f"WARNING: {warning}")
    for error in messages.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(f"Built {len(slides)} slides: {output_path}")
    print(f"Build report: {report_path}")
    if messages.errors or (strict and messages.warnings):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build 1920×1080 HTML slides from structured Markdown")
    parser.add_argument(
        "source",
        nargs="?",
        default="examples/basic/slides.md",
        type=Path,
        help="Markdown source (default: examples/basic/slides.md)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="examples/basic/index.html",
        type=Path,
        help="HTML output (default: examples/basic/index.html)",
    )
    parser.add_argument("--overrides", type=Path, help="layout JSON exported by editor mode; defaults to <source>.layout.json when present")
    parser.add_argument("--strict", action="store_true", help="treat design warnings as build failures")
    args = parser.parse_args()
    overrides = args.overrides.resolve() if args.overrides else None
    return build(args.source.resolve(), args.output.resolve(), args.strict, overrides)


if __name__ == "__main__":
    raise SystemExit(main())
