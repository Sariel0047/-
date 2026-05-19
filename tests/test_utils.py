"""
`utils.py` 测试骨架。
"""


from __future__ import annotations

import time
from pathlib import Path

from qianiu_auto_report.utils import snapshot_directory, wait_for_download_complete


def test_wait_for_download_complete_ignores_unrelated_old_temp_files(tmp_path: Path) -> None:
    """
    目录里存在历史 .tmp 文件时，不应阻塞本次新下载文件识别。
    """
    old_tmp = tmp_path / "history.tmp"
    old_tmp.write_text("old-temp", encoding="utf-8")

    baseline = snapshot_directory(tmp_path)
    report = tmp_path / "new_report.xlsx"
    report.write_bytes(b"excel-bytes")

    result = wait_for_download_complete(
        directory=tmp_path,
        timeout_seconds=2,
        poll_interval_seconds=0.05,
        start_time=time.time(),
        previous_snapshot=baseline,
        temp_suffixes=(".tmp", ".crdownload", ".part"),
        file_filter=lambda item: item.suffix.lower() == ".xlsx",
    )

    assert result == report


def test_wait_for_download_complete_accepts_new_file_even_if_old_mtime(tmp_path: Path) -> None:
    """
    新文件若 mtime 早于触发时间（例如服务端时间回写），仍应识别为下载结果。
    """
    baseline = snapshot_directory(tmp_path)
    trigger = time.time()

    report = tmp_path / "server_time_report.xlsx"
    report.write_bytes(b"excel-bytes")
    old_ts = trigger - 3600
    report.touch()
    report_stat = report.stat()
    report_mtime_ns = int(old_ts * 1_000_000_000)
    # 使用 ns 级时间，模拟“下载后文件时间戳比触发时间早”的场景
    import os

    os.utime(report, ns=(report_stat.st_atime_ns, report_mtime_ns))

    result = wait_for_download_complete(
        directory=tmp_path,
        timeout_seconds=2,
        poll_interval_seconds=0.05,
        start_time=trigger,
        previous_snapshot=baseline,
        temp_suffixes=(".tmp", ".crdownload", ".part"),
        file_filter=lambda item: item.suffix.lower() == ".xlsx",
    )

    assert result == report


def test_wait_for_download_complete_ignores_disappearing_temp_file(tmp_path: Path, monkeypatch) -> None:
    """
    临时下载文件若在轮询中被 Chrome 迅速重命名并消失，不应导致整个等待流程失败。
    """
    baseline = snapshot_directory(tmp_path)
    trigger = time.time()

    temp_file = tmp_path / "broken_report.xlsx.crdownload"
    temp_file.write_bytes(b"temp")
    report = tmp_path / "broken_report.xlsx"
    report.write_bytes(b"excel-bytes")

    original_stat = Path.stat

    def fake_stat(self: Path, *args, **kwargs):
        if self.name.endswith(".crdownload"):
            raise FileNotFoundError(self)
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat, raising=True)

    result = wait_for_download_complete(
        directory=tmp_path,
        timeout_seconds=2,
        poll_interval_seconds=0.05,
        start_time=trigger,
        previous_snapshot=baseline,
        temp_suffixes=(".tmp", ".crdownload", ".part"),
        file_filter=lambda item: item.suffix.lower() == ".xlsx",
    )

    assert result == report
