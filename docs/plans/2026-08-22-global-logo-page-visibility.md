# Global Logo — Per-slide Visibility Exceptions

- Plan ID: `20260822-global-logo-page-visibility`
- Status: `Implemented`
- Created: `2026-08-22`
- Last updated: `2026-08-24`

## Goal

保留全局 Logo 的统一开关、图片和尺寸，同时允许封面或其他指定页通过页面元数据单独隐藏。

## Scope

- 新增页面指令 `global-logo: hidden`，默认值为 `visible`。
- Logo 运行时同时考虑全局开关和页面级隐藏例外。
- 扩展 Global Logo Harness 与浏览器测试。

## Non-goals

- 不为每页保存独立 Logo 图片或尺寸。
- 不改变全局 Logo 的上传、缩放、导出和持久化合同。
- 不根据页面类型强制自动隐藏；例外必须显式声明。

## Acceptance gates

- [x] 全局 Logo 开启时，普通页显示，`global-logo: hidden` 页不显示。
- [x] 隐藏页不保留 Logo 导致的标题宽度缩减。
- [x] 关闭再打开全局 Logo 后，页面例外仍有效。
- [x] Focused Harness、浏览器测试、`npm test` 与 `git diff --check` 通过。

## Validation evidence

- `global-logo: hidden` 生成 `data-global-logo-visibility="hidden"`，运行时不创建第二套 Logo 状态，只对当前页应用可见性例外。
- Global Logo Harness 同时覆盖普通页与隐藏页，并验证刷新后例外仍然生效。
- 2026-08-24：完整 `npm test` 通过，包括 Python 单元测试及 Presenter Focus、Footer Chapter Navigation、Citations、Global Logo、Media Playback、Diagram Design 浏览器测试。
- `git diff --check` 通过。
