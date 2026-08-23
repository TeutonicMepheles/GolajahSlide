# Slide Authoring Controls

- Plan ID: `20260822-slide-authoring-controls`
- Status: `Implemented`
- Created: `2026-08-22`
- Last updated: `2026-08-24`

## Goal

补齐结构页和 Gallery 的显式创作控制，并让 Callout 与标题区域复用现有行内引用能力。

## Scope

- `pure-image: true` 让 cover / section 的第一张图片铺满舞台。
- `tab-labels` 提供命名 Gallery Tab；`gallery-display: tabs` 允许双图显式切换。
- Callout 类型标记后可追加自定义标题。
- 页面标题与副标题支持标准脚注引用。

## Non-goals

- 不改变未声明配置的布局结果。
- 不改变 Markdown 页面边界或自动重写作者内容。
- 不引入外部依赖。

## Acceptance gates

- [x] `gallery-display: tabs` 使双图 Gallery 使用命名标签切换。
- [x] 未声明该配置的双图 Gallery 继续并列显示。
- [x] `pure-image` 只对 cover / section 生效并校验媒体类型。
- [x] 显式 Callout 标题与默认中文标题均正确渲染。
- [x] 标题和副标题中的引用被解析并纳入来源工具提示。
- [x] 严格构建无 warning / error。
- [x] 单元测试与完整浏览器测试通过。

## Validation evidence

- `test_pure_image_structural_slide_has_no_hero_copy` 覆盖纯图结构页。
- `test_gallery_uses_authored_tab_labels_and_falls_back_safely` 与 `test_two_image_gallery_can_opt_into_tabs` 覆盖 Gallery 行为。
- `test_callout_accepts_an_explicit_title_and_preserves_defaults` 与 `test_citations_render_in_slide_title_and_subtitle` 覆盖文本扩展。
- 2026-08-24：完整 `npm test` 与 `git diff --check` 通过。
