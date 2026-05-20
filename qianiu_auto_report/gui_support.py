"""
GUI 文案与展示辅助函数。
"""

from __future__ import annotations

import os
import platform
from pathlib import PurePosixPath, PureWindowsPath
from pathlib import Path


def format_platform_label(platform: str) -> str:
    """
    将内部平台值转换为更适合界面展示的文案。
    """
    normalized = (platform or "").strip().lower()
    return {
        "auto": "自动识别",
        "taobao": "淘宝",
        "douyin": "抖音",
    }.get(normalized, "自动识别")


def normalize_platform_selection(value: str) -> str:
    """
    将界面上显示的平台选项映射回内部平台值。
    """
    normalized = (value or "").strip().lower()
    if normalized in {"auto", "自动识别"}:
        return "auto"
    if normalized in {"taobao", "淘宝", "淘宝 / 天猫", "天猫"}:
        return "taobao"
    if normalized in {"douyin", "抖音"}:
        return "douyin"
    return "auto"


def format_attach_mode_label(attach_mode: bool) -> str:
    """
    将浏览器连接方式转换为更直白的界面文案。
    """
    _ = attach_mode
    return "9222 工作浏览器"


def format_output_dir_label(output_dir: Path | str) -> str:
    """
    输出目录用于界面展示时的短文案。
    """
    path = Path(output_dir).expanduser()
    desktop = Path.home() / "Desktop"
    if path == desktop:
        return "桌面"
    return str(path)


def resolve_chrome_executable(
    *,
    system_name: str | None = None,
    chrome_binary_path: str = "",
) -> str:
    """
    解析用于启动工作浏览器的 Chrome 可执行文件。
    """
    configured = chrome_binary_path.strip()
    if configured:
        return configured

    system = system_name or platform.system()
    if system == "Windows":
        env = os.environ
        candidates = []
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = env.get(key, "").strip()
            if root:
                candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "chrome"

    if system == "Linux":
        return "google-chrome"

    if system == "Darwin":
        default_macos_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if default_macos_chrome.exists():
            return str(default_macos_chrome)
        return str(default_macos_chrome)

    return "Google Chrome"


def build_work_browser_command(
    *,
    system_name: str | None = None,
    home_dir: Path | str | None = None,
    chrome_binary_path: str = "",
) -> list[str]:
    """
    构造唤起 9222 工作浏览器的系统命令。
    """
    system = system_name or platform.system()
    if home_dir is None:
        home = Path.home()
    elif system == "Windows":
        home = PureWindowsPath(home_dir)
    elif system in {"Darwin", "Linux"}:
        home = PurePosixPath(home_dir)
    else:
        home = Path(home_dir)
    profile_dir = str(home / ".qianiu_chrome_profile")
    args = [
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}",
    ]

    if system == "Darwin":
        executable = resolve_chrome_executable(
            system_name=system,
            chrome_binary_path=chrome_binary_path,
        )
        return [executable, *args]

    if system == "Windows":
        executable = resolve_chrome_executable(
            system_name=system,
            chrome_binary_path=chrome_binary_path,
        )
        return ["cmd", "/c", "start", "", executable, *args]

    executable = resolve_chrome_executable(
        system_name=system,
        chrome_binary_path=chrome_binary_path,
    )
    return [executable, *args]
