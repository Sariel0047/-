"""
网页自动导出模块。
"""

from __future__ import annotations

import json
import re
import socket
import time
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from qianiu_auto_report.config import (
    ATTACH_TO_EXISTING_BROWSER,
    CHROME_BINARY_PATH,
    CHROME_PROFILE_DIRECTORY,
    CHROME_USER_DATA_DIR,
    CHROMEDRIVER_PATH,
    DateConfig,
    DEBUGGER_ADDRESS,
    DEFAULT_TIMEOUT,
    DEFAULT_WINDOW_SIZE,
    ExportConfig,
)
from qianiu_auto_report.utils import safe_log, snapshot_directory, wait_for_download_complete


Locator = Tuple[str, str]


class WebExporter:
    """
    Selenium 网页导出器。
    """

    DEFAULT_SELECTORS: dict[str, tuple[Locator, ...]] = {
        "trade_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-trade']"),
            (By.CSS_SELECTOR, "a[title='交易']"),
            (By.CSS_SELECTOR, "span[title='交易']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='交易']"),
        ),
        "refund_manage_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-refund-manage']"),
            (By.CSS_SELECTOR, "a[title='退款管理']"),
            (By.CSS_SELECTOR, "span[title='退款管理']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='退款管理']"),
        ),
        "switch_standard_button": (
            (By.CSS_SELECTOR, "[data-testid='switch-standard']"),
            (By.CSS_SELECTOR, "a[title='切换标准版']"),
            (By.CSS_SELECTOR, "button[title='切换标准版']"),
            (By.XPATH, "//*[self::a or self::button or self::span][contains(normalize-space(),'切换标准版')]"),
        ),
        "finance_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-finance']"),
            (By.CSS_SELECTOR, "a[title='财务']"),
            (By.CSS_SELECTOR, "span[title='财务']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='财务']"),
        ),
        "promotion_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-promotion']"),
            (By.CSS_SELECTOR, "a[title='推广']"),
            (By.CSS_SELECTOR, "span[title='推广']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='推广']"),
        ),
        "reconciliation_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-reconciliation']"),
            (By.CSS_SELECTOR, "a[title='对账管理']"),
            (By.CSS_SELECTOR, "span[title='对账管理']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='对账管理']"),
        ),
        "account_details_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-account-details']"),
            (By.CSS_SELECTOR, "a[title='账户明细']"),
            (By.CSS_SELECTOR, "span[title='账户明细']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='账户明细']"),
        ),
        "bill_summary_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-bill-summary']"),
            (By.CSS_SELECTOR, "a[title='收支账单']"),
            (By.CSS_SELECTOR, "span[title='收支账单']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='收支账单']"),
        ),
        "corner_popup_close": (
            (By.CSS_SELECTOR, "button[aria-label*='关闭']"),
            (By.CSS_SELECTOR, "button[title*='关闭']"),
            (By.CSS_SELECTOR, "[role='dialog'] button"),
            (By.CSS_SELECTOR, "[class*='notice'] button"),
            (By.CSS_SELECTOR, "[class*='message'] button"),
            (By.CSS_SELECTOR, "[class*='message'] [class*='close']"),
            (By.CSS_SELECTOR, "[class*='popup'] [class*='close']"),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'重要消息')]/ancestor::*[self::div or self::section][1]"
                "//*[self::button or self::span or self::i]"
                "[contains(@class,'close') or contains(@aria-label,'关闭') or contains(@title,'关闭')"
                " or normalize-space()='×' or normalize-space()='✕' or normalize-space()='x' or normalize-space()='X']",
            ),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'重要消息')]/ancestor::*[self::div or self::section][1]"
                "//*[self::button or self::span or self::i][normalize-space()='×' or normalize-space()='✕']",
            ),
        ),
        "combined_query_button": (
            (By.CSS_SELECTOR, "button[data-testid='combined-query']"),
            (By.CSS_SELECTOR, "button[title='组合查询']"),
            (By.CSS_SELECTOR, "button[aria-label='组合查询']"),
        ),
        "status_dropdown": (
            (By.CSS_SELECTOR, "[data-testid='after-sale-status']"),
            (By.CSS_SELECTOR, "[data-name='after-sale-status']"),
            (By.CSS_SELECTOR, "input[placeholder*='售后状态']"),
            (By.CSS_SELECTOR, "[aria-label*='售后状态']"),
            (
                By.XPATH,
                "//*[self::div or self::span or self::label][contains(normalize-space(),'售后状态')]",
            ),
        ),
        "status_tag_refund_success": (
            (By.CSS_SELECTOR, "[data-testid='tag-refund-success']"),
            (By.CSS_SELECTOR, "span[title='退款成功']"),
            (By.CSS_SELECTOR, "label[title='退款成功']"),
            (By.CSS_SELECTOR, "li[title='退款成功']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='退款成功']"),
        ),
        "status_tag_in_progress": (
            (By.CSS_SELECTOR, "[data-testid='tag-in-progress']"),
            (By.CSS_SELECTOR, "span[title='进行中的订单']"),
            (By.CSS_SELECTOR, "label[title='进行中的订单']"),
            (By.CSS_SELECTOR, "li[title='进行中的订单']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='进行中的订单']"),
        ),
        "status_refund_success_option": (
            (By.CSS_SELECTOR, "li[title='退款成功']"),
            (By.CSS_SELECTOR, "li[data-value='退款成功']"),
            (By.CSS_SELECTOR, "div[title='退款成功']"),
            (By.CSS_SELECTOR, "span[title='退款成功']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='退款成功']"),
        ),
        "status_in_progress_option": (
            (By.CSS_SELECTOR, "li[title='进行中的订单']"),
            (By.CSS_SELECTOR, "li[data-value='进行中的订单']"),
            (By.CSS_SELECTOR, "div[title='进行中的订单']"),
            (By.CSS_SELECTOR, "span[title='进行中的订单']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='进行中的订单']"),
        ),
        "search_button": (
            (By.CSS_SELECTOR, "button[data-testid='search']"),
            (By.CSS_SELECTOR, "button[aria-label='搜索']"),
            (By.CSS_SELECTOR, "button[title='搜索']"),
            (By.XPATH, "//button[normalize-space()='搜索售后单']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'搜索售后单')]",
            ),
        ),
        "batch_export_button": (
            (By.CSS_SELECTOR, "button[data-testid='batch-export']"),
            (By.CSS_SELECTOR, "button[aria-label='批量导出']"),
            (By.CSS_SELECTOR, "button[title='批量导出']"),
            (By.XPATH, "//button[normalize-space()='批量导出']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'批量导出')]",
            ),
        ),
        "generate_report_button": (
            (By.CSS_SELECTOR, "button[data-testid='generate-report']"),
            (By.CSS_SELECTOR, "button[aria-label='生成报表']"),
            (By.CSS_SELECTOR, "button[title='生成报表']"),
            (By.XPATH, "//button[normalize-space()='生成报表']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'生成报表')]",
            ),
        ),
        "confirm_button": (
            (By.CSS_SELECTOR, "button[data-testid='confirm']"),
            (By.CSS_SELECTOR, "button[aria-label='确认']"),
            (By.CSS_SELECTOR, "button[title='确认']"),
            (By.XPATH, "//button[normalize-space()='确认']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'确认')]",
            ),
        ),
        "view_generated_report_button": (
            (By.CSS_SELECTOR, "button[data-testid='view-generated-report']"),
            (By.CSS_SELECTOR, "button[aria-label='查看已生成报表']"),
            (By.CSS_SELECTOR, "button[title='查看已生成报表']"),
            (By.XPATH, "//button[normalize-space()='查看已生成报表']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'查看已生成报表')]",
            ),
        ),
        "download_report_button": (
            (By.CSS_SELECTOR, "button[data-testid='download-refund-report']"),
            (By.CSS_SELECTOR, "button[aria-label='下载退款单报表']"),
            (By.CSS_SELECTOR, "button[title='下载退款单报表']"),
            (By.XPATH, "//button[normalize-space()='下载退款单报表']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'下载退款单报表')]",
            ),
        ),
        "account_details_yesterday_button": (
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[1]/div/div/div[2]/label[1]",
            ),
            (By.XPATH, "//button[normalize-space()='昨天']"),
            (By.XPATH, "//*[self::button or self::span or self::div or self::a][normalize-space()='昨天']"),
            (By.XPATH, "//*[contains(@class,'btn') and normalize-space()='昨天']"),
        ),
        "account_details_reason_dropdown": (
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]/div/span/span[1]",
            ),
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]/div/span/span[2]",
            ),
            (
                By.XPATH,
                "//*[self::div or self::span][contains(normalize-space(),'原因') and contains(normalize-space(),'请选择')]",
            ),
            (
                By.XPATH,
                "//*[self::label or self::span][normalize-space()='原因']/following::*[self::div or self::span][1]",
            ),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'原因') and (contains(normalize-space(),'请选择') or contains(normalize-space(),'交易赔付'))]",
            ),
        ),
        "bill_summary_date_picker_control": (
            (
                By.XPATH,
                "//*[@id='wui-page']/div/div[2]/div/div[2]/div/div/div[2]/div/div/div[2]/form/div/div[1]/div/div",
            ),
        ),
        "bill_summary_business_dropdown_control": (
            (
                By.XPATH,
                "//*[@id='wui-page']/div/div[2]/div/div[2]/div/div/div[2]/div/div/div[2]/form/div/div[4]/div/div",
            ),
        ),
        "bill_summary_business_cross_border_option": (
            (
                By.XPATH,
                "//*[@id='qn-worbench-container']/div[2]/div/ul/li[5]/div/span",
            ),
            (
                By.XPATH,
                "//*[self::li or self::div or self::span][normalize-space()='淘宝天猫跨境服务增值费']",
            ),
            (
                By.XPATH,
                "//*[self::li or self::div or self::span][contains(normalize-space(),'淘宝天猫跨境服务增值费')]",
            ),
        ),
        "account_details_reason_trade_compensation": (
            (
                By.XPATH,
                "/html/body/div[4]/div/div/ul/li[5]/div/div/div",
            ),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='交易赔付']"),
            (
                By.XPATH,
                "//*[self::li or self::div or self::span][contains(normalize-space(),'交易赔付')]",
            ),
        ),
        "account_details_search_button": (
            (By.XPATH, "//button[normalize-space()='搜索']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::div or self::span][contains(normalize-space(),'搜索')]",
            ),
        ),
        "wanxiangtai_ai_entry": (
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'万相台') and contains(normalize-space(),'无界')]",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'万象台') and contains(normalize-space(),'无界')]",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'万相台AI无界') or contains(normalize-space(),'万象台AI无界')]",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'万相台ai无界') or contains(normalize-space(),'万象台ai无界')]",
            ),
        ),
        "promotion_report_tab": (
            (By.XPATH, "//*[self::a or self::button or self::div or self::span][normalize-space()='报表']"),
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'报表')]",
            ),
        ),
        "promotion_audience_report_menu": (
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span][normalize-space()='人群报表']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::div or self::span]"
                "[contains(normalize-space(),'人群报表')]",
            ),
        ),
        "promotion_summary_period_dropdown": (
            (
                By.XPATH,
                "//*[contains(normalize-space(),'数据汇总周期')]/following::*[self::div or self::span][1]",
            ),
            (
                By.XPATH,
                "//*[self::div or self::span][contains(normalize-space(),'数据汇总周期')]",
            ),
        ),
        "promotion_summary_period_yesterday_option": (
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='昨日']"),
            (By.XPATH, "//*[self::li or self::div or self::span][contains(normalize-space(),'昨日')]"),
        ),
        "promotion_mask_close": (
            (By.CSS_SELECTOR, "[class*='mask'] [class*='close']"),
            (By.CSS_SELECTOR, "[class*='modal'] [class*='close']"),
            (By.CSS_SELECTOR, "[class*='dialog'] [class*='close']"),
            (
                By.XPATH,
                "//*[self::button or self::span]"
                "[normalize-space()='关闭' or normalize-space()='我知道了' or normalize-space()='知道了']",
            ),
        ),
        "common_search_button": (
            (By.XPATH, "//button[normalize-space()='搜索']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span][contains(normalize-space(),'搜索')]",
            ),
        ),
    }

    STATUS_SELECTOR_KEY_MAP: dict[str, tuple[str, ...]] = {
        "退款成功": ("status_tag_refund_success", "status_refund_success_option"),
        "进行中的订单": ("status_tag_in_progress", "status_in_progress_option"),
    }

    def __init__(
        self,
        login_url: Optional[str] = None,
        export_url: Optional[str] = None,
        export_list_url: Optional[str] = None,
        assume_logged_in: Optional[bool] = None,
        attach_to_existing_browser: Optional[bool] = None,
        debugger_address: Optional[str] = None,
        expected_url_prefix: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        download_wait_seconds: Optional[int] = None,
        selectors: Optional[dict[str, tuple[Locator, ...]]] = None,
        headless: bool = False,
    ) -> None:
        self.login_url = login_url or ExportConfig.LOGIN_URL
        self.export_url = export_url or ExportConfig.EXPORT_URL
        self.export_list_url = export_list_url or ExportConfig.EXPORT_LIST_URL
        self.assume_logged_in = (
            ExportConfig.ASSUME_LOGGED_IN if assume_logged_in is None else assume_logged_in
        )
        self.attach_to_existing_browser = (
            ATTACH_TO_EXISTING_BROWSER
            if attach_to_existing_browser is None
            else attach_to_existing_browser
        )
        self.debugger_address = (debugger_address or DEBUGGER_ADDRESS).strip()
        self.expected_url_prefix = (expected_url_prefix or ExportConfig.EXPECTED_URL_PREFIX).strip()
        self.timeout_seconds = timeout_seconds or DEFAULT_TIMEOUT
        self.download_wait_seconds = download_wait_seconds or ExportConfig.DOWNLOAD_WAIT_SECONDS
        self.selectors = selectors or self.DEFAULT_SELECTORS
        self.headless = headless
        self.interaction_delay_seconds = max(float(ExportConfig.INTERACTION_DELAY_SECONDS), 0.0)
        self.ui_poll_interval_seconds = max(float(ExportConfig.UI_POLL_INTERVAL_SECONDS), 0.05)
        self.export_list_switch_timeout_seconds = max(
            int(ExportConfig.EXPORT_LIST_SWITCH_TIMEOUT_SECONDS), 10
        )
        self.report_ready_timeout_seconds = max(int(ExportConfig.REPORT_READY_TIMEOUT_SECONDS), 60)
        self.report_ready_poll_interval_seconds = max(
            float(ExportConfig.REPORT_READY_POLL_INTERVAL_SECONDS), 0.5
        )

        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.download_dir: Optional[Path] = None
        self._is_attached_session = False

    def _split_debugger_address(self) -> tuple[str, int]:
        """
        解析调试地址为 host 和 port。
        """
        address = (self.debugger_address or "").strip()
        if ":" not in address:
            raise ValueError(
                f"DEBUGGER_ADDRESS 格式错误：{address}，应为 host:port（如 127.0.0.1:9222）。"
            )

        host, port_text = address.rsplit(":", 1)
        host = host.strip() or "127.0.0.1"
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(
                f"DEBUGGER_ADDRESS 端口无效：{address}，应为 host:port（如 127.0.0.1:9222）。"
            ) from exc

        if port <= 0 or port > 65535:
            raise ValueError(f"DEBUGGER_ADDRESS 端口超出范围：{port}")
        return host, port

    def _check_debugger_ready(self) -> None:
        """
        附着前检测调试端口与 Chrome DevTools 接口是否可用。
        """
        host, port = self._split_debugger_address()

        try:
            with socket.create_connection((host, port), timeout=1.5):
                pass
        except OSError as exc:
            raise RuntimeError(
                "附着已打开浏览器失败：调试端口不可连接。"
                f"\n当前配置：{host}:{port}"
                "\n请先用调试模式启动 Chrome，再登录千牛页面。"
                "\nmacOS 启动命令："
                '\nopen -na "Google Chrome" --args --remote-debugging-port=9222 '
                '--user-data-dir="$HOME/.qianiu_chrome_profile"'
            ) from exc

        endpoint = f"http://{host}:{port}/json/version"
        try:
            with urlopen(endpoint, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            raise RuntimeError(
                "附着已打开浏览器失败：调试接口未就绪。"
                f"\n调试接口：{endpoint}"
                "\n请确认你连接的是调试模式 Chrome（而不是普通已打开的 Chrome）。"
            ) from exc

        browser_name = str(payload.get("Browser", "")).strip()
        websocket_url = str(payload.get("webSocketDebuggerUrl", "")).strip()
        if not browser_name or not websocket_url:
            raise RuntimeError(
                "附着已打开浏览器失败：调试接口返回异常。"
                f"\n调试接口：{endpoint}"
                f"\n返回内容：{payload}"
            )

    @staticmethod
    def _normalize_url_prefix(prefix: str) -> str:
        """
        标准化 URL 前缀，统一补齐末尾斜杠。
        """
        value = (prefix or "").strip()
        if not value:
            return ""
        if not value.endswith("/"):
            value = f"{value}/"
        return value

    def _get_expected_host(self) -> str:
        """
        获取期望控制页面的主机名。
        """
        if self.export_url:
            host = urlparse(self.export_url).netloc.strip().lower()
            if host:
                return host
        if self.expected_url_prefix:
            return urlparse(self.expected_url_prefix).netloc.strip().lower()
        return ""

    def _is_expected_url(self, url: str) -> bool:
        """
        判断 URL 是否属于允许控制的页面范围。
        """
        current_url = (url or "").strip()
        if current_url in {"", "about:blank", "data:,"}:
            return False

        current_url_lower = current_url.lower()
        export_url = (self.export_url or "").strip().lower()
        expected_prefix = self._normalize_url_prefix(self.expected_url_prefix).lower()

        if export_url and current_url_lower.startswith(export_url):
            return True
        if expected_prefix and current_url_lower.startswith(expected_prefix):
            return True

        expected_host = self._get_expected_host()
        if not expected_host:
            return True

        current_host = urlparse(current_url).netloc.strip().lower()
        return current_host == expected_host

    def ensure_expected_page_or_switch(self) -> str:
        """
        校验当前窗口是否为目标业务页面，如需要则自动切换至匹配标签页。
        """
        driver = self._ensure_driver()

        checked_urls: list[str] = []
        handles: list[str] = []
        try:
            handles = list(driver.window_handles)
        except Exception:
            handles = []

        if not handles:
            raise RuntimeError("未检测到可用浏览器标签页，请确认浏览器窗口已打开。")

        current_handle = driver.current_window_handle
        ordered_handles = [current_handle, *[item for item in handles if item != current_handle]]

        for handle in ordered_handles:
            try:
                driver.switch_to.window(handle)
                current_url = (driver.current_url or "").strip()
            except Exception:
                continue

            checked_urls.append(current_url or "<空白页面>")
            if self._is_expected_url(current_url):
                return current_url

        target_hint = self.export_url or self.expected_url_prefix or "千牛工作台页面"
        checked_text = " | ".join(checked_urls) if checked_urls else "<未读取到任何 URL>"
        raise RuntimeError(
            "附着模式安全校验失败：未找到允许自动化控制的千牛页面。"
            f"\n已检测页面：{checked_text}"
            f"\n请先手动打开：{target_hint}"
        )

    def get_current_url(self) -> str:
        """
        获取当前标签页 URL。
        """
        driver = self._ensure_driver()
        return (driver.current_url or "").strip()

    def _configure_download_behavior(self) -> None:
        """
        使用 CDP 设置下载目录（附着已有浏览器时优先使用）。
        """
        driver = self._ensure_driver()
        if self.download_dir is None:
            return

        try:
            driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {
                    "behavior": "allow",
                    "downloadPath": str(self.download_dir.resolve()),
                },
            )
        except Exception:
            # 某些 Chrome/Driver 版本可能不支持该命令，忽略后继续使用浏览器默认下载目录。
            pass

    def _ensure_driver(self) -> webdriver.Chrome:
        """
        确保 driver 已初始化。
        """
        if self.driver is None:
            raise RuntimeError("浏览器未初始化，请先调用 init_driver。")
        return self.driver

    def _ensure_wait(self) -> WebDriverWait:
        """
        确保显式等待对象已初始化。
        """
        if self.wait is None:
            raise RuntimeError("WebDriverWait 未初始化，请先调用 init_driver。")
        return self.wait

    def _wait_dom_ready(self) -> None:
        """
        等待页面 DOM 加载完成。
        """
        wait = self._ensure_wait()
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

    def _wait_for_any_clickable(self, selector_key: str) -> WebElement:
        """
        在候选选择器中等待可点击元素。
        """
        wait = self._ensure_wait()
        last_error: Optional[Exception] = None

        for locator in self.selectors.get(selector_key, ()):
            try:
                return wait.until(EC.element_to_be_clickable(locator))
            except Exception as exc:
                last_error = exc
                continue

        raise TimeoutException(f"未找到可点击元素：{selector_key}") from last_error

    def _click_with_retry(self, element: WebElement) -> None:
        """
        点击元素，失败时使用 JavaScript 回退。
        """
        driver = self._ensure_driver()
        try:
            element.click()
            return
        except StaleElementReferenceException:
            raise
        except WebDriverException:
            try:
                driver.execute_script("arguments[0].click();", element)
                return
            except StaleElementReferenceException:
                raise

    def _click_by_text(self, texts: tuple[str, ...]) -> bool:
        """
        通过文本兜底查找按钮并点击。
        """
        wait = self._ensure_wait()

        def _find_clickable_text(driver: webdriver.Chrome) -> WebElement | bool:
            for selector in ("button", "li", "a", "span", "div"):
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        element_text = (element.text or "").strip()
                        if any(text == element_text or text in element_text for text in texts):
                            return element
                    except StaleElementReferenceException:
                        continue
            return False

        for _ in range(3):
            try:
                element = wait.until(_find_clickable_text)
                self._click_with_retry(element)
                return True
            except StaleElementReferenceException:
                time.sleep(0.2)
                continue
            except TimeoutException:
                return False
        return False

    def _try_click_selector(self, selector_key: str) -> bool:
        """
        尝试按选择器点击，找不到时返回 False。
        """
        if not self.selectors.get(selector_key):
            return False
        for _ in range(3):
            try:
                element = self._wait_for_any_clickable(selector_key)
                self._click_with_retry(element)
                return True
            except StaleElementReferenceException:
                time.sleep(0.2)
                continue
            except TimeoutException:
                return False
        return False

    def _has_any_visible_element(self, selector_key: str) -> bool:
        """
        判断候选定位中是否存在可见元素。
        """
        driver = self._ensure_driver()
        for locator in self.selectors.get(selector_key, ()):
            elements = driver.find_elements(*locator)
            for element in elements:
                try:
                    if element.is_displayed():
                        return True
                except StaleElementReferenceException:
                    continue
        return False

    def _page_has_export_controls(self) -> bool:
        """
        判断当前页面是否已处于退款导出页面。
        """
        by_selector = any(
            self._has_any_visible_element(selector_key)
            for selector_key in ("combined_query_button", "status_dropdown", "batch_export_button")
        )
        if by_selector:
            return True

        # 文案兜底：新版页面在不同账户下 class 变化较大，但文本相对稳定
        has_query_text = self._page_contains_text("售后单查询")
        has_search_text = self._page_contains_text("搜索售后单")
        has_export_text = self._page_contains_text("批量导出")
        return has_query_text and (has_search_text or has_export_text)

    def _wait_for_export_controls(self, timeout_seconds: float = 6.0) -> bool:
        """
        等待退款导出相关控件出现，适配 SPA 异步渲染。
        """
        end_time = time.time() + timeout_seconds
        while time.time() < end_time:
            if self._page_has_export_controls():
                return True
            time.sleep(0.2)
        return False

    def _quick_click_any(self, selector_key: str) -> bool:
        """
        快速尝试点击（不走显式等待），适用于可选弹窗等场景。
        """
        driver = self._ensure_driver()
        locators = self.selectors.get(selector_key, ())
        if not locators:
            return False

        for locator in locators:
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue

            for element in elements:
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    self._click_with_retry(element)
                    return True
                except (StaleElementReferenceException, WebDriverException):
                    continue

        return False

    def _page_contains_text(self, text: str) -> bool:
        """
        判断当前页面文本是否包含指定内容。
        """
        driver = self._ensure_driver()
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            return text in (body.text or "")
        except Exception:
            return False

    def _is_export_list_page(self) -> bool:
        """
        判断当前是否已在“退款单导出报表”页面。
        """
        driver = self._ensure_driver()
        current_url = (driver.current_url or "").lower()
        if "refund-list/export-list" in current_url:
            return True
        return self._page_contains_text("退款单导出报表")

    def _close_corner_popup_if_present(self) -> bool:
        """
        关闭右下角消息弹窗（如存在）。
        """
        clicked = False
        for _ in range(3):
            if self._quick_click_any("corner_popup_close"):
                clicked = True
                time.sleep(0.2)
                continue
            break
        return clicked

    def _switch_to_standard_version_if_needed(self) -> bool:
        """
        如当前为非标准版，点击左下角“切换标准版”后等待页面稳定。
        """
        if self._page_contains_text("切换极速版"):
            # 已经是标准版
            return False

        if not self._page_contains_text("切换标准版"):
            return False

        switched = self._quick_click_any("switch_standard_button") or self._click_by_text(("切换标准版",))
        if not switched:
            return False

        self._wait_dom_ready()
        time.sleep(max(self.interaction_delay_seconds * 4.0, 0.15))
        return True

    def _log_step(self, message: str) -> None:
        """
        输出关键步骤日志。
        """
        safe_log(message)

    def _count_visible_matches(self, selector_key: str) -> int:
        """
        统计某组定位在当前页面命中的可见元素数。
        """
        driver = self._ensure_driver()
        count = 0
        for locator in self.selectors.get(selector_key, ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if element.is_displayed():
                        count += 1
                except StaleElementReferenceException:
                    continue
        return count

    def _build_selector_debug_summary(self, selector_keys: tuple[str, ...]) -> str:
        """
        构建选择器命中摘要。
        """
        return "，".join(f"{key}={self._count_visible_matches(key)}" for key in selector_keys)

    def _page_text_snippet(self, max_length: int = 180) -> str:
        """
        提取当前页面正文片段。
        """
        driver = self._ensure_driver()
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            body_text = ""

        normalized = re.sub(r"\s+", " ", body_text).strip()
        if not normalized:
            return "<空白页面>"
        return normalized[:max_length]

    def _raise_timeout_with_context(
        self,
        message: str,
        selector_keys: tuple[str, ...] = (),
        extra_details: tuple[str, ...] = (),
    ) -> None:
        """
        抛出包含当前页面上下文的超时异常。
        """
        details = [message, f"当前URL：{self.get_current_url()}"]
        if selector_keys:
            details.append(f"选择器命中：{self._build_selector_debug_summary(selector_keys)}")
        for detail in extra_details:
            if detail:
                details.append(detail)
        details.append(f"页面片段：{self._page_text_snippet()}")
        raise TimeoutException("\n".join(details))

    def _find_visible_text_elements(
        self,
        texts: tuple[str, ...],
        exact: bool = True,
    ) -> list[WebElement]:
        """
        按文本查找可见元素。
        """
        driver = self._ensure_driver()
        matched: list[WebElement] = []

        for text in texts:
            normalized = (text or "").strip()
            if not normalized:
                continue

            if exact:
                xpath = (
                    "//*[self::a or self::button or self::span or self::div or self::li or self::p]"
                    f"[normalize-space()='{normalized}']"
                )
            else:
                xpath = (
                    "//*[self::a or self::button or self::span or self::div or self::li or self::p]"
                    f"[contains(normalize-space(),'{normalized}')]"
                )

            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue

            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        matched.append(element)
                except StaleElementReferenceException:
                    continue

        return matched

    def _find_left_panel_text_elements(
        self,
        texts: tuple[str, ...],
        exact: bool = True,
        min_left: int = 0,
        max_left: int = 420,
        min_top: int = 90,
    ) -> list[WebElement]:
        """
        在左侧导航区域按文本筛选可见元素，避免误点顶部同名入口。
        """
        candidates = self._find_visible_text_elements(texts=texts, exact=exact)
        filtered: list[tuple[float, float, WebElement]] = []

        for element in candidates:
            try:
                rect = element.rect
                x = float(rect.get("x", -1))
                y = float(rect.get("y", -1))
                width = float(rect.get("width", 0))
                height = float(rect.get("height", 0))
            except Exception:
                continue

            if width < 18 or height < 14:
                continue
            if x < float(min_left) or x > float(max_left):
                continue
            if y < float(min_top):
                continue
            filtered.append((x, y, element))

        filtered.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in filtered]

    def _click_left_panel_text_with_wait(
        self,
        texts: tuple[str, ...],
        exact: bool = True,
        timeout_seconds: float = 10.0,
        required: bool = True,
        step_name: Optional[str] = None,
        min_left: int = 0,
        max_left: int = 420,
        min_top: int = 90,
    ) -> bool:
        """
        在左侧导航区域按文本点击，优先用于主菜单和财务二级菜单。
        """
        end_time = time.time() + max(timeout_seconds, 1.0)
        last_error: Optional[Exception] = None

        while time.time() < end_time:
            elements = self._find_left_panel_text_elements(
                texts=texts,
                exact=exact,
                min_left=min_left,
                max_left=max_left,
                min_top=min_top,
            )
            for element in elements:
                try:
                    self._click_with_retry(element)
                    if step_name:
                        self._log_step(step_name)
                    time.sleep(max(self.interaction_delay_seconds, 0.08))
                    return True
                except (StaleElementReferenceException, WebDriverException) as exc:
                    last_error = exc
                    continue
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))

        if required:
            detail = f"最近异常：{type(last_error).__name__}: {last_error}" if last_error else ""
            self._raise_timeout_with_context(
                f"左侧导航未找到文本按钮：{' / '.join(texts)}",
                extra_details=(detail,),
            )
        return False

    def _click_text_with_wait(
        self,
        texts: tuple[str, ...],
        exact: bool = True,
        timeout_seconds: float = 10.0,
        required: bool = True,
        step_name: Optional[str] = None,
    ) -> bool:
        """
        在限定时间内按文本查找并点击元素。
        """
        end_time = time.time() + max(timeout_seconds, 1.0)
        last_error: Optional[Exception] = None

        while time.time() < end_time:
            for element in self._find_visible_text_elements(texts=texts, exact=exact):
                try:
                    self._click_with_retry(element)
                    if step_name:
                        self._log_step(step_name)
                    time.sleep(max(self.interaction_delay_seconds, 0.08))
                    return True
                except (StaleElementReferenceException, WebDriverException) as exc:
                    last_error = exc
                    continue
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))

        if required:
            detail = f"最近异常：{type(last_error).__name__}: {last_error}" if last_error else ""
            self._raise_timeout_with_context(
                f"未找到文本按钮：{' / '.join(texts)}",
                extra_details=(detail,),
            )
        return False

    def _wait_until(
        self,
        predicate: Callable[[], bool],
        timeout_seconds: float,
        message: str,
        selector_keys: tuple[str, ...] = (),
    ) -> None:
        """
        条件轮询等待，超时时附带页面诊断。
        """
        end_time = time.time() + max(timeout_seconds, 1.0)
        last_error: Optional[Exception] = None

        while time.time() < end_time:
            try:
                if predicate():
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))

        extra_details = ()
        if last_error is not None:
            extra_details = (f"最近异常：{type(last_error).__name__}: {last_error}",)
        self._raise_timeout_with_context(
            message,
            selector_keys=selector_keys,
            extra_details=extra_details,
        )

    def _is_account_details_page(self) -> bool:
        """
        判断当前是否已进入账户明细页面。
        """
        current_url = self.get_current_url().lower()
        if "whale-accountant/bill/account-details" in current_url:
            return True
        if "whale-accountant/index" in current_url:
            return False
        return (
            self._has_any_visible_element("account_details_yesterday_button")
            and self._has_any_visible_element("account_details_reason_dropdown")
            and self._has_any_visible_element("account_details_search_button")
        )

    def _is_bill_summary_page(self) -> bool:
        """
        判断当前是否已进入收支账单页面。
        """
        current_url = self.get_current_url().lower()
        if "whale-accountant/bill/summary" in current_url:
            return True
        if "whale-accountant/index" in current_url:
            return False
        return self._page_contains_text("支出账单") and self._page_contains_text("日汇总")

    def _is_finance_center_page(self) -> bool:
        """
        判断当前是否已进入财务中心（总览）上下文。
        """
        current_url = self.get_current_url().lower()
        if "whale-accountant/index" in current_url:
            return True
        if "whale-accountant/" in current_url and self._page_contains_text("对账管理"):
            return True
        return self._page_contains_text("资金管理") and self._page_contains_text("对账管理")

    def _wait_left_nav_ready(self) -> None:
        """
        等待标准版左侧导航加载完成。
        """
        self._switch_default_content()
        self._wait_until(
            lambda: (
                self._has_any_visible_element("finance_menu")
                or self._page_contains_text("财务")
                or self._page_contains_text("交易")
            ),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="标准版左侧导航未加载完成。",
            selector_keys=("finance_menu", "trade_menu", "switch_standard_button"),
        )

    def _open_finance_reconciliation_menu(self) -> bool:
        """
        点击左侧“财务”，等待默认展开的“对账管理”子菜单出现。
        """
        self._switch_default_content()
        self._close_corner_popup_if_present()
        self._wait_left_nav_ready()

        if self._is_finance_center_page() or self._is_account_details_page() or self._is_bill_summary_page():
            return True

        clicked = self._click_left_panel_text_with_wait(
            ("财务",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已点击左侧菜单：财务",
            min_left=0,
            max_left=130,
            min_top=120,
        )
        if not clicked:
            # 兜底：部分皮肤结构下左侧主菜单 DOM 不稳定，保留原选择器尝试
            clicked = self._try_click_selector("finance_menu")
            if clicked:
                self._log_step("已点击左侧菜单：财务（选择器兜底）")

        if not clicked:
            return False

        self._close_corner_popup_if_present()
        try:
            self._wait_until(
                lambda: (
                    self._is_finance_center_page()
                    or self._is_account_details_page()
                    or self._is_bill_summary_page()
                    or self._page_contains_text("账户明细")
                    or self._page_contains_text("收支账单")
                    or self._page_contains_text("对账管理")
                ),
                timeout_seconds=max(self.timeout_seconds, 10),
                message="点击【财务】后未看到默认展开的对账管理菜单。",
                selector_keys=("finance_menu", "account_details_menu", "bill_summary_menu"),
            )
        except TimeoutException:
            return False
        time.sleep(max(self.interaction_delay_seconds * 1.5, 0.1))
        return True

    def _navigate_to_account_details_page(self) -> None:
        """
        通过左侧导航进入账户明细页，失败时回退直达 URL。
        """
        self._switch_default_content()
        self._close_corner_popup_if_present()
        _ = self._switch_to_standard_version_if_needed()
        self._wait_left_nav_ready()

        if not self._is_account_details_page():
            finance_ready = self._open_finance_reconciliation_menu()
            if not self._is_account_details_page():
                clicked = self._click_left_panel_text_with_wait(
                    ("账户明细",),
                    timeout_seconds=max(self.timeout_seconds, 8),
                    required=False,
                    step_name="已进入菜单：账户明细",
                    min_left=115,
                    max_left=360,
                    min_top=120,
                )
                if not clicked and finance_ready and self._try_click_selector("account_details_menu"):
                    self._log_step("已进入菜单：账户明细")
                elif not clicked and finance_ready:
                    self._click_text_with_wait(("账户明细",), step_name="已进入菜单：账户明细")
                elif not clicked and not finance_ready:
                    self._log_step("未确认财务子菜单展开，准备回退直达账户明细 URL")

        try:
            self._wait_until(
                self._is_account_details_page,
                timeout_seconds=max(self.timeout_seconds, 15),
                message="点击左侧菜单后仍未进入【账户明细】页面。",
                selector_keys=("account_details_menu", "finance_menu", "reconciliation_menu"),
            )
            return
        except TimeoutException:
            self._log_step("左侧菜单未进入账户明细，尝试直达 URL")

        self._navigate_to_url(ExportConfig.ACCOUNT_DETAILS_URL)
        self._wait_until(
            self._is_account_details_page,
            timeout_seconds=max(self.timeout_seconds, 12),
            message="未进入【账户明细】页面。",
            selector_keys=("account_details_menu", "finance_menu", "reconciliation_menu"),
        )

    def _navigate_to_bill_summary_page(self) -> None:
        """
        通过左侧导航进入收支账单页，失败时回退直达 URL。
        """
        self._switch_default_content()
        self._close_corner_popup_if_present()
        self._wait_left_nav_ready()

        if not self._is_bill_summary_page():
            finance_ready = self._open_finance_reconciliation_menu()
            if not self._is_bill_summary_page():
                clicked = self._click_left_panel_text_with_wait(
                    ("收支账单",),
                    timeout_seconds=max(self.timeout_seconds, 8),
                    required=False,
                    step_name="已进入菜单：收支账单",
                    min_left=115,
                    max_left=360,
                    min_top=120,
                )
                if not clicked and finance_ready and self._try_click_selector("bill_summary_menu"):
                    self._log_step("已进入菜单：收支账单")
                elif not clicked and finance_ready:
                    self._click_left_panel_text_with_wait(
                        ("收支账单",),
                        step_name="已进入菜单：收支账单",
                        min_left=115,
                        max_left=360,
                        min_top=120,
                    )

        try:
            self._wait_until(
                self._is_bill_summary_page,
                timeout_seconds=max(self.timeout_seconds, 15),
                message="点击左侧菜单后仍未进入【收支账单】页面。",
                selector_keys=("bill_summary_menu", "finance_menu", "reconciliation_menu"),
            )
            return
        except TimeoutException:
            self._log_step("左侧菜单未进入收支账单，尝试直达 URL")

        self._navigate_to_url(ExportConfig.BILL_SUMMARY_URL)
        self._wait_until(
            self._is_bill_summary_page,
            timeout_seconds=max(self.timeout_seconds, 12),
            message="未进入【收支账单】页面。",
            selector_keys=("bill_summary_menu", "finance_menu", "reconciliation_menu"),
        )

    def _build_export_candidate_urls(self) -> list[str]:
        """
        构建可能的导出页面候选地址。
        """
        candidates: list[str] = []
        if self.export_url:
            candidates.append(self.export_url)

        base_url = self.export_url or self.expected_url_prefix
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            candidates.append(f"{parsed.scheme}://{parsed.netloc}/home.htm/trade-platform/refund-list")

        # 去重保持顺序
        deduplicated: list[str] = []
        for url in candidates:
            clean = (url or "").strip()
            if clean and clean not in deduplicated:
                deduplicated.append(clean)
        return deduplicated

    def _build_export_list_candidate_urls(self) -> list[str]:
        """
        构建导出列表页候选地址（用于切换失败时的兜底直达）。
        """
        candidates: list[str] = []
        if self.export_list_url:
            candidates.append(self.export_list_url)

        base_url = self.export_url or self.expected_url_prefix
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            candidates.append(f"{parsed.scheme}://{parsed.netloc}/home.htm/trade-platform/refund-list/export-list")

        deduplicated: list[str] = []
        for url in candidates:
            clean = (url or "").strip()
            if clean and clean not in deduplicated:
                deduplicated.append(clean)
        return deduplicated

    @staticmethod
    def _token_to_float(token: str) -> Optional[float]:
        """
        将数字 token 转为浮点数。
        """
        value = (token or "").strip()
        if not value:
            return None
        value = value.replace(",", "").replace("−", "-").replace("—", "-").replace(" ", "")
        try:
            return float(value)
        except ValueError:
            return None

    @classmethod
    def _extract_numbers_from_text(cls, text: str, include_signed_only: bool = False) -> list[float]:
        """
        从文本中提取数字。
        """
        source = str(text or "")
        source = source.replace("−", "-").replace("—", "-")
        if include_signed_only:
            pattern = r"([+\-]\s*\d[\d,]*(?:\.\d+)?)"
        else:
            pattern = r"([+\-]?\d[\d,]*(?:\.\d+)?)"

        values: list[float] = []
        for match in re.finditer(pattern, source):
            token = match.group(1)
            parsed = cls._token_to_float(token)
            if parsed is not None:
                values.append(parsed)
        return values

    def _extract_primary_metric_from_block(self, block_text: str, label: str = "") -> Optional[float]:
        """
        从区块文本中提取主值，忽略百分比。
        """
        lines = [line.strip() for line in str(block_text or "").splitlines() if line.strip()]
        label_text = (label or "").strip()

        for line in lines:
            if label_text and label_text in line and len(line) <= len(label_text) + 6:
                continue
            if "%" in line:
                continue
            numbers = self._extract_numbers_from_text(line)
            if numbers:
                return numbers[0]

        for match in re.finditer(r"([+\-]?\d[\d,]*(?:\.\d+)?)(\s*%)?", str(block_text or "")):
            if match.group(2):
                continue
            parsed = self._token_to_float(match.group(1))
            if parsed is not None:
                return parsed
        return None

    def _navigate_to_url(self, url: str) -> None:
        """
        打开指定 URL 并等待页面加载。
        """
        target = (url or "").strip()
        if not target:
            raise ValueError("目标 URL 为空，无法跳转。")
        driver = self._ensure_driver()
        driver.get(target)
        self._wait_dom_ready()
        self._close_corner_popup_if_present()

    def _click_blank_area(self) -> None:
        """
        点击页面空白区域，用于关闭蒙版或下拉面板。
        """
        driver = self._ensure_driver()
        try:
            driver.execute_script("document.body.click();")
        except Exception:
            pass

    def _switch_default_content(self) -> None:
        """
        切回默认文档上下文。
        """
        driver = self._ensure_driver()
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    def _account_details_controls_visible(self) -> bool:
        """
        判断当前文档上下文是否可见账户明细筛选控件。
        """
        return (
            self._has_any_visible_element("account_details_yesterday_button")
            or self._has_any_visible_element("account_details_reason_dropdown")
            or self._has_any_visible_element("account_details_search_button")
            or self._page_contains_text("保证金流水")
        )

    def _ensure_account_details_context(self) -> bool:
        """
        确保已切换到账户明细内容区域（兼容 iframe 场景）。
        """
        driver = self._ensure_driver()
        self._switch_default_content()
        if self._account_details_controls_visible():
            return True

        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        for frame in frames:
            try:
                self._switch_default_content()
                driver.switch_to.frame(frame)
            except Exception:
                continue

            if self._account_details_controls_visible():
                return True

            sub_frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            for sub_frame in sub_frames:
                try:
                    driver.switch_to.frame(sub_frame)
                except Exception:
                    continue

                if self._account_details_controls_visible():
                    return True

                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    break

        self._switch_default_content()
        return False

    def _extract_home_metric(self, label: str) -> float:
        """
        从首页卡片中提取指标值。
        """
        driver = self._ensure_driver()
        candidates = driver.find_elements(
            By.XPATH,
            f"//*[self::div or self::span or self::p][normalize-space()='{label}']",
        )
        candidates.extend(
            driver.find_elements(
                By.XPATH,
                f"//*[self::div or self::span or self::p][contains(normalize-space(),'{label}')]",
            )
        )

        for element in candidates:
            try:
                if not element.is_displayed():
                    continue
                current = element
                for _ in range(5):
                    block_text = (current.text or "").strip()
                    value = self._extract_primary_metric_from_block(block_text, label=label)
                    if value is not None:
                        return value
                    current = current.find_element(By.XPATH, "./..")
            except Exception:
                continue

        raise TimeoutException(f"未读取到首页指标：{label}")

    def _click_search_button(self) -> None:
        """
        点击当前页面搜索按钮。
        """
        ok = (
            self._try_click_selector("common_search_button")
            or self._try_click_selector("search_button")
            or self._click_by_text(("搜索",))
        )
        if not ok:
            self._raise_timeout_with_context(
                "未找到【搜索】按钮。",
                selector_keys=("common_search_button", "search_button"),
            )

    def _wait_account_details_filters_ready(self) -> None:
        """
        等待“账户明细”筛选区域加载完成。
        """
        self._wait_until(
            lambda: (
                self._is_account_details_page()
                and self._ensure_account_details_context()
                and self._has_any_visible_element("account_details_yesterday_button")
                and (
                    self._has_any_visible_element("account_details_reason_dropdown")
                    or self._page_contains_text("原因")
                )
                and (
                    self._has_any_visible_element("account_details_search_button")
                    or self._page_contains_text("搜索")
                )
            ),
            timeout_seconds=max(self.timeout_seconds, 18),
            message="账户明细筛选区域未加载完成。",
            selector_keys=(
                "account_details_yesterday_button",
                "account_details_reason_dropdown",
                "account_details_search_button",
            ),
        )

    def _get_account_reason_control_value(self) -> str:
        """
        读取账户明细筛选区“原因”控件当前展示值。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()

        # 优先使用用户提供的精确 XPath
        for locator in self.selectors.get("account_details_reason_dropdown", ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = (element.text or "").strip()
                    if not text:
                        text = (element.get_attribute("value") or "").strip()
                    if not text:
                        text = (element.get_attribute("title") or "").strip()
                    if not text:
                        continue
                    normalized = re.sub(r"\s+", " ", text).strip()
                    if normalized.startswith("原因"):
                        normalized = normalized.replace("原因", "", 1).strip()
                    if normalized in {"原因", "-", "--"}:
                        continue
                    if len(normalized) > 120:
                        # 过滤误命中的大容器文本（会把整页表格拼接进来）
                        continue
                    if normalized:
                        return normalized
                except Exception:
                    continue
        try:
            value = driver.execute_script(
                """
                function normalize(text) {
                  return String(text || '').replace(/\\s+/g, ' ').trim();
                }
                function isVisible(el) {
                  if (!el) return false;
                  if (el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 60 && rect.height >= 20 && rect.y >= 120 && rect.y <= 780;
                }
                const candidates = [];
                const nodes = Array.from(document.querySelectorAll('input, div, span'));
                for (const node of nodes) {
                  if (!isVisible(node)) continue;
                  const rect = node.getBoundingClientRect();
                  if (rect.x < 160 || rect.x > 860) continue;
                  if (rect.y < 220 || rect.y > 700) continue;
                  if (rect.width < 180 || rect.width > 520) continue;
                  if (rect.height < 20 || rect.height > 90) continue;

                  let text = '';
                  if (node.tagName === 'INPUT') {
                    text = normalize(node.value || node.placeholder || '');
                  } else {
                    const input = node.querySelector('input');
                    if (input) {
                      text = normalize(input.value || input.placeholder || '');
                    }
                    if (!text) {
                      text = normalize(node.innerText || '');
                    }
                  }
                  if (!text) continue;
                  if (text.length > 120) continue;
                  if (text.includes('搜索') || text.includes('重置') || text.includes('订单编号')) continue;
                  if (text.includes('完成时间') || text.includes('业务编号')) continue;
                  if (!(text.startsWith('原因') || text.includes('请选择') || text.includes('交易赔付'))) continue;

                  let value = text;
                  if (value.startsWith('原因')) {
                    value = normalize(value.replace(/^原因/, ''));
                  }
                  if (!value) value = text;

                  let score = 100;
                  if (text.startsWith('原因')) score += 100;
                  if (text.includes('请选择')) score += 40;
                  if (text.includes('交易赔付')) score += 60;
                  if (rect.y >= 300 && rect.y <= 560) score += 30;
                  candidates.push({ value, score });
                }
                candidates.sort((a, b) => b.score - a.score);
                return candidates.length ? candidates[0].value : '';
                """
            )
            return str(value or "").strip()
        except Exception:
            return ""

    def _open_account_reason_dropdown(self) -> bool:
        """
        打开账户明细的“原因”下拉框。
        """
        self._ensure_account_details_context()
        # 精确 XPath 优先：先点箭头，再点输入框
        driver = self._ensure_driver()
        specific_xpaths = (
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]/div/span/span[2]",
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]/div/span/span[1]",
        )
        for xpath in specific_xpaths:
            try:
                nodes = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for node in nodes:
                try:
                    if not node.is_displayed() or not node.is_enabled():
                        continue
                    self._click_with_retry(node)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue

        if self._try_click_selector("account_details_reason_dropdown"):
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            return True

        try:
            clicked = driver.execute_script(
                """
                function normalize(text) {
                  return String(text || '').replace(/\\s+/g, ' ').trim();
                }
                function isVisible(el) {
                  if (!el) return false;
                  if (el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 60 && rect.height >= 20 && rect.x >= 120 && rect.y >= 120 && rect.y <= 820;
                }
                function clickNode(node) {
                  if (!node) return false;
                  try {
                    node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    node.click();
                    return true;
                  } catch (err) {
                    return false;
                  }
                }

                function elementAtPointClick(x, y) {
                  const el = document.elementFromPoint(x, y);
                  if (!el) return false;
                  return clickNode(el);
                }

                const candidates = [];
                const nodes = Array.from(document.querySelectorAll('input, div, span, button'));
                for (const node of nodes) {
                  if (!isVisible(node)) continue;
                  const rect = node.getBoundingClientRect();
                  if (rect.x < 160 || rect.x > 860) continue;
                  if (rect.y < 220 || rect.y > 700) continue;
                  if (rect.width < 180 || rect.width > 520) continue;
                  if (rect.height < 20 || rect.height > 90) continue;

                  const text = normalize(node.value || node.placeholder || node.innerText || node.getAttribute('title') || '');
                  if (!(text.startsWith('原因') || text.includes('请选择') || text.includes('交易赔付'))) continue;
                  if (text.includes('搜索') || text.includes('重置') || text.includes('订单编号')) continue;

                  let score = 100;
                  if (text.startsWith('原因')) score += 100;
                  if (text.includes('请选择')) score += 60;
                  if (rect.y >= 300 && rect.y <= 560) score += 30;
                  candidates.push({ node, rect, score });
                }
                candidates.sort((a, b) => b.score - a.score);

                for (const item of candidates.slice(0, 5)) {
                  const { node, rect } = item;
                  const arrowX = rect.right - 12;
                  const arrowY = rect.top + rect.height / 2;
                  if (elementAtPointClick(arrowX, arrowY)) return true;

                  const arrow = node.querySelector(
                    "[class*='arrow'],[class*='icon'],[class*='suffix'],[class*='trigger'],svg,i"
                  );
                  if (clickNode(arrow)) return true;
                  if (clickNode(node)) return true;
                }
                return false;
                """
            )
            if clicked:
                return True
        except Exception:
            pass

        return self._click_by_text(("原因", "请选择"))

    def _find_account_reason_panel(self) -> Optional[WebElement]:
        """
        获取账户明细“原因”下拉面板滚动容器。
        """
        driver = self._ensure_driver()
        try:
            panel = driver.execute_script(
                """
                const nodes = Array.from(document.querySelectorAll('div, ul'));
                let best = null;
                let bestScore = -1;
                for (const el of nodes) {
                  if (el.offsetParent === null) continue;
                  const rect = el.getBoundingClientRect();
                  if (rect.width < 180 || rect.height < 100) continue;
                  const text = (el.innerText || '').trim();
                  if (!text) continue;
                  const hasReasonOptions =
                    text.includes('交易赔付') ||
                    text.includes('主体变更') ||
                    text.includes('违约金罚扣') ||
                    text.includes('交易售后');
                  if (!hasReasonOptions) continue;
                  const style = window.getComputedStyle(el);
                  const className = String(el.className || '').toLowerCase();
                  const isDropdownLike =
                    className.includes('menu') ||
                    className.includes('dropdown') ||
                    className.includes('select') ||
                    className.includes('popup') ||
                    className.includes('list');
                  const scrollable =
                    ['auto', 'scroll', 'overlay'].includes(style.overflowY) && el.scrollHeight > el.clientHeight + 8;
                  let score = 0;
                  if (isDropdownLike) score += 300;
                  if (scrollable) score += Math.max(el.scrollHeight - el.clientHeight, 50);
                  if (text.includes('交易赔付')) score += 200;
                  if (rect.y >= 160 && rect.y <= 760) score += 80;
                  if (rect.x >= 180 && rect.x <= 900) score += 60;
                  if (score > bestScore) {
                    best = el;
                    bestScore = score;
                  }
                }
                return best;
                """
            )
            return panel
        except Exception:
            return None

    def _scroll_account_reason_panel(self, step: int = 220) -> bool:
        """
        滚动账户明细“原因”下拉面板。
        """
        driver = self._ensure_driver()
        panel = self._find_account_reason_panel()
        if panel is None:
            return False
        try:
            moved = driver.execute_script(
                """
                const el = arguments[0];
                const step = arguments[1];
                const before = el.scrollTop;
                el.scrollTop = Math.min(el.scrollTop + step, el.scrollHeight);
                return el.scrollTop - before;
                """,
                panel,
                step,
            )
            return bool(moved and moved > 0)
        except Exception:
            return False

    def _is_account_reason_selected(self, reason_text: str) -> bool:
        """
        判断账户明细“原因”是否已选择指定值。
        """
        current = self._get_account_reason_control_value()
        if not current:
            return False
        if "请选择" in current:
            return False
        if reason_text in current:
            return True
        if reason_text == "交易赔付":
            trade_keywords = (
                "交易赔付",
                "违背发货承诺",
                "物流轨迹异常",
                "赔付",
                "承诺",
            )
            return any(keyword in current for keyword in trade_keywords)
        return False

    def _click_account_reason_option(self, reason_text: str) -> bool:
        """
        在“原因”下拉面板中点击目标选项。
        """
        driver = self._ensure_driver()
        try:
            clicked = driver.execute_script(
                """
                const target = String(arguments[0] || '').trim();
                if (!target) return false;

                function normalize(text) {
                  return String(text || '').replace(/\\s+/g, ' ').trim();
                }
                function isVisible(el) {
                  if (!el) return false;
                  if (el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 20 && rect.height >= 14 && rect.x >= 120 && rect.y >= 150 && rect.y <= 980;
                }
                function clickNode(node) {
                  if (!node) return false;
                  try {
                    node.scrollIntoView({ block: 'center', inline: 'nearest' });
                  } catch (err) {}
                  try {
                    node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    node.click();
                    return true;
                  } catch (err) {
                    return false;
                  }
                }

                const optionNodes = Array.from(
                  document.querySelectorAll(
                    "li, [role='option'], [class*='menu-item'], [class*='select-option'], [class*='dropdown-item'], div, span"
                  )
                );

                let best = null;
                let bestScore = -1;
                for (const node of optionNodes) {
                  if (!isVisible(node)) continue;
                  const text = normalize(node.innerText || node.textContent || '');
                  if (!text) continue;
                  if (!(text === target || text.includes(target))) continue;
                  if (text.includes('原因') || text.includes('请选择')) continue;
                  if (text.length > 24) continue;
                  const rect = node.getBoundingClientRect();
                  if (!(rect.x >= 220 && rect.x <= 780 && rect.y >= 220 && rect.y <= 760)) continue;
                  const cls = String(node.className || '').toLowerCase();
                  const parentCls = String((node.parentElement && node.parentElement.className) || '').toLowerCase();
                  const isDropdownLike =
                    cls.includes('option') ||
                    cls.includes('item') ||
                    cls.includes('menu') ||
                    cls.includes('dropdown') ||
                    cls.includes('select') ||
                    parentCls.includes('menu') ||
                    parentCls.includes('dropdown') ||
                    parentCls.includes('select');
                  if (!isDropdownLike && node.tagName !== 'LI' && node.getAttribute('role') !== 'option') continue;
                  let score = 100;
                  if (text === target) score += 120;
                  if (rect.width <= 420) score += 30;
                  if (rect.y >= 180 && rect.y <= 900) score += 10;
                  if (cls.includes('option') || cls.includes('item')) score += 35;
                  if (score > bestScore) {
                    bestScore = score;
                    best = node;
                  }
                }
                if (!best) return false;
                return clickNode(best);
                """,
                reason_text,
            )
            if clicked:
                return True
        except Exception:
            pass

        panel = self._find_account_reason_panel()
        scopes: list[WebElement | webdriver.Chrome] = []
        if panel is not None:
            scopes.append(panel)
        scopes.append(driver)

        xpaths_scope = (
            f".//*[self::li or self::div or self::span][normalize-space()='{reason_text}']",
            f".//*[self::li or self::div or self::span][contains(normalize-space(),'{reason_text}')]",
        )
        xpaths_driver = (
            f"//*[self::li or self::div or self::span][normalize-space()='{reason_text}']",
            f"//*[self::li or self::div or self::span][contains(normalize-space(),'{reason_text}')]",
        )
        for scope in scopes:
            xpath_list = xpaths_scope if scope is not driver else xpaths_driver
            for xpath in xpath_list:
                try:
                    candidates = scope.find_elements(By.XPATH, xpath)
                except Exception:
                    continue

                for candidate in candidates:
                    try:
                        if not candidate.is_displayed():
                            continue
                        text = (candidate.text or "").strip()
                        if not text or "原因" in text:
                            continue
                        rect = candidate.rect
                        x = float(rect.get("x", -1))
                        y = float(rect.get("y", -1))
                        width = float(rect.get("width", 0))
                        height = float(rect.get("height", 0))
                        if width < 24 or height < 14:
                            continue
                        if not (180 <= x <= 980 and 200 <= y <= 940):
                            continue
                        self._click_with_retry(candidate)
                        time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                        return True
                    except Exception:
                        continue
        return False

    def _list_visible_account_reason_options(self) -> list[str]:
        """
        列出当前下拉中可见的“原因”选项文本，用于调试。
        """
        driver = self._ensure_driver()
        try:
            options = driver.execute_script(
                """
                function normalize(text) {
                  return String(text || '').replace(/\\s+/g, ' ').trim();
                }
                const nodes = Array.from(document.querySelectorAll('li, [role="option"], div, span'))
                  .filter(el => el.offsetParent !== null);
                const values = [];
                for (const el of nodes) {
                  const rect = el.getBoundingClientRect();
                  if (rect.x < 180 || rect.x > 980 || rect.y < 180 || rect.y > 940) continue;
                  if (rect.width < 80 || rect.height < 18) continue;
                  const text = normalize(el.innerText || '');
                  if (!text) continue;
                  if (text.length > 40) continue;
                  if (text.includes('搜索') || text.includes('重置') || text.includes('订单编号')) continue;
                  if (
                    text.includes('主体变更') ||
                    text.includes('其他划扣') ||
                    text.includes('欠费划扣') ||
                    text.includes('临时支用') ||
                    text.includes('交易赔付') ||
                    text.includes('违约金罚扣') ||
                    text.includes('交易售后') ||
                    text.includes('充值') ||
                    text.includes('提现') ||
                    text.includes('发货承诺') ||
                    text.includes('物流轨迹异常') ||
                    text.includes('赔付')
                  ) {
                    values.push(text);
                  }
                }
                return Array.from(new Set(values)).slice(0, 20);
                """
            )
            if isinstance(options, list):
                return [str(item).strip() for item in options if str(item).strip()]
        except Exception:
            pass
        return []

    def _select_account_reason_trade_compensation(self) -> bool:
        """
        在账户明细页面选择 原因=交易赔付。
        """
        self._ensure_account_details_context()
        if self._is_account_reason_selected("交易赔付"):
            return True

        for _ in range(12):
            if not self._open_account_reason_dropdown():
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                continue

            clicked = self._try_click_selector("account_details_reason_trade_compensation")
            for candidate_text in (
                "交易赔付",
                "违背发货承诺",
                "物流轨迹异常",
                "延迟发货",
                "赔付",
            ):
                if clicked:
                    break
                if self._click_account_reason_option(candidate_text):
                    clicked = True
                    break

            if not clicked:
                option = self._find_status_option_element("交易赔付")
                if option is not None:
                    try:
                        self._click_with_retry(option)
                        clicked = True
                    except Exception:
                        clicked = False

            if clicked:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                if self._is_account_reason_selected("交易赔付"):
                    self._click_blank_area()
                    return True

            moved = self._scroll_account_reason_panel(step=220)
            if not moved:
                self._click_blank_area()
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))

        current_reason = self._get_account_reason_control_value() or "<未识别>"
        visible_options = self._list_visible_account_reason_options()
        options_preview = " | ".join(visible_options) if visible_options else "<未识别>"
        self._log_step(
            "未能稳定选中原因【交易赔付】，"
            f"当前原因控件值：{current_reason}，可见选项：{options_preview}。"
            "将继续执行搜索，并在结果汇总阶段按【交易赔付+日期】二次过滤。"
        )
        self._click_blank_area()
        return False

    def _select_account_details_yesterday(self) -> None:
        """
        在账户明细页面选择时间快捷项“昨天”。
        """
        self._ensure_account_details_context()
        report_date = DateConfig.default_report_date_str()
        clicked = self._try_click_selector("account_details_yesterday_button") or self._click_by_text(("昨天",))
        if not clicked:
            if not self._set_date_range_inputs(report_date, report_date):
                raise TimeoutException("未找到【昨天】按钮，且无法设置日期为前一天。")
            return

        # 点击“昨天”后再校验一次，不生效时直接写入日期
        if not self._set_date_range_inputs(report_date, report_date):
            # 不强制抛错，部分页面点击昨天后会自动生效
            pass

    def _click_account_details_search_button(self) -> None:
        """
        点击账户明细页面的搜索按钮。
        """
        self._ensure_account_details_context()
        if self._try_click_selector("account_details_search_button"):
            return

        driver = self._ensure_driver()
        buttons = driver.find_elements(By.XPATH, "//button[normalize-space()='搜索']")
        for button in buttons:
            try:
                if button.is_displayed() and button.is_enabled():
                    self._click_with_retry(button)
                    return
            except Exception:
                continue

        # 最后兜底
        if self._click_by_text(("搜索",)):
            return

        raise TimeoutException("未找到账户明细页面【搜索】按钮。")

    def _set_date_range_inputs(self, start_date: str, end_date: str) -> bool:
        """
        使用脚本设置页面内两个日期输入框。
        """
        driver = self._ensure_driver()
        try:
            updated = driver.execute_script(
                """
                const [startDate, endDate] = arguments;
                const visibleInputs = Array.from(document.querySelectorAll('input'))
                  .filter((el) => el.offsetParent !== null);

                const dateLikeInputs = visibleInputs.filter((el) => {
                  const text = `${el.value || ''} ${el.placeholder || ''}`;
                  return /\\d{4}-\\d{2}-\\d{2}/.test(text);
                });

                if (dateLikeInputs.length < 2) {
                  return false;
                }

                const target = [dateLikeInputs[0], dateLikeInputs[1]];
                target[0].focus();
                target[0].value = startDate;
                target[0].dispatchEvent(new Event('input', { bubbles: true }));
                target[0].dispatchEvent(new Event('change', { bubbles: true }));
                target[0].blur();

                target[1].focus();
                target[1].value = endDate;
                target[1].dispatchEvent(new Event('input', { bubbles: true }));
                target[1].dispatchEvent(new Event('change', { bubbles: true }));
                target[1].blur();

                return true;
                """,
                start_date,
                end_date,
            )
            return bool(updated)
        except Exception:
            return False

    def _extract_bill_summary_date_tokens(self) -> list[str]:
        """
        读取收支账单筛选栏中展示的日期值（最多返回前两个）。
        """
        driver = self._ensure_driver()
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

        # 优先读取用户提供的日期选择器 XPath
        for locator in self.selectors.get("bill_summary_date_picker_control", ()):
            try:
                controls = driver.find_elements(*locator)
            except Exception:
                continue
            for control in controls:
                try:
                    if not control.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", (control.text or "")).strip()
                    if not text:
                        text = re.sub(r"\s+", " ", (control.get_attribute("innerText") or "")).strip()
                    if not text:
                        continue
                    matches = date_pattern.findall(text)
                    if matches:
                        return matches[:2]
                except Exception:
                    continue

        try:
            tokens = driver.execute_script(
                """
                const pattern = /^\\d{4}-\\d{2}-\\d{2}$/;
                const nodes = Array.from(document.querySelectorAll('input, span, div'))
                  .filter(el => el.offsetParent !== null);
                const candidates = [];
                for (const el of nodes) {
                  const value = String(el.value || el.innerText || '').trim();
                  if (!pattern.test(value)) continue;
                  const rect = el.getBoundingClientRect();
                  if (rect.width < 60 || rect.width > 280) continue;
                  if (rect.height < 18 || rect.height > 80) continue;
                  if (rect.x < 180 || rect.x > 820) continue;
                  if (rect.y < 140 || rect.y > 620) continue;
                  candidates.push({value, x: rect.x, y: rect.y});
                }
                candidates.sort((a, b) => (a.y - b.y) || (a.x - b.x));
                const result = [];
                for (const item of candidates) {
                  if (result.length >= 2) break;
                  result.push(item.value);
                }
                return result;
                """
            )
            if isinstance(tokens, list):
                return [str(item).strip() for item in tokens if str(item).strip()]
        except Exception:
            pass
        return []

    def _is_bill_summary_date_selected(self, report_date: str) -> bool:
        """
        判断收支账单日期筛选是否已生效为指定单日。
        """
        tokens = self._extract_bill_summary_date_tokens()
        if len(tokens) < 2:
            return len(tokens) == 1 and tokens[0] == report_date
        return tokens[0] == report_date and tokens[1] == report_date

    def _open_bill_summary_date_picker(self) -> bool:
        """
        打开收支账单日期选择器。
        """
        if self._try_click_selector("bill_summary_date_picker_control"):
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            return True

        driver = self._ensure_driver()
        candidates = driver.find_elements(
            By.XPATH,
            "//*[self::input or self::span or self::div][string-length(normalize-space())=10 and contains(normalize-space(),'-')]",
        )
        filtered: list[tuple[float, float, WebElement]] = []
        for element in candidates:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                rect = element.rect
                x = float(rect.get("x", -1))
                y = float(rect.get("y", -1))
                if not (180 <= x <= 820 and 140 <= y <= 620):
                    continue
                filtered.append((y, x, element))
            except Exception:
                continue

        if not filtered:
            return False
        filtered.sort(key=lambda item: (item[0], item[1]))
        try:
            self._click_with_retry(filtered[0][2])
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            return True
        except Exception:
            return False

    def _click_calendar_day(self, report_date: str) -> bool:
        """
        在弹出的日期面板中点击指定日期。
        """
        driver = self._ensure_driver()
        day = str(int(report_date[-2:]))
        xpaths = (
            f"//*[@title='{report_date}']",
            f"//*[contains(@title,'{report_date}')]",
            f"//*[contains(@aria-label,'{report_date}')]",
            f"//*[contains(@data-date,'{report_date}')]",
            f"//*[contains(@class,'cell') and normalize-space()='{day}']",
            f"//*[contains(@class,'day') and normalize-space()='{day}']",
        )

        for xpath in xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue

            for element in elements:
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    rect = element.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if not (220 <= x <= 980 and 180 <= y <= 920):
                        continue
                    self._click_with_retry(element)
                    return True
                except Exception:
                    continue
        return False

    def _set_bill_summary_single_day(self, report_date: str) -> None:
        """
        在收支账单页将日期设置为单日范围（前一天到前一天）。
        """
        if self._is_bill_summary_date_selected(report_date):
            return

        if self._set_date_range_inputs(report_date, report_date):
            self._click_blank_area()
            if self._is_bill_summary_date_selected(report_date):
                return

        for _ in range(4):
            if not self._open_bill_summary_date_picker():
                continue
            first_clicked = self._click_calendar_day(report_date)
            second_clicked = self._click_calendar_day(report_date)
            self._click_blank_area()
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            if first_clicked and second_clicked and self._is_bill_summary_date_selected(report_date):
                return

        self._raise_timeout_with_context(
            f"收支账单日期筛选未生效：{report_date} ~ {report_date}",
        )

    def _is_bill_summary_business_selected(self, business_name: str) -> bool:
        """
        判断收支账单“业务小类”是否已选中目标值。
        """
        driver = self._ensure_driver()

        for locator in self.selectors.get("bill_summary_business_dropdown_control", ()):
            try:
                controls = driver.find_elements(*locator)
            except Exception:
                continue
            for control in controls:
                try:
                    if not control.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", (control.text or "")).strip()
                    if (not text) or len(text) > 120:
                        try:
                            text = str(
                                driver.execute_script(
                                    """
                                    const root = arguments[0];
                                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                                    const nodes = [root, ...Array.from(root.querySelectorAll('input, span, div'))];
                                    const values = [];
                                    for (const node of nodes) {
                                      if (node.offsetParent === null) continue;
                                      const rect = node.getBoundingClientRect();
                                      if (rect.width < 20 || rect.height < 14) continue;
                                      let t = '';
                                      if (node.tagName === 'INPUT') {
                                        t = normalize(node.value || node.placeholder || '');
                                      } else {
                                        t = normalize(node.innerText || '');
                                      }
                                      if (!t) continue;
                                      if (t.length > 40) continue;
                                      if (t === '业务小类') continue;
                                      values.push(t);
                                    }
                                    return values.join(' | ');
                                    """,
                                    control,
                                )
                            ).strip()
                        except Exception:
                            pass
                    if business_name in text:
                        return True
                except Exception:
                    continue

        try:
            matches = driver.find_elements(
                By.XPATH,
                (
                    "//*[contains(normalize-space(),'业务小类') "
                    f"and contains(normalize-space(),'{business_name}') "
                    "and not(contains(normalize-space(),'全部'))]"
                ),
            )
            for item in matches:
                try:
                    if not item.is_displayed():
                        continue
                    rect = item.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if 180 <= x <= 980 and 150 <= y <= 640:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _open_bill_summary_business_dropdown(self) -> bool:
        """
        打开收支账单“业务小类”下拉框。
        """
        driver = self._ensure_driver()
        for locator in self.selectors.get("bill_summary_business_dropdown_control", ()):
            try:
                controls = driver.find_elements(*locator)
            except Exception:
                continue
            for control in controls:
                try:
                    if not control.is_displayed() or not control.is_enabled():
                        continue
                    rect = control.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    width = float(rect.get("width", 0))
                    height = float(rect.get("height", 0))
                    if x < 120 or y < 120 or width < 120 or height < 18:
                        continue

                    clicked_arrow = False
                    try:
                        clicked_arrow = bool(
                            driver.execute_script(
                                """
                                const el = arguments[0];
                                const rect = el.getBoundingClientRect();
                                const x = Math.max(rect.right - 10, rect.left + 4);
                                const y = rect.top + rect.height / 2;
                                const target = document.elementFromPoint(x, y);
                                if (!target) return false;
                                try {
                                  target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                  target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                  target.click();
                                  return true;
                                } catch (err) {
                                  return false;
                                }
                                """,
                                control,
                            )
                        )
                    except Exception:
                        clicked_arrow = False

                    if not clicked_arrow:
                        self._click_with_retry(control)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue

        if self._try_click_selector("bill_summary_business_dropdown_control"):
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            return True

        try:
            controls = driver.find_elements(
                By.XPATH,
                "//*[contains(normalize-space(),'业务小类') and (contains(normalize-space(),'全部') or contains(normalize-space(),'请选择'))]",
            )
            for control in controls:
                try:
                    if not control.is_displayed() or not control.is_enabled():
                        continue
                    rect = control.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if not (180 <= x <= 980 and 150 <= y <= 640):
                        continue
                    self._click_with_retry(control)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue
        except Exception:
            pass

        return self._click_text_with_wait(
            ("业务小类",),
            exact=False,
            required=False,
            step_name="已展开业务小类下拉",
        )

    def _click_bill_summary_business_option(self, business_name: str) -> bool:
        """
        在“业务小类”下拉面板点击目标项。
        """
        driver = self._ensure_driver()
        if "淘宝天猫跨境服务增值费" in business_name:
            if self._try_click_selector("bill_summary_business_cross_border_option"):
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                return True
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '').trim();
                    if (!target) return false;
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 120 && rect.x <= 980 && rect.y >= 160 && rect.y <= 940;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      try {
                        node.scrollIntoView({ block: 'center', inline: 'nearest' });
                      } catch (err) {}
                      try {
                        node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };

                    const panelSelectors = [
                      "[role='listbox']",
                      "[class*='dropdown']",
                      "[class*='menu']",
                      "[class*='select']",
                      "[class*='popup']",
                      "[class*='overlay']"
                    ].join(',');

                    const panels = Array.from(document.querySelectorAll(panelSelectors)).filter(visible);
                    const scopeNodes = panels.length
                      ? panels.flatMap((panel) => Array.from(panel.querySelectorAll("li, [role='option'], div, span")))
                      : Array.from(document.querySelectorAll("li, [role='option'], [class*='menu-item'], [class*='select-option'], div, span"));

                    let best = null;
                    let bestScore = -1;
                    for (const node of scopeNodes) {
                      if (!visible(node)) continue;
                      const text = normalize(node.innerText || node.textContent || '');
                      if (!text) continue;
                      if (!(text === target || text.includes(target))) continue;
                      if (text.includes('业务小类') || text.includes('搜索') || text.includes('重置')) continue;
                      if (text.length > 40) continue;
                      const rect = node.getBoundingClientRect();
                      let score = 100;
                      if (text === target) score += 120;
                      if (rect.width <= 420) score += 25;
                      if (rect.x >= 200 && rect.x <= 820) score += 25;
                      const cls = String(node.className || '').toLowerCase();
                      if (cls.includes('option') || cls.includes('item') || cls.includes('menu')) score += 35;
                      if (score > bestScore) {
                        bestScore = score;
                        best = node;
                      }
                    }
                    return clickNode(best);
                    """,
                    business_name,
                )
            )
            if clicked:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                return True
        except Exception:
            pass

        xpaths = (
            f"//*[self::li or self::div or self::span][normalize-space()='{business_name}']",
            f"//*[self::li or self::div or self::span][contains(normalize-space(),'{business_name}')]",
        )
        for xpath in xpaths:
            try:
                options = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for option in options:
                try:
                    if not option.is_displayed() or not option.is_enabled():
                        continue
                    rect = option.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if not (180 <= x <= 980 and 200 <= y <= 940):
                        continue
                    self._click_with_retry(option)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue
        return False

    def _set_bill_summary_business_subcategory(self, business_name: str) -> None:
        """
        设置收支账单“业务小类”为目标值。
        """
        if self._is_bill_summary_business_selected(business_name):
            return

        for _ in range(6):
            self._close_corner_popup_if_present()
            self._open_bill_summary_business_dropdown()
            if self._click_bill_summary_business_option(business_name):
                self._click_blank_area()
                if self._is_bill_summary_business_selected(business_name):
                    return
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))
        self._log_step(f"收支账单业务小类未稳定选中：{business_name}，按当前筛选继续执行")

    def _close_bill_update_mask_if_present(self) -> None:
        """
        关闭收支账单说明蒙版。
        """
        if not self._page_contains_text("收支账单更新了"):
            return
        _ = self._click_by_text(("关闭",))
        self._click_blank_area()

    def _wait_switch_to_promotion_workspace(
        self,
        previous_handles: set[str],
        timeout_seconds: float = 20.0,
    ) -> bool:
        """
        等待并切换到“万相台AI无界”页面（新开页或当前页跳转均兼容）。
        """
        driver = self._ensure_driver()
        end_time = time.time() + max(timeout_seconds, 5.0)
        url_hints = ("alimama", "one.alimama", "wanxiangtai", "wuxiangtai")

        while time.time() < end_time:
            handles = list(self._capture_window_handles())
            if not handles:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                continue

            new_handles = [handle for handle in handles if handle not in previous_handles]
            ordered_handles = [*new_handles, *[handle for handle in handles if handle not in new_handles]]

            for handle in ordered_handles:
                try:
                    driver.switch_to.window(handle)
                    current_url = (driver.current_url or "").strip().lower()
                except Exception:
                    continue

                if any(hint in current_url for hint in url_hints):
                    return True
                if self._page_contains_text("万相台") or self._page_contains_text("万象台"):
                    return True

            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
        return False

    def _close_promotion_mask_if_present(self) -> None:
        """
        关闭“万相台AI无界”页面蒙版（优先点关闭，兜底点空白）。
        """
        driver = self._ensure_driver()
        for _ in range(4):
            _ = self._quick_click_any("promotion_mask_close")
            self._click_blank_area()
            try:
                driver.execute_script(
                    """
                    const node = document.elementFromPoint(20, 20);
                    if (node) {
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                    }
                    """
                )
            except Exception:
                pass
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))

    def _open_promotion_workspace(self) -> None:
        """
        从左侧导航进入“推广”，并打开“万相台AI无界”页面。
        """
        self._switch_default_content()
        self._close_corner_popup_if_present()
        self._wait_left_nav_ready()

        clicked_menu = self._click_left_panel_text_with_wait(
            ("推广",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已点击左侧菜单：推广",
            min_left=0,
            max_left=130,
            min_top=120,
        )
        if not clicked_menu and self._try_click_selector("promotion_menu"):
            clicked_menu = True
            self._log_step("已点击左侧菜单：推广（选择器兜底）")

        if not clicked_menu:
            self._raise_timeout_with_context(
                "未找到左侧菜单【推广】。",
                selector_keys=("promotion_menu", "finance_menu"),
            )

        self._close_corner_popup_if_present()
        self._wait_until(
            lambda: (
                self._has_any_visible_element("wanxiangtai_ai_entry")
                or self._page_contains_text("万相台")
                or self._page_contains_text("万象台")
            ),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="推广页面未加载完成，未看到【万相台AI无界】入口。",
            selector_keys=("wanxiangtai_ai_entry", "promotion_menu"),
        )

        previous_handles = self._capture_window_handles()
        clicked_entry = (
            self._try_click_selector("wanxiangtai_ai_entry")
            or self._click_text_with_wait(
                ("万相台AI无界", "万象台AI无界", "万相台ai无界", "万象台ai无界"),
                exact=False,
                required=False,
            )
            or self._click_text_with_wait(
                ("万相台", "万象台"),
                exact=False,
                required=False,
            )
        )
        if not clicked_entry:
            self._raise_timeout_with_context(
                "未找到【万相台AI无界】入口。",
                selector_keys=("wanxiangtai_ai_entry",),
            )
        self._log_step("已点击入口：万相台AI无界")

        switched = self._wait_switch_to_promotion_workspace(
            previous_handles,
            timeout_seconds=max(self.timeout_seconds, 18),
        )
        if not switched:
            self._raise_timeout_with_context("点击【万相台AI无界】后未进入对应页面。")

        self._wait_dom_ready()
        self._close_promotion_mask_if_present()

    def _navigate_to_promotion_audience_report_page(self) -> None:
        """
        在万相台页面中进入“报表 -> 人群报表”。
        """
        self._close_promotion_mask_if_present()

        clicked_report = (
            self._try_click_selector("promotion_report_tab")
            or self._click_text_with_wait(("报表",), required=False)
        )
        if not clicked_report:
            self._raise_timeout_with_context(
                "未找到顶部菜单【报表】。",
                selector_keys=("promotion_report_tab",),
            )
        self._log_step("已进入顶部菜单：报表")
        time.sleep(max(self.interaction_delay_seconds * 1.5, 0.12))

        self._close_promotion_mask_if_present()
        clicked_audience = (
            self._try_click_selector("promotion_audience_report_menu")
            or self._click_text_with_wait(("人群报表",), exact=False, required=False)
        )
        if not clicked_audience:
            self._raise_timeout_with_context(
                "未找到左侧菜单【人群报表】。",
                selector_keys=("promotion_audience_report_menu",),
            )
        self._log_step("已进入菜单：人群报表")

        self._wait_until(
            lambda: (
                self._page_contains_text("数据汇总周期")
                and (
                    self._page_contains_text("花费（元）")
                    or self._page_contains_text("花费(元)")
                    or self._page_contains_text("花费")
                )
            ),
            timeout_seconds=max(self.timeout_seconds, 18),
            message="人群报表页面未加载完成。",
            selector_keys=("promotion_summary_period_dropdown", "promotion_audience_report_menu"),
        )

    def _is_promotion_summary_period_yesterday(self) -> bool:
        """
        判断“数据汇总周期”是否已选中“昨日”。
        """
        driver = self._ensure_driver()
        for locator in self.selectors.get("promotion_summary_period_dropdown", ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", (element.text or "")).strip()
                    if "昨日" in text:
                        return True
                    inner = re.sub(r"\s+", " ", (element.get_attribute("innerText") or "")).strip()
                    if "昨日" in inner:
                        return True
                except Exception:
                    continue

        try:
            matched = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 40 && rect.height >= 16 && rect.x >= 80 && rect.y >= 60 && rect.y <= 980;
                };
                const labels = Array.from(document.querySelectorAll('div, span, p')).filter(visible);
                for (const node of labels) {
                  const text = normalize(node.innerText || '');
                  if (!text || !text.includes('数据汇总周期')) continue;
                  let current = node;
                  for (let i = 0; i < 4; i += 1) {
                    if (!current) break;
                    const block = normalize(current.innerText || '');
                    if (block.includes('数据汇总周期') && block.includes('昨日')) {
                      return true;
                    }
                    current = current.parentElement;
                  }
                }
                return false;
                """
            )
            return bool(matched)
        except Exception:
            return False

    def _set_promotion_summary_period_yesterday(self) -> None:
        """
        设置“数据汇总周期”为“昨日”。
        """
        if self._is_promotion_summary_period_yesterday():
            self._log_step("人群报表已选择数据汇总周期：昨日")
            return

        for _ in range(6):
            self._close_promotion_mask_if_present()
            opened = (
                self._try_click_selector("promotion_summary_period_dropdown")
                or self._click_text_with_wait(("数据汇总周期",), exact=False, required=False)
            )
            if not opened:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                continue

            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            selected = (
                self._try_click_selector("promotion_summary_period_yesterday_option")
                or self._click_text_with_wait(("昨日",), required=False)
            )
            self._click_blank_area()
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))

            if selected and self._is_promotion_summary_period_yesterday():
                self._log_step("人群报表已选择数据汇总周期：昨日")
                return

        self._raise_timeout_with_context(
            "未能将【数据汇总周期】设置为【昨日】。",
            selector_keys=(
                "promotion_summary_period_dropdown",
                "promotion_summary_period_yesterday_option",
            ),
        )

    def _extract_promotion_spend_fee(self) -> float:
        """
        读取人群报表“数据汇总”中的“花费（元）”。
        """
        driver = self._ensure_driver()
        labels = ("花费（元）", "花费(元)")

        for label in labels:
            xpaths = (
                f"//*[self::div or self::span or self::p][normalize-space()='{label}']",
                f"//*[self::div or self::span or self::p][contains(normalize-space(),'{label}')]",
            )
            for xpath in xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue

                for element in elements:
                    try:
                        if not element.is_displayed():
                            continue
                        current: Optional[WebElement] = element
                        for _ in range(4):
                            if current is None:
                                break
                            block_text = re.sub(r"\s+", " ", (current.text or "")).strip()
                            if block_text and len(block_text) <= 220:
                                inline = re.search(
                                    r"(?:花费（元）|花费\(元\))[^0-9+\-−¥￥]*[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)",
                                    block_text,
                                )
                                if inline:
                                    parsed = self._token_to_float(inline.group(1))
                                    if parsed is not None:
                                        return round(abs(parsed), 2)

                                parsed_metric = self._extract_primary_metric_from_block(
                                    block_text,
                                    label=label,
                                )
                                if parsed_metric is not None:
                                    return round(abs(float(parsed_metric)), 2)

                            try:
                                current = current.find_element(By.XPATH, "./..")
                            except Exception:
                                break
                    except Exception:
                        continue

        try:
            token = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 30 && rect.height >= 14 && rect.x >= 80 && rect.y >= 80 && rect.y <= 980;
                };
                const labels = ['花费（元）', '花费(元)'];
                const nodes = Array.from(document.querySelectorAll('div, span, p, strong, b')).filter(visible);
                let best = null;
                for (const node of nodes) {
                  const text = normalize(node.innerText || '');
                  if (!labels.includes(text)) continue;
                  let container = node;
                  for (let i = 0; i < 4; i += 1) {
                    if (!container) break;
                    const block = normalize(container.innerText || '');
                    if (!block || block.length > 220) {
                      container = container.parentElement;
                      continue;
                    }
                    if (!(block.includes('花费（元）') || block.includes('花费(元)'))) {
                      container = container.parentElement;
                      continue;
                    }
                    const candidates = [container, ...Array.from(container.querySelectorAll('div, span, p, strong, b'))];
                    for (const item of candidates) {
                      if (!visible(item)) continue;
                      const candidateText = normalize(item.innerText || '');
                      if (!candidateText || candidateText.length > 28) continue;
                      if (candidateText.includes('花费')) continue;
                      const match = candidateText.match(/[¥￥]?\s*[+\-−]?\d[\d,]*(?:\.\d+)?/);
                      if (!match) continue;
                      const rect = item.getBoundingClientRect();
                      const labelRect = node.getBoundingClientRect();
                      let score = 100;
                      if (rect.y >= labelRect.y - 6 && rect.y <= labelRect.y + 80) score += 50;
                      if (rect.x >= labelRect.x - 30 && rect.x <= labelRect.x + 320) score += 40;
                      if (candidateText.includes('¥') || candidateText.includes('￥')) score += 20;
                      if (!best || score > best.score) {
                        best = { token: match[0], score };
                      }
                    }
                    container = container.parentElement;
                  }
                }
                return best ? best.token : '';
                """
            )
            parsed = self._token_to_float(str(token or "").replace("¥", "").replace("￥", ""))
            if parsed is not None:
                return round(abs(parsed), 2)
        except Exception:
            pass

        page_text = self._page_text_snippet(max_length=6000)
        for pattern in (
            r"花费（元）[^0-9+\-−¥￥]*[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)",
            r"花费\(元\)[^0-9+\-−¥￥]*[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)",
        ):
            match = re.search(pattern, page_text)
            if not match:
                continue
            parsed = self._token_to_float(match.group(1))
            if parsed is not None:
                return round(abs(parsed), 2)

        no_data_markers = (
            "暂无数据",
            "没有数据",
            "暂无记录",
            "暂无结果",
            "--",
        )
        if any(self._page_contains_text(marker) for marker in no_data_markers):
            self._log_step("人群报表未读取到花费数据，按 0.00 处理")
            return 0.0

        self._raise_timeout_with_context("未读取到人群报表【花费（元）】。")

    def _collect_promotion_fee(self) -> float:
        """
        在“推广 -> 万相台AI无界 -> 报表 -> 人群报表”中提取推广费用。
        """
        self._open_promotion_workspace()
        self._navigate_to_promotion_audience_report_page()
        self._set_promotion_summary_period_yesterday()
        self._close_promotion_mask_if_present()
        time.sleep(max(self.interaction_delay_seconds * 2.0, 0.2))
        promotion_fee = self._extract_promotion_spend_fee()
        self._log_step(f"人群报表推广费用（花费）：{promotion_fee}")
        return promotion_fee

    def _extract_account_details_date_tokens(self) -> list[str]:
        """
        提取账户明细筛选区日期值（优先返回开始/结束日期）。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
        try:
            tokens = driver.execute_script(
                """
                const pattern = /^\\d{4}-\\d{2}-\\d{2}$/;
                const values = [];
                const nodes = Array.from(document.querySelectorAll('input, span, div'))
                  .filter(el => el.offsetParent !== null);
                for (const el of nodes) {
                  const text = String(el.value || el.innerText || '').replace(/\\s+/g, ' ').trim();
                  if (!text) continue;
                  if (!pattern.test(text)) continue;
                  const rect = el.getBoundingClientRect();
                  if (rect.width < 58 || rect.height < 16) continue;
                  if (rect.x < 120 || rect.x > 980) continue;
                  if (rect.y < 120 || rect.y > 760) continue;
                  values.push({ text, x: rect.x, y: rect.y });
                }
                values.sort((a, b) => (a.y - b.y) || (a.x - b.x));
                return values.slice(0, 2).map(item => item.text);
                """
            )
            if isinstance(tokens, list):
                normalized = [str(item).strip() for item in tokens if str(item).strip()]
                if normalized:
                    return normalized
        except Exception:
            pass

        # 兜底：某些页面把两个日期渲染在同一容器文本中
        try:
            nodes = driver.find_elements(By.XPATH, "//*[self::div or self::span or self::input]")
            collected: list[str] = []
            for node in nodes:
                try:
                    if not node.is_displayed():
                        continue
                    rect = node.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    width = float(rect.get("width", 0))
                    height = float(rect.get("height", 0))
                    if x < 120 or x > 980 or y < 120 or y > 760:
                        continue
                    if width < 80 or height < 16:
                        continue
                    text = (node.text or "").strip()
                    if not text and node.tag_name.lower() == "input":
                        text = (node.get_attribute("value") or "").strip()
                    if not text:
                        continue
                    matches = date_pattern.findall(text)
                    for item in matches:
                        if item not in collected:
                            collected.append(item)
                    if len(collected) >= 2:
                        return collected[:2]
                except Exception:
                    continue
        except Exception:
            pass
        return []

    def _log_account_details_filter_state(self) -> None:
        """
        输出账户明细搜索前筛选状态，便于排查筛选未生效问题。
        """
        reason_value = self._get_account_reason_control_value() or "<未识别>"
        date_tokens = self._extract_account_details_date_tokens()
        date_value = " ~ ".join(date_tokens) if date_tokens else "<未识别>"
        self._log_step(f"搜索前筛选状态：日期={date_value}，原因={reason_value}")

    def _sum_outgoing_amount_on_account_details(
        self,
        report_date: Optional[str] = None,
        reason_text: Optional[str] = None,
    ) -> float:
        """
        汇总账户明细中操作类型为“出账”的收支金额绝对值。
        """
        # 参数保留用于接口兼容；当前按用户要求仅做“收支金额（元）”列汇总
        _ = report_date
        _ = reason_text

        self._ensure_account_details_context()
        driver = self._ensure_driver()

        row_xpaths = (
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            "//*[@id='app']//table/tbody/tr",
        )

        rows: list[WebElement] = []
        for xpath in row_xpaths:
            try:
                found = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            visible_rows = []
            for row in found:
                try:
                    if row.is_displayed():
                        visible_rows.append(row)
                except Exception:
                    continue
            if visible_rows:
                rows = visible_rows
                break

        amount_tokens: list[str] = []
        seen_row_keys: set[str] = set()
        for row in rows:
            try:
                row_text = re.sub(r"\s+", " ", (row.text or "")).strip()
            except Exception:
                row_text = ""
            if not row_text:
                continue
            row_key = row_text[:260]
            if row_key in seen_row_keys:
                continue
            seen_row_keys.add(row_key)

            cell_text = ""
            try:
                # 固定取第4列（收支金额）
                cell_candidates = row.find_elements(By.XPATH, "./td[4]")
            except Exception:
                cell_candidates = []
            if not cell_candidates:
                continue

            cell = cell_candidates[0]
            try:
                cell_text = re.sub(r"\s+", " ", (cell.text or "")).strip()
                if not cell_text:
                    cell_text = re.sub(r"\s+", " ", (cell.get_attribute("innerText") or "")).strip()
            except Exception:
                cell_text = ""
            if not cell_text:
                continue
            amount_tokens.append(cell_text)

        total = 0.0
        parsed_values: list[float] = []
        self._log_step(f"收支金额列原始命中 token：{amount_tokens}")
        for token in amount_tokens:
            raw = (
                str(token or "")
                .replace("¥", "")
                .replace("￥", "")
                .replace("−", "-")
                .replace("–", "-")
                .replace("—", "-")
                .replace("﹣", "-")
                .replace("－", "-")
                .replace(",", "")
                .strip()
            )
            if not raw:
                continue
            # 优先取带符号金额；无符号时按正数处理
            match = re.search(r"[+-]?\d+(?:\.\d{1,2})?", raw)
            if not match:
                continue
            parsed = self._token_to_float(match.group(0))
            if parsed is None:
                continue
            value = abs(parsed)
            parsed_values.append(value)
            total += value

        self._log_step(f"收支金额列命中项：{parsed_values}")
        return round(total, 2)

    def _extract_cross_border_monthly_payment(self, business_name: str) -> float:
        """
        从收支账单中读取指定业务大类的“本月付款”。
        """
        driver = self._ensure_driver()
        business_nodes = driver.find_elements(
            By.XPATH,
            f"//*[contains(normalize-space(),'{business_name}')]",
        )

        def _pick_best_row_text(node: WebElement) -> str:
            best_text = ""
            current: Optional[WebElement] = node
            for _ in range(9):
                if current is None:
                    break
                try:
                    text = re.sub(r"\s+", " ", (current.text or "")).strip()
                except Exception:
                    text = ""
                if text and business_name in text and "CNY" in text:
                    if not best_text or len(text) < len(best_text):
                        best_text = text
                try:
                    current = current.find_element(By.XPATH, "./..")
                except Exception:
                    break
            return best_text

        for node in business_nodes:
            try:
                if not node.is_displayed():
                    continue
                row_text = _pick_best_row_text(node)
                if not row_text:
                    continue

                currency_match = re.search(r"CNY\s*([+\-−]?\d[\d,]*(?:\.\d+)?)", row_text)
                if currency_match:
                    parsed = self._token_to_float(currency_match.group(1))
                    if parsed is not None:
                        return round(abs(parsed), 2)

                numbers = self._extract_numbers_from_text(row_text, include_signed_only=False)
                positive_numbers = [value for value in numbers if value > 0]
                if positive_numbers:
                    return round(positive_numbers[0], 2)
            except Exception:
                continue

        # 兜底增强：从可见“业务大类行”中提取本月付款（兼容无 CNY、仅整数金额）
        try:
            row_texts = driver.execute_script(
                """
                const target = arguments[0];
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 120 && rect.height >= 16 && rect.x >= 120 && rect.x <= 1180 && rect.y >= 120 && rect.y <= 980;
                };
                const nodes = Array.from(document.querySelectorAll('tr, [role="row"], div, li')).filter(visible);
                const rows = [];
                for (const node of nodes) {
                  const text = normalize(node.innerText || '');
                  if (!text) continue;
                  if (!text.includes(target)) continue;
                  if (text.length < 8 || text.length > 420) continue;
                  if (text.includes('业务大类') && text.includes('本月付款')) continue;
                  rows.push(text);
                }
                return Array.from(new Set(rows)).slice(0, 30);
                """,
                business_name,
            ) or []

            for row_text in row_texts:
                row_str = str(row_text or "")
                month_match = re.search(r"本月付款[^0-9+\-−]*([+\-−]?\d[\d,]*(?:\.\d+)?)", row_str)
                if month_match:
                    parsed = self._token_to_float(month_match.group(1))
                    if parsed is not None:
                        return round(abs(parsed), 2)

                currency_match = re.search(r"CNY\s*([+\-−]?\d[\d,]*(?:\.\d+)?)", row_str)
                if currency_match:
                    parsed = self._token_to_float(currency_match.group(1))
                    if parsed is not None:
                        return round(abs(parsed), 2)

                decimal_tokens = re.findall(r"([+\-−]?\d+\.\d{1,2})", row_str)
                parsed_decimals: list[float] = []
                for token in decimal_tokens:
                    parsed = self._token_to_float(token)
                    if parsed is None:
                        continue
                    if abs(parsed) > 100000:
                        continue
                    parsed_decimals.append(abs(parsed))
                if parsed_decimals:
                    return round(parsed_decimals[-1], 2)

                integer_tokens = re.findall(r"\b\d+\b", row_str)
                parsed_ints: list[float] = []
                for token in integer_tokens:
                    try:
                        value = float(token)
                    except Exception:
                        continue
                    if value > 10000:
                        continue
                    parsed_ints.append(value)
                if parsed_ints:
                    return round(parsed_ints[-1], 2)
        except Exception:
            pass

        # 兜底：按业务大类所在行读取“本月付款”所在列（仅在标题存在时尝试）
        try:
            row_texts = driver.execute_script(
                """
                const target = arguments[0];
                const all = Array.from(document.querySelectorAll('tr, div, li'))
                  .filter(el => el.offsetParent !== null)
                  .map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
                  .filter(Boolean);
                const rows = [];
                for (const text of all) {
                  if (!text.includes(target)) continue;
                  if (!text.includes('CNY')) continue;
                  if (text.length > 260) continue;
                  rows.push(text);
                }
                return rows.slice(0, 20);
                """,
                business_name,
            ) or []
            for row_text in row_texts:
                currency_match = re.search(r"CNY\s*([+\-−]?\d[\d,]*(?:\.\d+)?)", str(row_text))
                if currency_match:
                    parsed = self._token_to_float(currency_match.group(1))
                    if parsed is not None:
                        return round(abs(parsed), 2)
        except Exception:
            pass

        summary_nodes = driver.find_elements(By.XPATH, "//*[contains(normalize-space(),'扣费金额合计')]")
        for node in summary_nodes:
            text = (node.text or "").strip()
            numbers = self._extract_numbers_from_text(text, include_signed_only=False)
            if numbers:
                return round(abs(numbers[0]), 2)

        no_data_markers = (
            "没有数据",
            "暂无数据",
            "暂无记录",
            "暂无结果",
            "无符合条件",
            "未查询到",
            "共0条",
            "共 0 条",
            "0条记录",
        )
        if any(self._page_contains_text(marker) for marker in no_data_markers) and not self._page_contains_text(
            business_name
        ):
            self._log_step(f"业务小类【{business_name}】查询无数据，按 0.00 处理")
            return 0.0

        # 最终兜底：不再抛错，按 0.00 返回，避免流程中断
        self._log_step(f"未稳定读取到业务小类【{business_name}】本月付款，按 0.00 处理")
        return 0.0

    def _extract_bill_summary_fee_total(self) -> float:
        """
        读取收支账单页面“扣费金额合计”数值（去除 ¥/￥ 符号）。
        """
        driver = self._ensure_driver()
        candidates: list[str] = []

        try:
            nodes = driver.find_elements(By.XPATH, "//*[contains(normalize-space(),'扣费金额合计')]")
        except Exception:
            nodes = []

        for node in nodes:
            try:
                if not node.is_displayed():
                    continue
                text = (node.text or "").strip()
                if not text:
                    text = (node.get_attribute("innerText") or "").strip()
                if text:
                    candidates.append(text)
            except Exception:
                continue

        if not candidates:
            try:
                text_from_page = driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const nodes = Array.from(document.querySelectorAll('div, span, p'))
                      .filter(el => el.offsetParent !== null);
                    for (const el of nodes) {
                      const text = normalize(el.innerText || '');
                      if (!text) continue;
                      if (!text.includes('扣费金额合计')) continue;
                      if (text.length > 120) continue;
                      return text;
                    }
                    return '';
                    """
                )
                if text_from_page:
                    candidates.append(str(text_from_page))
            except Exception:
                pass

        for text in candidates:
            normalized = re.sub(r"\s+", " ", str(text or "")).strip()
            if not normalized:
                continue

            # 示例：扣费金额合计：¥ 0.00
            match = re.search(r"扣费金额合计[^0-9+\-−¥￥]*[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)", normalized)
            if match:
                parsed = self._token_to_float(match.group(1))
                if parsed is not None:
                    return round(abs(parsed), 2)

            # 兜底：仅抽取该文本中的数字
            numbers = self._extract_numbers_from_text(normalized, include_signed_only=False)
            if numbers:
                return round(abs(numbers[0]), 2)

            if "扣费金额合计" in normalized and ("--" in normalized or "—" in normalized):
                return 0.0

        # 多候选兜底：优先非 0，其次 0
        parsed_values: list[float] = []
        for text in candidates:
            normalized = re.sub(r"\s+", " ", str(text or "")).strip()
            if not normalized:
                continue
            match = re.search(r"扣费金额合计[^0-9+\-−¥￥]*[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)", normalized)
            if not match:
                continue
            parsed = self._token_to_float(match.group(1))
            if parsed is None:
                continue
            parsed_values.append(round(abs(parsed), 2))
        non_zero = [value for value in parsed_values if value > 0]
        if non_zero:
            return non_zero[0]
        if parsed_values:
            return parsed_values[0]

        self._log_step("未读取到【扣费金额合计】，按 0.00 处理")
        return 0.0

    def _ensure_bill_summary_expense_day(self) -> None:
        """
        确保收支账单页落在“支出账单 + 日汇总”上下文。
        """
        current_url = (self.get_current_url() or "").lower()
        if "billdirection=expense" not in current_url or "billtype=day" not in current_url:
            self._log_step("收支账单当前非支出日汇总，跳转到目标参数页")
            self._navigate_to_url(ExportConfig.BILL_SUMMARY_URL)

        _ = self._click_text_with_wait(("支出账单",), required=False, step_name="收支账单已切换：支出账单")
        _ = self._click_text_with_wait(("日汇总",), required=False, step_name="收支账单已切换：日汇总")

        current_url = (self.get_current_url() or "").lower()
        if "billdirection=expense" not in current_url or "billtype=day" not in current_url:
            self._navigate_to_url(ExportConfig.BILL_SUMMARY_URL)

    def _collect_home_dashboard_metrics(self) -> dict[str, Any]:
        """
        提取极速版首页核心指标。
        """
        self._navigate_to_url(self.export_url or "https://myseller.taobao.com/home.htm/QnworkbenchHome/")
        self._close_corner_popup_if_present()

        payment_amount = self._extract_home_metric("支付金额")
        payment_buyers = self._extract_home_metric("支付买家数")
        payment_sub_orders = self._extract_home_metric("支付子订单数")

        return {
            "payment_amount": round(float(payment_amount), 2),
            "payment_buyer_count": int(round(payment_buyers)),
            "payment_sub_order_count": int(round(payment_sub_orders)),
        }

    def _collect_trade_compensation_amount(self) -> float:
        """
        在“财务 -> 对账管理 -> 账户明细”中提取交易赔付（出账）金额。
        """
        self._navigate_to_account_details_page()
        self._close_corner_popup_if_present()
        self._wait_account_details_filters_ready()

        self._log_step("账户明细筛选区已加载")
        self._select_account_details_yesterday()
        self._log_step("账户明细已选择日期：昨天")
        reason_selected = self._select_account_reason_trade_compensation()
        if reason_selected:
            self._log_step("账户明细已选择原因：交易赔付")
        else:
            self._log_step("账户明细原因未稳定选中，已启用结果二次过滤兜底")
        self._click_blank_area()

        self._log_account_details_filter_state()
        self._click_account_details_search_button()
        self._log_step("账户明细已点击搜索")
        time.sleep(max(self.interaction_delay_seconds * 3.5, 0.3))
        report_date = DateConfig.default_report_date_str()
        amount = self._sum_outgoing_amount_on_account_details(
            report_date=report_date,
            reason_text="交易赔付",
        )
        self._log_step(f"账户明细交易赔付汇总（收支金额列）：{amount}")
        if amount <= 0:
            self._log_step("交易赔付查询无数据，按 0.00 处理")
            return 0.0
        return amount

    def _collect_cross_border_value_added_fee(self) -> float:
        """
        在“财务 -> 对账管理 -> 收支账单”中提取跨境服务增值费本月付款。
        """
        self._navigate_to_bill_summary_page()
        self._close_bill_update_mask_if_present()
        self._close_corner_popup_if_present()

        self._ensure_bill_summary_expense_day()

        report_date = DateConfig.default_report_date_str()
        self._set_bill_summary_single_day(report_date)
        self._log_step(f"收支账单已设置日期：{report_date} ~ {report_date}")
        self._click_blank_area()

        target_business = "淘宝天猫跨境服务增值费"
        self._set_bill_summary_business_subcategory(target_business)
        self._log_step(f"收支账单已选择业务小类：{target_business}")
        self._click_blank_area()

        self._click_search_button()
        self._log_step("收支账单已点击搜索")
        time.sleep(max(self.interaction_delay_seconds * 3.0, 0.2))
        fee_total = self._extract_bill_summary_fee_total()
        self._log_step(f"收支账单扣费金额合计：{fee_total}")
        return fee_total

    def collect_business_finance_metrics(
        self,
        download_dir: Optional[Path] = None,
        login_handler: Optional[Callable[[webdriver.Chrome], None]] = None,
    ) -> dict[str, Any]:
        """
        采集退款管理之外的业务/财务指标。
        """
        self.validate_runtime_config()
        if self.driver is None:
            target_dir = Path(download_dir) if download_dir is not None else Path(ExportConfig.DOWNLOAD_DIR)
            target_dir.mkdir(parents=True, exist_ok=True)
            self.init_driver(download_dir=target_dir)
            self.open_login_page()
            self.login(login_handler=login_handler)
        else:
            self._ensure_wait()

        home_metrics = self._collect_home_dashboard_metrics()
        _ = self._switch_to_standard_version_if_needed()

        trade_compensation = self._collect_trade_compensation_amount()
        cross_border_fee = self._collect_cross_border_value_added_fee()
        promotion_fee = self._collect_promotion_fee()

        report_date = DateConfig.default_report_date_str()
        return {
            "report_date": report_date,
            "payment_buyer_count": home_metrics["payment_buyer_count"],
            "payment_amount": home_metrics["payment_amount"],
            "payment_sub_order_count": home_metrics["payment_sub_order_count"],
            "trade_compensation": round(trade_compensation, 2),
            "cross_border_value_added_fee": round(cross_border_fee, 2),
            "promotion_fee": round(promotion_fee, 2),
        }

    def _capture_window_handles(self) -> set[str]:
        """
        获取当前窗口句柄集合。
        """
        driver = self._ensure_driver()
        try:
            return set(driver.window_handles)
        except Exception:
            return set()

    def _try_switch_to_export_list_page(self) -> bool:
        """
        尝试在现有标签页中切换到导出列表页。
        """
        driver = self._ensure_driver()
        handles = list(self._capture_window_handles())
        if not handles:
            return False

        for handle in reversed(handles):
            try:
                driver.switch_to.window(handle)
                if self._is_export_list_page():
                    return True
            except Exception:
                continue
        return False

    def _wait_switch_to_export_list_page(
        self,
        previous_handles: set[str],
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        等待新标签页打开并切换到导出列表页。
        """
        driver = self._ensure_driver()
        limit = timeout_seconds if timeout_seconds is not None else self.export_list_switch_timeout_seconds
        end_time = time.time() + max(float(limit), 5.0)
        clicked_view_button = False
        candidate_urls = self._build_export_list_candidate_urls()
        round_count = 0

        while time.time() < end_time:
            current_handles = self._capture_window_handles()
            if current_handles and (current_handles - previous_handles):
                self._try_switch_to_export_list_page()
            elif self._try_switch_to_export_list_page():
                return True

            if self._is_export_list_page():
                return True

            if not clicked_view_button:
                clicked_view_button = (
                    self._try_click_selector("view_generated_report_button")
                    or self._click_by_text(("查看已生成报表",))
                )

            round_count += 1
            if round_count % 6 == 0:
                # 兜底：有些账号不会自动切标签，直接打开导出列表页
                for url in candidate_urls:
                    try:
                        driver.get(url)
                        self._wait_dom_ready()
                        if self._is_export_list_page():
                            return True
                    except Exception:
                        continue

            time.sleep(self.ui_poll_interval_seconds)

        return self._is_export_list_page()

    def _extract_request_time_text(self, raw_text: str) -> str:
        """
        从文本中提取“报表申请时间”时间串。
        """
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", raw_text or "")
        return match.group(1) if match else ""

    def _capture_latest_request_time(self) -> str:
        """
        读取列表顶部最新报表申请时间。
        """
        driver = self._ensure_driver()
        labels = driver.find_elements(By.XPATH, "//*[contains(normalize-space(),'报表申请时间')]")
        for label in labels:
            try:
                if not label.is_displayed():
                    continue
                extracted = self._extract_request_time_text(label.text or "")
                if extracted:
                    return extracted
            except StaleElementReferenceException:
                continue
        return ""

    def _iter_visible_download_buttons(self) -> list[WebElement]:
        """
        获取页面中可见可点击的“下载退款单报表”按钮。
        """
        driver = self._ensure_driver()
        buttons: list[WebElement] = []
        for locator in self.selectors.get("download_report_button", ()):
            try:
                candidates = driver.find_elements(*locator)
            except Exception:
                continue
            for element in candidates:
                try:
                    if element.is_displayed() and element.is_enabled():
                        buttons.append(element)
                except StaleElementReferenceException:
                    continue
        return buttons

    def _find_download_button(self, request_time: str = "") -> Optional[WebElement]:
        """
        按申请时间优先匹配下载按钮，兜底使用首个可见下载按钮。
        """
        buttons = self._iter_visible_download_buttons()
        if not buttons:
            return None

        if request_time:
            for button in buttons:
                try:
                    card = button.find_element(
                        By.XPATH,
                        "ancestor::*[self::div or self::li][contains(.,'报表申请时间')][1]",
                    )
                    if request_time in (card.text or ""):
                        return button
                except Exception:
                    continue

        return buttons[0]

    def _wait_report_ready_and_click_download(
        self,
        request_time: str = "",
        timeout_seconds: Optional[int] = None,
    ) -> float:
        """
        等待报表从“生成中”变“已完成”，并点击下载按钮。
        """
        driver = self._ensure_driver()
        limit = timeout_seconds if timeout_seconds is not None else self.report_ready_timeout_seconds
        end_time = time.time() + max(int(limit), 60)
        round_count = 0

        while time.time() < end_time:
            if not self._try_switch_to_export_list_page():
                time.sleep(self.ui_poll_interval_seconds)
                continue

            self._close_corner_popup_if_present()
            button = self._find_download_button(request_time=request_time)
            if button is not None:
                self._click_with_retry(button)
                return time.time()

            round_count += 1
            if round_count % 4 == 0:
                try:
                    driver.refresh()
                    self._wait_dom_ready()
                    self._close_corner_popup_if_present()
                except Exception:
                    pass
            time.sleep(self.report_ready_poll_interval_seconds)

        raise TimeoutException(
            "等待报表生成超时：未找到可点击的【下载退款单报表】按钮。"
            "请在导出列表页确认进度是否已完成。"
        )

    def _submit_batch_export_task(self) -> float:
        """
        在“批量导出退款单”流程中提交任务并最终触发下载。
        """
        previous_handles = self._capture_window_handles()

        generate_clicked = (
            self._try_click_selector("generate_report_button")
            or self._click_by_text(("生成报表",))
        )
        if not generate_clicked:
            raise TimeoutException("未找到【生成报表】按钮。")

        time.sleep(max(self.interaction_delay_seconds * 2.0, 0.08))
        _ = self._try_click_selector("confirm_button") or self._click_by_text(("确认",))

        if not self._wait_switch_to_export_list_page(previous_handles=previous_handles):
            raise TimeoutException("未进入导出列表页（refund-list/export-list）。")

        self._wait_dom_ready()
        self._close_corner_popup_if_present()
        request_time = self._capture_latest_request_time()
        return self._wait_report_ready_and_click_download(request_time=request_time)

    def _open_trade_refund_menu(self) -> None:
        """
        按“交易 -> 退款管理”菜单路径进入退款页。
        """
        if not self._try_click_selector("trade_menu"):
            if not self._click_by_text(("交易",)):
                raise TimeoutException("未找到一级菜单【交易】。")
        time.sleep(max(self.interaction_delay_seconds * 2.5, 0.08))

        if not self._try_click_selector("refund_manage_menu"):
            if not self._click_by_text(("退款管理",)):
                raise TimeoutException("未找到二级菜单【退款管理】。")

    def _open_combined_query(self) -> None:
        """
        打开组合查询面板。
        """
        if self._try_click_selector("combined_query_button"):
            return
        self._click_by_text(("组合查询", "高级筛选"))

    def _open_status_dropdown_panel(self) -> bool:
        """
        打开“售后状态”下拉面板。
        """
        self._close_corner_popup_if_present()
        if self._try_click_selector("status_dropdown"):
            return True
        if self._click_by_text(("售后状态",)):
            return True

        driver = self._ensure_driver()
        candidates = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(),'售后状态') or "
            "(contains(normalize-space(),'已选择') and contains(normalize-space(),'项'))]",
        )
        for element in candidates:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                self._click_with_retry(element)
                return True
            except (StaleElementReferenceException, WebDriverException):
                continue
        return False

    def _find_status_dropdown_container(self) -> Optional[WebElement]:
        """
        获取“售后状态”下拉列表的滚动容器。
        """
        driver = self._ensure_driver()
        try:
            container = driver.execute_script(
                """
                const nodes = Array.from(document.querySelectorAll('div, ul'));
                let best = null;
                let bestScore = -1;
                for (const el of nodes) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 150 || rect.height < 100) continue;
                    if (rect.bottom <= 0 || rect.top >= window.innerHeight) continue;

                    const text = (el.innerText || '').trim();
                    if (!text) continue;
                    if (!(text.includes('进行中的订单') || text.includes('退款') || text.includes('售后状态'))) {
                        continue;
                    }

                    const style = window.getComputedStyle(el);
                    const className = String(el.className || '').toLowerCase();
                    const overflowY = style.overflowY;
                    const scrollableByStyle = ['auto', 'scroll', 'overlay'].includes(overflowY);
                    const scrollableByClass =
                        className.includes('virtual') || className.includes('scroll') || className.includes('menu');
                    const scrollable = (scrollableByStyle || scrollableByClass) && el.scrollHeight > el.clientHeight + 8;
                    if (!scrollable) continue;

                    let score = (el.scrollHeight - el.clientHeight);
                    if (text.includes('进行中的订单')) score += 120;
                    if (text.includes('退款成功') || text.includes('退款关闭')) score += 180;
                    if (className.includes('select') || className.includes('dropdown')) score += 120;
                    if (score > bestScore) {
                        best = el;
                        bestScore = score;
                    }
                }
                return best;
                """
            )
            return container
        except Exception:
            return None

    def _find_status_option_element(self, status_text: str) -> Optional[WebElement]:
        """
        在下拉面板中查找目标状态选项。
        """
        search_text = (status_text or "").strip()
        if not search_text:
            return None

        # 兼容不同文案
        aliases = [search_text]
        if search_text == "退款成功":
            aliases.extend(["退款成功", "退款完结"])

        container = self._find_status_dropdown_container()
        xpath_templates = (
            ".//*[self::li or self::div or self::span][normalize-space()='{text}']",
            ".//*[self::li or self::div or self::span][contains(normalize-space(),'{text}')]",
        )

        def _find_from_scope(scope: WebElement | webdriver.Chrome) -> Optional[WebElement]:
            for alias in aliases:
                for xpath_template in xpath_templates:
                    xpath = xpath_template.format(text=alias)
                    try:
                        elements = scope.find_elements(By.XPATH, xpath)
                    except Exception:
                        continue
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                return element
                        except StaleElementReferenceException:
                            continue
            return None

        if container is not None:
            found = _find_from_scope(container)
            if found is not None:
                return found

        return _find_from_scope(self._ensure_driver())

    def _scroll_status_dropdown_panel(self, step: int = 240) -> bool:
        """
        滚动“售后状态”下拉列表。
        """
        driver = self._ensure_driver()
        container = self._find_status_dropdown_container()
        if container is None:
            return False

        try:
            moved = driver.execute_script(
                """
                const el = arguments[0];
                const step = arguments[1];
                const before = el.scrollTop;
                el.scrollTop = Math.min(el.scrollTop + step, el.scrollHeight);
                return el.scrollTop - before;
                """,
                container,
                step,
            )
            return bool(moved and moved > 0)
        except Exception:
            return False

    def _is_status_selected(self, status_text: str) -> bool:
        """
        判断售后状态是否已选中，避免重复点击导致反选。
        """
        driver = self._ensure_driver()

        for locator in self.selectors.get("status_dropdown", ()):
            elements = driver.find_elements(*locator)
            for element in elements:
                try:
                    text = (element.text or "").strip()
                    if status_text and status_text in text and "已选择" in text:
                        return True
                except StaleElementReferenceException:
                    continue

        # 兜底：部分账号的“已选择”信息在独立节点显示
        try:
            marked = driver.find_elements(
                By.XPATH,
                f"//*[contains(normalize-space(),'已选择') and contains(normalize-space(),'{status_text}')]",
            )
            if marked:
                return True
        except Exception:
            pass

        return False

    def _select_after_sale_status(self, status_text: str) -> None:
        """
        选择售后状态条件。
        """
        selector_keys = self.STATUS_SELECTOR_KEY_MAP.get(status_text)
        if selector_keys is None:
            raise ValueError(f"不支持的售后状态：{status_text}")

        if self._is_status_selected(status_text):
            return

        self._open_status_dropdown_panel()

        # 第一轮：按预置定位尝试
        for selector_key in selector_keys:
            if self._try_click_selector(selector_key):
                if self._is_status_selected(status_text):
                    return

        # 第二轮：在下拉列表中滚动查找
        for _ in range(20):
            option = self._find_status_option_element(status_text)
            if option is not None:
                try:
                    self._click_with_retry(option)
                except StaleElementReferenceException:
                    time.sleep(0.2)
                    continue
                if self._is_status_selected(status_text):
                    return

            moved = self._scroll_status_dropdown_panel(step=260)
            if not moved:
                # 可能面板被关闭，重新打开
                self._open_status_dropdown_panel()
            time.sleep(0.15)

        # 最后一轮：文本兜底
        if self._click_by_text((status_text,)):
            if self._is_status_selected(status_text):
                return

        raise TimeoutException(f"无法选择售后状态：{status_text}")

    def init_driver(self, download_dir: Optional[Path] = None) -> None:
        """
        初始化浏览器驱动。
        """
        self.download_dir = Path(download_dir) if download_dir is not None else Path.cwd()
        self.download_dir.mkdir(parents=True, exist_ok=True)

        options = Options()
        if self.attach_to_existing_browser:
            if not self.debugger_address:
                raise ValueError("附着模式已开启，但 DEBUGGER_ADDRESS 为空。")
            self._check_debugger_ready()
            options.add_experimental_option("debuggerAddress", self.debugger_address)
        else:
            prefs = {
                "download.default_directory": str(self.download_dir.resolve()),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            }
            options.add_experimental_option("prefs", prefs)
            if CHROME_USER_DATA_DIR:
                options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
            if CHROME_PROFILE_DIRECTORY:
                options.add_argument(f"--profile-directory={CHROME_PROFILE_DIRECTORY}")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument(f"--window-size={DEFAULT_WINDOW_SIZE}")
            if self.headless:
                options.add_argument("--headless=new")

        if CHROME_BINARY_PATH:
            options.binary_location = CHROME_BINARY_PATH

        if CHROMEDRIVER_PATH.exists():
            service = Service(executable_path=str(CHROMEDRIVER_PATH))
        else:
            service = Service()

        try:
            self.driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            if self.attach_to_existing_browser:
                host, port = self._split_debugger_address()
                raise RuntimeError(
                    "附着已打开浏览器失败。"
                    f"\n请确认 Chrome 已通过远程调试端口启动：{self.debugger_address}"
                    f"\n可在浏览器中打开并确认可访问：http://{host}:{port}/json/version"
                    "\nmacOS 可参考：open -na \"Google Chrome\" --args "
                    "--remote-debugging-port=9222 --user-data-dir=\"$HOME/.qianiu_chrome_profile\""
                ) from exc
            raise

        self._is_attached_session = self.attach_to_existing_browser
        self.wait = WebDriverWait(self.driver, self.timeout_seconds)
        self._configure_download_behavior()

    def validate_runtime_config(self) -> None:
        """
        校验导出流程基础配置。
        """
        if not self.export_url and not self.login_url:
            raise ValueError(
                "导出地址和登录地址均未配置。请设置 ExportConfig.EXPORT_URL 或 ExportConfig.LOGIN_URL。"
            )
        if self.attach_to_existing_browser and not self.debugger_address:
            raise ValueError("附着模式已开启，但未配置 DEBUGGER_ADDRESS。")

    def open_login_page(self) -> None:
        """
        打开入口页面（登录页或首页）。
        """
        if self.attach_to_existing_browser:
            self.ensure_expected_page_or_switch()
            return

        entry_url = self.login_url or self.export_url
        if not entry_url:
            return

        driver = self._ensure_driver()
        driver.get(entry_url)
        self._wait_dom_ready()

    def login(self, login_handler: Optional[Callable[[webdriver.Chrome], None]] = None) -> None:
        """
        登录预留接口。
        - 传入 login_handler 时由外部实现登录流程
        - 不传时使用手动登录等待
        """
        if login_handler is None:
            self.wait_for_manual_login()
            return

        driver = self._ensure_driver()
        login_handler(driver)

    def wait_for_manual_login(self, timeout_seconds: int = 300) -> None:
        """
        等待用户手动登录。
        """
        driver = self._ensure_driver()
        WebDriverWait(driver, timeout_seconds).until(
            lambda d: "login" not in (d.current_url or "").lower()
            and (d.current_url or "").strip() not in {"", "data:,", "about:blank"}
        )

    def navigate_to_export_page(self) -> None:
        """
        跳转到退款管理导出页面。
        """
        driver = self._ensure_driver()
        if self.attach_to_existing_browser:
            self.ensure_expected_page_or_switch()

        self._close_corner_popup_if_present()
        switched = self._switch_to_standard_version_if_needed()
        if switched:
            self._close_corner_popup_if_present()

        if self._wait_for_export_controls():
            return

        candidate_urls = self._build_export_candidate_urls()
        current_url = (driver.current_url or "").strip().lower()
        for candidate_url in candidate_urls:
            if current_url.startswith(candidate_url.lower()):
                continue
            driver.get(candidate_url)
            self._wait_dom_ready()
            self._close_corner_popup_if_present()
            self._switch_to_standard_version_if_needed()
            self._close_corner_popup_if_present()
            if self._wait_for_export_controls():
                return
            current_url = (driver.current_url or "").strip().lower()

        self._open_trade_refund_menu()
        self._wait_dom_ready()
        self._close_corner_popup_if_present()

        if not self._wait_for_export_controls():
            raise TimeoutException(
                "未检测到退款导出控件。请确认已在【标准版】并成功进入【交易 -> 退款管理】页面。"
            )

    def set_export_conditions(
        self,
        after_sale_status: Optional[str] = None,
        after_sale_statuses: Optional[tuple[str, ...]] = None,
        use_combined_query: bool = True,
        **kwargs,
    ) -> None:
        """
        设置导出条件，默认售后状态为“退款成功 + 进行中的订单”。
        """
        statuses: list[str] = []
        if after_sale_statuses:
            statuses.extend(list(after_sale_statuses))
        if after_sale_status:
            statuses.append(after_sale_status)
        if not statuses:
            statuses = ["退款成功", "进行中的订单"]

        unique_statuses = list(dict.fromkeys(statuses))

        if use_combined_query:
            self._open_combined_query()

        for status in unique_statuses:
            self._select_after_sale_status(status)

        driver = self._ensure_driver()
        driver.execute_script("document.body.click();")

        _ = kwargs

    def trigger_export(self) -> float:
        """
        点击搜索并触发批量导出，返回触发时间戳。
        """
        self._close_corner_popup_if_present()

        search_ok = self._try_click_selector("search_button") or self._click_by_text(("搜索售后单", "搜索"))
        if not search_ok:
            raise TimeoutException("未找到【搜索售后单】按钮。")

        self._close_corner_popup_if_present()

        export_ok = self._try_click_selector("batch_export_button") or self._click_by_text(("批量导出",))
        if not export_ok:
            raise TimeoutException("未找到【批量导出】按钮。")

        # 新版导出链路：批量导出 -> 生成报表 -> 确认 -> 导出列表 -> 下载退款单报表
        return self._submit_batch_export_task()

    def wait_for_download(
        self,
        download_dir: Path,
        trigger_ts: float,
        snapshot: Optional[dict[str, tuple[int, int]]] = None,
    ) -> Path:
        """
        等待文件下载完成并返回文件路径。
        """
        try:
            return wait_for_download_complete(
                directory=download_dir,
                timeout_seconds=self.download_wait_seconds,
                poll_interval_seconds=1.0,
                start_time=trigger_ts,
                previous_snapshot=snapshot,
                temp_suffixes=(".crdownload", ".part", ".tmp"),
            )
        except TimeoutError as exc:
            raise TimeoutException(f"下载超时，未检测到完整文件：{download_dir}") from exc

    def export_report(
        self,
        download_dir: Path,
        login_handler: Optional[Callable[[webdriver.Chrome], None]] = None,
        **kwargs,
    ) -> Path:
        """
        执行完整导出流程。
        """
        self.validate_runtime_config()
        target_dir = Path(download_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.init_driver(download_dir=target_dir)
        self.open_login_page()
        self.login(login_handler=login_handler)
        return self.export_after_login(download_dir=target_dir, **kwargs)

    def export_after_login(self, download_dir: Path, **kwargs) -> Path:
        """
        用户登录成功后继续执行导出流程。
        """
        target_dir = Path(download_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.validate_runtime_config()
        self._ensure_driver()
        self._ensure_wait()

        self.navigate_to_export_page()
        self.set_export_conditions(**kwargs)

        snapshot = snapshot_directory(target_dir)
        trigger_ts = self.trigger_export()
        return self.wait_for_download(
            download_dir=target_dir,
            trigger_ts=trigger_ts,
            snapshot=snapshot,
        )

    def close(self) -> None:
        """
        关闭浏览器。
        """
        if self.driver is not None:
            try:
                if self._is_attached_session:
                    if getattr(self.driver, "service", None) is not None:
                        self.driver.service.stop()
                else:
                    self.driver.quit()
            finally:
                self.driver = None
                self.wait = None
                self._is_attached_session = False
