#!/usr/bin/env python3
"""clashctl 展示顺序回归：pool_order 从 Script.js 还原地区池名线索。

组名统一加后缀后，曾出现配置顺序与命令行显示顺序不一致；这里用打补丁的
脚本源码验证后缀解析，以及名字被避让（X / XYZ / 年月日）时的前缀匹配。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from clashctl import commands, platform, setup_console

setup_console()


SCRIPT_TEMPLATE = """var REGION_NAME = { HK: "香港", SG: "新加坡", US: "美国" };
var PREFER = ["HK", "SG", "US"];
"""

# 带实测清单：CA 3 个、GB 2 个、DE 1 个，用来验证未列入 PREFER 的桶排序
SCRIPT_WITH_MANIFEST = """var REGION_NAME = { HK: "香港", SG: "新加坡", US: "美国", CA: "加拿大", GB: "英国", DE: "德国" };
var PREFER = ["HK", "SG", "US"];
var POOL_SUFFIX = "池";
// >>> VERIFIED-EXITS
var VERIFIED = {
  "CA 1": ["CA", 100], "CA 2": ["CA", 110], "CA 3": ["CA", 120],
  "GB 1": ["GB", 200], "GB 2": ["GB", 210],
  "DE 1": ["DE", 300]
};
// <<< VERIFIED-EXITS
"""


class PoolOrderTests(unittest.TestCase):
    def _order(self, script_text, pools, node_names=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Script.js")
            Path(path).write_text(script_text, encoding="utf-8")
            with patch.object(platform, "script_path", return_value=path):
                return commands.pool_order(pools, node_names)

    def test_pool_order_reads_suffix(self):
        got = self._order(SCRIPT_TEMPLATE + 'var POOL_SUFFIX = "池";\n',
                          ["美国池", "德国池", "香港池", "新加坡池"])
        self.assertEqual(got, ["香港池", "新加坡池", "美国池", "德国池"])

    def test_pool_order_without_suffix_still_works(self):
        got = self._order(SCRIPT_TEMPLATE, ["新加坡", "香港", "德国"])
        self.assertEqual(got, ["香港", "新加坡", "德国"])

    def test_pool_order_matches_escalated_names(self):
        # 名字被订阅节点占用时会加 X / XYZ / 日期，显示顺序仍要按地区归位
        got = self._order(SCRIPT_TEMPLATE + 'var POOL_SUFFIX = "池";\n',
                          ["美国池 X", "香港池", "新加坡池"])
        self.assertEqual(got, ["香港池", "新加坡池", "美国池 X"])

    def test_pool_order_tail_uses_verified_node_counts(self):
        # API 键序是字典序（加拿大/德国/英国），配置真实顺序按实测节点数降序
        alive = ["CA 1", "CA 2", "CA 3", "GB 1", "GB 2", "DE 1"]
        got = self._order(SCRIPT_WITH_MANIFEST,
                          ["加拿大池", "德国池", "英国池"], alive)
        self.assertEqual(got, ["加拿大池", "英国池", "德国池"])

    def test_pool_order_prefer_ranks_before_node_count(self):
        # PREFER 里的地区无条件优先，即使清单里它的节点数更少
        got = self._order(SCRIPT_WITH_MANIFEST, ["加拿大池", "新加坡池", "香港池"])
        self.assertEqual(got, ["香港池", "新加坡池", "加拿大池"])

    def test_pool_order_tail_matches_escalated_names(self):
        alive = ["CA 1", "CA 2", "CA 3", "GB 1", "GB 2", "DE 1"]
        got = self._order(SCRIPT_WITH_MANIFEST,
                          ["加拿大池 X", "德国池", "英国池"], alive)
        self.assertEqual(got, ["加拿大池 X", "英国池", "德国池"])


if __name__ == "__main__":
    unittest.main()
