"""
网页自动导出模块。
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import date, datetime
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
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from qianiu_auto_report.browser_runtime import driver_matches_browser_major
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

    PROMOTION_CROWD_REPORT_URL = "https://one.alimama.com/index.html#!/report/crowd?rptType=crowd"
    DOUYIN_AFTER_SALE_WORKBENCH_URL = (
        "https://fxg.jinritemai.com/ffa/merchant-aftersale-workbench/aftersale/list"
    )
    QIANNIU_DATA_DASHBOARD_URL = "https://myseller.taobao.com/home.htm/op-sycm-data/"
    SYCM_HOME_URL = "https://sycm.taobao.com/portal/home.htm"

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
        "switch_speed_button": (
            (By.CSS_SELECTOR, "[data-testid='switch-speed']"),
            (By.CSS_SELECTOR, "a[title='切换极速版']"),
            (By.CSS_SELECTOR, "button[title='切换极速版']"),
            (By.XPATH, "//*[self::a or self::button or self::span][contains(normalize-space(),'切换极速版')]"),
        ),
        "home_period_last_1day_tab": (
            (
                By.XPATH,
                "//*[normalize-space()='实时']/following::*[self::button or self::a or self::span or self::div]"
                "[normalize-space()='近1天' or normalize-space()='近1日'][1]",
            ),
            (By.XPATH, "//*[self::button or self::a or self::span or self::div][normalize-space()='近1天']"),
            (By.XPATH, "//*[self::button or self::a or self::span or self::div][normalize-space()='近1日']"),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'实时概况')]/following::*[self::button or self::a or self::span or self::div]"
                "[normalize-space()='近1天' or normalize-space()='近1日'][1]",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'近1天')]",
            ),
        ),
        "home_shop_name": (
            (
                By.XPATH,
                "//*[@id='icestarkNode']/div/div/div[2]/div/div/div[1]/div/div/div[1]/div[2]/div[1]/div",
            ),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'保证金')]/ancestor::*[self::div or self::section][1]"
                "//*[self::div or self::span or self::p][contains(normalize-space(),'店')]",
            ),
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
            (
                By.XPATH,
                "//*[@id='guide_search_form']/div/div[2]/div[2]/div/form/div[1]/div/span/span[1]",
            ),
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
            (
                By.XPATH,
                "//*[@id='guide_search_form']//li[normalize-space()='退款成功' or normalize-space()='退款完结']",
            ),
            (By.CSS_SELECTOR, "li[title='退款成功']"),
            (By.CSS_SELECTOR, "li[title='退款完结']"),
            (By.CSS_SELECTOR, "li[data-value='退款成功']"),
            (By.CSS_SELECTOR, "li[data-value='退款完结']"),
            (By.CSS_SELECTOR, "div[title='退款成功']"),
            (By.CSS_SELECTOR, "div[title='退款完结']"),
            (By.CSS_SELECTOR, "span[title='退款成功']"),
            (By.CSS_SELECTOR, "span[title='退款完结']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='退款成功']"),
            (By.XPATH, "//*[self::li or self::div or self::span][normalize-space()='退款完结']"),
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
                "//*[self::label or self::span or self::div][normalize-space()='业务大类']"
                "/following::*[self::div or self::span][contains(normalize-space(),'全部') "
                "or contains(normalize-space(),'请选择')][1]",
            ),
            (
                By.XPATH,
                "//*[self::label or self::span or self::div][normalize-space()='业务小类']"
                "/following::*[self::div or self::span][contains(normalize-space(),'全部') "
                "or contains(normalize-space(),'请选择')][1]",
            ),
            (
                By.XPATH,
                "//*[@id='wui-page']/div/div[2]/div/div[2]/div/div/div[2]/div/div/div[2]/form/div/div[3]/div/div",
            ),
            (
                By.XPATH,
                "//*[@id='wui-page']/div/div[2]/div/div[2]/div/div/div[2]/div/div/div[2]/form/div/div[4]/div/div",
            ),
        ),
        "bill_summary_business_cross_border_option": (
            (
                By.XPATH,
                "//*[self::li or self::div or self::span][normalize-space()='淘宝天猫跨境服务增值费']",
            ),
            (
                By.XPATH,
                "//*[self::li or self::div or self::span][contains(normalize-space(),'淘宝天猫跨境服务增值费')]",
            ),
            (
                By.XPATH,
                "//*[@id='qn-worbench-container']/div[2]/div/ul/li[5]/div/span"
                "[contains(normalize-space(),'淘宝天猫跨境服务增值费')]",
            ),
        ),
        "account_details_reason_trade_compensation": (
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
                "//*[self::button or self::a][contains(normalize-space(),'搜索')]",
            ),
        ),
        "wanxiangtai_ai_entry": (
            (
                By.XPATH,
                "//*[@id='mx_98']/a",
            ),
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
        ),
        "promotion_report_tab": (
            (
                By.XPATH,
                "//*[@id='mx_66']/div/div/div/div[4]/a",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][normalize-space()='报表']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'报表')]",
            ),
        ),
        "promotion_audience_report_menu": (
            (
                By.XPATH,
                "//*[@id='universalBP_common_layout_main_menu']/div[4]/a",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][normalize-space()='人群报表']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'人群报表')]",
            ),
        ),
        "promotion_summary_period_control": (
            (
                By.XPATH,
                "//*[@id='trigger_mx_2510']",
            ),
            (
                By.XPATH,
                "//*[@id='trigger_mx_2510']/div/span",
            ),
            (
                By.XPATH,
                "//*[@id='trigger_mx_8342']/div/span",
            ),
            (
                By.XPATH,
                "//*[normalize-space()='数据汇总周期']/following::*[starts-with(@id,'trigger_mx_')][1]",
            ),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'数据汇总周期')]/following::*[starts-with(@id,'trigger_mx_')][1]",
            ),
            (
                By.XPATH,
                "//*[contains(normalize-space(),'数据汇总周期')]/following::*[self::div or self::span][1]",
            ),
            (
                By.XPATH,
                "//*[self::div or self::span][contains(normalize-space(),'数据汇总周期')]",
            ),
        ),
        "promotion_summary_period_yesterday": (
            (
                By.XPATH,
                "//*[@id='mx_8706']/button",
            ),
            (
                By.XPATH,
                "//*[@id='mx_9736']/button",
            ),
            (
                By.XPATH,
                "//*[starts-with(@id,'mx_')]//button[normalize-space()='昨天' or normalize-space()='昨日']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][normalize-space()='昨天']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'昨天')]",
            ),
        ),
        "douyin_popup_ack_button": (
            (By.XPATH, "//button[normalize-space()='我知道了']"),
            (By.XPATH, "//*[self::button or self::a or self::span or self::div][normalize-space()='我知道了']"),
            (By.XPATH, "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'我知道了')]"),
        ),
        "douyin_popup_close_button": (
            (
                By.XPATH,
                "//*[self::button or self::span or self::i][normalize-space()='×' or normalize-space()='✕' or normalize-space()='x' or normalize-space()='X']",
            ),
            (
                By.XPATH,
                "//*[contains(@class,'close') or contains(@aria-label,'关闭') or contains(@title,'关闭')]",
            ),
        ),
        "douyin_compass_entry": (
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='电商罗盘']"),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'电商罗盘')]",
            ),
        ),
        "douyin_period_last_1day_tab": (
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='近1天']"),
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='近1日']"),
            (
                By.XPATH,
                "//*[contains(@class,'tab') or contains(@class,'time') or contains(@class,'period')]"
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'近1天') or contains(normalize-space(),'近1日')]",
            ),
        ),
        "douyin_period_custom_tab": (
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='自定义']"),
            (
                By.XPATH,
                "//*[contains(@class,'tab') or contains(@class,'time') or contains(@class,'period')]"
                "//*[self::a or self::button or self::span or self::div][normalize-space()='自定义']",
            ),
        ),
        "douyin_business_more_data_link": (
            (
                By.XPATH,
                "//*[contains(normalize-space(),'经营概况')]/following::*"
                "[self::a or self::button or self::span or self::div][contains(normalize-space(),'查看更多数据')][1]",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][normalize-space()='查看更多数据']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'查看更多数据')]",
            ),
        ),
        "douyin_refund_analysis_menu": (
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][normalize-space()='全店退款分析']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'全店退款分析')]",
            ),
        ),
        "douyin_refund_period_last_1day_tab": (
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='近1天']"),
            (By.XPATH, "//*[self::a or self::button or self::span or self::div][normalize-space()='近1日']"),
        ),
        "douyin_refund_download_detail_button": (
            (By.XPATH, "//button[normalize-space()='下载明细']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][normalize-space()='下载明细']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'下载明细')]",
            ),
        ),
        "douyin_after_sale_workbench_menu": (
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][normalize-space()='售后工作台']",
            ),
            (
                By.XPATH,
                "//*[self::a or self::button or self::span or self::div][contains(normalize-space(),'售后工作台')]",
            ),
        ),
        "douyin_after_sale_query_button": (
            (By.XPATH, "//button[normalize-space()='查询']"),
            (
                By.XPATH,
                "//button[translate(normalize-space(), ' \u00a0', '')='查询']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][normalize-space()='查询']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a][translate(normalize-space(), ' \u00a0', '')='查询']",
            ),
            (By.XPATH, "//*[self::button or self::a][contains(normalize-space(),'查询')]"),
            (
                By.XPATH,
                "//*[self::button or self::a][contains(translate(normalize-space(), ' \u00a0', ''),'查询')]",
            ),
        ),
        "douyin_after_sale_export_button": (
            (By.XPATH, "//button[normalize-space()='导出']"),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][normalize-space()='导出']",
            ),
            (By.XPATH, "//*[self::button or self::a][contains(normalize-space(),'导出')]"),
        ),
        "douyin_header_shop_hover_area": (
            (By.XPATH, '//*[@id="fxg-pc-header"]/div/div[2]/div[7]'),
            (By.XPATH, "//*[@id='fxg-pc-header']/div/div[2]/div[7]"),
            (By.CSS_SELECTOR, "#fxg-pc-header .headerShopName"),
            (By.CSS_SELECTOR, "#fxg-pc-header [class*='headerShopName']"),
        ),
        "douyin_shop_switch_menu_item": (
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][normalize-space()='切换组织/店铺']",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'切换组织')]",
            ),
            (
                By.XPATH,
                "//*[self::button or self::a or self::span or self::div][contains(normalize-space(),'切换店铺')]",
            ),
        ),
        "douyin_shop_switcher_title": (
            (
                By.XPATH,
                "//*[self::div or self::span or self::p][contains(normalize-space(),'请选择店铺')]",
            ),
            (
                By.XPATH,
                "//*[self::div or self::span or self::p][contains(normalize-space(),'选择店铺')]",
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
        # 推广页面渲染重，动作节奏单独放慢，避免“反复横跳”
        self.promotion_action_delay_seconds = max(self.interaction_delay_seconds * 4.0, 0.55)
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
        self._debugger_browser_version = ""

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
        self._debugger_browser_version = browser_name

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
        if expected_host.endswith("jinritemai.com") and current_host.endswith("jinritemai.com"):
            return True
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

    def _wait_for_any_clickable(
        self,
        selector_key: str,
        timeout_seconds: Optional[float] = None,
    ) -> WebElement:
        """
        在候选选择器中等待可点击元素。
        """
        if timeout_seconds is None:
            wait = self._ensure_wait()
        else:
            wait = WebDriverWait(self._ensure_driver(), max(float(timeout_seconds), 0.5))
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

    def _try_click_selector(
        self,
        selector_key: str,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        尝试按选择器点击，找不到时返回 False。
        """
        if not self.selectors.get(selector_key):
            return False
        for _ in range(3):
            try:
                element = self._wait_for_any_clickable(
                    selector_key=selector_key,
                    timeout_seconds=timeout_seconds,
                )
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

    def _page_contains_compact_text(self, text: str) -> bool:
        """
        判断页面去除空白后的文本是否包含指定内容，用于兼容“查 询”这类被拆开的按钮文案。
        """
        driver = self._ensure_driver()
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            page_text = re.sub(r"\s+", "", body.text or "")
            target_text = re.sub(r"\s+", "", text or "")
            return bool(target_text) and target_text in page_text
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
        if "refund-list" in current_url and ("export-list" in current_url or "export" in current_url):
            return True

        stable_markers = (
            "退款单导出报表",
            "报表申请时间",
            "预计退款单数量",
            "下载退款单报表",
            "进度：",
        )
        hit_count = sum(1 for marker in stable_markers if self._page_contains_text(marker))
        return hit_count >= 2

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

    def _switch_to_speed_version_if_needed(self) -> bool:
        """
        如当前为非极速版，点击左下角“切换极速版”后等待页面稳定。
        """
        if self._page_contains_text("切换标准版"):
            # 已经是极速版
            return False

        if not self._page_contains_text("切换极速版"):
            return False

        switched = self._quick_click_any("switch_speed_button") or self._click_by_text(("切换极速版",))
        if not switched:
            return False

        self._wait_dom_ready()
        time.sleep(max(self.interaction_delay_seconds * 4.0, 0.15))
        self._log_step("已切换：极速版")
        return True

    def _click_home_period_last_1day_by_js(self) -> bool:
        """
        使用 JS 在首页实时概况区域点击“近1天”。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      try {
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };

                    const labels = Array.from(document.querySelectorAll("div, span, p, h2, h3"))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || '') === '实时概况');
                    const labelRects = labels.map((el) => el.getBoundingClientRect());

                    const candidates = Array.from(document.querySelectorAll("button, a, span, div"))
                      .filter(visible)
                      .filter((el) => {
                        const t = normalize(el.innerText || el.textContent || '');
                        return t === '近1天' || t === '近1日';
                      });
                    if (!candidates.length) return false;

                    let best = null;
                    let bestScore = -1;
                    for (const node of candidates) {
                      const rect = node.getBoundingClientRect();
                      const text = normalize(node.innerText || node.textContent || '');
                      const cls = String(node.className || '').toLowerCase();
                      let score = 100;
                      if (text === '近1天') score += 30;
                      if (cls.includes('active') || cls.includes('selected') || cls.includes('current') || cls.includes('checked')) score += 20;
                      if (rect.width >= 28 && rect.width <= 160) score += 20;

                      if (labelRects.length) {
                        let minDist = 999999;
                        for (const lr of labelRects) {
                          const cx = rect.left + rect.width / 2;
                          const cy = rect.top + rect.height / 2;
                          const lx = lr.left + lr.width / 2;
                          const ly = lr.top + lr.height / 2;
                          const dist = Math.hypot(cx - lx, cy - ly);
                          if (dist < minDist) minDist = dist;
                        }
                        score += Math.max(0, 260 - Math.min(minDist, 260));
                      }

                      if (score > bestScore) {
                        best = node;
                        bestScore = score;
                      }
                    }
                    return clickNode(best);
                    """
                )
            )
            return clicked
        except Exception:
            return False

    def _get_home_period_active_label(self) -> str:
        """
        读取首页实时概况当前激活周期标签（实时/近1天/近7天/近30天）。
        """
        driver = self._ensure_driver()
        try:
            label = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 20 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                };
                const labels = ['实时', '近1天', '近1日', '近7天', '近30天', '近1周', '近30日'];
                const selectedByNode = (node) => {
                  if (!node) return false;
                  const attrs = ['aria-selected', 'aria-checked', 'aria-pressed', 'data-selected', 'data-active'];
                  for (const key of attrs) {
                    const value = String(node.getAttribute(key) || '').toLowerCase();
                    if (value === 'true' || value === '1' || value === 'yes' || value === 'active' || value === 'selected') return true;
                  }
                  const cls = String(node.className || '').toLowerCase();
                  if (/(^|\\s)(active|selected|current|checked|is-active|actived|on)(\\s|$)/.test(cls)) return true;
                  return false;
                };
                const styleScore = (node) => {
                  if (!node) return 0;
                  const style = window.getComputedStyle(node);
                  const color = style.color || '';
                  const rgb = color.match(/\\d+/g) || [];
                  const sum = rgb.slice(0, 3).map((v) => Number(v) || 0).reduce((a, b) => a + b, 0);
                  const fontWeight = Number(style.fontWeight) || 400;
                  const borderBottomWidth = parseFloat(style.borderBottomWidth || '0') || 0;
                  const borderBottomStyle = String(style.borderBottomStyle || '').toLowerCase();
                  const textDecoration = String(style.textDecorationLine || style.textDecoration || '').toLowerCase();
                  let score = 0;
                  if (fontWeight >= 600) score += 22;
                  if (sum > 0 && sum <= 300) score += 15;
                  if (borderBottomWidth >= 1 && borderBottomStyle !== 'none') score += 35;
                  if (textDecoration.includes('underline')) score += 20;
                  return score;
                };

                const nodes = Array.from(document.querySelectorAll('button, a, span, div'))
                  .filter(visible)
                  .map((el) => {
                    const text = normalize(el.innerText || el.textContent || '');
                    return { el, text };
                  })
                  .filter((item) => labels.includes(item.text));
                if (!nodes.length) return '';

                // 强优先：显式 selected/active
                for (const item of nodes) {
                  if (selectedByNode(item.el)) return item.text;
                  let parent = item.el.parentElement;
                  for (let i = 0; i < 2 && parent; i += 1) {
                    if (selectedByNode(parent)) return item.text;
                    parent = parent.parentElement;
                  }
                }

                // 兜底：按样式强度推断激活项
                let bestText = '';
                let bestScore = -1;
                for (const item of nodes) {
                  let score = styleScore(item.el);
                  let parent = item.el.parentElement;
                  for (let i = 0; i < 2 && parent; i += 1) {
                    score += Math.floor(styleScore(parent) * 0.35);
                    parent = parent.parentElement;
                  }
                  if (score > bestScore) {
                    bestScore = score;
                    bestText = item.text;
                  }
                }
                if (bestScore >= 18) return bestText;
                return '';
                """
            )
            return str(label or "").strip()
        except Exception:
            return ""

    def _is_home_period_last_1day_selected(self) -> bool:
        """
        判断首页实时概况周期是否已切换到“近1天”。
        """
        active_label = self._get_home_period_active_label()
        if active_label:
            return active_label in {"近1天", "近1日"}

        driver = self._ensure_driver()
        try:
            selected = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                    };
                    const selectedByNode = (node) => {
                      if (!node) return false;
                      const attrs = ['aria-selected', 'aria-checked', 'aria-pressed', 'data-selected', 'data-active'];
                      for (const key of attrs) {
                        const value = String(node.getAttribute(key) || '').toLowerCase();
                        if (value === 'true' || value === '1' || value === 'yes' || value === 'active' || value === 'selected') return true;
                      }
                      const cls = String(node.className || '').toLowerCase();
                      if (/(^|\\s)(active|selected|current|checked|is-active|actived|on)(\\s|$)/.test(cls)) return true;
                      return false;
                    };
                    const styleScore = (node) => {
                      if (!node) return 0;
                      const style = window.getComputedStyle(node);
                      const color = style.color || '';
                      const rgb = color.match(/\\d+/g) || [];
                      const sum = rgb.slice(0, 3).map((v) => Number(v) || 0).reduce((a, b) => a + b, 0);
                      const fontWeight = Number(style.fontWeight) || 400;
                      const borderBottomWidth = parseFloat(style.borderBottomWidth || '0') || 0;
                      const borderBottomStyle = String(style.borderBottomStyle || '').toLowerCase();
                      const textDecoration = String(style.textDecorationLine || style.textDecoration || '').toLowerCase();
                      let score = 0;
                      if (fontWeight >= 600) score += 25;
                      if (sum > 0 && sum <= 360) score += 15;
                      if (sum > 0 && sum <= 240) score += 10;
                      if (borderBottomWidth >= 1 && borderBottomStyle !== 'none') score += 35;
                      if (textDecoration.includes('underline')) score += 20;
                      return score;
                    };
                    const collectNodes = (labels) => {
                      const nodes = Array.from(document.querySelectorAll("button, a, span, div"))
                        .filter(visible)
                        .filter((el) => {
                          const t = normalize(el.innerText || el.textContent || '');
                          return labels.includes(t);
                        });
                      return nodes;
                    };

                    const nodes = collectNodes(['近1天', '近1日']);
                    let best1day = 0;
                    for (const node of nodes) {
                      let score = 0;
                      if (selectedByNode(node)) return true;
                      score += styleScore(node);
                      let current = node.parentElement;
                      for (let i = 0; i < 3 && current; i += 1) {
                        if (selectedByNode(current)) return true;
                        score += Math.floor(styleScore(current) * 0.35);
                        current = current.parentElement;
                      }
                      if (score > best1day) best1day = score;
                    }

                    const otherNodes = collectNodes(['实时', '近7天', '近30天', '近1周', '近30日']);
                    let bestOther = 0;
                    for (const node of otherNodes) {
                        let score = styleScore(node);
                        let current = node.parentElement;
                      for (let i = 0; i < 3 && current; i += 1) {
                        score += Math.floor(styleScore(current) * 0.35);
                        current = current.parentElement;
                      }
                      if (score > bestOther) bestOther = score;
                    }
                    if (best1day >= 22 && (bestOther === 0 || best1day >= bestOther + 3)) {
                      return true;
                    }
                    return false;
                    """
                )
            )
            return selected
        except Exception:
            return False

    def _is_home_statistics_date_target(self, report_date: str) -> bool:
        """
        判断首页“统计时间”是否已经切换到目标日期（通常为昨天）。
        """
        target = (report_date or "").strip()
        if not target:
            return False

        driver = self._ensure_driver()
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            body_text = ""
        normalized = re.sub(r"\s+", " ", body_text).strip()
        if not normalized:
            return False

        match = re.search(r"统计时间[:：]?\s*(20\d{2}-\d{2}-\d{2})", normalized)
        if match:
            return match.group(1) == target
        if "统计时间" in normalized and target in normalized:
            return True
        return False

    def _set_home_period_last_1day(self) -> None:
        """
        首页读取核心指标前，先切换到“近1天”。
        """
        report_date = DateConfig.default_report_date_str()
        current_label = self._get_home_period_active_label()
        self._log_step(f"首页实时概况当前周期：{current_label or '<未识别>'}")
        if self._is_home_period_last_1day_selected() or self._is_home_statistics_date_target(report_date):
            self._log_step("首页实时概况已选择：近1天")
            return

        for _ in range(4):
            clicked = (
                self._try_click_selector("home_period_last_1day_tab", timeout_seconds=1.5)
                or self._click_text_with_wait(("近1天", "近1日"), exact=True, timeout_seconds=2.0, required=False)
                or self._click_home_period_last_1day_by_js()
            )
            if clicked:
                time.sleep(max(self.interaction_delay_seconds * 2.5, 0.35))
                current_label = self._get_home_period_active_label()
                if current_label in {"近1天", "近1日"}:
                    self._log_step("首页实时概况已选择：近1天")
                    return
                if self._is_home_period_last_1day_selected():
                    self._log_step("首页实时概况已选择：近1天")
                    return
                if self._is_home_statistics_date_target(report_date):
                    self._log_step(f"首页实时概况已选择：近1天（按统计时间 {report_date} 校验）")
                    return
            else:
                time.sleep(max(self.ui_poll_interval_seconds, 0.15))

        if self._is_home_period_last_1day_selected() or self._is_home_statistics_date_target(report_date):
            self._log_step("首页实时概况已选择：近1天")
            return

        self._raise_timeout_with_context(
            "未能将首页实时概况切换到【近1天】。",
            selector_keys=("home_period_last_1day_tab",),
        )

    def _log_step(self, message: str) -> None:
        """
        输出关键步骤日志。
        """
        safe_log(message)

    @staticmethod
    def _format_report_date(report_date: date | datetime | str | None = None) -> str:
        """
        将报表日期格式化为 YYYY-MM-DD；未传时使用默认“昨天”。
        """
        if report_date is None:
            return DateConfig.default_report_date_str()
        if isinstance(report_date, datetime):
            return report_date.date().strftime(DateConfig.DATE_FORMAT)
        if isinstance(report_date, date):
            return report_date.strftime(DateConfig.DATE_FORMAT)
        parsed = datetime.strptime(str(report_date).strip(), DateConfig.DATE_FORMAT)
        return parsed.strftime(DateConfig.DATE_FORMAT)

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

    def _click_wanxiangtai_ai_entry_by_exact_xpath(self) -> bool:
        """
        优先使用用户提供的 XPath 点击“万相台ai无界”入口。
        """
        driver = self._ensure_driver()
        xpaths = (
            "//*[@id='mx_98']/a",
            '//*[@id="mx_98"]/a',
        )
        for _ in range(3):
            for xpath in xpaths:
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
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
        return False

    def _get_wanxiangtai_entry_href(self) -> str:
        """
        读取“万相台ai无界”入口链接，作为点击失败时的 URL 兜底。
        """
        driver = self._ensure_driver()
        candidate_locators: list[tuple[str, str]] = [
            (By.XPATH, "//*[@id='mx_98']/a"),
            (By.XPATH, '//*[@id="mx_98"]/a'),
        ]
        candidate_locators.extend(self.selectors.get("wanxiangtai_ai_entry", ()))

        fallback_http_href = ""
        for by, value in candidate_locators:
            try:
                nodes = driver.find_elements(by, value)
            except Exception:
                continue
            for node in nodes:
                href_candidates: list[str] = []
                try:
                    href_candidates.append(str(node.get_attribute("href") or "").strip())
                except Exception:
                    pass

                try:
                    anchors = node.find_elements(By.XPATH, ".//a[@href] | ancestor::a[@href][1]")
                except Exception:
                    anchors = []
                for anchor in anchors:
                    try:
                        href_candidates.append(str(anchor.get_attribute("href") or "").strip())
                    except Exception:
                        continue

                for href in href_candidates:
                    if not href.startswith("http"):
                        continue
                    if self._is_wanxiangtai_url(href):
                        return href
                    if not fallback_http_href:
                        fallback_http_href = href

        if fallback_http_href:
            return fallback_http_href
        return ""

    @staticmethod
    def _is_wanxiangtai_url(url: str) -> bool:
        """
        判断 URL 是否属于万相台页面，避免误把卖家后台页判定为成功切换。
        """
        current_url = (url or "").strip().lower()
        if not current_url:
            return False
        if "myseller.taobao.com" in current_url:
            return False
        if "alimama.com" not in current_url:
            return False

        url_hints = (
            "one.alimama.com",
            "#!/report",
            "/report/",
            "universalbp",
            "wxt",
            "wanxiangtai",
        )
        return any(hint in current_url for hint in url_hints)

    def _is_wanxiangtai_page_by_content(self) -> bool:
        """
        当 URL 还未稳定时，通过页面稳定文案辅助识别万相台页面。
        """
        current_url = (self.get_current_url() or "").lower()
        if "myseller.taobao.com" in current_url:
            return False

        required_markers = ("基础报表", "人群报表")
        optional_markers = ("报表", "洞察", "创意", "工具", "账户", "推广")

        if not all(self._page_contains_text(marker) for marker in required_markers):
            return False
        hit_optional = sum(1 for marker in optional_markers if self._page_contains_text(marker))
        return hit_optional >= 2

    def _is_promotion_unavailable_page(self) -> bool:
        """
        识别万相台无权限/未授权页面，这类店铺推广费用按 0 处理。
        """
        page_text = self._page_text_snippet(max_length=2000)
        if not page_text or page_text == "<空白页面>":
            return False

        compact_text = re.sub(r"\s+", "", page_text)
        unavailable_markers = (
            "暂无权限登录",
            "账号暂无权限",
            "无权限登录",
            "万相台无界权限",
            "子账号授权",
            "请主账号",
        )
        if any(marker in compact_text for marker in unavailable_markers) and (
            "万相台" in compact_text or "无界" in compact_text
        ):
            return True
        return False

    def _is_wanxiangtai_ready_context(self) -> bool:
        """
        判断当前标签是否已进入可继续处理的万相台上下文。

        仅 URL 命中 one.alimama.com 不够：部分入口会先打开空白中转壳页，
        需要等到报表正文、无权限提示或目标报表 URL 真正稳定后才算就绪。
        """
        current_url = (self.get_current_url() or "").lower()
        if not self._is_wanxiangtai_url(current_url):
            return False

        if self._is_promotion_unavailable_page():
            return True
        if self._is_wanxiangtai_page_by_content():
            return True

        page_snippet = self._page_text_snippet(max_length=120)
        if page_snippet == "<空白页面>":
            return False

        if "/report/crowd" in current_url or "#!/report/crowd" in current_url:
            return (
                self._page_contains_text("数据汇总")
                or self._page_contains_text("花费")
                or self._page_contains_text("人群报表")
            )

        return (
            self._page_contains_text("报表")
            and (self._page_contains_text("万相台") or self._page_contains_text("人群报表"))
        )

    def _open_promotion_crowd_report_directly(self, reason: str = "") -> None:
        """
        直达万相台人群报表，修复入口打开空白中转页或顶部导航不可见的情况。
        """
        if reason:
            self._log_step(f"{reason}，直达人群报表")
        else:
            self._log_step("直达人群报表")

        self._navigate_to_url(self.PROMOTION_CROWD_REPORT_URL)
        self._promotion_pause(1.4)
        self._wait_until(
            lambda: (
                self._is_promotion_unavailable_page()
                or self._is_wanxiangtai_page_by_content()
                or (
                    self._page_contains_text("数据汇总")
                    and self._page_contains_text("花费")
                )
            ),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="直达人群报表后页面未加载完成。",
            selector_keys=("promotion_report_tab", "promotion_audience_report_menu", "promotion_summary_period_control"),
        )

    def _wait_switch_to_wanxiangtai_page(
        self,
        previous_handles: set[str],
        timeout_seconds: float = 20.0,
    ) -> bool:
        """
        等待切换到“万相台ai无界”新页面（兼容新标签与当前页跳转）。
        """
        driver = self._ensure_driver()
        end_time = time.time() + max(timeout_seconds, 5.0)

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
                    _ = (driver.current_url or "").strip().lower()
                except Exception:
                    continue

                if self._is_wanxiangtai_ready_context():
                    return True

            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
        return False

    def _open_promotion_then_wanxiangtai_page(self) -> None:
        """
        先点击左侧“推广”，再点击“万相台ai无界”，并切到新页面。
        """
        self._switch_default_content()
        self._close_corner_popup_if_present()
        self._wait_left_nav_ready()

        clicked_promotion = self._click_left_panel_text_with_wait(
            ("推广",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已点击左侧菜单：推广",
            min_left=0,
            max_left=130,
            min_top=120,
        )
        if not clicked_promotion and self._try_click_selector("promotion_menu"):
            clicked_promotion = True
            self._log_step("已点击左侧菜单：推广（选择器兜底）")
        if not clicked_promotion:
            clicked_promotion = self._click_text_with_wait(("推广",), required=False)
            if clicked_promotion:
                self._log_step("已点击左侧菜单：推广（文本兜底）")
        if not clicked_promotion:
            self._raise_timeout_with_context(
                "未找到左侧菜单【推广】。",
                selector_keys=("promotion_menu", "finance_menu"),
            )
        self._promotion_pause(1.0)

        self._wait_until(
            lambda: (
                self._has_any_visible_element("wanxiangtai_ai_entry")
                or self._page_contains_text("万相台")
                or self._page_contains_text("万象台")
            ),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="推广页面未加载完成，未看到【万相台ai无界】入口。",
            selector_keys=("wanxiangtai_ai_entry", "promotion_menu"),
        )

        entry_href = self._get_wanxiangtai_entry_href()
        previous_handles = self._capture_window_handles()
        clicked_entry = (
            self._click_wanxiangtai_ai_entry_by_exact_xpath()
            or self._quick_click_any("wanxiangtai_ai_entry")
            or self._try_click_selector("wanxiangtai_ai_entry")
            or self._click_text_with_wait(("万相台ai无界", "万相台AI无界", "万象台AI无界"), exact=False, required=False)
        )
        if not clicked_entry:
            self._raise_timeout_with_context(
                "未找到【万相台ai无界】入口（含 XPath: //*[@id='mx_98']/a）。",
                selector_keys=("wanxiangtai_ai_entry",),
            )
        self._log_step("已点击入口：万相台ai无界")
        self._promotion_pause(1.0)

        switched = self._wait_switch_to_wanxiangtai_page(
            previous_handles=previous_handles,
            timeout_seconds=max(self.timeout_seconds, 18),
        )
        if not switched and entry_href:
            try:
                self._navigate_to_url(entry_href)
                try:
                    self._wait_until(
                        self._is_wanxiangtai_ready_context,
                        timeout_seconds=max(self.timeout_seconds, 10),
                        message="入口链接直达后万相台页面未稳定。",
                        selector_keys=("wanxiangtai_ai_entry", "promotion_report_tab"),
                    )
                    switched = True
                except TimeoutException:
                    switched = False
                if switched:
                    self._log_step("已通过入口链接直达：万相台ai无界页面")
            except Exception:
                switched = False
        if not switched:
            try:
                self._open_promotion_crowd_report_directly("万相台入口页未稳定")
                switched = True
            except Exception:
                switched = False
        if not switched:
            self._raise_timeout_with_context("点击【万相台ai无界】后未切换到新页面。")
        self._wait_until(
            self._is_wanxiangtai_ready_context,
            timeout_seconds=max(self.timeout_seconds, 8),
            message="万相台页面校验未通过（URL/页面特征不匹配）。",
            selector_keys=("wanxiangtai_ai_entry", "promotion_report_tab"),
        )
        self._wait_dom_ready()
        self._promotion_pause(0.8)
        self._log_step(f"已切换到万相台ai无界页面：{self.get_current_url()}")

    def _close_promotion_mask_by_blank_click(self) -> None:
        """
        若存在蒙版弹窗，点击空白处关闭。
        """
        driver = self._ensure_driver()
        try:
            has_mask = bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 120 && rect.height >= 80;
                    };
                    const nodes = Array.from(document.querySelectorAll("div, section, aside, [role='dialog'], [aria-modal='true']"))
                      .filter(visible);
                    for (const node of nodes) {
                      const cls = String(node.className || '').toLowerCase();
                      const text = String(node.innerText || '');
                      const style = window.getComputedStyle(node);
                      const rect = node.getBoundingClientRect();
                      const isPopupLike =
                        cls.includes('modal') || cls.includes('dialog') || cls.includes('popup') ||
                        cls.includes('mask') || cls.includes('backdrop') || cls.includes('overlay') ||
                        node.getAttribute('role') === 'dialog' || node.getAttribute('aria-modal') === 'true';
                      const isLargeLayer =
                        rect.width >= window.innerWidth * 0.35 && rect.height >= window.innerHeight * 0.25;
                      const hasPromoText = /优惠券|立即领取|万相台|万象台|弹窗|福利/.test(text);
                      const fixedLayer = ['fixed', 'absolute', 'sticky'].includes(style.position);
                      if ((isPopupLike || hasPromoText) && (isLargeLayer || fixedLayer)) return true;
                    }
                    return false;
                    """
                )
            )
        except Exception:
            has_mask = False

        if not has_mask:
            return

        for _ in range(2):
            closed = False
            try:
                closed = bool(
                    driver.execute_script(
                        """
                        const visible = (el) => {
                          if (!el || el.offsetParent === null) return false;
                          const rect = el.getBoundingClientRect();
                          return rect.width >= 120 && rect.height >= 80;
                        };
                        const clickAt = (x, y) => {
                          const node = document.elementFromPoint(x, y);
                          if (!node) return false;
                          try {
                            node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
                            node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x, clientY: y }));
                            node.click();
                            return true;
                          } catch (err) {
                            return false;
                          }
                        };
                        const nodes = Array.from(document.querySelectorAll("div, section, aside, [role='dialog'], [aria-modal='true']"))
                          .filter(visible);
                        let best = null;
                        let bestScore = -1;
                        for (const node of nodes) {
                          const cls = String(node.className || '').toLowerCase();
                          const text = String(node.innerText || '');
                          const rect = node.getBoundingClientRect();
                          const style = window.getComputedStyle(node);
                          const z = Number(style.zIndex) || 0;
                          const popupLike =
                            cls.includes('modal') || cls.includes('dialog') || cls.includes('popup') ||
                            cls.includes('mask') || cls.includes('backdrop') || cls.includes('overlay') ||
                            node.getAttribute('role') === 'dialog' || node.getAttribute('aria-modal') === 'true';
                          if (!popupLike && !/优惠券|立即领取|万相台|万象台|福利/.test(text)) continue;
                          let score = z + rect.width * rect.height / 10000;
                          if (rect.width >= window.innerWidth * 0.5) score += 100;
                          if (rect.height >= window.innerHeight * 0.35) score += 100;
                          if (score > bestScore) {
                            best = node;
                            bestScore = score;
                          }
                        }
                        if (!best) return false;
                        const rect = best.getBoundingClientRect();
                        // 点击弹窗容器左上空白区域，避免误触页面导航
                        const x = Math.max(rect.left + 14, 14);
                        const y = Math.max(rect.top + 14, 14);
                        return clickAt(x, y);
                        """
                    )
                )
            except Exception:
                closed = False

            if not closed:
                self._click_blank_area()
            self._promotion_pause(0.8)

    def _open_promotion_report_page(self) -> None:
        """
        在万相台页面按用户提供 XPath 进入“报表 -> 人群报表”。
        """
        self._close_promotion_mask_by_blank_click()
        self._promotion_pause(0.8)

        current_url = (self.get_current_url() or "").lower()
        if "/report/crowd" in current_url:
            try:
                self._wait_until(
                    lambda: (
                        self._is_promotion_unavailable_page()
                        or (
                            self._page_contains_text("数据汇总")
                            and self._page_contains_text("花费")
                        )
                    ),
                    timeout_seconds=max(self.timeout_seconds, 16),
                    message="当前人群报表页面未加载完成。",
                    selector_keys=("promotion_audience_report_menu", "promotion_summary_period_control"),
                )
            except TimeoutException:
                self._open_promotion_crowd_report_directly("当前人群报表加载不稳定")
            self._log_step("当前已在人群报表页面")
            return

        clicked_report = (
            self._try_click_selector("promotion_report_tab")
            or self._click_text_with_wait(("报表",), required=False)
        )
        if not clicked_report:
            if self._is_promotion_unavailable_page():
                self._log_step("万相台无界暂无权限，推广费用按 0.00 处理")
                return
            if self._is_wanxiangtai_url(current_url):
                self._open_promotion_crowd_report_directly("未找到顶部导航【报表】")
                return
            self._raise_timeout_with_context(
                "未找到顶部导航【报表】。",
                selector_keys=("promotion_report_tab",),
            )
        self._log_step("已进入顶部导航：报表")
        self._promotion_pause(1.2)
        self._wait_until(
            lambda: ("/report" in (self.get_current_url() or "").lower()) or self._page_contains_text("基础报表"),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="点击【报表】后页面未稳定进入报表模块。",
            selector_keys=("promotion_report_tab", "promotion_audience_report_menu"),
        )
        self._close_promotion_mask_by_blank_click()
        self._promotion_pause(0.6)

        clicked_audience = (
            self._try_click_selector("promotion_audience_report_menu")
            or self._click_text_with_wait(("人群报表",), exact=False, required=False)
        )
        if not clicked_audience:
            self._raise_timeout_with_context(
                "未找到左侧导航【人群报表】。",
                selector_keys=("promotion_audience_report_menu",),
            )
        self._log_step("已进入菜单：人群报表")
        self._promotion_pause(1.0)

        self._wait_until(
            lambda: self._page_contains_text("数据汇总") and self._page_contains_text("花费"),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="人群报表页面未加载完成。",
            selector_keys=("promotion_audience_report_menu", "promotion_summary_period_control"),
        )

    def _is_promotion_period_yesterday_selected(self) -> bool:
        """
        判断数据汇总周期是否为昨天/昨日。
        """
        period_text = self._get_promotion_period_display_text()
        if period_text:
            normalized = re.sub(r"\s+", " ", period_text).strip()
            return ("昨天" in normalized) or ("昨日" in normalized)

        # 兜底：保留旧逻辑
        driver = self._ensure_driver()
        for locator in self.selectors.get("promotion_summary_period_control", ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", (element.text or "")).strip()
                    if ("昨天" in text) or ("昨日" in text):
                        return True
                    inner_text = re.sub(r"\s+", " ", (element.get_attribute("innerText") or "")).strip()
                    if ("昨天" in inner_text) or ("昨日" in inner_text):
                        return True
                except Exception:
                    continue
        return False

    def _get_promotion_period_display_text(self) -> str:
        """
        读取“数据汇总周期”控件当前展示值。
        """
        driver = self._ensure_driver()

        # 优先精确 XPath
        for locator in self.selectors.get("promotion_summary_period_control", ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", (element.text or "")).strip()
                    if text:
                        return text
                    inner_text = re.sub(r"\s+", " ", (element.get_attribute("innerText") or "")).strip()
                    if inner_text:
                        return inner_text
                except Exception:
                    continue

        try:
            value = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 36 && rect.height >= 18 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                };

                const labels = Array.from(document.querySelectorAll('div, span, label, p'))
                  .filter(visible)
                  .filter((el) => normalize(el.innerText || '') === '数据汇总周期');

                let bestText = '';
                let bestScore = -1;
                for (const label of labels) {
                  const lr = label.getBoundingClientRect();
                  const candidates = Array.from(document.querySelectorAll("[id^='trigger_mx_'], div, span"))
                    .filter(visible);
                  for (const c of candidates) {
                    const cr = c.getBoundingClientRect();
                    const text = normalize(c.innerText || '');
                    if (!text) continue;
                    if (text === '数据汇总周期') continue;
                    const dist = Math.hypot((cr.left + cr.width / 2) - (lr.left + lr.width / 2), (cr.top + cr.height / 2) - (lr.top + lr.height / 2));
                    let score = 220 - Math.min(dist, 220);
                    if (String(c.id || '').startsWith('trigger_mx_')) score += 120;
                    if (text.includes('昨天') || text.includes('昨日')) score += 60;
                    if (score > bestScore) {
                      bestScore = score;
                      bestText = text;
                    }
                  }
                }
                return bestText;
                """
            )
            return str(value or "").strip()
        except Exception:
            return ""

    def _is_promotion_report_date_target(self, report_date: str) -> bool:
        """
        根据数据汇总顶部“YYYY-MM-DD 对比 ...”文案判断是否已落在目标日期。
        """
        target = (report_date or "").strip()
        if not target:
            return False

        driver = self._ensure_driver()
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            body_text = ""
        normalized = re.sub(r"\s+", " ", body_text).strip()
        if not normalized:
            return False

        # 只接受“对比”前的汇总日期片段，避免下方明细表中恰好出现目标日期时误判刷新完成。
        range_matches = re.findall(
            r"(20\d{2}-\d{2}-\d{2})\s*至\s*(20\d{2}-\d{2}-\d{2})\s*对比",
            normalized,
        )
        for start_date, end_date in range_matches:
            if start_date == target and end_date == target:
                return True

        single_matches = re.findall(
            r"(20\d{2}-\d{2}-\d{2})\s*对比",
            normalized,
        )
        if single_matches and single_matches[0] == target:
            return True
        return False

    def _click_visible_xpath_candidates(self, xpaths: tuple[str, ...]) -> bool:
        """
        按 XPath 列表点击第一个可见可用元素（用于推广页稳定定位）。
        """
        driver = self._ensure_driver()
        for xpath in xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue

            for element in elements:
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    self._click_with_retry(element)
                    self._promotion_pause(0.4)
                    return True
                except Exception:
                    continue
        return False

    def _click_promotion_period_control_by_js(self) -> bool:
        """
        动态定位“数据汇总周期”控件：优先匹配 id^=trigger_mx_ 且靠近标签。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 36 && rect.height >= 20 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 300;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      try {
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };

                    const labelNodes = Array.from(document.querySelectorAll('div, span, label, p'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || '') === '数据汇总周期');
                    const labels = labelNodes.map((el) => el.getBoundingClientRect());

                    const candidates = Array.from(document.querySelectorAll("[id^='trigger_mx_'], div, span, a, button"))
                      .filter(visible);
                    let best = null;
                    let bestScore = -1;

                    for (const node of candidates) {
                      const rect = node.getBoundingClientRect();
                      const id = String(node.id || '');
                      const text = normalize(node.innerText || '');
                      const cls = String(node.className || '').toLowerCase();

                      let score = 0;
                      if (id.startsWith('trigger_mx_')) score += 220;
                      if (text.includes('昨天') || text.includes('昨日')) score += 80;
                      if (cls.includes('trigger') || cls.includes('select') || cls.includes('dropdown')) score += 40;
                      if (rect.y >= 100 && rect.y <= 420) score += 30;
                      if (rect.width >= 80 && rect.width <= 420) score += 20;

                      if (labels.length) {
                        let minDist = 999999;
                        for (const lr of labels) {
                          const cx = rect.left + rect.width / 2;
                          const cy = rect.top + rect.height / 2;
                          const lx = lr.left + lr.width / 2;
                          const ly = lr.top + lr.height / 2;
                          const dist = Math.hypot(cx - lx, cy - ly);
                          if (dist < minDist) minDist = dist;
                        }
                        score += Math.max(0, 220 - Math.min(minDist, 220));
                      }

                      if (score > bestScore) {
                        best = node;
                        bestScore = score;
                      }
                    }
                    return clickNode(best);
                    """
                )
            )
            if clicked:
                self._promotion_pause(0.4)
            return clicked
        except Exception:
            return False

    def _click_promotion_yesterday_by_js(self) -> bool:
        """
        下拉框 XPath 未命中时，使用文本“昨天/昨日”做一次 JS 精准点击兜底。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 28 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 300;
                    };
                    const nodes = Array.from(document.querySelectorAll('button, li, a, div, span')).filter(visible);
                    let best = null;
                    let bestScore = -1;
                    for (const node of nodes) {
                      const text = normalize(node.innerText || node.textContent || '');
                      if (!(text === '昨天' || text === '昨日')) continue;
                      const rect = node.getBoundingClientRect();
                      const cls = String(node.className || '').toLowerCase();
                      if (rect.y > window.innerHeight * 0.75) continue;
                      if (rect.width > 420) continue;
                      let score = 100;
                      if (node.tagName === 'BUTTON') score += 50;
                      if (cls.includes('menu') || cls.includes('dropdown') || cls.includes('option')) score += 40;
                      if (rect.y >= 90 && rect.y <= window.innerHeight - 30) score += 20;
                      if (score > bestScore) {
                        best = node;
                        bestScore = score;
                      }
                    }
                    if (!best) return false;
                    try {
                      best.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      best.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      best.click();
                      return true;
                    } catch (err) {
                      return false;
                    }
                    """
                )
            )
            return clicked
        except Exception:
            return False

    def _click_promotion_range_date_input_by_js(self, input_index: int) -> bool:
        """
        在人群报表日期范围弹层中点击起始/结束日期输入框。
        """
        driver = self._ensure_driver()
        try:
            element = driver.execute_script(
                """
                    const inputIndex = Number(arguments[0]);
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const rect = el.getBoundingClientRect();
                      const style = getComputedStyle(el);
                      return rect.width >= 40 && rect.height >= 16
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.y >= -80 && rect.y <= window.innerHeight + 420;
                    };
                    const outputs = Array.from(document.querySelectorAll('.mx-output-open, [id^="mx_output"]'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || '').includes('选择日期'));
                    const output = outputs[0];
                    if (!output) return null;
                    const triggers = Array.from(output.querySelectorAll('[id^="trigger_mx_"], .mxgc-calendar-datepicker'))
                      .filter(visible)
                      .filter((el) => {
                        const text = normalize(el.innerText || el.textContent || '');
                        return /\\d{4}-\\d{2}-\\d{2}|昨日|昨天/.test(text);
                      });
                    const unique = [];
                    const seen = new Set();
                    for (const node of triggers) {
                      const rect = node.getBoundingClientRect();
                      const key = `${Math.round(rect.left)}:${Math.round(rect.top)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;
                      if (seen.has(key)) continue;
                      seen.add(key);
                      unique.push(node);
                    }
                    unique.sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      return (ar.top - br.top) || (ar.left - br.left);
                    });
                    return unique[inputIndex] || null;
                    """,
                int(input_index),
            )
            if not element:
                return False
            self._click_with_retry(element)
            return True
        except Exception:
            return False

    def _click_promotion_calendar_day_by_js(self, report_date: str) -> bool:
        """
        在万相台日期面板中按完整日期属性点击目标日。
        """
        driver = self._ensure_driver()
        try:
            element = driver.execute_script(
                """
                    const target = String(arguments[0] || '').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const rect = el.getBoundingClientRect();
                      const style = getComputedStyle(el);
                      return rect.width >= 8 && rect.height >= 8
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.y >= -120 && rect.y <= window.innerHeight + 520;
                    };
                    const disabled = (el) => {
                      const cls = String(el.className || '').toLowerCase();
                      const aria = String(el.getAttribute('aria-disabled') || '').toLowerCase();
                      return el.hasAttribute('disabled') || aria === 'true' || cls.includes('disabled');
                    };
                    const nodes = Array.from(document.querySelectorAll(
                      `[title="${target}"], [aria-label*="${target}"], [data-date="${target}"]`
                    )).filter(visible).filter((el) => !disabled(el));
                    nodes.sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      return (br.top - ar.top) || (br.left - ar.left);
                    });
                    return nodes[0] || null;
                    """,
                report_date,
            )
            if not element:
                return False
            self._click_with_retry(element)
            return True
        except Exception:
            return False

    def _extract_promotion_range_picker_dates_by_js(self) -> list[str]:
        """
        读取人群报表日期范围弹层中当前展示的起止日期。
        """
        driver = self._ensure_driver()
        try:
            tokens = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  const style = getComputedStyle(el);
                  return rect.width >= 30 && rect.height >= 12
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.y >= -80 && rect.y <= window.innerHeight + 420;
                };
                const outputs = Array.from(document.querySelectorAll('.mx-output-open, [id^="mx_output"]'))
                  .filter(visible)
                  .filter((el) => normalize(el.innerText || '').includes('选择日期'));
                const output = outputs[0];
                if (!output) return [];
                const triggers = Array.from(output.querySelectorAll('[id^="trigger_mx_"], .mxgc-calendar-datepicker'))
                  .filter(visible)
                  .map((el) => {
                    const rect = el.getBoundingClientRect();
                    const text = normalize(el.innerText || el.textContent || '');
                    return { text, left: rect.left, top: rect.top, width: rect.width, height: rect.height };
                  })
                  .filter((item) => /\\d{4}-\\d{2}-\\d{2}|昨日|昨天/.test(item.text));
                const result = [];
                const seen = new Set();
                for (const item of triggers.sort((a, b) => (a.top - b.top) || (a.left - b.left))) {
                  const key = `${Math.round(item.left)}:${Math.round(item.top)}:${Math.round(item.width)}:${Math.round(item.height)}`;
                  if (seen.has(key)) continue;
                  seen.add(key);
                  const match = item.text.match(/\\d{4}-\\d{2}-\\d{2}|昨日|昨天/);
                  if (match) result.push(match[0]);
                  if (result.length >= 2) break;
                }
                return result;
                """
            )
        except Exception:
            return []
        if not isinstance(tokens, list):
            return []
        return [str(item).strip() for item in tokens if str(item).strip()]

    def _confirm_promotion_range_picker_by_js(self) -> bool:
        """
        点击人群报表日期范围弹层的【确定】。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const rect = el.getBoundingClientRect();
                      const style = getComputedStyle(el);
                      return rect.width >= 20 && rect.height >= 12
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.y >= -80 && rect.y <= window.innerHeight + 420;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      const rect = node.getBoundingClientRect();
                      const x = Math.max(1, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
                      const y = Math.max(1, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
                      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        node.dispatchEvent(new MouseEvent(type, {
                          bubbles: true,
                          cancelable: true,
                          clientX: x,
                          clientY: y,
                          view: window,
                        }));
                      }
                      return true;
                    };
                    const outputs = Array.from(document.querySelectorAll('.mx-output-open, [id^="mx_output"]'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || '').includes('选择日期'));
                    const output = outputs[0];
                    if (!output) return false;
                    const buttons = Array.from(output.querySelectorAll('button, span, div'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || el.textContent || '') === '确定');
                    buttons.sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      return (ar.top - br.top) || (ar.left - br.left);
                    });
                    return clickNode(buttons[0]);
                    """
                )
            )
        except Exception:
            return False

    def _set_promotion_report_date(self, report_date: date | datetime | str | None = None) -> None:
        """
        设置人群报表数据汇总周期为指定单日。
        """
        target = self._format_report_date(report_date)
        current_period_text = self._get_promotion_period_display_text()
        self._log_step(f"人群报表当前数据汇总周期控件值：{current_period_text or '<未识别>'}")

        if self._is_promotion_report_date_target(target) and target in current_period_text:
            self._log_step(f"人群报表已选择数据汇总周期：{target}")
            return

        for _ in range(4):
            opened = (
                self._click_visible_xpath_candidates(
                    (
                        "//*[@id='trigger_mx_2510']",
                        "//*[@id='trigger_mx_2510']/div/span",
                        "//*[@id='trigger_mx_8342']",
                        "//*[@id='trigger_mx_8342']/div/span",
                        "//*[normalize-space()='数据汇总周期']/following::*[starts-with(@id,'trigger_mx_')][1]",
                        "//*[contains(normalize-space(),'数据汇总周期')]/following::*[starts-with(@id,'trigger_mx_')][1]",
                    )
                )
                or self._click_promotion_period_control_by_js()
                or self._try_click_selector("promotion_summary_period_control")
            )
            if not opened:
                self._promotion_pause(0.5)
                continue
            self._promotion_pause(0.5)

            selected_all = True
            for input_index in (0, 1):
                if not self._click_promotion_range_date_input_by_js(input_index):
                    selected_all = False
                    break
                self._promotion_pause(0.25)
                if not self._click_promotion_calendar_day_by_js(target):
                    selected_all = False
                    break
                self._promotion_pause(0.45)

            tokens = self._extract_promotion_range_picker_dates_by_js()
            if not selected_all or len(tokens) < 2 or tokens[0] != target or tokens[1] != target:
                self._log_step(
                    "人群报表日期弹层未锁定目标日期，重试："
                    f"目标={target}，当前={tokens or '<未识别>'}"
                )
                self._click_blank_area()
                self._promotion_pause(0.5)
                continue

            if not self._confirm_promotion_range_picker_by_js():
                self._click_blank_area()
                self._promotion_pause(0.5)
                continue

            self._promotion_pause(1.2)
            try:
                self._wait_until(
                    lambda: self._is_promotion_report_date_target(target),
                    timeout_seconds=max(self.timeout_seconds, 10),
                    message=f"人群报表日期未切换到：{target}",
                    selector_keys=("promotion_summary_period_control",),
                )
            except TimeoutException:
                self._log_step(f"人群报表确认日期后未观测到数据刷新到：{target}，重试")
                continue

            self._log_step(f"人群报表已选择数据汇总周期：{target}")
            return

        if self._is_promotion_report_date_target(target):
            self._log_step(f"周期控件未稳定识别，但页面日期已是 {target}，继续后续读取")
            return

        self._raise_timeout_with_context(
            f"未能将人群报表数据汇总周期切换到：{target}",
            selector_keys=("promotion_summary_period_control",),
        )

    def _set_promotion_period_yesterday(self) -> None:
        """
        设置人群报表数据汇总周期为“昨天”。
        """
        report_date = DateConfig.default_report_date_str()
        current_period_text = self._get_promotion_period_display_text()
        self._log_step(f"人群报表当前数据汇总周期控件值：{current_period_text or '<未识别>'}")

        if self._is_promotion_period_yesterday_selected() and self._is_promotion_report_date_target(report_date):
            self._log_step("人群报表已选择数据汇总周期：昨天")
            return

        for _ in range(4):
            self._close_promotion_mask_by_blank_click()
            opened = (
                self._click_visible_xpath_candidates(
                    (
                        "//*[@id='trigger_mx_2510']",
                        "//*[@id='trigger_mx_2510']/div/span",
                        "//*[@id='trigger_mx_8342']",
                        "//*[@id='trigger_mx_8342']/div/span",
                        "//*[normalize-space()='数据汇总周期']/following::*[starts-with(@id,'trigger_mx_')][1]",
                        "//*[contains(normalize-space(),'数据汇总周期')]/following::*[starts-with(@id,'trigger_mx_')][1]",
                    )
                )
                or self._click_promotion_period_control_by_js()
                or self._try_click_selector("promotion_summary_period_control")
                or self._click_text_with_wait(("数据汇总周期",), exact=False, required=False)
            )
            if not opened:
                self._promotion_pause(0.6)
                continue

            self._promotion_pause(0.8)
            selected = (
                self._click_visible_xpath_candidates(
                    (
                        "//*[@id='mx_8706']/button",
                        "//*[@id='mx_9736']/button",
                        "//*[starts-with(@id,'mx_')]//button[normalize-space()='昨天' or normalize-space()='昨日']",
                    )
                )
                or self._try_click_selector("promotion_summary_period_yesterday")
                or self._click_text_with_wait(("昨天", "昨日"), exact=False, required=False)
                or self._click_promotion_yesterday_by_js()
            )
            self._click_blank_area()
            self._promotion_pause(1.2)

            # 强校验：必须看到目标日期落位，避免“控件文本误判”
            if selected:
                try:
                    self._wait_until(
                        lambda: self._is_promotion_report_date_target(report_date),
                        timeout_seconds=max(self.timeout_seconds, 8),
                        message=f"已点击昨天，但页面数据未切换到目标日期：{report_date}",
                        selector_keys=("promotion_summary_period_control", "promotion_summary_period_yesterday"),
                    )
                except TimeoutException:
                    # 继续重试下一轮
                    self._log_step("点击昨天后未观测到目标日期生效，重试")
                    continue

            if selected and self._is_promotion_report_date_target(report_date):
                self._log_step("人群报表已选择数据汇总周期：昨天")
                return

        if self._is_promotion_report_date_target(report_date):
            self._log_step("周期控件未稳定识别，但页面日期已是昨天，继续后续读取")
            return

        self._raise_timeout_with_context(
            "未能将数据汇总周期切换到【昨天】。",
            selector_keys=("promotion_summary_period_control", "promotion_summary_period_yesterday"),
        )

    def _extract_promotion_spend_fee(self) -> float:
        """
        读取人群报表【数据汇总】下的【花费（元）】数值。
        """
        driver = self._ensure_driver()

        try:
            token = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 20 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                };
                const labels = Array.from(document.querySelectorAll('div, span, p'))
                  .filter(visible)
                  .filter(el => {
                    const t = normalize(el.innerText || '');
                    return t === '花费（元）' || t === '花费(元)';
                  });

                for (const label of labels) {
                  const lr = label.getBoundingClientRect();
                  // 仅取“数据汇总卡片”区域，规避下方表格同名列
                  if (lr.y > Math.min(window.innerHeight * 0.78, 760)) continue;
                  let node = label;
                  for (let i = 0; i < 6; i += 1) {
                    if (!node) break;
                    const text = normalize(node.innerText || '');
                    if (text && text.length <= 260 && (text.includes('花费（元）') || text.includes('花费(元)'))) {
                      const m = text.match(/(?:花费（元）|花费\\(元\\))[^0-9+\\-−]*([+\\-−]?\\d[\\d,]*(?:\\.\\d+)?)/);
                      if (m && m[1]) return m[1];
                    }
                    node = node.parentElement;
                  }

                  // 邻近数字兜底：取标签下方最近主值
                  const parent = label.parentElement || label;
                  const nums = Array.from(parent.querySelectorAll('div, span, p, strong, b'))
                    .filter(visible)
                    .map((el) => {
                      const t = normalize(el.innerText || '');
                      const rect = el.getBoundingClientRect();
                      return { el, t, rect };
                    })
                    .filter((item) => {
                      if (!item.t) return false;
                      if (item.t.includes('对比') || item.t.includes('%')) return false;
                      if (!/^[¥￥]?[+\\-−]?\\d[\\d,]*(?:\\.\\d+)?$/.test(item.t)) return false;
                      const dy = item.rect.y - lr.y;
                      return dy >= 8 && dy <= 130 && Math.abs(item.rect.x - lr.x) <= 220;
                    });
                  nums.sort((a, b) => (a.rect.y - b.rect.y) || (a.rect.x - b.rect.x));
                  if (nums.length) return nums[0].t;
                }
                return '';
                """
            )
            parsed = self._token_to_float(str(token or "").replace("−", "-"))
            if parsed is not None:
                return round(abs(parsed), 2)
        except Exception:
            pass

        page_text = self._page_text_snippet(max_length=8000)
        for pattern in (
            r"(?:花费（元）|花费\(元\))[^0-9+\-−]*([+\-−]?\d[\d,]*(?:\.\d+)?)",
            r"数据汇总[^0-9+\-−]{0,80}(?:花费（元）|花费\(元\))[^0-9+\-−]*([+\-−]?\d[\d,]*(?:\.\d+)?)",
        ):
            match = re.search(pattern, page_text)
            if not match:
                continue
            parsed = self._token_to_float(match.group(1))
            if parsed is not None:
                return round(abs(parsed), 2)

        no_data_markers = ("暂无数据", "没有数据", "暂无结果", "--")
        if any(self._page_contains_text(marker) for marker in no_data_markers):
            self._log_step("人群报表无花费数据，推广费用按 0.00 处理")
            return 0.0

        self._raise_timeout_with_context("未读取到【数据汇总 -> 花费（元）】。")

    def _collect_promotion_fee(self, report_date: date | datetime | str | None = None) -> float:
        """
        采集推广费用：推广 -> 万相台ai无界 -> 报表 -> 人群报表 -> 指定日期 -> 花费（元）。
        """
        try:
            self._open_promotion_then_wanxiangtai_page()
        except TimeoutException as exc:
            if "未找到【万相台ai无界】入口" not in str(exc):
                raise
            self._log_step("未找到万相台ai无界入口，推广费用按 0.00 处理")
            return 0.0
        if self._is_promotion_unavailable_page():
            self._log_step("万相台无界暂无权限，推广费用按 0.00 处理")
            return 0.0

        self._open_promotion_report_page()
        if self._is_promotion_unavailable_page():
            self._log_step("万相台无界暂无权限，推广费用按 0.00 处理")
            return 0.0

        report_date_str = self._format_report_date(report_date)
        self._set_promotion_report_date(report_date_str)
        time.sleep(max(self.interaction_delay_seconds * 2.5, 0.3))
        fee = self._extract_promotion_spend_fee()
        self._log_step(f"人群报表推广费用（花费）：{fee}")
        return fee

    def _ensure_douyin_runtime_context(self) -> None:
        """
        切换到抖店流程时，注入抖店域名配置，避免附着模式误判为千牛域名。
        """
        if "jinritemai" not in (self.export_url or "").lower():
            self.export_url = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"
        if "jinritemai" not in (self.expected_url_prefix or "").lower():
            self.expected_url_prefix = "https://fxg.jinritemai.com/"
        if not (self.login_url or "").strip():
            self.login_url = self.export_url

    def _switch_to_existing_douyin_page(self) -> bool:
        """
        附着已有浏览器时，优先切到真实可用的抖店/罗盘标签页，跳过空白或 404 标签。
        """
        driver = self._ensure_driver()
        candidates: list[tuple[int, str]] = []

        try:
            handles = list(driver.window_handles)
        except Exception:
            handles = []

        for handle in handles:
            try:
                driver.switch_to.window(handle)
                current_url = (driver.current_url or "").strip().lower()
            except Exception:
                continue

            if "jinritemai.com" not in current_url:
                continue

            try:
                page_text = str(
                    driver.execute_script(
                        "return (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();"
                    )
                    or ""
                )
            except Exception:
                page_text = ""

            text_lower = page_text.lower()
            if not page_text or "404 page not found" in text_lower:
                continue

            score = 10
            if self._is_douyin_compass_url(current_url) or self._is_douyin_compass_page_by_content():
                score += 2000
            if "/ffa/mshop/homepage" in current_url:
                score += 800
            if "电商罗盘" in page_text:
                score += 200
            if (driver.title or "").strip() == "首页":
                score += 50

            candidates.append((score, handle))

        if not candidates:
            return False

        _, selected_handle = max(candidates, key=lambda item: item[0])
        driver.switch_to.window(selected_handle)
        return True

    @staticmethod
    def _is_douyin_compass_url(url: str) -> bool:
        """
        判定是否已进入抖店“电商罗盘”页面。
        """
        current_url = (url or "").strip().lower()
        if not current_url or "jinritemai.com" not in current_url:
            return False

        compass_hints = (
            "compass",
            "ecommerce",
            "business-compass",
            "/ecp/",
            "#/compass",
        )
        return any(hint in current_url for hint in compass_hints)

    def _is_douyin_compass_page_by_content(self) -> bool:
        """
        通过页面特征判断是否已进入电商罗盘数据面板。
        """
        current_url = (self.get_current_url() or "").lower()
        if "jinritemai.com" not in current_url:
            return False
        driver = self._ensure_driver()
        page_title = ""
        try:
            page_title = str(driver.title or "")
        except Exception:
            page_title = ""
        if not self._is_douyin_compass_url(current_url) and "罗盘" not in page_title:
            return False
        required_markers = ("成交金额", "成交订单数", "支出金额")
        return all(self._page_contains_text(marker) for marker in required_markers)

    def _wait_switch_to_douyin_compass_page(
        self,
        previous_handles: set[str],
        timeout_seconds: float = 18.0,
    ) -> bool:
        """
        等待切换到抖店“电商罗盘”页面，兼容同页跳转与新标签页。
        """
        driver = self._ensure_driver()
        end_time = time.time() + max(timeout_seconds, 5.0)

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

                if self._is_douyin_compass_url(current_url):
                    return True
                if self._is_douyin_compass_page_by_content():
                    return True

            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
        return False

    def _close_douyin_notice_popup_if_present(self) -> bool:
        """
        关闭抖店首页弹窗（“我知道了”或右上角 X）。
        """
        closed = False
        for _ in range(4):
            clicked_ack = (
                self._try_click_selector("douyin_popup_ack_button", timeout_seconds=1.2)
                or self._click_text_with_wait(("我知道了",), exact=False, timeout_seconds=1.6, required=False)
            )
            if clicked_ack:
                closed = True
                self._promotion_pause(0.6)
                continue

            clicked_close = self._quick_click_any("douyin_popup_close_button")
            if clicked_close:
                closed = True
                self._promotion_pause(0.6)
                continue

            break
        if closed:
            self._log_step("已关闭抖店弹窗提醒")
        return closed

    def _open_douyin_compass_page(self) -> None:
        """
        点击顶部导航【电商罗盘】，并切到罗盘数据页面。
        """
        current_url = (self.get_current_url() or "").lower()
        if self._is_douyin_compass_url(current_url):
            if "refund-analysis" in current_url or "business-part" in current_url:
                driver = self._ensure_driver()
                driver.get("https://compass.jinritemai.com/shop")
                self._wait_dom_ready()
                self._promotion_pause(1.0)
            self._wait_until(
                self._is_douyin_compass_page_by_content,
                timeout_seconds=max(self.timeout_seconds, 20),
                message="电商罗盘页面未加载完成（未识别到成交金额/成交订单数/支出金额）。",
                selector_keys=("douyin_period_last_1day_tab",),
            )
            self._close_douyin_notice_popup_if_present()
            self._log_step("已在电商罗盘页面")
            return

        self._switch_default_content()
        self._close_douyin_notice_popup_if_present()
        previous_handles = self._capture_window_handles()

        clicked = (
            self._try_click_selector("douyin_compass_entry", timeout_seconds=max(self.timeout_seconds, 8))
            or self._click_text_with_wait(("电商罗盘",), exact=False, timeout_seconds=max(self.timeout_seconds, 8), required=False)
        )
        if not clicked:
            self._log_step("未直接点到顶部【电商罗盘】，改用罗盘 URL 兜底")
            driver = self._ensure_driver()
            driver.get("https://compass.jinritemai.com/shop")
            self._wait_dom_ready()
            self._promotion_pause(1.0)
            self._close_douyin_notice_popup_if_present()
            self._wait_until(
                lambda: self._is_douyin_compass_url(self.get_current_url() or "")
                or self._is_douyin_compass_page_by_content(),
                timeout_seconds=max(self.timeout_seconds, 15),
                message="点击【电商罗盘】后未进入罗盘页面。",
                selector_keys=("douyin_compass_entry",),
            )
            self._wait_until(
                self._is_douyin_compass_page_by_content,
                timeout_seconds=max(self.timeout_seconds, 20),
                message="电商罗盘页面未加载完成（未识别到成交金额/成交订单数/支出金额）。",
                selector_keys=("douyin_period_last_1day_tab",),
            )
            self._close_douyin_notice_popup_if_present()
            self._log_step("已进入电商罗盘页面")
            return
        self._log_step("已进入顶部导航：电商罗盘")
        self._promotion_pause(1.0)

        switched = self._wait_switch_to_douyin_compass_page(
            previous_handles=previous_handles,
            timeout_seconds=max(self.timeout_seconds, 20),
        )
        if not switched and not (
            self._is_douyin_compass_url(self.get_current_url() or "")
            or self._is_douyin_compass_page_by_content()
        ):
            self._log_step("点击【电商罗盘】后未直接切页，改用罗盘 URL 兜底")
            driver = self._ensure_driver()
            driver.get("https://compass.jinritemai.com/shop")
            self._wait_dom_ready()
            self._promotion_pause(1.0)
            self._close_douyin_notice_popup_if_present()
            self._wait_until(
                lambda: self._is_douyin_compass_url(self.get_current_url() or "")
                or self._is_douyin_compass_page_by_content(),
                timeout_seconds=max(self.timeout_seconds, 15),
                message="点击【电商罗盘】后未进入罗盘页面。",
                selector_keys=("douyin_compass_entry",),
            )

        self._wait_until(
            self._is_douyin_compass_page_by_content,
            timeout_seconds=max(self.timeout_seconds, 20),
            message="电商罗盘页面未加载完成（未识别到成交金额/成交订单数/支出金额）。",
            selector_keys=("douyin_period_last_1day_tab",),
        )
        self._close_douyin_notice_popup_if_present()
        self._log_step("已进入电商罗盘页面")

    def _is_douyin_period_last_1day_selected(self) -> bool:
        """
        判断电商罗盘周期是否已选中“近1天”。
        """
        driver = self._ensure_driver()
        try:
            selected = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                    };
                    const selectedByNode = (node) => {
                      if (!node) return false;
                      const attrs = ['aria-selected', 'aria-checked', 'aria-pressed', 'data-selected', 'data-active'];
                      for (const key of attrs) {
                        const value = String(node.getAttribute(key) || '').toLowerCase();
                        if (value === 'true' || value === '1' || value === 'yes' || value === 'active' || value === 'selected') return true;
                      }
                      const cls = String(node.className || '').toLowerCase();
                      return /(\\bactive\\b|\\bselected\\b|\\bcurrent\\b|\\bchecked\\b|\\bon\\b)/.test(cls);
                    };

                    const nodes = Array.from(document.querySelectorAll('button, a, span, div'))
                      .filter(visible)
                      .filter((node) => {
                        const text = normalize(node.innerText || node.textContent || '');
                        return text === '近1天' || text === '近1日';
                      });
                    for (const node of nodes) {
                      if (selectedByNode(node)) return true;
                      let current = node.parentElement;
                      for (let i = 0; i < 3 && current; i += 1) {
                        if (selectedByNode(current)) return true;
                        current = current.parentElement;
                      }
                    }
                    return false;
                    """
                )
            )
            return selected
        except Exception:
            return False

    def _set_douyin_period_last_1day(self) -> None:
        """
        在电商罗盘中切换周期到“近1天”。
        """
        if self._is_douyin_period_last_1day_selected():
            self._log_step("电商罗盘已选择周期：近1天")
            return

        for _ in range(4):
            clicked = (
                self._try_click_selector("douyin_period_last_1day_tab", timeout_seconds=1.8)
                or self._click_text_with_wait(("近1天", "近1日"), exact=True, timeout_seconds=2.0, required=False)
            )
            if clicked:
                self._promotion_pause(0.9)
                if self._is_douyin_period_last_1day_selected():
                    self._log_step("电商罗盘已选择周期：近1天")
                    return
            else:
                self._promotion_pause(0.5)

        # 某些场景选中态 class 不稳定，这里允许软校验通过继续执行。
        if self._page_contains_text("近1天") or self._page_contains_text("近1日"):
            self._log_step("电商罗盘周期选中态未稳定识别，继续按【近1天】读取数据")
            return

        self._raise_timeout_with_context(
            "未能将电商罗盘周期切换到【近1天】。",
            selector_keys=("douyin_period_last_1day_tab",),
        )

    def _set_douyin_compass_report_date(self, report_date: date | datetime | str) -> None:
        """
        在抖音电商罗盘首页选择指定单日；默认昨日仍使用“近1天”，历史日期走“自定义”。
        """
        target = self._format_report_date(report_date)
        if target == DateConfig.default_report_date_str():
            self._set_douyin_period_last_1day()
            return

        if self._is_douyin_compass_report_date_selected(target):
            self._log_step(f"电商罗盘已选择日期：{target}")
            return

        before_metric_signature = self._douyin_compass_metric_signature()
        if not self._open_douyin_compass_custom_date_picker():
            self._raise_timeout_with_context(
                "电商罗盘未找到【自定义】日期按钮。",
                selector_keys=("douyin_period_custom_tab",),
            )

        if not self._is_douyin_compass_custom_date_picker_open():
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        if not self._is_douyin_compass_custom_date_picker_open():
            self._raise_timeout_with_context("电商罗盘自定义日期面板未打开。")

        if not self._click_douyin_compass_calendar_day_twice(target):
            self._raise_timeout_with_context(f"电商罗盘未能选择日期：{target}")

        try:
            self._wait_until(
                lambda: self._is_douyin_compass_report_date_selected(target),
                timeout_seconds=max(min(self.timeout_seconds, 8), 4),
                message=f"电商罗盘日期未切换到：{target}",
                selector_keys=("douyin_period_custom_tab",),
            )
        except TimeoutException:
            if not self._did_douyin_compass_refresh_after_date_pick(before_metric_signature):
                raise
            self._log_step("图表日期文本未能自动读取，已按核心指标刷新确认日期选择生效")
        self._log_step(f"电商罗盘已选择日期：{target}")

    def _douyin_compass_metric_signature(self) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        返回罗盘首页三项核心指标签名，用于判断日期切换后的异步刷新。
        """
        snippet = self._page_text_snippet(max_length=16000)
        return (
            self._extract_metric_value_after_label_from_text(snippet, "成交金额"),
            self._extract_metric_value_after_label_from_text(snippet, "成交订单数"),
            self._extract_metric_value_after_label_from_text(snippet, "支出金额"),
        )

    def _did_douyin_compass_refresh_after_date_pick(
        self,
        before_metric_signature: tuple[Optional[float], Optional[float], Optional[float]],
    ) -> bool:
        """
        当图表日期轴不可从 DOM 读取时，用日期面板关闭和核心指标变化确认切换生效。
        """
        if self._is_douyin_compass_custom_date_picker_open():
            return False
        after_metric_signature = self._douyin_compass_metric_signature()
        if not any(value is not None for value in before_metric_signature):
            return any(value is not None for value in after_metric_signature)
        return after_metric_signature != before_metric_signature

    def _open_douyin_compass_custom_date_picker(self) -> bool:
        """
        点击/悬停“自定义”按钮，打开电商罗盘日期选择器。
        """
        driver = self._ensure_driver()
        candidates: list[WebElement] = []
        for locator in self.selectors.get("douyin_period_custom_tab", ()):
            try:
                candidates.extend(driver.find_elements(*locator))
            except Exception:
                continue

        for element in candidates:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                ActionChains(driver).move_to_element(element).pause(0.8).perform()
                time.sleep(max(self.ui_poll_interval_seconds, 0.2))
                if self._is_douyin_compass_custom_date_picker_open():
                    return True
                ActionChains(driver).move_to_element(element).pause(0.1).click().perform()
                time.sleep(max(self.ui_poll_interval_seconds, 0.2))
                if self._is_douyin_compass_custom_date_picker_open():
                    return True
            except Exception:
                try:
                    self._click_with_retry(element)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.2))
                    if self._is_douyin_compass_custom_date_picker_open():
                        return True
                except Exception:
                    continue

        clicked = self._try_click_selector("douyin_period_custom_tab", timeout_seconds=2.0) or self._click_text_with_wait(
            ("自定义",),
            exact=True,
            timeout_seconds=2.0,
            required=False,
        )
        if clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        return bool(clicked and self._is_douyin_compass_custom_date_picker_open())

    def _is_douyin_compass_custom_date_picker_open(self) -> bool:
        """
        判断电商罗盘自定义双月日期面板是否已打开。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 360 && rect.height >= 220
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 80;
                    };
                    return Array.from(document.querySelectorAll('div, section'))
                      .some((el) => {
                        if (!visible(el)) return false;
                        const text = normalize(el.innerText || el.textContent || '');
                        const monthCount = (text.match(/20\\d{2}年\\s*\\d{1,2}月/g) || []).length;
                        return monthCount >= 1 && text.includes('自定义支持至多连续31天');
                      });
                    """
                )
            )
        except Exception:
            return False

    def _click_douyin_compass_calendar_day_twice(self, report_date: str) -> bool:
        """
        在电商罗盘自定义日期面板中连续点击目标日期两次，选择单日范围。
        """
        target = self._format_report_date(report_date)
        if not self._bring_douyin_compass_calendar_month_into_view(target):
            return False

        first_clicked = self._click_douyin_compass_calendar_day(target)
        if first_clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.18))
        second_clicked = self._click_douyin_compass_calendar_day(target)
        if second_clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.25))
        return bool(first_clicked and second_clicked)

    def _bring_douyin_compass_calendar_month_into_view(self, report_date: str) -> bool:
        """
        尝试把电商罗盘日期面板翻到目标月份。
        """
        target = self._format_report_date(report_date)
        target_year, target_month, _target_day = (int(part) for part in target.split("-"))
        driver = self._ensure_driver()

        for _ in range(14):
            visible_months = self._extract_douyin_compass_calendar_months()
            if any((year, month) == (target_year, target_month) for year, month in visible_months):
                return True
            if not visible_months:
                return False

            min_month = min(visible_months)
            max_month = max(visible_months)
            direction = "next" if (target_year, target_month) > max_month else "prev"
            try:
                clicked = bool(
                    driver.execute_script(
                        """
                        const direction = arguments[0];
                        const visible = (el) => {
                          if (!el) return false;
                          const style = getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width >= 8 && rect.height >= 8
                            && rect.bottom >= 0 && rect.top <= window.innerHeight + 120;
                        };
                        const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                        const panelRoots = Array.from(document.querySelectorAll(
                          '.auxo-picker-panel, .auxo-picker-date-panel, .auxo-picker-dropdown, ' +
                          '.sp-range-picker-join-dropdown, [class*="picker-panel"], [class*="picker-dropdown"], [class*="date-panel"]'
                        ))
                          .filter(visible)
                          .filter((el) => /20\\d{2}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent || '')));
                        const searchRoots = panelRoots.length ? panelRoots : [document];
                        const nodes = searchRoots.flatMap((root) => Array.from(root.querySelectorAll('button, span, div, i, svg')))
                          .filter(visible)
                          .map((el) => {
                            const rect = el.getBoundingClientRect();
                            const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');
                            const cls = String(el.className || '').toLowerCase();
                            const cleanCls = cls.replace(/placement-[a-z-]+/g, ' ');
                            const hint = `${text} ${cleanCls}`.toLowerCase();
                            const isCalendarNav = /picker-header-(super-)?(prev|next)-btn|picker-(super-)?(prev|next)-icon|\\b(prev|next)-btn\\b|\\b(prev|next)-icon\\b/.test(cleanCls)
                              || /^[<>‹›«»]$/.test(text)
                              || /上个月|上一月|下个月|下一月|上一年|下一年/.test(text);
                            const isJumpArrow = /«|»|super|jump|double|year|年份|年度|上一年|下一年/.test(hint);
                            let singleArrowScore = 0;
                            if (isCalendarNav && !isJumpArrow) {
                              if (direction === 'prev' && (/‹|<|上个月|上一月|prev|left|previous/.test(hint))) singleArrowScore = 2;
                              if (direction === 'next' && (/›|>|下个月|下一月|next|right/.test(hint))) singleArrowScore = 2;
                            }
                            return { el, rect, text, cls, hint, isCalendarNav, isJumpArrow, singleArrowScore };
                          })
                          .filter((item) => item.isCalendarNav)
                          .filter((item) => {
                            if (direction === 'prev') {
                              return /上|prev|left|previous|«|‹/.test(item.hint) || item.text === '<' || item.text === '‹';
                            }
                            return /下|next|right|»|›/.test(item.hint) || item.text === '>' || item.text === '›';
                          });
                        nodes.sort((a, b) => {
                          if (b.singleArrowScore !== a.singleArrowScore) return b.singleArrowScore - a.singleArrowScore;
                          if (a.isJumpArrow !== b.isJumpArrow) return a.isJumpArrow ? 1 : -1;
                          return direction === 'prev' ? a.rect.left - b.rect.left : b.rect.left - a.rect.left;
                        });
                        if (!nodes.length) return false;
                        const node = nodes[0].el;
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                        """,
                        direction,
                    )
                )
            except Exception:
                clicked = False

            if not clicked:
                return False
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))

        return False

    def _extract_douyin_compass_calendar_months(self) -> list[tuple[int, int]]:
        """
        读取电商罗盘日期面板当前可见月份。
        """
        driver = self._ensure_driver()
        try:
            raw_months = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 20 && rect.height >= 12
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 120;
                };
                const values = [];
                for (const el of Array.from(document.querySelectorAll('div, span, section'))) {
                  if (!visible(el)) continue;
                  const text = normalize(el.innerText || el.textContent || '');
                  const matches = text.matchAll(/(20\\d{2})年\\s*(\\d{1,2})月/g);
                  for (const match of matches) {
                    values.push(`${match[1]}-${String(match[2]).padStart(2, '0')}`);
                  }
                }
                return Array.from(new Set(values));
                """
            )
        except Exception:
            raw_months = []

        months: list[tuple[int, int]] = []
        for value in raw_months or []:
            try:
                year_text, month_text = str(value).split("-", 1)
                months.append((int(year_text), int(month_text)))
            except (TypeError, ValueError):
                continue
        return months

    def _click_douyin_compass_calendar_day(self, report_date: str) -> bool:
        """
        点击电商罗盘自定义日期面板中的目标日期。
        """
        driver = self._ensure_driver()
        target = self._format_report_date(report_date)
        target_year, target_month, target_day = (int(part) for part in target.split("-"))
        day_text = str(target_day)
        target_month_text = f"{target_year}年{target_month}月"
        target_month_padded_text = f"{target_year}年{target_month:02d}月"

        try:
            return bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '');
                    const targetMonthText = String(arguments[1] || '');
                    const targetMonthPaddedText = String(arguments[2] || '');
                    const dayText = String(arguments[3] || '');
                    const targetMonthVariants = [targetMonthText, targetMonthPaddedText]
                      .map((value) => value.replace(/\\s+/g, ''))
                      .filter(Boolean);
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 10 && rect.height >= 10
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 120;
                    };
                    const isDisabled = (el) => {
                      if (!el) return false;
                      const attrText = [
                        el.getAttribute('aria-disabled'),
                        el.getAttribute('disabled'),
                        el.getAttribute('class'),
                        el.parentElement && el.parentElement.getAttribute('class'),
                      ].join(' ').toLowerCase();
                      return /disabled/.test(attrText) || attrText.includes('true');
                    };
                    const clickNode = (node) => {
                      if (!node || isDisabled(node)) return false;
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                      return true;
                    };

                    const monthMatches = (text) => {
                      const compact = normalize(text).replace(/\\s+/g, '');
                      return targetMonthVariants.some((variant) => compact.includes(variant));
                    };
                    const panels = Array.from(document.querySelectorAll(
                      '.auxo-picker-panel, .auxo-picker-date-panel, .auxo-picker-dropdown, ' +
                      '.sp-range-picker-join-dropdown, [class*="picker-panel"], [class*="picker-dropdown"], [class*="date-panel"]'
                    ))
                      .filter(visible)
                      .map((panel) => ({ panel, text: normalize(panel.innerText || panel.textContent || ''), rect: panel.getBoundingClientRect() }))
                      .filter((item) => monthMatches(item.text));
                    panels.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);

                    const searchRoots = panels.length ? panels.map((item) => item.panel) : [document];
                    for (const panel of searchRoots) {
                      const attrMatches = Array.from(panel.querySelectorAll('[title], [aria-label], [data-date]'))
                        .filter(visible)
                        .filter((el) => {
                          const text = `${el.getAttribute('title') || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-date') || ''}`;
                          return text.includes(target) && !isDisabled(el);
                        });
                      if (attrMatches.length) return clickNode(attrMatches[0]);

                      const candidates = Array.from(panel.querySelectorAll('td, .auxo-picker-cell, .auxo-picker-cell-inner, button, span, div'))
                        .filter(visible)
                        .map((el) => ({ el, text: normalize(el.innerText || el.textContent || ''), rect: el.getBoundingClientRect() }))
                        .filter((item) => item.text === dayText && !isDisabled(item.el))
                        .filter((item) => {
                          const cls = String(item.el.className || '').toLowerCase();
                          const tag = item.el.tagName.toLowerCase();
                          return tag === 'td' || cls.includes('picker-cell') || cls.includes('day') || cls.includes('date');
                        });
                      candidates.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                      if (candidates.length) return clickNode(candidates[0].el);
                    }
                    return false;
                    """,
                    target,
                    target_month_text,
                    target_month_padded_text,
                    day_text,
                )
            )
        except Exception:
            return False

    def _is_douyin_compass_report_date_selected(self, report_date: str) -> bool:
        """
        通过页面文案/图表横轴判断电商罗盘是否已切换到目标单日。
        """
        target = self._format_report_date(report_date)
        month_day = datetime.strptime(target, DateConfig.DATE_FORMAT).strftime("%m/%d")
        compact_month_day = month_day.lstrip("0")
        text = self._page_text_snippet(max_length=12000)
        compact = re.sub(r"\s+", "", text)
        if target in text or month_day in text or compact_month_day in text:
            return True
        return bool(self._douyin_compass_chart_contains_date(month_day))

    def _douyin_compass_chart_contains_date(self, month_day: str) -> bool:
        """
        读取图表 SVG/canvas 周边文本，确认横轴出现目标 MM/DD。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '');
                    const variants = new Set([target, target.replace(/^0/, '')]);
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 4 && rect.height >= 4
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 260;
                    };
                    const nodes = Array.from(document.querySelectorAll('svg text, canvas, div, span'))
                      .filter(visible);
                    for (const node of nodes) {
                      const text = normalize(node.innerText || node.textContent || node.getAttribute('aria-label') || node.getAttribute('title') || '');
                      for (const variant of variants) {
                        if (text.includes(variant)) return true;
                      }
                    }
                    return false;
                    """,
                    month_day,
                )
            )
        except Exception:
            return False

    @classmethod
    def _extract_metric_value_after_label_from_text(cls, text: str, label: str) -> Optional[float]:
        """
        从页面顺序文本中读取指标名后紧跟的主数值，避免取到较上期/同行标杆等对比值。
        """
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        target_label = str(label or "").strip()
        if not normalized or not target_label:
            return None

        label_pattern = re.escape(target_label)
        pattern = re.compile(
            rf"(?<![\u4e00-\u9fffA-Za-z0-9]){label_pattern}\s*[：:]?\s*[¥￥]?\s*"
            r"([+\-−]?\d[\d,]*(?:\s*\.\s*\d+)?)\s*([万亿]?)"
        )
        for match in pattern.finditer(normalized):
            parsed = cls._token_to_float(re.sub(r"\s+", "", match.group(1)))
            if parsed is None:
                continue
            unit = (match.group(2) or "").strip()
            if unit == "万":
                parsed *= 10000
            elif unit == "亿":
                parsed *= 100000000
            return round(parsed, 2)

        return None

    def _extract_douyin_compass_metric(self, label: str) -> float:
        """
        在电商罗盘读取指定指标值。
        """
        driver = self._ensure_driver()

        snippet = self._page_text_snippet(max_length=30000)
        parsed_from_text = self._extract_metric_value_after_label_from_text(snippet, label)
        if parsed_from_text is not None:
            return round(abs(parsed_from_text), 2)

        if re.search(rf"{re.escape(label)}[^\n\r]{{0,20}}(--|—|-)", snippet):
            return 0.0

        try:
            token = driver.execute_script(
                """
                const targetLabel = String(arguments[0] || '').trim();
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 18 && rect.height >= 12 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 320;
                };
                const parseToken = (text) => {
                  const raw = normalize(text);
                  if (!raw || raw.length > 36) return '';
                  if (/%|同比|环比|较前|昨日|今日|近7天|近30天/.test(raw)) return '';
                  if (/20\\d{2}[-\\/.]\\d{1,2}[-\\/.]\\d{1,2}/.test(raw)) return '';
                  const m = raw.match(/[¥￥]?\\s*[+\\-−]?\\d[\\d,]*(?:\\.\\d+)?/);
                  if (!m || !m[0]) return '';
                  return m[0];
                };
                const candidates = [];
                const labels = Array.from(document.querySelectorAll('div, span, p, strong, b'))
                  .filter(visible)
                  .filter((el) => {
                    const t = normalize(el.innerText || el.textContent || '');
                    return t === targetLabel || t.includes(targetLabel);
                  });

                for (const labelNode of labels) {
                  const lr = labelNode.getBoundingClientRect();
                  let scope = labelNode.parentElement;
                  for (let depth = 0; depth < 6 && scope; depth += 1) {
                    const scopeText = normalize(scope.innerText || '');
                    if (!scopeText || scopeText.length > 900) {
                      scope = scope.parentElement;
                      continue;
                    }
                    const nodes = Array.from(scope.querySelectorAll('div, span, p, strong, b'))
                      .filter(visible);
                    for (const node of nodes) {
                      if (node === labelNode) continue;
                      const token = parseToken(node.innerText || node.textContent || '');
                      if (!token) continue;
                      const rect = node.getBoundingClientRect();
                      const dy = rect.top - lr.top;
                      const dx = Math.abs(rect.left - lr.left);
                      let score = 0;
                      if (dy >= -16 && dy <= 120) score += 120;
                      else if (dy > 120 && dy <= 220) score += 45;
                      if (dx <= 240) score += 80;
                      else if (dx <= 420) score += 30;
                      if (rect.width <= 280) score += 20;
                      if (rect.y <= Math.min(window.innerHeight * 0.82, 900)) score += 20;
                      candidates.push({ token, score });
                    }
                    scope = scope.parentElement;
                  }
                }
                candidates.sort((a, b) => b.score - a.score);
                return candidates.length ? candidates[0].token : '';
                """,
                label,
            )
            parsed = self._token_to_float(str(token or "").replace("¥", "").replace("￥", ""))
            if parsed is not None:
                return round(abs(parsed), 2)
        except Exception:
            pass

        pattern = rf"{re.escape(label)}[^\n\r0-9¥￥+\-−]{{0,24}}[¥￥]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)"
        match = re.search(pattern, snippet)
        if match:
            parsed = self._token_to_float(match.group(1))
            if parsed is not None:
                return round(abs(parsed), 2)

        self._raise_timeout_with_context(
            f"未读取到抖店电商罗盘指标：{label}",
            selector_keys=("douyin_period_last_1day_tab",),
        )

    def _extract_douyin_shop_name(self) -> str:
        """
        在抖店页面读取店铺名（读取失败时返回空字符串）。
        """
        driver = self._ensure_driver()
        try:
            value = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 40 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= 260;
                };
                const headerNodes = Array.from(document.querySelectorAll(
                  '#fxg-pc-header .headerShopName, #fxg-pc-header [class*="headerShopName"], [class*="headerShopName"], [class*="shopName"], [class*="ShopName"]'
                ))
                  .filter(visible)
                  .map((el) => normalize(el.innerText || el.textContent || ''))
                  .filter((text) => text && text.length >= 2 && text.length <= 36);
                if (headerNodes.length) return headerNodes[0];

                const blacklist = /消息|帮助|客服|登录|退出|工作台|电商罗盘|数据参谋|抖音号|ID[:：]|运费险|保费|流量|短视频|订单|商品|售后|资金|营销|活动|管理|中心|首页|规则|课程|服务市场/;
                const nodes = Array.from(document.querySelectorAll('div, span, p, a'))
                  .filter(visible)
                  .map((el) => {
                    const rect = el.getBoundingClientRect();
                    const text = normalize(el.innerText || '');
                    let score = 0;
                    if (rect.left >= window.innerWidth * 0.62 && rect.top <= 120) score += 260;
                    if (/(旗舰店|专卖店|专营店|店铺|小店|女装|女裤|裙裤|源头|高品|品质)/.test(text)) score += 140;
                    return { text, score };
                  })
                  .filter((item) => item.text && item.text.length >= 2 && item.text.length <= 36 && !blacklist.test(item.text))
                  .sort((a, b) => b.score - a.score)
                  .map((item) => item.text);
                for (const text of nodes) {
                  if (/店铺排行|看看我超过谁|第\\s*\\d+\\s*名/.test(text)) {
                    const name = normalize(text.split(/7日店铺排行|店铺排行|第\\s*\\d+\\s*名/)[0] || '');
                    if (name && name.length >= 2 && name.length <= 20) return name;
                    continue;
                  }
                  if (/(旗舰店|专卖店|专营店|店铺|小店)/.test(text)) return text;
                }
                for (const text of nodes) {
                  if (/^[\\u4e00-\\u9fffA-Za-z0-9][\\u4e00-\\u9fffA-Za-z0-9\\s_-]{1,18}$/.test(text)) return text;
                }
                return '';
                """
            )
            return str(value or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _normalize_douyin_shop_name(shop_name: str) -> str:
        """
        归一化抖店店铺名，用于去重比较。
        """
        return re.sub(r"\s+", "", str(shop_name or "")).strip()

    def _open_douyin_homepage(self) -> None:
        """
        回到抖店首页，作为切换组织/店铺的稳定入口。
        """
        self._ensure_douyin_runtime_context()
        driver = self._ensure_driver()
        homepage_url = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"

        try:
            current_url = (driver.current_url or "").strip().lower()
        except Exception:
            current_url = ""

        if "jinritemai.com" not in current_url or "/ffa/mshop/homepage" not in current_url:
            driver.get(homepage_url)
            try:
                self._wait_dom_ready()
            except Exception:
                pass
            self._promotion_pause(1.2)

        self._close_douyin_notice_popup_if_present()
        self._wait_until(
            lambda: "jinritemai.com" in (self.get_current_url() or "").lower()
            and (
                self._page_contains_text("电商罗盘")
                or self._page_contains_text("切换组织")
                or self._page_contains_text("店铺")
            ),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="抖店首页未加载完成，无法切换组织/店铺。",
            selector_keys=("douyin_compass_entry", "douyin_shop_switch_menu_item"),
        )

    def _get_current_douyin_home_shop_name(self) -> str:
        """
        回到抖店首页读取右上角真实店铺名，用于校正罗盘页正文干扰。
        """
        try:
            self._open_douyin_homepage()
            return self._extract_douyin_shop_name()
        except Exception as exc:
            self._log_step(f"抖店首页店铺名读取失败，继续使用页面识别值：{type(exc).__name__}: {exc}")
            return ""

    def _click_douyin_top_shop_name(self, current_shop_name: str = "") -> bool:
        """
        hover 右上角当前店铺名，展开账号/店铺菜单。
        """
        driver = self._ensure_driver()
        for locator in self.selectors.get("douyin_header_shop_hover_area", ()):
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    ActionChains(driver).move_to_element(element).pause(0.8).perform()
                    self._promotion_pause(0.7)
                    if self._page_contains_text("切换组织/店铺") or self._page_contains_text("切换组织"):
                        return True
                except (StaleElementReferenceException, WebDriverException):
                    continue

        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const currentShop = String(arguments[0] || '').replace(/\\s+/g, '').trim();
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const compact = (v) => normalize(v).replace(/\\s+/g, '');
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 24 && rect.height >= 14
                        && rect.x >= 0 && rect.y >= 0
                        && rect.y <= Math.max(180, window.innerHeight * 0.24);
                    };
                    const hoverNode = (node) => {
                      if (!node) return false;
                      let target = node;
                      for (let i = 0; i < 5 && target; i += 1) {
                        const tag = String(target.tagName || '').toLowerCase();
                        const role = String(target.getAttribute('role') || '').toLowerCase();
                        const cls = String(target.className || '').toLowerCase();
                        const cursor = window.getComputedStyle(target).cursor;
                        if (tag === 'button' || tag === 'a' || role === 'button'
                            || cursor === 'pointer' || /dropdown|trigger|account|shop|user|header/.test(cls)) {
                          break;
                        }
                        target = target.parentElement;
                      }
                      target = target || node;
                      try {
                        const rect = target.getBoundingClientRect();
                        const x = rect.left + rect.width / 2;
                        const y = rect.top + rect.height / 2;
                        for (const type of ['mouseover', 'mouseenter', 'mousemove']) {
                          target.dispatchEvent(new MouseEvent(type, {
                            bubbles: true,
                            clientX: x,
                            clientY: y,
                          }));
                        }
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };

                    const blacklist = /电商罗盘|订单|商品|售后|数据|首页|消息|帮助|客服|下载|搜索|通知|工作台|指南|进入|新手/;
                    const candidates = Array.from(document.querySelectorAll('button, a, div, span, p'))
                      .filter(visible)
                      .map((node) => {
                        const text = normalize(node.innerText || node.textContent || '');
                        const rect = node.getBoundingClientRect();
                        let score = 0;
                        if (!text || text.length < 2 || text.length > 42 || blacklist.test(text)) return null;
                        if (rect.left >= window.innerWidth * 0.48) score += 160;
                        if (rect.right >= window.innerWidth * 0.72) score += 90;
                        if (rect.top <= 120) score += 50;
                        if (currentShop && compact(text).includes(currentShop)) score += 500;
                        if (/旗舰店|专卖店|专营店|店铺|小店|女装|女裤|裙裤|源头|高品|品质/.test(text)) score += 130;
                        if (/蓝天|账号|ID[:：]|子账号|主账号/.test(text)) score -= 120;
                        return { node, score, text };
                      })
                      .filter(Boolean)
                      .sort((a, b) => b.score - a.score);
                    if (!candidates.length || candidates[0].score < 100) return false;
                    return hoverNode(candidates[0].node);
                    """,
                    current_shop_name,
                )
            )
            if clicked:
                self._promotion_pause(0.8)
            return clicked
        except Exception:
            return False

    def _open_douyin_shop_switcher(self, current_shop_name: str = "") -> bool:
        """
        打开【切换组织/店铺】弹层。没有入口时返回 False，便于单店铺账号直接结束。
        """
        self._open_douyin_homepage()
        if self._page_contains_text("请选择店铺"):
            return True

        for _ in range(3):
            if not self._page_contains_text("切换组织/店铺") and not self._page_contains_text("切换组织"):
                self._click_douyin_top_shop_name(current_shop_name=current_shop_name)

            clicked_switch = (
                self._try_click_selector("douyin_shop_switch_menu_item", timeout_seconds=2.0)
                or self._click_text_with_wait(
                    ("切换组织/店铺", "切换组织", "切换店铺"),
                    exact=False,
                    timeout_seconds=2.0,
                    required=False,
                )
            )
            if clicked_switch:
                self._promotion_pause(1.0)
                try:
                    self._wait_until(
                        lambda: self._page_contains_text("请选择店铺")
                        or bool(self._list_douyin_switchable_shops()),
                        timeout_seconds=6.0,
                        message="点击【切换组织/店铺】后未出现店铺选择弹层。",
                        selector_keys=("douyin_shop_switcher_title",),
                    )
                    return True
                except TimeoutException:
                    continue

            self._promotion_pause(0.6)

        self._log_step("抖店未找到【切换组织/店铺】入口，按单店铺流程结束")
        return False

    def _list_douyin_switchable_shops(self) -> list[str]:
        """
        读取【请选择店铺】弹层中的店铺名称。
        """
        driver = self._ensure_driver()
        try:
            raw_items = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 24 && rect.height >= 12
                    && rect.x >= 0 && rect.y >= 0
                    && rect.y <= window.innerHeight + 120;
                };
                const bad = /请选择店铺|选择店铺|切换组织|切换店铺|当前|进入|取消|确定|关闭|登录|退出|主账号|子账号|账号|ID[:：]|授权|官方账号|店铺类型|角色|搜索/;
                const roots = Array.from(document.querySelectorAll('[role="dialog"], .modal, .dialog, .semi-modal, .auxo-modal, div'))
                  .filter(visible)
                  .filter((node) => {
                    const text = normalize(node.innerText || '');
                    return text.includes('请选择店铺') || text.includes('选择店铺');
                  })
                  .sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (br.width * br.height) - (ar.width * ar.height);
                  });
                if (!roots.length) return [];
                const scope = roots[0];
                const primaryNames = Array.from(scope.querySelectorAll('[class*="introName"], [class*="shopName"], [class*="ShopName"]'))
                  .filter(visible)
                  .map((node) => normalize(node.innerText || node.textContent || ''))
                  .filter((text) => text && text.length >= 2 && text.length <= 32);
                if (primaryNames.length) return primaryNames;

                const out = [];
                const seen = new Set();
                const excluded = /抖店工作台|子账号|主账号|个体店|企业店|正常营业|停业|冻结|请选择店铺|选择店铺|切换组织|切换店铺|当前|进入|取消|确定|关闭|登录|退出|账号|ID[:：]|授权|官方账号|店铺类型|角色|搜索/;
                const nodes = Array.from(scope.querySelectorAll('div, span, p, button, a'))
                  .filter(visible);
                for (const node of nodes) {
                  const text = normalize(node.innerText || node.textContent || '');
                  if (!text || text.length < 2 || text.length > 32) continue;
                  if (text.includes('\\n') || bad.test(text) || excluded.test(text)) continue;
                  if (/^\\d+$/.test(text)) continue;
                  if (!/[\\u4e00-\\u9fffA-Za-z0-9]/.test(text)) continue;
                  if (!/(店|铺|源头|女装|女裤|裙裤|品质|高品|旗舰|专营|专卖|小店|[\\u4e00-\\u9fff]{2,})/.test(text)) continue;
                  const compact = text.replace(/\\s+/g, '');
                  if (seen.has(compact)) continue;
                  seen.add(compact);
                  out.push(text);
                }
                return out;
                """
            )
        except Exception:
            return []

        shops: list[str] = []
        for item in raw_items or []:
            shop_name = str(item or "").strip()
            normalized = self._normalize_douyin_shop_name(shop_name)
            if not normalized:
                continue
            if normalized not in {self._normalize_douyin_shop_name(name) for name in shops}:
                shops.append(shop_name)
        return shops

    def _click_douyin_shop_card(self, shop_name: str) -> bool:
        """
        在店铺选择弹层中点击指定店铺卡片。
        """
        target = str(shop_name or "").strip()
        if not target:
            return False

        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const targetText = String(arguments[0] || '').replace(/\\s+/g, '').trim();
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const compact = (v) => normalize(v).replace(/\\s+/g, '');
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 24 && rect.height >= 12
                        && rect.x >= 0 && rect.y >= 0
                        && rect.y <= window.innerHeight + 120;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      let target = node;
                      for (let i = 0; i < 7 && target; i += 1) {
                        const tag = String(target.tagName || '').toLowerCase();
                        const role = String(target.getAttribute('role') || '').toLowerCase();
                        const cls = String(target.className || '').toLowerCase();
                        const cursor = window.getComputedStyle(target).cursor;
                        const text = normalize(target.innerText || '');
                        if (tag === 'button' || tag === 'a' || role === 'button'
                            || cursor === 'pointer' || /card|item|shop|org|store|option/.test(cls)
                            || (text.includes('进入') && text.length <= 220)) {
                          break;
                        }
                        target = target.parentElement;
                      }
                      target = target || node;
                      try {
                        target.scrollIntoView({ block: 'center', inline: 'center' });
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        target.click();
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };
                    const candidates = Array.from(document.querySelectorAll('button, a, div, span, p'))
                      .filter(visible)
                      .map((node) => {
                        const text = normalize(node.innerText || node.textContent || '');
                        const key = compact(text);
                        if (!key || !key.includes(targetText)) return null;
                        let score = 200 - Math.abs(key.length - targetText.length);
                        if (key === targetText) score += 300;
                        const rect = node.getBoundingClientRect();
                        if (rect.width >= 60 && rect.height >= 20) score += 30;
                        return { node, score };
                      })
                      .filter(Boolean)
                      .sort((a, b) => b.score - a.score);
                    if (!candidates.length) return false;
                    return clickNode(candidates[0].node);
                    """,
                    target,
                )
            )
        except Exception:
            clicked = False

        if not clicked:
            clicked = self._click_text_with_wait((target,), exact=True, timeout_seconds=2.0, required=False)

        if clicked:
            self._promotion_pause(1.6)
        return clicked

    def _switch_to_next_unvisited_douyin_shop(self, visited_shop_names: tuple[str, ...]) -> str:
        """
        从店铺选择弹层中切换到下一个未采集店铺，成功时返回目标店铺名。
        """
        visited_normalized = {
            self._normalize_douyin_shop_name(shop_name) for shop_name in visited_shop_names if shop_name
        }
        current_shop_name = visited_shop_names[-1] if visited_shop_names else ""
        if not self._open_douyin_shop_switcher(current_shop_name=current_shop_name):
            return ""

        shop_names = self._list_douyin_switchable_shops()
        self._log_step(f"抖店可切换店铺：{shop_names}")
        target_shop = ""
        for shop_name in shop_names:
            if self._normalize_douyin_shop_name(shop_name) not in visited_normalized:
                target_shop = shop_name
                break

        if not target_shop:
            self._log_step("抖店店铺已全部采集完成")
            return ""

        if not self._click_douyin_shop_card(target_shop):
            self._raise_timeout_with_context(
                f"未能点击抖店店铺：{target_shop}",
                selector_keys=("douyin_shop_switcher_title",),
            )

        self._wait_until(
            lambda: not self._page_contains_text("请选择店铺")
            or target_shop in self._page_text_snippet(max_length=5000),
            timeout_seconds=max(self.timeout_seconds, 15),
            message=f"切换抖店店铺后页面未完成刷新：{target_shop}",
            selector_keys=("douyin_shop_switcher_title", "douyin_compass_entry"),
        )
        self._close_douyin_notice_popup_if_present()
        self._log_step(f"已切换抖店店铺：{target_shop}")
        return target_shop

    @staticmethod
    def _is_douyin_refund_analysis_url(url: str) -> bool:
        """
        判定是否已进入抖店罗盘“全店退款分析”页面。
        """
        current_url = (url or "").strip().lower()
        return "jinritemai.com" in current_url and "refund-analysis" in current_url

    def _is_douyin_refund_analysis_page_by_content(self) -> bool:
        """
        通过稳定文案判断是否已在“全店退款分析”页面。
        """
        current_url = (self.get_current_url() or "").lower()
        if "jinritemai.com" not in current_url:
            return False
        markers = ("全店退款分析", "本店数据", "下载明细")
        return all(self._page_contains_text(marker) for marker in markers)

    def _click_douyin_business_more_data_by_js(self) -> bool:
        """
        点击罗盘首页“经营概况”卡片中的【查看更多数据】，优先选择页面左侧入口。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 24 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 260;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      try {
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                      } catch (err) {
                        return false;
                      }
                    };

                    const candidates = Array.from(document.querySelectorAll('a, button, span, div'))
                      .filter(visible)
                      .filter((node) => normalize(node.innerText || node.textContent || '').includes('查看更多数据'));
                    if (!candidates.length) return false;

                    let best = null;
                    let bestScore = -1;
                    for (const node of candidates) {
                      const rect = node.getBoundingClientRect();
                      let scope = node.parentElement;
                      let scopeText = '';
                      for (let i = 0; i < 6 && scope; i += 1) {
                        const text = normalize(scope.innerText || '');
                        if (text.length > scopeText.length && text.length <= 1800) scopeText = text;
                        scope = scope.parentElement;
                      }
                      let score = 100;
                      if (scopeText.includes('经营概况')) score += 240;
                      if (scopeText.includes('收支概况')) score -= 180;
                      if (rect.left < window.innerWidth * 0.58) score += 120;
                      if (rect.top < window.innerHeight * 0.65) score += 40;
                      if (score > bestScore) {
                        best = node;
                        bestScore = score;
                      }
                    }
                    return clickNode(best);
                    """
                )
            )
        except Exception:
            return False

    def _open_douyin_refund_analysis_page(self) -> None:
        """
        打开抖音罗盘“全店退款分析”页面。
        """
        driver = self._ensure_driver()
        if self._is_douyin_refund_analysis_url(self.get_current_url() or ""):
            self._wait_until(
                self._is_douyin_refund_analysis_page_by_content,
                timeout_seconds=max(self.timeout_seconds, 20),
                message="全店退款分析页面未加载完成。",
                selector_keys=("douyin_refund_download_detail_button",),
            )
            return

        if not self._is_douyin_compass_url(self.get_current_url() or ""):
            self._open_douyin_compass_page()

        previous_handles = self._capture_window_handles()
        clicked_more = (
            self._click_douyin_business_more_data_by_js()
            or self._try_click_selector("douyin_business_more_data_link", timeout_seconds=3.0)
            or self._click_text_with_wait(("查看更多数据",), exact=False, timeout_seconds=3.0, required=False)
        )
        if clicked_more:
            self._promotion_pause(1.0)
            self._wait_switch_to_douyin_compass_page(
                previous_handles=previous_handles,
                timeout_seconds=max(self.timeout_seconds, 10),
            )

        if not self._page_contains_text("全店退款分析") and "business-part" not in (
            self.get_current_url() or ""
        ).lower():
            driver.get("https://compass.jinritemai.com/shop/business-part")
            self._wait_dom_ready()
            self._promotion_pause(1.0)

        clicked_refund = (
            self._try_click_selector("douyin_refund_analysis_menu", timeout_seconds=5.0)
            or self._click_text_with_wait(("全店退款分析",), exact=True, timeout_seconds=5.0, required=False)
        )
        if not clicked_refund and not self._is_douyin_refund_analysis_url(self.get_current_url() or ""):
            driver.get("https://compass.jinritemai.com/shop/refund-analysis")

        self._wait_until(
            lambda: self._is_douyin_refund_analysis_url(self.get_current_url() or "")
            or self._is_douyin_refund_analysis_page_by_content(),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="未进入抖店罗盘【全店退款分析】页面。",
            selector_keys=("douyin_refund_analysis_menu", "douyin_refund_download_detail_button"),
        )
        self._wait_until(
            self._is_douyin_refund_analysis_page_by_content,
            timeout_seconds=max(self.timeout_seconds, 20),
            message="全店退款分析页面未加载完成。",
            selector_keys=("douyin_refund_download_detail_button",),
        )
        self._log_step("已进入菜单：全店退款分析")

    def _set_douyin_refund_analysis_period_last_1day(self) -> None:
        """
        在全店退款分析页面切换周期为“近1天”。
        """
        clicked = (
            self._try_click_selector("douyin_refund_period_last_1day_tab", timeout_seconds=3.0)
            or self._click_text_with_wait(("近1天", "近1日"), exact=True, timeout_seconds=3.0, required=False)
        )
        if clicked:
            self._promotion_pause(1.0)
        if self._page_contains_text("近1天") or self._page_contains_text("近1日"):
            self._log_step("全店退款分析已选择周期：近1天")
            return
        self._raise_timeout_with_context(
            "未能将全店退款分析周期切换到【近1天】。",
            selector_keys=("douyin_refund_period_last_1day_tab",),
        )

    def _download_douyin_refund_analysis_detail(self, download_dir: Path) -> Path:
        """
        点击【下载明细】并等待抖音退款分析明细文件下载完成。
        """
        target_dir = Path(download_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        snapshot = snapshot_directory(target_dir)
        trigger_ts = time.time()
        clicked = (
            self._try_click_selector("douyin_refund_download_detail_button", timeout_seconds=5.0)
            or self._click_text_with_wait(("下载明细",), exact=True, timeout_seconds=5.0, required=False)
        )
        if not clicked:
            self._raise_timeout_with_context(
                "未找到全店退款分析【下载明细】按钮。",
                selector_keys=("douyin_refund_download_detail_button",),
            )
        self._log_step("全店退款分析已点击：下载明细")

        try:
            detail_file = wait_for_download_complete(
                directory=target_dir,
                timeout_seconds=max(self.download_wait_seconds, 90),
                poll_interval_seconds=1.0,
                start_time=trigger_ts,
                previous_snapshot=snapshot,
                temp_suffixes=(".crdownload", ".part", ".tmp"),
                file_filter=lambda file_path: (
                    file_path.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".et"}
                    and not file_path.name.startswith("~$")
                    and ("退款分析" in file_path.name or "refund" in file_path.name.lower())
                ),
            )
        except TimeoutError as exc:
            raise TimeoutException(f"全店退款分析明细下载超时：{target_dir}") from exc
        self._log_step(f"全店退款分析明细已下载：{detail_file}")
        return detail_file

    def _collect_douyin_refund_analysis_summary(self, download_dir: Path) -> dict[str, Any]:
        """
        下载并汇总抖音罗盘“全店退款分析”明细。
        """
        from qianiu_auto_report.data_process import DataProcessor

        self._open_douyin_refund_analysis_page()
        self._set_douyin_refund_analysis_period_last_1day()
        detail_file = self._download_douyin_refund_analysis_detail(download_dir=download_dir)
        summary = DataProcessor().summarize_douyin_refund_analysis(detail_file)
        refund_metrics = summary.get("douyin_refund_metrics", {})
        self._log_step(
            "全店退款分析汇总："
            f"退款总订单数={refund_metrics.get('refund_total_order_count', 0)}，"
            f"退款总金额={refund_metrics.get('refund_total_amount', 0.0)}，"
            f"发货前退款订单数={refund_metrics.get('pre_shipment_refund_order_count', 0)}，"
            f"发货前退款金额={refund_metrics.get('pre_shipment_refund_amount', 0.0)}"
        )
        return summary

    @staticmethod
    def _is_douyin_after_sale_workbench_url(url: str) -> bool:
        """
        判定是否已进入抖店“售后工作台”页面。
        """
        current_url = (url or "").strip().lower()
        return "jinritemai.com" in current_url and "merchant-aftersale-workbench" in current_url

    def _is_douyin_after_sale_workbench_page_by_content(self) -> bool:
        """
        通过稳定文案判断是否已在“售后工作台”售后管理页。
        """
        current_url = (self.get_current_url() or "").lower()
        if "jinritemai.com" not in current_url:
            return False
        if not self._is_douyin_after_sale_workbench_url(current_url):
            return False
        return self._has_douyin_after_sale_filter_controls()

    def _has_douyin_after_sale_filter_controls(self) -> bool:
        """
        判断售后工作台筛选区是否已真实渲染完成。
        """
        try:
            driver = self._ensure_driver()
            ready = bool(
                driver.execute_script(
                    """
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const compact = (value) => normalize(value).replace(/\\s+/g, '');
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 18 && rect.height >= 12 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 480;
                    };
                    const textOf = (node) => normalize(
                      node.innerText
                      || node.textContent
                      || node.getAttribute('aria-label')
                      || node.getAttribute('placeholder')
                      || node.value
                      || ''
                    );
                    const nodes = Array.from(
                      document.querySelectorAll('button, a, span, div, label, input, [role="button"]')
                    ).filter(visible);
                    const hasText = (needle) => nodes.some((node) => {
                      const text = textOf(node);
                      return text.includes(needle) || compact(text).includes(needle);
                    });
                    const hasAction = (needle) => nodes.some((node) => {
                      const text = textOf(node);
                      const denseText = compact(text);
                      if (!(text === needle || text.includes(needle) || denseText === needle || denseText.includes(needle))) return false;
                      const tag = String(node.tagName || '').toLowerCase();
                      const role = String(node.getAttribute('role') || '').toLowerCase();
                      const cls = String(node.className || '').toLowerCase();
                      if (denseText === needle || denseText.includes(needle)) return true;
                      return tag === 'button'
                        || tag === 'a'
                        || role === 'button'
                        || text === needle
                        || /(button|btn|action|operate)/.test(cls);
                    });
                    return hasText('售后状态')
                      && hasText('售后类型')
                      && hasAction('查询')
                      && hasAction('导出');
                    """
                )
            )
            if ready:
                return True
        except Exception:
            markers = ("售后状态", "售后类型", "导出")
            return all(self._page_contains_text(marker) for marker in markers) and (
                self._page_contains_text("查询") or self._page_contains_compact_text("查询")
            )

        snippet = self._page_text_snippet(max_length=8000)
        compact = re.sub(r"\s+", "", snippet)
        return (
            "售后状态" in compact
            and "售后类型" in compact
            and "导出" in compact
            and "查询" in compact
        )

    def _open_douyin_after_sale_workbench_page(self) -> None:
        """
        打开抖店“售后工作台”页面。
        """
        driver = self._ensure_driver()
        self._ensure_douyin_runtime_context()
        self._switch_default_content()
        self._close_douyin_notice_popup_if_present()

        if self._is_douyin_after_sale_workbench_url(self.get_current_url() or ""):
            self._wait_until(
                self._is_douyin_after_sale_workbench_page_by_content,
                timeout_seconds=max(self.timeout_seconds * 2, 45),
                message="售后工作台筛选区未加载完成。",
                selector_keys=("douyin_after_sale_query_button", "douyin_after_sale_export_button"),
            )
            return

        if "jinritemai.com" not in (self.get_current_url() or "").lower():
            self._open_douyin_homepage()

        clicked = (
            self._try_click_selector("douyin_after_sale_workbench_menu", timeout_seconds=5.0)
            or self._click_left_panel_text_with_wait(
                ("售后工作台",),
                exact=True,
                timeout_seconds=5.0,
                required=False,
                step_name="已点击左侧菜单：售后工作台",
            )
            or self._click_text_with_wait(("售后工作台",), exact=True, timeout_seconds=5.0, required=False)
        )
        if clicked:
            self._promotion_pause(1.0)

        if not self._is_douyin_after_sale_workbench_url(self.get_current_url() or ""):
            driver.get(self.DOUYIN_AFTER_SALE_WORKBENCH_URL)
            self._wait_dom_ready()
            self._promotion_pause(1.0)

        self._wait_until(
            lambda: self._is_douyin_after_sale_workbench_url(self.get_current_url() or "")
            or self._is_douyin_after_sale_workbench_page_by_content(),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="未进入抖店【售后工作台】页面。",
            selector_keys=("douyin_after_sale_workbench_menu",),
        )
        self._wait_until(
            self._is_douyin_after_sale_workbench_page_by_content,
            timeout_seconds=max(self.timeout_seconds * 2, 45),
            message="售后工作台筛选区未加载完成。",
            selector_keys=("douyin_after_sale_query_button", "douyin_after_sale_export_button"),
        )
        self._log_step("已进入菜单：售后工作台")

    def _select_douyin_after_sale_field_option(
        self,
        field_text: str,
        option_text: str,
        *,
        timeout_seconds: float = 8.0,
    ) -> bool:
        """
        在售后工作台筛选区选择指定字段的下拉选项。
        """
        driver = self._ensure_driver()
        field_xpath = (
            "//*[contains(@class,'labelWrapper') and normalize-space()=$FIELD]"
            "/following-sibling::*[contains(@class,'fieldWrapper')]"
            "//*[contains(@class,'auxo-select-selector') or @role='combobox'][1]"
        ).replace("$FIELD", f"'{field_text}'")
        option_xpath = (
            "//*[contains(@class,'auxo-select-dropdown') and not(contains(@class,'hidden'))]"
            "//*[contains(@class,'auxo-select-item-option') and "
            f"(normalize-space()='{option_text}' or @title='{option_text}')]"
        )

        def click_field() -> bool:
            for xpath in (
                field_xpath,
                (
                    "//*[contains(@class,'labelWrapper') and normalize-space()='%s']"
                    "/following::*[contains(@class,'auxo-select-selector') or @role='combobox'][1]"
                    % field_text
                ),
            ):
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                            element,
                        )
                        self._promotion_pause(0.15)
                        self._click_with_retry(element)
                        return True
                    except (StaleElementReferenceException, WebDriverException):
                        continue
            return False

        def click_option() -> bool:
            try:
                options = driver.find_elements(By.XPATH, option_xpath)
            except Exception:
                options = []
            for option in options:
                try:
                    if not option.is_displayed() or not option.is_enabled():
                        continue
                    self._click_with_retry(option)
                    return True
                except (StaleElementReferenceException, WebDriverException):
                    continue
            return self._click_text_with_wait(
                (option_text,),
                exact=True,
                timeout_seconds=1.0,
                required=False,
            )

        end_time = time.time() + max(timeout_seconds, 1.0)
        while time.time() < end_time:
            if click_field():
                self._promotion_pause(0.25)
                if click_option():
                    self._promotion_pause(0.35)
                    return True
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))
        return False

    def _click_douyin_after_sale_more_filters(self) -> bool:
        """
        展开售后工作台“更多筛选”。
        """
        if self._has_douyin_after_sale_date_shortcut_control():
            return True
        clicked = self._click_text_with_wait(
            ("更多筛选",),
            exact=True,
            timeout_seconds=5.0,
            required=False,
        )
        if clicked:
            self._promotion_pause(0.5)
        return clicked or self._has_douyin_after_sale_date_shortcut_control()

    def _has_douyin_after_sale_date_shortcut_control(self) -> bool:
        """
        判断日期筛选行右侧的快捷下拉是否已展示。
        """
        driver = self._ensure_driver()
        shortcut_xpaths = (
            "//*[contains(@class,'auxo-picker-range')]/following::*[contains(@class,'auxo-select-selector')][1]",
            (
                "//*[contains(@class,'auxo-col') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-input-group') and not(.//*[contains(@class,'auxo-picker-range')])]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
        )
        for xpath in shortcut_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        return True
                except (StaleElementReferenceException, WebDriverException):
                    continue
        return self._page_contains_text("申请时间") and self._page_contains_text("收起")

    def _select_douyin_after_sale_date_field_option(
        self,
        option_text: str,
        *,
        timeout_seconds: float = 8.0,
    ) -> bool:
        """
        在售后工作台日期复合控件中，把左侧日期字段切换为指定选项。
        """
        driver = self._ensure_driver()
        field_xpaths = (
            (
                "//*[contains(@class,'compactWrapper') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
            (
                "//*[contains(@class,'auxo-input-group') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
        )
        option_xpaths = (
            (
                "//*[contains(@class,'auxo-select-dropdown') and not(contains(@class,'hidden'))]"
                "//*[contains(@class,'auxo-select-item-option') and "
                f"(normalize-space()='{option_text}' or @title='{option_text}')]"
            ),
            (
                "//*[contains(@class,'auxo-select-item-option') and "
                f"(normalize-space()='{option_text}' or @title='{option_text}')]"
            ),
            (
                "//*[contains(@class,'auxo-select-item-option') and "
                f"contains(normalize-space(),'{option_text}')]"
            ),
        )

        def open_field() -> bool:
            for xpath in field_xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        current_text = re.sub(r"\s+", " ", element.text or "").strip()
                        if current_text == option_text:
                            return True
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                            element,
                        )
                        self._promotion_pause(0.1)
                        self._click_with_retry(element)
                        return True
                    except (StaleElementReferenceException, WebDriverException):
                        continue
            return False

        def click_option() -> bool:
            for xpath in option_xpaths:
                try:
                    options = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for option in options:
                    try:
                        if not option.is_displayed() or not option.is_enabled():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                            option,
                        )
                        self._promotion_pause(0.1)
                        self._click_with_retry(option)
                        return True
                    except (StaleElementReferenceException, WebDriverException):
                        continue
            return self._click_text_with_wait(
                (option_text,),
                exact=True,
                timeout_seconds=1.0,
                required=False,
            )

        end_time = time.time() + max(timeout_seconds, 1.0)
        while time.time() < end_time:
            if open_field():
                self._promotion_pause(0.25)
                if self._is_douyin_after_sale_date_field_selected(option_text):
                    return True
                if click_option():
                    self._promotion_pause(0.35)
                    return self._is_douyin_after_sale_date_field_selected(option_text)
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))
        return self._is_douyin_after_sale_date_field_selected(option_text)

    def _is_douyin_after_sale_date_field_selected(self, option_text: str) -> bool:
        """
        判断日期复合控件左侧字段是否已切换为目标值。
        """
        driver = self._ensure_driver()
        field_xpaths = (
            (
                "//*[contains(@class,'compactWrapper') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
            (
                "//*[contains(@class,'auxo-input-group') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
        )
        for xpath in field_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = re.sub(r"\s+", " ", element.text or "").strip()
                    title = re.sub(r"\s+", " ", element.get_attribute("title") or "").strip()
                    if text == option_text or title == option_text:
                        return True
                except (StaleElementReferenceException, WebDriverException):
                    continue
        return False

    def _select_douyin_after_sale_date_shortcut(self, option_text: str) -> bool:
        """
        选择日期行右侧的日期快捷项，避免误点日期范围输入框或其它“请选择”筛选。
        """
        driver = self._ensure_driver()

        shortcut_xpaths = (
            "//*[contains(@class,'auxo-picker-range')]/following::*[contains(@class,'auxo-select-selector')][1]",
            (
                "//*[contains(@class,'auxo-col') and .//*[contains(@class,'auxo-picker-range')]]"
                "//*[contains(@class,'auxo-input-group') and not(.//*[contains(@class,'auxo-picker-range')])]"
                "//*[contains(@class,'auxo-select-selector')][1]"
            ),
        )
        option_xpaths = (
            (
                "//*[contains(@class,'auxo-select-dropdown') and not(contains(@class,'hidden'))]"
                "//*[contains(@class,'auxo-select-item-option') and "
                f"(normalize-space()='{option_text}' or @title='{option_text}')]"
            ),
            (
                "//*[contains(@class,'auxo-select-item-option') and "
                f"(normalize-space()='{option_text}' or @title='{option_text}')]"
            ),
            (
                "//*[contains(@class,'auxo-select-item-option') and "
                f"contains(normalize-space(),'{option_text}')]"
            ),
        )

        def open_shortcut() -> bool:
            for xpath in shortcut_xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                            element,
                        )
                        self._promotion_pause(0.1)
                        self._click_with_retry(element)
                        return True
                    except (StaleElementReferenceException, WebDriverException):
                        continue
            return False

        def click_option() -> bool:
            for xpath in option_xpaths:
                try:
                    options = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for option in options:
                    try:
                        if not option.is_displayed() or not option.is_enabled():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                            option,
                        )
                        self._promotion_pause(0.1)
                        self._click_with_retry(option)
                        return True
                    except (StaleElementReferenceException, WebDriverException):
                        continue
            return self._click_text_with_wait(
                (option_text,),
                exact=True,
                timeout_seconds=1.0,
                required=False,
            )

        end_time = time.time() + 8.0
        while time.time() < end_time:
            if open_shortcut():
                self._promotion_pause(0.25)
                if click_option():
                    self._promotion_pause(0.35)
                    return True
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))
        return False

    def _set_douyin_after_sale_export_conditions(
        self,
        report_date: date | datetime | str | None = None,
    ) -> None:
        """
        设置抖店售后工作台导出条件：退款成功、全部、按完结时间选择报表日期。
        """
        report_date_str = self._format_report_date(report_date)
        if not self._select_douyin_after_sale_field_option("售后状态", "退款成功"):
            self._raise_timeout_with_context(
                "售后工作台未能选择售后状态：退款成功",
                selector_keys=("douyin_after_sale_query_button",),
            )
        self._log_step("售后工作台已选择售后状态：退款成功")

        if not self._select_douyin_after_sale_field_option("售后类型", "全部"):
            self._raise_timeout_with_context(
                "售后工作台未能选择售后类型：全部",
                selector_keys=("douyin_after_sale_query_button",),
            )
        self._log_step("售后工作台已选择售后类型：全部")

        if not self._click_douyin_after_sale_more_filters():
            self._raise_timeout_with_context(
                "售后工作台未能展开【更多筛选】。",
                selector_keys=("douyin_after_sale_query_button",),
            )

        if not self._select_douyin_after_sale_date_field_option("完结时间"):
            self._raise_timeout_with_context(
                "售后工作台未能切换日期字段：完结时间",
                selector_keys=("douyin_after_sale_query_button",),
            )
        self._log_step("售后工作台已选择日期字段：完结时间")

        if report_date_str == DateConfig.default_report_date_str():
            if not self._select_douyin_after_sale_date_shortcut("昨日"):
                self._raise_timeout_with_context(
                    "售后工作台未能选择日期范围：昨日",
                    selector_keys=("douyin_after_sale_query_button",),
                )
            self._log_step("售后工作台已选择日期：昨日")
            return

        if not self._set_douyin_after_sale_custom_single_day(report_date_str):
            self._raise_timeout_with_context(
                f"售后工作台未能选择日期：{report_date_str}",
                selector_keys=("douyin_after_sale_query_button",),
            )
        self._log_step(f"售后工作台已选择日期：{report_date_str}")

    def _set_douyin_after_sale_custom_single_day(self, report_date: str) -> bool:
        """
        在售后工作台日期范围控件中选择指定单日。
        """
        target = self._format_report_date(report_date)
        if self._is_douyin_after_sale_date_range_selected(target):
            return True
        if not self._click_douyin_after_sale_start_date_input():
            return False
        time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        if not self._click_douyin_after_sale_calendar_day_twice(target):
            return False
        if not self._click_douyin_after_sale_calendar_confirm():
            return False
        try:
            self._wait_until(
                lambda: self._is_douyin_after_sale_date_range_selected(target),
                timeout_seconds=max(self.timeout_seconds, 12),
                message=f"售后工作台日期未切换到：{target}",
            )
        except TimeoutException:
            return False
        return True

    def _click_douyin_after_sale_start_date_input(self) -> bool:
        """
        点击售后工作台日期范围的开始日期输入框。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 50 && rect.height >= 18
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 120;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                      return true;
                    };

                    const rangeNodes = Array.from(document.querySelectorAll('.auxo-picker-range, [class*="picker-range"], [class*="PickerRange"]'))
                      .filter(visible)
                      .map((el) => ({ el, text: normalize(el.innerText || el.textContent || ''), rect: el.getBoundingClientRect() }))
                      .filter((item) => item.text.includes('开始日期') || item.text.includes('结束日期') || /\\d{4}[/-]\\d{2}[/-]\\d{2}/.test(item.text));
                    rangeNodes.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    const range = rangeNodes[0] && rangeNodes[0].el;
                    if (range) {
                      const inputs = Array.from(range.querySelectorAll('input')).filter(visible);
                      if (inputs.length) return clickNode(inputs[0]);
                      const children = Array.from(range.querySelectorAll('span, div, button')).filter(visible)
                        .map((el) => ({ el, text: normalize(el.innerText || el.textContent || el.getAttribute('placeholder') || ''), rect: el.getBoundingClientRect() }))
                        .filter((item) => item.text.includes('开始日期') || /\\d{4}[/-]\\d{2}[/-]\\d{2}/.test(item.text));
                      children.sort((a, b) => a.rect.left - b.rect.left);
                      if (children.length) return clickNode(children[0].el);
                    }

                    const placeholders = Array.from(document.querySelectorAll('input[placeholder*="开始日期"], input[placeholder*="开始"]'))
                      .filter(visible);
                    if (placeholders.length) return clickNode(placeholders[0]);
                    return false;
                    """
                )
            )
        except Exception:
            return False

    def _click_douyin_after_sale_calendar_day_twice(self, report_date: str) -> bool:
        """
        在售后工作台日期面板中连续点击目标日期两次。
        """
        target = self._format_report_date(report_date)
        if not self._bring_douyin_after_sale_calendar_month_into_view(target):
            return False
        first_clicked = self._click_douyin_after_sale_calendar_day(target)
        if first_clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.18))
        second_clicked = self._click_douyin_after_sale_calendar_day(target)
        if second_clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        return bool(first_clicked and second_clicked)

    def _bring_douyin_after_sale_calendar_month_into_view(self, report_date: str) -> bool:
        """
        尝试将售后工作台日期面板翻到目标月份。
        """
        target = self._format_report_date(report_date)
        target_year, target_month, _target_day = (int(part) for part in target.split("-"))
        driver = self._ensure_driver()

        for _ in range(14):
            visible_months = self._extract_douyin_after_sale_calendar_months()
            if any((year, month) == (target_year, target_month) for year, month in visible_months):
                return True
            if not visible_months:
                return False

            max_month = max(visible_months)
            direction = "next" if (target_year, target_month) > max_month else "prev"
            try:
                clicked = bool(
                    driver.execute_script(
                        """
                        const direction = arguments[0];
                        const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                        const visible = (el) => {
                          if (!el) return false;
                          const style = getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width >= 8 && rect.height >= 8
                            && rect.bottom >= 0 && rect.top <= window.innerHeight + 140;
                        };
                        const panelRoots = Array.from(document.querySelectorAll(
                          '.auxo-picker-panel, .auxo-picker-date-panel, .auxo-picker-dropdown, ' +
                          '.sp-range-picker-join-dropdown, [class*="picker-panel"], [class*="picker-dropdown"], [class*="date-panel"]'
                        ))
                          .filter(visible)
                          .filter((el) => /20\\d{2}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent || '')));
                        const searchRoots = panelRoots.length ? panelRoots : [document];
                        const nodes = searchRoots.flatMap((root) => Array.from(root.querySelectorAll('button, span, div, i, svg')))
                          .filter(visible)
                          .map((el) => {
                            const rect = el.getBoundingClientRect();
                            const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');
                            const cls = String(el.className || '').toLowerCase();
                            const cleanCls = cls.replace(/placement-[a-z-]+/g, ' ');
                            const hint = `${text} ${cleanCls}`.toLowerCase();
                            const isCalendarNav = /picker-header-(super-)?(prev|next)-btn|picker-(super-)?(prev|next)-icon|\\b(prev|next)-btn\\b|\\b(prev|next)-icon\\b/.test(cleanCls)
                              || /^[<>‹›«»]$/.test(text)
                              || /上个月|上一月|下个月|下一月|上一年|下一年/.test(text);
                            const isJumpArrow = /«|»|super|jump|double|year|年份|年度|上一年|下一年/.test(hint);
                            let singleArrowScore = 0;
                            if (isCalendarNav && !isJumpArrow) {
                              if (direction === 'prev' && (/‹|<|上个月|上一月|prev|left|previous/.test(hint))) singleArrowScore = 2;
                              if (direction === 'next' && (/›|>|下个月|下一月|next|right/.test(hint))) singleArrowScore = 2;
                            }
                            return { el, rect, text, cls, hint, isCalendarNav, isJumpArrow, singleArrowScore };
                          })
                          .filter((item) => item.isCalendarNav)
                          .filter((item) => {
                            if (direction === 'prev') {
                              return /上|prev|left|previous|«|‹/.test(item.hint) || item.text === '<' || item.text === '‹';
                            }
                            return /下|next|right|»|›/.test(item.hint) || item.text === '>' || item.text === '›';
                          });
                        nodes.sort((a, b) => {
                          if (b.singleArrowScore !== a.singleArrowScore) return b.singleArrowScore - a.singleArrowScore;
                          if (a.isJumpArrow !== b.isJumpArrow) return a.isJumpArrow ? 1 : -1;
                          return direction === 'prev' ? a.rect.left - b.rect.left : b.rect.left - a.rect.left;
                        });
                        if (!nodes.length) return false;
                        const node = nodes[0].el;
                        node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        node.click();
                        return true;
                        """,
                        direction,
                    )
                )
            except Exception:
                clicked = False
            if not clicked:
                return False
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        return False

    def _extract_douyin_after_sale_calendar_months(self) -> list[tuple[int, int]]:
        """
        读取售后工作台日期面板当前可见月份。
        """
        driver = self._ensure_driver()
        try:
            raw_months = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 20 && rect.height >= 12
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 140;
                };
                const values = [];
                for (const el of Array.from(document.querySelectorAll('div, span, section'))) {
                  if (!visible(el)) continue;
                  const text = normalize(el.innerText || el.textContent || '');
                  const matches = text.matchAll(/(20\\d{2})年\\s*(\\d{1,2})月/g);
                  for (const match of matches) {
                    values.push(`${match[1]}-${String(match[2]).padStart(2, '0')}`);
                  }
                }
                return Array.from(new Set(values));
                """
            )
        except Exception:
            raw_months = []

        months: list[tuple[int, int]] = []
        for value in raw_months or []:
            try:
                year_text, month_text = str(value).split("-", 1)
                months.append((int(year_text), int(month_text)))
            except (TypeError, ValueError):
                continue
        return months

    def _click_douyin_after_sale_calendar_day(self, report_date: str) -> bool:
        """
        点击售后工作台日期面板中的目标日期。
        """
        driver = self._ensure_driver()
        target = self._format_report_date(report_date)
        target_year, target_month, target_day = (int(part) for part in target.split("-"))
        day_text = str(target_day)
        target_month_text = f"{target_year}年{target_month}月"

        try:
            return bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '');
                    const targetMonthText = String(arguments[1] || '');
                    const dayText = String(arguments[2] || '');
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 10 && rect.height >= 10
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 140;
                    };
                    const isDisabled = (el) => {
                      if (!el) return false;
                      const attrText = [
                        el.getAttribute('aria-disabled'),
                        el.getAttribute('disabled'),
                        el.getAttribute('class'),
                        el.parentElement && el.parentElement.getAttribute('class'),
                      ].join(' ').toLowerCase();
                      return /disabled/.test(attrText) || attrText.includes('true');
                    };
                    const clickNode = (node) => {
                      if (!node || isDisabled(node)) return false;
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                      return true;
                    };

                    const panels = Array.from(document.querySelectorAll('.auxo-picker-panel, .auxo-picker-date-panel'))
                      .filter(visible)
                      .map((panel) => ({ panel, text: normalize(panel.innerText || panel.textContent || ''), rect: panel.getBoundingClientRect() }))
                      .filter((item) => item.text.replace(/\\s+/g, '').includes(targetMonthText));
                    panels.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    const panel = panels[0] && panels[0].panel;
                    if (!panel) return false;

                    const attrMatches = Array.from(panel.querySelectorAll('[title], [aria-label], [data-date]'))
                      .filter(visible)
                      .filter((el) => {
                        const text = `${el.getAttribute('title') || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-date') || ''}`;
                        return text.includes(target) && !isDisabled(el);
                      });
                    if (attrMatches.length) return clickNode(attrMatches[0]);

                    const candidates = Array.from(panel.querySelectorAll('td, .auxo-picker-cell, .auxo-picker-cell-inner, button, span, div'))
                      .filter(visible)
                      .map((el) => ({ el, text: normalize(el.innerText || el.textContent || ''), rect: el.getBoundingClientRect() }))
                      .filter((item) => item.text === dayText && !isDisabled(item.el))
                      .filter((item) => {
                        const cls = String(item.el.className || '').toLowerCase();
                        return item.el.tagName.toLowerCase() === 'td' || cls.includes('picker-cell-inner');
                      });
                    candidates.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    if (!candidates.length) return false;
                    return clickNode(candidates[0].el);
                    """,
                    target,
                    target_month_text,
                    day_text,
                )
            )
        except Exception:
            return False

    def _click_douyin_after_sale_calendar_confirm(self) -> bool:
        """
        点击售后工作台日期面板的【确定】。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 10 && rect.height >= 10
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 140;
                    };
                    const dropdowns = Array.from(document.querySelectorAll('.auxo-picker-dropdown, .sp-range-picker-join-dropdown'))
                      .filter(visible);
                    for (const dropdown of dropdowns) {
                      const buttons = Array.from(dropdown.querySelectorAll('button, [role="button"], .sp-picker-range-ok-btn'))
                        .filter(visible)
                        .filter((el) => normalize(el.innerText || el.textContent || '') === '确定');
                      if (!buttons.length) continue;
                      const node = buttons[buttons.length - 1];
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                      return true;
                    }
                    return false;
                    """
                )
            )
        except Exception:
            clicked = False
        if not clicked:
            clicked = self._click_text_with_wait(("确定",), exact=True, timeout_seconds=5.0, required=False)
        if clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.25))
        return clicked

    def _is_douyin_after_sale_date_range_selected(self, report_date: str) -> bool:
        """
        判断售后工作台日期范围是否显示为目标单日。
        """
        target = self._format_report_date(report_date)
        slash = target.replace("-", "/")
        compact_values = ""
        try:
            driver = self._ensure_driver()
            input_values = driver.execute_script(
                """
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 20 && rect.height >= 12
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 140;
                };
                return Array.from(document.querySelectorAll('input'))
                  .filter(visible)
                  .map((input) => String(input.value || '').trim())
                  .filter(Boolean);
                """
            )
            compact_values = re.sub(r"\s+", "", " ".join(str(value) for value in (input_values or [])))
        except Exception:
            compact_values = ""

        compact = compact_values + re.sub(r"\s+", "", self._page_text_snippet(max_length=6000))
        start_ok = f"{slash}00:00:00" in compact or f"{target}00:00:00" in compact
        end_ok = f"{slash}23:59:59" in compact or f"{target}23:59:59" in compact
        return start_ok and end_ok

    def _download_douyin_after_sale_orders(self, download_dir: Path) -> Path:
        """
        点击【查询】和【导出】，等待售后单文件下载完成。
        """
        target_dir = Path(download_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        query_clicked = (
            self._try_click_selector("douyin_after_sale_query_button", timeout_seconds=5.0)
            or self._click_text_with_wait(("查询",), exact=True, timeout_seconds=5.0, required=False)
        )
        if not query_clicked:
            self._raise_timeout_with_context(
                "售后工作台未找到【查询】按钮。",
                selector_keys=("douyin_after_sale_query_button",),
            )
        self._log_step("售后工作台已点击：查询")
        self._promotion_pause(1.2)

        snapshot = snapshot_directory(target_dir)
        trigger_ts = time.time()
        export_clicked = (
            self._try_click_selector("douyin_after_sale_export_button", timeout_seconds=5.0)
            or self._click_text_with_wait(("导出",), exact=True, timeout_seconds=5.0, required=False)
        )
        if not export_clicked:
            self._raise_timeout_with_context(
                "售后工作台未找到【导出】按钮。",
                selector_keys=("douyin_after_sale_export_button",),
            )
        self._log_step("售后工作台已点击：导出")

        if self._is_douyin_after_sale_zero_export_notice_present(timeout_seconds=3.0):
            raise TimeoutException("售后工作台售后单导出为0条，无法导出。")

        try:
            detail_file = wait_for_download_complete(
                directory=target_dir,
                timeout_seconds=max(self.download_wait_seconds, 120),
                poll_interval_seconds=1.0,
                start_time=trigger_ts,
                previous_snapshot=snapshot,
                temp_suffixes=(".crdownload", ".part", ".tmp"),
                file_filter=lambda file_path: (
                    file_path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}
                    and not file_path.name.startswith("~$")
                ),
            )
        except TimeoutError as exc:
            raise TimeoutException(f"售后工作台售后单下载超时：{target_dir}") from exc
        self._log_step(f"售后工作台售后单已下载：{detail_file}")
        return detail_file

    def _is_douyin_after_sale_zero_export_notice_present(self, timeout_seconds: float = 2.0) -> bool:
        """
        判断售后工作台是否弹出“0条无法导出”的提示。
        """
        zero_markers = (
            "售后单导出为0条",
            "导出为0条",
            "无法导出",
            "请修改筛选条件后重试",
        )
        end_time = time.time() + max(timeout_seconds, 0.1)
        while time.time() < end_time:
            page_text = self._page_text_snippet(max_length=1200)
            if "0条" in page_text and any(marker in page_text for marker in zero_markers):
                return True
            time.sleep(max(self.ui_poll_interval_seconds, 0.1))
        return False

    def _build_zero_douyin_after_sale_refund_summary(self) -> dict[str, Any]:
        """
        构建抖店售后工作台无可导出售后单时的 0 退款汇总。
        """
        from qianiu_auto_report.data_process import DataProcessor

        summary = DataProcessor()._build_empty_summary()
        metrics = dict(DataProcessor.DOUYIN_ZERO_REFUND_METRICS)
        summary["total_count"] = 0
        summary["total_amount"] = 0.0
        summary["douyin_refund_metrics"] = metrics
        summary["report_date"] = DateConfig.default_report_date_str()
        return summary

    def _collect_douyin_after_sale_refund_summary(
        self,
        download_dir: Path,
        report_date: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        """
        从抖店售后工作台导出售后单并汇总退款。
        """
        from qianiu_auto_report.data_process import DataProcessor

        self._open_douyin_after_sale_workbench_page()
        if report_date is None:
            self._set_douyin_after_sale_export_conditions()
        else:
            self._set_douyin_after_sale_export_conditions(report_date=report_date)
        try:
            detail_file = self._download_douyin_after_sale_orders(download_dir=download_dir)
        except TimeoutException as exc:
            if "导出为0条" not in str(exc):
                raise
            self._log_step("售后工作台售后单为 0 条，退款数据按 0 处理")
            summary = self._build_zero_douyin_after_sale_refund_summary()
        else:
            summary = DataProcessor().summarize_douyin_after_sale_orders(detail_file)
        refund_metrics = summary.get("douyin_refund_metrics", {})
        self._log_step(
            "售后工作台退款汇总："
            f"未发货退款={refund_metrics.get('pre_shipment_refund_order_count', 0)}单/"
            f"{refund_metrics.get('pre_shipment_refund_amount', 0.0)}元，"
            f"已发货退款={refund_metrics.get('received_refund_order_count', 0)}单/"
            f"{refund_metrics.get('received_refund_amount', 0.0)}元，"
            f"退货退款={refund_metrics.get('return_refund_order_count', 0)}单/"
            f"{refund_metrics.get('return_refund_amount', 0.0)}元"
        )
        return summary

    def _build_douyin_metrics_result(
        self,
        trade_amount: float,
        trade_order_count: int,
        expense_amount: float,
        shop_name: str = "",
        refund_summary: Optional[dict[str, Any]] = None,
        report_date: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        """
        将抖店电商罗盘指标映射到当前报表字段结构。
        """
        order_count = int(round(float(trade_order_count)))
        result_report_date = self._format_report_date(report_date)
        if refund_summary is not None:
            summary_report_date = str(refund_summary.get("report_date", "") or "").strip()
            if summary_report_date and report_date is None:
                result_report_date = summary_report_date
        result = {
            "report_date": result_report_date,
            "platform": "douyin",
            "shop_name": str(shop_name or "").strip(),
            "payment_buyer_count": order_count,
            "payment_amount": round(float(trade_amount), 2),
            "payment_sub_order_count": order_count,
            "trade_compensation": 0.0,
            "cross_border_value_added_fee": 0.0,
            "promotion_fee": round(float(expense_amount), 2),
        }
        if refund_summary is not None:
            result["refund_summary"] = refund_summary
        return result

    def collect_douyin_compass_metrics(
        self,
        download_dir: Optional[Path] = None,
        login_handler: Optional[Callable[[webdriver.Chrome], None]] = None,
        switch_to_existing_page: bool = True,
        report_date: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        """
        采集抖店指标：弹窗关闭 -> 电商罗盘 -> 选择日期 -> 读取成交金额/成交订单数/支出金额。
        """
        self._ensure_douyin_runtime_context()
        self.validate_runtime_config()

        if self.driver is None:
            target_dir = Path(download_dir) if download_dir is not None else Path(ExportConfig.DOWNLOAD_DIR)
            target_dir.mkdir(parents=True, exist_ok=True)
            self.init_driver(download_dir=target_dir)
            self.open_login_page()
            self.login(login_handler=login_handler)
        else:
            self._ensure_wait()

        if self.attach_to_existing_browser and switch_to_existing_page:
            self._switch_to_existing_douyin_page()

        self._close_douyin_notice_popup_if_present()
        self._log_step("抖店退款数据来源：售后工作台售后单")

        self._open_douyin_compass_page()
        report_date_str = self._format_report_date(report_date)
        self._set_douyin_compass_report_date(report_date_str)
        self._promotion_pause(1.0)

        trade_amount = self._extract_douyin_compass_metric("成交金额")
        trade_order_count = int(round(self._extract_douyin_compass_metric("成交订单数")))
        expense_amount = self._extract_douyin_compass_metric("支出金额")
        shop_name = self._extract_douyin_shop_name()
        if shop_name:
            self._log_step(f"抖店店铺名：{shop_name}")
        target_dir = Path(download_dir) if download_dir is not None else Path(ExportConfig.DOWNLOAD_DIR)
        if report_date is None:
            refund_summary = self._collect_douyin_after_sale_refund_summary(download_dir=target_dir)
        else:
            refund_summary = self._collect_douyin_after_sale_refund_summary(
                download_dir=target_dir,
                report_date=report_date_str,
            )

        self._log_step(
            "电商罗盘提取结果："
            f"成交金额={trade_amount}，成交订单数={trade_order_count}，支出金额={expense_amount}"
        )
        return self._build_douyin_metrics_result(
            trade_amount=trade_amount,
            trade_order_count=trade_order_count,
            expense_amount=expense_amount,
            shop_name=shop_name,
            refund_summary=refund_summary,
            report_date=report_date_str,
        )

    def collect_douyin_all_shop_metrics(
        self,
        download_dir: Optional[Path] = None,
        login_handler: Optional[Callable[[webdriver.Chrome], None]] = None,
        max_shops: int = 5,
        report_date: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """
        采集当前抖店及店铺切换弹层中其它店铺的数据，每个店铺返回一组报表指标。
        """
        target_dir = Path(download_dir) if download_dir is not None else Path(ExportConfig.DOWNLOAD_DIR)
        metrics_list: list[dict[str, Any]] = []
        visited_shop_names: list[str] = []
        visited_keys: set[str] = set()
        max_count = max(int(max_shops), 1)
        expected_shop_name: Optional[str] = None

        for index in range(max_count):
            if not expected_shop_name:
                expected_shop_name = self._get_current_douyin_home_shop_name() or None

            collect_kwargs: dict[str, Any] = {
                "download_dir": target_dir,
                "login_handler": login_handler if index == 0 else None,
                "switch_to_existing_page": (index == 0 and not expected_shop_name),
            }
            if report_date is not None:
                collect_kwargs["report_date"] = report_date
            metrics = self.collect_douyin_compass_metrics(**collect_kwargs)
            metrics.setdefault("platform", "douyin")

            if expected_shop_name:
                detected_shop_name = str(metrics.get("shop_name") or "").strip()
                detected_key = self._normalize_douyin_shop_name(detected_shop_name)
                expected_key = self._normalize_douyin_shop_name(expected_shop_name)
                if not detected_key or detected_key != expected_key:
                    self._log_step(
                        "抖店店铺名按切换目标校正："
                        f"页面识别={detected_shop_name or '<空>'}，切换目标={expected_shop_name}"
                    )
                    metrics["shop_name"] = expected_shop_name

            shop_name = str(metrics.get("shop_name") or "").strip() or f"抖音店铺{index + 1}"
            shop_key = self._normalize_douyin_shop_name(shop_name)
            if shop_key in visited_keys:
                self._log_step(f"抖店店铺重复，停止继续采集：{shop_name}")
                break

            metrics["shop_name"] = shop_name
            metrics_list.append(metrics)
            visited_shop_names.append(shop_name)
            visited_keys.add(shop_key)

            if len(metrics_list) >= max_count:
                break

            switched_shop_name = self._switch_to_next_unvisited_douyin_shop(tuple(visited_shop_names))
            if not switched_shop_name:
                break
            expected_shop_name = (
                str(switched_shop_name).strip() if isinstance(switched_shop_name, str) else None
            ) or None

        return metrics_list

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
        has_yesterday = self._has_any_visible_element("account_details_yesterday_button")
        has_reason = self._has_any_visible_element("account_details_reason_dropdown")
        has_search = self._has_any_visible_element("account_details_search_button")
        has_account_markers = (
            self._page_contains_text("保证金流水")
            or self._page_contains_text("收支金额（元）")
            or self._page_contains_text("业务编号/订单编号")
            or self._page_contains_text("完成时间")
            or self._page_contains_text("原因")
        )

        # 不能仅凭“搜索”判断：外层页面存在全局搜索，容易误判导致无法进入真实内容区域。
        if has_search and not has_yesterday and not has_reason and not has_account_markers:
            return False

        return (
            has_yesterday
            or has_reason
            or (has_search and has_account_markers)
            or has_account_markers
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

    def _collect_qianniu_data_dashboard_metrics(self, report_date: date | datetime | str) -> dict[str, Any]:
        """
        从千牛极速版【数据】页按单日读取全店核心指标。
        """
        report_date_str = self._format_report_date(report_date)
        self._open_qianniu_data_dashboard_page()
        self._set_qianniu_data_dashboard_day(report_date_str)

        payment_amount = self._extract_qianniu_data_metric("支付金额")
        payment_buyers = self._extract_qianniu_data_metric("支付买家数")
        payment_sub_orders = self._extract_qianniu_data_metric("支付子订单数")

        shop_name = self._extract_home_shop_name()
        if self._looks_like_qianniu_data_metric_text(shop_name):
            shop_name = ""
        return {
            "shop_name": shop_name,
            "payment_amount": round(float(payment_amount), 2),
            "payment_buyer_count": int(round(payment_buyers)),
            "payment_sub_order_count": int(round(payment_sub_orders)),
        }

    def _open_qianniu_data_dashboard_page(self) -> None:
        """
        打开千牛极速版左侧【数据】对应的全店数据页。
        """
        current_url = (self.get_current_url() or "").lower()
        if "myseller.taobao.com/home.htm/op-sycm-data" in current_url:
            return

        if "myseller.taobao.com" in current_url:
            self._switch_to_speed_version_if_needed()
            clicked = self._click_left_panel_text_with_wait(
                ("数据",),
                exact=True,
                timeout_seconds=3.0,
                required=False,
                step_name="已点击左侧菜单：数据",
                min_left=0,
                max_left=190,
                min_top=120,
            )
            if clicked:
                try:
                    self._wait_until(
                        lambda: "op-sycm-data" in (self.get_current_url() or "").lower()
                        and self._page_contains_text("全店数据")
                        and self._page_contains_text("支付金额"),
                        timeout_seconds=max(self.timeout_seconds, 15),
                        message="千牛数据页未加载完成。",
                    )
                    return
                except TimeoutException:
                    pass

        self._log_step("改用 URL 直达千牛【数据】页")
        self._navigate_to_url(self.QIANNIU_DATA_DASHBOARD_URL)
        self._wait_until(
            lambda: "op-sycm-data" in (self.get_current_url() or "").lower()
            and self._page_contains_text("全店数据")
            and self._page_contains_text("支付金额"),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="千牛数据页未加载完成。",
        )

    def _set_qianniu_data_dashboard_day(self, report_date: str) -> None:
        """
        在千牛【数据】页顶部全店数据中选择指定单日。
        """
        target = self._format_report_date(report_date)
        if self._is_qianniu_data_report_date_selected(target):
            self._log_step(f"千牛数据页已选择日期：{target}")
            return

        before_metric_signature = self._qianniu_data_overview_metric_signature()
        if not self._click_qianniu_data_day_button():
            self._raise_timeout_with_context("千牛数据页未找到顶部【日】按钮。")
        time.sleep(max(self.ui_poll_interval_seconds, 0.2))

        if not self._is_qianniu_data_calendar_open():
            _ = self._click_qianniu_data_current_date_field()
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))

        if not self._click_qianniu_data_calendar_day(target):
            self._raise_timeout_with_context(f"千牛数据页日历未能选择日期：{target}")

        self._wait_until(
            lambda: self._is_qianniu_data_report_date_selected(target),
            timeout_seconds=max(self.timeout_seconds, 15),
            message=f"千牛数据页统计时间未切换到：{target}",
        )
        self._wait_qianniu_data_dashboard_refresh(target, before_metric_signature)
        self._log_step(f"千牛数据页已选择日期：{target}")

    def _is_qianniu_data_report_date_selected(self, report_date: str) -> bool:
        """
        判断千牛【数据】页顶部全店数据统计时间是否为目标日期。
        """
        target = self._format_report_date(report_date)
        snippet = self._page_text_snippet(max_length=4000)
        section = self._slice_qianniu_data_overview_text(snippet)
        compact = re.sub(r"\s+", "", section)
        return f"统计时间{target}" in compact

    def _qianniu_data_overview_text(self) -> str:
        """
        读取千牛【数据】页顶部全店数据区域文本。
        """
        return self._slice_qianniu_data_overview_text(self._page_text_snippet(max_length=8000))

    def _qianniu_data_overview_metric_signature(self) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        返回顶部三项核心指标签名，用于判断切换日期后的指标是否已刷新。
        """
        text = self._qianniu_data_overview_text()
        return (
            self._extract_metric_value_after_label_from_text(text, "支付金额"),
            self._extract_metric_value_after_label_from_text(text, "支付买家数"),
            self._extract_metric_value_after_label_from_text(text, "支付子订单数"),
        )

    def _wait_qianniu_data_dashboard_refresh(
        self,
        report_date: str,
        before_metric_signature: tuple[Optional[float], Optional[float], Optional[float]],
    ) -> None:
        """
        等待千牛【数据】页日期切换后的顶部指标完成异步刷新。
        """
        target = self._format_report_date(report_date)
        if not any(value is not None for value in before_metric_signature):
            time.sleep(max(self.interaction_delay_seconds, 0.5))
            return

        try:
            self._wait_until(
                lambda: self._is_qianniu_data_report_date_selected(target)
                and self._qianniu_data_overview_metric_signature() != before_metric_signature,
                timeout_seconds=max(min(self.timeout_seconds, 5), 2),
                message=f"千牛数据页顶部指标未刷新到日期：{target}",
            )
        except TimeoutException:
            if not self._is_qianniu_data_report_date_selected(target):
                raise
            self._log_step("千牛数据页日期已切换，顶部指标未检测到变化，短暂等待后继续")
            time.sleep(max(self.interaction_delay_seconds, 0.8))

    def _click_qianniu_data_day_button(self) -> bool:
        """
        点击顶部全店数据区域的【日】按钮。
        """
        driver = self._ensure_driver()
        candidates: list[tuple[float, float, WebElement]] = []
        try:
            elements = driver.find_elements(By.XPATH, "//button[normalize-space()='日']")
        except Exception:
            elements = []

        for element in elements:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                rect = element.rect
                y = float(rect.get("y", 9999))
                x = float(rect.get("x", 0))
                if y > 240:
                    continue
                candidates.append((y, -x, element))
            except Exception:
                continue

        candidates.sort(key=lambda item: (item[0], item[1]))
        for _y, _x, element in candidates:
            try:
                ActionChains(driver).move_to_element(element).pause(0.05).click().perform()
                time.sleep(max(self.interaction_delay_seconds, 0.1))
                return True
            except Exception:
                try:
                    self._click_with_retry(element)
                    time.sleep(max(self.interaction_delay_seconds, 0.1))
                    return True
                except Exception:
                    continue
        return False

    def _click_qianniu_data_current_date_field(self) -> bool:
        """
        点击顶部统计时间文本，打开单日日期面板。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 60 && rect.height >= 12
                        && rect.bottom >= 0 && rect.top <= window.innerHeight;
                    };
                    const nodes = Array.from(document.querySelectorAll('div, span, button'))
                      .filter((el) => visible(el))
                      .map((el) => ({ el, text: normalize(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                      .filter((item) => item.text.startsWith('统计时间 20') && item.rect.y <= Math.max(240, window.innerHeight * 0.42));
                    nodes.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    if (!nodes.length) return false;
                    nodes[0].el.click();
                    return true;
                    """
                )
            )
        except Exception:
            return False

    def _is_qianniu_data_calendar_open(self) -> bool:
        """
        判断千牛【数据】页单日日期面板是否已打开。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 220 && rect.height >= 180
                        && rect.bottom >= 0 && rect.top <= window.innerHeight;
                    };
                    return Array.from(document.querySelectorAll('div, section'))
                      .some((el) => visible(el) && /\\d{4}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent)));
                    """
                )
            )
        except Exception:
            return False

    def _click_qianniu_data_calendar_day(self, report_date: str) -> bool:
        """
        在已打开的千牛单日日期面板中点击目标日期。
        """
        driver = self._ensure_driver()
        target = self._format_report_date(report_date)
        target_year, target_month, target_day = (int(part) for part in target.split("-"))

        try:
            cells = driver.find_elements(By.CSS_SELECTOR, f".tbd-picker-dropdown td[title='{target}']")
        except Exception:
            cells = []
        for cell in cells:
            try:
                if not cell.is_displayed() or not cell.is_enabled():
                    continue
                cell_class = (cell.get_attribute("class") or "").lower()
                if "disabled" in cell_class:
                    continue
                inner_nodes = [
                    node
                    for node in cell.find_elements(By.CSS_SELECTOR, ".tbd-picker-cell-inner")
                    if node.is_displayed() and node.is_enabled()
                ]
                clickable = inner_nodes[0] if inner_nodes else cell
                ActionChains(driver).move_to_element(clickable).pause(0.05).click().perform()
                time.sleep(max(self.interaction_delay_seconds, 0.1))
                return True
            except Exception:
                try:
                    self._click_with_retry(cell)
                    time.sleep(max(self.interaction_delay_seconds, 0.1))
                    return True
                except Exception:
                    continue

        for _ in range(14):
            state = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 220 && rect.height >= 180
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 80;
                };
                const panels = Array.from(document.querySelectorAll('div, section'))
                  .filter((el) => visible(el) && /\\d{4}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent)))
                  .map((el) => ({ el, text: normalize(el.innerText || el.textContent), rect: el.getBoundingClientRect() }));
                panels.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                if (!panels.length) return null;
                const match = panels[0].text.match(/(\\d{4})年\\s*(\\d{1,2})月/);
                return match ? { year: Number(match[1]), month: Number(match[2]) } : null;
                """
            )
            if not state:
                return False

            current_year = int(state.get("year", 0))
            current_month = int(state.get("month", 0))
            if current_year == target_year and current_month == target_month:
                break

            direction = "next" if (current_year, current_month) < (target_year, target_month) else "prev"
            clicked_arrow = bool(
                driver.execute_script(
                    """
                    const direction = arguments[0];
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 8 && rect.height >= 8
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 80;
                    };
                    const panels = Array.from(document.querySelectorAll('div, section'))
                      .filter((el) => visible(el) && /\\d{4}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent)))
                      .map((el) => ({ el, rect: el.getBoundingClientRect() }));
                    panels.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    if (!panels.length) return false;
                    const panel = panels[0].el;
                    const panelRect = panels[0].rect;
                    const nodes = Array.from(panel.querySelectorAll('button, span, div, i, svg'))
                      .filter(visible)
                      .map((el) => ({ el, text: normalize(el.innerText || el.textContent), cls: String(el.className || '').toLowerCase(), rect: el.getBoundingClientRect() }))
                      .filter((item) => item.rect.y <= panelRect.y + 70);
                    const isNext = (item) => item.text === '›' || item.text === '>' || item.cls.includes('next') || item.cls.includes('right');
                    const isPrev = (item) => item.text === '‹' || item.text === '<' || item.cls.includes('prev') || item.cls.includes('left');
                    const candidates = nodes.filter(direction === 'next' ? isNext : isPrev)
                      .filter((item) => !item.cls.includes('double'));
                    candidates.sort((a, b) => direction === 'next' ? b.rect.x - a.rect.x : a.rect.x - b.rect.x);
                    if (!candidates.length) return false;
                    candidates[0].el.click();
                    return true;
                    """,
                    direction,
                )
            )
            if not clicked_arrow:
                return False
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))

        day_text = str(target_day)
        try:
            return bool(
                driver.execute_script(
                    """
                    const dayText = String(arguments[0]);
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 14 && rect.height >= 14
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 80;
                    };
                    const panels = Array.from(document.querySelectorAll('div, section'))
                      .filter((el) => visible(el) && /\\d{4}年\\s*\\d{1,2}月/.test(normalize(el.innerText || el.textContent)))
                      .map((el) => ({ el, rect: el.getBoundingClientRect() }));
                    panels.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    if (!panels.length) return false;
                    const panel = panels[0].el;
                    const nodes = Array.from(panel.querySelectorAll('td, button, div, span'))
                      .filter(visible)
                      .map((el) => ({ el, text: normalize(el.innerText || el.textContent), cls: String(el.className || '').toLowerCase(), rect: el.getBoundingClientRect() }))
                      .filter((item) => item.text === dayText)
                      .filter((item) => !item.cls.includes('disabled') && !item.cls.includes('outside') && !item.cls.includes('prev') && !item.cls.includes('next'));
                    nodes.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    if (!nodes.length) return false;
                    nodes[0].el.click();
                    return true;
                    """,
                    day_text,
                )
            )
        except Exception:
            return False

    def _extract_qianniu_data_metric(self, label: str) -> float:
        """
        从千牛极速版【数据】页顶部全店数据区域读取指定指标。
        """
        token = ""
        try:
            driver = self._ensure_driver()
            token = str(
                driver.execute_script(
                    """
                    const targetLabel = String(arguments[0] || '').trim();
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 40 && rect.height >= 18
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 120;
                    };
                    const parseValue = (text) => {
                      const escaped = targetLabel.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
                      const match = normalize(text).match(new RegExp('(?:^|[^\\\\u4e00-\\\\u9fffA-Za-z0-9])' + escaped + '\\\\s*[：:]?\\\\s*[¥￥]?\\\\s*([+\\\\-−]?\\\\d[\\\\d,]*(?:\\\\.\\\\d+)?)'));
                      return match ? match[1] : '';
                    };
                    const isTargetBlock = (text) => {
                      const raw = normalize(text);
                      return raw === targetLabel
                        || raw.startsWith(targetLabel + ' ')
                        || raw.startsWith(targetLabel + '：')
                        || raw.startsWith(targetLabel + ':');
                    };
                    const roots = Array.from(document.querySelectorAll('.index-oveview, [class*="index-oveview"], [class*="overview"]'))
                      .filter(visible)
                      .filter((el) => parseValue(normalize(el.innerText || '')));
                    const root = roots[0] || document.body;
                    const blocks = Array.from(root.querySelectorAll('.low-grid-item, [class*="grid-item"], [class*="common-wrapper"], div'))
                      .filter(visible)
                      .map((el) => ({ el, text: normalize(el.innerText || ''), rect: el.getBoundingClientRect() }))
                      .filter((item) => isTargetBlock(item.text) && item.text.length <= 220);
                    blocks.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    for (const item of blocks) {
                      const parsed = parseValue(item.text);
                      if (parsed) return parsed;
                    }
                    return parseValue(normalize(root.innerText || ''));
                    """,
                    label,
                )
                or ""
            )
        except Exception:
            token = ""

        parsed = self._token_to_float(token)
        if parsed is not None:
            return round(abs(parsed), 2)

        snippet = self._page_text_snippet(max_length=12000)
        section = self._slice_qianniu_data_overview_text(snippet)
        parsed_from_text = self._extract_metric_value_after_label_from_text(section, label)
        if parsed_from_text is not None:
            return round(abs(parsed_from_text), 2)

        self._raise_timeout_with_context(f"未读取到千牛数据页指标：{label}")

    @staticmethod
    def _looks_like_qianniu_data_metric_text(text: str) -> bool:
        """
        识别被数据卡片误当成店铺名的文本。
        """
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized:
            return False
        metric_labels = ("支付金额", "支付买家数", "支付子订单数", "店铺客户数", "净支付金额")
        return any(label in normalized for label in metric_labels) and bool(re.search(r"\d", normalized))

    @staticmethod
    def _slice_qianniu_data_overview_text(text: str) -> str:
        """
        截取千牛【数据】页顶部全店数据区域，避开下方商品/流量表格。
        """
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        start = normalized.find("全店数据")
        if start >= 0:
            normalized = normalized[start:]
        end_candidates = [
            normalized.find(marker)
            for marker in (" 商品 流量 ", "商品 流量", " 标准类目 ", " 指标选择 ")
            if normalized.find(marker) > 0
        ]
        if end_candidates:
            normalized = normalized[: min(end_candidates)]
        return normalized

    def _collect_sycm_dashboard_metrics(self, report_date: date | datetime | str) -> dict[str, Any]:
        """
        从生意参谋按自定义单日读取支付核心指标。
        """
        report_date_str = self._format_report_date(report_date)
        self._open_sycm_dashboard_page()
        self._set_sycm_custom_single_day(report_date_str)

        payment_amount = self._extract_sycm_metric("支付金额")
        payment_buyers = self._extract_sycm_metric("支付买家数")
        try:
            payment_sub_orders = self._extract_sycm_metric("支付子订单数")
        except TimeoutException:
            if not self._click_sycm_metric_next_page():
                raise
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
            payment_sub_orders = self._extract_sycm_metric("支付子订单数")

        shop_name = self._extract_home_shop_name()
        return {
            "shop_name": shop_name,
            "payment_amount": round(float(payment_amount), 2),
            "payment_buyer_count": int(round(payment_buyers)),
            "payment_sub_order_count": int(round(payment_sub_orders)),
        }

    def _open_sycm_dashboard_page(self) -> None:
        """
        打开生意参谋首页。优先尝试千牛左侧【数据】，失败时 URL 直达。
        """
        if "sycm.taobao.com" in (self.get_current_url() or "").lower():
            return

        previous_handles = self._capture_window_handles()
        clicked = self._click_left_panel_text_with_wait(
            ("数据",),
            exact=True,
            timeout_seconds=3.0,
            required=False,
            step_name="已点击左侧菜单：数据",
            min_left=0,
            max_left=190,
            min_top=120,
        )
        if clicked and self._wait_switch_to_sycm_page(previous_handles=previous_handles, timeout_seconds=8.0):
            return

        self._log_step("未能通过左侧【数据】进入生意参谋，改用 URL 直达")
        self._navigate_to_url(self.SYCM_HOME_URL)
        self._wait_until(
            lambda: "sycm.taobao.com" in (self.get_current_url() or "").lower()
            and self._page_contains_text("数据概览"),
            timeout_seconds=max(self.timeout_seconds, 20),
            message="生意参谋页面未加载完成。",
        )

    def _wait_switch_to_sycm_page(
        self,
        previous_handles: set[str],
        timeout_seconds: float = 12.0,
    ) -> bool:
        """
        等待点击【数据】后切换到生意参谋页面。
        """
        driver = self._ensure_driver()
        end_time = time.time() + max(timeout_seconds, 2.0)
        while time.time() < end_time:
            handles = list(self._capture_window_handles())
            new_handles = [handle for handle in handles if handle not in previous_handles]
            ordered_handles = [*new_handles, *[handle for handle in handles if handle not in new_handles]]
            for handle in ordered_handles:
                try:
                    driver.switch_to.window(handle)
                    current_url = (driver.current_url or "").lower()
                except Exception:
                    continue
                if "sycm.taobao.com" in current_url:
                    self._wait_dom_ready()
                    self._wait_until(
                        lambda: self._page_contains_text("数据概览"),
                        timeout_seconds=max(self.timeout_seconds, 15),
                        message="生意参谋数据概览未加载完成。",
                    )
                    return True
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))
        return False

    def _set_sycm_custom_single_day(self, report_date: str) -> None:
        """
        在生意参谋选择自定义单日日期。
        """
        target = self._format_report_date(report_date)
        if self._is_sycm_report_date_selected(target):
            self._log_step(f"生意参谋已选择日期：{target}")
            return

        if not self._click_text_with_wait(("自定义",), exact=True, timeout_seconds=5.0, required=False):
            self._raise_timeout_with_context("生意参谋未找到【自定义】日期按钮。")
        time.sleep(max(self.ui_poll_interval_seconds, 0.2))

        if not self._click_sycm_calendar_day(target):
            self._raise_timeout_with_context(f"生意参谋未能选择日期：{target}")

        if not self._click_text_with_wait(("确定",), exact=True, timeout_seconds=5.0, required=False):
            self._raise_timeout_with_context("生意参谋日期面板未找到【确定】按钮。")

        self._wait_until(
            lambda: self._is_sycm_report_date_selected(target),
            timeout_seconds=max(self.timeout_seconds, 12),
            message=f"生意参谋日期未切换到：{target}",
        )
        self._log_step(f"生意参谋已选择日期：{target}")

    def _is_sycm_report_date_selected(self, report_date: str) -> bool:
        """
        判断生意参谋日期是否已显示为指定单日。
        """
        target = self._format_report_date(report_date)
        compact = re.sub(r"\s+", "", self._page_text_snippet(max_length=4000))
        return f"{target}~{target}" in compact or f"{target}至{target}" in compact

    def _click_sycm_calendar_day(self, report_date: str) -> bool:
        """
        点击生意参谋日期面板中的指定日期。当前先支持可见月份中的日期。
        """
        driver = self._ensure_driver()
        target = self._format_report_date(report_date)
        day_text = str(int(target.rsplit("-", 1)[1]))
        try:
            return bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '');
                    const dayText = String(arguments[1] || '');
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 14 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 200;
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      node.click();
                      return true;
                    };
                    const byAttrs = Array.from(document.querySelectorAll('[title], [aria-label], [data-date]'))
                      .filter(visible)
                      .filter((el) => {
                        const text = `${el.getAttribute('title') || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-date') || ''}`;
                        return text.includes(target);
                      });
                    if (byAttrs.length) return clickNode(byAttrs[0]);

                    const candidates = Array.from(document.querySelectorAll('td, div, span, a, button'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || el.textContent || '') === dayText)
                      .filter((el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.y >= 250 && rect.y <= Math.min(window.innerHeight - 80, 820);
                      });
                    candidates.sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
                    if (!candidates.length) return false;
                    if (candidates.length >= 2) {
                      clickNode(candidates[0]);
                      clickNode(candidates[candidates.length - 1]);
                      return true;
                    }
                    clickNode(candidates[0]);
                    clickNode(candidates[0]);
                    return true;
                    """,
                    target,
                    day_text,
                )
            )
        except Exception:
            return False

    def _extract_sycm_metric(self, label: str) -> float:
        """
        从生意参谋指标卡片中读取数值。
        """
        parsed_from_text = self._extract_metric_value_after_label_from_text(
            self._page_text_snippet(max_length=12000),
            label,
        )
        if parsed_from_text is not None:
            return parsed_from_text
        self._raise_timeout_with_context(f"未读取到生意参谋指标：{label}")

    def _click_sycm_metric_next_page(self) -> bool:
        """
        点击生意参谋指标卡片右侧翻页箭头。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 12 && rect.height >= 12 && rect.x >= 0 && rect.y >= 250 && rect.y <= 850;
                    };
                    const nodes = Array.from(document.querySelectorAll('button, div, span, i, svg, a'))
                      .filter(visible)
                      .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = String(el.innerText || el.textContent || '').trim();
                        const cls = String(el.className || '').toLowerCase();
                        const aria = String(el.getAttribute('aria-label') || '').toLowerCase();
                        return { el, rect, text, cls, aria };
                      })
                      .filter((item) => {
                        if (item.text && !['›', '>', ''].includes(item.text)) return false;
                        if (item.aria.includes('next') || item.aria.includes('下一')) return true;
                        if (item.cls.includes('next') || item.cls.includes('right') || item.cls.includes('arrow')) return true;
                        return item.rect.x >= window.innerWidth * 0.42 && item.rect.x <= window.innerWidth * 0.58 && item.rect.y >= 420;
                      });
                    nodes.sort((a, b) => b.rect.x - a.rect.x);
                    if (!nodes.length) return false;
                    const node = nodes[0].el;
                    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    node.click();
                    return true;
                    """
                )
            )
        except Exception:
            return False

    def _extract_home_shop_name(self) -> str:
        """
        在首页读取当前店铺名称。
        """
        driver = self._ensure_driver()

        def _clean_shop_name(raw_value: str) -> str:
            raw_text = str(raw_value or "").strip()
            if not raw_text:
                return ""
            raw_text = re.sub(r"\s*(?:ID|Id|id)\s*[:：].*$", "", raw_text).strip()
            raw_text = re.sub(r"([^\s:：]{2,36}(?:旗舰店|专卖店|专营店|官方店|店铺|店))\s*[:：].*$", r"\1", raw_text).strip()

            # 优先按可视行拆分，取第一条“像店铺名”的行
            lines = [line.strip() for line in re.split(r"[\r\n]+", raw_text) if line.strip()]
            blacklist = (
                "店铺成长",
                "成长层级",
                "保证金",
                "已足额缴纳",
                "已缴纳",
                "Lv.",
                "评分",
                "物流",
                "售后",
                "发货",
                "违规",
                "支付金额",
                "支付买家数",
                "支付子订单数",
            )

            candidate = ""
            for line in lines:
                compact = re.sub(r"\s+", " ", line).strip()
                if not compact:
                    continue
                if any(key in compact for key in blacklist):
                    continue
                if len(compact) < 2 or len(compact) > 36:
                    continue
                candidate = compact
                break

            if not candidate:
                candidate = re.sub(r"\s+", " ", raw_text).strip()

            # 当文本粘连了其他字段时，按关键字切断尾部
            for marker in ("店铺成长", "成长层级", "保证金", "已足额缴纳", "已缴纳", " Lv", "Lv.", "评分"):
                idx = candidate.find(marker)
                if idx > 1:
                    candidate = candidate[:idx].strip()
            candidate = candidate.strip(" -|：:·，,;；")

            # 允许不带“店”字的店铺名（例如：好梦轻奢裙裤）
            if len(candidate) < 2 or len(candidate) > 36:
                return ""
            return candidate

        # 0) 严格优先：使用用户指定的精确 XPath
        exact_xpath = "//*[@id='icestarkNode']/div/div/div[2]/div/div/div[1]/div/div/div[1]/div[2]/div[1]/div"
        for locator in ((By.XPATH, exact_xpath),):
            try:
                nodes = driver.find_elements(*locator)
            except Exception:
                continue
            for node in nodes:
                try:
                    if not node.is_displayed():
                        continue
                    raw_text = (node.text or "").strip()
                    if not raw_text:
                        raw_text = (node.get_attribute("innerText") or "").strip()
                    text = _clean_shop_name(raw_text)
                    if text:
                        return text
                except Exception:
                    continue

        # 0.5) 选择器兜底（仍优先 home_shop_name）
        for locator in self.selectors.get("home_shop_name", ()):
            try:
                nodes = driver.find_elements(*locator)
            except Exception:
                continue
            for node in nodes:
                try:
                    if not node.is_displayed():
                        continue
                    raw_text = (node.text or "").strip()
                    if not raw_text:
                        raw_text = (node.get_attribute("innerText") or "").strip()
                    text = _clean_shop_name(raw_text)
                    if text:
                        return text
                except Exception:
                    continue

        # 千牛统一顶部壳层：历史日期走【数据】页时，店铺名通常在右上角 shopName 节点。
        try:
            token = driver.execute_script(
                """
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 20 && rect.height >= 12
                    && rect.y >= 0 && rect.y <= 100
                    && rect.x >= Math.max(720, window.innerWidth * 0.48);
                };
                const blacklist = /^(管家|协议|下载|规则|消息|反馈|客服|财务|运营|蓝天)$/;
                const nodes = Array.from(
                  document.querySelectorAll(
                    '[class*="shopName"], [class*="ShopName"], [class*="shop-name"], [class*="Shop-name"]'
                  )
                )
                  .filter(visible)
                  .map((el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                      text: normalize(el.innerText || el.textContent),
                      cls: String(el.className || ''),
                      x: rect.x,
                      y: rect.y,
                    };
                  })
                  .filter((item) => item.text.length >= 2 && item.text.length <= 36)
                  .filter((item) => !blacklist.test(item.text))
                  .filter((item) => !/(支付金额|支付买家数|支付子订单数|统计时间|全店数据)/.test(item.text));
                nodes.sort((a, b) => (a.y - b.y) || (b.x - a.x));
                return nodes.length ? nodes[0].text : '';
                """
            )
            shop_name = _clean_shop_name(str(token or ""))
            if shop_name:
                return shop_name
        except Exception:
            pass

        # 优先使用“店铺名 + 保证金”同区域文案
        try:
            token = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 30 && rect.height >= 14 && rect.x >= 0 && rect.y >= 0 && rect.y <= window.innerHeight + 240;
                };
                const blacklist = /(支付金额|支付买家数|支付子订单数|店铺客数|支付转化率|加购人数|实时|近1天|近7天|近30天|统计时间|重要消息|查看详情|客服|消息|规则|财务|推广|订单|数据|客服)/;

                const pickCandidate = (text, rect) => {
                  const t = normalize(text);
                  if (!t || t.length < 2 || t.length > 36) return null;
                  if (blacklist.test(t)) return null;
                  if (!/(店|旗舰店|专卖店|专营店|官方店)/.test(t)) return null;
                  let score = 100;
                  if (t.includes('旗舰店')) score += 40;
                  if (t.includes('专卖店') || t.includes('专营店') || t.includes('官方店')) score += 26;
                  if (rect.y >= 120 && rect.y <= 420) score += 35;
                  if (rect.x >= 160 && rect.x <= 820) score += 25;
                  if (t.includes('vullvan')) score += 5;
                  return { text: t, score };
                };

                // 1) 以“保证金”为锚点，在同容器寻找店铺名
                const guaranteeNodes = Array.from(document.querySelectorAll('div, span, p, a'))
                  .filter(visible)
                  .filter((el) => normalize(el.innerText || el.textContent || '') === '保证金');
                for (const anchor of guaranteeNodes) {
                  let parent = anchor;
                  for (let i = 0; i < 4 && parent; i += 1) {
                    const bucket = Array.from(parent.querySelectorAll('div, span, p, a'))
                      .filter(visible)
                      .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const t = normalize(el.innerText || el.textContent || '');
                        return { el, rect, text: t };
                      })
                      .filter((item) => item.text && item.text.length <= 36);

                    let best = null;
                    let bestScore = -1;
                    for (const item of bucket) {
                      const picked = pickCandidate(item.text, item.rect);
                      if (!picked) continue;
                      if (picked.score > bestScore) {
                        best = picked.text;
                        bestScore = picked.score;
                      }
                    }
                    if (best) return best;
                    parent = parent.parentElement;
                  }
                }

                // 2) 全页候选兜底（首页上半屏）
                const nodes = Array.from(document.querySelectorAll('div, span, p, a'))
                  .filter(visible);
                let fallback = '';
                let fallbackScore = -1;
                for (const node of nodes) {
                  const rect = node.getBoundingClientRect();
                  if (rect.y > window.innerHeight * 0.62) continue;
                  const picked = pickCandidate(node.innerText || node.textContent || '', rect);
                  if (!picked) continue;
                  if (picked.score > fallbackScore) {
                    fallback = picked.text;
                    fallbackScore = picked.score;
                  }
                }
                return fallback;
                """
            )
            shop_name = _clean_shop_name(str(token or ""))
            if shop_name:
                return shop_name
        except Exception:
            pass

        # 兜底：正文正则提取“xxx旗舰店 保证金”
        snippet = self._page_text_snippet(max_length=10000)
        if snippet:
            match = re.search(r"([^\s]{2,36}(?:旗舰店|专卖店|专营店|官方店|店铺))\s+保证金", snippet)
            if match:
                return match.group(1).strip()

        return ""

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
                and self._account_details_controls_visible()
            ),
            timeout_seconds=max(self.timeout_seconds, 18),
            message="账户明细筛选区域未加载完成。",
            selector_keys=(
                "account_details_yesterday_button",
                "account_details_reason_dropdown",
                "account_details_search_button",
            ),
        )

    @staticmethod
    def _clean_account_reason_value(raw_text: str) -> str:
        """
        清理账户明细“原因”控件值，避免把日期/整条筛选栏误认成原因。
        """
        normalized = re.sub(r"\s+", " ", str(raw_text or "")).strip()
        if not normalized:
            return ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s*[~至-]\s*\d{4}-\d{2}-\d{2})?", normalized):
            return ""
        container_markers = (
            "昨天",
            "今天",
            "7日",
            "30日",
            "本月",
            "本年",
            "资金类型",
            "订单编号",
            "业务编号",
            "搜索",
            "重置",
            "完成时间",
            "收支金额",
        )
        if any(marker in normalized for marker in container_markers):
            return ""
        if len(normalized) > 80:
            return ""
        if normalized.startswith("原因"):
            normalized = normalized.replace("原因", "", 1).strip(" :：|/-")
        if normalized.lower() in {"on", "true", "false"}:
            return ""
        if normalized in {"", "原因", "-", "--", "请选择", "全部"}:
            return ""
        if "请选择" in normalized or "全部" in normalized:
            return ""
        return normalized

    def _get_account_reason_input_value(self) -> str:
        """
        读取账户明细“原因”输入框当前 value。用于搜索前判断是否已填入待提交文本。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()

        candidate_xpaths = (
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]//input",
            "//*[self::label or self::span][normalize-space()='原因']/following::input[1]",
        )
        for xpath in candidate_xpaths:
            try:
                inputs = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for input_element in inputs:
                try:
                    if not input_element.is_displayed():
                        continue
                    value = self._clean_account_reason_value(input_element.get_attribute("value") or "")
                    if value:
                        return value
                except Exception:
                    continue

        try:
            value = driver.execute_script(
                """
                function normalize(text) {
                  return String(text || '').replace(/\\s+/g, ' ').trim();
                }
                function visible(el) {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 60 && rect.height >= 16 && rect.x >= 120 && rect.y >= 120 && rect.y <= 820;
                }
                const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
                let best = null;
                let bestScore = -1;
                for (const input of inputs) {
                  const value = normalize(input.value || '');
                  if (!value) continue;
                  if (/^\\d{4}-\\d{2}-\\d{2}$/.test(value)) continue;
                  const placeholder = normalize(input.getAttribute('placeholder') || '');
                  let parent = input.parentElement;
                  let context = `${value} ${placeholder}`;
                  for (let depth = 0; depth < 4 && parent; depth += 1) {
                    context += ' ' + normalize(parent.innerText || '');
                    parent = parent.parentElement;
                  }
                  if (context.includes('搜索') || context.includes('订单编号') || context.includes('业务编号')) continue;
                  if (context.includes('开始时间') || context.includes('结束时间')) continue;
                  let score = 0;
                  if (context.includes('原因')) score += 160;
                  if (placeholder.includes('请选择') || placeholder.includes('原因')) score += 60;
                  if (value.includes('交易赔付')) score += 120;
                  const rect = input.getBoundingClientRect();
                  if (rect.x >= 180 && rect.x <= 860) score += 20;
                  if (rect.y >= 220 && rect.y <= 700) score += 20;
                  if (score > bestScore) {
                    bestScore = score;
                    best = value;
                  }
                }
                return bestScore > 0 ? best : '';
                """
            )
            return self._clean_account_reason_value(str(value or ""))
        except Exception:
            return ""

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
                    raw_values: list[str] = []
                    try:
                        inputs = element.find_elements(By.XPATH, ".//input")
                    except Exception:
                        inputs = []
                    for input_element in inputs:
                        try:
                            raw_values.extend(
                                [
                                    input_element.get_attribute("value") or "",
                                    input_element.get_attribute("title") or "",
                                    input_element.get_attribute("aria-label") or "",
                                ]
                            )
                        except Exception:
                            continue
                    raw_values.extend(
                        [
                            element.get_attribute("value") or "",
                            element.get_attribute("title") or "",
                            element.get_attribute("aria-label") or "",
                            element.text or "",
                        ]
                    )
                    for text in raw_values:
                        normalized = self._clean_account_reason_value(text)
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
                  if (text.length > 80) continue;
                  if (text.includes('搜索') || text.includes('重置') || text.includes('订单编号')) continue;
                  if (text.includes('完成时间') || text.includes('业务编号')) continue;
                  if (text.includes('昨天') || text.includes('今天') || text.includes('7日') || text.includes('30日')) continue;
                  if (text.includes('本月') || text.includes('本年') || text.includes('资金类型')) continue;
                  if (!(text.startsWith('原因') || text.includes('请选择') || text.includes('交易赔付'))) continue;

                  let value = text;
                  if (value.startsWith('原因')) {
                    value = normalize(value.replace(/^原因/, '').replace(/^[:：|/\\-]+/, ''));
                  }
                  if (!value || value === '请选择' || value === '全部') continue;
                  if (value.includes('请选择') || value.includes('全部')) continue;
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
            return self._clean_account_reason_value(str(value or ""))
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
        return self._account_reason_value_matches(current, reason_text)

    def _account_reason_value_matches(self, current: str, reason_text: str) -> bool:
        """
        判断原因控件值/输入值是否匹配目标原因。
        """
        if not current:
            return False
        compact_current = self._compact_selected_text(current, prefixes=("原因", "已选择"))
        if not compact_current:
            return False
        if reason_text == "交易赔付":
            trade_aliases = (
                "交易赔付",
                "交易赔付/违背承诺/违背发货承诺/延迟发货",
                "违背发货承诺",
                "物流轨迹异常",
                "延迟发货",
                "赔付",
            )
            return compact_current in trade_aliases
        return compact_current == self._compact_selected_text(reason_text)

    def _is_account_reason_ready_for_search(self, reason_text: str) -> bool:
        """
        判断搜索前原因条件是否已具备：控件已选中，或可输入框里已填入目标词。
        """
        if self._is_account_reason_selected(reason_text):
            return True
        input_value = self._get_account_reason_input_value()
        return self._account_reason_value_matches(input_value, reason_text)

    @staticmethod
    def _trade_compensation_reason_keywords() -> tuple[str, ...]:
        """
        账户明细中可归入“交易赔付”的原因文案。
        """
        return (
            "交易赔付",
            "违背承诺",
            "违背发货承诺",
            "延迟发货",
            "物流轨迹异常",
            "赔付",
        )

    def _account_reason_text_matches(self, reason_value: str, reason_text: str) -> bool:
        """
        判断表格“原因”列文本是否匹配目标原因。
        """
        normalized_reason = re.sub(r"\s+", " ", str(reason_text or "")).strip()
        normalized_value = re.sub(r"\s+", " ", str(reason_value or "")).strip()
        if not normalized_reason:
            return True
        if not normalized_value:
            return False
        if normalized_reason != "交易赔付":
            return normalized_reason in normalized_value
        return any(keyword in normalized_value for keyword in self._trade_compensation_reason_keywords())

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
            f".//*[self::li or @role='option' or contains(@class,'option') or contains(@class,'item')][normalize-space()='{reason_text}']",
            f".//*[self::li or @role='option' or contains(@class,'option') or contains(@class,'item')][contains(normalize-space(),'{reason_text}')]",
        )
        xpaths_driver = (
            f"//*[self::li or @role='option' or contains(@class,'option') or contains(@class,'item')][normalize-space()='{reason_text}']",
            f"//*[self::li or @role='option' or contains(@class,'option') or contains(@class,'item')][contains(normalize-space(),'{reason_text}')]",
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
                        text = re.sub(
                            r"\s+",
                            " ",
                            (candidate.text or candidate.get_attribute("innerText") or "").strip(),
                        )
                        if not text or "原因" in text or "请选择" in text:
                            continue
                        if any(marker in text for marker in ("搜索", "重置", "订单编号", "业务编号", "资金类型")):
                            continue
                        if reason_text not in text or len(text) > 50:
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

    def _type_account_reason_text(self, reason_text: str) -> bool:
        """
        在账户明细“原因”可输入控件中直接填入原因文本。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        reason_text = str(reason_text or "").strip()
        if not reason_text:
            return False

        def _iter_reason_inputs() -> list[WebElement]:
            candidates: list[WebElement] = []
            xpaths = (
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[1]/form/div[3]//input",
                "//*[self::label or self::span][normalize-space()='原因']/following::input[1]",
                "//*[contains(normalize-space(),'原因') and not(contains(normalize-space(),'搜索'))]//input",
            )
            for xpath in xpaths:
                try:
                    candidates.extend(driver.find_elements(By.XPATH, xpath))
                except Exception:
                    continue

            for locator in self.selectors.get("account_details_reason_dropdown", ()):
                try:
                    controls = driver.find_elements(*locator)
                except Exception:
                    continue
                for control in controls:
                    try:
                        if not control.is_displayed():
                            continue
                        if str(getattr(control, "tag_name", "")).lower() == "input":
                            candidates.append(control)
                        candidates.extend(control.find_elements(By.XPATH, ".//input"))
                    except Exception:
                        continue

            try:
                js_input = driver.execute_script(
                    """
                    function normalize(text) {
                      return String(text || '').replace(/\\s+/g, ' ').trim();
                    }
                    function visible(el) {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 80 && rect.height >= 16 && rect.x >= 120 && rect.y >= 160 && rect.y <= 820;
                    }
                    const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
                    let best = null;
                    let bestScore = -1;
                    for (const input of inputs) {
                      const rect = input.getBoundingClientRect();
                      const placeholder = normalize(input.getAttribute('placeholder') || '');
                      const value = normalize(input.value || '');
                      let parent = input.parentElement;
                      let context = placeholder + ' ' + value;
                      for (let depth = 0; depth < 4 && parent; depth += 1) {
                        context += ' ' + normalize(parent.innerText || '');
                        parent = parent.parentElement;
                      }
                      if (context.includes('搜索') || context.includes('订单编号') || context.includes('业务编号')) continue;
                      let score = 0;
                      if (context.includes('原因')) score += 160;
                      if (placeholder.includes('请选择') || placeholder.includes('原因')) score += 80;
                      if (value.includes('交易赔付')) score += 80;
                      if (rect.x >= 180 && rect.x <= 860) score += 30;
                      if (rect.y >= 220 && rect.y <= 700) score += 30;
                      if (rect.width >= 120 && rect.width <= 520) score += 20;
                      if (score > bestScore) {
                        bestScore = score;
                        best = input;
                      }
                    }
                    return bestScore > 0 ? best : null;
                    """
                )
                if js_input is not None:
                    candidates.append(js_input)
            except Exception:
                pass

            unique: list[WebElement] = []
            seen: set[str] = set()
            for candidate in candidates:
                try:
                    key = candidate.id
                except Exception:
                    key = str(id(candidate))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(candidate)
            return unique

        for input_element in _iter_reason_inputs():
            try:
                if not input_element.is_displayed() or not input_element.is_enabled():
                    continue
                self._click_with_retry(input_element)
                time.sleep(max(self.ui_poll_interval_seconds, 0.08))
                try:
                    input_element.clear()
                except Exception:
                    for chord in (Keys.COMMAND + "a", Keys.CONTROL + "a"):
                        try:
                            input_element.send_keys(chord)
                            input_element.send_keys(Keys.BACKSPACE)
                            break
                        except Exception:
                            continue
                input_element.send_keys(reason_text)
                try:
                    driver.execute_script(
                        """
                        const input = arguments[0];
                        const value = arguments[1];
                        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                        if (input.value !== value && setter) {
                          setter.call(input, value);
                        }
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        input_element,
                        reason_text,
                    )
                except Exception:
                    pass
                return True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return False

    def _click_first_account_reason_result(self, reason_text: str) -> bool:
        """
        点击“原因”输入后过滤出来的第一条下拉结果。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        reason_text = str(reason_text or "").strip()
        if not reason_text:
            return False

        def _click_option(option: WebElement) -> bool:
            try:
                clicked = driver.execute_script(
                    """
                    const node = arguments[0];
                    if (!node) return false;
                    const targets = [
                      node.matches && node.matches("[class*='label-selectable']") ? node : null,
                      node.querySelector && node.querySelector("[class*='label-selectable']"),
                      node.querySelector && node.querySelector("[class*='label']"),
                      node.querySelector && node.querySelector("span"),
                      node,
                    ].filter(Boolean);
                    for (const target of targets) {
                      try {
                        target.scrollIntoView({ block: 'center', inline: 'nearest' });
                      } catch (err) {}
                      const rect = target.getBoundingClientRect();
                      if (rect.width <= 0 || rect.height <= 0) continue;
                      const clientX = rect.left + rect.width / 2;
                      const clientY = rect.top + rect.height / 2;
                      const events = [
                        new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window, clientX, clientY }),
                        new MouseEvent('mousemove', { bubbles: true, cancelable: true, view: window, clientX, clientY }),
                        new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window, clientX, clientY }),
                        new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window, clientX, clientY }),
                        new MouseEvent('click', { bubbles: true, cancelable: true, view: window, clientX, clientY }),
                      ];
                      for (const event of events) {
                        target.dispatchEvent(event);
                      }
                      try {
                        target.click();
                      } catch (err) {}
                      return true;
                    }
                    return false;
                    """,
                    option,
                )
                if not clicked:
                    self._click_with_retry(option)
                time.sleep(max(self.ui_poll_interval_seconds, 0.16))
                return True
            except StaleElementReferenceException:
                raise
            except Exception:
                return False

        visible_label_xpaths = (
            f"//div[contains(@class,'next-tree-node-label-selectable') and normalize-space()='{reason_text}']",
            f"//div[contains(@class,'next-tree-node-label-selectable') and contains(normalize-space(),'{reason_text}')]",
            f"//div[contains(@class,'next-tree-node-inner') and contains(normalize-space(),'{reason_text}') "
            "and not(ancestor::*[contains(@style,'display: none')])]",
        )
        for xpath in visible_label_xpaths:
            try:
                options = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for option in options:
                try:
                    if not option.is_displayed() or not option.is_enabled():
                        continue
                    text = re.sub(r"\s+", " ", (option.text or option.get_attribute("innerText") or "")).strip()
                    if reason_text not in text:
                        continue
                    if _click_option(option):
                        return True
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

        verified_xpath = "/html/body/div[4]/div/div/ul/li[4]/div"
        for _ in range(3):
            try:
                options = driver.find_elements(By.XPATH, verified_xpath)
            except Exception:
                options = []
            option = options[0] if options else None
            if option is None:
                break
            try:
                if not option.is_displayed() or not option.is_enabled():
                    break
                text = re.sub(r"\s+", " ", (option.text or option.get_attribute("innerText") or "")).strip()
                if reason_text not in text:
                    break
                if _click_option(option):
                    return True
            except StaleElementReferenceException:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                continue
            except Exception:
                continue

        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const target = String(arguments[0] || '').trim();
                    if (!target) return false;

                    function normalize(text) {
                      return String(text || '').replace(/\\s+/g, ' ').trim();
                    }
                    function visible(el) {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 80 && rect.y >= 120 && rect.y <= 980;
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
                    function findReasonInput() {
                      const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
                      let best = null;
                      let bestScore = -1;
                      for (const input of inputs) {
                        const rect = input.getBoundingClientRect();
                        const value = normalize(input.value || '');
                        const placeholder = normalize(input.getAttribute('placeholder') || '');
                        let parent = input.parentElement;
                        let context = `${value} ${placeholder}`;
                        for (let depth = 0; depth < 4 && parent; depth += 1) {
                          context += ' ' + normalize(parent.innerText || '');
                          parent = parent.parentElement;
                        }
                        if (context.includes('搜索') || context.includes('订单编号') || context.includes('业务编号')) continue;
                        let score = 0;
                        if (value.includes(target)) score += 180;
                        if (context.includes('原因')) score += 120;
                        if (placeholder.includes('请选择') || placeholder.includes('原因')) score += 60;
                        if (rect.x >= 160 && rect.x <= 900) score += 20;
                        if (rect.y >= 180 && rect.y <= 760) score += 20;
                        if (score > bestScore) {
                          bestScore = score;
                          best = input;
                        }
                      }
                      return bestScore > 0 ? best : null;
                    }

                    const input = findReasonInput();
                    const inputRect = input ? input.getBoundingClientRect() : null;
                    const panels = Array.from(document.querySelectorAll('ul, div, [role="listbox"]'))
                      .filter(visible)
                      .filter((panel) => {
                        const text = normalize(panel.innerText || '');
                        if (!text.includes(target)) return false;
                        const rect = panel.getBoundingClientRect();
                        if (rect.width < 160 || rect.height < 24) return false;
                        if (text.includes('完成时间') || text.includes('收支金额') || text.includes('现金总余额')) return false;
                        if (inputRect) {
                          if (rect.top < inputRect.bottom - 12) return false;
                          if (rect.top > inputRect.bottom + 360) return false;
                          if (rect.right < inputRect.left - 80 || rect.left > inputRect.right + 120) return false;
                        }
                        return true;
                      })
                      .map((panel) => {
                        const rect = panel.getBoundingClientRect();
                        const cls = String(panel.className || '').toLowerCase();
                        let score = 0;
                        if (cls.includes('dropdown') || cls.includes('select') || cls.includes('menu') || cls.includes('popup')) score += 200;
                        if (panel.querySelector('li,[role="option"],[class*="option"],[class*="tree"]')) score += 120;
                        if (inputRect) score -= Math.abs(rect.top - inputRect.bottom);
                        return { panel, rect, score };
                      })
                      .sort((a, b) => b.score - a.score || a.rect.top - b.rect.top);

                    const scopes = panels.length ? panels.map((item) => item.panel) : [document.body];
                    for (const scope of scopes.slice(0, 4)) {
                      const optionNodes = Array.from(
                        scope.querySelectorAll('li, [role="option"], [class*="option"], [class*="menu-item"], [class*="tree-node"], div, span')
                      );
                      const candidates = [];
                      for (const node of optionNodes) {
                        if (!visible(node)) continue;
                        const text = normalize(node.innerText || node.textContent || '');
                        if (!text || !text.includes(target)) continue;
                        if (text.includes('原因') || text.includes('请选择')) continue;
                        if (text.includes('搜索') || text.includes('重置') || text.includes('订单编号') || text.includes('业务编号')) continue;
                        if (text.length > 80) continue;
                        const rect = node.getBoundingClientRect();
                        if (inputRect && rect.top < inputRect.bottom - 12) continue;
                        const cls = String(node.className || '').toLowerCase();
                        const parentCls = String((node.parentElement && node.parentElement.className) || '').toLowerCase();
                        const dropdownLike =
                          node.tagName === 'LI' ||
                          node.getAttribute('role') === 'option' ||
                          cls.includes('option') ||
                          cls.includes('item') ||
                          cls.includes('tree') ||
                          parentCls.includes('dropdown') ||
                          parentCls.includes('select') ||
                          parentCls.includes('menu') ||
                          parentCls.includes('tree');
                        if (!dropdownLike && panels.length === 0) continue;
                        let score = 0;
                        if (text === target) score += 200;
                        if (text.startsWith(target)) score += 120;
                        if (node.tagName === 'LI' || node.getAttribute('role') === 'option') score += 80;
                        if (cls.includes('option') || cls.includes('item') || cls.includes('tree')) score += 40;
                        candidates.push({ node, rect, score });
                      }
                      candidates.sort((a, b) => b.score - a.score || a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                      if (candidates.length && clickNode(candidates[0].node)) {
                        return true;
                      }
                    }
                    return false;
                    """,
                    reason_text,
                )
            )
            if clicked:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                return True
        except Exception:
            pass

        xpaths = (
            f"(//*[self::li or @role='option' or contains(@class,'option') or contains(@class,'item') or contains(@class,'tree')]"
            f"[contains(normalize-space(),'{reason_text}')])[1]",
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
                    text = re.sub(r"\s+", " ", (option.text or option.get_attribute("innerText") or "")).strip()
                    if not text or reason_text not in text:
                        continue
                    if any(marker in text for marker in ("原因", "请选择", "搜索", "重置", "订单编号", "业务编号")):
                        continue
                    self._click_with_retry(option)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue
        return False

    def _select_account_reason_trade_compensation(self) -> bool:
        """
        在账户明细页面输入 原因=交易赔付，并点击过滤结果第一项完成选中。
        """
        self._ensure_account_details_context()
        if self._is_account_reason_selected("交易赔付"):
            return True

        for attempt in range(6):
            if self._type_account_reason_text("交易赔付"):
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                if self._click_first_account_reason_result("交易赔付"):
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    if self._is_account_reason_ready_for_search("交易赔付"):
                        self._click_blank_area()
                        return True
                if self._is_account_reason_ready_for_search("交易赔付"):
                    self._click_blank_area()
                    return True

            if attempt == 0:
                self._open_account_reason_dropdown()
            else:
                self._click_blank_area()
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))

        current_reason = self._get_account_reason_control_value() or "<未识别>"
        visible_options = self._list_visible_account_reason_options()
        options_preview = " | ".join(visible_options) if visible_options else "<未识别>"
        self._log_step(
            "未能稳定输入并选中原因【交易赔付】，"
            f"当前原因控件值：{current_reason}，可见选项：{options_preview}。"
            "将停止后续搜索，避免带错筛选继续执行。"
        )
        self._click_blank_area()
        return False

    def _select_account_details_yesterday(self) -> None:
        """
        在账户明细页面选择时间快捷项“昨天”。
        """
        self._select_account_details_single_day(
            DateConfig.default_report_date_str(),
            prefer_yesterday_shortcut=True,
        )

    def _select_account_details_single_day(
        self,
        report_date: date | datetime | str | None = None,
        prefer_yesterday_shortcut: bool = False,
    ) -> None:
        """
        在账户明细页面选择指定单日。
        """
        self._ensure_account_details_context()
        target_date = self._format_report_date(report_date)
        if prefer_yesterday_shortcut:
            clicked = self._try_click_selector("account_details_yesterday_button") or self._click_by_text(("昨天",))
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            if clicked and self._is_account_details_date_selected(target_date):
                return
        else:
            clicked = False

        for _ in range(4):
            if not self._open_account_details_date_picker():
                continue

            first_clicked = self._click_calendar_day(target_date)
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            second_clicked = self._click_calendar_day(target_date)
            if not second_clicked and self._open_account_details_date_picker():
                second_clicked = self._click_calendar_day(target_date)

            self._click_blank_area()
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))
            if first_clicked and second_clicked and self._is_account_details_date_selected(target_date):
                return

        if not clicked and not self._set_date_range_inputs(target_date, target_date):
            raise TimeoutException(f"无法设置账户明细日期：{target_date} ~ {target_date}。")
        self._click_blank_area()

    def _open_account_details_date_picker(self) -> bool:
        """
        打开账户明细日期选择器，优先点击结束日期输入框以便连续锁定单日。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        selectors = (
            ".bail-range-picker .next-date-picker2 input[placeholder='结束']",
            ".bail-range-picker .next-date-picker2 [role='button']",
            ".bail-range-picker .next-date-picker2",
            ".next-date-picker2 input[placeholder='结束']",
            ".next-date-picker2 [role='button']",
        )
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            for element in elements:
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    self._click_with_retry(element)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    if self._visible_calendar_month_indexes():
                        return True
                except Exception:
                    continue
        return False

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
                  .filter((el) => el.offsetParent !== null)
                  .map((el) => ({ el, rect: el.getBoundingClientRect() }))
                  .filter((item) => item.rect.width >= 40 && item.rect.height >= 14)
                  .sort((a, b) => (a.rect.y - b.rect.y) || (a.rect.x - b.rect.x))
                  .map((item) => item.el);

                const dateLikeInputs = visibleInputs.filter((el) => {
                  const text = `${el.value || ''} ${el.placeholder || ''}`;
                  return /\\d{4}-\\d{2}-\\d{2}/.test(text)
                    || ['开始', '结束'].includes(String(el.placeholder || '').trim());
                });

                if (dateLikeInputs.length < 2) {
                  return false;
                }

                const target = [dateLikeInputs[0], dateLikeInputs[1]];
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                const fireInput = (el, value) => {
                  el.focus();
                  if (setter) {
                    setter.call(el, '');
                  } else {
                    el.value = '';
                  }
                  el.dispatchEvent(
                    typeof InputEvent === 'function'
                      ? new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null })
                      : new Event('input', { bubbles: true })
                  );
                  if (setter) {
                    setter.call(el, value);
                  } else {
                    el.value = value;
                  }
                  el.dispatchEvent(
                    typeof InputEvent === 'function'
                      ? new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value })
                      : new Event('input', { bubbles: true })
                  );
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter', code: 'Enter' }));
                  el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter', code: 'Enter' }));
                  el.blur();
                };

                fireInput(target[0], startDate);
                fireInput(target[1], endDate);

                return true;
                """,
                start_date,
                end_date,
            )
            return bool(updated)
        except Exception:
            return False

    def _is_account_details_date_selected(self, report_date: str) -> bool:
        """
        判断账户明细筛选区日期是否已显示为指定单日。
        """
        target_date = self._format_report_date(report_date)
        tokens = self._extract_account_details_date_tokens()
        if len(tokens) < 2:
            return False
        return tokens[0] == target_date and tokens[1] == target_date

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
        target_month = self._calendar_month_index(report_date)
        for _ in range(36):
            if self._click_exact_calendar_day(report_date):
                return True

            visible_months = self._visible_calendar_month_indexes()
            if not visible_months:
                return False

            first_month = min(visible_months)
            last_month = max(visible_months)
            if target_month < first_month:
                if not self._click_calendar_month_nav("prev"):
                    return False
            elif target_month > last_month:
                if not self._click_calendar_month_nav("next"):
                    return False
            else:
                # 目标月份已可见但找不到完整日期，不能退化成只按“31”之类的数字点击。
                return False
            time.sleep(max(self.ui_poll_interval_seconds, 0.12))

        return self._click_exact_calendar_day(report_date)

    @staticmethod
    def _calendar_month_index(date_text: str) -> int:
        """
        将 YYYY-MM-DD / YYYY-MM 转成可比较的月份序号。
        """
        year = int(date_text[:4])
        month = int(date_text[5:7])
        return year * 12 + month

    def _click_exact_calendar_day(self, report_date: str) -> bool:
        """
        只点击能通过完整日期属性确认的日历格子。
        """
        driver = self._ensure_driver()
        xpaths = (
            f"//*[@title='{report_date}']",
            f"//*[contains(@title,'{report_date}')]",
            f"//*[contains(@aria-label,'{report_date}')]",
            f"//*[contains(@data-date,'{report_date}')]",
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
                    if not (0 <= x <= 980 and 180 <= y <= 920):
                        continue
                    self._click_with_retry(element)
                    return True
                except Exception:
                    continue
        return False

    def _visible_calendar_month_indexes(self) -> list[int]:
        """
        读取当前日期面板可见的月份。
        """
        driver = self._ensure_driver()
        try:
            raw_months = driver.execute_script(
                """
                function visible(el) {
                  const rect = el.getBoundingClientRect();
                  const style = getComputedStyle(el);
                  return !!(rect.width && rect.height && style.display !== 'none' && style.visibility !== 'hidden');
                }
                const headers = Array.from(
                  document.querySelectorAll(
                    '.next-date-picker2-overlay[aria-hidden="false"] .next-calendar2-header, ' +
                    '.next-date-picker2-overlay .next-calendar2-header, ' +
                    '.next-calendar2-header'
                  )
                ).filter(visible);
                const result = [];
                const seen = new Set();
                for (const header of headers) {
                  const text = String(header.innerText || header.textContent || '').replace(/\\s+/g, '');
                  const match = text.match(/(\\d{4})年(\\d{1,2})月/);
                  if (!match) continue;
                  const key = `${match[1]}-${match[2]}`;
                  if (seen.has(key)) continue;
                  seen.add(key);
                  result.push([Number(match[1]), Number(match[2])]);
                }
                return result;
                """
            )
        except Exception:
            return []

        months: list[int] = []
        if not isinstance(raw_months, list):
            return months

        for item in raw_months:
            try:
                if isinstance(item, dict):
                    year = int(item.get("year"))
                    month = int(item.get("month"))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    year = int(item[0])
                    month = int(item[1])
                else:
                    match = re.search(r"(\d{4})\D+(\d{1,2})", str(item))
                    if not match:
                        continue
                    year = int(match.group(1))
                    month = int(match.group(2))
                if 1 <= month <= 12:
                    months.append(year * 12 + month)
            except Exception:
                continue
        return months

    def _click_calendar_month_nav(self, direction: str) -> bool:
        """
        点击日期面板的上一月/下一月按钮。
        """
        driver = self._ensure_driver()
        icon_class = "next-icon-arrow-left" if direction == "prev" else "next-icon-arrow-right"
        xpaths = (
            "//*[contains(@class,'next-date-picker2-overlay') and not(@aria-hidden='true')]"
            f"//button[.//*[contains(concat(' ', normalize-space(@class), ' '), ' {icon_class} ')]]",
            f"//button[.//*[contains(concat(' ', normalize-space(@class), ' '), ' {icon_class} ')]]",
        )
        for xpath in xpaths:
            try:
                buttons = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for button in buttons:
                try:
                    if not button.is_displayed() or not button.is_enabled():
                        continue
                    rect = button.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if not (0 <= x <= 980 and 180 <= y <= 920):
                        continue
                    self._click_with_retry(button)
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

    @staticmethod
    def _bill_summary_business_filter_labels() -> tuple[str, ...]:
        """
        收支账单业务筛选的候选标签，优先业务大类，兼容旧页面业务小类。
        """
        return ("业务大类", "业务小类")

    @staticmethod
    def _compact_selected_text(text: str, prefixes: tuple[str, ...] = ()) -> str:
        """
        将下拉控件显示值规整成用于精确比较的文本。
        """
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized:
            return ""
        if any(marker in normalized for marker in ("请选择", "全部")):
            return ""
        for prefix in prefixes:
            if prefix and normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip(" :：|/-")
        return re.sub(r"\s+", "", normalized)

    def _is_bill_summary_business_selected(
        self,
        business_name: str,
        filter_label: str | None = None,
    ) -> bool:
        """
        判断收支账单业务筛选是否已选中目标值。
        """
        driver = self._ensure_driver()
        labels = (filter_label,) if filter_label else self._bill_summary_business_filter_labels()
        target_compact = self._compact_selected_text(business_name)
        if not target_compact:
            return False

        def _is_selected_value(raw: str) -> bool:
            normalized = re.sub(r"\s+", " ", str(raw or "")).strip()
            if not normalized:
                return False
            # 只接受筛选控件自身的值。结果表、汇总区、下拉候选项混合文本都不能算选中。
            reject_markers = (
                "请选择",
                "全部",
                "CNY",
                "本月付款",
                "付款金额",
                "扣费金额",
                "扣费金额合计",
                "下载明细",
                "业务范围",
                "页面公告",
                "搜索",
                "重置",
                " | ",
            )
            if any(marker in normalized for marker in reject_markers):
                return False
            if len(normalized) > 80:
                return False
            compact = self._compact_selected_text(normalized, prefixes=(*labels, "已选择"))
            return compact == target_compact

        for locator in self.selectors.get("bill_summary_business_dropdown_control", ()):
            try:
                controls = driver.find_elements(*locator)
            except Exception:
                continue
            for control in controls:
                try:
                    if not control.is_displayed():
                        continue
                    raw_values = (
                        control.text or "",
                        control.get_attribute("value") or "",
                        control.get_attribute("innerText") or "",
                        control.get_attribute("title") or "",
                        control.get_attribute("aria-label") or "",
                    )
                    for raw in raw_values:
                        if _is_selected_value(raw):
                            return True

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
                                    t = normalize(node.value || '');
                                  } else {
                                    t = normalize(node.innerText || '');
                                  }
                                  if (!t) continue;
                                  if (t.length > 60) continue;
                                  if (t === '业务大类' || t === '业务小类') continue;
                                  values.push(t);
                                }
                                return values.join(' | ');
                                """,
                                control,
                            )
                        ).strip()
                    except Exception:
                        text = ""
                    if _is_selected_value(text):
                        return True
                except Exception:
                    continue
        return False

    def _open_bill_summary_business_dropdown(self, filter_label: str = "业务大类") -> bool:
        """
        打开收支账单“业务大类/业务小类”下拉框。
        """
        driver = self._ensure_driver()
        label = (filter_label or "业务大类").strip()
        try:
            clicked_by_label = bool(
                driver.execute_script(
                    """
                    const label = String(arguments[0] || '').trim();
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width >= 20 && rect.height >= 12 && rect.x >= 60 && rect.y >= 90;
                    };
                    const clickArrow = (el) => {
                      if (!el) return false;
                      try {
                        el.scrollIntoView({ block: 'center', inline: 'nearest' });
                      } catch (err) {}
                      const rect = el.getBoundingClientRect();
                      const x = Math.max(rect.right - 10, rect.left + 8);
                      const y = rect.top + rect.height / 2;
                      const target = document.elementFromPoint(x, y) || el;
                      try {
                        target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        target.click();
                        return true;
                      } catch (err) {
                        try {
                          el.click();
                          return true;
                        } catch (innerErr) {
                          return false;
                        }
                      }
                    };
                    const labelNodes = Array.from(document.querySelectorAll('label, span, div'))
                      .filter(visible)
                      .filter((el) => normalize(el.innerText || el.textContent || '') === label);
                    let best = null;
                    let bestScore = -1;
                    for (const anchor of labelNodes) {
                      const anchorRect = anchor.getBoundingClientRect();
                      let parent = anchor;
                      for (let depth = 0; depth < 5 && parent; depth += 1) {
                        const nodes = Array.from(parent.querySelectorAll('input, div, span, [role="combobox"], [class*="select"], [class*="picker"]'))
                          .filter(visible);
                        for (const node of nodes) {
                          const rect = node.getBoundingClientRect();
                          if (Math.abs(rect.top - anchorRect.top) > 80) continue;
                          if (rect.right <= anchorRect.right) continue;
                          if (rect.width < 80 || rect.height < 18) continue;
                          const text = normalize(node.value || node.innerText || node.textContent || '');
                          if (text.includes('搜索') || text.includes('重置')) continue;
                          let score = 100;
                          if (text.includes('全部') || text.includes('请选择')) score += 80;
                          const cls = String(node.className || '').toLowerCase();
                          if (cls.includes('select') || cls.includes('picker')) score += 45;
                          if (rect.width >= 120 && rect.width <= 420) score += 25;
                          if (score > bestScore) {
                            bestScore = score;
                            best = node;
                          }
                        }
                        parent = parent.parentElement;
                      }
                    }
                    return clickArrow(best);
                    """,
                    label,
                )
            )
            if clicked_by_label:
                time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                return True
        except Exception:
            pass

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

        for candidate_label in (label, *self._bill_summary_business_filter_labels()):
            try:
                controls = driver.find_elements(
                    By.XPATH,
                    (
                        f"//*[contains(normalize-space(),'{candidate_label}') "
                        "and (contains(normalize-space(),'全部') or contains(normalize-space(),'请选择'))]"
                    ),
                )
                for control in controls:
                    try:
                        if not control.is_displayed() or not control.is_enabled():
                            continue
                        rect = control.rect
                        x = float(rect.get("x", -1))
                        y = float(rect.get("y", -1))
                        if not (120 <= x <= 1100 and 120 <= y <= 760):
                            continue
                        self._click_with_retry(control)
                        time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                        return True
                    except Exception:
                        continue
            except Exception:
                pass

        return self._click_text_with_wait(
            (label,),
            exact=False,
            required=False,
            step_name=f"已展开{label}下拉",
        )

    def _click_bill_summary_business_option(self, business_name: str) -> bool:
        """
        在“业务大类/业务小类”下拉面板点击目标项。
        """
        driver = self._ensure_driver()
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
                      return rect.width >= 20 && rect.height >= 14 && rect.x >= 80 && rect.x <= window.innerWidth + 80 && rect.y >= 120 && rect.y <= 940;
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

                    const panels = Array.from(document.querySelectorAll(panelSelectors)).filter((panel) => {
                      if (!visible(panel)) return false;
                      const text = normalize(panel.innerText || '');
                      return text.includes(target);
                    });
                    const scopeNodes = panels.length
                      ? panels.flatMap((panel) => Array.from(panel.querySelectorAll("li, [role='option'], div, span")))
                      : Array.from(document.querySelectorAll("li, [role='option'], [class*='menu-item'], [class*='select-option']"));

                    let best = null;
                    let bestScore = -1;
                    for (const node of scopeNodes) {
                      if (!visible(node)) continue;
                      const text = normalize(node.innerText || node.textContent || '');
                      if (!text) continue;
	                      if (!(text === target || text.includes(target))) continue;
	                      if (text.includes('业务大类') || text.includes('业务小类') || text.includes('搜索') || text.includes('重置')) continue;
	                      if (text.includes('CNY') || text.includes('本月付款') || text.includes('扣费金额') || text.includes('下载明细')) continue;
	                      if (text.length > 40) continue;
	                      const rect = node.getBoundingClientRect();
                      let score = 100;
                      if (text === target) score += 120;
                      if (rect.width <= 420) score += 25;
                      if (rect.x >= 120 && rect.x <= window.innerWidth - 80) score += 25;
	                      const cls = String(node.className || '').toLowerCase();
	                      const parentCls = String((node.parentElement && node.parentElement.className) || '').toLowerCase();
	                      const role = String(node.getAttribute('role') || '').toLowerCase();
	                      const dropdownLike =
	                        role === 'option' ||
	                        node.tagName === 'LI' ||
	                        cls.includes('option') ||
	                        cls.includes('item') ||
	                        cls.includes('menu') ||
	                        parentCls.includes('dropdown') ||
	                        parentCls.includes('menu') ||
	                        parentCls.includes('select') ||
	                        parentCls.includes('popup') ||
	                        parentCls.includes('overlay');
	                      if (!dropdownLike) continue;
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
            f"//*[(@role='option' or self::li or contains(@class,'option') or contains(@class,'item')) and normalize-space()='{business_name}']",
            f"//*[(@role='option' or self::li or contains(@class,'option') or contains(@class,'item')) and contains(normalize-space(),'{business_name}')]",
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
                    text = re.sub(r"\s+", " ", (option.text or option.get_attribute("innerText") or "")).strip()
                    if not text:
                        continue
                    if any(
                        marker in text
                        for marker in ("CNY", "本月付款", "扣费金额", "下载明细", "业务大类", "业务小类")
                    ):
                        continue
                    if business_name not in text or len(text) > 40:
                        continue
                    rect = option.rect
                    x = float(rect.get("x", -1))
                    y = float(rect.get("y", -1))
                    if not (80 <= x <= 1400 and 120 <= y <= 940):
                        continue
                    self._click_with_retry(option)
                    time.sleep(max(self.ui_poll_interval_seconds, 0.12))
                    return True
                except Exception:
                    continue
        return False

    def _set_bill_summary_business_category(self, business_name: str) -> str:
        """
        设置收支账单业务筛选为目标值，优先“业务大类”，兼容“业务小类”。
        """
        for label in self._bill_summary_business_filter_labels():
            if self._is_bill_summary_business_selected(business_name, filter_label=label):
                return label

        for label in self._bill_summary_business_filter_labels():
            for _ in range(4):
                self._close_corner_popup_if_present()
                self._open_bill_summary_business_dropdown(filter_label=label)
                if self._click_bill_summary_business_option(business_name):
                    self._click_blank_area()
                    if self._is_bill_summary_business_selected(business_name, filter_label=label):
                        return label
                time.sleep(max(self.ui_poll_interval_seconds, 0.15))

        self._raise_timeout_with_context(
            f"收支账单业务大类/小类未稳定选中：{business_name}",
            selector_keys=("bill_summary_business_dropdown_control", "bill_summary_business_cross_border_option"),
            extra_details=(f"页面片段：{self._page_text_snippet(max_length=260)}",),
        )
        return self._bill_summary_business_filter_labels()[0]

    def _set_bill_summary_business_subcategory(self, business_name: str) -> None:
        """
        兼容旧调用：设置收支账单业务筛选。
        """
        self._set_bill_summary_business_category(business_name)

    def _close_bill_update_mask_if_present(self) -> None:
        """
        关闭收支账单说明蒙版。
        """
        if not self._page_contains_text("收支账单更新了"):
            return
        _ = self._click_by_text(("关闭",))
        self._click_blank_area()

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
                  if (rect.x < 0 || rect.x > 980) continue;
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
                    if x < 0 or x > 980 or y < 120 or y > 760:
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
        reason_value = (
            self._get_account_reason_control_value()
            or self._get_account_reason_input_value()
            or "<未识别>"
        )
        date_tokens = self._extract_account_details_date_tokens()
        date_value = " ~ ".join(date_tokens) if date_tokens else "<未识别>"
        self._log_step(f"搜索前筛选状态：日期={date_value}，原因={reason_value}")

    def _snapshot_account_details_rows(self) -> str:
        """
        记录当前账户明细表格前几行文本，用于等待搜索结果变化。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        try:
            rows = driver.find_elements(By.XPATH, "//*[@id='app']//table/tbody/tr")
        except Exception:
            return ""
        texts: list[str] = []
        for row in rows[:6]:
            try:
                if not row.is_displayed():
                    continue
                text = re.sub(r"\s+", " ", (row.text or "")).strip()
                if text:
                    texts.append(text[:220])
            except Exception:
                continue
        return "\n".join(texts)

    def _wait_account_details_results_settled(self, previous_snapshot: Optional[str] = None) -> None:
        """
        点击搜索后等待账户明细表格刷新/稳定。
        """
        start_time = time.time()
        timeout_seconds = max(self.timeout_seconds, 8)
        last_snapshot = previous_snapshot or ""
        while time.time() - start_time < timeout_seconds:
            current_snapshot = self._snapshot_account_details_rows()
            if current_snapshot and (not last_snapshot or current_snapshot != last_snapshot):
                time.sleep(max(self.ui_poll_interval_seconds, 0.15))
                return
            no_data_markers = ("暂无数据", "暂无记录", "暂无结果", "没有数据", "未查询到", "共0条")
            if any(self._page_contains_text(marker) for marker in no_data_markers):
                return
            time.sleep(max(self.ui_poll_interval_seconds, 0.15))

    def _collect_account_details_visible_reason_cells(self, limit: int = 12) -> list[str]:
        """
        读取当前账户明细表格可见行的“原因”列。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        row_xpaths = (
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            "//*[@id='app']//table/tbody/tr",
        )
        reasons: list[str] = []
        for xpath in row_xpaths:
            try:
                rows = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for row in rows:
                if len(reasons) >= max(limit, 1):
                    break
                try:
                    if not row.is_displayed():
                        continue
                    cells = row.find_elements(By.XPATH, "./td")
                    if len(cells) >= 2:
                        text = re.sub(r"\s+", " ", (cells[1].text or cells[1].get_attribute("innerText") or "")).strip()
                    else:
                        text = ""
                    if text:
                        reasons.append(text)
                except Exception:
                    continue
            if reasons:
                break
        return reasons

    def _collect_account_details_visible_date_cells(self, limit: int = 12) -> list[str]:
        """
        读取当前账户明细表格可见行的“完成时间”列日期。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()
        row_xpaths = (
            "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            "//*[@id='app']//table/tbody/tr",
        )
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
        dates: list[str] = []
        for xpath in row_xpaths:
            try:
                rows = driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for row in rows:
                if len(dates) >= max(limit, 1):
                    break
                try:
                    if not row.is_displayed():
                        continue
                    cells = row.find_elements(By.XPATH, "./td")
                    if cells:
                        text = re.sub(r"\s+", " ", (cells[0].text or cells[0].get_attribute("innerText") or "")).strip()
                    else:
                        text = re.sub(r"\s+", " ", (row.text or "")).strip()
                    match = date_pattern.search(text)
                    if match:
                        dates.append(match.group(0))
                except Exception:
                    continue
            if dates:
                break
        return dates

    def _account_details_visible_rows_match_date(self, report_date: str) -> bool:
        """
        搜索后校验当前可见表格行是否都属于目标完成日期；无数据时视为可接受。
        """
        target_date = self._format_report_date(report_date)
        dates = self._collect_account_details_visible_date_cells(limit=12)
        if not dates:
            no_data_markers = ("暂无数据", "暂无记录", "暂无结果", "没有数据", "未查询到", "共0条")
            return any(self._page_contains_text(marker) for marker in no_data_markers)
        return all(item == target_date for item in dates)

    def _account_details_visible_rows_match_reason(self, reason_text: str) -> bool:
        """
        搜索后校验当前可见表格行是否都落在目标原因内；无数据时视为可接受。
        """
        reasons = self._collect_account_details_visible_reason_cells(limit=12)
        if not reasons:
            no_data_markers = ("暂无数据", "暂无记录", "暂无结果", "没有数据", "未查询到", "共0条")
            return any(self._page_contains_text(marker) for marker in no_data_markers)
        return all(self._account_reason_text_matches(reason, reason_text) for reason in reasons)

    def _sum_outgoing_amount_on_account_details(
        self,
        report_date: Optional[str] = None,
        reason_text: Optional[str] = None,
    ) -> float:
        """
        汇总账户明细中操作类型为“出账”的收支金额绝对值。
        """
        self._ensure_account_details_context()
        driver = self._ensure_driver()

        normalized_report_date = str(report_date or "").strip()
        normalized_reason = str(reason_text or "").strip()

        def _normalize_cell_text(cell: WebElement) -> str:
            try:
                text = re.sub(r"\s+", " ", (cell.text or "")).strip()
                if not text:
                    text = re.sub(r"\s+", " ", (cell.get_attribute("innerText") or "")).strip()
                return text
            except Exception:
                return ""

        def _row_matches_fallback_text(row_text: str) -> bool:
            normalized_row = re.sub(r"\s+", " ", str(row_text or "")).strip()
            if not normalized_row:
                return False

            if normalized_report_date and normalized_report_date not in normalized_row:
                return False

            if not normalized_reason:
                return True

            if normalized_reason != "交易赔付":
                return normalized_reason in normalized_row

            trade_keywords = self._trade_compensation_reason_keywords()
            return any(keyword in normalized_row for keyword in trade_keywords)

        def _row_matches_structured_cells(cells: list[WebElement]) -> tuple[bool, str]:
            if len(cells) < 4:
                return (False, "")
            date_cell = _normalize_cell_text(cells[0])
            reason_cell = _normalize_cell_text(cells[1])
            operation_cell = _normalize_cell_text(cells[2])
            amount_cell = _normalize_cell_text(cells[3])
            if normalized_report_date and normalized_report_date not in date_cell:
                return (False, amount_cell)
            if "出账" not in operation_cell:
                return (False, amount_cell)
            if not self._account_reason_text_matches(reason_cell, normalized_reason):
                return (False, amount_cell)
            return (True, amount_cell)

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
        seen_visual_amount_keys: set[tuple[int, str]] = set()
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

            try:
                cells = row.find_elements(By.XPATH, "./td")
            except Exception:
                cells = []

            if cells:
                matches_row, cell_text = _row_matches_structured_cells(cells)
                if not matches_row:
                    continue
            elif not _row_matches_fallback_text(row_text):
                continue
            else:
                cell_text = ""
                cell_candidates = row.find_elements(By.XPATH, "./td[4]")
                if not cell_candidates:
                    continue
                cell_text = _normalize_cell_text(cell_candidates[0])
            if not cell_text:
                continue

            amount_key = (
                str(cell_text or "")
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
            try:
                row_y = int(round(float(getattr(row, "rect", {}).get("y"))))
            except Exception:
                row_y = None
            if row_y is not None and amount_key:
                visual_amount_key = (row_y, amount_key)
                if visual_amount_key in seen_visual_amount_keys:
                    continue
                seen_visual_amount_keys.add(visual_amount_key)

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

    def _snapshot_bill_summary_rows(self) -> str:
        """
        记录当前收支账单结果区前几行文本，用于等待搜索刷新。
        """
        driver = self._ensure_driver()
        try:
            texts = driver.execute_script(
                """
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el || el.offsetParent === null) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.width >= 120 && rect.height >= 16 && rect.x >= 80 && rect.x <= 1320 && rect.y >= 120 && rect.y <= 980;
                };
                const rows = Array.from(document.querySelectorAll('tr, [role="row"], div, li'))
                  .filter(visible)
                  .map((el) => normalize(el.innerText || el.textContent || ''))
                  .filter(Boolean)
                  .filter((text) => {
                    if (text.length < 8 || text.length > 520) return false;
                    if (text.includes('业务大类') && text.includes('本月付款')) return false;
                    return /CNY|本月付款|淘宝天猫跨境服务增值费|暂无数据|暂无记录|没有数据|未查询到/.test(text);
                  });
                return Array.from(new Set(rows)).slice(0, 8);
                """
            )
        except Exception:
            return ""
        if not isinstance(texts, list):
            return ""
        return "\n".join(str(item).strip()[:260] for item in texts if str(item).strip())

    def _wait_bill_summary_results_settled(self, previous_snapshot: Optional[str] = None) -> None:
        """
        点击搜索后等待收支账单结果区刷新/稳定，避免读取旧结果。
        """
        start_time = time.time()
        timeout_seconds = max(self.timeout_seconds, 10)
        last_snapshot = previous_snapshot or ""
        no_data_markers = ("暂无数据", "暂无记录", "暂无结果", "没有数据", "未查询到", "共0条")
        while time.time() - start_time < timeout_seconds:
            current_snapshot = self._snapshot_bill_summary_rows()
            if current_snapshot and (not last_snapshot or current_snapshot != last_snapshot):
                time.sleep(max(self.ui_poll_interval_seconds, 0.18))
                return
            if any(self._page_contains_text(marker) for marker in no_data_markers):
                time.sleep(max(self.ui_poll_interval_seconds, 0.18))
                return
            time.sleep(max(self.ui_poll_interval_seconds, 0.18))

        self._log_step("收支账单搜索后结果区未观察到明显变化，继续用当前页面校验读取")

    def _bill_summary_visible_rows_match_business(self, business_name: str) -> bool:
        """
        搜索后校验当前可见结果是否已收敛到目标业务；无数据时视为可接受。
        """
        target = str(business_name or "").strip()
        if not target:
            return False
        snapshot = self._snapshot_bill_summary_rows()
        no_data_markers = ("暂无数据", "暂无记录", "暂无结果", "没有数据", "未查询到", "共0条")
        if not snapshot:
            return any(self._page_contains_text(marker) for marker in no_data_markers)
        if any(marker in snapshot for marker in no_data_markers):
            return True
        row_texts = [line for line in snapshot.splitlines() if line.strip()]
        if not row_texts:
            return False
        business_rows = [line for line in row_texts if target in line]
        return bool(business_rows)

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

    def _collect_home_dashboard_metrics(
        self,
        report_date: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        """
        提取极速版首页核心指标。
        """
        if report_date is not None:
            report_date_str = self._format_report_date(report_date)
            if report_date_str != DateConfig.default_report_date_str():
                metrics = self._collect_qianniu_data_dashboard_metrics(report_date_str)
                if not str(metrics.get("shop_name") or "").strip():
                    fallback_shop_name = self._extract_home_shop_name_from_home_page()
                    if fallback_shop_name:
                        self._log_step(f"首页店铺名兜底识别：{fallback_shop_name}")
                        metrics["shop_name"] = fallback_shop_name
                return metrics

        self._navigate_to_url(self.export_url or "https://myseller.taobao.com/home.htm/QnworkbenchHome/")
        self._close_corner_popup_if_present()
        self._switch_to_speed_version_if_needed()
        self._close_corner_popup_if_present()
        self._set_home_period_last_1day()
        shop_name = self._extract_home_shop_name()
        if shop_name:
            self._log_step(f"首页店铺名：{shop_name}")
        else:
            self._log_step("首页店铺名未识别，文件名将使用默认前缀")

        payment_amount = self._extract_home_metric("支付金额")
        payment_buyers = self._extract_home_metric("支付买家数")
        payment_sub_orders = self._extract_home_metric("支付子订单数")

        return {
            "shop_name": shop_name,
            "payment_amount": round(float(payment_amount), 2),
            "payment_buyer_count": int(round(payment_buyers)),
            "payment_sub_order_count": int(round(payment_sub_orders)),
        }

    def _extract_home_shop_name_from_home_page(self) -> str:
        """
        回到千牛首页读取店铺名，用于历史日期数据页无法识别店铺名时兜底。
        """
        try:
            shop_name = self._extract_home_shop_name()
            if shop_name and not self._looks_like_qianniu_data_metric_text(shop_name):
                return shop_name
        except Exception:
            pass

        try:
            self._navigate_to_url(self.export_url or "https://myseller.taobao.com/home.htm/QnworkbenchHome/")
            self._close_corner_popup_if_present()
            self._switch_to_speed_version_if_needed()
            self._close_corner_popup_if_present()
            shop_name = self._extract_home_shop_name()
            if self._looks_like_qianniu_data_metric_text(shop_name):
                return ""
            return shop_name
        except Exception as exc:
            self._log_step(f"首页店铺名兜底识别失败：{type(exc).__name__}: {exc}")
            return ""

    def _collect_trade_compensation_amount(
        self,
        report_date: date | datetime | str | None = None,
    ) -> float:
        """
        在“财务 -> 对账管理 -> 账户明细”中提取交易赔付（出账）金额。
        """
        self._navigate_to_account_details_page()
        self._close_corner_popup_if_present()
        self._wait_account_details_filters_ready()

        self._log_step("账户明细筛选区已加载")
        report_date_str = self._format_report_date(report_date)
        if report_date is None:
            self._select_account_details_yesterday()
        else:
            self._select_account_details_single_day(report_date_str)
        self._log_step(f"账户明细已选择日期：{report_date_str}")
        if not self._is_account_details_date_selected(report_date_str):
            self._raise_timeout_with_context(
                f"账户明细日期筛选未生效：{report_date_str} ~ {report_date_str}",
                selector_keys=("account_details_yesterday_button", "account_details_search_button"),
            )
        reason_selected = self._select_account_reason_trade_compensation()
        if reason_selected:
            self._log_step("账户明细已选择原因：交易赔付")
        else:
            self._raise_timeout_with_context(
                "账户明细原因未稳定选中：交易赔付",
                selector_keys=("account_details_reason_dropdown", "account_details_reason_trade_compensation"),
            )
        self._click_blank_area()
        if not self._is_account_reason_ready_for_search("交易赔付"):
            self._raise_timeout_with_context(
                "账户明细原因筛选未生效：交易赔付",
                selector_keys=("account_details_reason_dropdown", "account_details_reason_trade_compensation"),
            )

        self._log_account_details_filter_state()
        previous_snapshot = self._snapshot_account_details_rows()
        self._click_account_details_search_button()
        self._log_step("账户明细已点击搜索")
        self._wait_account_details_results_settled(previous_snapshot=previous_snapshot)
        if not self._account_details_visible_rows_match_date(report_date_str):
            visible_dates = self._collect_account_details_visible_date_cells(limit=8)
            dates_preview = " | ".join(visible_dates) if visible_dates else "<未识别>"
            self._raise_timeout_with_context(
                f"账户明细日期搜索后结果未收敛到：{report_date_str}",
                selector_keys=("account_details_yesterday_button", "account_details_search_button"),
                extra_details=(f"可见结果完成时间：{dates_preview}",),
            )
        if not self._account_details_visible_rows_match_reason("交易赔付"):
            visible_reasons = self._collect_account_details_visible_reason_cells(limit=8)
            reasons_preview = " | ".join(visible_reasons) if visible_reasons else "<未识别>"
            self._raise_timeout_with_context(
                "账户明细原因搜索后结果未收敛到：交易赔付",
                selector_keys=("account_details_reason_dropdown", "account_details_search_button"),
                extra_details=(f"可见结果原因：{reasons_preview}",),
            )
        amount = self._sum_outgoing_amount_on_account_details(
            report_date=report_date_str,
            reason_text="交易赔付",
        )
        self._log_step(f"账户明细交易赔付汇总（收支金额列）：{amount}")
        if amount <= 0:
            self._log_step("交易赔付查询无数据，按 0.00 处理")
            return 0.0
        return amount

    def _collect_cross_border_value_added_fee(
        self,
        report_date: date | datetime | str | None = None,
    ) -> float:
        """
        在“财务 -> 对账管理 -> 收支账单”中提取跨境服务增值费本月付款。
        """
        self._navigate_to_bill_summary_page()
        self._close_bill_update_mask_if_present()
        self._close_corner_popup_if_present()

        self._ensure_bill_summary_expense_day()

        report_date_str = self._format_report_date(report_date)
        self._set_bill_summary_single_day(report_date_str)
        self._log_step(f"收支账单已设置日期：{report_date_str} ~ {report_date_str}")
        self._click_blank_area()

        target_business = "淘宝天猫跨境服务增值费"
        selected_filter = self._set_bill_summary_business_category(target_business)
        self._log_step(f"收支账单已选择{selected_filter}：{target_business}")
        self._click_blank_area()
        if not self._is_bill_summary_business_selected(target_business, filter_label=selected_filter):
            self._raise_timeout_with_context(
                f"收支账单业务筛选未生效：{target_business}",
                selector_keys=("bill_summary_business_dropdown_control", "bill_summary_business_cross_border_option"),
            )

        previous_snapshot = self._snapshot_bill_summary_rows()
        self._click_search_button()
        self._log_step("收支账单已点击搜索")
        self._wait_bill_summary_results_settled(previous_snapshot=previous_snapshot)
        if not self._bill_summary_visible_rows_match_business(target_business):
            self._raise_timeout_with_context(
                f"收支账单搜索后结果未收敛到业务：{target_business}",
                selector_keys=("bill_summary_business_dropdown_control",),
                extra_details=(f"可见结果：{self._snapshot_bill_summary_rows() or '<未识别>'}",),
            )
        fee_total = self._extract_cross_border_monthly_payment(target_business)
        self._log_step(f"收支账单淘宝天猫跨境服务增值费本月付款：{fee_total}")
        return fee_total

    def collect_business_finance_metrics(
        self,
        download_dir: Optional[Path] = None,
        login_handler: Optional[Callable[[webdriver.Chrome], None]] = None,
        report_date: date | datetime | str | None = None,
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

        report_date_str = self._format_report_date(report_date)
        home_metrics = self._collect_home_dashboard_metrics(report_date=report_date_str)
        _ = self._switch_to_standard_version_if_needed()

        trade_compensation = self._collect_trade_compensation_amount(report_date=report_date_str)
        cross_border_fee = self._collect_cross_border_value_added_fee(report_date=report_date_str)
        promotion_fee = self._collect_promotion_fee(report_date=report_date_str)

        return {
            "report_date": report_date_str,
            "platform": "taobao",
            "shop_name": home_metrics.get("shop_name", ""),
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
                if self._try_switch_to_export_list_page():
                    self._log_step("已切换到导出列表页（新标签页）")
                    return True
            elif self._try_switch_to_export_list_page():
                self._log_step("已切换到导出列表页（现有标签页）")
                return True

            if self._is_export_list_page():
                self._log_step("已进入导出列表页")
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
                            self._log_step("已进入导出列表页（URL兜底直达）")
                            return True
                    except Exception:
                        continue

            time.sleep(self.ui_poll_interval_seconds)

        # 超时前最后一次兜底：再尝试切页与 URL 直达，减少误判。
        if self._try_switch_to_export_list_page():
            self._log_step("已切换到导出列表页（最终兜底）")
            return True
        for url in candidate_urls:
            try:
                driver.get(url)
                self._wait_dom_ready()
                if self._is_export_list_page():
                    self._log_step("已进入导出列表页（最终URL兜底）")
                    return True
            except Exception:
                continue

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
            # 指定了本次申请时间时，不允许回退下载历史按钮，必须等待对应记录生成完成。
            return None

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
        self._log_step("退款管理已点击：生成报表")

        time.sleep(max(self.interaction_delay_seconds * 2.0, 0.08))
        confirm_clicked = self._try_click_selector("confirm_button") or self._click_by_text(("确认",))
        if confirm_clicked:
            self._log_step("退款管理已点击：确认")

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
        self._switch_default_content()
        self._close_corner_popup_if_present()
        self._wait_left_nav_ready()

        clicked_trade = self._click_left_panel_text_with_wait(
            ("交易",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已点击左侧菜单：交易",
            min_left=0,
            max_left=130,
            min_top=120,
        )
        if not clicked_trade and self._try_click_selector("trade_menu"):
            clicked_trade = True
            self._log_step("已点击左侧菜单：交易（选择器兜底）")
        if not clicked_trade and self._click_by_text(("交易",)):
            clicked_trade = True
            self._log_step("已点击左侧菜单：交易（文本兜底）")
        if not clicked_trade:
            raise TimeoutException("未找到一级菜单【交易】。")

        time.sleep(max(self.interaction_delay_seconds * 2.2, 0.12))
        self._close_corner_popup_if_present()

        clicked_refund = self._click_left_panel_text_with_wait(
            ("退款管理",),
            timeout_seconds=max(self.timeout_seconds, 10),
            required=False,
            step_name="已进入菜单：退款管理",
            min_left=110,
            max_left=360,
            min_top=120,
        )
        if not clicked_refund and self._try_click_selector("refund_manage_menu"):
            clicked_refund = True
            self._log_step("已进入菜单：退款管理（选择器兜底）")
        if not clicked_refund and self._click_by_text(("退款管理",)):
            clicked_refund = True
            self._log_step("已进入菜单：退款管理（文本兜底）")
        if not clicked_refund:
            raise TimeoutException("未找到二级菜单【退款管理】。")

        self._wait_until(
            lambda: self._page_has_export_controls()
            or ("refund-list" in (self.get_current_url() or "").lower())
            or self._page_contains_text("售后单查询"),
            timeout_seconds=max(self.timeout_seconds, 15),
            message="点击【退款管理】后未进入售后查询页面。",
            selector_keys=("combined_query_button", "status_dropdown", "search_button"),
        )

    def _open_combined_query(self) -> None:
        """
        打开组合查询面板。
        """
        opened = self._try_click_selector("combined_query_button") or self._click_by_text(("组合查询", "高级筛选"))
        if not opened:
            raise TimeoutException("未找到【组合查询】下拉框。")

        self._wait_until(
            lambda: self._has_any_visible_element("status_dropdown") or self._page_contains_text("售后状态"),
            timeout_seconds=max(self.timeout_seconds, 8),
            message="点击【组合查询】后未出现售后状态筛选。",
            selector_keys=("combined_query_button", "status_dropdown"),
        )
        self._log_step("退款管理已展开：组合查询")

    def _open_status_dropdown_panel(self) -> bool:
        """
        打开“售后状态”下拉面板。
        """
        self._close_corner_popup_if_present()
        if self._try_click_selector("status_dropdown", timeout_seconds=2.2):
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

    def _status_aliases(self, status_text: str) -> tuple[str, ...]:
        """
        获取售后状态的兼容文案集合。
        """
        normalized = re.sub(r"\s+", " ", str(status_text or "")).strip()
        if not normalized:
            return tuple()

        aliases = [normalized]
        if normalized == "退款成功":
            aliases.append("退款完结")
        return tuple(dict.fromkeys(aliases))

    def _looks_like_selected_status_text(self, text: str, aliases: tuple[str, ...]) -> bool:
        """
        判断文本是否可视为“状态已选中”。
        """
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized or not aliases:
            return False

        if not any(alias in normalized for alias in aliases):
            return False

        selected_markers = ("已选择", "已选", "✓", "✔", "☑")
        if any(marker in normalized for marker in selected_markers):
            return True

        compact = (
            normalized.replace("▼", "")
            .replace("▽", "")
            .replace("▾", "")
            .replace("▿", "")
            .replace("⌄", "")
            .replace("⏷", "")
            .replace(":", " ")
        )
        compact = re.sub(r"\s+", " ", compact).strip()

        for alias in aliases:
            if compact == alias:
                return True
            if re.fullmatch(rf"{re.escape(alias)}\s*(?:\d+\s*项)?", compact):
                return True

        return False

    def _get_status_control_value(self) -> str:
        """
        读取“售后状态”控件当前值（用于日志诊断）。
        """
        driver = self._ensure_driver()
        values: list[str] = []

        for locator in self.selectors.get("status_dropdown", ()):
            elements = driver.find_elements(*locator)
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    for token in (
                        element.text or "",
                        element.get_attribute("value") or "",
                        element.get_attribute("innerText") or "",
                        element.get_attribute("title") or "",
                        element.get_attribute("aria-label") or "",
                    ):
                        cleaned = re.sub(r"\s+", " ", str(token)).strip()
                        if cleaned and cleaned not in values:
                            values.append(cleaned)
                except StaleElementReferenceException:
                    continue

        if not values:
            return "<未识别>"
        return " | ".join(values[:3])

    def _collect_visible_status_options(self, limit: int = 8) -> list[str]:
        """
        收集当前可见的售后状态候选项（用于日志诊断）。
        """
        driver = self._ensure_driver()
        aliases = ("退款成功", "退款完结", "进行中的订单", "退款关闭")
        options: list[str] = []

        candidates = driver.find_elements(
            By.XPATH,
            "//*[self::li or self::div or self::span or self::button]"
            "[contains(normalize-space(),'退款') or contains(normalize-space(),'进行中的订单')]",
        )
        for element in candidates:
            if len(options) >= max(limit, 1):
                break
            try:
                if not element.is_displayed():
                    continue
                text = re.sub(r"\s+", " ", (element.text or "")).strip()
                if not text:
                    continue
                if not any(alias in text for alias in aliases):
                    continue
                if len(text) > 60:
                    continue
                if text not in options:
                    options.append(text)
            except StaleElementReferenceException:
                    continue
        return options

    def _clear_selected_after_sale_status(self) -> None:
        """
        清空售后状态控件里已选标签（如“进行中的订单”），避免与目标状态叠加。
        """
        driver = self._ensure_driver()
        clear_xpaths = (
            "//*[@id='guide_search_form']/div/div[2]/div[2]/div/form/div[1]/div/span/span[1]"
            "//*[contains(@class,'close') or contains(@class,'remove') or "
            "normalize-space()='×' or normalize-space()='✕' or normalize-space()='x' or normalize-space()='X']",
            "//*[contains(@id,'guide_search_form')]//*[contains(normalize-space(),'已选择')]"
            "//*[contains(@class,'close') or contains(@class,'remove') or "
            "normalize-space()='×' or normalize-space()='✕' or normalize-space()='x' or normalize-space()='X']",
        )

        for _ in range(6):
            clicked = False
            for xpath in clear_xpaths:
                try:
                    nodes = driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue
                for node in nodes:
                    try:
                        if not node.is_displayed() or not node.is_enabled():
                            continue
                        self._click_with_retry(node)
                        clicked = True
                        time.sleep(max(self.ui_poll_interval_seconds, 0.1))
                        break
                    except Exception:
                        continue
                if clicked:
                    break
            if not clicked:
                return

    def _wait_status_selected(self, status_text: str, timeout_seconds: float = 2.2) -> bool:
        """
        轮询等待售后状态选中生效。
        """
        end_time = time.time() + max(float(timeout_seconds), 0.3)
        while time.time() < end_time:
            if self._is_status_selected(status_text):
                return True
            time.sleep(0.12)
        return self._is_status_selected(status_text)

    def _is_status_selected(self, status_text: str) -> bool:
        """
        判断售后状态是否已选中，避免重复点击导致反选。
        """
        driver = self._ensure_driver()
        aliases = self._status_aliases(status_text)
        if not aliases:
            return False

        for locator in self.selectors.get("status_dropdown", ()):
            elements = driver.find_elements(*locator)
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    for token in (
                        element.text or "",
                        element.get_attribute("value") or "",
                        element.get_attribute("innerText") or "",
                        element.get_attribute("title") or "",
                        element.get_attribute("aria-label") or "",
                    ):
                        if self._looks_like_selected_status_text(token, aliases):
                            return True
                except StaleElementReferenceException:
                    continue

        # 兜底：部分账号的“已选择”信息在独立节点显示
        try:
            for alias in aliases:
                marked = driver.find_elements(
                    By.XPATH,
                    f"//*[contains(normalize-space(),'已选择') and contains(normalize-space(),'{alias}')]",
                )
                if marked:
                    return True
        except Exception:
            pass

        # 兜底：部分控件为单选，value 文案直接是状态名（无“已选择”字样）
        try:
            inputs = driver.find_elements(
                By.XPATH,
                "//input[contains(@placeholder,'售后状态') or contains(@aria-label,'售后状态')]",
            )
            for input_element in inputs:
                try:
                    if not input_element.is_displayed():
                        continue
                    value_text = re.sub(
                        r"\s+",
                        " ",
                        (input_element.get_attribute("value") or ""),
                    ).strip()
                    if self._looks_like_selected_status_text(value_text, aliases):
                        return True
                except StaleElementReferenceException:
                    continue
        except Exception:
            pass

        # 兜底：下拉项自身带 selected/checked 状态
        try:
            for alias in aliases:
                selected_items = driver.find_elements(
                    By.XPATH,
                    "//*[contains(normalize-space(),'%s') and "
                    "(@aria-selected='true' or @aria-checked='true' "
                    "or contains(@class,'selected') or contains(@class,'checked'))]"
                    % alias,
                )
                for item in selected_items:
                    try:
                        if item.is_displayed():
                            return True
                    except StaleElementReferenceException:
                        continue
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

        # 先清空默认已选状态（例如“进行中的订单”），再选择目标状态。
        self._clear_selected_after_sale_status()
        self._open_status_dropdown_panel()

        # 第一轮：按预置定位尝试
        for selector_key in selector_keys:
            if self._try_click_selector(selector_key, timeout_seconds=2.2):
                if self._wait_status_selected(status_text, timeout_seconds=2.5):
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
                if self._wait_status_selected(status_text, timeout_seconds=1.8):
                    return

            moved = self._scroll_status_dropdown_panel(step=260)
            if not moved:
                # 可能面板被关闭，重新打开
                self._open_status_dropdown_panel()
            time.sleep(0.15)

        # 最后一轮：文本兜底
        if self._click_by_text((status_text,)):
            if self._wait_status_selected(status_text, timeout_seconds=2.5):
                return

        control_value = self._get_status_control_value()
        visible_options = self._collect_visible_status_options(limit=8)
        options_text = " | ".join(visible_options) if visible_options else "<未识别>"
        raise TimeoutException(
            f"无法选择售后状态：{status_text}。当前控件值：{control_value}。可见选项：{options_text}"
        )

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

        chromedriver_path = self._resolve_chromedriver_path()
        driver_errors: list[str] = []
        if chromedriver_path is not None:
            service = Service(executable_path=str(chromedriver_path))
        else:
            service = Service()

        try:
            self.driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            driver_errors.append(str(exc))
            if chromedriver_path is not None:
                try:
                    self._log_step("内置 chromedriver 启动失败，改用 Selenium Manager 自动匹配驱动。")
                    self.driver = webdriver.Chrome(service=Service(), options=options)
                except WebDriverException as fallback_exc:
                    driver_errors.append(str(fallback_exc))
                else:
                    self._is_attached_session = self.attach_to_existing_browser
                    self.wait = WebDriverWait(self.driver, self.timeout_seconds)
                    self._configure_download_behavior()
                    return
            if self.attach_to_existing_browser:
                host, port = self._split_debugger_address()
                details = "\n".join(item for item in driver_errors if item)
                raise RuntimeError(
                    "附着已打开浏览器失败。"
                    f"\n请确认 Chrome 已通过远程调试端口启动：{self.debugger_address}"
                    f"\n可在浏览器中打开并确认可访问：http://{host}:{port}/json/version"
                    "\nWindows 可检查是否已安装 Google Chrome，或重启程序点【重新打开工作浏览器】。"
                    f"\nDriver 细节：{details[:1200]}"
                ) from exc
            raise

        self._is_attached_session = self.attach_to_existing_browser
        self.wait = WebDriverWait(self.driver, self.timeout_seconds)
        self._configure_download_behavior()

    def _promotion_pause(self, scale: float = 1.0) -> None:
        """
        推广链路专用节奏控制，默认比常规操作更慢。
        """
        time.sleep(max(self.promotion_action_delay_seconds * max(scale, 0.2), 0.2))

    def _resolve_chromedriver_path(self) -> Optional[Path]:
        """
        解析可用的 chromedriver 路径，优先项目/打包资源，其次 Selenium 本地缓存。
        """
        candidates: list[Path] = []

        candidates.append(CHROMEDRIVER_PATH)
        executable_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"

        bundle_root = Path(getattr(sys, "_MEIPASS", "") or "")
        if bundle_root:
            candidates.append(bundle_root / "qianiu_auto_report" / "drivers" / executable_name)
            candidates.append(bundle_root / "drivers" / executable_name)

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / "qianiu_auto_report" / "drivers" / executable_name)
            candidates.append(exe_dir / "drivers" / executable_name)

        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file() and self._is_chromedriver_compatible(candidate):
                    return candidate
            except OSError:
                continue

        cache_roots = (
            Path.home() / ".cache" / "selenium" / "chromedriver",
            Path.home() / "Library" / "Caches" / "selenium" / "chromedriver",
        )
        cached_candidates: list[Path] = []
        for root in cache_roots:
            if not root.exists():
                continue
            cached_candidates.extend(path for path in root.glob("**/chromedriver*") if path.is_file())

        if not cached_candidates:
            return None

        compatible_candidates = [
            path for path in cached_candidates if self._is_chromedriver_compatible(path)
        ]
        if not compatible_candidates:
            self._log_step("本地缓存 chromedriver 与当前 Chrome 版本不匹配，改用 Selenium Manager 自动匹配驱动。")
            return None

        best = max(compatible_candidates, key=lambda item: item.stat().st_mtime)
        self._log_step(f"使用缓存 chromedriver：{best}")
        return best

    def _is_chromedriver_compatible(self, path: Path) -> bool:
        """
        附着调试浏览器时，跳过与当前 Chrome 主版本不一致的 chromedriver。
        """
        browser_version = self._debugger_browser_version
        if not self.attach_to_existing_browser or not browser_version:
            return True

        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            return True

        driver_version = f"{result.stdout or ''}\n{result.stderr or ''}"
        if driver_matches_browser_major(
            driver_version_text=driver_version,
            browser_version_text=browser_version,
        ):
            return True

        self._log_step(
            f"跳过版本不匹配的 chromedriver：{path}（{driver_version.strip() or '未识别版本'}；当前 {browser_version}）"
        )
        return False

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

        # 先按用户指定路径导航（交易 -> 退款管理）
        try:
            self._open_trade_refund_menu()
        except Exception:
            # 菜单路径失败时，回退到原先 URL 直达策略
            pass

        if self._wait_for_export_controls(timeout_seconds=8.0):
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
        设置导出条件，默认售后状态为“退款成功”。
        """
        statuses: list[str] = []
        if after_sale_statuses:
            statuses.extend(list(after_sale_statuses))
        if after_sale_status:
            statuses.append(after_sale_status)
        if not statuses:
            statuses = ["退款成功"]

        unique_statuses = list(dict.fromkeys(statuses))

        if use_combined_query:
            self._open_combined_query()

        for status in unique_statuses:
            self._select_after_sale_status(status)
            self._log_step(f"退款管理已选择售后状态：{status}")

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
        self._log_step("退款管理已点击：搜索售后单")

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
                file_filter=lambda file_path: (
                    file_path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}
                    and not file_path.name.startswith("~$")
                ),
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
