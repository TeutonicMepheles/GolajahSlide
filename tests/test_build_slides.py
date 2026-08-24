import contextlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build_slides

SAMPLE_SOURCE = build_slides.ROOT / "examples" / "basic" / "slides.md"


class SlideTemplateTests(unittest.TestCase):
    def setUp(self):
        self.messages = build_slides.BuildMessages()

    def test_ratio_driven_layouts(self):
        square = build_slides.Media("square.svg", "square.svg", "", "", 800, 800)
        wide = build_slides.Media("wide.svg", "wide.svg", "", "", 1600, 900)
        short_copy = [build_slides.Block("section", "", "简短说明")]
        self.assertEqual(build_slides.resolve_layout("content", "auto", [square], short_copy, self.messages, 1), "split")
        self.assertEqual(build_slides.resolve_layout("content", "auto", [wide], short_copy, self.messages, 2), "media")
        self.assertEqual(build_slides.resolve_layout("content", "chart", [square], short_copy, self.messages, 3), "split")

    def test_wide_media_falls_back_when_copy_is_long(self):
        wide = build_slides.Media("wide.svg", "wide.svg", "", "", 1600, 900)
        long_copy = [build_slides.Block("section", "", "说明" * 60)]
        self.assertEqual(build_slides.resolve_layout("content", "auto", [wide], long_copy, self.messages, 3), "split")

    def test_sample_build_has_no_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sample.html"
            result = build_slides.build(SAMPLE_SOURCE, output)
            self.assertEqual(result, 0)
            self.assertTrue(output.exists())
            source = output.read_text(encoding="utf-8")
            self.assertIn('data-layout-resolved="media"', source)
            self.assertIn("class PresenterFocus", source)
            for placeholder in build_slides.TEMPLATE_FRAGMENT_PATHS:
                self.assertNotIn(placeholder, source)

    def test_archscribe_block_embeds_animation_and_reduced_motion_poster(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "flow.spec.json").write_text('{"layout":"graph"}', encoding="utf-8")
            (assets / "flow.gif").write_bytes(b"GIF89a")
            (assets / "flow.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 1110, 300))
            (assets / "flow.excalidraw").write_text(json.dumps({"elements": [
                {"type": "text", "text": "中文流程", "x": 80, "y": 190, "width": 80, "height": 24, "fontSize": 17}
            ]}), encoding="utf-8")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""---
title: Diagram test
---
<!-- slide
id: flow
type: content
layout: auto
-->
# 中文动态流程图

```archscribe
spec: assets/flow.spec.json
src: assets/flow.gif
poster: assets/flow.png
title: 中文流程
alt: 包含失败回路的中文流程图
crop: 50,160,1110,300
min-font-size: 28
```
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            source = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertIn('data-diagram-engine="archscribe"', source)
            self.assertIn('data-layout-resolved="chart"', source)
            self.assertIn('(prefers-reduced-motion: reduce)', source)
            self.assertIn('srcset="assets/flow.png"', source)
            self.assertEqual(report["archscribe"]["detected"], 1)
            self.assertGreaterEqual(report["archscribe"]["typography"]["flow"]["projectedMinFontSize"], 28)
            self.assertGreaterEqual(report["archscribe"]["typography"]["flow"]["minimumSafeMargin"], 24)
            self.assertEqual(report["warnings"], [])

    def test_archscribe_typography_below_minimum_fails(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "flow.spec.json").write_text('{"layout":"graph"}', encoding="utf-8")
            (assets / "flow.gif").write_bytes(b"GIF89a")
            (assets / "flow.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 1210, 654))
            (assets / "flow.excalidraw").write_text(json.dumps({"elements": [
                {"type": "text", "text": "过小文字", "x": 100, "y": 200, "width": 80, "height": 20, "fontSize": 12}
            ]}), encoding="utf-8")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""# 字号失败示例

```archscribe
spec: assets/flow.spec.json
src: assets/flow.gif
poster: assets/flow.png
min-font-size: 28
```
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertTrue(any("最小字号投影后" in error for error in report["errors"]))

    def test_mermaid_svg_is_inlined_namespaced_and_validated(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            svg_path = assets / "flow.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" id="base" viewBox="0 0 1000 400">'
                '<style>#base .edge{marker-end:url(#arrow)}</style>'
                '<defs><marker id="arrow"><path d="M0 0L10 5L0 10Z"/></marker></defs>'
                '<path class="edge" d="M40 200H900" marker-end="url(#arrow)"/>'
                '<text x="80" y="180" font-size="28">中文流程</text></svg>\n',
                encoding="utf-8",
            )
            svg_path.with_suffix(".diagram-build.json").write_text(json.dumps({
                "schemaVersion": "1.0",
                "engine": "mermaid",
                "svgSha256": build_slides.sha256_file(svg_path),
                "minimumSafeMargin": 32,
                "minimumSourceFontSize": 28,
            }), encoding="utf-8")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""<!-- slide
id: flow
type: content
layout: chart
footer: false
-->
# Mermaid SVG

```mermaid
@slide
src: assets/flow.svg
title: 中文流程
alt: 中文流程说明
@end
flowchart LR
  A --> B
```
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            source = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertIn('data-diagram-engine="mermaid"', source)
            self.assertIn('<svg', source)
            self.assertNotIn('src="assets/flow.svg"', source)
            self.assertNotIn('id="base"', source)
            self.assertNotIn("url(#arrow)", source)
            self.assertNotIn("mermaid.run", source)
            quality = report["diagrams"]["quality"]["flow"][0]
            self.assertGreaterEqual(quality["projectedMinFontSize"], 28)
            self.assertGreaterEqual(quality["minimumSafeMargin"], 24)

    def test_excalidraw_svg_requires_matching_quality_report(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "flow.excalidraw").write_text('{"type":"excalidraw","version":2,"elements":[]}', encoding="utf-8")
            svg_path = assets / "flow.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 400">'
                '<text x="60" y="120" font-size="32">可编辑流程</text></svg>\n',
                encoding="utf-8",
            )
            svg_path.with_suffix(".diagram-build.json").write_text(json.dumps({
                "schemaVersion": "1.0",
                "engine": "excalidraw",
                "svgSha256": "stale-hash",
                "minimumSafeMargin": 32,
                "minimumSourceFontSize": 32,
            }), encoding="utf-8")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""<!-- slide
id: editable
type: content
layout: chart
footer: false
-->
# Excalidraw SVG

```excalidraw
source: assets/flow.excalidraw
src: assets/flow.svg
title: 可编辑流程
```
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertTrue(any("质量报告不一致" in error for error in report["errors"]))

    def test_mermaid_requires_explicit_slide_metadata(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""# Mermaid metadata

```mermaid
flowchart LR
  A --> B
```
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertTrue(any("@slide" in error for error in report["errors"]))

    def test_mermaid_frontmatter_does_not_split_slides(self):
        deck, chunks = build_slides.split_deck_source("""# First

```mermaid
@slide
src: assets/flow.svg
@end
---
config:
  theme: base
---
flowchart LR
  A --> B
```

---

# Second
""")
        self.assertEqual(deck, {})
        self.assertEqual(len(chunks), 2)
        self.assertIn("theme: base", chunks[0])
        self.assertTrue(chunks[1].startswith("# Second"))

    def test_diagram_design_mermaid_tracks_semantic_and_html_sources(self):
        with tempfile.TemporaryDirectory(dir=build_slides.ROOT) as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            authored = assets / "flow.diagram.html"
            authored.write_text(
                '<!doctype html><html><body><svg xmlns="http://www.w3.org/2000/svg" '
                'viewBox="0 0 1840 800" role="img" aria-labelledby="flow-title flow-desc">'
                '<title id="flow-title">Editorial flow</title><desc id="flow-desc">A to B.</desc>'
                '<rect width="1840" height="800" fill="#fff"/>'
                '<text x="80" y="120" font-size="28">A to B</text></svg></body></html>',
                encoding="utf-8",
            )
            svg_path = assets / "flow.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1840 800">'
                '<text x="80" y="120" font-size="28">A to B</text></svg>\n',
                encoding="utf-8",
            )
            definition = "flowchart LR\n  A --> B"
            svg_path.with_suffix(".diagram-build.json").write_text(json.dumps({
                "schemaVersion": "1.0",
                "engine": "diagram-design",
                "renderer": "diagram-design",
                "source": "assets/flow.diagram.html",
                "sourceHtmlSha256": build_slides.sha256_file(authored),
                "mermaidSourceHash": build_slides.mermaid_semantic_hash(definition),
                "svgSha256": build_slides.sha256_file(svg_path),
                "minimumSafeMargin": 48,
                "minimumSourceFontSize": 28,
            }), encoding="utf-8")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text(f"""<!-- slide
id: editorial
type: content
layout: chart
footer: false
-->
# Editorial Mermaid

```mermaid
@slide
renderer: diagram-design
source: assets/flow.diagram.html
src: assets/flow.svg
title: Editorial flow
safe-margin: 40
@end
{definition}
```
""", encoding="utf-8")

            result = build_slides.build(markdown, output)
            source = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertIn('data-diagram-engine="diagram-design"', source)
            self.assertEqual(report["diagrams"]["diagramDesign"]["detected"], 1)
            self.assertEqual(report["diagrams"]["mermaid"]["detected"], 0)

            markdown.write_text(markdown.read_text(encoding="utf-8").replace("A --> B", "A --> C"), encoding="utf-8")
            stale_result = build_slides.build(markdown, output)
            stale_report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(stale_result, 1)
            self.assertTrue(any("Mermaid 定义已变化" in error for error in stale_report["errors"]))

    def test_diagram_design_html_rejects_active_or_remote_content(self):
        with self.assertRaisesRegex(ValueError, "script"):
            build_slides.validate_diagram_design_source("<html><script>alert(1)</script></html>")
        with self.assertRaisesRegex(ValueError, "网络资源"):
            build_slides.validate_diagram_design_source('<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.com/x.css"</style></svg>')
        with self.assertRaisesRegex(ValueError, "外部资源"):
            build_slides.validate_diagram_design_source('<svg xmlns="http://www.w3.org/2000/svg"><use href="icons.svg#cloud"/></svg>')
        build_slides.validate_diagram_design_source(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>https://example.com is a label</text><use href="#cloud"/></svg>'
        )

    def test_extract_first_svg_from_editorial_html(self):
        extracted = build_slides.extract_first_svg_from_html(
            '<html><body><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9">'
            '<text font-size="28">safe</text></svg><svg viewBox="0 0 1 1"></svg></body></html>'
        )
        self.assertIn('viewBox="0 0 16 9"', extracted)
        self.assertNotIn('viewBox="0 0 1 1"', extracted)

    def test_repo_diagram_skill_extracts_golajah_mermaid_metadata_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown = Path(directory) / "slides.md"
            marker = Path(directory) / "must-not-exist"
            markdown.write_text(f"""```mermaid
@slide
renderer: diagram-design
source: assets/flow.diagram.html
src: assets/flow.svg
@end
flowchart LR
  A[输入] --> B[输出]
  click A \"file:///{marker.as_posix()}\"
```
""", encoding="utf-8")
            script = build_slides.ROOT / ".agents" / "skills" / "golajah-diagram-design" / "scripts" / "mermaid_extract.py"
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", str(script), str(markdown), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            payload = json.loads(completed.stdout)
            diagram = payload["diagrams"][0]
            self.assertEqual(diagram["kind"], "flowchart")
            self.assertEqual([node["label"] for node in diagram["nodes"]], ["输入", "输出"])
            self.assertEqual(diagram["discarded"]["click_handlers"], 1)
            self.assertFalse(marker.exists())

    def test_svg_diagram_layout_rejects_multiple_or_mixed_blocks(self):
        slide = build_slides.Slide(
            number=1,
            slide_id="diagram-density",
            kind="content",
            title="Diagram density",
            subtitle="",
            section="",
            layout_requested="chart",
            layout_resolved="chart",
            config={},
            media=[],
            blocks=[
                build_slides.Block("mermaid", "<svg/>", ""),
                build_slides.Block("excalidraw", "<svg/>", ""),
                build_slides.Block("section", "<p>copy</p>", "copy"),
            ],
            raw_body="",
        )

        build_slides.validate_slide(slide, "presentation", self.messages)

        self.assertTrue(any("每页最多放置一个" in error for error in self.messages.errors))
        self.assertTrue(any("不要混排正文块" in error for error in self.messages.errors))

    def test_editor_override_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            output = directory_path / "overridden.html"
            overrides = directory_path / "slides.layout.json"
            overrides.write_text(json.dumps({
                "schemaVersion": "1.0",
                "stage": {"width": 1920, "height": 1080},
                "shortcuts": {"presenterFocus": "Ctrl+K"},
                "branding": {"logo": {"enabled": True, "src": "data:image/png;base64,iVBORw0KGgo=", "width": 236, "height": 88}},
                "slides": {
                    "wide-image": {
                        "layout": "split",
                        "typography": {"lineHeight": 1.6, "color": "#223344", "bold": True},
                        "animation": {"mode": "custom", "order": ["header", "block-1", "visual"], "stepMs": 160},
                        "regions": {
                            "content": {"x": 120, "y": 224, "width": 1660, "height": 680},
                            "visual": {"x": 120, "y": 224, "width": 720, "height": 680},
                            "copy": {"x": 872, "y": 224, "width": 908, "height": 680}
                        }
                    }
                }
            }), encoding="utf-8")
            result = build_slides.build(SAMPLE_SOURCE, output, overrides_path=overrides)
            source = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertIn('data-slide-id="wide-image"', source)
            self.assertIn('data-layout-resolved="split"', source)
            self.assertIn('"x":120', source)
            self.assertIn('"lineHeight":1.6', source)
            self.assertIn('"color":"#223344"', source)
            self.assertIn('"order":["header","block-1","visual"]', source)
            self.assertIn('"stepMs":160', source)
            self.assertIn('"presenterFocus":"Ctrl+K"', source)
            self.assertIn('"branding":{"logo":{"enabled":true,"src":"data:image/png;base64,iVBORw0KGgo=","width":236,"height":88}}', source)
            self.assertEqual(report["layoutOverrides"]["appliedSlides"], ["wide-image"])

    def test_editor_sidecar_is_auto_loaded_and_scaled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "my deck.md"
            output = root / "my deck.html"
            markdown.write_text("""---
title: Sidecar test
---
<!-- slide
id: summary
type: content
layout: auto
-->
# Summary

One point.
""", encoding="utf-8")
            markdown.with_suffix(".layout.json").write_text(json.dumps({
                "schemaVersion": "1.0",
                "stage": {"width": 960, "height": 540},
                "slides": {
                    "summary": {
                        "layout": "split",
                        "regions": {
                            "content": {"x": 55, "y": 107, "width": 850, "height": 358}
                        }
                    }
                }
            }), encoding="utf-8")
            result = build_slides.build(markdown, output)
            source = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertIn('data-layout-resolved="split"', source)
            self.assertIn('"x":110', source)
            self.assertIn('"width":1700', source)
            self.assertEqual(report["layoutOverrides"]["appliedSlides"], ["summary"])
            self.assertTrue(any("坐标已换算" in warning for warning in report["warnings"]))

    def test_duplicate_editor_ids_fail_the_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "duplicate.md"
            output = root / "duplicate.html"
            markdown.write_text("""---
title: Duplicate ID
---
<!-- slide
id: same
type: content
-->
# First

First page.

---

<!-- slide
id: same
type: content
-->
# Second

Second page.
""", encoding="utf-8")
            result = build_slides.build(markdown, output)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertTrue(any("页面 id=same 重复" in error for error in report["errors"]))

    def test_region_normalization_clamps_invalid_bounds(self):
        messages = build_slides.BuildMessages()
        region = build_slides.normalize_region(
            {"x": -200, "y": 1400, "width": 4000, "height": 12}, messages, 1, "content"
        )
        self.assertEqual(region, {"x": 0, "y": 1032, "width": 1920, "height": 48})
        child = build_slides.clamp_region_to_content(
            {"x": 60, "y": 180, "width": 900, "height": 760},
            {"x": 120, "y": 230, "width": 800, "height": 650},
        )
        self.assertEqual(child, {"x": 120, "y": 230, "width": 800, "height": 650})

    def test_editor_typography_and_animation_are_normalized(self):
        messages = build_slides.BuildMessages()
        typography = build_slides.normalize_typography(
            {"lineHeight": 9, "color": "#abc", "bold": "yes"}, messages, 1
        )
        animation = build_slides.normalize_animation(
            {"mode": "custom", "order": ["header", "header", "bad key", "block-1"], "stepMs": 5}, messages, 1
        )
        self.assertEqual(typography, {"lineHeight": 1.8, "color": "#AABBCC", "bold": True})
        self.assertEqual(animation, {"mode": "custom", "order": ["header", "block-1"], "stepMs": 40})

    def test_presenter_focus_shortcut_is_normalized_and_rejects_conflicts(self):
        messages = build_slides.BuildMessages()
        self.assertEqual(build_slides.normalize_presenter_focus_shortcut("shift+ctrl+k", messages), "Ctrl+Shift+K")
        self.assertEqual(build_slides.normalize_presenter_focus_shortcut("E", messages), "H")
        self.assertEqual(build_slides.normalize_presenter_focus_shortcut("Ctrl+A", messages), "H")
        self.assertEqual(build_slides.normalize_presenter_focus_shortcut("not-a-key", messages), "H")
        self.assertEqual(len(messages.warnings), 3)

    def test_block_titles_are_larger_than_body_text(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")

        def font_size(selector):
            import re
            match = re.search(re.escape(selector) + r"\s*\{[^}]*font-size:\s*(\d+)px", template)
            self.assertIsNotNone(match, selector)
            return int(match.group(1))

        self.assertGreater(font_size(".text-card h3"), font_size(".text-card p"))
        self.assertGreater(font_size(".callout-card > strong"), font_size(".callout-card p"))
        self.assertGreater(font_size(".code-label"), font_size(".code-card code"))

    def test_callout_uses_the_same_type_scale_as_plain_content(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn(".text-card h3 { margin: 0 0 14px; color: var(--accent-strong); font-size: 36px;", template)
        self.assertIn(".text-card p { margin: 0; font-size: 29px;", template)
        self.assertIn(".callout-card > strong { display: block; margin-bottom: 10px; color: #fff; font-size: 36px;", template)
        self.assertIn(".callout-card p { color: inherit; font-size: 29px;", template)
        self.assertIn(".text-grid.focus-grid :is(.text-card h3, .callout-card > strong) { font-size: 44px; }", template)
        self.assertIn(".density-speaking :is(.text-card h3, .callout-card > strong) { font-size: 38px; }", template)

    def test_callout_accepts_an_explicit_title_and_preserves_defaults(self):
        explicit = build_slides.parse_blocks(
            "> [!WARNING] Notice\n> 这是风险说明。",
            build_slides.ROOT,
            build_slides.ROOT,
            self.messages,
            1,
        )
        default = build_slides.parse_blocks(
            "> [!WARNING]\n> 这是风险说明。",
            build_slides.ROOT,
            build_slides.ROOT,
            self.messages,
            2,
        )
        self.assertIn("<strong>Notice</strong>", explicit[0].html)
        self.assertIn("callout-warning", explicit[0].html)
        self.assertIn("<strong>风险提示</strong>", default[0].html)

    def test_pure_image_structural_slide_has_no_hero_copy(self):
        media = build_slides.Media("cover.png", "assets/cover.png", "课程封面", "", 1920, 1080)
        slide = build_slides.Slide(
            number=1,
            slide_id="cover",
            kind="cover",
            title="课程标题",
            subtitle="课程副标题",
            section="",
            layout_requested="hero-full",
            layout_resolved="hero-full",
            config={"pure-image": "true", "image-fit": "cover"},
            media=[media],
            blocks=[],
            raw_body="",
        )
        source = build_slides.render_slide(slide, {"density": "speaking"}, [])
        self.assertIn("pure-image-slide", source)
        self.assertIn('class="pure-image-shell reveal"', source)
        self.assertIn('src="assets/cover.png"', source)
        self.assertNotIn("hero-copy", source)
        self.assertNotIn("课程标题</h1>", source)

    def test_gallery_uses_authored_tab_labels_and_falls_back_safely(self):
        media = [
            build_slides.Media(f"{index}.png", f"assets/{index}.png", f"图 {index}", "", 1600, 900)
            for index in range(1, 4)
        ]
        slide = build_slides.Slide(
            number=1,
            slide_id="tabs",
            kind="content",
            title="命名 Tab",
            subtitle="",
            section="前言",
            layout_requested="gallery",
            layout_resolved="gallery",
            config={"tab-labels": "接近性 | 局部露出 | 控件选择"},
            media=media,
            blocks=[],
            raw_body="",
        )
        named = build_slides.render_gallery(slide)
        self.assertIn("media-tab-list named-tabs", named)
        self.assertIn(">接近性</button>", named)
        slide.config["tab-labels"] = "数量不匹配 | 回退"
        fallback = build_slides.render_gallery(slide)
        self.assertNotIn("named-tabs", fallback)
        self.assertIn(">1</button>", fallback)

    def test_two_image_gallery_can_opt_into_tabs(self):
        media = [
            build_slides.Media(f"{index}.png", f"assets/{index}.png", f"图 {index}", "", 1600, 900)
            for index in range(1, 3)
        ]
        slide = build_slides.Slide(
            number=1,
            slide_id="two-image-tabs",
            kind="content",
            title="双图 Tab",
            subtitle="",
            section="前言",
            layout_requested="gallery",
            layout_resolved="gallery",
            config={"gallery-display": "tabs", "tab-labels": "模型参数文件 | FineWeb 数据管线"},
            media=media,
            blocks=[],
            raw_body="",
        )
        rendered = build_slides.render_gallery(slide)
        self.assertIn("media-tabs", rendered)
        self.assertIn("media-tab-list named-tabs", rendered)
        self.assertNotIn("media-grid count-2", rendered)

        slide.config = {}
        side_by_side = build_slides.render_gallery(slide)
        self.assertIn("media-grid count-2", side_by_side)

    def test_three_image_gallery_can_explicitly_use_grid(self):
        media = [
            build_slides.Media(f"{index}.png", f"assets/{index}.png", f"图 {index}", "", 1600, 900)
            for index in range(1, 4)
        ]
        slide = build_slides.Slide(
            number=1,
            slide_id="three-image-grid",
            kind="content",
            title="三图并列",
            subtitle="",
            section="前言",
            layout_requested="gallery",
            layout_resolved="gallery",
            config={"gallery-display": "grid"},
            media=media,
            blocks=[],
            raw_body="",
        )
        rendered = build_slides.render_gallery(slide)
        self.assertIn("media-grid count-3", rendered)
        self.assertNotIn("media-tabs", rendered)

    def test_non_heading_content_uses_editorial_type_and_text_dividers(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn('--font-sans: "Source Han Sans SC"', template)
        self.assertIn('--font-serif: "Source Han Serif SC"', template)
        self.assertRegex(template, r"(?s)\.section-card\s*\{[^}]*border:\s*0;[^}]*border-bottom:\s*1px solid")
        self.assertRegex(template, r"(?s)\.section-card\s*\{[^}]*border-radius:\s*0;[^}]*background:\s*transparent;")
        self.assertRegex(template, r"(?s)\.content :is\(\.text-card h3, \.callout-card > strong, \.data-table th\)\s*\{[^}]*font-family:\s*var\(--font-serif\);[^}]*font-weight:\s*700;")
        self.assertRegex(template, r"(?s)\.content :is\(\.text-card p, \.text-card ul, \.text-card ol, \.text-card li, \.data-table td, \.media-figure figcaption\)\s*\{[^}]*font-family:\s*var\(--font-sans\);[^}]*font-weight:\s*400;")
        self.assertRegex(template, r"(?s)\.callout-card\s*\{[^}]*border:\s*0;[^}]*border-radius:\s*0;[^}]*background:\s*var\(--accent\);[^}]*color:\s*rgba\(255,255,255,\.76\);")
        self.assertRegex(template, r"(?s)\.callout-card::after\s*\{[^}]*height:\s*1px;[^}]*background:\s*rgba\(255,255,255,\.72\);")
        self.assertRegex(template, r"(?s)\.callout-card > strong\s*\{[^}]*color:\s*#fff;")
        self.assertRegex(template, r"(?s)\.callout-card code\s*\{[^}]*border:\s*1px solid rgba\(255,255,255,\.32\);[^}]*background:\s*rgba\(17,17,17,\.34\);[^}]*color:\s*#fff;")
        self.assertIn(".code-card { padding:", template)
        self.assertIn(".chart-svg { display:", template)

    def test_missing_source_fails_cleanly_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "existing.html"
            output.write_text("keep this version", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = build_slides.build(root / "missing.md", output)
            self.assertEqual(result, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep this version")
            self.assertIn("cannot read Markdown source", stderr.getvalue())

    def test_runtime_includes_accessible_controls_and_guarded_touch_navigation(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn(".deck-controls:focus-within", template)
        self.assertIn('aria-controls="layoutEditorPanel"', template)
        self.assertIn('aria-hidden="true" inert', template)
        self.assertIn('this.panel.toggleAttribute("inert", !active)', template)
        self.assertIn("event.metaKey || event.ctrlKey || event.altKey", template)
        self.assertIn('event.key === "Escape" && this.layoutEditor.active', template)
        self.assertIn("Math.abs(dx) > Math.abs(dy) * 1.25", template)
        self.assertIn("if (this.layoutEditor.active || event.target.closest", template)
        self.assertIn("file.size > 4 * 1024 * 1024", template)
        self.assertIn('["ArrowLeft", "ArrowRight", "Home", "End"]', template)

    def test_presenter_focus_marks_semantic_text_containers(self):
        paragraph = build_slides.paragraph_block(["<p>正文</p>"], "标题")
        table = build_slides.render_table(["| A |", "| --- |", "| B |"])
        self.assertIn("data-presenter-focus", paragraph.html)
        self.assertIn("data-presenter-focus", table.html)

        slide = build_slides.Slide(
            number=1,
            slide_id="focus-test",
            kind="content",
            title="聚焦测试",
            subtitle="",
            section="测试",
            layout_requested="text",
            layout_resolved="text",
            config={},
            blocks=[paragraph],
            media=[],
            raw_body="",
        )
        source = build_slides.render_slide(slide, {}, ["测试"])
        self.assertIn('class="slide-header reveal" data-presenter-focus', source)
        self.assertIn('class="card text-card section-card" data-presenter-focus', source)

    def test_presenter_focus_supports_explicit_inline_fragments(self):
        source = build_slides.render_inline("普通文本 ==重点 **结论**== 与 `code`")
        self.assertIn('<mark data-presenter-text="inline">重点 <strong>结论</strong></mark>', source)
        self.assertIn("<code>code</code>", source)

    def test_citations_are_numbered_by_first_use_and_reused(self):
        messages = build_slides.BuildMessages()
        source, definitions = build_slides.extract_citations(
            "正文[^kimi]，再次引用[^kimi]。\n\n[^kimi]: Kimi Agent 框架 — https://www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks",
            messages,
        )
        registry = build_slides.CitationRegistry(definitions, messages)
        rendered = build_slides.render_inline(source, registry, 1)
        self.assertEqual(rendered.count('data-citation-number="1"'), 2)
        self.assertIn('data-citation-text="Kimi Agent 框架"', rendered)
        self.assertIn('href="https://www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks"', rendered)
        self.assertNotIn("[^kimi]:", source)
        self.assertEqual(messages.errors, [])

    def test_citations_render_in_slide_title_and_subtitle(self):
        messages = build_slides.BuildMessages()
        _, definitions = build_slides.extract_citations(
            "[^title]: 标题来源 — https://example.com/title\n[^subtitle]: 副标题来源 — https://example.com/subtitle",
            messages,
        )
        registry = build_slides.CitationRegistry(definitions, messages)
        slide = build_slides.Slide(
            1, "heading-citations", "content", "标题[^title]", "副标题[^subtitle]", "测试", "text", "text", {}, [], [], ""
        )
        rendered = build_slides.render_slide(slide, {}, ["测试"], citations=registry)
        header = rendered.split("<header", 1)[1].split("</header>", 1)[0]
        self.assertNotIn("[^title]", header)
        self.assertNotIn("[^subtitle]", header)
        self.assertIn('href="https://example.com/title"', rendered)
        self.assertIn('href="https://example.com/subtitle"', rendered)
        self.assertEqual(messages.errors, [])

    def test_citation_definition_accepts_trailing_markdown_link(self):
        messages = build_slides.BuildMessages()
        _, definitions = build_slides.extract_citations(
            "[^kimi]: Kimi 来源 — [打开原文](https://www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks)",
            messages,
        )
        self.assertEqual(definitions["kimi"].text, "Kimi 来源")
        self.assertEqual(definitions["kimi"].display_url, "www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks")
        self.assertEqual(messages.errors, [])

    def test_citation_validation_reports_missing_duplicate_and_unlinked_definitions(self):
        messages = build_slides.BuildMessages()
        _, definitions = build_slides.extract_citations(
            "[^dup]: 第一条 — https://example.com/one\n[^dup]: 第二条 — https://example.com/two\n[^offline]: 没有链接",
            messages,
        )
        registry = build_slides.CitationRegistry(definitions, messages)
        missing = build_slides.render_inline("缺失[^unknown]", registry, 3)
        self.assertIn("citation-missing", missing)
        self.assertTrue(any("重复定义" in error for error in messages.errors))
        self.assertTrue(any("缺少 http(s)" in error for error in messages.errors))
        self.assertTrue(any("P3" in error and "没有对应定义" in error for error in messages.errors))

    def test_citation_feature_is_composed_into_a_strict_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text(
                "# 引用测试\n\n正文[^kimi]\n\n[^kimi]: Kimi — https://www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks\n",
                encoding="utf-8",
            )
            self.assertEqual(build_slides.build(markdown, output, strict=True), 0)
            rendered = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertIn("class Citations", rendered)
            self.assertNotIn("{{CITATIONS_CSS}}", rendered)
            self.assertEqual(report["citations"], {"defined": 1, "referenced": 1, "ids": ["kimi"]})

    def test_presenter_focus_feature_sources_are_composed_and_input_aware(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        style = build_slides.TEMPLATE_FRAGMENT_PATHS["{{PRESENTER_FOCUS_CSS}}"].read_text(encoding="utf-8")
        runtime = build_slides.TEMPLATE_FRAGMENT_PATHS["{{PRESENTER_FOCUS_RUNTIME}}"].read_text(encoding="utf-8")
        self.assertIn("{{PRESENTER_FOCUS_CSS}}", template)
        self.assertIn("{{PRESENTER_FOCUS_RUNTIME}}", template)
        self.assertIn('id="focus"', template)
        self.assertIn('id="editorPresenterFocusShortcut"', template)
        self.assertIn("matchesShortcut(event)", runtime)
        self.assertIn('aria-keyshortcuts', runtime)
        self.assertIn("class PresenterFocus", runtime)
        self.assertNotIn('event.key === "h" || event.key === "H"', template)
        self.assertIn("body.presenter-focus-enabled:not(.editor-open)", style)
        self.assertIn("@media (hover: hover) and (pointer: fine)", style)
        self.assertIn(":has([data-presenter-focus]:not(.is-fullscreen):hover)", style)
        self.assertIn(":has([data-presenter-text]:hover)", style)
        self.assertIn("registerTextTargets", runtime)
        self.assertIn("presenter-pointer-cue", style)
        self.assertIn("createPointerCue", runtime)
        self.assertIn("requestAnimationFrame", runtime)
        self.assertIn("--presenter-focus-container-ring", style)
        self.assertIn("--presenter-focus-text-ring", style)
        self.assertIn("--presenter-pointer-ring", style)
        self.assertIn("color-mix(in srgb, var(--accent)", style)
        self.assertIn("overflow: visible", style)
        self.assertIn("@media (prefers-reduced-motion: reduce)", template)

    def test_global_logo_feature_is_composed_and_defaults_off(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        style = build_slides.TEMPLATE_FRAGMENT_PATHS["{{GLOBAL_LOGO_CSS}}"].read_text(encoding="utf-8")
        runtime = build_slides.TEMPLATE_FRAGMENT_PATHS["{{GLOBAL_LOGO_RUNTIME}}"].read_text(encoding="utf-8")
        self.assertIn("{{GLOBAL_LOGO_CSS}}", template)
        self.assertIn("{{GLOBAL_LOGO_RUNTIME}}", template)
        self.assertIn('id="editorLogoEnabled"', template)
        self.assertIn('id="editorLogoFile"', template)
        self.assertIn("class GlobalLogo", runtime)
        self.assertIn("sourceFromFile", runtime)
        self.assertIn('dataset.globalLogoVisibility === "hidden"', runtime)
        self.assertIn(".global-logo", style)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.html"
            self.assertEqual(build_slides.build(SAMPLE_SOURCE, output), 0)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn('"branding":{"logo":{"enabled":false,"src":"","width":190,"height":72}}', rendered)
            self.assertNotIn("{{GLOBAL_LOGO_CSS}}", rendered)
            self.assertNotIn("{{GLOBAL_LOGO_RUNTIME}}", rendered)

        source = """---\ntitle: Logo visibility\n---\n\n<!-- slide\nid: shown\ntype: content\nlayout: text\n-->\n# Shown\n\n---\n\n<!-- slide\nid: hidden\ntype: content\nlayout: text\nglobal-logo: hidden\n-->\n# Hidden\n"""
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "slides.md"
            output = Path(directory) / "index.html"
            source_path.write_text(source, encoding="utf-8")
            self.assertEqual(build_slides.build(source_path, output), 0)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn('data-slide-id="shown"', rendered)
            self.assertIn('data-global-logo-visibility="visible"', rendered)
            self.assertIn('data-slide-id="hidden"', rendered)
            self.assertIn('data-global-logo-visibility="hidden"', rendered)

    def test_footer_chapters_group_repeated_names_and_fall_back_to_titles(self):
        slides = [
            build_slides.Slide(1, "intro", "content", "开场", "", "基础", "text", "text", {}, [], [], "", "概览"),
            build_slides.Slide(2, "intro-more", "content", "更多开场", "", "基础", "text", "text", {}, [], [], "", "概览"),
            build_slides.Slide(3, "setup", "content", "配置", "", "基础", "text", "text", {}, [], [], ""),
            build_slides.Slide(4, "advanced", "content", "深入标题", "", "深入", "text", "text", {}, [], [], ""),
        ]

        chapters = build_slides.collect_section_chapters(["基础", "深入"], slides)

        self.assertEqual(chapters["基础"], [
            {"title": "概览", "page": 1},
            {"title": "配置", "page": 3},
        ])
        self.assertEqual(chapters["深入"], [{"title": "深入标题", "page": 4}])
        footer = build_slides.render_footer(slides[1], ["基础", "深入"], chapters)
        self.assertEqual(footer.count('role="menuitem"'), 3)
        self.assertIn('data-slide-target="0" data-page-number="1"', footer)
        self.assertIn('data-slide-target="2" data-page-number="3"', footer)
        self.assertIn('aria-current="location"', footer)

    def test_footer_chapter_navigation_feature_is_composed(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        style = build_slides.TEMPLATE_FRAGMENT_PATHS["{{FOOTER_CHAPTER_NAVIGATION_CSS}}"].read_text(encoding="utf-8")
        runtime = build_slides.TEMPLATE_FRAGMENT_PATHS["{{FOOTER_CHAPTER_NAVIGATION_RUNTIME}}"].read_text(encoding="utf-8")
        self.assertIn("{{FOOTER_CHAPTER_NAVIGATION_CSS}}", template)
        self.assertIn("{{FOOTER_CHAPTER_NAVIGATION_RUNTIME}}", template)
        self.assertIn("class FooterChapterNavigation", runtime)
        self.assertIn("bottom: 54px", style)
        self.assertIn("body.editor-open .section-footer-menu", style)
        self.assertIn("@media print", style)
        self.assertIn("new FooterChapterNavigation(presentation)", template)

    def test_local_video_renders_native_media_and_composes_playback_feature(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        style = build_slides.TEMPLATE_FRAGMENT_PATHS["{{MEDIA_PLAYBACK_CSS}}"].read_text(encoding="utf-8")
        runtime = build_slides.TEMPLATE_FRAGMENT_PATHS["{{MEDIA_PLAYBACK_RUNTIME}}"].read_text(encoding="utf-8")
        self.assertIn("{{MEDIA_PLAYBACK_CSS}}", template)
        self.assertIn("{{MEDIA_PLAYBACK_RUNTIME}}", template)
        self.assertIn("class MediaPlayback", runtime)
        self.assertIn(".video-media", style)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "demo.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
            (assets / "demo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""<!-- slide
id: video
type: content
layout: media
footer: false
-->
# 视频演示

![机械臂演示](assets/demo.mp4 "原始演示视频")
""", encoding="utf-8")

            self.assertEqual(build_slides.build(markdown, output, strict=True), 0)
            rendered = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertIn('<video controls playsinline preload="metadata" data-slide-video', rendered)
            self.assertRegex(rendered, r'<source src="data:video/mp4;base64,[^"]+" type="video/mp4">')
            self.assertRegex(rendered, r'poster="data:image/png;base64,[^"]+"')
            self.assertIn('data-slide-video-shell', rendered)
            self.assertNotIn("{{MEDIA_PLAYBACK_CSS}}", rendered)
            self.assertNotIn("{{MEDIA_PLAYBACK_RUNTIME}}", rendered)
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["errors"], [])

    def test_video_autoplay_loop_is_scoped_by_slide_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "demo.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""<!-- slide
id: loop
type: content
layout: split
video-playback: autoplay-loop
footer: false
-->
# 循环视频

![会话间消息传递](assets/demo.mp4 "自动循环演示")

### 说明

只在这一页自动播放。
""", encoding="utf-8")

            self.assertEqual(build_slides.build(markdown, output, strict=True), 0)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn('<video autoplay loop muted playsinline preload="auto" data-slide-video data-video-autoplay', rendered)
            self.assertNotIn('<video controls', rendered)

    def test_authoring_document_preserves_exact_source_and_utf16_ranges(self):
        source = (
            "\ufeff---\r\ntitle: 可逆模型\r\n---\r\n\r\n"
            "<!-- slide\r\nid: first\r\nlayout: gallery\r\ngallery-display: tabs\r\n-->\r\n"
            "# 第一页😀\r\n## 副标题\r\n\r\n"
            "![图一](assets/one.png \"图注一\")\r\n\r\n"
            "### 文本块\r\n\r\n正文[^source]\r\n\r\n"
            "> [!TIP] 提示\r\n> Callout 正文\r\n\r\n"
            "---\r\n\r\n# 第二页\r\n\r\n"
            "```mermaid\r\n---\r\n```\r\n\r\n"
            "[^source]: 原始资料 — https://example.com/source\r\n"
        )
        document = build_slides.parse_authoring_document(source)
        payload = build_slides.authoring_document_payload(document)

        self.assertEqual(document.source, source)
        self.assertTrue(document.bom)
        self.assertEqual(document.newline, "\r\n")
        self.assertEqual(len(document.slides), 2)
        self.assertEqual([item.kind for item in document.slides[0].items], ["image", "text", "callout"])
        self.assertEqual([citation.citation_id for citation in document.citations], ["source"])
        self.assertEqual(payload["source"]["offsetEncoding"], "utf-16")
        reconstructed = payload["source"]["prefix"]
        for index, slide in enumerate(payload["slides"]):
            reconstructed += slide["source"]
            if index < len(payload["source"]["separators"]):
                reconstructed += payload["source"]["separators"][index]
        reconstructed += payload["source"]["suffix"]
        self.assertEqual(reconstructed, source)

        encoded = source.encode("utf-16-le")
        for slide in payload["slides"]:
            source_range = slide["sourceRange"]
            sliced = encoded[source_range["start"] * 2 : source_range["end"] * 2].decode("utf-16-le")
            self.assertEqual(sliced, slide["source"])
            for item in slide["items"]:
                item_range = item["sourceRange"]
                sliced = encoded[item_range["start"] * 2 : item_range["end"] * 2].decode("utf-16-le")
                self.assertEqual(sliced, item["markdown"])

    def test_build_source_hash_uses_exact_crlf_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "slides.md"
            output = root / "index.html"
            source = "# CRLF 页面\r\n\r\n正文。\r\n"
            markdown.write_bytes(source.encode("utf-8"))

            self.assertEqual(build_slides.build(markdown, output, strict=True), 0)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(report["authoring"]["sourceSha256"], build_slides.sha256_file(markdown))

    def test_authoring_item_ids_are_slide_scoped_and_position_independent(self):
        without_media = """<!-- slide
id: stable
-->
# 标题

### 文本块

相同正文。

> [!NOTE] 重复
> 相同提醒。

> [!NOTE] 重复
> 相同提醒。
"""
        with_media = without_media.replace("# 标题\n\n", "# 标题\n\n![新增图片](assets/new.png)\n\n")
        first = build_slides.parse_authoring_document(without_media).slides[0]
        second = build_slides.parse_authoring_document(with_media).slides[0]
        first_text_id = next(item.item_id for item in first.items if item.kind == "text")
        second_text_id = next(item.item_id for item in second.items if item.kind == "text")
        self.assertEqual(first_text_id, second_text_id)
        callout_ids = [item.item_id for item in first.items if item.kind == "callout"]
        self.assertEqual(len(callout_ids), len(set(callout_ids)))
        self.assertTrue(callout_ids[1].endswith("-2"))

    def test_build_attaches_authoring_identity_to_slides_blocks_and_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            for name in ("one.png", "two.png"):
                (assets / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 1600, 900))
            markdown = root / "slides.md"
            output = root / "index.html"
            markdown.write_text("""<!-- slide
id: authored
type: content
layout: gallery
gallery-display: tabs
-->
# 可编辑页面
## 可编辑副标题

![图一](assets/one.png "图注一")
![图二](assets/two.png "图注二")

### 文本块

正文。

> [!TIP] Callout
> 提示正文。
""", encoding="utf-8")

            self.assertEqual(build_slides.build(markdown, output, strict=True), 0)
            rendered = output.read_text(encoding="utf-8")
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            document = build_slides.parse_authoring_document(markdown.read_text(encoding="utf-8"))
            payload = build_slides.authoring_document_payload(document)
            self.assertEqual(payload["slides"][0]["galleryDisplay"], "tabs")
            self.assertEqual([item["kind"] for item in payload["slides"][0]["items"]], ["image", "image", "text", "callout"])
            self.assertIn('data-slide-id="authored"', rendered)
            self.assertRegex(rendered, r'data-author-base-hash="[0-9a-f]{64}"')
            self.assertIn('data-author-item-kind="image"', rendered)
            self.assertIn('data-author-item-kind="text"', rendered)
            self.assertIn('data-author-item-kind="callout"', rendered)
            self.assertIn('data-author-field="slide-title"', rendered)
            self.assertIn('data-author-field="slide-subtitle"', rendered)
            self.assertIn('data-author-field="title"', rendered)
            self.assertIn('data-author-field="body"', rendered)
            self.assertIn('data-author-field="caption"', rendered)
            self.assertEqual(report["authoring"]["sourceSha256"], document.revision)

    def test_layout_source_hash_rejects_stale_content_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "slides.md"
            output = root / "index.html"
            overrides = root / "slides.layout.json"
            markdown.write_text("# 当前源码\n\n正文。\n", encoding="utf-8")
            overrides.write_text(json.dumps({
                "schemaVersion": "1.0",
                "sourceHash": "0" * 64,
                "slides": {"p1": {"layout": "text"}},
            }), encoding="utf-8")

            result = build_slides.build(markdown, output, overrides_path=overrides)
            report = json.loads(output.with_suffix(".build.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertTrue(any("sourceHash" in message for message in report["errors"]))
            self.assertEqual(report["layoutOverrides"]["appliedSlides"], [])

    def test_authoring_model_preserves_explicit_layout_filename_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / "slides.md"
            output = root / "index.html"
            overrides = root / "review.layout.json"
            source = "# 当前源码\n\n正文。\n"
            markdown.write_text(source, encoding="utf-8")
            overrides.write_text(json.dumps({
                "schemaVersion": "1.0",
                "sourceHash": build_slides.sha256_source(source),
                "slides": {},
            }), encoding="utf-8")

            self.assertEqual(build_slides.build(markdown, output, strict=True, overrides_path=overrides), 0)
            rendered = output.read_text(encoding="utf-8")
            match = re.search(r'<script id="deckAuthoringModel" type="application/json">(.*?)</script>', rendered, re.S)
            self.assertIsNotNone(match)
            payload = json.loads(match.group(1))
            self.assertEqual(payload["source"]["layoutName"], "review.layout.json")
            self.assertEqual(payload["source"]["layoutSha256"], build_slides.sha256_file(overrides))
            self.assertIn('this.outputName = "review.layout.json"', rendered)
            editor_match = re.search(r'<script id="deckEditorConfig" type="application/json">(.*?)</script>', rendered, re.S)
            self.assertIsNotNone(editor_match)
            editor_payload = json.loads(editor_match.group(1))
            self.assertEqual(editor_payload["sourceHash"], build_slides.sha256_source(source))

    def test_atomic_writer_replaces_content_without_temp_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact.txt"
            target.write_text("old", encoding="utf-8")
            target.chmod(0o644)
            build_slides.write_text_atomic(target, "new\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "new\n")
            if os.name != "nt":
                self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
