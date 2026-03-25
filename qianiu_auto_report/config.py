"""
项目配置模块。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path


class PathConfig:
    """
    路径配置。
    """

    BASE_DIR = Path(__file__).resolve().parent.parent
    PACKAGE_DIR = Path(__file__).resolve().parent

    ASSETS_DIR = PACKAGE_DIR / "assets"
    DRIVERS_DIR = PACKAGE_DIR / "drivers"
    OUTPUT_ROOT_DIR = PACKAGE_DIR / "output"
    DOWNLOAD_DIR = OUTPUT_ROOT_DIR / "raw"
    PROCESSED_DIR = OUTPUT_ROOT_DIR / "processed"
    REPORT_OUTPUT_DIR = OUTPUT_ROOT_DIR / "excel"
    LOG_DIR = PACKAGE_DIR / "logs"
    TEMPLATE_DIR = PACKAGE_DIR / "templates"


class BrowserConfig:
    """
    浏览器配置。
    """

    DEFAULT_BROWSER = "chrome"
    DEFAULT_TIMEOUT = 20
    WINDOW_SIZE = "1366,900"
    HEADLESS = False

    # 可通过环境变量覆盖浏览器路径，便于多环境切换
    CHROME_BINARY_PATH = os.getenv("QIANNIU_CHROME_BINARY_PATH", "").strip()
    # 固定用户目录用于复用登录态，减少触发滑块验证
    CHROME_USER_DATA_DIR = Path(
        os.getenv("QIANNIU_CHROME_USER_DATA_DIR", str(Path.home() / ".qianiu_chrome_profile"))
    ).expanduser()
    CHROME_PROFILE_DIRECTORY = os.getenv("QIANNIU_CHROME_PROFILE_DIRECTORY", "Default").strip()
    # 是否附着到已打开浏览器（需Chrome开启远程调试端口）
    ATTACH_TO_EXISTING_BROWSER = os.getenv("QIANNIU_ATTACH_TO_EXISTING_BROWSER", "1").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "on",
    }
    DEBUGGER_ADDRESS = os.getenv("QIANNIU_DEBUGGER_ADDRESS", "127.0.0.1:9222").strip()

    _default_driver_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
    CHROMEDRIVER_PATH = Path(
        os.getenv(
            "QIANNIU_CHROMEDRIVER_PATH",
            str(PathConfig.DRIVERS_DIR / _default_driver_name),
        )
    ).expanduser()


class DateConfig:
    """
    日期配置。
    """

    DATE_FORMAT = "%Y-%m-%d"
    DEFAULT_OFFSET_DAYS = 1

    @classmethod
    def default_report_date(cls, now: date | datetime | None = None) -> date:
        """
        获取默认报表日期，默认取前一天。
        """
        if now is None:
            base_date = date.today()
        elif isinstance(now, datetime):
            base_date = now.date()
        else:
            base_date = now

        return base_date - timedelta(days=cls.DEFAULT_OFFSET_DAYS)

    @classmethod
    def default_report_date_str(cls, now: date | datetime | None = None) -> str:
        """
        获取默认报表日期字符串，格式为 YYYY-MM-DD。
        """
        return cls.default_report_date(now=now).strftime(cls.DATE_FORMAT)


class ExportConfig:
    """
    网页导出配置。
    """

    LOGIN_URL = ""
    EXPORT_URL = "https://myseller.taobao.com/home.htm/QnworkbenchHome/"
    EXPORT_LIST_URL = "https://myseller.taobao.com/home.htm/trade-platform/refund-list/export-list"
    ACCOUNT_DETAILS_URL = "https://myseller.taobao.com/home.htm/whale-accountant/bill/account-details"
    BILL_SUMMARY_URL = (
        "https://myseller.taobao.com/home.htm/whale-accountant/bill/summary?"
        "billType=day&billDirection=expense"
    )
    EXPECTED_URL_PREFIX = "https://myseller.taobao.com/"
    ASSUME_LOGGED_IN = False
    DOWNLOAD_DIR = Path(
        os.getenv("QIANNIU_DOWNLOAD_DIR", str(Path.home() / "Desktop"))
    ).expanduser()
    DOWNLOAD_WAIT_SECONDS = 30
    # 测试模式：跳过“退款管理页面自动操作”，直接读取下载目录最新 Excel
    # 设为 False 可恢复完整网页自动化流程
    SKIP_REFUND_MANAGE_ACTIONS = os.getenv("QIANNIU_SKIP_REFUND_MANAGE_ACTIONS", "1").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "on",
    }
    # 简化联调模式：可按需跳过数据处理
    SKIP_DATA_PROCESS = os.getenv("QIANNIU_SKIP_DATA_PROCESS", "1").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "on",
    }
    # 默认保留 Excel 写入（输出到桌面），设置为 1/true 可临时跳过
    SKIP_EXCEL_WRITE = os.getenv("QIANNIU_SKIP_EXCEL_WRITE", "0").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "on",
    }
    INTERACTION_DELAY_SECONDS = float(os.getenv("QIANNIU_INTERACTION_DELAY_SECONDS", "0.12"))
    UI_POLL_INTERVAL_SECONDS = float(os.getenv("QIANNIU_UI_POLL_INTERVAL_SECONDS", "0.25"))
    EXPORT_LIST_SWITCH_TIMEOUT_SECONDS = int(os.getenv("QIANNIU_EXPORT_LIST_SWITCH_TIMEOUT_SECONDS", "90"))
    REPORT_READY_TIMEOUT_SECONDS = int(os.getenv("QIANNIU_REPORT_READY_TIMEOUT_SECONDS", "900"))
    REPORT_READY_POLL_INTERVAL_SECONDS = float(
        os.getenv("QIANNIU_REPORT_READY_POLL_INTERVAL_SECONDS", "1.2")
    )


class ExcelConfig:
    """
    Excel 输出配置。
    """

    DEFAULT_SHEET_NAME = "Report"
    HEADER_ROW_INDEX = 1
    START_ROW_INDEX = 2
    TEMPLATE_FILENAME = "template.xlsx"


# 应用元信息
APP_NAME = "qianiu_auto_report"
APP_VERSION = "0.1.0"

# 兼容旧代码常量导出
BASE_DIR = PathConfig.BASE_DIR
PACKAGE_DIR = PathConfig.PACKAGE_DIR

ASSETS_DIR = PathConfig.ASSETS_DIR
DRIVERS_DIR = PathConfig.DRIVERS_DIR
OUTPUT_DIR = PathConfig.OUTPUT_ROOT_DIR
RAW_OUTPUT_DIR = PathConfig.DOWNLOAD_DIR
PROCESSED_OUTPUT_DIR = PathConfig.PROCESSED_DIR
EXCEL_OUTPUT_DIR = PathConfig.REPORT_OUTPUT_DIR
LOG_DIR = PathConfig.LOG_DIR
TEMPLATE_DIR = PathConfig.TEMPLATE_DIR

DEFAULT_BROWSER = BrowserConfig.DEFAULT_BROWSER
DEFAULT_TIMEOUT = BrowserConfig.DEFAULT_TIMEOUT
DEFAULT_WINDOW_SIZE = BrowserConfig.WINDOW_SIZE
CHROME_BINARY_PATH = BrowserConfig.CHROME_BINARY_PATH
CHROME_USER_DATA_DIR = BrowserConfig.CHROME_USER_DATA_DIR
CHROME_PROFILE_DIRECTORY = BrowserConfig.CHROME_PROFILE_DIRECTORY
ATTACH_TO_EXISTING_BROWSER = BrowserConfig.ATTACH_TO_EXISTING_BROWSER
DEBUGGER_ADDRESS = BrowserConfig.DEBUGGER_ADDRESS
CHROMEDRIVER_PATH = BrowserConfig.CHROMEDRIVER_PATH

APP_ICON_PATH = ASSETS_DIR / "icons" / "app.ico"
REPORT_TEMPLATE_PATH = TEMPLATE_DIR / "report_template.xlsx"
LOG_FILE_PATH = LOG_DIR / "app.log"
