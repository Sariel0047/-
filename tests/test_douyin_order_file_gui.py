"""
抖音订单表离线处理窗口测试。
"""

from __future__ import annotations

from pathlib import Path

from qianiu_auto_report.douyin_order_file_gui import DouyinOrderFileWindow


class _FakeVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def test_get_request_accepts_local_table_file(tmp_path: Path) -> None:
    """
    抖音离线窗口应读取本地表格路径。
    """
    input_file = tmp_path / "douyin.csv"
    input_file.write_bytes(b"placeholder")

    fake = type("FakeWindow", (), {})()
    fake.input_file_var = _FakeVar(str(input_file))

    request = DouyinOrderFileWindow._get_request(fake)

    assert request == {
        "input_file": input_file,
    }


def test_get_request_accepts_wps_et_file(tmp_path: Path) -> None:
    """
    抖音离线窗口应接受 WPS 表格 .et 文件。
    """
    input_file = tmp_path / "douyin.et"
    input_file.write_bytes(b"placeholder")

    fake = type("FakeWindow", (), {})()
    fake.input_file_var = _FakeVar(str(input_file))

    request = DouyinOrderFileWindow._get_request(fake)

    assert request == {
        "input_file": input_file,
    }
