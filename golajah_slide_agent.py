#!/usr/bin/env python3
"""JSON-first Agent CLI and dependency-free stdio MCP bridge for GolajahSlide.

The service layer in this file deliberately reuses ``build_slides`` for the
Markdown dialect and lossless source map. CLI and MCP are only adapters around
the same functions, so an Agent cannot accidentally use a second parser with
different page boundaries or identities.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import html
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

try:
    import fcntl
except ImportError:  # pragma: no cover - GolajahSlide currently targets macOS/Linux Agents.
    fcntl = None

import build_slides


VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"
MCP_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
EXPLICIT_ID_RE = re.compile(r"^[0-9A-Za-z_-]+$")
RESERVED_PAGE_ID_RE = re.compile(r"^p[1-9]\d*$", re.IGNORECASE)
LEGACY_PAGE_KEY_RE = re.compile(r"^P([1-9]\d*)$")
CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class AgentToolError(RuntimeError):
    """Expected, machine-readable failure from an Agent operation."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


@dataclass(frozen=True)
class DeckState:
    path: Path
    source: str
    document: build_slides.AuthoringDocument
    deck: dict[str, object]


@dataclass(frozen=True)
class EditImpact:
    source: str
    changed_ids: tuple[str, ...]
    invalidated_ids: tuple[str, ...]
    clear_layout_ids: tuple[str, ...]
    inserted: bool
    final_numbers: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class LayoutSnapshot:
    path: Path
    exists: bool
    sha256: str | None
    original: str | None
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class LayoutChange:
    original: str
    updated: str
    before_sha256: str
    after_sha256: str
    invalidated: tuple[str, ...]
    migrated: tuple[dict[str, str], ...]
    reconciled: tuple[dict[str, str], ...]


class PathPolicy:
    """Resolve real paths inside one MCP root and reject symlink escapes."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise AgentToolError("INVALID_ROOT", f"MCP root is not a directory: {self.root}")

    def resolve(
        self,
        value: str | Path,
        *,
        must_exist: bool = False,
        file_only: bool = False,
    ) -> Path:
        raw = Path(value).expanduser()
        candidate = raw if raw.is_absolute() else self.root / raw
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise AgentToolError(
                "PATH_OUTSIDE_ROOT",
                f"Path is outside the configured MCP root: {value}",
                {"root": str(self.root)},
            ) from error
        if must_exist and not resolved.exists():
            raise AgentToolError("FILE_NOT_FOUND", f"Path does not exist: {resolved}")
        if file_only and resolved.exists() and not resolved.is_file():
            raise AgentToolError("NOT_A_FILE", f"Expected a file: {resolved}")
        return resolved


def _read_source(path: Path, allowed_root: str | Path | None = None) -> str:
    if allowed_root is not None:
        root = Path(allowed_root).expanduser().resolve()
        try:
            payload = build_slides._asset_bytes(path, root, str(path))
        except build_slides.AssetBoundaryError as error:
            raise AgentToolError(
                "PATH_OUTSIDE_ROOT",
                "Markdown source changed to a path outside the configured MCP root.",
                {"resolvedPath": str(error.resolved_path), "root": str(error.allowed_root)},
            ) from error
        if payload is None:
            raise AgentToolError("FILE_NOT_FOUND", f"Markdown source does not exist: {path}")
        try:
            return payload.decode("utf-8")
        except UnicodeError as error:
            raise AgentToolError("SOURCE_READ_FAILED", f"Cannot decode Markdown source {path}: {error}") from error
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError as error:
        raise AgentToolError("FILE_NOT_FOUND", f"Markdown source does not exist: {path}") from error
    except (OSError, UnicodeError) as error:
        raise AgentToolError("SOURCE_READ_FAILED", f"Cannot read Markdown source {path}: {error}") from error


def _source_path(path: str | Path, allowed_root: str | Path | None = None) -> Path:
    source_path = Path(path).expanduser().resolve()
    if allowed_root is not None:
        root = Path(allowed_root).expanduser().resolve()
        try:
            source_path.relative_to(root)
        except ValueError as error:
            raise AgentToolError(
                "PATH_OUTSIDE_ROOT",
                f"Markdown source is outside the configured MCP root: {source_path}",
                {"root": str(root)},
            ) from error
    if source_path.suffix.lower() != ".md":
        raise AgentToolError("INVALID_SOURCE", f"GolajahSlide source must be a .md file: {source_path}")
    if not source_path.is_file():
        raise AgentToolError("FILE_NOT_FOUND", f"Markdown source does not exist: {source_path}")
    return source_path


def _load_deck(path: str | Path, allowed_root: str | Path | None = None) -> DeckState:
    source_path = _source_path(path, allowed_root)
    source = _read_source(source_path, allowed_root)
    try:
        document = build_slides.parse_authoring_document(source, source_path.name)
        deck, _ = build_slides.split_deck_source(source)
    except Exception as error:
        raise AgentToolError("SOURCE_PARSE_FAILED", f"Cannot parse {source_path}: {error}") from error
    if not document.slides or not any(slide.title.value.strip() for slide in document.slides):
        raise AgentToolError(
            "INVALID_DECK",
            f"Markdown does not contain a GolajahSlide page with a '# title': {source_path}",
        )
    return DeckState(source_path, source, document, deck)


def _layout_path(
    source_path: Path,
    explicit: str | Path | None = None,
    *,
    allowed_root: str | Path | None = None,
) -> Path:
    raw = Path(explicit).expanduser() if explicit is not None else source_path.with_suffix(".layout.json")
    path = raw.resolve(strict=False)
    if not path.name.endswith(".layout.json"):
        raise AgentToolError("INVALID_LAYOUT_PATH", f"Layout sidecar must end with .layout.json: {path}")
    if allowed_root is not None:
        root = Path(allowed_root).expanduser().resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise AgentToolError(
                "PATH_OUTSIDE_ROOT",
                f"Layout sidecar is outside the configured MCP root: {path}",
                {"root": str(root)},
            ) from error
    return path


def _layout_metadata(
    source_path: Path,
    explicit: str | Path | None = None,
    *,
    allowed_root: str | Path | None = None,
) -> dict[str, Any]:
    path = _layout_path(source_path, explicit, allowed_root=allowed_root)
    try:
        payload = _read_regular_bytes(path)
    except OSError as error:
        raise AgentToolError("LAYOUT_READ_FAILED", f"Cannot inspect layout sidecar {path}: {error}") from error
    return {
        "path": str(path),
        "exists": payload is not None,
        "sha256": hashlib.sha256(payload).hexdigest() if payload is not None else None,
    }


def _item_counts(slide: build_slides.AuthoringSlide) -> dict[str, int]:
    counts = Counter(item.kind for item in slide.items)
    return dict(sorted(counts.items()))


def _slide_summary(slide: build_slides.AuthoringSlide) -> dict[str, Any]:
    raw_text = "\n".join(item.markdown for item in slide.items)
    return {
        "number": slide.number,
        "id": slide.slide_id,
        "explicitId": bool(slide.config.get("id", "").strip()),
        "title": slide.title.value,
        "subtitle": slide.subtitle.value,
        "type": slide.config.get("type", "content"),
        "layout": slide.config.get("layout", "auto"),
        "section": slide.config.get("section", ""),
        "chapter": slide.config.get("chapter", ""),
        "galleryDisplay": slide.config.get("gallery-display", ""),
        "itemCount": len(slide.items),
        "itemKinds": _item_counts(slide),
        "textCharacters": len(re.sub(r"\s+", "", raw_text)),
        "sha256": slide.base_hash,
    }


def _deck_issues(state: DeckState) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for slide in state.document.slides:
        explicit_id = slide.config.get("id", "").strip()
        if not explicit_id:
            issues.append({
                "code": "IMPLICIT_SLIDE_ID",
                "severity": "warning",
                "slide": slide.number,
                "slideId": slide.slide_id,
                "message": "页面使用易随顺序变化的默认 ID；结构性编辑前应添加显式 id。",
            })
        elif not EXPLICIT_ID_RE.fullmatch(explicit_id):
            issues.append({
                "code": "NORMALIZED_SLIDE_ID",
                "severity": "warning",
                "slide": slide.number,
                "slideId": slide.slide_id,
                "message": f"显式 id={explicit_id!r} 会被规范化为 {slide.slide_id!r}。",
            })
        if not slide.title.value.strip():
            issues.append({
                "code": "MISSING_TITLE",
                "severity": "error",
                "slide": slide.number,
                "slideId": slide.slide_id,
                "message": "页面缺少一级标题。",
            })
        if slide.slide_id in seen:
            issues.append({
                "code": "DUPLICATE_SLIDE_ID",
                "severity": "error",
                "slide": slide.number,
                "slideId": slide.slide_id,
                "message": f"页面 ID 与第 {seen[slide.slide_id]} 页重复。",
            })
        else:
            seen[slide.slide_id] = slide.number
    return issues


def inspect_deck(path: str | Path, *, asset_root: str | Path | None = None) -> dict[str, Any]:
    """Return the cheap, lossless outline used before every Agent mutation."""
    state = _load_deck(path, asset_root)
    slides = [_slide_summary(slide) for slide in state.document.slides]
    issues = _deck_issues(state)
    aggregate = Counter()
    for slide in state.document.slides:
        aggregate.update(item.kind for item in slide.items)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "inspect",
        "source": {
            "path": str(state.path),
            "name": state.path.name,
            "sha256": state.document.revision,
            "newline": state.document.newline,
            "bom": state.document.bom,
        },
        "layout": _layout_metadata(state.path, allowed_root=asset_root),
        "deck": dict(state.deck),
        "counts": {
            "slides": len(slides),
            "explicitSlideIds": sum(1 for slide in state.document.slides if slide.config.get("id", "").strip()),
            "items": sum(aggregate.values()),
            "itemKinds": dict(sorted(aggregate.items())),
            "issues": len(issues),
        },
        "issues": issues,
        "slides": slides,
    }


def _find_slide(document: build_slides.AuthoringDocument, selector: str | int) -> build_slides.AuthoringSlide:
    raw = str(selector).strip()
    id_matches = [slide for slide in document.slides if slide.slide_id == raw]
    if len(id_matches) == 1:
        return id_matches[0]
    if len(id_matches) > 1:
        raise AgentToolError("AMBIGUOUS_SLIDE", f"Slide ID is duplicated: {raw}")
    page_raw = raw[1:] if raw.startswith("#") else raw
    if page_raw.isdigit():
        number = int(page_raw)
        if 1 <= number <= len(document.slides):
            return document.slides[number - 1]
    raise AgentToolError("SLIDE_NOT_FOUND", f"No slide matches selector: {selector}")


def _find_stable_slide(
    document: build_slides.AuthoringDocument,
    slide_id: str,
) -> build_slides.AuthoringSlide:
    """Resolve a mutation target only by its exact authored ID; never by page number."""
    matches = [
        slide
        for slide in document.slides
        if slide.config.get("id", "").strip() == slide_id
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AgentToolError("AMBIGUOUS_SLIDE", f"Stable slide ID is duplicated: {slide_id}")
    generated_match = next((slide for slide in document.slides if slide.slide_id == slide_id), None)
    if generated_match is not None:
        raise AgentToolError(
            "RESERVED_SLIDE_ID" if RESERVED_PAGE_ID_RE.fullmatch(slide_id) else "EXPLICIT_ID_REQUIRED",
            "Mutation targets must use an exact explicit slide ID, not an implicit page identity.",
            {"slide": generated_match.number, "slideId": generated_match.slide_id},
        )
    raise AgentToolError("SLIDE_NOT_FOUND", f"No slide has the explicit stable ID: {slide_id}")


def get_slide(
    path: str | Path,
    selector: str | int,
    *,
    asset_root: str | Path | None = None,
) -> dict[str, Any]:
    state = _load_deck(path, asset_root)
    slide = _find_slide(state.document, selector)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "slide",
        "source": {"path": str(state.path), "sha256": state.document.revision},
        "slide": {**_slide_summary(slide), "config": dict(slide.config)},
        "markdown": slide.span.text(state.source),
        "items": [
            {
                "id": item.item_id,
                "kind": item.kind,
                "movable": item.movable,
                "sha256": item.base_hash,
                "fields": {name: field.value for name, field in item.fields.items()},
                "markdown": item.markdown,
            }
            for item in slide.items
        ],
    }


def _search_snippet(text: str, query: str, radius: int = 72) -> str:
    folded = text.casefold()
    index = folded.find(query.casefold())
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    compact = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("…" if start else "") + compact + ("…" if end < len(text) else "")


def search_deck(
    path: str | Path,
    query: str,
    limit: int = 20,
    *,
    asset_root: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise AgentToolError("INVALID_QUERY", "Search query must not be empty.")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise AgentToolError("INVALID_ARGUMENTS", "limit must be an integer between 1 and 100.")
    if not 1 <= limit <= 100:
        raise AgentToolError("INVALID_ARGUMENTS", "limit must be between 1 and 100.")
    safe_limit = limit
    state = _load_deck(path, asset_root)
    matches: list[dict[str, Any]] = []
    for slide in state.document.slides:
        searchable = "\n".join([
            slide.title.value,
            slide.subtitle.value,
            *[item.markdown for item in slide.items],
        ])
        snippet = _search_snippet(searchable, query)
        if not snippet:
            continue
        matches.append({**_slide_summary(slide), "snippet": snippet})
        if len(matches) >= safe_limit:
            break
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "search",
        "source": {"path": str(state.path), "sha256": state.document.revision},
        "query": query,
        "limit": safe_limit,
        "count": len(matches),
        "matches": matches,
    }


def _capture_build(
    source_path: Path,
    output_path: Path,
    *,
    strict: bool,
    overrides_path: Path | None = None,
    asset_root: Path | None = None,
    source_snapshot: str | None = None,
) -> tuple[int, dict[str, Any], str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = build_slides.build(
                source_path,
                output_path,
                strict=strict,
                overrides_path=overrides_path,
                allowed_asset_root=asset_root,
                source_snapshot=source_snapshot,
                discover_overrides=False,
            )
    except build_slides.AssetBoundaryError as error:
        raise AgentToolError(
            "PATH_OUTSIDE_ROOT",
            "A rendered asset reference escapes the configured MCP root.",
            {
                "asset": error.source,
                "resolvedPath": str(error.resolved_path),
                "root": str(error.allowed_root),
            },
        ) from error
    except build_slides.UnsafeAssetReferenceError as error:
        raise AgentToolError(
            "UNSAFE_SVG_REFERENCE",
            "A rooted SVG must be self-contained and cannot load another local file.",
            {"svg": str(error.path), "references": error.references},
        ) from error
    report_path = output_path.with_suffix(".build.json")
    report: dict[str, Any] = {}
    if report_path.is_file():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                report = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            report = {}
    return exit_code, report, stdout.getvalue(), stderr.getvalue()


def _raise_for_operational_build_failure(
    exit_code: int,
    report: dict[str, Any],
    stdout: str,
    stderr: str,
) -> None:
    """Keep diagnostic exit 1 as a result, but normalize builder exit 2 as an operation error."""
    if exit_code < 2:
        return
    raise AgentToolError(
        "BUILD_OPERATION_FAILED",
        "GolajahSlide could not complete the build operation.",
        {
            "buildExitCode": exit_code,
            "logs": {"stdout": stdout, "stderr": stderr},
            "report": report,
        },
    )


def _assert_path_inside_root(path: Path, root: Path, label: str, raw: str) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise AgentToolError(
            "PATH_OUTSIDE_ROOT",
            f"Local {label} path escapes the configured MCP root: {raw}",
            {"asset": raw, "resolvedPath": str(resolved), "root": str(root)},
        ) from error
    return resolved


def _assert_local_asset_inside_root(
    raw_source: object,
    source_dir: Path,
    root: Path,
    label: str,
) -> Path | None:
    raw = str(raw_source or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https", "data"}:
        return None
    if parsed.scheme:
        raise AgentToolError(
            "PATH_OUTSIDE_ROOT",
            f"Local {label} uses a disallowed URI scheme: {parsed.scheme}",
            {"asset": raw, "root": str(root)},
        )
    if unquote(parsed.path) != parsed.path or parsed.query or parsed.fragment:
        raise AgentToolError(
            "PATH_OUTSIDE_ROOT",
            f"Local {label} must use a plain unencoded filesystem path: {raw}",
            {"asset": raw, "root": str(root)},
        )
    return _assert_path_inside_root(source_dir / raw, root, label, raw)


def _validate_svg_references(svg_path: Path, root: Path, label: str) -> None:
    """Require diagram SVGs to be self-contained except fragments/data/remote URLs."""
    if svg_path.suffix.lower() != ".svg":
        return
    try:
        payload = build_slides._asset_bytes(svg_path, root, str(svg_path))
        if payload is None:
            return
        source = payload.decode("utf-8")
    except build_slides.AssetBoundaryError as error:
        raise AgentToolError(
            "PATH_OUTSIDE_ROOT",
            f"Local {label} SVG changed to a path outside the configured MCP root.",
            {"asset": str(svg_path), "resolvedPath": str(error.resolved_path), "root": str(root)},
        ) from error
    except build_slides.UnsafeAssetReferenceError as error:
        raise AgentToolError(
            "UNSAFE_SVG_REFERENCE",
            f"{label} SVG must be self-contained; local nested resources are not allowed.",
            {"svg": str(error.path), "references": error.references, "root": str(root)},
        ) from error
    except (OSError, UnicodeError) as error:
        raise AgentToolError("ASSET_READ_FAILED", f"Cannot inspect {label} SVG: {error}") from error
    candidates: list[str] = []
    candidates.extend(
        html.unescape(match.group(1)).strip()
        for match in re.finditer(r'(?is)\b(?:href|xlink:href|src|poster)\s*=\s*["\']([^"\']+)["\']', source)
    )
    for match in re.finditer(r'(?is)\bsrcset\s*=\s*["\']([^"\']+)["\']', source):
        for entry in html.unescape(match.group(1)).split(","):
            if entry.strip():
                candidates.append(entry.strip().split()[0])
    candidates.extend(
        html.unescape(match.group(1)).strip()
        for match in re.finditer(r'(?is)url\(\s*["\']?([^"\')]+)', source)
    )
    unsafe = []
    for candidate in candidates:
        parsed = urlsplit(candidate)
        if (
            not candidate
            or candidate.startswith("#")
            or candidate.lower().startswith(("data:image/", "http://", "https://", "blob:"))
            or (not parsed.scheme and parsed.path == "" and parsed.fragment)
        ):
            continue
        unsafe.append(candidate)
    if unsafe:
        raise AgentToolError(
            "UNSAFE_SVG_REFERENCE",
            f"{label} SVG must be self-contained; local nested resources are not allowed.",
            {"svg": str(svg_path), "references": unsafe[:10], "root": str(root)},
        )


def _validate_build_asset_boundary(state: DeckState, asset_root: str | Path | None) -> None:
    """Reject every authored local path that the builder may read outside an MCP root."""
    if asset_root is None:
        return
    root = Path(asset_root).expanduser().resolve()
    source_dir = state.path.parent
    for slide in state.document.slides:
        for item in slide.items:
            if item.kind not in {"image", "video"}:
                continue
            field = item.fields.get("source")
            if field:
                asset = _assert_local_asset_inside_root(field.value, source_dir, root, f"P{slide.number} media")
                if asset and asset.suffix.lower() == ".svg":
                    _validate_svg_references(asset, root, f"P{slide.number} media")
                if asset and item.kind == "video":
                    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
                        _assert_path_inside_root(asset.with_suffix(suffix), root, f"P{slide.number} video poster", field.value)
    for index, spec in enumerate(build_slides.find_mermaid_specs(state.source), 1):
        svg = _assert_local_asset_inside_root(spec.get("src"), source_dir, root, f"Mermaid {index} SVG")
        if svg:
            _assert_path_inside_root(svg.with_suffix(".diagram-build.json"), root, f"Mermaid {index} report", str(spec.get("src", "")))
            _validate_svg_references(svg, root, f"Mermaid {index}")
        if build_slides.mermaid_renderer(spec) == "diagram-design":
            _assert_local_asset_inside_root(spec.get("source"), source_dir, root, f"Mermaid {index} source")
    for index, config in enumerate(build_slides.find_excalidraw_configs(state.source), 1):
        _assert_local_asset_inside_root(config.get("source"), source_dir, root, f"Excalidraw {index} source")
        svg = _assert_local_asset_inside_root(config.get("src"), source_dir, root, f"Excalidraw {index} SVG")
        if svg:
            _assert_path_inside_root(svg.with_suffix(".diagram-build.json"), root, f"Excalidraw {index} report", str(config.get("src", "")))
            _validate_svg_references(svg, root, f"Excalidraw {index}")
    for index, config in enumerate(build_slides.find_archscribe_configs(state.source), 1):
        for key, label in (("src", "animation"), ("spec", "spec"), ("poster", "poster")):
            asset = _assert_local_asset_inside_root(config.get(key), source_dir, root, f"Archscribe {index} {label}")
            if key == "src" and asset:
                for suffix in (".png", ".excalidraw", ".archscribe-build.json"):
                    _assert_path_inside_root(asset.with_suffix(suffix), root, f"Archscribe {index} derived asset", str(config.get(key, "")))


def _resolved_build_layout(
    state: DeckState,
    explicit: str | Path | None,
    asset_root: str | Path | None,
) -> Path | None:
    """Freeze automatic layout discovery to one canonical, root-checked path."""
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.name.endswith(".layout.json"):
            raise AgentToolError("INVALID_LAYOUT_PATH", f"Layout override must end with .layout.json: {candidate}")
        if not candidate.is_file():
            raise AgentToolError("FILE_NOT_FOUND", f"Layout override does not exist: {candidate}")
    else:
        automatic = state.path.with_suffix(".layout.json")
        candidate = automatic.resolve() if automatic.is_file() else None
    if candidate is not None and asset_root is not None:
        root = Path(asset_root).expanduser().resolve()
        candidate = _assert_path_inside_root(candidate, root, "layout sidecar", str(candidate))
    return candidate


def audit_deck(
    path: str | Path,
    strict: bool = True,
    *,
    asset_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build in a disposable directory and return diagnostics without artifacts."""
    if type(strict) is not bool:
        raise AgentToolError("INVALID_ARGUMENTS", "strict must be a JSON boolean.")
    state = _load_deck(path, asset_root)
    _validate_build_asset_boundary(state, asset_root)
    override_path = _resolved_build_layout(state, None, asset_root)
    with tempfile.TemporaryDirectory(prefix="golajah-agent-audit-") as directory:
        output = Path(directory) / "index.html"
        exit_code, report, stdout, stderr = _capture_build(
            state.path,
            output,
            strict=strict,
            overrides_path=override_path,
            asset_root=Path(asset_root).expanduser().resolve() if asset_root is not None else None,
            source_snapshot=state.source,
        )
    _raise_for_operational_build_failure(exit_code, report, stdout, stderr)
    if report:
        report["source"] = str(state.path)
        report["output"] = None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "audit",
        "source": {"path": str(state.path), "sha256": state.document.revision},
        "strict": bool(strict),
        "buildExitCode": exit_code,
        "ok": exit_code == 0,
        "report": report,
        "logs": {"stdout": stdout, "stderr": stderr},
        "artifactsWritten": False,
    }


def build_deck(
    path: str | Path,
    output: str | Path,
    strict: bool = True,
    overrides: str | Path | None = None,
    *,
    asset_root: str | Path | None = None,
) -> dict[str, Any]:
    if type(strict) is not bool:
        raise AgentToolError("INVALID_ARGUMENTS", "strict must be a JSON boolean.")
    state = _load_deck(path, asset_root)
    _validate_build_asset_boundary(state, asset_root)
    output_path = Path(output).expanduser().resolve()
    if output_path.suffix.lower() != ".html":
        raise AgentToolError("INVALID_OUTPUT", f"Build output must end with .html: {output_path}")
    override_path = _resolved_build_layout(state, overrides, asset_root)
    report_path = output_path.with_suffix(".build.json")
    automatic_layout = state.path.with_suffix(".layout.json").resolve(strict=False)
    protected = {state.path.resolve(strict=False), automatic_layout}
    if override_path:
        protected.add(override_path.resolve(strict=False))
    collisions = [
        candidate
        for candidate in (output_path, report_path)
        if candidate.resolve(strict=False) in protected
    ]
    if collisions:
        raise AgentToolError(
            "INVALID_OUTPUT",
            "Build output or report collides with source/layout input.",
            {"paths": [str(candidate) for candidate in collisions]},
        )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise AgentToolError("OUTPUT_CREATE_FAILED", f"Cannot create build output directory: {error}") from error
    exit_code, report, stdout, stderr = _capture_build(
        state.path,
        output_path,
        strict=strict,
        overrides_path=override_path,
        asset_root=Path(asset_root).expanduser().resolve() if asset_root is not None else None,
        source_snapshot=state.source,
    )
    _raise_for_operational_build_failure(exit_code, report, stdout, stderr)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "build",
        "source": {"path": str(state.path), "sha256": state.document.revision},
        "output": str(output_path),
        "reportPath": str(report_path),
        "strict": bool(strict),
        "buildExitCode": exit_code,
        "ok": exit_code == 0,
        "report": report,
        "logs": {"stdout": stdout, "stderr": stderr},
    }


def _normalize_newlines(value: str, newline: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)


_OPERATION_FIELDS = {
    "insert_slide": frozenset({"op", "after_slide_id", "before_slide_id", "markdown"}),
    "replace_slide": frozenset({"op", "slide_id", "markdown"}),
    "append_content": frozenset({"op", "slide_id", "markdown"}),
    "set_fields": frozenset({"op", "slide_id", "fields"}),
}
_OPERATION_REQUIRED_FIELDS = {
    "insert_slide": frozenset({"op", "markdown"}),
    "replace_slide": frozenset({"op", "slide_id", "markdown"}),
    "append_content": frozenset({"op", "slide_id", "markdown"}),
    "set_fields": frozenset({"op", "slide_id", "fields"}),
}


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _validate_stable_selector(value: Any, field: str, index: int) -> None:
    if not isinstance(value, str) or not EXPLICIT_ID_RE.fullmatch(value):
        raise AgentToolError(
            "INVALID_ARGUMENTS",
            f"Operation {index} field {field} must be an exact stable slide ID string.",
        )


def _validate_operations(operations: Any) -> list[dict[str, Any]]:
    """Validate the one operation contract shared by service, CLI and MCP adapters."""
    if not isinstance(operations, list) or not operations:
        raise AgentToolError("INVALID_OPERATIONS", "Operations must be a non-empty array of objects.")
    for index, operation in enumerate(operations, 1):
        if not isinstance(operation, dict):
            raise AgentToolError("INVALID_ARGUMENTS", f"Operation {index} must be an object.")
        op = operation.get("op")
        if not isinstance(op, str) or op not in _OPERATION_FIELDS:
            raise AgentToolError("INVALID_ARGUMENTS", f"Operation {index} has an invalid op value.")
        unexpected = sorted(str(field) for field in set(operation) - _OPERATION_FIELDS[op])
        if unexpected:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} ({op}) has unexpected field(s): {', '.join(unexpected)}.",
            )
        missing = sorted(_OPERATION_REQUIRED_FIELDS[op] - set(operation))
        if missing:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} ({op}) is missing field(s): {', '.join(missing)}.",
            )
        for selector_field in ("slide_id", "after_slide_id", "before_slide_id"):
            if selector_field in operation:
                _validate_stable_selector(operation[selector_field], selector_field, index)
        if op == "insert_slide" and "after_slide_id" in operation and "before_slide_id" in operation:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} (insert_slide) accepts only one insertion anchor.",
            )
        if "markdown" in operation and not isinstance(operation["markdown"], str):
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} field markdown must be a string.",
            )
        if op != "set_fields":
            continue
        fields = operation["fields"]
        if not isinstance(fields, dict) or not fields:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} field fields must be a non-empty object.",
            )
        unexpected_fields = sorted(str(field) for field in set(fields) - {"title", "subtitle", "config"})
        if unexpected_fields:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} fields has unexpected key(s): {', '.join(unexpected_fields)}.",
            )
        if "title" in fields and not isinstance(fields["title"], str):
            raise AgentToolError("INVALID_ARGUMENTS", f"Operation {index} fields.title must be a string.")
        if "subtitle" in fields and fields["subtitle"] is not None and not isinstance(fields["subtitle"], str):
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Operation {index} fields.subtitle must be a string or null.",
            )
        if "config" in fields:
            config = fields["config"]
            if not isinstance(config, dict) or not config:
                raise AgentToolError(
                    "INVALID_ARGUMENTS",
                    f"Operation {index} fields.config must be a non-empty object.",
                )
            for key, value in config.items():
                if not isinstance(key, str) or not CONFIG_KEY_RE.fullmatch(key):
                    raise AgentToolError(
                        "INVALID_CONFIG",
                        f"Invalid slide directive key in operation {index}: {key!r}",
                    )
                if not _is_json_value(value):
                    raise AgentToolError(
                        "INVALID_ARGUMENTS",
                        f"Operation {index} fields.config.{key} must be a finite JSON value.",
                    )
    return operations


def _validate_slide_snippet(
    markdown: Any,
    newline: str,
) -> tuple[str, build_slides.AuthoringSlide, build_slides.AuthoringDocument]:
    if not isinstance(markdown, str) or not markdown.strip():
        raise AgentToolError("INVALID_OPERATION", "Slide markdown must be a non-empty string.")
    normalized = _normalize_newlines(markdown.strip("\r\n"), newline) + newline
    document = build_slides.parse_authoring_document(normalized, "slide-snippet.md")
    if document.frontmatter is not None or len(document.slides) != 1:
        raise AgentToolError("INVALID_SLIDE_MARKDOWN", "Slide markdown must contain exactly one page and no frontmatter.")
    slide = document.slides[0]
    explicit_id = slide.config.get("id", "").strip()
    if not explicit_id or not EXPLICIT_ID_RE.fullmatch(explicit_id):
        raise AgentToolError(
            "EXPLICIT_ID_REQUIRED",
            "Inserted or replacement slide markdown must declare a stable id using letters, digits, '-' or '_'.",
        )
    if not slide.title.value.strip():
        raise AgentToolError("MISSING_TITLE", "Inserted or replacement slide must contain a '# title'.")
    return normalized, slide, document


def _line_bounds(source: str, position: int) -> tuple[int, int]:
    cursor = 0
    for line in source.splitlines(keepends=True):
        end = cursor + len(line)
        if cursor <= position < end or (position == len(source) == end):
            return cursor, end
        cursor = end
    return position, position


def _trimmed_slide_end(state: DeckState, slide: build_slides.AuthoringSlide) -> int:
    limit = slide.span.end
    while limit > slide.span.start and state.source[limit - 1] in "\r\n":
        limit -= 1
    return limit


def _assert_unique_document(source: str, source_name: str) -> build_slides.AuthoringDocument:
    document = build_slides.parse_authoring_document(source, source_name)
    if not document.slides:
        raise AgentToolError("EMPTY_DECK", "An edit cannot remove every slide.")
    seen: dict[str, int] = {}
    for slide in document.slides:
        if not slide.title.value.strip():
            raise AgentToolError("MISSING_TITLE", f"Slide {slide.number} has no '# title'.")
        if slide.slide_id in seen:
            raise AgentToolError(
                "DUPLICATE_SLIDE_ID",
                f"Slide ID {slide.slide_id!r} is duplicated on pages {seen[slide.slide_id]} and {slide.number}.",
            )
        seen[slide.slide_id] = slide.number
    seen_citations: set[str] = set()
    for citation in document.citations:
        if citation.citation_id in seen_citations:
            raise AgentToolError("DUPLICATE_CITATION_ID", f"Citation ID is duplicated: {citation.citation_id}")
        seen_citations.add(citation.citation_id)
    return document


def _render_config_value(key: str, value: Any) -> str:
    if isinstance(value, (dict, list, bool, int, float)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value).strip()
    if "\n" in rendered or "\r" in rendered or "<!--" in rendered or "-->" in rendered:
        raise AgentToolError("INVALID_CONFIG", f"Directive value for {key!r} must be one line.")
    return rendered


def _set_directive_config(source: str, slide: build_slides.AuthoringSlide, changes: dict[str, Any], newline: str) -> str:
    """Patch only requested directive entries, retaining comments, spacing and other raw values."""
    explicit_id = slide.config.get("id", "").strip()
    replacements: list[tuple[int, int, str]] = []
    additions: list[str] = []
    for raw_key, value in changes.items():
        if not isinstance(raw_key, str) or not CONFIG_KEY_RE.fullmatch(raw_key):
            raise AgentToolError("INVALID_CONFIG", f"Invalid slide directive key: {raw_key!r}")
        key = raw_key
        if key == "id":
            if not explicit_id:
                if value is not None and RESERVED_PAGE_ID_RE.fullmatch(str(value).strip()):
                    raise AgentToolError(
                        "RESERVED_SLIDE_ID",
                        "Implicit pages cannot be assigned an ID in the legacy P<n> namespace.",
                    )
                raise AgentToolError(
                    "SLIDE_ID_CHANGE_REJECTED",
                    "set_fields cannot add an ID to an implicit page; use a dedicated migration workflow.",
                )
            if value is None or str(value).strip() != explicit_id:
                raise AgentToolError("SLIDE_ID_CHANGE_REJECTED", "set_fields cannot remove or change a slide ID.")
        entry = slide.directive.entries.get(key) if slide.directive else None
        if value is None:
            if entry and entry.span:
                line_start, line_end = _line_bounds(source, entry.span.start)
                line = source[line_start:line_end]
                if "<!--" not in line and "-->" not in line:
                    replacements.append((line_start, line_end, ""))
                else:
                    prefix = source[line_start:entry.span.start]
                    key_match = re.search(
                        rf"(?i)(?:^|[ \t]){re.escape(key)}[ \t]*:[ \t]*$",
                        prefix,
                    )
                    if not key_match:
                        raise AgentToolError("INVALID_CONFIG", f"Cannot locate directive field {key!r} safely.")
                    removal_start = line_start + key_match.start()
                    removal_end = entry.span.end
                    while removal_end < line_end and source[removal_end] in " \t":
                        removal_end += 1
                    replacements.append((removal_start, removal_end, ""))
            continue
        rendered = _render_config_value(key, value)
        if entry and entry.span:
            if entry.span.text(source) != rendered:
                replacements.append((entry.span.start, entry.span.end, rendered))
        else:
            additions.append(f"{key}: {rendered}")

    if slide.directive:
        if additions:
            closing = source.rfind("-->", slide.directive.span.start, slide.directive.span.end)
            if closing < 0:
                raise AgentToolError("INVALID_CONFIG", "Slide directive closing marker is missing.")
            closing_line_start, _ = _line_bounds(source, closing)
            addition = "".join(line + newline for line in additions)
            if source[closing_line_start:closing].strip():
                prefix = "" if source[:closing].endswith(("\n", "\r")) else newline
                replacements.append((closing, closing, prefix + addition))
            else:
                replacements.append((closing_line_start, closing_line_start, addition))
        updated = source
        for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        return updated

    if not additions:
        return source
    directive = newline.join(["<!-- slide", *additions, "-->"]) + newline
    return source[: slide.span.start] + directive + source[slide.span.start :]


def _set_text_field(source: str, slide: build_slides.AuthoringSlide, name: str, value: Any, newline: str) -> str:
    if name not in {"title", "subtitle"}:
        raise AgentToolError("INVALID_FIELD", f"Unsupported text field: {name}")
    rendered = "" if value is None else str(value).strip()
    if "\n" in rendered or "\r" in rendered:
        raise AgentToolError("INVALID_FIELD", f"{name} must be one line.")
    field = slide.title if name == "title" else slide.subtitle
    if name == "title" and not rendered:
        raise AgentToolError("MISSING_TITLE", "A slide title cannot be empty.")
    if field.span:
        if rendered:
            return source[: field.span.start] + rendered + source[field.span.end :]
        line_start, line_end = _line_bounds(source, field.span.start)
        return source[:line_start] + source[line_end:]
    if name == "title":
        raise AgentToolError("MISSING_TITLE", "Cannot update a missing title with an unstable insertion point.")
    if not rendered:
        return source
    if not slide.title.span:
        raise AgentToolError("MISSING_TITLE", "Add a title before adding a subtitle.")
    _, title_line_end = _line_bounds(source, slide.title.span.start)
    prefix = "" if title_line_end and source[title_line_end - 1 : title_line_end] in {"\n", "\r"} else newline
    addition = prefix + "## " + rendered + newline
    return source[:title_line_end] + addition + source[title_line_end:]


def _insert_slide(source: str, state: DeckState, operation: dict[str, Any]) -> tuple[str, str, bool]:
    snippet, candidate, _ = _validate_slide_snippet(operation.get("markdown"), state.document.newline)
    if RESERVED_PAGE_ID_RE.fullmatch(candidate.slide_id):
        raise AgentToolError(
            "RESERVED_SLIDE_ID",
            f"New slide id={candidate.slide_id!r} conflicts with the legacy P<n> layout namespace.",
        )
    if any(slide.slide_id == candidate.slide_id for slide in state.document.slides):
        raise AgentToolError("DUPLICATE_SLIDE_ID", f"Slide ID already exists: {candidate.slide_id}")
    reserved_existing = [
        slide.slide_id
        for slide in state.document.slides
        if slide.config.get("id", "").strip() and RESERVED_PAGE_ID_RE.fullmatch(slide.slide_id)
    ]
    if reserved_existing:
        raise AgentToolError(
            "RESERVED_SLIDE_ID",
            "Insert cannot safely migrate a deck whose explicit IDs use the legacy P<n> namespace.",
            {"slides": reserved_existing},
        )
    after = operation.get("after_slide_id")
    before = operation.get("before_slide_id")
    if after and before:
        raise AgentToolError("INVALID_OPERATION", "insert_slide accepts only one of after_slide_id or before_slide_id.")
    slides = list(state.document.slides)
    if before:
        target = _find_stable_slide(state.document, before)
        insertion_index = target.number - 1
    elif after:
        target = _find_stable_slide(state.document, after)
        insertion_index = target.number
    else:
        insertion_index = len(slides)
    unstable = [
        slide.slide_id
        for slide in slides[insertion_index:]
        if not slide.config.get("id", "").strip()
    ]
    if unstable:
        raise AgentToolError(
            "UNSTABLE_SLIDE_IDS",
            "Insert would renumber slides that do not have explicit IDs.",
            {"slides": unstable},
        )
    separator = state.document.newline * 2 + "---" + state.document.newline * 2
    if insertion_index < len(slides):
        position = slides[insertion_index].span.start
        updated = source[:position] + snippet.rstrip("\r\n") + separator + source[position:]
    else:
        if slides:
            last = slides[-1]
            position = _trimmed_slide_end(state, last)
            updated = source[:position].rstrip("\r\n") + separator + snippet + source[position:]
        else:
            updated = source + snippet
    return updated, candidate.slide_id, insertion_index < len(slides)


def _replace_slide(source: str, state: DeckState, operation: dict[str, Any]) -> tuple[str, str]:
    selector = operation.get("slide_id")
    if not selector:
        raise AgentToolError("INVALID_OPERATION", "replace_slide requires slide_id.")
    target = _find_stable_slide(state.document, selector)
    snippet, candidate, candidate_document = _validate_slide_snippet(operation.get("markdown"), state.document.newline)
    if candidate.slide_id != target.slide_id:
        raise AgentToolError(
            "SLIDE_ID_CHANGE_REJECTED",
            f"Replacement must preserve id={target.slide_id!r}; received {candidate.slide_id!r}.",
        )
    end = _trimmed_slide_end(state, target)
    replacement = snippet.rstrip("\r\n")
    replacement_citation_ids = {citation.citation_id for citation in candidate_document.citations}
    preserved_citations = [
        citation.markdown.strip("\r\n")
        for citation in state.document.citations
        if target.span.start <= citation.span.start < target.span.end
        and citation.citation_id not in replacement_citation_ids
    ]
    if preserved_citations:
        separator = state.document.newline * 2
        replacement += separator + separator.join(preserved_citations)
    return source[: target.span.start] + replacement + source[end:], target.slide_id


def _append_content(source: str, state: DeckState, operation: dict[str, Any]) -> tuple[str, str]:
    selector = operation.get("slide_id")
    markdown = operation.get("markdown")
    if not selector or not isinstance(markdown, str) or not markdown.strip():
        raise AgentToolError("INVALID_OPERATION", "append_content requires slide_id and non-empty markdown.")
    target = _find_stable_slide(state.document, selector)
    addition = _normalize_newlines(markdown.strip("\r\n"), state.document.newline)
    end = _trimmed_slide_end(state, target)
    prefix = source[:end].rstrip("\r\n")
    updated = prefix + state.document.newline * 2 + addition + state.document.newline + source[end:]
    updated_document = build_slides.parse_authoring_document(updated, state.path.name)
    if [slide.slide_id for slide in updated_document.slides] != [slide.slide_id for slide in state.document.slides]:
        raise AgentToolError(
            "CONTENT_CREATED_SLIDE",
            "append_content cannot contain a top-level slide separator; use insert_slide with an explicit ID.",
        )
    return updated, target.slide_id


def _set_fields(source: str, state: DeckState, operation: dict[str, Any]) -> tuple[str, str]:
    selector = operation.get("slide_id")
    fields = operation.get("fields")
    if not selector or not isinstance(fields, dict) or not fields:
        raise AgentToolError("INVALID_OPERATION", "set_fields requires slide_id and a non-empty fields object.")
    allowed = {"title", "subtitle", "config"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise AgentToolError("INVALID_FIELD", f"Unsupported set_fields keys: {', '.join(unknown)}")
    target = _find_stable_slide(state.document, selector)
    target_id = target.slide_id
    updated = source
    if "config" in fields:
        if not isinstance(fields["config"], dict):
            raise AgentToolError("INVALID_CONFIG", "set_fields.config must be an object.")
        updated = _set_directive_config(updated, target, fields["config"], state.document.newline)
    if "title" in fields:
        current = DeckState(state.path, updated, build_slides.parse_authoring_document(updated, state.path.name), state.deck)
        target = _find_stable_slide(current.document, target_id)
        updated = _set_text_field(updated, target, "title", fields["title"], current.document.newline)
    if "subtitle" in fields:
        current = DeckState(state.path, updated, build_slides.parse_authoring_document(updated, state.path.name), state.deck)
        target = _find_stable_slide(current.document, target_id)
        updated = _set_text_field(updated, target, "subtitle", fields["subtitle"], current.document.newline)
    return updated, target_id


def _apply_operations(state: DeckState, operations: Iterable[dict[str, Any]]) -> EditImpact:
    source = state.source
    touched_order: list[str] = []
    invalidation_candidates: list[str] = []
    clear_layout_candidates: list[str] = []
    inserted = False
    operation_list = list(operations)
    if not operation_list:
        raise AgentToolError("INVALID_OPERATIONS", "At least one edit operation is required.")
    for index, operation in enumerate(operation_list, 1):
        if not isinstance(operation, dict):
            raise AgentToolError("INVALID_OPERATION", f"Operation {index} must be an object.")
        current_document = _assert_unique_document(source, state.path.name)
        current = DeckState(state.path, source, current_document, state.deck)
        op = str(operation.get("op", "")).strip()
        before_operation = source
        if op == "insert_slide":
            source, changed_id, _ = _insert_slide(source, current, operation)
            inserted = inserted or source != before_operation
        elif op == "replace_slide":
            source, changed_id = _replace_slide(source, current, operation)
            if source != before_operation:
                invalidation_candidates.append(changed_id)
        elif op == "append_content":
            source, changed_id = _append_content(source, current, operation)
            if source != before_operation:
                invalidation_candidates.append(changed_id)
        elif op == "set_fields":
            source, changed_id = _set_fields(source, current, operation)
            fields = operation.get("fields")
            config = fields.get("config") if isinstance(fields, dict) else None
            if source != before_operation and isinstance(config, dict) and "layout" in config:
                clear_layout_candidates.append(changed_id)
        else:
            raise AgentToolError(
                "INVALID_OPERATION",
                f"Unsupported operation {op!r}; use insert_slide, replace_slide, append_content or set_fields.",
            )
        if source != before_operation:
            touched_order.append(changed_id)
    final_document = _assert_unique_document(source, state.path.name)
    before_hashes = {slide.slide_id: slide.base_hash for slide in state.document.slides}
    after_hashes = {slide.slide_id: slide.base_hash for slide in final_document.slides}
    changed_set = {
        slide_id
        for slide_id in set(before_hashes) | set(after_hashes)
        if before_hashes.get(slide_id) != after_hashes.get(slide_id)
    }
    changed_ids = tuple(slide_id for slide_id in dict.fromkeys(touched_order) if slide_id in changed_set)
    invalidated_ids = tuple(
        slide_id for slide_id in dict.fromkeys(invalidation_candidates) if slide_id in changed_set
    )
    clear_layout_ids = tuple(
        slide_id for slide_id in dict.fromkeys(clear_layout_candidates) if slide_id in changed_set
    )
    final_numbers = tuple((slide.slide_id, slide.number) for slide in final_document.slides)
    return EditImpact(source, changed_ids, invalidated_ids, clear_layout_ids, inserted, final_numbers)


def _read_layout_for_edit(
    path: Path,
    before_sha256: str,
    source_path: Path,
    *,
    explicit: bool,
) -> LayoutSnapshot:
    try:
        original_bytes = _read_regular_bytes(path)
        if original_bytes is None:
            return LayoutSnapshot(path, False, None, None, None)
        original = original_bytes.decode("utf-8")
        payload = json.loads(original)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentToolError("LAYOUT_READ_FAILED", f"Cannot safely update layout sidecar {path}: {error}") from error
    if not isinstance(payload, dict):
        raise AgentToolError("LAYOUT_READ_FAILED", f"Layout sidecar must contain an object: {path}")
    version = str(payload.get("schemaVersion", build_slides.EDITOR_SCHEMA_VERSION))
    if version != build_slides.EDITOR_SCHEMA_VERSION:
        raise AgentToolError(
            "LAYOUT_SCHEMA_MISMATCH",
            f"Layout schemaVersion={version!r} is not supported for safe edits.",
            {"expected": build_slides.EDITOR_SCHEMA_VERSION},
        )
    if not isinstance(payload.get("slides"), dict):
        raise AgentToolError("LAYOUT_SCHEMA_MISMATCH", "Layout sidecar must contain a slides object.")
    recorded_source = payload.get("source")
    if recorded_source is not None and str(recorded_source).strip() != source_path.name:
        raise AgentToolError(
            "LAYOUT_SOURCE_MISMATCH",
            "Layout sidecar is bound to a different Markdown source.",
            {"layoutSource": recorded_source, "expectedSource": source_path.name},
        )
    if explicit and recorded_source is None:
        raise AgentToolError(
            "LAYOUT_SOURCE_MISMATCH",
            "An explicit layout sidecar must declare its bound source filename.",
            {"expectedSource": source_path.name},
        )
    recorded = payload.get("sourceHash")
    if recorded and str(recorded).strip().lower() != before_sha256.lower():
        raise AgentToolError(
            "SOURCE_CONFLICT",
            "Layout sidecar sourceHash does not match the current Markdown source.",
            {"layoutPath": str(path), "layoutSourceHash": recorded, "sourceSha256": before_sha256},
        )
    return LayoutSnapshot(path, True, hashlib.sha256(original_bytes).hexdigest(), original, payload)


def _layout_update(
    snapshot: LayoutSnapshot,
    state: DeckState,
    after_sha256: str,
    impact: EditImpact,
) -> LayoutChange | None:
    if not snapshot.exists or snapshot.original is None or snapshot.payload is None:
        return None
    if state.source == impact.source:
        return None
    original = snapshot.original
    payload = snapshot.payload
    slides = payload["slides"]
    assert isinstance(slides, dict)
    migrated: list[dict[str, str]] = []
    if impact.inserted:
        final_numbers = dict(impact.final_numbers)
        for legacy_key in [str(key) for key in slides if LEGACY_PAGE_KEY_RE.fullmatch(str(key))]:
            match = LEGACY_PAGE_KEY_RE.fullmatch(legacy_key)
            assert match is not None
            number = int(match.group(1))
            if not 1 <= number <= len(state.document.slides):
                raise AgentToolError(
                    "UNSTABLE_LAYOUT_OVERRIDE",
                    f"Cannot map stale legacy layout key {legacy_key} before inserting a page.",
                )
            slide = state.document.slides[number - 1]
            explicit_id = slide.config.get("id", "").strip()
            shifted = final_numbers.get(slide.slide_id) != number
            stable_override_exists = slide.slide_id in slides
            if not shifted and not stable_override_exists:
                continue
            if shifted and (not explicit_id or RESERVED_PAGE_ID_RE.fullmatch(slide.slide_id)):
                raise AgentToolError(
                    "UNSTABLE_LAYOUT_OVERRIDE",
                    f"Legacy layout key {legacy_key} cannot be migrated to a stable explicit slide ID.",
                    {"slide": number, "slideId": slide.slide_id},
                )
            if slide.slide_id not in slides:
                slides[slide.slide_id] = slides[legacy_key]
            slides.pop(legacy_key, None)
            migrated.append({"from": legacy_key, "to": slide.slide_id})
    invalidated: list[str] = []
    original_numbers = {slide.slide_id: slide.number for slide in state.document.slides}
    for slide_id in impact.invalidated_ids:
        removed = slides.pop(slide_id, None) is not None
        number = original_numbers.get(slide_id)
        if number is not None:
            removed = slides.pop(f"P{number}", None) is not None or removed
        if removed:
            invalidated.append(slide_id)
    reconciled: list[dict[str, str]] = []
    for slide_id in impact.clear_layout_ids:
        number = original_numbers.get(slide_id)
        for key in (slide_id, f"P{number}" if number is not None else ""):
            raw_override = slides.get(key)
            if not isinstance(raw_override, dict):
                continue
            updated_override = dict(raw_override)
            reconciled_fields: list[str] = []
            if "layout" in updated_override:
                updated_override.pop("layout", None)
                reconciled_fields.append("layout")
            regions = updated_override.get("regions")
            if isinstance(regions, dict):
                content_region = regions.get("content")
                retained_regions = {"content": content_region} if isinstance(content_region, dict) else {}
                if regions != retained_regions:
                    if retained_regions:
                        updated_override["regions"] = retained_regions
                    else:
                        updated_override.pop("regions", None)
                    reconciled_fields.append("regions")
            if not reconciled_fields:
                continue
            if updated_override:
                slides[key] = updated_override
            else:
                slides.pop(key, None)
            reconciled.extend(
                {"slideId": slide_id, "key": key, "field": field}
                for field in reconciled_fields
            )
    payload["sourceHash"] = after_sha256
    updated = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if updated == original:
        return None
    return LayoutChange(
        original,
        updated,
        snapshot.sha256 or build_slides.sha256_source(original),
        build_slides.sha256_source(updated),
        tuple(invalidated),
        tuple(migrated),
        tuple(reconciled),
    )


def _unified_diff(before: str, after: str, path: Path) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    ))


@contextlib.contextmanager
def _source_write_lock(path: Path):
    """Serialize cooperating Agent writers without leaving a file in the deck."""
    if fcntl is None:
        raise AgentToolError("LOCK_UNAVAILABLE", "Safe Agent writes require POSIX advisory file locking.")
    user = str(os.getuid()) if hasattr(os, "getuid") else "default"
    lock_directory = Path(tempfile.gettempdir()) / f"golajah-slide-agent-locks-{user}"
    handle = None
    try:
        lock_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = lock_directory / f"{build_slides.sha256_source(str(path))}.lock"
        handle = lock_path.open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError as error:
        if handle:
            handle.close()
        raise AgentToolError("LOCK_FAILED", f"Cannot acquire the source edit lock: {error}") from error
    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _stage_text(path: Path, source: str) -> Path:
    """Fsync a same-directory temporary file without replacing its target yet."""
    try:
        target_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        target_mode = 0o644
    descriptor = -1
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = -1
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, target_mode)
        return temporary_path
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise


def _read_regular_bytes(path: Path) -> bytes | None:
    """Read one canonical regular-file snapshot without following a replaced leaf symlink."""
    if path.resolve(strict=False) != path:
        raise OSError(f"path no longer resolves to its canonical target: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"expected a regular file: {path}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _current_hash(path: Path) -> str | None:
    try:
        contents = _read_regular_bytes(path)
        return hashlib.sha256(contents).hexdigest() if contents is not None else None
    except OSError as error:
        raise AgentToolError("FILE_READ_FAILED", f"Cannot fingerprint {path}: {error}") from error


def _assert_original_snapshot(state: DeckState, layout: LayoutSnapshot) -> None:
    actual_source = _current_hash(state.path)
    if actual_source != state.document.revision:
        raise AgentToolError(
            "SOURCE_CONFLICT",
            "Markdown source changed immediately before commit.",
            {"expectedSha256": state.document.revision, "actualSha256": actual_source},
        )
    actual_layout = _current_hash(layout.path)
    if actual_layout != layout.sha256:
        raise AgentToolError(
            "LAYOUT_CONFLICT",
            "Layout sidecar appeared, disappeared, or changed immediately before commit.",
            {"expectedSha256": layout.sha256, "actualSha256": actual_layout},
        )


def _restore_if_owned(path: Path, owned_sha256: str, original: str, recovery: dict[str, str], label: str) -> None:
    try:
        actual = _current_hash(path)
        if actual != owned_sha256:
            recovery[label] = "skipped because another process changed the file"
            return
        build_slides.write_text_atomic(path, original)
        recovery[label] = "restored original contents"
    except (AgentToolError, OSError) as error:
        recovery[label] = f"restore failed: {error}"


def _commit_edit(
    state: DeckState,
    updated: str,
    after_sha256: str,
    layout: LayoutSnapshot,
    layout_change: LayoutChange | None,
) -> None:
    source_stage: Path | None = None
    layout_stage: Path | None = None
    source_replaced = False
    layout_replaced = False
    recovery: dict[str, str] = {}
    try:
        source_stage = _stage_text(state.path, updated)
        if layout_change:
            layout_stage = _stage_text(layout.path, layout_change.updated)
        _assert_original_snapshot(state, layout)
        # Commit Markdown first. A hard process termination can still interrupt this
        # two-file transaction, but the survivable state is then new source + old
        # sourceHash-bound layout, which readers reject without destroying overrides.
        if _current_hash(state.path) != state.document.revision:
            raise AgentToolError("SOURCE_CONFLICT", "Markdown source changed during commit.")
        if _current_hash(layout.path) != layout.sha256:
            raise AgentToolError("LAYOUT_CONFLICT", "Layout sidecar changed during commit.")
        assert source_stage is not None
        os.replace(source_stage, state.path)
        source_stage = None
        source_replaced = True
        if _current_hash(state.path) != after_sha256:
            raise OSError("source hash verification failed after atomic replace")
        if _current_hash(layout.path) != layout.sha256:
            raise AgentToolError("LAYOUT_CONFLICT", "Layout sidecar changed before its commit.")
        if layout_stage and layout_change:
            os.replace(layout_stage, layout.path)
            layout_stage = None
            layout_replaced = True
            if _current_hash(layout.path) != layout_change.after_sha256:
                raise OSError("layout hash verification failed after atomic replace")
        expected_layout = layout_change.after_sha256 if layout_change else layout.sha256
        if _current_hash(state.path) != after_sha256:
            raise OSError("source hash verification failed after layout replace")
        if _current_hash(layout.path) != expected_layout:
            raise OSError("layout hash verification failed after commit")
    except Exception as error:
        if layout_replaced and layout_change:
            _restore_if_owned(
                layout.path,
                layout_change.after_sha256,
                layout_change.original,
                recovery,
                "layout",
            )
        if source_replaced:
            _restore_if_owned(state.path, after_sha256, state.source, recovery, "source")
        if isinstance(error, AgentToolError):
            if recovery:
                error.details["recovery"] = recovery
            raise
        raise AgentToolError(
            "WRITE_FAILED",
            f"Cannot write edit transaction: {error}",
            {"recovery": recovery} if recovery else None,
        ) from error
    finally:
        if source_stage:
            source_stage.unlink(missing_ok=True)
        if layout_stage:
            layout_stage.unlink(missing_ok=True)


def edit_deck(
    path: str | Path,
    operations: Any,
    write: bool = False,
    expected_sha256: str | None = None,
    expected_layout_sha256: str | None = None,
    layout_path: str | Path | None = None,
    *,
    allowed_root: str | Path | None = None,
) -> dict[str, Any]:
    """Preview or atomically write a revision-guarded source edit plan."""
    if type(write) is not bool:
        raise AgentToolError("INVALID_ARGUMENTS", "write must be a JSON boolean.")
    if expected_sha256 is not None and not isinstance(expected_sha256, str):
        raise AgentToolError("INVALID_ARGUMENTS", "expected_sha256 must be a string.")
    if expected_layout_sha256 is not None and not isinstance(expected_layout_sha256, str):
        raise AgentToolError("INVALID_ARGUMENTS", "expected_layout_sha256 must be a string.")
    operation_list = _validate_operations(operations)
    source_path = _source_path(path, allowed_root)
    manager = _source_write_lock(source_path) if write else contextlib.nullcontext()
    with manager:
        state = _load_deck(source_path, allowed_root)
        before_sha256 = state.document.revision
        if write and not expected_sha256:
            raise AgentToolError(
                "EXPECTED_SHA256_REQUIRED",
                "Writing requires expected_sha256 from a fresh inspect/get result.",
                {"sourceSha256": before_sha256},
            )
        if expected_sha256 and expected_sha256 != before_sha256:
            raise AgentToolError(
                "SOURCE_CONFLICT",
                "Markdown source changed since the Agent inspected it.",
                {"expectedSha256": expected_sha256, "actualSha256": before_sha256},
            )
        sidecar = _layout_path(state.path, layout_path, allowed_root=allowed_root)
        layout = _read_layout_for_edit(
            sidecar,
            before_sha256,
            state.path,
            explicit=layout_path is not None,
        )
        if layout.exists:
            if write and expected_layout_sha256 is None:
                raise AgentToolError(
                    "EXPECTED_LAYOUT_SHA256_REQUIRED",
                    "Writing with a layout sidecar requires expected_layout_sha256 from a fresh inspect.",
                    {"layoutSha256": layout.sha256},
                )
            if expected_layout_sha256 == "" or (
                expected_layout_sha256 is not None
                and expected_layout_sha256.lower() != str(layout.sha256).lower()
            ):
                raise AgentToolError(
                    "LAYOUT_CONFLICT",
                    "Layout sidecar changed or appeared since the Agent inspected it.",
                    {"expectedSha256": expected_layout_sha256, "actualSha256": layout.sha256},
                )
        elif expected_layout_sha256 not in {None, ""}:
            raise AgentToolError(
                "LAYOUT_CONFLICT",
                "Layout sidecar disappeared since the Agent inspected it.",
                {"expectedSha256": expected_layout_sha256, "actualSha256": None},
            )
        impact = _apply_operations(state, operation_list)
        updated = impact.source
        after_sha256 = build_slides.sha256_source(updated)
        layout_change = _layout_update(layout, state, after_sha256, impact)
        source_diff = _unified_diff(state.source, updated, state.path)
        layout_diff = (
            _unified_diff(layout_change.original, layout_change.updated, sidecar)
            if layout_change else ""
        )
        changed = state.source != updated
        written = False
        if write and changed:
            _commit_edit(state, updated, after_sha256, layout, layout_change)
            written = True
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "edit",
            "source": {"path": str(state.path), "sha256": after_sha256 if written else before_sha256},
            "written": written,
            "dryRun": not write,
            "changed": changed,
            "changedSlideIds": list(impact.changed_ids),
            "beforeSha256": before_sha256,
            "afterSha256": after_sha256,
            "diff": source_diff,
            "layout": {
                "path": str(sidecar),
                "exists": layout.exists,
                "beforeSha256": layout.sha256,
                "afterSha256": layout_change.after_sha256 if layout_change else layout.sha256,
                "updated": bool(layout_change),
                "invalidatedSlides": list(layout_change.invalidated) if layout_change else [],
                "migratedLegacyKeys": list(layout_change.migrated) if layout_change else [],
                "reconciledFields": list(layout_change.reconciled) if layout_change else [],
                "diff": layout_diff,
            },
            "nextStep": (
                "Run audit, then build the delivery HTML."
                if write
                else "Review diff, then repeat with write=true and the current source/layout SHA-256 values."
            ),
        }


def _markdown_report(result: dict[str, Any]) -> str:
    kind = result.get("kind")
    source = result.get("source", {})
    path = source.get("path", "") if isinstance(source, dict) else ""
    sha256 = source.get("sha256", "") if isinstance(source, dict) else ""
    if kind == "inspect":
        counts = result.get("counts", {})
        deck = result.get("deck", {})
        lines = [
            "# GolajahSlide Deck Report",
            "",
            f"- Source: `{path}`",
            f"- SHA-256: `{sha256}`",
            f"- Title: {deck.get('title', '(untitled)') if isinstance(deck, dict) else '(untitled)'}",
            f"- Slides: {counts.get('slides', 0) if isinstance(counts, dict) else 0}",
            "",
            "## Slides",
            "",
            "| Page | ID | Title | Section / Chapter | Layout | Items |",
            "|---:|---|---|---|---|---:|",
        ]
        for slide in result.get("slides", []):
            lines.append(
                f"| {slide['number']} | `{slide['id']}` | {slide['title']} | "
                f"{slide.get('section', '')} / {slide.get('chapter', '')} | {slide.get('layout', 'auto')} | {slide.get('itemCount', 0)} |"
            )
        issues = result.get("issues", [])
        lines.extend(["", "## Structural findings", ""])
        if issues:
            lines.extend(f"- [{issue['severity']}] P{issue.get('slide', '?')} {issue['code']}: {issue['message']}" for issue in issues)
        else:
            lines.append("- No structural findings.")
        return "\n".join(lines) + "\n"
    if kind == "audit":
        report = result.get("report", {})
        warnings = report.get("warnings", []) if isinstance(report, dict) else []
        errors = report.get("errors", []) if isinstance(report, dict) else []
        lines = [
            "# GolajahSlide Quality Audit",
            "",
            f"- Source: `{path}`",
            f"- SHA-256: `{sha256}`",
            f"- Result: {'PASS' if result.get('ok') else 'FAIL'}",
            f"- Strict: `{str(result.get('strict', False)).lower()}`",
            f"- Slides: {report.get('slides', 0) if isinstance(report, dict) else 0}",
            "",
            "## Errors",
            "",
            *([f"- {item}" for item in errors] or ["- None."]),
            "",
            "## Warnings",
            "",
            *([f"- {item}" for item in warnings] or ["- None."]),
        ]
        return "\n".join(lines) + "\n"
    if kind == "search":
        lines = [f"# Search results: {result.get('query', '')}", "", f"Source: `{path}`", ""]
        for match in result.get("matches", []):
            lines.extend([f"## P{match['number']} · {match['title']}", "", match.get("snippet", ""), ""])
        if not result.get("matches"):
            lines.append("No matches.\n")
        return "\n".join(lines)
    if kind == "slide":
        slide = result.get("slide", {})
        return (
            f"# P{slide.get('number', '?')} · {slide.get('title', '')}\n\n"
            f"- ID: `{slide.get('id', '')}`\n- Source SHA-256: `{sha256}`\n\n"
            "```markdown\n" + str(result.get("markdown", "")).rstrip() + "\n```\n"
        )
    if kind == "edit":
        lines = [
            "# GolajahSlide Edit Preview" if result.get("dryRun") else "# GolajahSlide Edit Result",
            "",
            f"- Source: `{path}`",
            f"- Written: `{str(result.get('written', False)).lower()}`",
            f"- Before SHA-256: `{result.get('beforeSha256', '')}`",
            f"- After SHA-256: `{result.get('afterSha256', '')}`",
            "",
            "```diff",
            str(result.get("diff", "")).rstrip(),
            "```",
        ]
        layout = result.get("layout", {})
        if isinstance(layout, dict) and layout.get("diff"):
            lines.extend(["", "## Layout sidecar", "", "```diff", str(layout["diff"]).rstrip(), "```"])
        return "\n".join(lines) + "\n"
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"


def _print_result(
    result: dict[str, Any],
    output_format: str = "json",
    *,
    top_level_ok: bool = True,
) -> None:
    if output_format == "markdown":
        sys.stdout.write(_markdown_report(result))
    else:
        sys.stdout.write(json.dumps({"ok": top_level_ok, "result": result}, ensure_ascii=False, indent=2) + "\n")


def _load_operations(path: str | None, inline: str | None) -> list[dict[str, Any]]:
    if inline is not None:
        raw = inline
    elif path == "-":
        raw = sys.stdin.read()
    elif path:
        try:
            raw = Path(path).expanduser().read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise AgentToolError("OPERATIONS_READ_FAILED", f"Cannot read operations JSON: {error}") from error
    else:
        raise AgentToolError("INVALID_OPERATIONS", "Provide --operations or --operations-json.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AgentToolError("INVALID_OPERATIONS", f"Operations are not valid JSON: {error}") from error
    if isinstance(payload, dict):
        if set(payload) != {"operations"}:
            raise AgentToolError(
                "INVALID_OPERATIONS",
                "Operations wrapper must contain only the operations field.",
            )
        payload = payload["operations"]
    return _validate_operations(payload)


def _tool_schema(
    name: str,
    title: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    *,
    read_only: bool,
    destructive: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only,
            "openWorldHint": False,
        },
    }


SOURCE_PROPERTY = {
    "type": "string",
    "description": "Markdown path relative to the configured MCP root (or an absolute path inside it).",
}


def mcp_tools() -> list[dict[str, Any]]:
    stable_id = {"type": "string", "pattern": EXPLICIT_ID_RE.pattern}
    edit_operation = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "op": {"const": "insert_slide"},
                    "after_slide_id": stable_id,
                    "before_slide_id": stable_id,
                    "markdown": {"type": "string"},
                },
                "required": ["op", "markdown"],
                "not": {"required": ["after_slide_id", "before_slide_id"]},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "op": {"const": "replace_slide"},
                    "slide_id": stable_id,
                    "markdown": {"type": "string"},
                },
                "required": ["op", "slide_id", "markdown"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "op": {"const": "append_content"},
                    "slide_id": stable_id,
                    "markdown": {"type": "string"},
                },
                "required": ["op", "slide_id", "markdown"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "op": {"const": "set_fields"},
                    "slide_id": stable_id,
                    "fields": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "subtitle": {"type": ["string", "null"]},
                            "config": {
                                "type": "object",
                                "minProperties": 1,
                                "propertyNames": {"pattern": CONFIG_KEY_RE.pattern},
                            },
                        },
                        "minProperties": 1,
                        "additionalProperties": False,
                    },
                },
                "required": ["op", "slide_id", "fields"],
                "additionalProperties": False,
            },
        ],
    }
    return [
        _tool_schema(
            "golajah_deck_inspect",
            "Inspect GolajahSlide deck",
            "Read a structured outline, source SHA-256, stable IDs, chapters, item counts and structural findings. Call this before edits.",
            {"source": SOURCE_PROPERTY},
            ["source"],
            read_only=True,
        ),
        _tool_schema(
            "golajah_deck_search",
            "Search GolajahSlide deck",
            "Search titles and authored slide content without reading generated HTML.",
            {
                "source": SOURCE_PROPERTY,
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            ["source", "query"],
            read_only=True,
        ),
        _tool_schema(
            "golajah_slide_get",
            "Get GolajahSlide page",
            "Read one slide by stable ID or 1-based page number, including exact Markdown and structured items.",
            {"source": SOURCE_PROPERTY, "selector": {"type": ["string", "integer"]}},
            ["source", "selector"],
            read_only=True,
        ),
        _tool_schema(
            "golajah_deck_audit",
            "Audit GolajahSlide deck",
            "Run a disposable build and return layout, citation, warning and error diagnostics without leaving artifacts.",
            {"source": SOURCE_PROPERTY, "strict": {"type": "boolean", "default": True}},
            ["source"],
            read_only=True,
        ),
        _tool_schema(
            "golajah_deck_edit",
            "Preview or write GolajahSlide edits",
            "Apply structured operations. Defaults to dry-run. A real write requires write=true, expected_sha256, and the current layout hash when a sidecar exists.",
            {
                "source": SOURCE_PROPERTY,
                "operations": {"type": "array", "minItems": 1, "items": edit_operation},
                "write": {"type": "boolean", "default": False},
                "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_layout_sha256": {
                    "type": "string",
                    "description": "Current layout SHA-256; use an empty string only when inspect observed no sidecar.",
                    "pattern": "^(?:[0-9a-f]{64})?$",
                },
                "layout": {"type": "string", "description": "Optional layout sidecar path inside the MCP root."},
            },
            ["source", "operations"],
            read_only=False,
            destructive=True,
        ),
        _tool_schema(
            "golajah_deck_build",
            "Build GolajahSlide HTML",
            "Replace a .html output and adjacent JSON report from current Markdown. Does not modify Markdown.",
            {
                "source": SOURCE_PROPERTY,
                "output": {"type": "string", "description": "HTML output path inside the MCP root; defaults to index.html beside source."},
                "strict": {"type": "boolean", "default": True},
                "overrides": {"type": "string", "description": "Optional layout sidecar path inside the MCP root."},
            },
            ["source"],
            read_only=False,
            destructive=True,
        ),
    ]


class StdioMCPServer:
    """Small MCP stdio adapter; no optional SDK is required."""

    def __init__(self, root: str | Path):
        self.paths = PathPolicy(root)
        self.protocol_version = MCP_PROTOCOL_VERSIONS[0]
        self.lifecycle = "new"

    def _source(self, arguments: dict[str, Any]) -> Path:
        value = arguments.get("source")
        if not isinstance(value, str) or not value:
            raise AgentToolError("INVALID_ARGUMENTS", "source is required.")
        return self.paths.resolve(value, must_exist=True, file_only=True)

    @staticmethod
    def _boolean(arguments: dict[str, Any], key: str, default: bool) -> bool:
        if key not in arguments:
            return default
        value = arguments[key]
        if type(value) is not bool:
            raise AgentToolError("INVALID_ARGUMENTS", f"{key} must be a JSON boolean.")
        return value

    @staticmethod
    def _optional_string(arguments: dict[str, Any], key: str) -> str | None:
        value = arguments.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise AgentToolError("INVALID_ARGUMENTS", f"{key} must be a string.")
        return value

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        argument_keys = {
            "golajah_deck_inspect": {"source"},
            "golajah_deck_search": {"source", "query", "limit"},
            "golajah_slide_get": {"source", "selector"},
            "golajah_deck_audit": {"source", "strict"},
            "golajah_deck_edit": {
                "source", "operations", "write", "expected_sha256",
                "expected_layout_sha256", "layout",
            },
            "golajah_deck_build": {"source", "output", "strict", "overrides"},
        }
        allowed = argument_keys.get(name)
        if allowed is None:
            raise AgentToolError("TOOL_NOT_FOUND", f"Unknown MCP tool: {name}")
        unknown = sorted(set(arguments) - allowed)
        if unknown:
            raise AgentToolError(
                "INVALID_ARGUMENTS",
                f"Unexpected argument(s) for {name}: {', '.join(unknown)}",
            )
        source = self._source(arguments)
        if name in {"golajah_deck_inspect", "golajah_deck_audit", "golajah_deck_edit", "golajah_deck_build"}:
            explicit_companion = arguments.get("layout") if name == "golajah_deck_edit" else arguments.get("overrides")
            if not explicit_companion:
                self.paths.resolve(source.with_suffix(".layout.json"))
        if name == "golajah_deck_inspect":
            return inspect_deck(source, asset_root=self.paths.root)
        if name == "golajah_deck_search":
            query = arguments.get("query")
            if not isinstance(query, str):
                raise AgentToolError("INVALID_ARGUMENTS", "query must be a string.")
            limit = arguments.get("limit", 20)
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise AgentToolError("INVALID_ARGUMENTS", "limit must be an integer.")
            if not 1 <= limit <= 100:
                raise AgentToolError("INVALID_ARGUMENTS", "limit must be between 1 and 100.")
            return search_deck(source, query, limit, asset_root=self.paths.root)
        if name == "golajah_slide_get":
            if "selector" not in arguments:
                raise AgentToolError("INVALID_ARGUMENTS", "selector is required.")
            if isinstance(arguments["selector"], bool) or not isinstance(arguments["selector"], (str, int)):
                raise AgentToolError("INVALID_ARGUMENTS", "selector must be a string or integer.")
            return get_slide(source, arguments["selector"], asset_root=self.paths.root)
        if name == "golajah_deck_audit":
            return audit_deck(
                source,
                self._boolean(arguments, "strict", True),
                asset_root=self.paths.root,
            )
        if name == "golajah_deck_edit":
            operations = arguments.get("operations")
            layout = self._optional_string(arguments, "layout")
            layout_path = self.paths.resolve(layout) if layout else None
            expected_source = self._optional_string(arguments, "expected_sha256")
            if expected_source is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_source):
                raise AgentToolError("INVALID_ARGUMENTS", "expected_sha256 must be a lowercase SHA-256 value.")
            expected_layout = self._optional_string(arguments, "expected_layout_sha256")
            if expected_layout is not None and not re.fullmatch(r"(?:[0-9a-f]{64})?", expected_layout):
                raise AgentToolError(
                    "INVALID_ARGUMENTS",
                    "expected_layout_sha256 must be empty or a lowercase SHA-256 value.",
                )
            return edit_deck(
                source,
                operations,
                write=self._boolean(arguments, "write", False),
                expected_sha256=expected_source,
                expected_layout_sha256=expected_layout,
                layout_path=layout_path,
                allowed_root=self.paths.root,
            )
        if name == "golajah_deck_build":
            raw_output = self._optional_string(arguments, "output")
            output = self.paths.resolve(raw_output if raw_output else source.with_name("index.html"))
            raw_overrides = self._optional_string(arguments, "overrides")
            overrides = self.paths.resolve(raw_overrides, must_exist=True, file_only=True) if raw_overrides else None
            return build_deck(
                source,
                output,
                self._boolean(arguments, "strict", True),
                overrides,
                asset_root=self.paths.root,
            )
        raise AgentToolError("TOOL_NOT_FOUND", f"Unknown MCP tool: {name}")  # pragma: no cover

    @staticmethod
    def _response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    @staticmethod
    def _tool_result(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "structuredContent": payload,
            "isError": is_error,
        }

    @staticmethod
    def _valid_initialize_params(params: dict[str, Any]) -> bool:
        protocol_version = params.get("protocolVersion")
        capabilities = params.get("capabilities")
        client_info = params.get("clientInfo")
        return (
            isinstance(protocol_version, str)
            and bool(protocol_version)
            and isinstance(capabilities, dict)
            and isinstance(client_info, dict)
            and isinstance(client_info.get("name"), str)
            and bool(client_info["name"])
            and isinstance(client_info.get("version"), str)
            and bool(client_info["version"])
        )

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
        method = message.get("method")
        is_request = "id" in message
        request_id = message.get("id")
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid params") if is_request else None
        if method == "initialize":
            if not is_request:
                return None
            if self.lifecycle != "new":
                return self._error(request_id, -32600, "Server is already initialized")
            if not self._valid_initialize_params(params):
                return self._error(request_id, -32602, "Invalid initialize params")
            requested = str(params.get("protocolVersion", ""))
            self.protocol_version = requested if requested in MCP_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSIONS[0]
            self.lifecycle = "initializing"
            return self._response(request_id, {
                "protocolVersion": self.protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "golajah-slide",
                    "title": "GolajahSlide Agent Tools",
                    "version": VERSION,
                },
                "instructions": (
                    "Inspect before editing. Use stable slide IDs. Edits are dry-run unless write=true, "
                    "and writes require the latest source SHA-256 plus layout SHA-256 when a sidecar exists. "
                    "All paths stay inside the configured root."
                ),
            })
        if method == "notifications/initialized":
            if not is_request and self.lifecycle == "initializing":
                self.lifecycle = "ready"
            return None
        if method == "notifications/cancelled":
            return None
        if not is_request:
            return None
        if method == "ping":
            return self._response(request_id, {})
        if method in {"tools/list", "tools/call"} and self.lifecycle != "ready":
            return self._error(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return self._response(request_id, {"tools": mcp_tools()})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if arguments is None:
                arguments = {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self._error(request_id, -32602, "Invalid tools/call params")
            try:
                payload = self.call_tool(name, arguments)
                return self._response(request_id, self._tool_result(payload))
            except AgentToolError as error:
                if error.code == "TOOL_NOT_FOUND":
                    return self._error(request_id, -32602, error.message)
                return self._response(request_id, self._tool_result({"error": error.payload()}, is_error=True))
            except Exception:
                return self._error(request_id, -32603, "Internal error")
        return self._error(request_id, -32601, "Method not found")

    def run(self) -> int:
        for raw_line in sys.stdin.buffer:
            try:
                message = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                response: Any = self._error(None, -32700, "Parse error", str(error))
            else:
                if isinstance(message, list):
                    response = self._error(
                        None,
                        -32600,
                        "Invalid Request",
                        "Batch requests are not supported.",
                    )
                else:
                    response = self.handle(message)
                    if response is None:
                        continue
            encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
            sys.stdout.write(encoded + "\n")
            sys.stdout.flush()
        return 0


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AgentToolError("INVALID_ARGUMENTS", message)


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Inspect, audit, safely edit and build GolajahSlide Markdown for Agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_format(command: argparse.ArgumentParser) -> None:
        command.add_argument("--format", choices=["json", "markdown"], default="json")

    inspect_parser = subparsers.add_parser("inspect", help="return deck outline and source revision")
    inspect_parser.add_argument("source", type=Path)
    add_format(inspect_parser)

    search_parser = subparsers.add_parser("search", help="search titles and authored content")
    search_parser.add_argument("source", type=Path)
    search_parser.add_argument("query", nargs="?")
    search_parser.add_argument("--query", dest="query_option")
    search_parser.add_argument("--limit", type=int, default=20)
    add_format(search_parser)

    get_parser = subparsers.add_parser("get", help="read one slide by ID or page number")
    get_parser.add_argument("source", type=Path)
    get_parser.add_argument("selector", nargs="?")
    selector_group = get_parser.add_mutually_exclusive_group()
    selector_group.add_argument("--slide-id", "--slide", dest="slide_id")
    selector_group.add_argument("--page", type=int)
    add_format(get_parser)

    audit_parser = subparsers.add_parser("audit", help="run a disposable quality build")
    audit_parser.add_argument("source", type=Path)
    audit_parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    add_format(audit_parser)

    edit_parser = subparsers.add_parser("edit", help="preview or write a guarded operation plan")
    edit_parser.add_argument("source", type=Path)
    operations_group = edit_parser.add_mutually_exclusive_group(required=True)
    operations_group.add_argument("--operations", "--operation-file", dest="operations", help="JSON file path, or '-' for stdin")
    operations_group.add_argument("--operations-json", help="inline JSON array")
    edit_parser.add_argument("--write", action="store_true")
    edit_parser.add_argument("--expect-source-sha256", "--expected-sha256", dest="expected_sha256")
    edit_parser.add_argument("--expect-layout-sha256", "--expected-layout-sha256", dest="expected_layout_sha256")
    edit_parser.add_argument("--layout", type=Path)
    add_format(edit_parser)

    build_parser = subparsers.add_parser("build", help="build a delivery HTML and report")
    build_parser.add_argument("source", type=Path)
    build_parser.add_argument("-o", "--output", type=Path)
    build_parser.add_argument("--overrides", type=Path)
    build_parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    add_format(build_parser)

    mcp_parser = subparsers.add_parser("mcp", help="serve the same operations over stdio MCP")
    mcp_parser.add_argument("--root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "mcp":
            return StdioMCPServer(args.root).run()
        if args.command == "inspect":
            result = inspect_deck(args.source)
        elif args.command == "search":
            if args.query is not None and args.query_option is not None:
                raise AgentToolError(
                    "INVALID_ARGUMENTS",
                    "Provide the search query either positionally or with --query, not both.",
                )
            query = args.query_option if args.query_option is not None else args.query
            if query is None:
                raise AgentToolError("INVALID_QUERY", "Provide a search query as a positional argument or with --query.")
            result = search_deck(args.source, query, args.limit)
        elif args.command == "get":
            selectors = (args.selector, args.slide_id, args.page)
            if sum(value is not None for value in selectors) > 1:
                raise AgentToolError(
                    "INVALID_ARGUMENTS",
                    "Provide exactly one slide selector: positional, --slide-id or --page.",
                )
            selector = args.slide_id if args.slide_id is not None else args.page if args.page is not None else args.selector
            if selector is None:
                raise AgentToolError("SLIDE_SELECTOR_REQUIRED", "Provide selector, --slide-id or --page.")
            result = get_slide(args.source, selector)
        elif args.command == "audit":
            result = audit_deck(args.source, args.strict)
        elif args.command == "edit":
            operations = _load_operations(args.operations, args.operations_json)
            result = edit_deck(
                args.source,
                operations,
                write=args.write,
                expected_sha256=args.expected_sha256,
                expected_layout_sha256=args.expected_layout_sha256,
                layout_path=args.layout,
            )
        elif args.command == "build":
            output = args.output or args.source.with_name("index.html")
            result = build_deck(args.source, output, args.strict, args.overrides)
        else:  # pragma: no cover - argparse enforces a subcommand.
            raise AgentToolError("UNKNOWN_COMMAND", f"Unknown command: {args.command}")
        domain_ok = not (args.command in {"audit", "build"} and not result.get("ok", False))
        _print_result(result, args.format, top_level_ok=domain_ok)
        if not domain_ok:
            return 1
        return 0
    except AgentToolError as error:
        sys.stdout.write(json.dumps({"ok": False, "error": error.payload()}, ensure_ascii=False) + "\n")
        return 2
    except Exception as error:
        payload = {
            "code": "INTERNAL_ERROR",
            "message": f"Unexpected command failure: {error}",
        }
        sys.stdout.write(json.dumps({"ok": False, "error": payload}, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
