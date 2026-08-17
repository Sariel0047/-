"""
Tk 界面任务入口与紧凑布局配置回归测试。
"""

from __future__ import annotations

from qianiu_auto_report.douyin_order_file_gui import DouyinOrderFileWindow
from qianiu_auto_report.gui import AppGUI


def test_main_window_exposes_online_tmall_and_douyin_tasks() -> None:
    fake = type("FakeGUI", (), {})()
    fake.open_order_export_window = lambda: None
    fake.open_douyin_order_file_window = lambda: None

    entries = AppGUI._get_task_entries(fake)

    assert [label for label, _command in entries] == [
        "在线自动生成",
        "天猫订单表处理",
        "抖音订单表处理",
    ]
    assert entries[0][1] is None
    assert callable(entries[1][1])
    assert callable(entries[2][1])


def test_main_and_douyin_use_compact_log_layouts() -> None:
    assert AppGUI.LOG_HEIGHT <= 10
    assert DouyinOrderFileWindow.LOG_HEIGHT <= 6
