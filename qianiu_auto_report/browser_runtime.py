"""
浏览器运行时辅助逻辑。
"""

from __future__ import annotations

import re


def extract_chrome_major_version(text: str) -> int | None:
    """
    从 Chrome / ChromeDriver 版本文本中提取主版本号。
    """
    match = re.search(r"\b(\d{2,3})\.\d+\.\d+\.\d+\b", text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def driver_matches_browser_major(
    *,
    driver_version_text: str,
    browser_version_text: str,
) -> bool:
    """
    判断 chromedriver 与当前 Chrome 主版本是否匹配。

    无法识别任一版本时返回 True，交给 Selenium 自身继续处理。
    """
    driver_major = extract_chrome_major_version(driver_version_text)
    browser_major = extract_chrome_major_version(browser_version_text)
    if driver_major is None or browser_major is None:
        return True
    return driver_major == browser_major


def summarize_technical_error(error_text: str) -> str:
    """
    从完整异常堆栈中提取适合 GUI 展示的一行技术细节。
    """
    text = (error_text or "").strip()
    if not text:
        return ""

    mismatch = _summarize_driver_mismatch(text)
    if mismatch:
        return mismatch

    lines = [_clean_trace_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    for index, line in enumerate(lines):
        if "附着已打开浏览器失败：调试端口不可连接" in line:
            details = [line]
            if index + 1 < len(lines) and lines[index + 1].startswith("当前配置："):
                details.append(lines[index + 1])
            return "".join(details)

    priority_markers = (
        "附着已打开浏览器失败",
        "无法自动判定平台",
        "ModuleNotFoundError",
        "No module named",
        "TimeoutException",
        "RuntimeError",
        "WebDriverException",
        "session not created",
        "This version of ChromeDriver",
    )
    for line in lines:
        if any(marker in line for marker in priority_markers):
            return line

    for line in reversed(lines):
        if "GetHandleVerifier" in line or line.lower().startswith("stacktrace"):
            continue
        return line
    return lines[-1] if lines else ""


def _summarize_driver_mismatch(text: str) -> str:
    """
    提取 ChromeDriver 与 Chrome 主版本不一致的常见报错。
    """
    driver_match = re.search(r"only supports Chrome version\s+(\d+)", text, re.IGNORECASE)
    browser_match = re.search(r"Current browser version is\s+(\d+)", text, re.IGNORECASE)
    if not driver_match or not browser_match:
        return ""
    return (
        "Chrome/ChromeDriver 主版本不一致："
        f"ChromeDriver {driver_match.group(1)}，Chrome {browser_match.group(1)}。"
    )


def _clean_trace_line(line: str) -> str:
    """
    清理 traceback 行首噪声。
    """
    value = (line or "").strip()
    if not value:
        return ""
    value = re.sub(r"^(?:RuntimeError|Exception|WebDriverException):\s*", "", value)
    return value.strip()
