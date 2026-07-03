"""
已卖出宝贝订单导出流程。
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from qianiu_auto_report.config import DateConfig, ExportConfig
from qianiu_auto_report.utils import snapshot_directory
from qianiu_auto_report.web_export import WebExporter


class SoldOrderExporter(WebExporter):
    """
    天猫/淘宝【已卖出宝贝】宝贝销售明细报表导出器。
    """

    SOLD_ORDERS_URL = ExportConfig.SOLD_ORDERS_URL
    SOLD_ORDERS_EXPORT_LIST_URL = ExportConfig.SOLD_ORDERS_EXPORT_LIST_URL

    SOLD_ORDER_SELECTORS = {
        "sold_orders_menu": (
            (By.CSS_SELECTOR, "[data-testid='menu-sold-orders']"),
            (By.CSS_SELECTOR, "a[title='已卖出宝贝']"),
            (By.CSS_SELECTOR, "span[title='已卖出宝贝']"),
            (By.XPATH, "//*[self::a or self::div or self::span or self::li][normalize-space()='已卖出宝贝']"),
        ),
        "sold_order_search_button": (
            (By.CSS_SELECTOR, "button[data-testid='sold-order-search']"),
            (By.CSS_SELECTOR, "button[title='搜索订单']"),
            (By.XPATH, "//button[normalize-space()='搜索订单']"),
            (By.XPATH, "//*[self::button or self::a or self::span][contains(normalize-space(),'搜索订单')]"),
        ),
        "sold_order_batch_export_button": (
            (By.CSS_SELECTOR, "button[data-testid='sold-order-batch-export']"),
            (By.CSS_SELECTOR, "button[title='批量导出']"),
            (By.XPATH, "//button[normalize-space()='批量导出']"),
            (By.XPATH, "//*[self::button or self::a or self::span][contains(normalize-space(),'批量导出')]"),
        ),
        "sold_order_sales_detail_report_option": (
            (By.XPATH, "//*[self::label or self::div or self::span][contains(normalize-space(),'宝贝销售明细报表')]"),
        ),
        "sold_order_download_report_button": (
            (By.XPATH, "//button[normalize-space()='下载报表']"),
            (By.XPATH, "//button[normalize-space()='下载']"),
            (By.XPATH, "//*[self::button or self::a][contains(normalize-space(),'下载报表')]"),
            (By.XPATH, "//*[self::button or self::a][contains(normalize-space(),'下载')]"),
        ),
    }

    def __init__(self, **kwargs: object) -> None:
        selectors = dict(WebExporter.DEFAULT_SELECTORS)
        selectors.update(self.SOLD_ORDER_SELECTORS)
        kwargs.setdefault("export_url", ExportConfig.EXPORT_URL)
        kwargs.setdefault("expected_url_prefix", ExportConfig.EXPECTED_URL_PREFIX)
        kwargs.setdefault("selectors", selectors)
        super().__init__(**kwargs)

    @staticmethod
    def normalize_product_ids(product_ids: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """
        标准化商品 ID 输入，支持逗号、中文逗号、分号、空白和换行。
        """
        if isinstance(product_ids, (tuple, list)):
            raw_items = [str(item or "") for item in product_ids]
        else:
            raw_items = re.split(r"[,，;；\s]+", str(product_ids or ""))

        normalized: list[str] = []
        for item in raw_items:
            token = str(item or "").strip()
            if not token:
                continue
            if token not in normalized:
                normalized.append(token)
        return tuple(normalized)

    @staticmethod
    def _format_date(value: date | datetime | str) -> str:
        if isinstance(value, datetime):
            return value.date().strftime(DateConfig.DATE_FORMAT)
        if isinstance(value, date):
            return value.strftime(DateConfig.DATE_FORMAT)
        parsed = datetime.strptime(str(value).strip(), DateConfig.DATE_FORMAT)
        return parsed.strftime(DateConfig.DATE_FORMAT)

    def _format_payment_datetime_range(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> tuple[str, str]:
        start = self._format_date(start_date)
        end = self._format_date(end_date)
        return f"{start} 00:00:00", f"{end} 23:59:59"

    def _is_sold_orders_page(self) -> bool:
        current_url = self.get_current_url().lower()
        if "trade-platform/tp/sold" in current_url:
            return True
        return (
            self._page_contains_text("已卖出宝贝")
            and self._page_contains_text("搜索订单")
            and self._page_contains_text("批量导出")
        )

    def _ensure_sold_order_filters_expanded(self) -> None:
        """
        确保【已卖出宝贝】筛选项处于展开状态，便于设置付款时间和批量搜索。
        """
        if self._page_contains_text("付款时间") and self._page_contains_text("批量搜索"):
            return

        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const clickNode = (node) => {
                      node.scrollIntoView({ block: 'center', inline: 'center' });
                      node.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                      node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                      node.click();
                      return true;
                    };
                    const candidates = Array.from(document.querySelectorAll('button, a, span, div'))
                      .filter(visible)
                      .map((el) => {
                        const text = normalize(el.innerText || el.textContent || '');
                        if (text !== '展开筛选项') return null;
                        const rect = el.getBoundingClientRect();
                        return { node: el, rect, area: rect.width * rect.height };
                      })
                      .filter(Boolean);
                    candidates.sort((a, b) => a.area - b.area || a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    if (!candidates.length) return false;
                    return clickNode(candidates[0].node);
                    """
                )
            )
        except Exception:
            clicked = False

        if not clicked:
            clicked = self._click_by_text(("展开筛选项",))
        if not clicked:
            self._raise_timeout_with_context("未找到【展开筛选项】按钮，无法设置付款时间。")

        self._wait_until(
            lambda: self._page_contains_text("付款时间") and self._page_contains_text("批量搜索"),
            timeout_seconds=max(self.timeout_seconds, 8),
            message="筛选项展开后仍未找到【付款时间】和【批量搜索】。",
            selector_keys=("sold_order_search_button",),
        )
        self._log_step("已展开已卖出宝贝筛选项")

    def _is_export_list_page(self) -> bool:
        current_url = self.get_current_url().lower()
        if "trade-platform/tp/export-list" in current_url:
            return True

        stable_markers = (
            "订单导出报表",
            "报表申请时间",
            "报表类型",
            "宝贝销售明细报表",
            "报表生成中",
        )
        hit_count = sum(1 for marker in stable_markers if self._page_contains_text(marker))
        return hit_count >= 2

    def navigate_to_sold_orders_page(self) -> None:
        """
        进入【交易 -> 已卖出宝贝】，失败时直达 URL。
        """
        driver = self._ensure_driver()
        if self.attach_to_existing_browser:
            self.ensure_expected_page_or_switch()
        self._switch_default_content()
        self._close_corner_popup_if_present()

        if self._is_sold_orders_page():
            self._log_step("当前已在已卖出宝贝页面")
            return

        clicked_trade = self._click_left_panel_text_with_wait(
            ("交易",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已点击左侧菜单：交易",
            min_left=0,
            max_left=160,
            min_top=120,
        )
        if not clicked_trade and self._try_click_selector("trade_menu"):
            self._log_step("已点击左侧菜单：交易（选择器兜底）")
        time.sleep(max(self.interaction_delay_seconds * 2.0, 0.2))

        clicked_sold = self._click_left_panel_text_with_wait(
            ("已卖出宝贝",),
            timeout_seconds=max(self.timeout_seconds, 8),
            required=False,
            step_name="已进入菜单：已卖出宝贝",
            min_left=110,
            max_left=380,
            min_top=120,
        )
        if not clicked_sold and self._try_click_selector("sold_orders_menu"):
            self._log_step("已进入菜单：已卖出宝贝（选择器兜底）")

        try:
            self._wait_until(
                self._is_sold_orders_page,
                timeout_seconds=max(self.timeout_seconds, 12),
                message="点击菜单后仍未进入【已卖出宝贝】页面。",
                selector_keys=("trade_menu", "sold_orders_menu"),
            )
            return
        except TimeoutException:
            self._log_step("菜单未进入已卖出宝贝，尝试直达 URL")

        driver.get(self.SOLD_ORDERS_URL)
        self._wait_dom_ready()
        self._close_corner_popup_if_present()
        self._wait_until(
            self._is_sold_orders_page,
            timeout_seconds=max(self.timeout_seconds, 16),
            message="未进入【已卖出宝贝】页面。",
            selector_keys=("trade_menu", "sold_orders_menu", "sold_order_search_button"),
        )

    def _set_precise_query(self, product_ids: str | tuple[str, ...] | list[str]) -> None:
        ids = self.normalize_product_ids(product_ids)
        if not ids:
            raise ValueError("请至少输入一个商品 ID。")
        value = ",".join(ids)
        driver = self._ensure_driver()
        ok = bool(
            driver.execute_script(
                """
                const value = String(arguments[0] || '');
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 5 && rect.height >= 5
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 240;
                };
                const setValue = (input, nextValue = value) => {
                  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                  setter.call(input, nextValue);
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                  input.dispatchEvent(new Event('change', { bubbles: true }));
                  return true;
                };
                const labels = Array.from(document.querySelectorAll('label, div, span, p'))
                  .filter(visible)
                  .filter((el) => normalize(el.innerText || el.textContent || '') === '精确查询');
                const candidates = [];
                for (const label of labels) {
                  const lr = label.getBoundingClientRect();
                  const ly = lr.top + lr.height / 2;
                  for (const input of Array.from(document.querySelectorAll('input')).filter(visible)) {
                    const ir = input.getBoundingClientRect();
                    const iy = ir.top + ir.height / 2;
                    if (ir.width < 80 || ir.height < 18) continue;
                    if (Math.abs(iy - ly) > 28) continue;
                    if (ir.left < lr.right - 8) continue;
                    candidates.push({ input, score: Math.abs(iy - ly) * 10 + Math.max(0, ir.left - lr.right) });
                  }
                }
                if (!candidates.length) return false;
                candidates.sort((a, b) => a.score - b.score);
                const target = candidates[0].input;
                target.focus();
                const ok = setValue(target);

                // 清理旧版本误填到顶部全局搜索的同值，避免残留条件干扰观察。
                const tr = target.getBoundingClientRect();
                for (const input of Array.from(document.querySelectorAll('input')).filter(visible)) {
                  if (input === target) continue;
                  const ir = input.getBoundingClientRect();
                  if (ir.top < tr.top - 70 && String(input.value || '') === value) {
                    setValue(input, '');
                  }
                }
                return ok;
                """,
                value,
            )
        )
        if not ok:
            self._raise_timeout_with_context("未找到【精确查询】输入框。")
        self._log_step(f"已卖出宝贝已输入商品 ID：{value}")

    def _is_batch_search_dialog_open(self) -> bool:
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body'))
                      .filter(visible);
                    return roots.some((root) => {
                      const text = normalize(root.innerText || root.textContent || '');
                      return text.includes('批量搜索') && text.includes('商品id');
                    });
                    """
                )
            )
        except Exception:
            return False

    def _open_batch_search_dialog(self) -> bool:
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const clickNode = (node) => {
                      node.scrollIntoView({ block: 'center', inline: 'center' });
                      node.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                      node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                      node.click();
                      return true;
                    };
                    const candidates = Array.from(document.querySelectorAll('button, a, span, div'))
                      .filter(visible)
                      .map((el) => {
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!text.includes('批量搜索') || text.includes('批量导出')) return null;
                        const rect = el.getBoundingClientRect();
                        return {
                          node: el,
                          text,
                          rect,
                          exact: text === '批量搜索',
                          area: rect.width * rect.height,
                        };
                      })
                      .filter(Boolean);
                    candidates.sort((a, b) => {
                      if (a.exact !== b.exact) return a.exact ? -1 : 1;
                      return a.area - b.area || a.rect.top - b.rect.top || a.rect.left - b.rect.left;
                    });
                    if (!candidates.length) return false;
                    return clickNode(candidates[0].node);
                    """
                )
            )
        except Exception:
            clicked = False

        if clicked:
            try:
                self._wait_until(
                    self._is_batch_search_dialog_open,
                    timeout_seconds=max(self.timeout_seconds, 8),
                    message="点击【批量搜索】后未出现批量搜索弹窗。",
                    selector_keys=("sold_order_search_button",),
                )
            except TimeoutException:
                return False
        return clicked

    def _select_batch_search_product_id_radio(self) -> bool:
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const targetText = '商品id';
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, '').trim().toLowerCase();
                    const displayText = (node) => normalize(node.innerText || node.textContent || '');
                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body'))
                      .filter(visible)
                      .filter((root) => displayText(root).includes('批量搜索'));
                    const searchRoots = roots.length ? roots : [document.body];
                    const isSelected = (node) => {
                      const radio = node.querySelector('input[type="radio"]');
                      if (radio && radio.checked) return true;
                      if (node.getAttribute('aria-checked') === 'true') return true;
                      const classText = String(node.className || '').toLowerCase();
                      return /checked|selected|active/.test(classText);
                    };
                    const clickNode = (node) => {
                      node.scrollIntoView({ block: 'center', inline: 'center' });
                      node.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                      node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                      node.click();
                      return true;
                    };
                    const candidates = [];
                    for (const root of searchRoots) {
                      for (const node of Array.from(root.querySelectorAll('.next-radio-wrapper, label'))) {
                        if (!visible(node)) continue;
                        if (displayText(node) !== targetText) continue;
                        candidates.push(node);
                      }
                    }
                    if (!candidates.length) return false;
                    const target = candidates[0];
                    if (isSelected(target)) return true;
                    const radio = target.querySelector('input[type="radio"]');
                    if (radio) clickNode(radio);
                    if (!isSelected(target)) clickNode(target);
                    return true;
                    """
                )
            )
        except Exception:
            clicked = False
        if clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        return clicked

    def _set_batch_search_product_ids(self, value: str) -> bool:
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const value = String(arguments[0] || '');
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body'))
                      .filter(visible)
                      .filter((root) => normalize(root.innerText || root.textContent || '').includes('批量搜索'));
                    const searchRoots = roots.length ? roots : [document.body];
                    const fields = [];
                    for (const root of searchRoots) {
                      fields.push(...Array.from(root.querySelectorAll('textarea')).filter(visible));
                      fields.push(...Array.from(root.querySelectorAll('input')).filter(visible));
                    }
                    const target = fields
                      .filter((field) => {
                        const type = String(field.getAttribute('type') || '').toLowerCase();
                        return !['radio', 'checkbox', 'button', 'submit'].includes(type);
                      })
                      .sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (br.width * br.height) - (ar.width * ar.height);
                      })[0];
                    if (!target) return false;
                    target.focus();
                    const proto = target.tagName.toLowerCase() === 'textarea'
                      ? window.HTMLTextAreaElement.prototype
                      : window.HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                    setter.call(target, value);
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));
                    target.blur();
                    return String(target.value || '') === value;
                    """,
                    value,
                )
            )
        except Exception:
            return False

    def _confirm_batch_search_dialog(self) -> bool:
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body'))
                      .filter(visible)
                      .filter((root) => normalize(root.innerText || root.textContent || '').includes('批量搜索'));
                    const searchRoots = roots.length ? roots : [document.body];
                    const buttons = [];
                    for (const root of searchRoots) {
                      buttons.push(...Array.from(root.querySelectorAll('button')).filter(visible));
                    }
                    const target = buttons.find((button) => normalize(button.innerText || button.textContent || '') === '确定');
                    if (!target) return false;
                    const className = String(target.className || '').toLowerCase();
                    if (target.disabled || className.includes('disabled') || target.getAttribute('aria-disabled') === 'true') {
                      return false;
                    }
                    target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                    target.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                    target.click();
                    return true;
                    """
                )
            )
        except Exception:
            clicked = False
        if clicked:
            time.sleep(max(self.interaction_delay_seconds * 2.0, 0.3))
        return clicked

    def _set_batch_product_id_search(self, product_ids: str | tuple[str, ...] | list[str]) -> None:
        ids = self.normalize_product_ids(product_ids)
        if not ids:
            raise ValueError("请至少输入一个商品 ID。")
        value = ",".join(ids)

        if not self._open_batch_search_dialog():
            self._raise_timeout_with_context("未找到或未打开【批量搜索】弹窗。")
        if not self._select_batch_search_product_id_radio():
            self._raise_timeout_with_context("未能选择批量搜索类型【商品id】。")
        if not self._set_batch_search_product_ids(value):
            self._raise_timeout_with_context("未能在【批量搜索】弹窗中填写商品 ID。")
        if not self._confirm_batch_search_dialog():
            self._raise_timeout_with_context("未能确认【批量搜索】弹窗。")
        self._log_step(f"已卖出宝贝已按商品id批量搜索：{value}")

    def _payment_time_values(self) -> tuple[str, str]:
        """
        读取【付款时间】范围控件的两个实际 input value。
        """
        driver = self._ensure_driver()
        try:
            values = driver.execute_script(
                """
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 5 && rect.height >= 5
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                };
                const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                const pickers = Array.from(document.querySelectorAll('.next-range-picker'))
                  .filter(visible)
                  .map((picker) => ({
                    picker,
                    text: normalize(picker.innerText || picker.textContent || ''),
                    rect: picker.getBoundingClientRect(),
                  }))
                  .filter((item) => item.text.includes('付款时间'));
                pickers.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                for (const item of pickers) {
                  const inputs = Array.from(item.picker.querySelectorAll('input')).filter(visible);
                  if (inputs.length >= 2) {
                    return [String(inputs[0].value || ''), String(inputs[1].value || '')];
                  }
                }
                return [];
                """
            )
        except Exception:
            values = []

        if isinstance(values, list) and len(values) >= 2:
            return str(values[0] or ""), str(values[1] or "")
        return "", ""

    def _payment_time_selected(self, start_text: str, end_text: str) -> bool:
        start_value, end_value = self._payment_time_values()
        return start_value == start_text and end_value == end_text

    def _open_payment_time_range_picker(self) -> bool:
        """
        打开【付款时间】日期范围面板。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const pickers = Array.from(document.querySelectorAll('.next-range-picker'))
                      .filter(visible)
                      .map((picker) => ({
                        picker,
                        text: normalize(picker.innerText || picker.textContent || ''),
                        rect: picker.getBoundingClientRect(),
                      }))
                      .filter((item) => item.text.startsWith('付款时间'));
                    pickers.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    if (!pickers.length) return false;
                    const target = pickers[0].picker.querySelector('input') || pickers[0].picker;
                    target.scrollIntoView({ block: 'center', inline: 'center' });
                    target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                    target.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                    target.click();
                    return true;
                    """
                )
            )
            if not clicked:
                return False
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
            return self._is_payment_time_range_picker_open()
        except Exception:
            return False

    def _is_payment_time_range_picker_open(self) -> bool:
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const inputs = Array.from(document.querySelectorAll('.next-range-picker-body input'))
                      .filter(visible);
                    const buttons = Array.from(document.querySelectorAll('.next-range-picker-body button'))
                      .filter(visible)
                      .map((button) => String(button.innerText || button.textContent || '').trim());
                    return inputs.length >= 4 && buttons.includes('确定');
                    """
                )
            )
        except Exception:
            return False

    def _set_payment_time_panel_inputs(self, start_date_text: str, end_date_text: str) -> bool:
        driver = self._ensure_driver()
        try:
            values = driver.execute_script(
                """
                const nextValues = [
                  String(arguments[0] || ''),
                  '00:00:00',
                  String(arguments[1] || ''),
                  '23:59:59',
                ];
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 5 && rect.height >= 5;
                };
                const inputs = Array.from(document.querySelectorAll('.next-range-picker-body input'))
                  .filter(visible);
                if (inputs.length < 4) return [];
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                for (let i = 0; i < 4; i += 1) {
                  inputs[i].focus();
                  setter.call(inputs[i], nextValues[i]);
                  inputs[i].dispatchEvent(new Event('input', { bubbles: true }));
                  inputs[i].dispatchEvent(new Event('change', { bubbles: true }));
                  inputs[i].blur();
                }
                return inputs.slice(0, 4).map((input) => String(input.value || ''));
                """,
                start_date_text,
                end_date_text,
            )
        except Exception:
            values = []
        return values == [start_date_text, "00:00:00", end_date_text, "23:59:59"]

    def _confirm_payment_time_range_picker(self) -> bool:
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5;
                    };
                    const buttons = Array.from(document.querySelectorAll('.next-range-picker-body button'))
                      .filter(visible)
                      .filter((button) => String(button.innerText || button.textContent || '').trim() === '确定');
                    const button = buttons[buttons.length - 1];
                    if (!button) return false;
                    const className = String(button.className || '').toLowerCase();
                    if (button.disabled || className.includes('disabled') || button.getAttribute('aria-disabled') === 'true') {
                      return false;
                    }
                    button.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                    button.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                    button.click();
                    return true;
                    """
                )
            )
        except Exception:
            return False

    def _clear_misfilled_payment_values(self, start_text: str, end_text: str) -> None:
        """
        清理旧版本可能误填到【宝贝名称】等普通输入框的日期值。
        """
        driver = self._ensure_driver()
        try:
            driver.execute_script(
                """
                const badValues = new Set([String(arguments[0] || ''), String(arguments[1] || '')]);
                const visible = (el) => {
                  if (!el) return false;
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width >= 5 && rect.height >= 5
                    && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                };
                const paymentPicker = Array.from(document.querySelectorAll('.next-range-picker'))
                  .filter(visible)
                  .find((picker) => String(picker.innerText || picker.textContent || '').includes('付款时间'));
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                for (const input of Array.from(document.querySelectorAll('input')).filter(visible)) {
                  if (paymentPicker && paymentPicker.contains(input)) continue;
                  if (!badValues.has(String(input.value || ''))) continue;
                  setter.call(input, '');
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                  input.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                start_text,
                end_text,
            )
        except Exception:
            return

    def _set_payment_time_range(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> None:
        start_date_text = self._format_date(start_date)
        end_date_text = self._format_date(end_date)
        start_text, end_text = self._format_payment_datetime_range(start_date, end_date)
        if self._payment_time_selected(start_text, end_text):
            self._log_step(f"已卖出宝贝付款时间已是：{start_text} ~ {end_text}")
            return

        if not self._open_payment_time_range_picker():
            self._raise_timeout_with_context("未找到或未打开【付款时间】日期范围控件。")
        if not self._set_payment_time_panel_inputs(start_date_text, end_date_text):
            self._raise_timeout_with_context("未能写入【付款时间】日期面板。")
        if not self._confirm_payment_time_range_picker():
            self._raise_timeout_with_context("未能确认【付款时间】日期面板。")

        self._wait_until(
            lambda: self._payment_time_selected(start_text, end_text),
            timeout_seconds=max(self.timeout_seconds, 8),
            message=f"已卖出宝贝付款时间未生效：{start_text} ~ {end_text}",
            selector_keys=("sold_order_search_button",),
        )
        self._clear_misfilled_payment_values(start_text, end_text)
        self._log_step(f"已卖出宝贝已设置付款时间：{start_text} ~ {end_text}")

    def set_export_conditions(
        self,
        product_ids: str | tuple[str, ...] | list[str],
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> None:
        """
        设置商品 ID 与付款时间。
        """
        self._close_corner_popup_if_present()
        self._ensure_sold_order_filters_expanded()
        self._set_batch_product_id_search(product_ids)
        self._set_payment_time_range(start_date=start_date, end_date=end_date)

    def _try_switch_to_export_list_page(self, target_handles: Optional[set[str]] = None) -> bool:
        driver = self._ensure_driver()
        handles = list(target_handles if target_handles is not None else self._capture_window_handles())
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
        driver = self._ensure_driver()
        limit = timeout_seconds if timeout_seconds is not None else self.export_list_switch_timeout_seconds
        end_time = time.time() + max(float(limit), 5.0)
        clicked_view_button = False
        round_count = 0

        while time.time() < end_time:
            current_handles = self._capture_window_handles()
            new_handles = current_handles - previous_handles if current_handles else set()
            if new_handles:
                if self._try_switch_to_export_list_page(target_handles=new_handles):
                    self._log_step("已切换到订单导出报表页（新标签页）")
                    return True

            if self._is_export_list_page():
                self._log_step("已进入订单导出报表页")
                return True

            if not clicked_view_button:
                clicked_view_button = (
                    self._try_click_selector("view_generated_report_button")
                    or self._click_by_text(("查看已生成报表",))
                )

            round_count += 1
            if round_count % 6 == 0:
                try:
                    driver.get(self.SOLD_ORDERS_EXPORT_LIST_URL)
                    self._wait_dom_ready()
                    if self._is_export_list_page():
                        self._log_step("已进入订单导出报表页（URL兜底直达）")
                        return True
                except Exception:
                    pass
            time.sleep(self.ui_poll_interval_seconds)

        current_handles = self._capture_window_handles()
        new_handles = current_handles - previous_handles if current_handles else set()
        if new_handles and self._try_switch_to_export_list_page(target_handles=new_handles):
            return True
        try:
            driver.get(self.SOLD_ORDERS_EXPORT_LIST_URL)
            self._wait_dom_ready()
        except Exception:
            pass
        return self._is_export_list_page()

    def _iter_visible_download_buttons(self) -> list[WebElement]:
        driver = self._ensure_driver()
        buttons: list[WebElement] = []
        for locator in self.selectors.get("sold_order_download_report_button", ()):
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
            return None
        return buttons[0]

    def _wait_report_ready_and_click_download(
        self,
        request_time: str = "",
        timeout_seconds: Optional[int] = None,
        origin_handle: str = "",
    ) -> float:
        driver = self._ensure_driver()
        limit = timeout_seconds if timeout_seconds is not None else self.report_ready_timeout_seconds
        end_time = time.time() + max(int(limit), 60)
        round_count = 0

        while time.time() < end_time:
            if not self._is_export_list_page():
                time.sleep(self.ui_poll_interval_seconds)
                continue

            self._close_corner_popup_if_present()
            button = self._find_download_button(request_time=request_time)
            if button is not None:
                download_handle = ""
                try:
                    download_handle = driver.current_window_handle
                except Exception:
                    download_handle = ""
                self._click_with_retry(button)
                if origin_handle:
                    try:
                        if download_handle and download_handle != origin_handle:
                            driver.close()
                            driver.switch_to.window(origin_handle)
                        elif download_handle == origin_handle and self._is_export_list_page():
                            driver.get(self.SOLD_ORDERS_URL)
                            self._wait_dom_ready()
                        else:
                            driver.switch_to.window(origin_handle)
                    except Exception:
                        pass
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
            "等待订单报表生成超时：未找到可点击的【下载报表】按钮。"
            "请在订单导出报表页确认进度是否已完成。"
        )

    def _select_sales_detail_report_option(self) -> bool:
        """
        在【批量导出订单】弹窗中选择【宝贝销售明细报表】。
        """
        driver = self._ensure_driver()
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const targetText = '宝贝销售明细报表';
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const labelText = (node) => normalize(node.innerText || node.textContent || '');
                    const isSelected = (node) => {
                      if (!node || labelText(node) !== targetText) return false;
                      const radio = node.querySelector('input[type="radio"]');
                      if (radio && radio.checked) return true;
                      if (node.getAttribute('aria-checked') === 'true') return true;
                      const classText = String(node.className || '').toLowerCase();
                      return /checked|selected|active/.test(classText);
                    };
                    const clickNode = (node) => {
                      if (!node) return false;
                      node.scrollIntoView({ block: 'center', inline: 'center' });
                      node.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, view: window }));
                      node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, view: window, pointerId: 1, pointerType: 'mouse' }));
                      node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, view: window }));
                      node.click();
                      return true;
                    };

                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body, body'))
                      .filter(visible)
                      .filter((root) => {
                        const text = normalize(root.innerText || root.textContent || '');
                        return text.includes('批量导出订单') && text.includes('报表类型');
                      });
                    const searchRoots = roots.length ? roots : [document.body];
                    const exactLabels = [];
                    for (const root of searchRoots) {
                      for (const el of Array.from(root.querySelectorAll('.next-radio-wrapper, label'))) {
                        if (!visible(el)) continue;
                        if (labelText(el) !== targetText) continue;
                        const rect = el.getBoundingClientRect();
                        exactLabels.push({ node: el, rect, selected: isSelected(el) });
                      }
                    }
                    exactLabels.sort((a, b) => {
                      if (a.selected !== b.selected) return a.selected ? -1 : 1;
                      return a.rect.top - b.rect.top || a.rect.left - b.rect.left;
                    });
                    if (!exactLabels.length) return false;
                    const target = exactLabels[0].node;
                    if (isSelected(target)) return true;

                    const radio = target.querySelector('input[type="radio"]');
                    if (radio) clickNode(radio);
                    if (!isSelected(target)) clickNode(target);
                    return true;
                    """
                )
            )
        except Exception:
            clicked = False

        if not clicked:
            clicked = self._click_text_with_wait(("宝贝销售明细报表",), exact=False, timeout_seconds=5.0, required=False)
        if clicked:
            time.sleep(max(self.ui_poll_interval_seconds, 0.2))
        return clicked and self._is_sales_detail_report_option_selected()

    def _is_sales_detail_report_option_selected(self) -> bool:
        """
        判断【宝贝销售明细报表】radio/card 是否已选中。
        """
        driver = self._ensure_driver()
        try:
            return bool(
                driver.execute_script(
                    """
                    const targetText = '宝贝销售明细报表';
                    const visible = (el) => {
                      if (!el) return false;
                      const style = getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width >= 5 && rect.height >= 5
                        && rect.bottom >= 0 && rect.top <= window.innerHeight + 300;
                    };
                    const normalize = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                    const roots = Array.from(document.querySelectorAll('[role="dialog"], .next-dialog, .next-overlay-inner, .next-dialog-body, body'))
                      .filter(visible)
                      .filter((root) => {
                        const text = normalize(root.innerText || root.textContent || '');
                        return text.includes('批量导出订单') && text.includes('报表类型');
                      });
                    const searchRoots = roots.length ? roots : [document.body];
                    for (const root of searchRoots) {
                      for (const el of Array.from(root.querySelectorAll('.next-radio-wrapper, label'))) {
                        if (!visible(el)) continue;
                        if (normalize(el.innerText || el.textContent || '') !== targetText) continue;
                        const card = el;
                        const radio = card.querySelector('input[type="radio"]');
                        if (radio && radio.checked) return true;
                        if (card.getAttribute('aria-checked') === 'true') return true;
                        const classText = String(card.className || '').toLowerCase();
                        if (/checked|selected|active/.test(classText)) return true;
                      }
                    }
                    return false;
                    """
                )
            )
        except Exception:
            return False

    def submit_export_task(self) -> float:
        """
        搜索订单，提交宝贝销售明细报表导出，并最终触发下载。
        """
        driver = self._ensure_driver()
        origin_handle = ""
        try:
            origin_handle = driver.current_window_handle
        except Exception:
            origin_handle = ""
        previous_handles = self._capture_window_handles()
        self._close_corner_popup_if_present()

        search_ok = (
            self._try_click_selector("sold_order_search_button", timeout_seconds=5.0)
            or self._click_by_text(("搜索订单",))
        )
        if not search_ok:
            raise TimeoutException("未找到【搜索订单】按钮。")
        self._log_step("已卖出宝贝已点击：搜索订单")
        time.sleep(max(self.interaction_delay_seconds * 8.0, 1.0))

        export_ok = (
            self._try_click_selector("sold_order_batch_export_button", timeout_seconds=5.0)
            or self._click_by_text(("批量导出",))
        )
        if not export_ok:
            raise TimeoutException("未找到【批量导出】按钮。")
        self._log_step("已卖出宝贝已点击：批量导出")

        self._wait_until(
            lambda: self._page_contains_text("批量导出订单") or self._page_contains_text("报表类型"),
            timeout_seconds=max(self.timeout_seconds, 12),
            message="点击批量导出后未出现【批量导出订单】弹窗。",
            selector_keys=("sold_order_batch_export_button", "sold_order_sales_detail_report_option"),
        )

        if not self._select_sales_detail_report_option():
            raise TimeoutException("未选择报表类型【宝贝销售明细报表】。")
        self._log_step("已选择报表类型：宝贝销售明细报表")

        generate_ok = (
            self._try_click_selector("generate_report_button", timeout_seconds=5.0)
            or self._click_by_text(("生成报表",))
        )
        if not generate_ok:
            raise TimeoutException("未找到【生成报表】按钮。")
        self._log_step("已卖出宝贝已点击：生成报表")

        time.sleep(max(self.interaction_delay_seconds * 2.0, 0.2))
        confirm_ok = self._try_click_selector("confirm_button", timeout_seconds=3.0) or self._click_by_text(("确认",))
        if confirm_ok:
            self._log_step("已卖出宝贝注意事项已确认")

        if not self._wait_switch_to_export_list_page(previous_handles=previous_handles):
            raise TimeoutException("未进入订单导出报表页（trade-platform/tp/export-list）。")

        self._wait_dom_ready()
        self._close_corner_popup_if_present()
        request_time = self._capture_latest_request_time()
        return self._wait_report_ready_and_click_download(
            request_time=request_time,
            origin_handle=origin_handle,
        )

    def export_after_login(
        self,
        download_dir: Path,
        product_ids: str | tuple[str, ...] | list[str],
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> Path:
        """
        用户登录成功后导出宝贝销售明细报表。
        """
        target_dir = Path(download_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.validate_runtime_config()
        self._ensure_driver()
        self._ensure_wait()

        self.navigate_to_sold_orders_page()
        self.set_export_conditions(
            product_ids=product_ids,
            start_date=start_date,
            end_date=end_date,
        )

        snapshot = snapshot_directory(target_dir)
        trigger_ts = self.submit_export_task()
        return self.wait_for_download(
            download_dir=target_dir,
            trigger_ts=trigger_ts,
            snapshot=snapshot,
        )
