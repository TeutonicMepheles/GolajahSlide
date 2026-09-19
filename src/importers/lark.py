"""Build-time Feishu source adapter. Standard library only; credentials stay in CLI.

The browser never talks to Feishu. The adapter saves an inspectable Markdown
snapshot and uses the existing slide compiler for layout and presentation.
"""
from __future__ import annotations

import base64
import html
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse


class LarkImportError(ValueError):
    pass


def cli_command(executable: str | None = None) -> list[str]:
    found = executable or shutil.which("lark-cli")
    if not found:
        raise LarkImportError("找不到 lark-cli；请安装并用用户身份登录，或传入 --lark-cli 路径")
    path = Path(found)
    # npm's Windows shim needs a shell. Run its packaged binary directly instead:
    # document text and URLs must never be interpolated into a shell command.
    if path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        binary = path.parent / "node_modules/@larksuite/cli/bin/lark-cli.exe"
        if not binary.is_file():
            raise LarkImportError("请用 --lark-cli 指定 lark-cli.exe，不能执行 shell 包装脚本")
        path = binary
    return [str(path.resolve())]


class LarkClient:
    def __init__(self, executable: str | None = None, identity: str = "user"):
        self.command = cli_command(executable)
        self.identity = identity

    def run(self, *args: str, cwd: Path | None = None) -> dict:
        try:
            result = subprocess.run(
                [*self.command, *args, "--as", self.identity],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180, shell=False, cwd=cwd,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LarkImportError(f"飞书 CLI 无法完成请求：{error}") from error
        if result.returncode:
            raise LarkImportError(f"飞书 CLI 请求失败：{result.stderr.strip() or result.stdout.strip()}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise LarkImportError("飞书 CLI 未返回有效 JSON") from error
        if not isinstance(payload, dict):
            raise LarkImportError("飞书 CLI 返回了非对象结果")
        if payload.get("code", 0) not in (0, "0") or payload.get("error"):
            raise LarkImportError(f"飞书请求失败：{payload.get('msg') or payload.get('error')}")
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise LarkImportError("飞书 CLI 返回了无效 data")
        return data


def resolve_document(reference: str, client: LarkClient) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", reference):
        return reference
    parsed = urlparse(reference)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == d or host.endswith("." + d) for d in ("feishu.cn", "larksuite.com")):
        raise LarkImportError("请提供 https://…feishu.cn/docx/… 或 /wiki/… 文档链接")
    match = re.fullmatch(r"/(docx|wiki)/([A-Za-z0-9_-]+)/?", parsed.path)
    if not match:
        raise LarkImportError("目前只支持新版 docx 文档和 Wiki 文档链接")
    kind, token = match.groups()
    if kind == "wiki":
        node = client.run("wiki", "spaces", "get_node", "--params", json.dumps({"token": token})).get("node", {})
        if node.get("obj_type") != "docx" or not node.get("obj_token"):
            raise LarkImportError(f"Wiki 节点不是新版云文档：{node.get('obj_type', 'unknown')}")
        token = node["obj_token"]
    return token


def fetch_document(reference: str, client: LarkClient) -> tuple[str, str, str]:
    token = resolve_document(reference, client)
    chunks: list[str] = []
    title = ""
    offset = 0
    seen: set[int] = set()
    while True:
        if offset in seen:
            raise LarkImportError("飞书文档分页游标重复，已停止以避免内容重复")
        seen.add(offset)
        data = client.run("docs", "+fetch", "--doc", token, "--offset", str(offset), "--limit", "20000")
        markdown = data.get("markdown")
        if not isinstance(markdown, str):
            raise LarkImportError("飞书响应缺少 markdown 正文")
        chunks.append(markdown)
        title = title or str(data.get("title", ""))
        if not data.get("has_more", False):
            break
        next_offset = data.get("next_offset")
        if next_offset is None:
            raise LarkImportError("飞书响应仍有下一页，但缺少 next_offset，无法保证文档完整")
        try:
            next_offset = int(next_offset)
        except (TypeError, ValueError) as error:
            raise LarkImportError("飞书分页 next_offset 无效") from error
        if next_offset <= offset:
            raise LarkImportError("飞书分页游标没有前进")
        offset = next_offset
    return title, "".join(chunks), token


class _Attributes(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.attributes: dict[str, str] = {}
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.attributes = dict(attrs)


def attributes(tag: str) -> dict[str, str]:
    return _Attributes(tag).attributes


def _table(source: str) -> str:
    if re.search(r"\b(?:rowspan|colspan)\s*=\s*['\"](?!1['\"])", source):
        raise LarkImportError("暂不支持合并单元格；请先在飞书拆分表格单元格")
    rows: list[list[str]] = []
    for row in re.findall(r"<lark-tr\b[^>]*>(.*?)</lark-tr>", source, re.S):
        cells = re.findall(r"<lark-td\b[^>]*>(.*?)</lark-td>", row, re.S)
        cleaned = []
        for cell in cells:
            if "\x00CODE" in cell or re.search(r"<(?:image|whiteboard|lark-table|callout|grid)\b|```|(?m:^\s*[-*+] )", cell):
                raise LarkImportError("暂不支持复杂表格单元格；请将图片、列表、代码等移出表格")
            if "|" in html.unescape(cell):
                raise LarkImportError("表格单元格中的竖线暂不支持；请用全角竖线代替")
            cleaned.append(" ".join(cell.split()))
        rows.append(cleaned)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise LarkImportError("飞书表格行列不完整")
    lines = ["| " + " | ".join(row) + " |" for row in rows]
    lines.insert(1, "| " + " | ".join("---" for _ in rows[0]) + " |")
    return "\n".join(lines)


def normalize_markdown(markdown: str, title: str, media_resolver) -> str:
    """Normalize supported Lark Markdown without interpreting code-block contents."""
    code: list[str] = []
    deck_config: list[str] = []
    if "\x00" in markdown:
        raise LarkImportError("飞书文档包含无效 NUL 字符")

    def protect(match):
        language, body = match.group(1).strip(), match.group(2)
        marker = re.match(r"golajahslide:\s*(deck|slide|chart|mermaid|excalidraw|archscribe)\s*\n", body)
        if marker:
            kind = marker.group(1)
            body = body[marker.end():].rstrip()
            if kind == "deck":
                if deck_config:
                    raise LarkImportError("文档只能有一个 golajahslide: deck 配置块")
                deck_config.append(body)
                return ""
            if kind == "slide":
                rendered = "<!-- slide\n" + body + "\n-->"
            else:
                rendered = f"```{kind}\n{body}\n```"
        else:
            rendered = f"```{language}\n{body.rstrip()}\n```"
        code.append(rendered)
        return f"\x00CODE{len(code)-1}\x00"

    source = re.sub(r"(?m)^```([^\n]*)\n([\s\S]*?)^```\s*$", protect, markdown.replace("\r\n", "\n"))
    inline_code: list[str] = []

    def protect_inline(match):
        inline_code.append(match.group())
        return f"\x00INLINE{len(inline_code)-1}\x00"

    source = re.sub(r"`[^`\n]+`", protect_inline, source)
    source = re.sub(r"<lark-table\b[^>]*>.*?</lark-table>", lambda m: _table(m.group()), source, flags=re.S)

    def media(match):
        tag = match.group()
        attrs = attributes(tag)
        token = attrs.get("token")
        if not token:
            raise LarkImportError("飞书图片缺少 token，无法下载")
        kind = "whiteboard" if tag.startswith("<whiteboard") else "media"
        path = media_resolver(token, kind)
        caption = attrs.get("caption") or attrs.get("alt") or ("画板" if kind == "whiteboard" else "图片")
        caption = caption.replace("[", "（").replace("]", "）").replace("\n", " ")
        return f"\n![{caption}]({path})\n"

    source = re.sub(r"<(?:image|whiteboard)\b[^>]*?/>", media, source)

    def callout(match):
        attrs = attributes(match.group(1))
        kind = "WARNING" if attrs.get("emoji") in {"⚠️", "⚠"} else "TIP" if attrs.get("emoji") == "💡" else "NOTE"
        content = match.group(2).strip()
        if "\x00CODE" in content or re.search(r"(?m)^!\[|^\|", content):
            raise LarkImportError("提示块中暂不支持代码、图片或表格")
        return f"> [!{kind}]\n" + "\n".join("> " + line for line in content.splitlines())

    source = re.sub(r"(<callout\b[^>]*>)(.*?)</callout>", callout, source, flags=re.S)
    source = re.sub(r"<text\b([^>]*)>(.*?)</text>", lambda m: "==" + m.group(2) + "==" if any(key in m.group(1) for key in ("background-color", "bgcolor")) else m.group(2), source, flags=re.S)
    # Feishu coalesces quote paragraphs, including an admonition marker and text.
    source = re.sub(r"(?m)^(>\s*\[![A-Za-z]+\])([^\n]+)$", r"\1\n> \2", source)
    source = re.sub(r"</?(?:quote-container)\b[^>]*>", "\n", source)
    source = re.sub(r"\s*\{(?:color|align)=['\"][^\n}]+\}\s*$", "", source, flags=re.M)
    unsupported = re.search(r"</?([A-Za-z][\w-]*)\b[^>]*>", source)
    if unsupported:
        raise LarkImportError(f"暂不支持飞书块 <{unsupported.group(1)}>；请转换为正文、表格或图片")
    # Lark escapes literal Markdown punctuation on export. Keep it inside code.
    source = re.sub(r"\\([\[\]<>~*_{}|])", r"\1", source)
    source = html.unescape(source)
    # Explicit dividers win. Otherwise every H1 starts a new slide.
    if not re.search(r"(?m)^---\s*$", source):
        count = 0
        lines = []
        for line in source.splitlines():
            if line.startswith("# "):
                count += 1
                if count > 1:
                    # Keep a page's metadata with the following H1.
                    at = len(lines)
                    while at and not lines[at-1].strip():
                        at -= 1
                    if at and re.fullmatch(r"\x00CODE\d+\x00", lines[at-1].strip()):
                        slot = int(re.search(r"\d+", lines[at-1]).group())
                        if code[slot].startswith("<!-- slide"):
                            at -= 1
                    lines.insert(at, "\n---\n")
            lines.append(line)
        source = "\n".join(lines)
    if not re.search(r"(?m)^# ", source):
        source = "# " + (title or "飞书文档").replace("\n", " ") + "\n\n" + source
    for index, body in enumerate(code):
        source = source.replace(f"\x00CODE{index}\x00", body)
    for index, body in enumerate(inline_code):
        source = source.replace(f"\x00INLINE{index}\x00", body)
    deck = deck_config[0] if deck_config else "title: " + json.dumps(title or "飞书文档", ensure_ascii=False)
    return "---\n" + deck + "\n---\n\n" + source.strip() + "\n"


def import_document(reference: str, directory: Path, client: LarkClient) -> Path:
    title, markdown, token = fetch_document(reference, client)
    directory.mkdir(parents=True, exist_ok=True)
    assets = directory / "assets"
    assets.mkdir(exist_ok=True)
    downloaded: dict[tuple[str, str], str] = {}

    def download(media_token: str, kind: str) -> str:
        key = (media_token, kind)
        if key in downloaded:
            return downloaded[key]
        # Token content never controls a filesystem path.
        import hashlib
        basename = hashlib.sha256((kind + ":" + media_token).encode()).hexdigest()[:24]
        target = assets / basename
        client.run("docs", "+media-download", "--token", media_token, "--type", kind, "--output", basename, "--overwrite", cwd=assets)
        candidates = [p for p in assets.glob(basename + ".*") if p.is_file()]
        if target.is_file():
            candidates.append(target)
        if len(candidates) != 1:
            raise LarkImportError("飞书媒体下载后没有得到唯一的资源文件")
        path = candidates[0]
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}:
            raise LarkImportError(f"不支持的媒体格式：{path.suffix or 'unknown'}")
        downloaded[key] = path.relative_to(directory).as_posix()
        return downloaded[key]

    normalized = normalize_markdown(markdown, title, download)
    snapshot = directory / "slides.md"
    snapshot.write_text(normalized, encoding="utf-8")
    (directory / "source.lark.md").write_text(markdown, encoding="utf-8")
    (directory / "source.json").write_text(json.dumps({
        "sourceType": "lark", "reference": reference, "documentId": token,
        "title": title, "mediaCount": len(downloaded),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot


def embed_media(output: Path, directory: Path) -> None:
    """Make imported deck images offline-capable without changing local builds."""
    source = output.read_text(encoding="utf-8")

    def replace(match):
        prefix, raw, suffix = match.groups()
        href = html.unescape(raw)
        if href.startswith("data:image/"):
            return match.group()
        if urlparse(href).scheme or href.startswith("//"):
            raise LarkImportError("导入的图片仍引用外部 URL，无法生成离线 HTML")
        path = (output.parent / href).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise LarkImportError("导入的图片不在已下载资源目录中")
        mime = mimetypes.guess_type(path.name)[0]
        if not mime or not mime.startswith("image/"):
            raise LarkImportError("导入的媒体不是可嵌入图片")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return prefix + f"data:{mime};base64,{encoded}" + suffix

    source = re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")', replace, source)
    output.write_text(source, encoding="utf-8")
    report_path = output.with_suffix(".build.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["sourceImport"] = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    report["sourceImport"]["embeddedImages"] = True
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
