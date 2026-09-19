from pathlib import Path
import unittest

import build_slides
from src.importers.lark import normalize_markdown


class ListHierarchyTests(unittest.TestCase):
    def render(self, source):
        lines = source.splitlines()
        result, end = build_slides.parse_list(lines, 0)
        self.assertEqual(end, len(lines))
        return result

    def test_nested_ordered_lists_keep_parent_child_ownership(self):
        self.assertEqual(self.render('1. **保持干燥：**\n   1. 食品\n1. **禁火防燃：**\n   1. 明火\n   1. 用电'),
                         '<ol><li><strong>保持干燥：</strong><ol><li>食品</li></ol></li><li><strong>禁火防燃：</strong><ol><li>明火</li><li>用电</li></ol></li></ol>')

    def test_three_levels_mixed_types_and_tabs(self):
        self.assertEqual(self.render('1. 父\n\t- 子\n\t\t1. 孙\n\t- 子二\n1. 父二'),
                         '<ol><li>父<ul><li>子<ol><li>孙</li></ol></li><li>子二</li></ul></li><li>父二</li></ol>')

    def test_blank_lines_and_wrapped_item_text(self):
        self.assertEqual(self.render('- 第一行\n  续行 **强调**\n\n  1. 子项\n\n- 第二项'),
                         '<ul><li>第一行 续行 <strong>强调</strong><ol><li>子项</li></ol></li><li>第二项</li></ul>')

    def test_numbered_list_start_and_repeated_one_markers(self):
        self.assertEqual(self.render('3. 三\n1. 四'), '<ol start="3"><li>三</li><li>四</li></ol>')
        self.assertEqual(self.render('1) 一\n1) 二'), '<ol><li>一</li><li>二</li></ol>')

    def test_flat_list_output_is_unchanged(self):
        self.assertEqual(self.render('- 一\n- 二'), '<ul><li>一</li><li>二</li></ul>')

    def test_following_paragraph_heading_and_code_are_not_swallowed(self):
        for suffix in ['正文', '### 卡片', '```python', '> 引用', '---', '| 列 |']:
            with self.subTest(suffix=suffix):
                _, end = build_slides.parse_list(['1. 父', '   1. 子', '', suffix], 0)
                self.assertEqual(end, 2)

    def test_adjacent_list_types_remain_separate(self):
        blocks = build_slides.parse_blocks('- 一\n1. 二', Path('.'), Path('.'), build_slides.BuildMessages(), 1)
        self.assertIn('<ul><li>一</li></ul><ol><li>二</li></ol>', blocks[0].html)

    def test_lark_normalization_preserves_list_indentation(self):
        source = normalize_markdown('# 页面\n1. 父\n   1. 子\n      - 孙', '文档', None)
        _, chunks = build_slides.split_deck_source(source)
        slide = build_slides.parse_slide(chunks[0], 1, {}, Path('.'), Path('.'), build_slides.BuildMessages())
        self.assertIn('<ol><li>父<ol><li>子<ul><li>孙</li></ul></li></ol></li></ol>', slide.blocks[0].html)


if __name__ == '__main__':
    unittest.main()
