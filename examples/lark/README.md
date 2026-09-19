# 飞书文档示例

[打开飞书文档](https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f)

由 `examples/basic/slides.md` 的 8 页内容创建。正文、标题、表格和图片是飞书原生块，
页面配置和图表数据使用代码块。`authoring.md` 是初始创建文本；`index.lark/`
是实际回读快照；`index.html` 是由该快照生成并嵌入图片的课件。

在项目根目录更新：

```bash
python build_slides.py --lark https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f -o examples/lark/index.html --strict
```

参阅 [飞书内容源说明](../../docs/LARK-SOURCE.md)。
