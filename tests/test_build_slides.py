import contextlib
import io
import json
import os
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
        self.assertIn("file.size > 2 * 1024 * 1024", template)
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

    def test_presenter_focus_feature_sources_are_composed_and_input_aware(self):
        template = build_slides.TEMPLATE_PATH.read_text(encoding="utf-8")
        style = build_slides.TEMPLATE_FRAGMENT_PATHS["{{PRESENTER_FOCUS_CSS}}"].read_text(encoding="utf-8")
        runtime = build_slides.TEMPLATE_FRAGMENT_PATHS["{{PRESENTER_FOCUS_RUNTIME}}"].read_text(encoding="utf-8")
        self.assertIn("{{PRESENTER_FOCUS_CSS}}", template)
        self.assertIn("{{PRESENTER_FOCUS_RUNTIME}}", template)
        self.assertIn('id="focus"', template)
        self.assertIn("class PresenterFocus", runtime)
        self.assertIn('event.key === "h" || event.key === "H"', template)
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
