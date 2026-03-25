"""
环境自检脚本。

用途：
1. 检查依赖是否安装
2. 检查关键配置是否完整
3. 检查模板、驱动、输出目录是否可用
"""

from __future__ import annotations

import importlib
import json
import socket
import sys
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from typing import Callable, List, Tuple

from qianiu_auto_report.config import BrowserConfig, ExportConfig, PathConfig, REPORT_TEMPLATE_PATH
from qianiu_auto_report.utils import ensure_directory


CheckResult = Tuple[str, str, str]


def _ok(name: str, detail: str) -> CheckResult:
    return ("OK", name, detail)


def _warn(name: str, detail: str) -> CheckResult:
    return ("WARN", name, detail)


def _fail(name: str, detail: str) -> CheckResult:
    return ("FAIL", name, detail)


def check_python_dependencies() -> List[CheckResult]:
    """
    检查核心依赖包。
    """
    dependencies = ("selenium", "pandas", "openpyxl", "tkinter")
    results: List[CheckResult] = []
    for package in dependencies:
        try:
            importlib.import_module(package)
            results.append(_ok(f"依赖:{package}", "已安装"))
        except Exception as exc:
            results.append(_fail(f"依赖:{package}", f"未安装或不可用: {exc}"))
    return results


def check_runtime_config() -> List[CheckResult]:
    """
    检查运行配置项。
    """
    results: List[CheckResult] = []

    if ExportConfig.EXPORT_URL.strip():
        results.append(_ok("配置:EXPORT_URL", ExportConfig.EXPORT_URL))
    else:
        results.append(_fail("配置:EXPORT_URL", "未配置，无法执行网页导出"))

    if ExportConfig.EXPECTED_URL_PREFIX.strip():
        results.append(_ok("配置:EXPECTED_URL_PREFIX", ExportConfig.EXPECTED_URL_PREFIX))
    else:
        results.append(_warn("配置:EXPECTED_URL_PREFIX", "为空，将按 EXPORT_URL 主机名兜底校验"))

    if ExportConfig.LOGIN_URL.strip():
        results.append(_ok("配置:LOGIN_URL", ExportConfig.LOGIN_URL))
    else:
        results.append(_warn("配置:LOGIN_URL", "为空，默认不主动打开登录页"))

    driver_path = Path(BrowserConfig.CHROMEDRIVER_PATH)
    if driver_path.exists():
        results.append(_ok("驱动:CHROMEDRIVER_PATH", str(driver_path)))
    else:
        results.append(
            _warn(
                "驱动:CHROMEDRIVER_PATH",
                f"路径不存在: {driver_path}（若使用 Selenium Manager 可忽略）",
            )
        )

    if BrowserConfig.CHROME_BINARY_PATH:
        binary_path = Path(BrowserConfig.CHROME_BINARY_PATH)
        if binary_path.exists():
            results.append(_ok("浏览器:CHROME_BINARY_PATH", str(binary_path)))
        else:
            results.append(_warn("浏览器:CHROME_BINARY_PATH", f"路径不存在: {binary_path}"))
    else:
        results.append(_warn("浏览器:CHROME_BINARY_PATH", "未配置，使用系统默认 Chrome"))

    if BrowserConfig.ATTACH_TO_EXISTING_BROWSER:
        results.append(
            _ok("模式:ATTACH_TO_EXISTING_BROWSER", f"已启用（{BrowserConfig.DEBUGGER_ADDRESS}）")
        )
        try:
            host, port_text = BrowserConfig.DEBUGGER_ADDRESS.rsplit(":", 1)
            host = host.strip() or "127.0.0.1"
            port = int(port_text)
            with socket.create_connection((host, port), timeout=1.0):
                results.append(_ok("调试端口", f"{host}:{port} 可连接"))
            endpoint = f"http://{host}:{port}/json/version"
            with urlopen(endpoint, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            browser_name = str(payload.get("Browser", "")).strip()
            websocket_url = str(payload.get("webSocketDebuggerUrl", "")).strip()
            if browser_name and websocket_url:
                results.append(_ok("调试接口", f"{endpoint} 可用（{browser_name}）"))
            else:
                results.append(_warn("调试接口", f"{endpoint} 返回内容异常"))
        except Exception:
            results.append(
                _warn(
                    "调试端口",
                    (
                        f"{BrowserConfig.DEBUGGER_ADDRESS} 不可连接；请先启动 Chrome 远程调试。"
                        " macOS 示例：open -na \"Google Chrome\" --args "
                        "--remote-debugging-port=9222 --user-data-dir=\"$HOME/.qianiu_chrome_profile\""
                    ),
                )
            )
    else:
        results.append(_warn("模式:ATTACH_TO_EXISTING_BROWSER", "未启用，将由程序自行启动浏览器"))

    return results


def check_template_files() -> List[CheckResult]:
    """
    检查模板文件。
    """
    results: List[CheckResult] = []
    preferred_template = PathConfig.TEMPLATE_DIR / "template.xlsx"
    legacy_template = REPORT_TEMPLATE_PATH

    if preferred_template.exists():
        results.append(_ok("模板:template.xlsx", str(preferred_template)))
    elif legacy_template.exists():
        results.append(_ok("模板:report_template.xlsx", str(legacy_template)))
    else:
        results.append(
            _fail(
                "模板文件",
                f"未找到 template.xlsx 或 report_template.xlsx（目录: {PathConfig.TEMPLATE_DIR}）",
            )
        )
    return results

def check_output_directories() -> List[CheckResult]:
    """
    检查输出目录是否可创建、可写。
    """
    targets = (
        ("下载目录", Path(ExportConfig.DOWNLOAD_DIR)),
        ("处理中间目录", PathConfig.PROCESSED_DIR),
        ("报表输出目录", PathConfig.REPORT_OUTPUT_DIR),
        ("日志目录", PathConfig.LOG_DIR),
    )

    results: List[CheckResult] = []
    for label, directory in targets:
        try:
            ensure_directory(directory)
            probe_file = directory / ".write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            results.append(_ok(f"目录:{label}", str(directory)))
        except Exception as exc:
            results.append(_fail(f"目录:{label}", f"不可写或不可创建: {exc}"))
    return results


def run_checks() -> List[CheckResult]:
    """
    执行所有检查项。
    """
    checks: List[Callable[[], List[CheckResult]]] = [
        check_python_dependencies,
        check_runtime_config,
        check_template_files,
        check_output_directories,
    ]
    all_results: List[CheckResult] = []
    for checker in checks:
        all_results.extend(checker())
    return all_results


def print_report(results: List[CheckResult]) -> int:
    """
    打印检查报告并返回退出码。
    """
    fail_count = 0
    warn_count = 0

    print("=== 千牛自动报表环境自检 ===")
    for status, name, detail in results:
        print(f"[{status:<4}] {name} - {detail}")
        if status == "FAIL":
            fail_count += 1
        elif status == "WARN":
            warn_count += 1

    print("\n--- 汇总 ---")
    print(f"FAIL: {fail_count}")
    print(f"WARN: {warn_count}")
    print(f"TOTAL: {len(results)}")

    if fail_count > 0:
        print("结论: 环境未就绪，请先修复 FAIL 项。")
        return 1
    print("结论: 环境可用。")
    return 0


def main() -> int:
    """
    自检入口。
    """
    results = run_checks()
    return print_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
