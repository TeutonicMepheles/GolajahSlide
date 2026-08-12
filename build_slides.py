#!/usr/bin/env python3
"""Build a fixed-stage HTML slide deck from the project's Markdown dialect.

The core compiler intentionally uses only the Python standard library. Optional
Mermaid and Excalidraw asset generation is delegated to the pinned Node build
toolchain, while the final deck keeps deterministic, dependency-free inline SVG.
The Markdown dialect supports headings, lists, tables, callouts, code, images,
lightweight charts and build-time diagrams.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "deck.html"
WEB_FEATURE_ROOT = ROOT / "src" / "web" / "features"
TEMPLATE_FRAGMENT_PATHS = {
    "{{PRESENTER_FOCUS_CSS}}": WEB_FEATURE_ROOT / "presenter-focus" / "style.css",
    "{{PRESENTER_FOCUS_RUNTIME}}": WEB_FEATURE_ROOT / "presenter-focus" / "runtime.js",
}
STAGE_WIDTH = 1920
STAGE_HEIGHT = 1080
DIAGRAM_STAGE_WIDTH = 1840
DIAGRAM_STAGE_HEIGHT = 800
DIAGRAM_MIN_FONT_SIZE = 28.0
EDITOR_SCHEMA_VERSION = "1.0"
IMAGE_RE = re.compile(r'^!\[([^\]]*)\]\((\S+?)(?:\s+["\']([^"\']*)["\'])?\)\s*$')
DIRECTIVE_RE = re.compile(r"<!--\s*slide\s*(.*?)-->", re.I | re.S)
TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
LIST_RE = re.compile(r"^\s*([-*+] |\d+[.)] )(.*)$")
INLINE_TOKEN_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|==[^=\n]+==|\[[^\]]+\]\([^)]+\))")
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
REVEAL_KEY_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
ARCHSCRIBE_FENCE_RE = re.compile(r"(?ms)^```archscribe[ \t]*\n(.*?)^```[ \t]*$")
MERMAID_FENCE_RE = re.compile(r"(?ms)^```mermaid[ \t]*\n(.*?)^```[ \t]*$")
EXCALIDRAW_FENCE_RE = re.compile(r"(?ms)^```excalidraw[ \t]*\n(.*?)^```[ \t]*$")
REMOTE_ASSET_PREFIXES = ("http://", "https://", "data:")
DIAGRAM_BLOCK_KINDS = {"chart", "mermaid", "excalidraw", "archscribe"}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
SLIDE_FONT_STACK = '"PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif'

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


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


def relative_asset_href(path: Path, output_dir: Path) -> str:
    try:
        return Path(os.path.relpath(path, output_dir)).as_posix()
    except ValueError:
        return path.as_uri()


def format_report_path(path: Path) -> str:
    try:
        return Path(os.path.relpath(path, ROOT)).as_posix()
    except ValueError:
        return path.as_posix()


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


def parse_mermaid_fence(raw: str) -> tuple[dict[str, object], str]:
    """Split Slide-only metadata from Mermaid syntax without stealing Mermaid frontmatter."""
    lines = raw.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None or lines[first].strip().lower() != "@slide":
        return {}, raw.strip()
    end = next(
        (index for index in range(first + 1, len(lines)) if lines[index].strip().lower() == "@end"),
        None,
    )
    if end is None:
        return {"metadata-error": "mermaid @slide 缺少 @end"}, ""
    return parse_key_values("\n".join(lines[first + 1 : end])), "\n".join(lines[end + 1 :]).strip()


def sha256_text(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def svg_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def svg_view_box(root: ET.Element) -> tuple[float, float, float, float] | None:
    raw = root.get("viewBox", "").strip()
    parts = [part for part in re.split(r"[\s,]+", raw) if part]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (float(part) for part in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def extract_svg_font_sizes(source: str) -> list[float]:
    sizes: list[float] = []
    pattern = re.compile(r"font-size\s*(?:=|:)\s*[\"']?\s*([0-9]+(?:\.[0-9]+)?)", re.I)
    style_blocks = re.findall(r"(?is)<style\b[^>]*>(.*?)</style>", source)
    source_without_styles = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", source)
    for match in pattern.finditer(source_without_styles):
        value = float(match.group(1))
        if value > 0:
            sizes.append(value)
    root_match = re.search(r"(?is)<svg\b[^>]*\bid=[\"']([^\"']+)[\"']", source)
    if root_match:
        root_selector = "#" + root_match.group(1)
        for stylesheet in style_blocks:
            for rule in re.finditer(r"(?s)([^{}]+)\{([^{}]*)\}", stylesheet):
                selectors, declarations = rule.groups()
                normalized = [selector.strip() for selector in selectors.split(",")]
                if root_selector not in normalized and f"{root_selector} svg" not in normalized:
                    continue
                match = pattern.search(declarations)
                if match and float(match.group(1)) > 0:
                    sizes.append(float(match.group(1)))
    return sizes


def strip_svg_dimensions(style: str) -> str:
    kept = []
    for declaration in style.split(";"):
        key = declaration.split(":", 1)[0].strip().lower()
        if key not in {"width", "height", "max-width", "max-height"} and declaration.strip():
            kept.append(declaration.strip())
    return ";".join(kept)


def sanitize_inline_svg(
    source: str,
    engine: str,
    unique_prefix: str,
    title: str,
    description: str,
    messages: BuildMessages,
    slide_no: int,
) -> str:
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        messages.error(slide_no, f"{engine} SVG 无法解析：{error}")
        return '<svg class="diagram-svg" viewBox="0 0 16 9" role="img"></svg>'
    if svg_local_name(root.tag) != "svg":
        messages.error(slide_no, f"{engine} 产物根元素不是 SVG")
        return '<svg class="diagram-svg" viewBox="0 0 16 9" role="img"></svg>'
    if svg_view_box(root) is None:
        messages.error(slide_no, f"{engine} SVG 缺少有效 viewBox")

    forbidden = {"script", "foreignobject", "iframe", "object", "embed"}

    def clean_children(parent: ET.Element) -> None:
        for child in list(parent):
            if svg_local_name(child.tag) in forbidden:
                parent.remove(child)
            else:
                clean_children(child)

    clean_children(root)
    ids: dict[str, str] = {}
    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            new_id = f"{unique_prefix}-{re.sub(r'[^0-9A-Za-z_-]+', '-', old_id)}"
            ids[old_id] = new_id
            element.set("id", new_id)
        for attribute in list(element.attrib):
            local = svg_local_name(attribute)
            value = element.attrib[attribute]
            if local.startswith("on"):
                del element.attrib[attribute]
            elif local in {"href", "src"} and re.match(r"(?i)\s*(?:https?:|javascript:|data:text/html)", value):
                del element.attrib[attribute]
                messages.warn(slide_no, f"{engine} SVG 中的外部引用已移除")
    id_replacements = sorted(ids.items(), key=lambda item: len(item[0]), reverse=True)
    for element in root.iter():
        for attribute, value in list(element.attrib.items()):
            updated = value
            for old_id, new_id in id_replacements:
                updated = updated.replace(f"url(#{old_id})", f"url(#{new_id})")
                if updated == f"#{old_id}":
                    updated = f"#{new_id}"
            element.set(attribute, updated)
        if svg_local_name(element.tag) == "style" and element.text:
            updated_style = element.text
            for old_id, new_id in id_replacements:
                updated_style = updated_style.replace(f"#{old_id}", f"#{new_id}")
            updated_style = re.sub(r"(?is)@import\s+[^;]+;", "", updated_style)
            updated_style = re.sub(r"(?i)url\(\s*[\"']?https?://[^)]+\)", "none", updated_style)
            element.text = updated_style

    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    if "style" in root.attrib:
        root.set("style", strip_svg_dimensions(root.attrib["style"]))
    classes = [item for item in root.get("class", "").split() if item]
    if "diagram-svg" not in classes:
        classes.append("diagram-svg")
    root.set("class", " ".join(classes))
    if not root.get("id"):
        root.set("id", f"{unique_prefix}-root")
    root.set("preserveAspectRatio", "xMidYMid meet")
    root.set("role", "img")
    root.set("focusable", "false")
    root.set("data-diagram-engine", engine)

    title_id = f"{unique_prefix}-title"
    description_id = f"{unique_prefix}-description"
    root.set("aria-labelledby", f"{title_id} {description_id}")
    for child in list(root):
        if svg_local_name(child.tag) in {"title", "desc"}:
            root.remove(child)
    title_node = ET.Element(f"{{{SVG_NS}}}title", {"id": title_id})
    title_node.text = title
    description_node = ET.Element(f"{{{SVG_NS}}}desc", {"id": description_id})
    description_node.text = description
    style_node = ET.Element(f"{{{SVG_NS}}}style", {"data-slide-diagram-style": "true"})
    root_selector = "#" + root.get("id", f"{unique_prefix}-root")
    style_node.text = f'{root_selector} text, {root_selector} tspan {{ font-family: {SLIDE_FONT_STACK} !important; }}'
    root.insert(0, description_node)
    root.insert(0, title_node)
    root.insert(2, style_node)
    return ET.tostring(root, encoding="unicode")


def read_diagram_sidecar(svg_path: Path) -> dict[str, object]:
    path = svg_path.with_suffix(".diagram-build.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def split_deck_source(source: str) -> tuple[dict[str, object], list[str]]:
    normalized = source.replace("\r\n", "\n").lstrip("\ufeff")
    deck: dict[str, object] = {}
    if normalized.startswith("---\n"):
        end = normalized.find("\n---", 4)
        if end != -1:
            deck = parse_key_values(normalized[4:end])
            normalized = normalized[end + 4 :].lstrip("\n")
    chunks: list[str] = []
    current: list[str] = []
    fence: str | None = None
    for line in normalized.splitlines():
        stripped = line.strip()
        if fence:
            current.append(line)
            if stripped.startswith(fence):
                fence = None
            continue
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            fence = fence_match.group(1)[0] * len(fence_match.group(1))
            current.append(line)
            continue
        if stripped == "---":
            chunk = "\n".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = []
            continue
        current.append(line)
    chunk = "\n".join(current).strip()
    if chunk:
        chunks.append(chunk)
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
            output_source = relative_asset_href(absolute, output_dir)
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
        elif token.startswith("=="):
            pieces.append(f'<mark data-presenter-text="inline">{render_inline(token[2:-2])}</mark>')
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
        '<article class="card table-card" data-presenter-focus data-visual-widget="table" tabindex="0">'
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


def parse_svg_diagram(
    config: dict[str, object],
    engine: str,
    source_dir: Path,
    messages: BuildMessages,
    slide_no: int,
    stage_size: tuple[int, int],
) -> Block:
    raw_source = str(config.get("src", "")).strip()
    title = str(config.get("title", f"{engine} 流程图")).strip() or f"{engine} 流程图"
    alt = str(config.get("alt", title)).strip() or title
    caption = str(config.get("caption", "")).strip()
    metrics: dict[str, object] = {"engine": engine, "src": raw_source}
    if not raw_source:
        messages.error(slide_no, f"{engine} 代码块缺少 src SVG 输出路径")
        source = '<svg class="diagram-svg" viewBox="0 0 16 9"></svg>'
        svg_path = None
    elif raw_source.startswith(REMOTE_ASSET_PREFIXES):
        messages.error(slide_no, f"{engine} 必须使用本地 SVG，以便内联并执行质量校验")
        source = '<svg class="diagram-svg" viewBox="0 0 16 9"></svg>'
        svg_path = None
    else:
        svg_path = (source_dir / raw_source).resolve()
        if svg_path.suffix.lower() != ".svg":
            messages.error(slide_no, f"{engine} src 必须是 .svg：{raw_source}")
        try:
            source = svg_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            messages.error(slide_no, f"{engine} SVG 不存在或无法读取：{raw_source}（{error}）")
            source = '<svg class="diagram-svg" viewBox="0 0 16 9"></svg>'

    sidecar = read_diagram_sidecar(svg_path) if svg_path and svg_path.is_file() else {}
    if svg_path and svg_path.is_file():
        recorded_hash = str(sidecar.get("svgSha256", ""))
        actual_hash = sha256_file(svg_path)
        if not sidecar:
            messages.error(slide_no, f"{engine} SVG 缺少 .diagram-build.json 质量报告；请运行 --render-diagrams")
        elif recorded_hash != actual_hash:
            messages.error(slide_no, f"{engine} SVG 与质量报告不一致；请重新运行 --render-diagrams")
        if sidecar.get("engine") and sidecar.get("engine") != engine:
            messages.error(slide_no, f"{engine} SVG 的质量报告引擎不匹配")

    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        root = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": "0 0 16 9"})
    view_box = svg_view_box(root)
    font_sizes = extract_svg_font_sizes(source)
    fallback_font = sidecar.get("minimumSourceFontSize")
    if font_sizes:
        source_min = min(font_sizes)
    elif isinstance(fallback_font, (int, float)) and float(fallback_font) > 0:
        source_min = float(fallback_font)
    else:
        source_min = 0.0
        messages.error(slide_no, f"{engine} SVG 中没有可校验的字号")
    projected = 0.0
    if view_box:
        _, _, view_width, view_height = view_box
        projected = source_min * min(stage_size[0] / view_width, stage_size[1] / view_height)
        metrics.update({
            "viewBoxWidth": round(view_width, 2),
            "viewBoxHeight": round(view_height, 2),
        })
    try:
        required_font = float(config.get("min-font-size", DIAGRAM_MIN_FONT_SIZE))
    except (TypeError, ValueError):
        required_font = DIAGRAM_MIN_FONT_SIZE
        messages.error(slide_no, f"{engine} min-font-size 必须是数字")
    if projected + 0.05 < required_font:
        messages.error(
            slide_no,
            f"{engine} 最小字号投影后约 {projected:.1f}px，低于 Slide 下限 {required_font:g}px；请减少节点、缩短标签或调整布局",
        )
    metrics.update({
        "sourceMinFontSize": round(source_min, 2),
        "projectedMinFontSize": round(projected, 2),
    })

    try:
        required_margin = float(config.get("safe-margin", 24))
    except (TypeError, ValueError):
        required_margin = 24.0
        messages.error(slide_no, f"{engine} safe-margin 必须是数字")
    recorded_margin = sidecar.get("minimumSafeMargin")
    if isinstance(recorded_margin, (int, float)):
        safe_margin = float(recorded_margin)
        metrics["minimumSafeMargin"] = round(safe_margin, 2)
        if safe_margin + 0.05 < required_margin:
            messages.error(slide_no, f"{engine} SVG 安全边距 {safe_margin:g}px，低于要求 {required_margin:g}px")
    elif svg_path and svg_path.is_file():
        messages.error(slide_no, f"{engine} SVG 质量报告缺少安全边距数据")

    prefix = f"diagram-p{slide_no}-{engine}-{sha256_text(raw_source)[:8]}"
    inline_svg = sanitize_inline_svg(source, engine, prefix, title, alt, messages, slide_no)
    figure_caption = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    markup = (
        '<figure class="card chart-card diagram-card" data-visual-widget="image" '
        f'data-diagram-engine="{html.escape(engine, quote=True)}" tabindex="0" '
        f'aria-label="{html.escape(title, quote=True)}">'
        '<div class="visual-widget-content chart-content diagram-content" data-visual-content>'
        f"{inline_svg}</div>{figure_caption}</figure>"
    )
    return Block(engine, markup, "", metrics)


def parse_mermaid_block(
    raw: str,
    source_dir: Path,
    messages: BuildMessages,
    slide_no: int,
    stage_size: tuple[int, int],
) -> Block:
    config, definition = parse_mermaid_fence(raw)
    if config.get("metadata-error"):
        messages.error(slide_no, str(config["metadata-error"]))
    if not config:
        messages.error(slide_no, "mermaid 代码块必须以 @slide 元数据开头，并以 @end 结束")
    if not definition:
        messages.error(slide_no, "mermaid 代码块缺少图表定义")
    return parse_svg_diagram(config, "mermaid", source_dir, messages, slide_no, stage_size)


def parse_excalidraw_block(
    raw: str,
    source_dir: Path,
    messages: BuildMessages,
    slide_no: int,
    stage_size: tuple[int, int],
) -> Block:
    config = parse_key_values(raw)
    raw_scene = str(config.get("source", "")).strip()
    if not raw_scene:
        messages.error(slide_no, "excalidraw 代码块缺少 source")
    elif raw_scene.startswith(REMOTE_ASSET_PREFIXES):
        messages.error(slide_no, "excalidraw source 必须是本地 .excalidraw 文件")
    else:
        scene_path = (source_dir / raw_scene).resolve()
        if scene_path.suffix.lower() not in {".excalidraw", ".json"}:
            messages.error(slide_no, f"excalidraw source 必须是 .excalidraw 或 .json：{raw_scene}")
        elif not scene_path.is_file():
            messages.error(slide_no, f"excalidraw source 不存在：{raw_scene}")
    return parse_svg_diagram(config, "excalidraw", source_dir, messages, slide_no, stage_size)


def resolve_block_asset(
    raw_source: str,
    source_dir: Path,
    output_dir: Path,
    messages: BuildMessages,
    slide_no: int,
    label: str,
) -> str:
    if raw_source.startswith(REMOTE_ASSET_PREFIXES):
        return raw_source
    absolute = (source_dir / raw_source).resolve()
    if not absolute.exists():
        messages.error(slide_no, f"Archscribe {label}不存在：{raw_source}")
    return relative_asset_href(absolute, output_dir)


def parse_crop_box(value: object) -> tuple[int, int, int, int] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = [part for part in re.split(r"[\s,]+", raw) if part]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (round(float(part)) for part in parts)
    except ValueError:
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    return x, y, width, height


def validate_archscribe_typography(
    config: dict[str, object],
    source_dir: Path,
    messages: BuildMessages,
    slide_no: int,
) -> dict[str, float]:
    raw_source = str(config.get("src", "")).strip()
    raw_poster = str(config.get("poster", "")).strip()
    if not raw_source or raw_source.startswith(REMOTE_ASSET_PREFIXES):
        return {}
    gif_path = (source_dir / raw_source).resolve()
    poster_path = (source_dir / raw_poster).resolve() if raw_poster else gif_path.with_suffix(".png")
    excalidraw_path = gif_path.with_suffix(".excalidraw")
    if not poster_path.is_file() or not excalidraw_path.is_file():
        messages.warn(slide_no, "缺少 PNG 或 Excalidraw，无法校验 Archscribe 在 Slide 中的实际字号")
        return {}
    size = image_size(poster_path)
    if not size:
        messages.warn(slide_no, f"无法读取 Archscribe poster 尺寸：{raw_poster or poster_path.name}")
        return {}
    try:
        payload = json.loads(excalidraw_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        messages.warn(slide_no, f"无法读取 Archscribe Excalidraw 字号：{error}")
        return {}

    crop_raw = str(config.get("crop", "")).strip()
    crop = parse_crop_box(crop_raw)
    mask = parse_crop_box(config.get("mask", ""))
    if crop_raw and crop is None:
        messages.error(slide_no, "archscribe crop 必须是 x,y,width,height 四个非负数")
        return {}
    texts: list[dict[str, object]] = []
    for element in payload.get("elements", []):
        if not isinstance(element, dict) or element.get("type") != "text" or not str(element.get("text", "")).strip():
            continue
        if crop:
            cx = float(element.get("x", 0)) + float(element.get("width", 0)) / 2
            cy = float(element.get("y", 0)) + float(element.get("height", 0)) / 2
            x, y, width, height = crop
            if not (x <= cx <= x + width and y <= cy <= y + height):
                continue
        texts.append(element)
    font_sizes = [float(element.get("fontSize", 0)) for element in texts if float(element.get("fontSize", 0)) > 0]
    if not font_sizes:
        messages.error(slide_no, "Archscribe 交付视口中没有可校验的文字")
        return {}
    source_min = min(font_sizes)
    scale = min(DIAGRAM_STAGE_WIDTH / size[0], DIAGRAM_STAGE_HEIGHT / size[1])
    projected = source_min * scale
    try:
        required = float(config.get("min-font-size", DIAGRAM_MIN_FONT_SIZE))
    except (TypeError, ValueError):
        required = DIAGRAM_MIN_FONT_SIZE
        messages.error(slide_no, "archscribe min-font-size 必须是数字")
    if projected + 0.05 < required:
        messages.error(
            slide_no,
            f"Archscribe 最小字号投影后约 {projected:.1f}px，低于 Slide 下限 {required:g}px；请减少节点、缩短标签或设置 crop",
        )
    safe_margin_result: float | None = None
    if crop:
        try:
            required_margin = float(config.get("safe-margin", 24))
        except (TypeError, ValueError):
            required_margin = 24.0
            messages.error(slide_no, "archscribe safe-margin 必须是数字")
        x, y, width, height = crop
        distances: list[float] = []
        for element in payload.get("elements", []):
            if not isinstance(element, dict):
                continue
            try:
                ex = float(element.get("x", 0))
                ey = float(element.get("y", 0))
                ew = abs(float(element.get("width", 0)))
                eh = abs(float(element.get("height", 0)))
            except (TypeError, ValueError):
                continue
            cx, cy = ex + ew / 2, ey + eh / 2
            if not (x <= cx <= x + width and y <= cy <= y + height):
                continue
            relative_cx, relative_cy = cx - x, cy - y
            if mask and mask[0] <= relative_cx <= mask[0] + mask[2] and mask[1] <= relative_cy <= mask[1] + mask[3]:
                continue
            if ew >= width * 0.85 or eh >= height * 0.85:
                continue
            left, top = ex - x, ey - y
            right, bottom = x + width - (ex + ew), y + height - (ey + eh)
            distances.append(min(left, top, right, bottom))
        if distances:
            safe_margin_result = min(distances)
            if safe_margin_result + 0.05 < required_margin:
                messages.error(
                    slide_no,
                    f"Archscribe 流程主体距裁切边界最小约 {safe_margin_result:.1f}px，低于安全边距 {required_margin:g}px",
                )
    result = {"sourceMinFontSize": round(source_min, 2), "projectedMinFontSize": round(projected, 2)}
    if safe_margin_result is not None:
        result["minimumSafeMargin"] = round(safe_margin_result, 2)
    cache_path = gif_path.with_suffix(".archscribe-build.json")
    try:
        delivery_cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        delivery_cache = {}
    if isinstance(delivery_cache.get("minimumRasterMargin"), (int, float)):
        raster_margin = float(delivery_cache["minimumRasterMargin"])
        result["minimumRasterMargin"] = round(raster_margin, 2)
        try:
            required_raster_margin = float(config.get("safe-margin", 24))
        except (TypeError, ValueError):
            required_raster_margin = 24.0
        if raster_margin + 0.05 < required_raster_margin:
            messages.error(
                slide_no,
                f"Archscribe 动画内容距成品边界最小约 {raster_margin:.1f}px，低于安全边距 {required_raster_margin:g}px",
            )
    return result


def parse_archscribe(
    raw: str,
    source_dir: Path,
    output_dir: Path,
    messages: BuildMessages,
    slide_no: int,
) -> Block:
    config = parse_key_values(raw)
    raw_source = str(config.get("src", "")).strip()
    raw_spec = str(config.get("spec", "")).strip()
    raw_poster = str(config.get("poster", "")).strip()
    title = str(config.get("title", "动态流程图")).strip() or "动态流程图"
    alt = str(config.get("alt", title)).strip() or title
    caption = str(config.get("caption", "")).strip()
    raw_crop = str(config.get("crop", "")).strip()
    raw_mask = str(config.get("mask", "")).strip()
    if raw_mask and parse_crop_box(raw_mask) is None:
        messages.error(slide_no, "archscribe mask 必须是 x,y,width,height 四个非负数")
    elif raw_mask and not raw_crop:
        messages.error(slide_no, "archscribe mask 必须与 crop 一起使用")
    typography = validate_archscribe_typography(config, source_dir, messages, slide_no)

    if not raw_source:
        messages.error(slide_no, "archscribe 代码块缺少 src")
        raw_source = "missing-archscribe-diagram.gif"
    elif not raw_source.lower().endswith(".gif"):
        messages.warn(slide_no, "archscribe src 建议使用 GIF，以保留流程动画")
    source = resolve_block_asset(raw_source, source_dir, output_dir, messages, slide_no, "动画")

    if not raw_spec:
        messages.error(slide_no, "archscribe 代码块缺少 spec，无法复现流程图")
    elif not raw_spec.startswith(REMOTE_ASSET_PREFIXES):
        resolve_block_asset(raw_spec, source_dir, output_dir, messages, slide_no, "配置")

    poster_source = ""
    if raw_poster:
        poster_source = resolve_block_asset(raw_poster, source_dir, output_dir, messages, slide_no, "静态海报")
    else:
        messages.warn(slide_no, "archscribe 代码块未提供 poster；减少动态效果时仍会播放 GIF")

    reduced_motion = (
        f'<source media="(prefers-reduced-motion: reduce)" srcset="{html.escape(poster_source, quote=True)}">'
        if poster_source else ""
    )
    figure_caption = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    markup = (
        '<figure class="card chart-card diagram-card" data-visual-widget="image" data-diagram-engine="archscribe" '
        f'tabindex="0" aria-label="{html.escape(title, quote=True)}">'
        '<div class="visual-widget-content chart-content diagram-content" data-visual-content>'
        f'<picture>{reduced_motion}<img src="{html.escape(source, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}" draggable="false"></picture>'
        f'</div>{figure_caption}</figure>'
    )
    return Block(
        "archscribe",
        markup,
        "",
        {"src": raw_source, "poster": raw_poster, "spec": raw_spec, "crop": str(config.get("crop", "")), **typography},
    )


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
    return Block("section", f'<article class="card text-card section-card" data-presenter-focus>{heading}{content}</article>', plain)


def parse_blocks(
    body: str,
    source_dir: Path,
    output_dir: Path,
    messages: BuildMessages,
    slide_no: int,
    diagram_stage_size: tuple[int, int] = (DIAGRAM_STAGE_WIDTH, DIAGRAM_STAGE_HEIGHT),
) -> list[Block]:
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
            elif language == "mermaid":
                blocks.append(parse_mermaid_block("\n".join(fenced), source_dir, messages, slide_no, diagram_stage_size))
            elif language == "excalidraw":
                blocks.append(parse_excalidraw_block("\n".join(fenced), source_dir, messages, slide_no, diagram_stage_size))
            elif language == "archscribe":
                blocks.append(parse_archscribe("\n".join(fenced), source_dir, output_dir, messages, slide_no))
            else:
                label = html.escape(language or "code")
                code = html.escape("\n".join(fenced))
                blocks.append(Block("code", f'<article class="card code-card" data-presenter-focus><span class="code-label">{label}</span><pre><code>{code}</code></pre></article>', "\n".join(fenced)))
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
            blocks.append(Block("callout", f'<article class="card soft text-card callout-card callout-{html.escape(callout_kind)}" data-presenter-focus><strong>{label}</strong><p>{render_inline(quote_text)}</p></article>', quote_text))
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
    return sum(len(re.sub(r"\s+", "", block.text)) for block in blocks if block.kind not in DIAGRAM_BLOCK_KINDS)


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
    visual_blocks = [block for block in blocks if block.kind in DIAGRAM_BLOCK_KINDS]
    if requested == "chart" and not visual_blocks:
        messages.warn(slide_no, "layout=chart 但页面没有图表代码块，已改用 auto")
        requested = "auto"
    if requested == "chart" or (requested == "auto" and visual_blocks):
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
    fullstage = not bool_config(config, "footer", True)
    diagram_stage_size = (DIAGRAM_STAGE_WIDTH, DIAGRAM_STAGE_HEIGHT) if fullstage else (1700, 716)
    blocks = parse_blocks(body_without_media, source_dir, output_dir, messages, number, diagram_stage_size)
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
        f'<div class="hero-shell hero-{slide.kind} hero-layout-{slide.layout_resolved}"><div class="hero-copy reveal" data-presenter-focus>'
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
        visuals = [block.html for block in slide.blocks if block.kind in DIAGRAM_BLOCK_KINDS]
        copy = [block for block in slide.blocks if block.kind not in DIAGRAM_BLOCK_KINDS]
        return f'<div class="chart-layout"><div class="chart-stage">{"".join(visuals)}</div>{render_copy(copy, "chart-copy")}</div>'
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
    has_diagram = any(block.kind in {"mermaid", "excalidraw", "archscribe"} for block in slide.blocks)
    diagram_class = " has-diagram diagram-fullstage" if has_diagram and not bool_config(slide.config, "footer", True) else (" has-diagram" if has_diagram else "")
    classes = f"slide {slide.kind}-slide layout-{slide.layout_resolved} density-{slide.config.get('density', str(deck.get('density', 'reading')))}{diagram_class}"
    if slide.kind in {"cover", "section"}:
        inner = render_hero(slide, deck)
    else:
        subtitle = f'<p class="subtitle">{render_inline(slide.subtitle)}</p>' if slide.subtitle else ""
        inner = (
            f'<header class="slide-header reveal" data-presenter-focus><h1>{render_inline(slide.title)}</h1>{subtitle}</header>'
            f'<div class="content">{render_content(slide)}</div>{render_footer(slide, sections)}'
        )
    return (
        f'<section class="{classes}" data-title="{html.escape(slide.title, quote=True)}" '
        f'data-slide-id="{html.escape(slide.slide_id, quote=True)}" data-source-page="P{slide.number}" '
        f'data-slide-kind="{html.escape(slide.kind, quote=True)}" data-media-count="{len(slide.media)}" '
        f'data-block-count="{len(slide.blocks)}" data-text-length="{body_text_length(slide.blocks)}" '
        f'data-has-table="{str(any(block.kind == "table" for block in slide.blocks)).lower()}" '
        f'data-has-chart="{str(any(block.kind == "chart" for block in slide.blocks)).lower()}" '
        f'data-has-diagram="{str(has_diagram).lower()}" '
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
    svg_diagrams = [block for block in slide.blocks if block.kind in {"mermaid", "excalidraw"}]
    if len(svg_diagrams) > 1:
        messages.error(slide.number, "为保证投影字号和安全区准确，每页最多放置一个 Mermaid 或 Excalidraw 图表")
    if svg_diagrams and len(slide.blocks) > 1:
        messages.error(slide.number, "Mermaid/Excalidraw 页面不要混排正文块；说明应放入副标题或图注")
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


def find_archscribe_configs(source: str) -> list[dict[str, object]]:
    return [parse_key_values(match.group(1)) for match in ARCHSCRIBE_FENCE_RE.finditer(source)]


def find_mermaid_specs(source: str) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for match in MERMAID_FENCE_RE.finditer(source):
        config, definition = parse_mermaid_fence(match.group(1))
        specs.append({**config, "definition": definition})
    return specs


def find_excalidraw_configs(source: str) -> list[dict[str, object]]:
    return [parse_key_values(match.group(1)) for match in EXCALIDRAW_FENCE_RE.finditer(source)]


def find_chrome_executable(configured: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if configured:
        candidates.append(configured)
    for variable in ("DIAGRAM_CHROME", "PUPPETEER_EXECUTABLE_PATH"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]))
    if os.name == "nt":
        candidates.extend([
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ])
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    else:
        candidates.extend([Path("/usr/bin/google-chrome"), Path("/usr/bin/chromium"), Path("/usr/bin/chromium-browser")])
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def svg_artifact_metrics(source: str, fallback_font_size: float | None = None) -> dict[str, float]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        raise ValueError(f"SVG 无法解析：{error}") from error
    view_box = svg_view_box(root)
    if not view_box:
        raise ValueError("SVG 缺少有效 viewBox")
    font_sizes = extract_svg_font_sizes(source)
    source_min = min(font_sizes) if font_sizes else float(fallback_font_size or 0)
    if source_min <= 0:
        raise ValueError("SVG 中没有可校验的字号")
    return {
        "viewBoxWidth": round(view_box[2], 2),
        "viewBoxHeight": round(view_box[3], 2),
        "minimumSourceFontSize": round(source_min, 2),
    }


def diagram_cache_matches(output_path: Path, sidecar_path: Path, build_hash: str) -> bool:
    if not output_path.is_file() or not sidecar_path.is_file():
        return False
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        return payload.get("buildHash") == build_hash and payload.get("svgSha256") == sha256_file(output_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False


def run_diagram_process(command: list[str], label: str, messages: BuildMessages) -> subprocess.CompletedProcess[str] | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        messages.error(None, f"无法启动 {label}：{error}")
        return None
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        messages.error(None, f"{label} 失败：{detail}")
        return None
    return completed


def measure_svg_safe_margin(
    runtime: Path,
    measure_script: Path,
    svg_path: Path,
    chrome: Path,
    messages: BuildMessages,
    label: str,
) -> float | None:
    command = [str(runtime), str(measure_script), "--input", str(svg_path), "--chrome", str(chrome)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        messages.error(None, f"无法启动 {label} SVG 安全区检测：{error}")
        return None
    if completed.returncode != 0:
        messages.error(None, f"{label} SVG 安全区检测失败：{completed.stderr.strip() or completed.returncode}")
        return None
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        return round(float(payload["minimumSafeMargin"]), 2)
    except (ValueError, KeyError, IndexError, json.JSONDecodeError) as error:
        messages.error(None, f"{label} SVG 安全区结果无效：{error}")
        return None


def render_diagram_assets(
    mermaid_specs: list[dict[str, object]],
    excalidraw_configs: list[dict[str, object]],
    source_dir: Path,
    node_executable: Path | None,
    chrome_executable: Path | None,
    force: bool,
    messages: BuildMessages,
) -> dict[str, object]:
    report: dict[str, object] = {
        "detected": len(mermaid_specs) + len(excalidraw_configs),
        "mermaid": {"detected": len(mermaid_specs), "rendered": [], "cached": []},
        "excalidraw": {"detected": len(excalidraw_configs), "rendered": [], "cached": []},
    }
    if not mermaid_specs and not excalidraw_configs:
        return report
    runtime_raw = str(node_executable) if node_executable else shutil.which("node")
    runtime = Path(runtime_raw).resolve() if runtime_raw else None
    if not runtime or not runtime.is_file():
        messages.error(None, "已请求渲染图表，但没有找到 Node.js；可用 --diagram-node 指定")
        return report
    chrome = find_chrome_executable(chrome_executable)
    if not chrome:
        messages.error(None, "已请求渲染图表，但没有找到 Chrome/Chromium；可用 --diagram-chrome 指定")
        return report

    mermaid_cli = ROOT / "node_modules" / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    mermaid_config = ROOT / "tools" / "mermaid.config.json"
    mermaid_css = ROOT / "tools" / "mermaid-slide.css"
    excalidraw_renderer = ROOT / "tools" / "render_excalidraw.mjs"
    excalidraw_entry = ROOT / "tools" / "excalidraw_export_entry.mjs"
    measure_script = ROOT / "tools" / "measure_svg.mjs"
    package_lock = ROOT / "package-lock.json"
    required = [mermaid_cli, mermaid_config, mermaid_css, excalidraw_renderer, excalidraw_entry, measure_script, package_lock]
    missing = [path for path in required if not path.is_file()]
    if missing:
        messages.error(None, "图表构建依赖不完整；请先运行 npm install：" + ", ".join(path.name for path in missing))
        return report
    toolchain_hash = sha256_text(*(path.read_text(encoding="utf-8", errors="replace") for path in required[1:]))

    for index, spec in enumerate(mermaid_specs, 1):
        raw_output = str(spec.get("src", "")).strip()
        definition = str(spec.get("definition", "")).strip()
        if spec.get("metadata-error"):
            messages.error(None, f"第 {index} 个 mermaid：{spec['metadata-error']}")
            continue
        if not raw_output or not definition:
            messages.error(None, f"第 {index} 个 mermaid 必须提供 src 和图表定义")
            continue
        if raw_output.startswith(REMOTE_ASSET_PREFIXES):
            messages.error(None, f"第 {index} 个 mermaid src 必须是本地路径")
            continue
        output_path = (source_dir / raw_output).resolve()
        if output_path.suffix.lower() != ".svg":
            messages.error(None, f"第 {index} 个 mermaid src 必须是 .svg：{raw_output}")
            continue
        build_hash = sha256_text("mermaid", definition, toolchain_hash)
        sidecar_path = output_path.with_suffix(".diagram-build.json")
        if not force and diagram_cache_matches(output_path, sidecar_path, build_hash):
            report["mermaid"]["cached"].append(raw_output)
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="golajah-mermaid-") as directory:
            temporary = Path(directory)
            input_path = temporary / "diagram.mmd"
            rendered_path = temporary / "diagram.svg"
            browser_config = temporary / "puppeteer.json"
            write_text_atomic(input_path, definition + "\n")
            write_text_atomic(browser_config, json.dumps({"executablePath": str(chrome), "headless": True}) + "\n")
            command = [
                str(runtime), str(mermaid_cli),
                "--input", str(input_path),
                "--output", str(rendered_path),
                "--configFile", str(mermaid_config),
                "--cssFile", str(mermaid_css),
                "--puppeteerConfigFile", str(browser_config),
                "--backgroundColor", "transparent",
                "--width", str(DIAGRAM_STAGE_WIDTH),
                "--height", str(DIAGRAM_STAGE_HEIGHT),
            ]
            if run_diagram_process(command, f"Mermaid 渲染（{raw_output}）", messages) is None:
                continue
            try:
                rendered_source = rendered_path.read_text(encoding="utf-8")
                metrics = svg_artifact_metrics(rendered_source, DIAGRAM_MIN_FONT_SIZE)
            except (OSError, UnicodeError, ValueError) as error:
                messages.error(None, f"Mermaid 产物校验失败（{raw_output}）：{error}")
                continue
            safe_margin = measure_svg_safe_margin(runtime, measure_script, rendered_path, chrome, messages, "Mermaid")
            if safe_margin is None:
                continue
        write_text_atomic(output_path, rendered_source.rstrip() + "\n")
        sidecar = {
            "schemaVersion": "1.0",
            "engine": "mermaid",
            "buildHash": build_hash,
            "svgSha256": sha256_file(output_path),
            "minimumSafeMargin": safe_margin,
            **metrics,
        }
        write_text_atomic(sidecar_path, json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n")
        report["mermaid"]["rendered"].append(raw_output)

    for index, config in enumerate(excalidraw_configs, 1):
        raw_scene = str(config.get("source", "")).strip()
        raw_output = str(config.get("src", "")).strip()
        if not raw_scene or not raw_output:
            messages.error(None, f"第 {index} 个 excalidraw 必须同时提供 source 与 src")
            continue
        if raw_scene.startswith(REMOTE_ASSET_PREFIXES) or raw_output.startswith(REMOTE_ASSET_PREFIXES):
            messages.error(None, f"第 {index} 个 excalidraw 只支持本地路径")
            continue
        scene_path = (source_dir / raw_scene).resolve()
        output_path = (source_dir / raw_output).resolve()
        if not scene_path.is_file():
            messages.error(None, f"Excalidraw source 不存在：{raw_scene}")
            continue
        if output_path.suffix.lower() != ".svg":
            messages.error(None, f"第 {index} 个 excalidraw src 必须是 .svg：{raw_output}")
            continue
        scene_source = scene_path.read_text(encoding="utf-8", errors="replace")
        build_hash = sha256_text("excalidraw", scene_source, toolchain_hash)
        sidecar_path = output_path.with_suffix(".diagram-build.json")
        if not force and diagram_cache_matches(output_path, sidecar_path, build_hash):
            report["excalidraw"]["cached"].append(raw_output)
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="golajah-excalidraw-") as directory:
            rendered_path = Path(directory) / "diagram.svg"
            command = [
                str(runtime), str(excalidraw_renderer),
                "--input", str(scene_path),
                "--output", str(rendered_path),
                "--padding", "32",
            ]
            environment = os.environ.copy()
            environment["DIAGRAM_CHROME"] = str(chrome)
            try:
                completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment)
            except OSError as error:
                messages.error(None, f"无法启动 Excalidraw 渲染：{error}")
                continue
            if completed.stderr.strip():
                print(completed.stderr.strip(), file=sys.stderr)
            if completed.returncode != 0:
                messages.error(None, f"Excalidraw 渲染失败（{raw_output}）：{completed.stderr.strip() or completed.returncode}")
                continue
            try:
                renderer_metrics = json.loads(completed.stdout.strip().splitlines()[-1])
                rendered_source = rendered_path.read_text(encoding="utf-8")
                fallback = renderer_metrics.get("minimumFontSize") if isinstance(renderer_metrics, dict) else None
                metrics = svg_artifact_metrics(rendered_source, float(fallback) if fallback else None)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError, IndexError) as error:
                messages.error(None, f"Excalidraw 产物校验失败（{raw_output}）：{error}")
                continue
            safe_margin = measure_svg_safe_margin(runtime, measure_script, rendered_path, chrome, messages, "Excalidraw")
            if safe_margin is None:
                continue
        write_text_atomic(output_path, rendered_source.rstrip() + "\n")
        sidecar = {
            "schemaVersion": "1.0",
            "engine": "excalidraw",
            "buildHash": build_hash,
            "svgSha256": sha256_file(output_path),
            "minimumSafeMargin": safe_margin,
            **metrics,
        }
        write_text_atomic(sidecar_path, json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n")
        report["excalidraw"]["rendered"].append(raw_output)
    return report


def render_archscribe_assets(
    configs: list[dict[str, object]],
    source_dir: Path,
    archscribe_home: Path | None,
    python_executable: Path | None,
    renderer: str,
    force: bool,
    messages: BuildMessages,
) -> dict[str, object]:
    report: dict[str, object] = {"detected": len(configs), "rendered": [], "cached": []}
    if not configs:
        return report

    configured_home = archscribe_home or (Path(os.environ["ARCHSCRIBE_HOME"]) if os.environ.get("ARCHSCRIBE_HOME") else None)
    if configured_home is None:
        messages.error(None, "已请求渲染 Archscribe，但未设置 --archscribe-home 或 ARCHSCRIBE_HOME")
        return report
    render_script = configured_home.resolve() / "scripts" / "render_animated_diagram.py"
    if not render_script.is_file():
        messages.error(None, f"Archscribe 渲染脚本不存在：{render_script}")
        return report

    runtime = (python_executable or Path(sys.executable)).resolve()
    if not runtime.is_file():
        messages.error(None, f"Archscribe Python 解释器不存在：{runtime}")
        return report

    for index, config in enumerate(configs, 1):
        raw_spec = str(config.get("spec", "")).strip()
        raw_source = str(config.get("src", "")).strip()
        raw_poster = str(config.get("poster", "")).strip()
        raw_crop = str(config.get("crop", "")).strip()
        raw_mask = str(config.get("mask", "")).strip()
        raw_safe_margin = str(config.get("safe-margin", "24")).strip()
        if not raw_spec or not raw_source:
            messages.error(None, f"第 {index} 个 archscribe 代码块必须同时提供 spec 与 src")
            continue
        if raw_spec.startswith(REMOTE_ASSET_PREFIXES) or raw_source.startswith(REMOTE_ASSET_PREFIXES):
            messages.error(None, f"第 {index} 个 archscribe 代码块的构建期渲染只支持本地路径")
            continue

        spec_path = (source_dir / raw_spec).resolve()
        gif_path = (source_dir / raw_source).resolve()
        poster_path = (source_dir / raw_poster).resolve() if raw_poster else gif_path.with_suffix(".png")
        if not spec_path.is_file():
            messages.error(None, f"Archscribe 配置不存在：{raw_spec}")
            continue
        if gif_path.suffix.lower() != ".gif":
            messages.error(None, f"Archscribe 动画输出必须为 .gif：{raw_source}")
            continue
        if poster_path.suffix.lower() != ".png":
            messages.error(None, f"Archscribe poster 必须为 .png：{raw_poster}")
            continue
        if poster_path.parent != gif_path.parent or poster_path.stem != gif_path.stem:
            messages.error(None, "Archscribe src 与 poster 必须位于同一目录并使用相同文件名")
            continue
        crop = parse_crop_box(raw_crop)
        if raw_crop and crop is None:
            messages.error(None, f"第 {index} 个 archscribe 代码块的 crop 必须是 x,y,width,height")
            continue
        mask = parse_crop_box(raw_mask)
        if raw_mask and mask is None:
            messages.error(None, f"第 {index} 个 archscribe 代码块的 mask 必须是 x,y,width,height")
            continue
        if raw_mask and not crop:
            messages.error(None, f"第 {index} 个 archscribe 代码块的 mask 必须与 crop 一起使用")
            continue
        try:
            safe_margin = float(raw_safe_margin)
        except ValueError:
            messages.error(None, f"第 {index} 个 archscribe 代码块的 safe-margin 必须是数字")
            continue
        if safe_margin < 0:
            messages.error(None, f"第 {index} 个 archscribe 代码块的 safe-margin 不能为负数")
            continue

        expected = [gif_path, poster_path, gif_path.with_suffix(".excalidraw")]
        cache_path = gif_path.with_suffix(".archscribe-build.json")
        cache_payload = {
            "schemaVersion": "1.0",
            "spec": raw_spec,
            "crop": raw_crop,
            "mask": raw_mask,
            "safeMargin": safe_margin,
            "renderer": renderer,
        }
        try:
            cached_payload = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else None
        except (OSError, UnicodeError, json.JSONDecodeError):
            cached_payload = None
        newest_input = spec_path.stat().st_mtime
        if (
            not force
            and isinstance(cached_payload, dict)
            and all(cached_payload.get(key) == value for key, value in cache_payload.items())
            and all(path.is_file() and path.stat().st_mtime >= newest_input for path in expected)
        ):
            report["cached"].append(raw_source)
            continue

        gif_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(runtime),
            "-X",
            "utf8",
            str(render_script),
            "--spec",
            str(spec_path),
            "--outdir",
            str(gif_path.parent),
            "--basename",
            gif_path.stem,
            "--renderer",
            renderer,
            "--formats",
            "gif,png,excalidraw",
            "--strict-formats",
            "--verify",
            "--check",
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            messages.error(None, f"无法启动 Archscribe：{error}")
            continue
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.stderr.strip():
            print(completed.stderr.strip(), file=sys.stderr)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit code {completed.returncode}"
            messages.error(None, f"Archscribe 渲染失败（{raw_spec}）：{detail}")
            continue
        if not all(path.is_file() for path in expected):
            missing = ", ".join(path.name for path in expected if not path.is_file())
            messages.error(None, f"Archscribe 未生成完整产物：{missing}")
            continue
        if crop:
            crop_script = ROOT / "tools" / "crop_archscribe_media.py"
            crop_command = [
                str(runtime),
                "-X",
                "utf8",
                str(crop_script),
                "--gif",
                str(gif_path),
                "--png",
                str(poster_path),
                "--box",
                ",".join(str(value) for value in crop),
            ]
            if mask:
                crop_command.extend(["--mask", ",".join(str(value) for value in mask)])
            crop_command.extend(["--safe-margin", f"{safe_margin:g}"])
            try:
                cropped = subprocess.run(
                    crop_command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as error:
                messages.error(None, f"无法启动 Archscribe Slide 视口裁切：{error}")
                continue
            if cropped.stdout.strip():
                print(cropped.stdout.strip())
            if cropped.stderr.strip():
                print(cropped.stderr.strip(), file=sys.stderr)
            if cropped.returncode != 0:
                detail = cropped.stderr.strip() or f"exit code {cropped.returncode}"
                messages.error(None, f"Archscribe Slide 视口裁切失败（{raw_spec}）：{detail}")
                continue
            try:
                crop_result = json.loads(cropped.stdout.strip().splitlines()[-1]) if cropped.stdout.strip() else {}
            except json.JSONDecodeError:
                crop_result = {}
            if isinstance(crop_result.get("minimumRasterMargin"), (int, float)):
                cache_payload["minimumRasterMargin"] = crop_result["minimumRasterMargin"]
        try:
            write_text_atomic(cache_path, json.dumps(cache_payload, ensure_ascii=False, indent=2) + "\n")
        except OSError as error:
            messages.error(None, f"无法写入 Archscribe 构建缓存：{error}")
            continue
        report["rendered"].append(raw_source)
    return report


def build(
    source_path: Path,
    output_path: Path,
    strict: bool = False,
    overrides_path: Path | None = None,
    render_archscribe: bool = False,
    archscribe_home: Path | None = None,
    archscribe_python: Path | None = None,
    archscribe_renderer: str = "auto",
    force_archscribe: bool = False,
    render_diagrams: bool = False,
    diagram_node: Path | None = None,
    diagram_chrome: Path | None = None,
    force_diagrams: bool = False,
) -> int:
    messages = BuildMessages()
    if not TEMPLATE_PATH.exists():
        print(f"ERROR: template missing: {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR: cannot read Markdown source {source_path}: {error}", file=sys.stderr)
        return 2
    mermaid_specs = find_mermaid_specs(source)
    excalidraw_configs = find_excalidraw_configs(source)
    diagram_report: dict[str, object] = {
        "detected": len(mermaid_specs) + len(excalidraw_configs),
        "renderRequested": render_diagrams,
        "mermaid": {"detected": len(mermaid_specs), "rendered": [], "cached": []},
        "excalidraw": {"detected": len(excalidraw_configs), "rendered": [], "cached": []},
    }
    if render_diagrams:
        diagram_report.update(render_diagram_assets(
            mermaid_specs,
            excalidraw_configs,
            source_path.parent,
            diagram_node,
            diagram_chrome,
            force_diagrams,
            messages,
        ))
    archscribe_configs = find_archscribe_configs(source)
    archscribe_report: dict[str, object] = {
        "detected": len(archscribe_configs),
        "renderRequested": render_archscribe,
        "rendered": [],
        "cached": [],
    }
    if render_archscribe:
        archscribe_report.update(render_archscribe_assets(
            archscribe_configs,
            source_path.parent,
            archscribe_home,
            archscribe_python,
            archscribe_renderer,
            force_archscribe,
            messages,
        ))
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        template_fragments = {
            placeholder: path.read_text(encoding="utf-8").rstrip("\r\n")
            for placeholder, path in TEMPLATE_FRAGMENT_PATHS.items()
        }
    except (OSError, UnicodeError) as error:
        print(f"ERROR: cannot read template source: {error}", file=sys.stderr)
        return 2
    deck, chunks = split_deck_source(source)
    if not chunks:
        print("ERROR: no slides found", file=sys.stderr)
        return 2
    slides = [parse_slide(chunk, index, deck, source_path.parent, output_path.parent, messages) for index, chunk in enumerate(chunks, 1)]
    if mermaid_specs or excalidraw_configs:
        diagram_report["quality"] = {
            slide.slide_id: [block.meta for block in slide.blocks if block.kind in {"mermaid", "excalidraw"}]
            for slide in slides
            if any(block.kind in {"mermaid", "excalidraw"} for block in slide.blocks)
        }
    if archscribe_configs:
        archscribe_report["typography"] = {
            slide.slide_id: {
                key: block.meta[key]
                for block in slide.blocks
                if block.kind == "archscribe"
                for key in ("sourceMinFontSize", "projectedMinFontSize", "minimumSafeMargin", "minimumRasterMargin")
                if key in block.meta
            }
            for slide in slides
            if any(block.kind == "archscribe" for block in slide.blocks)
        }
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
        **template_fragments,
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
        "source": format_report_path(source_path),
        "output": format_report_path(output_path),
        "slides": len(slides),
        "layouts": {str(slide.number): slide.layout_resolved for slide in slides},
        "layoutOverrides": {
            "source": format_report_path(resolved_overrides_path) if resolved_overrides_path else None,
            "appliedSlides": applied_overrides,
        },
        "warnings": messages.warnings,
        "errors": messages.errors,
    }
    if archscribe_configs:
        report["archscribe"] = archscribe_report
    if mermaid_specs or excalidraw_configs:
        report["diagrams"] = diagram_report
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
    parser.add_argument("--render-archscribe", action="store_true", help="render archscribe fences before building the slides")
    parser.add_argument("--force-archscribe", action="store_true", help="render Archscribe assets even when outputs are newer than the spec")
    parser.add_argument("--archscribe-home", type=Path, help="Archscribe checkout; defaults to ARCHSCRIBE_HOME")
    parser.add_argument("--archscribe-python", type=Path, help="Python executable with Archscribe dependencies; defaults to this Python")
    parser.add_argument(
        "--archscribe-renderer",
        choices=["auto", "browser", "pillow"],
        default="auto",
        help="Archscribe renderer (default: auto)",
    )
    parser.add_argument("--render-diagrams", action="store_true", help="render Mermaid and Excalidraw SVG assets before building")
    parser.add_argument("--force-diagrams", action="store_true", help="render diagram SVG assets even when the content cache matches")
    parser.add_argument("--diagram-node", type=Path, help="Node.js executable used by diagram renderers")
    parser.add_argument("--diagram-chrome", type=Path, help="Chrome/Chromium executable used by diagram renderers")
    args = parser.parse_args()
    overrides = args.overrides.resolve() if args.overrides else None
    return build(
        args.source.resolve(),
        args.output.resolve(),
        args.strict,
        overrides,
        args.render_archscribe,
        args.archscribe_home,
        args.archscribe_python,
        args.archscribe_renderer,
        args.force_archscribe,
        args.render_diagrams,
        args.diagram_node,
        args.diagram_chrome,
        args.force_diagrams,
    )


if __name__ == "__main__":
    raise SystemExit(main())
