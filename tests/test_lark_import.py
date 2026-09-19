import contextlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import build_slides
from src.importers.lark import (
    LarkClient, LarkImportError, embed_media, fetch_document,
    import_document, normalize_markdown, resolve_document,
)


class LarkImportTests(unittest.TestCase):
    def normalize(self, text):
        return normalize_markdown(text, "文档标题", lambda token, kind: "assets/image.png")

    def test_character_pagination_keeps_code_and_chinese_intact(self):
        client = Mock()
        client.run.side_effect = [
            {"title": "测试", "markdown": "# 页面\n```yaml\ngolajah", "has_more": True, "next_offset": 18},
            {"markdown": "slide: slide\nid: p1\n```", "has_more": False},
        ]
        title, text, token = fetch_document("doc123", client)
        self.assertIn("golajahslide: slide", text)
        self.assertEqual((title, token), ("测试", "doc123"))
        self.assertIn("18", client.run.call_args.args)

    def test_incomplete_or_looping_pagination_fails(self):
        for cursor in (None, 0, -1, "bad"):
            client = Mock()
            client.run.return_value = {"markdown": "abc", "has_more": True, "next_offset": cursor}
            with self.subTest(cursor=cursor), self.assertRaises(LarkImportError):
                fetch_document("doc123", client)

    def test_wiki_resolves_docx_and_rejects_other_types(self):
        client = Mock()
        client.run.return_value = {"node": {"obj_type": "docx", "obj_token": "realDoc"}}
        self.assertEqual(resolve_document("https://team.feishu.cn/wiki/node123", client), "realDoc")
        client.run.return_value = {"node": {"obj_type": "sheet", "obj_token": "sheet123"}}
        with self.assertRaisesRegex(LarkImportError, "sheet"):
            resolve_document("https://team.feishu.cn/wiki/node123", client)
        for url in ("https://evil.example/docx/id", "https://feishu.cn.evil.example/docx/id", "https://team.feishu.cn/sheets/id"):
            with self.subTest(url=url), self.assertRaises(LarkImportError):
                resolve_document(url, client)

    def test_native_metadata_chart_highlight_and_quote_round_trip(self):
        source = '''```yaml
golajahslide: deck
title: 测试
```
```yaml
golajahslide: slide
id: graph
layout: chart
```
# 图表
```plaintext
golajahslide: chart
type: bar
labels: 甲 | 乙
values: 1 | 2
```
> [!TIP]保持原来的提示类型。
<text bgcolor="yellow">高亮内容</text>
'''
        normalized = self.normalize(source)
        self.assertIn("<!-- slide\nid: graph", normalized)
        self.assertIn("```chart\ntype: bar", normalized)
        self.assertIn("> [!TIP]\n> 保持原来的提示类型。", normalized)
        self.assertIn("==高亮内容==", normalized)
        deck, chunks = build_slides.split_deck_source(normalized)
        self.assertEqual(deck["title"], "测试")
        self.assertEqual(len(chunks), 1)

    def test_literal_tags_and_dividers_in_code_are_preserved(self):
        resolver = Mock()
        source = '# 示例\n`<image token="not-media"/>`\n```html\n<image token="not-media"/>\n---\n```\n'
        text = normalize_markdown(source, "例子", resolver)
        resolver.assert_not_called()
        self.assertIn('`<image token="not-media"/>`', text)
        self.assertEqual(len(build_slides.split_deck_source(text)[1]), 1)

    def test_simple_table_and_native_callout(self):
        text = self.normalize('''# 表格
<lark-table header-row="true"><lark-tr><lark-td>列一</lark-td><lark-td>列二</lark-td></lark-tr>
<lark-tr><lark-td>`<tag>`</lark-td><lark-td>数值</lark-td></lark-tr></lark-table>
<callout emoji="💡">方法提示</callout>''')
        self.assertIn("| 列一 | 列二 |", text)
        self.assertIn("| `<tag>` | 数值 |", text)
        self.assertIn("> [!TIP]\n> 方法提示", text)

    def test_unsupported_blocks_and_merged_cells_fail_visibly(self):
        for source in ('<sheet token="x"/>', '<grid cols="2">内容</grid>',
                       '<lark-table><lark-tr><lark-td colspan="2">合并</lark-td></lark-tr></lark-table>'):
            with self.subTest(source=source), self.assertRaises(LarkImportError):
                self.normalize("# 页面\n" + source)

    def test_h1_page_splitting_and_plain_document_title(self):
        self.assertEqual(len(build_slides.split_deck_source(self.normalize("# 一\n正文\n# 二\n正文"))[1]), 2)
        self.assertIn("# 文档标题", self.normalize("普通正文"))

    def test_h1_split_keeps_next_page_metadata_with_next_page(self):
        source = '# 一\n正文\n```yaml\ngolajahslide: slide\nid: second\n```\n# 二\n正文'
        chunks = build_slides.split_deck_source(self.normalize(source))[1]
        self.assertNotIn("id: second", chunks[0])
        self.assertIn("id: second", chunks[1])

    def test_import_download_build_and_embed_is_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "index.lark"
            client = Mock()
            def run(*args, cwd=None):
                if "+fetch" in args:
                    return {"title": "图片", "markdown": '# 图片\n<image token="../../unsafe" caption="图片说明"/>', "has_more": False}
                self.assertEqual(args[args.index("--type") + 1], "media")
                target = cwd / (args[args.index("--output") + 1] + ".png")
                target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 1600, 900))
                return {"path": str(target)}
            client.run.side_effect = run
            snapshot = import_document("doc123", directory, client)
            output = root / "index.html"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_slides.build(snapshot, output, strict=True), 0)
            embed_media(output, directory)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn('src="data:image/png;base64,', rendered)
            self.assertIn("图片说明", rendered)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertTrue(report["sourceImport"]["embeddedImages"])
            self.assertEqual(report["layouts"], {"1": "media"})

    def test_cli_failure_propagates_without_shell(self):
        with patch("src.importers.lark.cli_command", return_value=["lark-cli"]):
            client = LarkClient()
        with patch("src.importers.lark.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "login expired")) as run:
            with self.assertRaisesRegex(LarkImportError, "login expired"):
                client.run("docs", "+fetch", "--doc", "doc123")
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertEqual(run.call_args.args[0][-2:], ["--as", "user"])

    def test_main_accepts_direct_lark_url_and_explicit_flag(self):
        for args in (["https://team.feishu.cn/docx/id"], ["--lark", "doc123"]):
            with self.subTest(args=args), patch("sys.argv", ["build_slides.py", *args]), \
                 patch("src.importers.lark.LarkClient"), \
                 patch("src.importers.lark.import_document", return_value=Path("slides.md")) as importer, \
                 patch("src.importers.lark.embed_media") as embed, \
                 patch("build_slides.build", return_value=0):
                self.assertEqual(build_slides.main(), 0)
                self.assertEqual(importer.call_args.args[0], args[-1])
                embed.assert_called_once()

    def test_live_fixture_preserves_eight_page_layouts_and_semantics(self):
        root = build_slides.ROOT / "examples/lark/index.lark"
        raw = (root / "source.lark.md").read_text(encoding="utf-8")
        normalized = self.normalize(raw)
        deck, chunks = build_slides.split_deck_source(normalized)
        messages = build_slides.BuildMessages()
        slides = [build_slides.parse_slide(chunk, i, deck, root, root, messages) for i, chunk in enumerate(chunks, 1)]
        self.assertEqual(len(slides), 8)
        self.assertEqual([s.slide_id for s in slides], ["cover", "layout-section", "square-image", "wide-image", "chinese-layout", "table-controls", "chart-controls", "delivery-check"])
        self.assertEqual(len(slides[5].blocks), 1)
        self.assertEqual(slides[5].blocks[0].kind, "table")
        self.assertIn("callout-tip", slides[4].blocks[-1].html)
        self.assertIn("<mark", slides[2].blocks[0].html)
        self.assertEqual(slides[6].blocks[0].kind, "chart")


if __name__ == "__main__":
    unittest.main()
