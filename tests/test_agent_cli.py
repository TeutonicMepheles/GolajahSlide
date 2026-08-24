import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import golajah_slide_agent


ROOT = Path(__file__).resolve().parents[1]
AGENT_CLI = ROOT / "golajah_slide_agent.py"

DECK_SOURCE = """---
title: Agent 契约示例
author: Golajah
sections: ["基础", "进阶"]
---

<!-- slide
id: intro
type: content
layout: text
section: 基础
chapter: 开场
-->
# 稳定开场
## Agent 可以按稳定 ID 读取

### 核心结论

使用源码指纹避免覆盖并发修改。

---

<!-- slide
id: details
type: content
layout: text
section: 进阶
chapter: 细节
-->
# 实现细节

### 安全写入

默认只生成 diff，显式确认后才写入。
"""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AgentCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "slides.md"
        self.source.write_text(DECK_SOURCE, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def ready_mcp(self, protocol_version="2025-11-25"):
        server = golajah_slide_agent.StdioMCPServer(self.root)
        initialized = server.handle({
            "jsonrpc": "2.0",
            "id": "initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "unit-test", "version": "1.0"},
            },
        })
        self.assertEqual(initialized["result"]["protocolVersion"], protocol_version)
        self.assertIsNone(server.handle({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }))
        return server

    def test_inspect_search_and_get_use_stable_slide_identity(self):
        inspected = golajah_slide_agent.inspect_deck(self.source)
        self.assertEqual(inspected["source"]["sha256"], sha256_text(DECK_SOURCE))
        self.assertEqual(inspected["deck"]["title"], "Agent 契约示例")
        self.assertEqual([slide["id"] for slide in inspected["slides"]], ["intro", "details"])
        self.assertEqual(inspected["slides"][0]["chapter"], "开场")

        matches = golajah_slide_agent.search_deck(self.source, "安全写入")
        self.assertEqual([match["id"] for match in matches["matches"]], ["details"])

        by_id = golajah_slide_agent.get_slide(self.source, "intro")
        by_number = golajah_slide_agent.get_slide(self.source, "2")
        self.assertEqual(by_id["slide"]["title"], "稳定开场")
        self.assertEqual(by_number["slide"]["id"], "details")
        self.assertIn("使用源码指纹", by_id["markdown"])

    def test_audit_and_build_return_reports_without_polluting_source_directory(self):
        before = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))
        audited = golajah_slide_agent.audit_deck(self.source, strict=True)
        after = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(audited["report"]["errors"], [])
        self.assertEqual(audited["report"]["warnings"], [])
        self.assertEqual(audited["report"]["slides"], 2)

        output = self.root / "built" / "index.html"
        built = golajah_slide_agent.build_deck(self.source, output, strict=True)
        self.assertTrue(output.is_file())
        self.assertTrue(output.with_suffix(".build.json").is_file())
        self.assertEqual(built["report"]["errors"], [])
        self.assertEqual(built["report"]["slides"], 2)

    def test_edit_is_dry_run_by_default_and_write_requires_current_hash(self):
        original = self.source.read_bytes()
        operation = {
            "op": "set_fields",
            "slide_id": "intro",
            "fields": {
                "title": "更新后的开场",
                "config": {"chapter": "新的 Chapter item"},
            },
        }
        preview = golajah_slide_agent.edit_deck(self.source, [operation])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(preview["written"])
        self.assertIn("更新后的开场", preview["diff"])
        self.assertNotEqual(preview["beforeSha256"], preview["afterSha256"])

        with self.assertRaises(golajah_slide_agent.AgentToolError) as missing:
            golajah_slide_agent.edit_deck(self.source, [operation], write=True)
        self.assertEqual(missing.exception.code, "EXPECTED_SHA256_REQUIRED")
        self.assertEqual(self.source.read_bytes(), original)

        with self.assertRaises(golajah_slide_agent.AgentToolError) as stale:
            golajah_slide_agent.edit_deck(
                self.source,
                [operation],
                write=True,
                expected_sha256="0" * 64,
            )
        self.assertEqual(stale.exception.code, "SOURCE_CONFLICT")
        self.assertEqual(self.source.read_bytes(), original)

        written = golajah_slide_agent.edit_deck(
            self.source,
            [operation],
            write=True,
            expected_sha256=sha256_text(DECK_SOURCE),
        )
        self.assertTrue(written["written"])
        self.assertEqual(written["afterSha256"], sha256_text(self.source.read_text(encoding="utf-8")))
        reparsed = golajah_slide_agent.get_slide(self.source, "intro")
        self.assertEqual(reparsed["slide"]["title"], "更新后的开场")
        self.assertEqual(reparsed["slide"]["chapter"], "新的 Chapter item")

    def test_edit_rejects_missing_duplicate_or_changed_stable_ids_atomically(self):
        original = self.source.read_bytes()
        missing_id = """<!-- slide
type: content
layout: auto
-->
# 缺少 ID

正文。
"""
        with self.assertRaises(golajah_slide_agent.AgentToolError):
            golajah_slide_agent.edit_deck(
                self.source,
                [{"op": "insert_slide", "after_slide_id": "intro", "markdown": missing_id}],
            )

        duplicate_id = """<!-- slide
id: intro
type: content
layout: auto
-->
# 重复 ID

正文。
"""
        with self.assertRaises(golajah_slide_agent.AgentToolError):
            golajah_slide_agent.edit_deck(
                self.source,
                [{"op": "insert_slide", "after_slide_id": "intro", "markdown": duplicate_id}],
            )

        changed_id = """<!-- slide
id: replacement-id
type: content
layout: text
-->
# 替换内容

正文。
"""
        with self.assertRaises(golajah_slide_agent.AgentToolError):
            golajah_slide_agent.edit_deck(
                self.source,
                [{"op": "replace_slide", "slide_id": "intro", "markdown": changed_id}],
            )
        self.assertEqual(self.source.read_bytes(), original)

    def test_all_supported_edit_operations_compose_in_one_transaction(self):
        operations = [
            {
                "op": "replace_slide",
                "slide_id": "details",
                "markdown": """<!-- slide
id: details
type: content
layout: text
section: 进阶
chapter: 细节
-->
# 替换后的实现细节

### 新结论

整个页面可以安全替换，但稳定 ID 不变。
""",
            },
            {
                "op": "append_content",
                "slide_id": "intro",
                "markdown": "> [!NOTE] Agent 提示\n> 这是追加到现有页面的内容。",
            },
            {
                "op": "insert_slide",
                "after_slide_id": "details",
                "markdown": """<!-- slide
id: closing
type: content
layout: text
section: 进阶
chapter: 总结
-->
# 新增总结

### 下一步

运行 audit 与严格构建。
""",
            },
            {
                "op": "set_fields",
                "slide_id": "intro",
                "fields": {"subtitle": "更新后的副标题", "config": {"chapter": "Agent 开场"}},
            },
        ]
        preview = golajah_slide_agent.edit_deck(self.source, operations)
        self.assertFalse(preview["written"])
        self.assertEqual(preview["changedSlideIds"], ["details", "intro", "closing"])
        self.assertIn("新增总结", preview["diff"])
        self.assertEqual(self.source.read_text(encoding="utf-8"), DECK_SOURCE)

        result = golajah_slide_agent.edit_deck(
            self.source,
            operations,
            write=True,
            expected_sha256=sha256_text(DECK_SOURCE),
        )
        self.assertTrue(result["written"])
        inspected = golajah_slide_agent.inspect_deck(self.source)
        self.assertEqual([slide["id"] for slide in inspected["slides"]], ["intro", "details", "closing"])
        self.assertEqual(inspected["slides"][0]["chapter"], "Agent 开场")
        self.assertEqual(inspected["slides"][0]["subtitle"], "更新后的副标题")
        self.assertEqual(inspected["slides"][1]["title"], "替换后的实现细节")
        self.assertIn("Agent 提示", golajah_slide_agent.get_slide(self.source, "intro")["markdown"])

    def test_edit_rebases_layout_hash_and_preserves_stable_slide_override(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {
                "intro": {
                    "layout": "split",
                    "regions": {"content": {"x": 100, "y": 200, "width": 1200, "height": 700}},
                },
                "details": {
                    "layout": "text",
                    "typography": {"lineHeight": 1.5, "color": "#222222", "bold": False},
                },
            },
        }
        layout_source = json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        operation = {"op": "set_fields", "slide_id": "intro", "fields": {"title": "带布局的更新"}}

        preview = golajah_slide_agent.edit_deck(self.source, [operation])
        self.assertFalse(preview["written"])
        self.assertTrue(preview["layout"]["updated"])
        self.assertEqual(preview["layout"]["invalidatedSlides"], [])
        self.assertIn('"sourceHash"', preview["layout"]["diff"])
        self.assertEqual(layout_path.read_text(encoding="utf-8"), layout_source)
        self.assertEqual(self.source.read_text(encoding="utf-8"), DECK_SOURCE)

        written = golajah_slide_agent.edit_deck(
            self.source,
            [operation],
            write=True,
            expected_sha256=before_sha256,
            expected_layout_sha256=sha256_text(layout_source),
        )
        updated_layout = json.loads(layout_path.read_text(encoding="utf-8"))
        self.assertEqual(updated_layout["sourceHash"], written["afterSha256"])
        self.assertEqual(updated_layout["slides"]["intro"], layout_payload["slides"]["intro"])
        self.assertEqual(updated_layout["slides"]["details"], layout_payload["slides"]["details"])

    def test_edit_preserves_utf8_bom_and_crlf_in_dry_run_and_write(self):
        crlf_source = "\ufeff" + DECK_SOURCE.replace("\n", "\r\n")
        original_bytes = crlf_source.encode("utf-8")
        self.source.write_bytes(original_bytes)
        before_sha256 = hashlib.sha256(original_bytes).hexdigest()
        operation = {
            "op": "set_fields",
            "slide_id": "intro",
            "fields": {"title": "保留 BOM 与 CRLF"},
        }

        preview = golajah_slide_agent.edit_deck(self.source, [operation])
        self.assertFalse(preview["written"])
        self.assertEqual(self.source.read_bytes(), original_bytes)
        self.assertNotEqual(preview["beforeSha256"], preview["afterSha256"])

        written = golajah_slide_agent.edit_deck(
            self.source,
            [operation],
            write=True,
            expected_sha256=before_sha256,
        )
        updated_bytes = self.source.read_bytes()
        updated_source = updated_bytes.decode("utf-8")
        self.assertTrue(updated_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(updated_source.startswith("\ufeff"))
        self.assertIn("\r\n", updated_source)
        self.assertNotIn("\n", updated_source.replace("\r\n", ""))
        self.assertNotIn("\r", updated_source.replace("\r\n", ""))
        self.assertEqual(written["afterSha256"], hashlib.sha256(updated_bytes).hexdigest())
        inspected = golajah_slide_agent.inspect_deck(self.source)
        self.assertTrue(inspected["source"]["bom"])
        self.assertEqual(inspected["source"]["newline"], "\r\n")
        self.assertEqual(inspected["source"]["sha256"], written["afterSha256"])

    def test_append_content_rejects_top_level_slide_separator_without_writing(self):
        original_bytes = self.source.read_bytes()
        before_sha256 = hashlib.sha256(original_bytes).hexdigest()
        injected_page = """追加到原页的正文。

---

<!-- slide
id: injected-page
type: content
layout: text
-->
# 不应通过 append_content 注入的新页

这段内容不能悄悄扩大页面边界。
"""
        caught = None
        try:
            golajah_slide_agent.edit_deck(
                self.source,
                [{"op": "append_content", "slide_id": "intro", "markdown": injected_page}],
                write=True,
                expected_sha256=before_sha256,
            )
        except golajah_slide_agent.AgentToolError as error:
            caught = error

        self.assertEqual(self.source.read_bytes(), original_bytes)
        self.assertIsNotNone(caught, "append_content must reject a top-level slide separator")
        self.assertEqual(
            [slide["id"] for slide in golajah_slide_agent.inspect_deck(self.source)["slides"]],
            ["intro", "details"],
        )

    def test_replace_slide_removes_old_tail_after_citation_but_keeps_global_definition(self):
        citation_source = """---
title: Citation replacement
---

<!-- slide
id: cited
type: content
layout: text
-->
# 原引用页

旧正文引用共享来源[^shared]。

[^shared]: 共享来源 — https://example.com/shared

### OLD TAIL AFTER CITATION

引用定义之后的旧正文也属于被替换页面，不能残留。
"""
        self.source.write_text(citation_source, encoding="utf-8")
        replacement = """<!-- slide
id: cited
type: content
layout: text
-->
# 新引用页

全新正文继续引用共享来源[^shared]。
"""
        golajah_slide_agent.edit_deck(
            self.source,
            [{"op": "replace_slide", "slide_id": "cited", "markdown": replacement}],
            write=True,
            expected_sha256=sha256_text(citation_source),
        )
        updated = self.source.read_text(encoding="utf-8")
        self.assertEqual(updated.count("[^shared]: 共享来源 — https://example.com/shared"), 1)
        self.assertIn("全新正文继续引用共享来源", updated)
        self.assertNotIn("OLD TAIL AFTER CITATION", updated)
        self.assertNotIn("引用定义之后的旧正文", updated)
        audited = golajah_slide_agent.audit_deck(self.source, strict=True)
        self.assertTrue(audited["ok"], audited)

    def test_insert_slide_removes_all_legacy_page_overrides_before_rebuild(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        stable_intro = {"layout": "text", "typography": {"lineHeight": 1.4}}
        stable_details = {"layout": "text", "typography": {"lineHeight": 1.6}}
        layout_source = json.dumps({
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {
                "P1": {"layout": "media"},
                "P2": {"layout": "text"},
                "intro": stable_intro,
                "details": stable_details,
            },
        }, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        inserted = """<!-- slide
id: inserted
type: content
layout: auto
section: 进阶
chapter: 插入页
-->
# 插入页面

### 说明

旧的 P2 覆盖不能套到这一页。
"""
        golajah_slide_agent.edit_deck(
            self.source,
            [{"op": "insert_slide", "after_slide_id": "intro", "markdown": inserted}],
            write=True,
            expected_sha256=before_sha256,
            expected_layout_sha256=sha256_text(layout_source),
        )
        updated_layout = json.loads(layout_path.read_text(encoding="utf-8"))
        self.assertFalse(any(re.fullmatch(r"P\d+", key) for key in updated_layout["slides"]))
        self.assertEqual(updated_layout["slides"]["intro"], stable_intro)
        self.assertEqual(updated_layout["slides"]["details"], stable_details)

        built = golajah_slide_agent.build_deck(self.source, self.root / "index.html", strict=True)
        self.assertNotIn("inserted", built["report"]["layoutOverrides"]["appliedSlides"])

    def test_direct_and_mcp_build_reject_non_html_output_without_overwriting_victim(self):
        problems = []
        server = golajah_slide_agent.StdioMCPServer(self.root)
        cases = {
            "direct": lambda victim: golajah_slide_agent.build_deck(self.source, victim, strict=True),
            "mcp": lambda victim: server.call_tool(
                "golajah_deck_build",
                {"source": "slides.md", "output": victim.name, "strict": True},
            ),
        }
        for mode, invoke in cases.items():
            victim = self.root / f"victim-{mode}.md"
            marker = f"DO NOT OVERWRITE {mode}\n"
            victim.write_text(marker, encoding="utf-8")
            error = None
            try:
                invoke(victim)
            except golajah_slide_agent.AgentToolError as caught:
                error = caught
            if victim.read_text(encoding="utf-8") != marker:
                problems.append(f"{mode} overwrote a non-HTML victim")
            if victim.with_suffix(".build.json").exists():
                problems.append(f"{mode} wrote a build report beside a non-HTML victim")
            if error is None:
                problems.append(f"{mode} accepted a non-.html output")
        self.assertEqual(problems, [])

    def test_mcp_default_build_output_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside_directory:
            outside = Path(outside_directory)
            victim = outside / "victim.html"
            victim.write_text("keep", encoding="utf-8")
            (self.root / "index.html").symlink_to(victim)

            server = golajah_slide_agent.StdioMCPServer(self.root)
            with self.assertRaises(golajah_slide_agent.AgentToolError) as context:
                server.call_tool("golajah_deck_build", {"source": "slides.md"})

            self.assertEqual(context.exception.code, "PATH_OUTSIDE_ROOT")
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep")
            self.assertFalse((outside / "victim.build.json").exists())

    def test_noop_set_fields_does_not_invalidate_layout_override(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {
                "intro": {"layout": "split", "regions": {"visual": {"x": 100, "y": 200, "width": 600, "height": 500}}},
                "details": {"layout": "text"},
            },
        }
        layout_source = json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        operation = {
            "op": "set_fields",
            "slide_id": "intro",
            "fields": {"title": "稳定开场", "subtitle": "Agent 可以按稳定 ID 读取", "config": {"chapter": "开场"}},
        }

        preview = golajah_slide_agent.edit_deck(self.source, [operation])
        self.assertFalse(preview["changed"])
        self.assertEqual(preview["beforeSha256"], preview["afterSha256"])
        self.assertEqual(preview["diff"], "")
        self.assertFalse(preview["layout"]["updated"])
        self.assertEqual(preview["layout"]["invalidatedSlides"], [])
        self.assertEqual(preview["layout"]["diff"], "")
        self.assertEqual(layout_path.read_text(encoding="utf-8"), layout_source)

    def test_mcp_string_false_write_is_invalid_and_never_writes_source(self):
        original = self.source.read_bytes()
        server = self.ready_mcp()
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 91,
            "method": "tools/call",
            "params": {
                "name": "golajah_deck_edit",
                "arguments": {
                    "source": "slides.md",
                    "operations": [{
                        "op": "set_fields",
                        "slide_id": "intro",
                        "fields": {"title": "字符串 false 不能触发写入"},
                    }],
                    "write": "false",
                    "expected_sha256": sha256_text(DECK_SOURCE),
                },
            },
        })
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue(response["result"]["isError"])
        error = response["result"]["structuredContent"]["error"]
        self.assertEqual(error["code"], "INVALID_ARGUMENTS")

    def test_get_rejects_non_markdown_source_in_direct_and_mcp_interfaces(self):
        html_source = self.root / "deck.html"
        text_source = self.root / "notes.txt"
        html_source.write_text(DECK_SOURCE, encoding="utf-8")
        text_source.write_text(DECK_SOURCE, encoding="utf-8")
        server = golajah_slide_agent.StdioMCPServer(self.root)
        problems = []
        for label, invoke in {
            "direct-html": lambda: golajah_slide_agent.get_slide(html_source, "intro"),
            "mcp-arbitrary": lambda: server.call_tool(
                "golajah_slide_get",
                {"source": text_source.name, "selector": "intro"},
            ),
        }.items():
            try:
                invoke()
            except golajah_slide_agent.AgentToolError:
                continue
            problems.append(f"{label} accepted a source that does not end with .md")
        self.assertEqual(problems, [])

    def test_mcp_build_rejects_local_media_outside_configured_root(self):
        outside = self.root.parent / f"{self.root.name}-outside.png"
        outside.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        ))
        self.addCleanup(outside.unlink, missing_ok=True)
        self.source.write_text(f"""<!-- slide
id: outside-media
type: content
layout: media
-->
# Root 外媒体

![不应读取的外部文件](../{outside.name})
""", encoding="utf-8")
        output = self.root / "outside-media.html"
        server = golajah_slide_agent.StdioMCPServer(self.root)
        error = None
        try:
            server.call_tool(
                "golajah_deck_build",
                {"source": "slides.md", "output": output.name, "strict": True},
            )
        except golajah_slide_agent.AgentToolError as caught:
            error = caught
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".build.json").exists())
        self.assertIsNotNone(error, "MCP build must reject media outside its configured root")
        self.assertEqual(error.code, "PATH_OUTSIDE_ROOT")

    def test_mcp_layout_write_requires_expected_layout_sha256(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        layout_source = json.dumps({
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {"intro": {"layout": "text"}},
        }, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        original_source = self.source.read_bytes()
        original_layout = layout_path.read_bytes()
        server = golajah_slide_agent.StdioMCPServer(self.root)
        error = None
        try:
            server.call_tool("golajah_deck_edit", {
                "source": "slides.md",
                "operations": [{
                    "op": "set_fields",
                    "slide_id": "intro",
                    "fields": {"title": "需要布局哈希"},
                }],
                "write": True,
                "expected_sha256": before_sha256,
            })
        except golajah_slide_agent.AgentToolError as caught:
            error = caught
        self.assertEqual(self.source.read_bytes(), original_source)
        self.assertEqual(layout_path.read_bytes(), original_layout)
        self.assertIsNotNone(error)
        self.assertEqual(error.code, "EXPECTED_LAYOUT_SHA256_REQUIRED")
        edit_tool = next(tool for tool in golajah_slide_agent.mcp_tools() if tool["name"] == "golajah_deck_edit")
        self.assertIn("expected_layout_sha256", edit_tool["inputSchema"]["properties"])

    def test_layout_hash_guard_rejects_mismatch_appearance_and_disappearance(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        layout_source = json.dumps({
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {"intro": {"layout": "text"}},
        }, ensure_ascii=False, indent=2) + "\n"
        observed_layout_sha256 = sha256_text(layout_source)
        cases = {
            "mismatch": {"actual": layout_source, "expected": "0" * 64},
            "appeared": {"actual": layout_source, "expected": ""},
            "disappeared": {"actual": None, "expected": observed_layout_sha256},
        }
        problems = []
        for label, case in cases.items():
            self.source.write_text(DECK_SOURCE, encoding="utf-8")
            if case["actual"] is None:
                layout_path.unlink(missing_ok=True)
            else:
                layout_path.write_text(case["actual"], encoding="utf-8")
            original_source = self.source.read_bytes()
            original_layout = layout_path.read_bytes() if layout_path.exists() else None
            error = None
            try:
                golajah_slide_agent.edit_deck(
                    self.source,
                    [{
                        "op": "set_fields",
                        "slide_id": "intro",
                        "fields": {"title": f"布局冲突 {label}"},
                    }],
                    write=True,
                    expected_sha256=before_sha256,
                    expected_layout_sha256=case["expected"],
                )
            except golajah_slide_agent.AgentToolError as caught:
                error = caught
            except Exception as caught:  # The public API must normalize failures.
                problems.append(f"{label} raised unexpected {type(caught).__name__}")
            if self.source.read_bytes() != original_source:
                problems.append(f"{label} changed source")
            current_layout = layout_path.read_bytes() if layout_path.exists() else None
            if current_layout != original_layout:
                problems.append(f"{label} changed layout")
            if error is None:
                problems.append(f"{label} did not raise AgentToolError")
            elif error.code not in {"LAYOUT_CONFLICT", "SOURCE_CONFLICT"}:
                problems.append(f"{label} returned {error.code}")
        self.assertEqual(problems, [])

    def test_custom_layout_path_and_document_shape_are_validated(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        valid = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {},
        }
        cases = {
            "suffix": (self.root / "custom.json", valid),
            "source": (self.root / "wrong-source.layout.json", {**valid, "source": "other.md"}),
            "slides": (self.root / "wrong-slides.layout.json", {**valid, "slides": []}),
            "schema": (self.root / "wrong-schema.layout.json", {**valid, "schemaVersion": "99.0"}),
        }
        operation = {"op": "set_fields", "slide_id": "intro", "fields": {"title": "布局校验"}}
        problems = []
        for label, (path, payload) in cases.items():
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                golajah_slide_agent.edit_deck(self.source, [operation], layout_path=path)
            except golajah_slide_agent.AgentToolError:
                continue
            problems.append(f"{label} custom layout was accepted")
        self.assertEqual(problems, [])

    def test_set_fields_preserves_unmodified_directive_comments_and_spacing(self):
        source = """---
title: Directive fidelity
---

<!-- slide
id: styled
type :  content
# keep this editorial directive comment
layout:    text
section :   基础
chapter: 开场
image-fit:   contain
-->
# 保留格式

正文。
"""
        self.source.write_text(source, encoding="utf-8")
        golajah_slide_agent.edit_deck(
            self.source,
            [{
                "op": "set_fields",
                "slide_id": "styled",
                "fields": {"config": {"chapter": "新的归属"}},
            }],
            write=True,
            expected_sha256=sha256_text(source),
        )
        updated = self.source.read_text(encoding="utf-8")
        self.assertIn("type :  content", updated)
        self.assertIn("# keep this editorial directive comment", updated)
        self.assertIn("layout:    text", updated)
        self.assertIn("section :   基础", updated)
        self.assertIn("image-fit:   contain", updated)
        self.assertIn("chapter: 新的归属", updated)

    def test_set_fields_rejects_invalid_directive_key_and_reserved_id_on_implicit_page(self):
        problems = []
        try:
            golajah_slide_agent.edit_deck(
                self.source,
                [{
                    "op": "set_fields",
                    "slide_id": "intro",
                    "fields": {"config": {"bad key": "value"}},
                }],
            )
        except golajah_slide_agent.AgentToolError as error:
            if error.code != "INVALID_CONFIG":
                problems.append(f"invalid key returned {error.code}")
        else:
            problems.append("invalid directive key was accepted")

        implicit_source = """<!-- slide
type: content
layout: text
-->
# 隐式 ID 页面

正文。
"""
        self.source.write_text(implicit_source, encoding="utf-8")
        try:
            golajah_slide_agent.edit_deck(
                self.source,
                [{
                    "op": "set_fields",
                    "slide_id": "p1",
                    "fields": {"config": {"id": "p1"}},
                }],
            )
        except golajah_slide_agent.AgentToolError as error:
            if error.code != "RESERVED_SLIDE_ID":
                problems.append(f"reserved implicit ID returned {error.code}")
        else:
            problems.append("implicit page accepted reserved explicit id=p1")
        self.assertEqual(problems, [])

    def test_compact_directive_addition_stays_inside_slide_comment(self):
        source = """<!-- slide id: compact -->
# 紧凑 Directive

正文。
"""
        self.source.write_text(source, encoding="utf-8")
        golajah_slide_agent.edit_deck(
            self.source,
            [{
                "op": "set_fields",
                "slide_id": "compact",
                "fields": {"config": {"chapter": "新增归属"}},
            }],
            write=True,
            expected_sha256=sha256_text(source),
        )
        updated = self.source.read_text(encoding="utf-8")
        directive = re.search(r"(?s)<!--\s*slide.*?-->", updated)
        self.assertIsNotNone(directive, updated)
        self.assertIn("id: compact", directive.group(0))
        self.assertIn("chapter: 新增归属", directive.group(0))
        self.assertNotIn("chapter: 新增归属", updated[:directive.start()] + updated[directive.end():])
        reparsed = golajah_slide_agent.get_slide(self.source, "compact")
        self.assertEqual(reparsed["slide"]["config"]["chapter"], "新增归属")

    def test_compact_directive_deletion_preserves_comment_and_stable_id(self):
        source = """<!-- slide id: compact
chapter: 即将删除 -->
# 删除单个字段

正文。
"""
        self.source.write_text(source, encoding="utf-8")
        golajah_slide_agent.edit_deck(
            self.source,
            [{
                "op": "set_fields",
                "slide_id": "compact",
                "fields": {"config": {"chapter": None}},
            }],
            write=True,
            expected_sha256=sha256_text(source),
        )
        updated = self.source.read_text(encoding="utf-8")
        directive = re.search(r"(?s)<!--\s*slide.*?-->", updated)
        self.assertIsNotNone(directive, updated)
        self.assertIn("id: compact", directive.group(0))
        self.assertNotIn("chapter:", directive.group(0))
        reparsed = golajah_slide_agent.get_slide(self.source, "compact")
        self.assertEqual(reparsed["slide"]["id"], "compact")
        self.assertNotIn("chapter", reparsed["slide"]["config"])

    def test_markdown_layout_change_reconciles_layout_specific_sidecar_regions(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        preserved_typography = {"lineHeight": 1.45, "bodyScale": 0.95}
        preserved_animation = {"mode": "sequence", "stepMs": 180}
        preserved_content = {"x": 120, "y": 180, "width": 900, "height": 650}
        stale_visual = {"x": 1110, "y": 180, "width": 690, "height": 650}
        stale_copy = {"x": 120, "y": 180, "width": 900, "height": 650}
        preserved_regions = {
            "content": preserved_content,
            "visual": stale_visual,
            "copy": stale_copy,
        }
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {
                "intro": {
                    "layout": "media",
                    "typography": preserved_typography,
                    "animation": preserved_animation,
                    "regions": preserved_regions,
                },
                "details": {"layout": "text"},
            },
        }
        layout_source = json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        golajah_slide_agent.edit_deck(
            self.source,
            [{
                "op": "set_fields",
                "slide_id": "intro",
                "fields": {"config": {"layout": "gallery"}},
            }],
            write=True,
            expected_sha256=before_sha256,
            expected_layout_sha256=sha256_text(layout_source),
        )
        self.assertEqual(golajah_slide_agent.get_slide(self.source, "intro")["slide"]["layout"], "gallery")
        updated_layout = json.loads(layout_path.read_text(encoding="utf-8"))
        intro_override = updated_layout["slides"]["intro"]
        self.assertNotIn("layout", intro_override)
        self.assertEqual(intro_override["typography"], preserved_typography)
        self.assertEqual(intro_override["animation"], preserved_animation)
        self.assertEqual(intro_override["regions"], {"content": preserved_content})
        self.assertEqual(updated_layout["slides"]["details"], {"layout": "text"})

    def test_replace_slide_rejects_implicit_page_and_reserved_explicit_id(self):
        source = """<!-- slide
type: content
layout: text
-->
# 隐式页面

正文。
"""
        self.source.write_text(source, encoding="utf-8")
        replacement = """<!-- slide
id: p1
type: content
layout: text
-->
# 不安全替换

不能将隐式页固化为 reserved ID。
"""
        with self.assertRaises(golajah_slide_agent.AgentToolError) as rejected:
            golajah_slide_agent.edit_deck(
                self.source,
                [{
                    "op": "replace_slide",
                    "slide_id": "p1",
                    "markdown": replacement,
                }],
                write=True,
                expected_sha256=sha256_text(source),
            )
        self.assertIn(rejected.exception.code, {"EXPLICIT_ID_REQUIRED", "RESERVED_SLIDE_ID"})
        self.assertEqual(self.source.read_text(encoding="utf-8"), source)

    def test_append_insert_preserves_unaffected_implicit_legacy_layout_key(self):
        source = """<!-- slide
type: content
layout: text
-->
# 保持第一页

末尾插入不会改变这一页的页码。
"""
        self.source.write_text(source, encoding="utf-8")
        before_sha256 = sha256_text(source)
        layout_path = self.source.with_suffix(".layout.json")
        legacy_override = {
            "layout": "split",
            "typography": {"lineHeight": 1.5},
            "animation": {"mode": "auto"},
        }
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {"P1": legacy_override},
        }
        layout_source = json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n"
        layout_path.write_text(layout_source, encoding="utf-8")
        inserted = """<!-- slide
id: appended
type: content
layout: text
-->
# 末尾新增页

新页面使用稳定 ID。
"""
        result = golajah_slide_agent.edit_deck(
            self.source,
            [{"op": "insert_slide", "markdown": inserted}],
            write=True,
            expected_sha256=before_sha256,
            expected_layout_sha256=sha256_text(layout_source),
        )
        self.assertEqual([slide["id"] for slide in golajah_slide_agent.inspect_deck(self.source)["slides"]], ["p1", "appended"])
        updated_layout = json.loads(layout_path.read_text(encoding="utf-8"))
        self.assertEqual(updated_layout["slides"], {"P1": legacy_override})
        self.assertEqual(updated_layout["sourceHash"], result["afterSha256"])
        self.assertEqual(result["layout"]["migratedLegacyKeys"], [])

    def test_cli_domain_build_failures_set_top_level_ok_false(self):
        warning_source = self.root / "strict-warning.md"
        warning_source.write_text("""<!-- slide
id: warning
type: content
layout: unsupported-layout
-->
# Strict Warning

正文。
""", encoding="utf-8")
        cases = (
            ("audit", ["audit", str(warning_source)]),
            ("build", ["build", str(warning_source), "--output", str(self.root / "strict-warning.html")]),
        )
        problems = []
        for label, arguments in cases:
            completed = subprocess.run(
                [sys.executable, str(AGENT_CLI), *arguments],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                check=False,
            )
            if completed.returncode != 1:
                problems.append(f"{label} domain failure exited {completed.returncode}")
                continue
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                problems.append(f"{label} did not emit a JSON result")
                continue
            if payload.get("ok") is not False:
                problems.append(f"{label} top-level ok was not false")
            if payload.get("result", {}).get("ok") is not False:
                problems.append(f"{label} domain result did not fail")
            if not payload.get("result", {}).get("report", {}).get("warnings"):
                problems.append(f"{label} did not retain strict warnings")
        self.assertEqual(problems, [])

    def test_cli_and_mcp_classify_builder_exit_two_as_operation_error(self):
        blocked_output = self.root / "blocked.html"
        blocked_output.mkdir()
        completed = subprocess.run(
            [
                sys.executable,
                str(AGENT_CLI),
                "build",
                str(self.source),
                "--output",
                str(blocked_output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        cli_payload = json.loads(completed.stdout)
        self.assertFalse(cli_payload["ok"])
        self.assertEqual(cli_payload["error"]["code"], "BUILD_OPERATION_FAILED")
        self.assertEqual(cli_payload["error"]["details"]["buildExitCode"], 2)

        server = self.ready_mcp()
        response = server.handle({
            "jsonrpc": "2.0",
            "id": "build-error",
            "method": "tools/call",
            "params": {
                "name": "golajah_deck_build",
                "arguments": {"source": "slides.md", "output": "blocked.html"},
            },
        })
        self.assertTrue(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["error"]["code"], "BUILD_OPERATION_FAILED")
        self.assertEqual(structured["error"]["details"]["buildExitCode"], 2)

    def test_mcp_build_annotation_is_destructive(self):
        build_tool = next(tool for tool in golajah_slide_agent.mcp_tools() if tool["name"] == "golajah_deck_build")
        self.assertTrue(build_tool["annotations"]["destructiveHint"])

    def test_mcp_requires_valid_initialize_handshake_before_tools(self):
        server = golajah_slide_agent.StdioMCPServer(self.root)
        initialize_notification = server.handle({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "notification", "version": "1.0"},
            },
        })
        self.assertIsNone(initialize_notification)

        for request_id, method, params in (
            (201, "tools/list", {}),
            (202, "tools/call", {"name": "golajah_deck_inspect", "arguments": {"source": "slides.md"}}),
        ):
            blocked = server.handle({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            })
            self.assertEqual(blocked["error"]["code"], -32002)

        invalid_params = (
            {},
            {"protocolVersion": 20251125, "capabilities": {}, "clientInfo": {"name": "x", "version": "1"}},
            {"protocolVersion": "2025-11-25", "capabilities": [], "clientInfo": {"name": "x", "version": "1"}},
            {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "x"}},
        )
        for index, params in enumerate(invalid_params, 1):
            rejected = server.handle({
                "jsonrpc": "2.0",
                "id": 210 + index,
                "method": "initialize",
                "params": params,
            })
            self.assertEqual(rejected["error"]["code"], -32602)

        initialized = server.handle({
            "jsonrpc": "2.0",
            "id": 220,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1.0"},
            },
        })
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
        before_ready = server.handle({"jsonrpc": "2.0", "id": 221, "method": "tools/list", "params": {}})
        self.assertEqual(before_ready["error"]["code"], -32002)
        self.assertIsNone(server.handle({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }))
        ready = server.handle({"jsonrpc": "2.0", "id": 222, "method": "tools/list", "params": {}})
        self.assertEqual(len(ready["result"]["tools"]), 6)

    def test_mcp_rejects_batch_for_current_protocol_versions(self):
        for protocol_version in ("2025-06-18", "2025-11-25"):
            with self.subTest(protocol_version=protocol_version):
                messages = [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": protocol_version,
                            "capabilities": {},
                            "clientInfo": {"name": "batch-test", "version": "1.0"},
                        },
                    },
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    [
                        {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
                        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
                    ],
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
                ]
                completed = subprocess.run(
                    [sys.executable, str(AGENT_CLI), "mcp", "--root", str(self.root)],
                    cwd=ROOT,
                    input="".join(json.dumps(message) + "\n" for message in messages),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=20,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
                self.assertEqual(len(responses), 3)
                self.assertEqual(responses[0]["result"]["protocolVersion"], protocol_version)
                self.assertIsNone(responses[1]["id"])
                self.assertEqual(responses[1]["error"]["code"], -32600)
                self.assertEqual(responses[2]["id"], 4)
                self.assertEqual(len(responses[2]["result"]["tools"]), 6)

    def test_mcp_unknown_tool_returns_jsonrpc_invalid_params(self):
        response = self.ready_mcp().handle({
            "jsonrpc": "2.0",
            "id": 301,
            "method": "tools/call",
            "params": {
                "name": "golajah_unknown_tool",
                "arguments": {"source": "slides.md"},
            },
        })
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertNotIn("result", response)

    def test_mcp_unexpected_tool_exception_returns_jsonrpc_internal_error(self):
        server = self.ready_mcp()
        with mock.patch.object(server, "call_tool", side_effect=RuntimeError("must not leak")):
            response = server.handle({
                "jsonrpc": "2.0",
                "id": 302,
                "method": "tools/call",
                "params": {
                    "name": "golajah_deck_inspect",
                    "arguments": {"source": "slides.md"},
                },
            })
        self.assertEqual(response["error"]["code"], -32603)
        self.assertNotIn("result", response)
        self.assertNotIn("must not leak", json.dumps(response))

    def test_mcp_runtime_rejects_schema_extras_and_out_of_range_limit(self):
        server = self.ready_mcp()
        cases = (
            (
                "top-level-extra",
                "golajah_deck_inspect",
                {"source": "slides.md", "unexpected": True},
            ),
            (
                "limit-too-small",
                "golajah_deck_search",
                {"source": "slides.md", "query": "Agent", "limit": 0},
            ),
            (
                "limit-too-large",
                "golajah_deck_search",
                {"source": "slides.md", "query": "Agent", "limit": 101},
            ),
            (
                "operation-extra",
                "golajah_deck_edit",
                {
                    "source": "slides.md",
                    "operations": [{
                        "op": "set_fields",
                        "slide_id": "intro",
                        "fields": {"title": "不应执行"},
                        "unexpected": "field",
                    }],
                },
            ),
        )
        problems = []
        for index, (label, name, arguments) in enumerate(cases, 1):
            response = server.handle({
                "jsonrpc": "2.0",
                "id": 400 + index,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            result = response.get("result", {})
            if result.get("isError") is not True:
                problems.append(f"{label} was not returned as a tool error")
                continue
            error = result.get("structuredContent", {}).get("error", {})
            if error.get("code") != "INVALID_ARGUMENTS":
                problems.append(f"{label} returned {error.get('code')!r}")
        self.assertEqual(problems, [])

    def test_mcp_build_rejects_nested_outside_root_references_in_local_svg(self):
        assets = self.root / "assets"
        assets.mkdir()
        svg_path = assets / "unsafe.svg"
        outside = self.root.parent / f"{self.root.name}-nested-svg.png"
        outside.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        ))
        self.addCleanup(outside.unlink, missing_ok=True)
        self.source.write_text("""<!-- slide
id: unsafe-svg
type: content
layout: media
-->
# SVG 嵌套资源边界

![不可信 SVG](assets/unsafe.svg)
""", encoding="utf-8")
        server = golajah_slide_agent.StdioMCPServer(self.root)
        cases = {
            "file-uri": f'<image href="{outside.as_uri()}" width="1" height="1"/>',
            "css-parent-escape": (
                f'<style>.leak {{ fill: url("../../{outside.name}"); }}</style>'
                '<rect class="leak" width="10" height="10"/>'
            ),
        }
        problems = []
        for label, nested_reference in cases.items():
            with self.subTest(label=label):
                output = self.root / f"unsafe-svg-{label}.html"
                svg_path.write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                    f"{nested_reference}</svg>",
                    encoding="utf-8",
                )
                error = None
                try:
                    server.call_tool("golajah_deck_build", {
                        "source": "slides.md",
                        "output": output.name,
                        "strict": True,
                    })
                except golajah_slide_agent.AgentToolError as caught:
                    error = caught
                if error is None:
                    problems.append(f"{label} nested SVG reference was accepted")
                if output.exists() or output.with_suffix(".build.json").exists():
                    problems.append(f"{label} wrote output before rejecting the SVG")
        self.assertEqual(problems, [])

    def test_mcp_build_rejects_percent_encoded_static_manifest_escape(self):
        outside = self.root.parent / f"{self.root.name}-encoded.png"
        outside.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        ))
        self.addCleanup(outside.unlink, missing_ok=True)
        self.source.write_text(f"""<!-- slide
id: encoded-escape
type: content
layout: media
-->
# 编码路径不能越界

![不可信编码路径](assets/%2e%2e/%2e%2e/{outside.name})
""", encoding="utf-8")
        output = self.root / "encoded-escape.html"
        server = golajah_slide_agent.StdioMCPServer(self.root)
        with self.assertRaises(golajah_slide_agent.AgentToolError) as rejected:
            server.call_tool("golajah_deck_build", {
                "source": "slides.md",
                "output": output.name,
                "strict": True,
            })
        self.assertEqual(rejected.exception.code, "PATH_OUTSIDE_ROOT")
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".build.json").exists())

    def test_build_and_audit_compile_the_validated_markdown_snapshot(self):
        original_source = DECK_SOURCE
        concurrent_source = DECK_SOURCE.replace("# 稳定开场", "# 竞态改写")
        original_validate = golajah_slide_agent._validate_build_asset_boundary
        cases = ("build", "audit")
        problems = []
        for label in cases:
            with self.subTest(label=label):
                self.source.write_text(original_source, encoding="utf-8")
                mutated = False

                def validate_then_mutate(state, asset_root):
                    nonlocal mutated
                    original_validate(state, asset_root)
                    self.source.write_text(concurrent_source, encoding="utf-8")
                    mutated = True

                with mock.patch.object(
                    golajah_slide_agent,
                    "_validate_build_asset_boundary",
                    side_effect=validate_then_mutate,
                ):
                    if label == "build":
                        output = self.root / "snapshot.html"
                        result = golajah_slide_agent.build_deck(self.source, output, strict=True)
                        rendered = output.read_text(encoding="utf-8")
                        if "稳定开场" not in rendered or "竞态改写" in rendered:
                            problems.append("build re-read the concurrently changed Markdown")
                    else:
                        result = golajah_slide_agent.audit_deck(self.source, strict=True)
                expected_hash = sha256_text(original_source)
                if not mutated:
                    problems.append(f"{label} did not inject the validation/build race")
                if result["source"]["sha256"] != expected_hash:
                    problems.append(f"{label} returned a hash from another source snapshot")
                if result["report"].get("authoring", {}).get("sourceSha256") != expected_hash:
                    problems.append(f"{label} compiled a different Markdown snapshot")
        self.assertEqual(problems, [])

    def test_automatic_layout_realpath_collision_is_rejected(self):
        report_target = self.root / "export.build.json"
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": sha256_text(DECK_SOURCE),
            "slides": {},
        }
        original = json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n"
        report_target.write_text(original, encoding="utf-8")
        self.source.with_suffix(".layout.json").symlink_to(report_target)

        with self.assertRaises(golajah_slide_agent.AgentToolError) as rejected:
            golajah_slide_agent.build_deck(self.source, self.root / "export.html", strict=True)

        self.assertEqual(rejected.exception.code, "INVALID_OUTPUT")
        self.assertEqual(report_target.read_text(encoding="utf-8"), original)
        self.assertFalse((self.root / "export.html").exists())

    def test_rooted_build_rejects_media_swapped_after_validation(self):
        media = self.root / "clip.mp4"
        outside = self.root.parent / f"{self.root.name}-outside.mp4"
        media.write_bytes(b"inside-video")
        outside.write_bytes(b"outside-secret-video")
        self.addCleanup(outside.unlink, missing_ok=True)
        self.source.write_text("""<!-- slide
id: race-video
type: content
layout: media
-->
# 媒体竞态

![演示](clip.mp4)
""", encoding="utf-8")
        original_validate = golajah_slide_agent._validate_build_asset_boundary
        swapped = False

        def validate_then_swap(state, asset_root):
            nonlocal swapped
            original_validate(state, asset_root)
            media.unlink()
            media.symlink_to(outside)
            swapped = True

        output = self.root / "race-video.html"
        with (
            mock.patch.object(
                golajah_slide_agent,
                "_validate_build_asset_boundary",
                side_effect=validate_then_swap,
            ),
            self.assertRaises(golajah_slide_agent.AgentToolError) as rejected,
        ):
            golajah_slide_agent.build_deck(
                self.source,
                output,
                strict=True,
                asset_root=self.root,
            )
        self.assertTrue(swapped)
        self.assertEqual(rejected.exception.code, "PATH_OUTSIDE_ROOT")
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".build.json").exists())

    def test_rooted_build_rejects_layout_swapped_after_discovery(self):
        layout = self.source.with_suffix(".layout.json")
        outside = self.root.parent / f"{self.root.name}-outside.layout.json"
        base = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": sha256_text(DECK_SOURCE),
            "slides": {},
        }
        layout.write_text(json.dumps(base), encoding="utf-8")
        outside.write_text(json.dumps({
            **base,
            "slides": {"intro": {"layout": "media"}},
        }), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        original_resolve = golajah_slide_agent._resolved_build_layout
        swapped = False

        def resolve_then_swap(state, explicit, asset_root):
            nonlocal swapped
            resolved = original_resolve(state, explicit, asset_root)
            layout.unlink()
            layout.symlink_to(outside)
            swapped = True
            return resolved

        output = self.root / "race-layout.html"
        with (
            mock.patch.object(
                golajah_slide_agent,
                "_resolved_build_layout",
                side_effect=resolve_then_swap,
            ),
            self.assertRaises(golajah_slide_agent.AgentToolError) as rejected,
        ):
            golajah_slide_agent.build_deck(
                self.source,
                output,
                strict=True,
                asset_root=self.root,
            )
        self.assertTrue(swapped)
        self.assertEqual(rejected.exception.code, "PATH_OUTSIDE_ROOT")
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".build.json").exists())

    def test_edit_rejects_source_and_layout_races_after_staging_without_overwrite(self):
        operation = {
            "op": "set_fields",
            "slide_id": "intro",
            "fields": {"title": "事务内更新"},
        }
        layout_path = self.source.with_suffix(".layout.json")
        original_stage_text = golajah_slide_agent._stage_text
        original_layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": sha256_text(DECK_SOURCE),
            "slides": {"intro": {"layout": "text"}},
        }
        original_layout = json.dumps(original_layout_payload, ensure_ascii=False, indent=2) + "\n"
        concurrent_source = DECK_SOURCE + "\n<!-- concurrent source writer -->\n"
        concurrent_created_layout = '{"concurrent": "created"}\n'
        concurrent_modified_layout = json.dumps(
            {**original_layout_payload, "concurrent": "modified"},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        cases = (
            ("source-modified", None, self.source, self.source, concurrent_source, None),
            ("layout-created", None, self.source, layout_path, concurrent_created_layout, None),
            (
                "layout-modified",
                original_layout,
                layout_path,
                layout_path,
                concurrent_modified_layout,
                sha256_text(original_layout),
            ),
        )
        problems = []
        for label, initial_layout, stage_trigger, race_target, concurrent_text, expected_layout_hash in cases:
            with self.subTest(label=label):
                self.source.write_text(DECK_SOURCE, encoding="utf-8")
                if initial_layout is None:
                    layout_path.unlink(missing_ok=True)
                else:
                    layout_path.write_text(initial_layout, encoding="utf-8")
                raced = False

                def stage_then_race(path, source):
                    nonlocal raced
                    staged = original_stage_text(path, source)
                    if not raced and Path(path).resolve() == stage_trigger.resolve():
                        race_target.write_text(concurrent_text, encoding="utf-8")
                        raced = True
                    return staged

                error = None
                with mock.patch.object(golajah_slide_agent, "_stage_text", side_effect=stage_then_race):
                    try:
                        golajah_slide_agent.edit_deck(
                            self.source,
                            [operation],
                            write=True,
                            expected_sha256=sha256_text(DECK_SOURCE),
                            expected_layout_sha256=expected_layout_hash,
                        )
                    except golajah_slide_agent.AgentToolError as caught:
                        error = caught
                if not raced:
                    problems.append(f"{label} did not inject its staged-write race")
                if error is None:
                    problems.append(f"{label} race was accepted")
                expected_source = concurrent_source if race_target == self.source else DECK_SOURCE
                if self.source.read_text(encoding="utf-8") != expected_source:
                    problems.append(f"{label} overwrote source contents")
                if race_target == layout_path:
                    if not layout_path.exists() or layout_path.read_text(encoding="utf-8") != concurrent_text:
                        problems.append(f"{label} overwrote concurrent layout contents")
        self.assertEqual(problems, [])

    def test_edit_rollback_does_not_overwrite_external_append_after_source_replace(self):
        operation = {
            "op": "set_fields",
            "slide_id": "intro",
            "fields": {"title": "已完成原子替换"},
        }
        external_append = b"\n<!-- external append after replace -->\n"
        original_replace = golajah_slide_agent.os.replace
        appended = False

        def replace_then_append(source, destination):
            nonlocal appended
            original_replace(source, destination)
            if not appended and Path(destination).resolve() == self.source.resolve():
                with self.source.open("ab") as handle:
                    handle.write(external_append)
                appended = True

        with mock.patch.object(golajah_slide_agent.os, "replace", side_effect=replace_then_append):
            with self.assertRaises(golajah_slide_agent.AgentToolError) as failed:
                golajah_slide_agent.edit_deck(
                    self.source,
                    [operation],
                    write=True,
                    expected_sha256=sha256_text(DECK_SOURCE),
                )
        final_source = self.source.read_bytes()
        self.assertTrue(appended)
        self.assertEqual(failed.exception.code, "WRITE_FAILED")
        self.assertIn(external_append, final_source)
        self.assertIn("已完成原子替换".encode("utf-8"), final_source)
        self.assertIn("skipped because another process changed", json.dumps(failed.exception.details))

    def test_cli_strict_defaults_no_strict_override_and_json_parse_errors(self):
        cases = (
            ("audit-default", ["audit", str(self.source)], True),
            ("audit-disabled", ["audit", str(self.source), "--no-strict"], False),
            (
                "build-default",
                ["build", str(self.source), "--output", str(self.root / "strict-default.html")],
                True,
            ),
            (
                "build-disabled",
                ["build", str(self.source), "--output", str(self.root / "strict-disabled.html"), "--no-strict"],
                False,
            ),
        )
        problems = []
        for label, arguments, expected_strict in cases:
            completed = subprocess.run(
                [sys.executable, str(AGENT_CLI), *arguments],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                check=False,
            )
            if completed.returncode != 0:
                problems.append(f"{label} exited {completed.returncode}: {completed.stderr}")
                continue
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                problems.append(f"{label} did not emit one JSON result")
                continue
            actual_strict = payload.get("result", {}).get("strict")
            if actual_strict is not expected_strict:
                problems.append(f"{label} strict={actual_strict!r}")
        self.assertEqual(problems, [])

        invalid = subprocess.run(
            [sys.executable, str(AGENT_CLI), "audit"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(invalid.stderr, "")
        error_lines = [line for line in invalid.stdout.splitlines() if line.strip()]
        self.assertEqual(len(error_lines), 1, invalid.stdout)
        error = json.loads(error_lines[0])
        self.assertFalse(error["ok"])
        self.assertEqual(error["error"]["code"], "INVALID_ARGUMENTS")
        self.assertNotIn("Traceback", invalid.stdout + invalid.stderr)

    def test_cli_rejects_conflicting_search_and_get_selectors_on_stdout(self):
        cases = {
            "search": ["search", str(self.source), "Agent", "--query", "other"],
            "get-page": ["get", str(self.source), "intro", "--page", "1"],
            "get-id": ["get", str(self.source), "intro", "--slide-id", "details"],
        }
        problems = []
        for label, arguments in cases.items():
            completed = subprocess.run(
                [sys.executable, str(AGENT_CLI), *arguments],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                check=False,
            )
            if completed.returncode != 2:
                problems.append(f"{label} exited {completed.returncode}")
                continue
            if completed.stderr:
                problems.append(f"{label} wrote its JSON error to stderr")
                continue
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                problems.append(f"{label} did not emit one stdout JSON document")
                continue
            if payload.get("error", {}).get("code") != "INVALID_ARGUMENTS":
                problems.append(f"{label} returned {payload.get('error', {}).get('code')!r}")
        self.assertEqual(problems, [])

    def test_path_policy_rejects_parent_and_symlink_escape(self):
        policy = golajah_slide_agent.PathPolicy(self.root)
        outside = self.root.parent / f"{self.root.name}-outside.md"
        outside.write_text(DECK_SOURCE, encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaises(golajah_slide_agent.AgentToolError) as parent_escape:
            policy.resolve(Path("..") / outside.name)
        self.assertEqual(parent_escape.exception.code, "PATH_OUTSIDE_ROOT")

        link = self.root / "outside-link.md"
        link.symlink_to(outside)
        with self.assertRaises(golajah_slide_agent.AgentToolError) as symlink_escape:
            policy.resolve(link)
        self.assertEqual(symlink_escape.exception.code, "PATH_OUTSIDE_ROOT")

    def test_rooted_read_services_reject_source_and_layout_symlink_escapes(self):
        outside_source = self.root.parent / f"{self.root.name}-read-outside.md"
        outside_source.write_text(DECK_SOURCE, encoding="utf-8")
        self.addCleanup(outside_source.unlink, missing_ok=True)
        source_alias = self.root / "source-alias.md"
        source_alias.symlink_to(outside_source)

        for read in (
            lambda: golajah_slide_agent.inspect_deck(source_alias, asset_root=self.root),
            lambda: golajah_slide_agent.search_deck(source_alias, "Agent", asset_root=self.root),
            lambda: golajah_slide_agent.get_slide(source_alias, "intro", asset_root=self.root),
        ):
            with self.assertRaises(golajah_slide_agent.AgentToolError) as source_escape:
                read()
            self.assertEqual(source_escape.exception.code, "PATH_OUTSIDE_ROOT")

        outside_layout = self.root.parent / f"{self.root.name}-read-outside.layout.json"
        outside_layout.write_text("{}\n", encoding="utf-8")
        self.addCleanup(outside_layout.unlink, missing_ok=True)
        self.source.with_suffix(".layout.json").symlink_to(outside_layout)
        with self.assertRaises(golajah_slide_agent.AgentToolError) as layout_escape:
            golajah_slide_agent.inspect_deck(self.source, asset_root=self.root)
        self.assertEqual(layout_escape.exception.code, "PATH_OUTSIDE_ROOT")

    def test_mutation_selectors_never_fall_back_to_page_numbers(self):
        original = self.source.read_bytes()
        inserted = """<!-- slide
id: inserted
type: content
layout: text
-->
# 不应插入

正文。
"""
        cases = (
            {"op": "set_fields", "slide_id": "1", "fields": {"title": "不能按页码改"}},
            {"op": "append_content", "slide_id": "#1", "markdown": "不能按页码追加"},
            {"op": "insert_slide", "after_slide_id": "1", "markdown": inserted},
        )
        errors = []
        for operation in cases:
            try:
                golajah_slide_agent.edit_deck(self.source, [operation])
            except golajah_slide_agent.AgentToolError as error:
                errors.append(error.code)
            else:
                errors.append("accepted")
        self.assertEqual(errors, ["SLIDE_NOT_FOUND", "INVALID_ARGUMENTS", "SLIDE_NOT_FOUND"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_service_cli_and_mcp_share_strict_nested_operation_validation(self):
        malformed = (
            {"op": "append_content", "slide_id": "intro", "markdown": "x", "before_slide_id": "details"},
            {"op": "set_fields", "slide_id": "intro", "fields": {"titel": "拼错字段"}},
            {"op": "set_fields", "slide_id": "intro", "fields": {"title": 42}},
            {"op": "set_fields", "slide_id": "intro", "fields": {"subtitle": False}},
            {"op": "set_fields", "slide_id": "intro", "fields": {"config": []}},
            {"op": "replace_slide", "slide_id": 1, "markdown": "# 类型错误"},
            {"op": "append_content", "slide_id": "intro", "markdown": True},
        )
        for operation in malformed:
            with self.subTest(operation=operation):
                with self.assertRaises(golajah_slide_agent.AgentToolError) as rejected:
                    golajah_slide_agent.edit_deck(self.source, [operation])
                self.assertEqual(rejected.exception.code, "INVALID_ARGUMENTS")

        representative = malformed[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(AGENT_CLI),
                "edit",
                str(self.source),
                "--operations-json",
                json.dumps([representative], ensure_ascii=False),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "INVALID_ARGUMENTS")

        server = self.ready_mcp()
        with self.assertRaises(golajah_slide_agent.AgentToolError) as mcp_rejected:
            server.call_tool("golajah_deck_edit", {
                "source": "slides.md",
                "operations": [representative],
            })
        self.assertEqual(mcp_rejected.exception.code, "INVALID_ARGUMENTS")

        edit_tool = next(tool for tool in golajah_slide_agent.mcp_tools() if tool["name"] == "golajah_deck_edit")
        variants = edit_tool["inputSchema"]["properties"]["operations"]["items"]["oneOf"]
        set_fields_schema = next(item for item in variants if item["properties"]["op"].get("const") == "set_fields")
        self.assertFalse(set_fields_schema["properties"]["fields"]["additionalProperties"])

    def test_layout_snapshot_hashes_the_same_raw_bytes_and_preserves_crlf_for_rollback(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        layout_path = self.source.with_suffix(".layout.json")
        layout_payload = {
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {"intro": {"layout": "text"}},
        }
        layout_bytes = (json.dumps(layout_payload, ensure_ascii=False, indent=2) + "\n").replace(
            "\n", "\r\n"
        ).encode("utf-8")
        layout_path.write_bytes(layout_bytes)
        layout_sha256 = hashlib.sha256(layout_bytes).hexdigest()
        operation = {"op": "set_fields", "slide_id": "intro", "fields": {"title": "原始字节快照"}}

        with mock.patch.object(
            golajah_slide_agent.build_slides,
            "sha256_file",
            side_effect=AssertionError("layout edit must not perform a second hash read"),
        ):
            preview = golajah_slide_agent.edit_deck(self.source, [operation])
        self.assertEqual(preview["layout"]["beforeSha256"], layout_sha256)
        self.assertEqual(layout_path.read_bytes(), layout_bytes)

        destinations = []
        original_replace = golajah_slide_agent.os.replace

        def fail_layout_replace(source, destination):
            resolved = Path(destination).resolve()
            destinations.append(resolved)
            if resolved == layout_path.resolve():
                raise OSError("injected layout replace failure")
            return original_replace(source, destination)

        with mock.patch.object(golajah_slide_agent.os, "replace", side_effect=fail_layout_replace):
            with self.assertRaises(golajah_slide_agent.AgentToolError) as failed:
                golajah_slide_agent.edit_deck(
                    self.source,
                    [operation],
                    write=True,
                    expected_sha256=before_sha256,
                    expected_layout_sha256=layout_sha256,
                )
        self.assertEqual(failed.exception.code, "WRITE_FAILED")
        self.assertGreaterEqual(len(destinations), 2)
        self.assertEqual(destinations[:2], [self.source.resolve(), layout_path.resolve()])
        self.assertEqual(self.source.read_bytes(), DECK_SOURCE.encode("utf-8"))
        self.assertEqual(layout_path.read_bytes(), layout_bytes)
        self.assertIn("restored original contents", failed.exception.details["recovery"]["source"])

    def test_mcp_edit_uses_canonical_automatic_layout_target_without_replacing_alias(self):
        before_sha256 = sha256_text(DECK_SOURCE)
        canonical = self.root / "canonical.layout.json"
        alias = self.source.with_suffix(".layout.json")
        layout_source = json.dumps({
            "schemaVersion": "1.0",
            "source": "slides.md",
            "sourceHash": before_sha256,
            "slides": {"intro": {"layout": "text"}},
        }, ensure_ascii=False, indent=2) + "\n"
        canonical.write_text(layout_source, encoding="utf-8")
        alias.symlink_to(canonical)

        result = self.ready_mcp().call_tool("golajah_deck_edit", {
            "source": "slides.md",
            "operations": [{
                "op": "set_fields",
                "slide_id": "intro",
                "fields": {"title": "通过 canonical sidecar 写入"},
            }],
            "write": True,
            "expected_sha256": before_sha256,
            "expected_layout_sha256": sha256_text(layout_source),
        })
        self.assertTrue(result["written"])
        self.assertEqual(Path(result["layout"]["path"]), canonical.resolve())
        self.assertTrue(alias.is_symlink())
        self.assertEqual(json.loads(canonical.read_text(encoding="utf-8"))["sourceHash"], result["afterSha256"])

    def test_cli_stdout_is_one_machine_readable_json_document(self):
        completed = subprocess.run(
            [sys.executable, str(AGENT_CLI), "inspect", str(self.source)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["slides"][0]["id"], "intro")
        self.assertNotIn("Built ", completed.stdout)

    def test_mcp_stdio_initialize_list_call_and_path_boundary(self):
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "contract-test", "version": "1.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "golajah_deck_inspect", "arguments": {"source": "slides.md"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "golajah_deck_inspect", "arguments": {"source": "../outside.md"}},
            },
        ]
        completed = subprocess.run(
            [sys.executable, str(AGENT_CLI), "mcp", "--root", str(self.root)],
            cwd=ROOT,
            input="".join(json.dumps(request, ensure_ascii=False) + "\n" for request in requests),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        by_id = {response.get("id"): response for response in responses}
        self.assertEqual(set(by_id), {1, 2, 3, 4, 5})
        self.assertIn("serverInfo", by_id[1]["result"])
        self.assertEqual(by_id[2]["result"], {})

        tools = by_id[3]["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(names, {
            "golajah_deck_inspect",
            "golajah_deck_search",
            "golajah_slide_get",
            "golajah_deck_audit",
            "golajah_deck_edit",
            "golajah_deck_build",
        })
        self.assertFalse(any(token in name for name in names for token in ("delete", "shell", "git", "publish")))

        content = by_id[4]["result"]["content"]
        self.assertEqual(content[0]["type"], "text")
        inspected = json.loads(content[0]["text"])
        self.assertEqual(inspected["slides"][0]["id"], "intro")
        self.assertTrue(by_id[5]["result"]["isError"])
        error = json.loads(by_id[5]["result"]["content"][0]["text"])
        self.assertEqual(error["error"]["code"], "PATH_OUTSIDE_ROOT")


if __name__ == "__main__":
    unittest.main()
