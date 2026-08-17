"""
天猫订单表离线处理窗口测试。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from qianiu_auto_report.order_export_gui import OrderExportWindow


class _FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


@pytest.mark.parametrize("suffix", [".csv", ".xlsx", ".xls", ".xlsm", ".et"])
def test_get_request_accepts_supported_tmall_table_files(tmp_path: Path, suffix: str) -> None:
    input_file = tmp_path / f"tmall-orders{suffix}"
    input_file.write_bytes(b"placeholder")
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_file))})()

    assert OrderExportWindow._get_request(fake) == {"input_file": input_file}


def test_get_request_rejects_unsupported_file(tmp_path: Path) -> None:
    input_file = tmp_path / "tmall-orders.txt"
    input_file.write_text("placeholder", encoding="utf-8")
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_file))})()

    with pytest.raises(ValueError, match=r"csv/.xlsx/.xls/.xlsm/.et"):
        OrderExportWindow._get_request(fake)


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_get_request_rejects_paths_that_are_not_files(tmp_path: Path, kind: str) -> None:
    input_path = tmp_path / "orders.xlsx"
    if kind == "directory":
        input_path.mkdir()
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_path))})()

    with pytest.raises(ValueError, match="请先选择一份天猫订单明细表"):
        OrderExportWindow._get_request(fake)


def test_build_output_path_uses_timestamp_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return cls(2026, 8, 17, 12, 34, 56)

    monkeypatch.setattr("qianiu_auto_report.order_export_gui.datetime", _FixedDatetime)
    fake = type("FakeWindow", (), {"output_dir": tmp_path})()

    output = OrderExportWindow._build_output_path(fake)

    assert output == tmp_path / "天猫订单汇总_20260817_123456.xlsx"


class _ImmediateWindow:
    def after(self, _delay: int, callback, *args: object) -> None:
        callback(*args)


def test_process_worker_summarizes_entire_input_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_file = tmp_path / "orders.xlsx"
    input_file.write_bytes(b"placeholder")
    output_file = tmp_path / "summary.xlsx"
    calls: list[tuple[Path, Path]] = []

    def fake_save(self, input_path: Path, output_path: Path) -> Path:
        calls.append((input_path, output_path))
        return output_path

    monkeypatch.setattr(
        "qianiu_auto_report.order_export_gui.DataProcessor.save_tmall_sold_order_summary",
        fake_save,
    )

    fake = type("FakeWindow", (), {})()
    fake.output_dir = tmp_path
    fake.window = _ImmediateWindow()
    fake.status_var = _FakeVar()
    fake.logs = []
    fake.append_log = lambda message, tag="": fake.logs.append((message, tag))
    fake._build_output_path = lambda: output_file
    fake.running_states = []
    fake._set_running = lambda running, status="": fake.running_states.append((running, status))

    OrderExportWindow._process_worker(fake, {"input_file": input_file})

    assert calls == [(input_file, output_file)]
    assert fake.status_var.value == "天猫订单汇总表已生成到桌面。"
    assert fake.running_states == [(False, "")]


class _FakeButton:
    def __init__(self) -> None:
        self.state = "normal"

    def config(self, **kwargs: object) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])


class _FakeProgress:
    def __init__(self) -> None:
        self.started = False

    def start(self, _interval: int) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False


def test_set_running_disables_all_actions_including_close() -> None:
    fake = type("FakeWindow", (), {})()
    fake.running = False
    fake.status_var = _FakeVar()
    fake.buttons = [_FakeButton() for _ in range(4)]
    fake.choose_file_button, fake.start_button, fake.close_button, fake.open_output_button = fake.buttons
    fake.progressbar = _FakeProgress()

    OrderExportWindow._set_running(fake, True, "正在处理")

    assert fake.running is True
    assert all(button.state == "disabled" for button in fake.buttons)
    assert fake.progressbar.started is True


def test_close_request_is_ignored_while_processing() -> None:
    fake = type("FakeWindow", (), {})()
    fake.running = True
    fake.status_var = _FakeVar()
    fake.window = type("FakeTkWindow", (), {"destroyed": False})()
    fake.window.destroy = lambda: setattr(fake.window, "destroyed", True)

    OrderExportWindow._on_close(fake)

    assert fake.window.destroyed is False
    assert "处理完成" in fake.status_var.value


def test_close_request_destroys_idle_window() -> None:
    fake = type("FakeWindow", (), {})()
    fake.running = False
    fake.status_var = _FakeVar()
    fake.window = type("FakeTkWindow", (), {"destroyed": False})()
    fake.window.destroy = lambda: setattr(fake.window, "destroyed", True)

    OrderExportWindow._on_close(fake)

    assert fake.window.destroyed is True
