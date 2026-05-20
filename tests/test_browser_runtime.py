"""
浏览器运行时辅助逻辑回归测试。
"""

from __future__ import annotations

from qianiu_auto_report.browser_runtime import (
    driver_matches_browser_major,
    extract_chrome_major_version,
    summarize_technical_error,
)


def test_extract_chrome_major_version_accepts_browser_and_driver_text() -> None:
    """
    Chrome DevTools 与 chromedriver --version 的格式不同，但都应能提取主版本。
    """
    assert extract_chrome_major_version("Chrome/148.0.7778.168") == 148
    assert extract_chrome_major_version("Google Chrome 148.0.7778.168") == 148
    assert extract_chrome_major_version("ChromeDriver 147.0.7727.117") == 147
    assert extract_chrome_major_version("not a chrome version") is None


def test_driver_matches_browser_major_rejects_known_mismatch() -> None:
    """
    已知主版本不一致时应跳过旧 chromedriver，让 Selenium Manager 接管。
    """
    assert (
        driver_matches_browser_major(
            driver_version_text="ChromeDriver 147.0.7727.117",
            browser_version_text="Chrome/148.0.7778.168",
        )
        is False
    )
    assert (
        driver_matches_browser_major(
            driver_version_text="ChromeDriver 148.0.7778.168",
            browser_version_text="Chrome/148.0.7778.168",
        )
        is True
    )
    assert (
        driver_matches_browser_major(
            driver_version_text="unrecognized",
            browser_version_text="Chrome/148.0.7778.168",
        )
        is True
    )


def test_summarize_technical_error_keeps_chromedriver_mismatch_instead_of_stack_tail() -> None:
    """
    GUI 技术细节不能只展示 GetHandleVerifier 这种底层堆栈尾巴。
    """
    traceback_text = """
RuntimeError: 附着已打开浏览器失败。
Driver 细节：Message: session not created: This version of ChromeDriver only supports Chrome version 147
Current browser version is 148.0.7778.168 with binary path /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
Stacktrace:
    chromedriver!GetHandleVerifier [0x7ff77fb980b4+1ef]
"""

    assert (
        summarize_technical_error(traceback_text)
        == "Chrome/ChromeDriver 主版本不一致：ChromeDriver 147，Chrome 148。"
    )


def test_summarize_technical_error_keeps_debug_port_failure_context() -> None:
    """
    端口不可连时应展示真正原因，不展示 macOS 启动命令尾行。
    """
    traceback_text = """
RuntimeError: 附着已打开浏览器失败：调试端口不可连接。
当前配置：127.0.0.1:9222
macOS 启动命令：
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.qianiu_chrome_profile"
"""

    assert (
        summarize_technical_error(traceback_text)
        == "附着已打开浏览器失败：调试端口不可连接。当前配置：127.0.0.1:9222"
    )
