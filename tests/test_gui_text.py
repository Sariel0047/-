"""
GUI 文案与展示格式回归测试。
"""

from __future__ import annotations

from pathlib import Path

from qianiu_auto_report.gui_support import (
    build_work_browser_command,
    format_attach_mode_label,
    format_output_dir_label,
    format_platform_label,
    normalize_platform_selection,
)


def test_format_platform_label_uses_user_friendly_words() -> None:
    """
    平台下拉对应的展示文案应对非技术用户更友好。
    """
    assert format_platform_label("auto") == "自动识别"
    assert format_platform_label("taobao") == "淘宝"
    assert format_platform_label("douyin") == "抖音"


def test_normalize_platform_selection_accepts_friendly_labels() -> None:
    """
    下拉框显示友好文案时，仍应能正确映射回内部平台值。
    """
    assert normalize_platform_selection("自动识别") == "auto"
    assert normalize_platform_selection("淘宝") == "taobao"
    assert normalize_platform_selection("淘宝 / 天猫") == "taobao"
    assert normalize_platform_selection("抖音") == "douyin"


def test_format_attach_mode_label_reads_like_a_plain_sentence() -> None:
    """
    连接方式提示应使用易懂文案，而不是内部配置名。
    """
    assert format_attach_mode_label(True) == "9222 工作浏览器"
    assert format_attach_mode_label(False) == "9222 工作浏览器"


def test_format_output_dir_label_prefers_short_desktop_name() -> None:
    """
    输出目录若为桌面，应优先显示“桌面”，避免把长路径堆到界面里。
    """
    assert format_output_dir_label(Path.home() / "Desktop") == "桌面"
    assert format_output_dir_label(Path("/tmp/custom-output")) == "/tmp/custom-output"


def test_build_work_browser_command_uses_exact_macos_debug_chrome_shape() -> None:
    """
    macOS 只负责执行用户指定的 9222 Chrome 启动命令。
    """
    command = build_work_browser_command(system_name="Darwin", home_dir=Path("/Users/demo"))

    assert command == [
        "open",
        "-na",
        "Google Chrome",
        "--args",
        "--remote-debugging-port=9222",
        "--user-data-dir=/Users/demo/.qianiu_chrome_profile",
    ]


def test_build_work_browser_command_uses_windows_start_command() -> None:
    """
    Windows 下用系统 start 命令唤起 Chrome，并带上同样的 9222 参数。
    """
    command = build_work_browser_command(system_name="Windows", home_dir=Path("C:/Users/demo"))

    assert command[:5] == ["cmd", "/c", "start", "", "chrome"]
    assert "--remote-debugging-port=9222" in command
    assert "--user-data-dir=C:/Users/demo/.qianiu_chrome_profile" in command
