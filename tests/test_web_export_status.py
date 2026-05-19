"""
`web_export.py` 售后状态选择相关回归测试。
"""

from __future__ import annotations

import pytest

pytest.importorskip("selenium")

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from qianiu_auto_report.web_export import WebExporter


class _FakeElement:
    def __init__(
        self,
        text: str = "",
        *,
        displayed: bool = True,
        enabled: bool = True,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self._displayed = displayed
        self._enabled = enabled
        self._attrs = attrs or {}

    def is_displayed(self) -> bool:
        return self._displayed

    def is_enabled(self) -> bool:
        return self._enabled

    def get_attribute(self, name: str) -> str:
        return self._attrs.get(name, "")

    def find_elements(self, by: str, value: str) -> list["_FakeElement"]:
        return []


class _FakeDriver:
    def __init__(self, mapping: dict[tuple[str, str], list[_FakeElement]]) -> None:
        self.mapping = mapping

    def find_elements(self, by: str, value: str) -> list[_FakeElement]:
        return list(self.mapping.get((by, value), []))


class _ClickableElement(_FakeElement):
    def __init__(
        self,
        text: str = "",
        *,
        displayed: bool = True,
        enabled: bool = True,
        clicks: list[str] | None = None,
        name: str = "",
        on_click: object | None = None,
    ) -> None:
        super().__init__(text=text, displayed=displayed, enabled=enabled)
        self.clicks = clicks if clicks is not None else []
        self.name = name or text
        self.on_click = on_click

    def click(self) -> None:
        self.clicks.append(self.name)
        if callable(self.on_click):
            self.on_click()


class _AfterSaleShortcutDriver:
    def __init__(self, clicks: list[str]) -> None:
        self.clicks = clicks
        self.date_field = _ClickableElement("申请时间", clicks=clicks, name="date-field")
        self.hidden_date_option = _ClickableElement(
            "完结时间",
            displayed=False,
            clicks=clicks,
            name="hidden-end-time-option",
        )
        self.visible_date_option = _ClickableElement(
            "完结时间",
            clicks=clicks,
            name="end-time-option",
            on_click=lambda: setattr(self.date_field, "text", "完结时间"),
        )
        self.shortcut = _ClickableElement("请选择", clicks=clicks, name="date-shortcut")
        self.hidden_option = _ClickableElement(
            "昨日",
            displayed=False,
            clicks=clicks,
            name="hidden-yesterday-option",
        )
        self.visible_option = _ClickableElement("昨日", clicks=clicks, name="yesterday-option")

    def find_elements(self, by: str, value: str) -> list[_FakeElement]:
        if by != By.XPATH:
            return []
        if "compactWrapper" in value and "auxo-picker-range" in value:
            return [self.date_field]
        if "auxo-select-dropdown" in value and "完结时间" in value:
            return [self.hidden_date_option, self.visible_date_option]
        if "auxo-picker-range" in value and "following" in value:
            return [self.shortcut]
        if "auxo-select-dropdown" in value and "昨日" in value:
            return [self.hidden_option, self.visible_option]
        return []

    def execute_script(self, _script: str, *_args: object) -> None:
        return None


def test_status_selected_accepts_plain_selected_value_without_selected_keyword() -> None:
    """
    售后状态控件仅显示“退款成功”时，也应视为已选中。
    """
    exporter = WebExporter()
    exporter.selectors = {
        "status_dropdown": ((By.XPATH, "//status-control"),),
    }

    fake_driver = _FakeDriver(
        mapping={
            (By.XPATH, "//status-control"): [_FakeElement(text="退款成功")],
        }
    )

    exporter.driver = fake_driver  # type: ignore[assignment]

    assert exporter._is_status_selected("退款成功") is True


def test_export_list_page_detected_by_stable_markers_even_without_export_list_in_url() -> None:
    """
    当 URL 尚未包含 export-list，但页面已呈现导出列表关键文案时，也应识别为导出列表页。
    """
    exporter = WebExporter()
    exporter.driver = type("Driver", (), {"current_url": "https://myseller.taobao.com/home.htm/trade-platform/refund-list"})()  # type: ignore[assignment]

    marker_hits = {"报表申请时间", "进度："}
    exporter._page_contains_text = lambda text: text in marker_hits  # type: ignore[method-assign]

    assert exporter._is_export_list_page() is True


def test_collect_home_metrics_switches_speed_before_extracting() -> None:
    """
    首页指标提取前应先尝试切换极速版，避免在标准版读取到错误模块数据。
    """
    exporter = WebExporter()
    call_order: list[str] = []

    exporter._navigate_to_url = lambda url: call_order.append("navigate")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: call_order.append("close_popup") or False  # type: ignore[method-assign]
    exporter._switch_to_speed_version_if_needed = lambda: call_order.append("switch_speed") or True  # type: ignore[method-assign]
    exporter._set_home_period_last_1day = lambda: call_order.append("set_period_1day")  # type: ignore[method-assign]
    exporter._extract_home_shop_name = lambda: "vullvan瑜妍旗舰店"  # type: ignore[method-assign]

    def _fake_extract(label: str) -> float:
        call_order.append(f"extract:{label}")
        values = {"支付金额": 100.0, "支付买家数": 10.0, "支付子订单数": 12.0}
        return values[label]

    exporter._extract_home_metric = _fake_extract  # type: ignore[method-assign]

    result = exporter._collect_home_dashboard_metrics()

    assert result["payment_amount"] == 100.0
    assert result["payment_buyer_count"] == 10
    assert result["payment_sub_order_count"] == 12
    assert result["shop_name"] == "vullvan瑜妍旗舰店"
    assert "switch_speed" in call_order
    assert "set_period_1day" in call_order
    assert call_order.index("switch_speed") < call_order.index("extract:支付金额")
    assert call_order.index("set_period_1day") < call_order.index("extract:支付金额")


def test_set_home_period_last_1day_accepts_statistics_date_fallback() -> None:
    """
    若“近1天”选中态无法稳定识别，但统计时间已是目标日期，应视为成功。
    """
    exporter = WebExporter()
    logs: list[str] = []

    exporter._try_click_selector = lambda *args, **kwargs: True  # type: ignore[method-assign]
    exporter._click_text_with_wait = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._click_home_period_last_1day_by_js = lambda: False  # type: ignore[method-assign]
    exporter._is_home_period_last_1day_selected = lambda: False  # type: ignore[method-assign]
    exporter._is_home_statistics_date_target = lambda report_date: True  # type: ignore[method-assign]
    exporter._log_step = lambda message: logs.append(message)  # type: ignore[method-assign]
    exporter._raise_timeout_with_context = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not timeout"))  # type: ignore[method-assign]

    exporter._set_home_period_last_1day()

    assert any("统计时间" in item for item in logs)


def test_is_home_period_last_1day_selected_by_active_label() -> None:
    """
    若能识别当前激活周期标签，应直接按标签判断近1天是否选中。
    """
    exporter = WebExporter()
    exporter._get_home_period_active_label = lambda: "近1天"  # type: ignore[method-assign]
    assert exporter._is_home_period_last_1day_selected() is True

    exporter._get_home_period_active_label = lambda: "实时"  # type: ignore[method-assign]
    assert exporter._is_home_period_last_1day_selected() is False


def test_extract_home_shop_name_prefers_exact_xpath() -> None:
    """
    店铺名读取应优先命中精确 XPath。
    """
    exporter = WebExporter()
    exporter.selectors = {
        "home_shop_name": ((By.XPATH, "//shop-name"),),
    }
    exporter.driver = _FakeDriver(  # type: ignore[assignment]
        mapping={
            (By.XPATH, "//shop-name"): [_FakeElement(text="vullvan瑜妍旗舰店")],
        }
    )

    assert exporter._extract_home_shop_name() == "vullvan瑜妍旗舰店"


def test_extract_home_shop_name_cleans_combined_text_from_exact_xpath() -> None:
    """
    精确 XPath 返回粘连文本时，应只保留店铺名部分。
    """
    exporter = WebExporter()
    exporter.driver = _FakeDriver(  # type: ignore[assignment]
        mapping={
            (
                By.XPATH,
                "//*[@id='icestarkNode']/div/div/div[2]/div/div/div[1]/div/div/div[1]/div[2]/div[1]/div",
            ): [_FakeElement(text="好梦轻奢裙裤 店铺成长层级 Lv.5 保证金 已足额缴纳")],
        }
    )

    assert exporter._extract_home_shop_name() == "好梦轻奢裙裤"


def test_bill_summary_business_category_prefers_business_category_before_subcategory() -> None:
    """
    收支账单跨境服务费应优先选择“业务大类”，再兼容旧页面“业务小类”。
    """
    exporter = WebExporter()
    calls: list[tuple[str, str]] = []
    selected: dict[str, str] = {"label": ""}

    def _fake_is_selected(_business_name: str, filter_label: str | None = None) -> bool:
        calls.append(("is_selected", filter_label or ""))
        return bool(filter_label and selected["label"] == filter_label)

    def _fake_open(filter_label: str = "业务大类") -> bool:
        calls.append(("open", filter_label))
        selected["label"] = filter_label
        return True

    exporter._is_bill_summary_business_selected = _fake_is_selected  # type: ignore[method-assign]
    exporter._open_bill_summary_business_dropdown = _fake_open  # type: ignore[method-assign]
    exporter._click_bill_summary_business_option = lambda business_name: calls.append(("click", business_name)) or True  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: None  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: None  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(("log", message))  # type: ignore[method-assign]
    exporter.ui_poll_interval_seconds = 0.0

    selected_label = exporter._set_bill_summary_business_category("淘宝天猫跨境服务增值费")

    assert selected_label == "业务大类"
    assert ("open", "业务大类") in calls
    assert ("open", "业务小类") not in calls


def test_select_account_reason_trade_compensation_types_text_then_clicks_first_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    账户明细原因应先输入“交易赔付”过滤下拉，再点击过滤结果第一项完成选中。
    """
    exporter = WebExporter()
    current_reason = {"value": "请选择"}
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._open_account_reason_dropdown = lambda: True  # type: ignore[method-assign]
    exporter._scroll_account_reason_panel = lambda step=220: False  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: None  # type: ignore[method-assign]
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]
    exporter._list_visible_account_reason_options = lambda: ["交易赔付/违背承诺/违背发货承诺/延迟发货"]  # type: ignore[method-assign]
    exporter._find_status_option_element = lambda _status_text: None  # type: ignore[method-assign]
    exporter._get_account_reason_control_value = lambda: current_reason["value"]  # type: ignore[method-assign]
    exporter.ui_poll_interval_seconds = 0.0

    def _fake_type_reason(reason_text: str) -> bool:
        calls.append(("type", reason_text))
        return reason_text == "交易赔付"

    exporter._type_account_reason_text = _fake_type_reason  # type: ignore[attr-defined]
    exporter._click_first_account_reason_result = lambda reason_text: (  # type: ignore[attr-defined]
        calls.append(("first_result", reason_text)) or current_reason.__setitem__("value", "交易赔付") or True
    )
    exporter._click_account_reason_option = lambda reason_text: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError(f"不应再使用旧的下拉文本兜底：{reason_text}")
    )

    assert exporter._select_account_reason_trade_compensation() is True
    assert calls == [("type", "交易赔付"), ("first_result", "交易赔付")]


def test_click_first_account_reason_result_prefers_visible_selectable_label() -> None:
    """
    输入交易赔付后，应优先点击当前可见的可选 label，避免固定 li 序号漂移点到隐藏项。
    """
    exporter = WebExporter()
    calls: list[tuple[str, str]] = []

    class _ReasonOption(_FakeElement):
        def __init__(self) -> None:
            super().__init__(text="交易赔付/违背承诺/违背发货承诺/延迟发货")

    class _Driver:
        def execute_script(self, *_args, **_kwargs) -> bool:
            calls.append(("script", "visible_label"))
            return True

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            calls.append(("find", value))
            if (
                by == By.XPATH
                and "next-tree-node-label-selectable" in value
                and "normalize-space()='交易赔付'" in value
            ):
                return [_ReasonOption()]
            return []

    exporter.driver = _Driver()  # type: ignore[assignment]
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._click_with_retry = lambda element: calls.append(("click", element.text))  # type: ignore[method-assign]
    exporter.ui_poll_interval_seconds = 0.0

    assert exporter._click_first_account_reason_result("交易赔付") is True
    assert "next-tree-node-label-selectable" in calls[0][1]
    assert ("script", "visible_label") in calls
    assert ("click", "交易赔付/违背承诺/违背发货承诺/延迟发货") not in calls


def test_collect_cross_border_value_added_fee_reads_target_business_row_not_page_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    收支账单跨境服务费应优先读取目标业务行，避免误用整页扣费合计。
    """
    exporter = WebExporter()
    calls: list[str] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._navigate_to_bill_summary_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter._close_bill_update_mask_if_present = lambda: calls.append("close_mask")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._ensure_bill_summary_expense_day = lambda: calls.append("ensure_expense_day")  # type: ignore[method-assign]
    exporter._set_bill_summary_single_day = lambda report_date: calls.append(f"set_date:{report_date}")  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: calls.append("blank")  # type: ignore[method-assign]
    exporter._set_bill_summary_business_category = lambda business_name: "业务大类"  # type: ignore[method-assign]
    exporter._is_bill_summary_business_selected = lambda business_name, filter_label=None: True  # type: ignore[method-assign]
    exporter._click_search_button = lambda: calls.append("search")  # type: ignore[method-assign]
    exporter._extract_cross_border_monthly_payment = lambda business_name: 82.3  # type: ignore[method-assign]
    exporter._extract_bill_summary_fee_total = lambda: 999.0  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(f"log:{message}")  # type: ignore[method-assign]
    exporter.interaction_delay_seconds = 0.0

    result = exporter._collect_cross_border_value_added_fee()

    assert result == 82.3
    assert "search" in calls
    assert any("淘宝天猫跨境服务增值费本月付款：82.3" in item for item in calls)
    assert not any("扣费金额合计" in item for item in calls)


def test_collect_cross_border_value_added_fee_raises_before_search_when_business_not_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    收支账单业务大类未真正选中时，不应点击搜索。
    """
    exporter = WebExporter()
    calls: list[str] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._navigate_to_bill_summary_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter._close_bill_update_mask_if_present = lambda: calls.append("close_mask")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._ensure_bill_summary_expense_day = lambda: calls.append("ensure_expense_day")  # type: ignore[method-assign]
    exporter._set_bill_summary_single_day = lambda report_date: calls.append(f"set_date:{report_date}")  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: calls.append("blank")  # type: ignore[method-assign]
    exporter._set_bill_summary_business_category = lambda business_name: "业务大类"  # type: ignore[method-assign]
    exporter._is_bill_summary_business_selected = lambda business_name, filter_label=None: False  # type: ignore[method-assign]
    exporter._click_search_button = lambda: calls.append("search")  # type: ignore[method-assign]
    exporter._extract_cross_border_monthly_payment = lambda business_name: 82.3  # type: ignore[method-assign]
    exporter._extract_bill_summary_fee_total = lambda: 999.0  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(f"log:{message}")  # type: ignore[method-assign]
    exporter.get_current_url = lambda: "https://myseller.taobao.com/home.htm/whale-accountant/bill/summary"  # type: ignore[method-assign]
    exporter._page_text_snippet = lambda max_length=180: "收支账单 页面片段"  # type: ignore[method-assign]
    exporter.driver = _FakeDriver(mapping={})  # type: ignore[assignment]
    exporter.interaction_delay_seconds = 0.0

    with pytest.raises(TimeoutException, match="淘宝天猫跨境服务增值费"):
        exporter._collect_cross_border_value_added_fee()

    assert "search" not in calls


def test_sum_outgoing_amount_on_account_details_filters_by_date_and_reason() -> None:
    """
    账户明细汇总应仅统计目标日期且原因匹配“交易赔付”的行。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]

    class _FakeRow:
        def __init__(self, row_text: str, amount_text: str) -> None:
            self.text = row_text
            self._amount_cell = _FakeElement(text=amount_text)

        def is_displayed(self) -> bool:
            return True

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "./td[4]":
                return [self._amount_cell]
            return []

    rows = [
        _FakeRow("A001 2026-05-14 交易赔付 9.03", "9.03"),
        _FakeRow("A002 2026-05-14 交易售后 88.00", "88.00"),
        _FakeRow("A003 2026-05-13 交易赔付 5.00", "5.00"),
        _FakeRow("A004 2026-05-14 交易赔付/违背承诺/违背发货承诺/延迟发货 4.20", "4.20"),
    ]
    exporter.driver = _FakeDriver(  # type: ignore[assignment]
        mapping={
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            ): rows,
        }
    )

    total = exporter._sum_outgoing_amount_on_account_details(
        report_date="2026-05-14",
        reason_text="交易赔付",
    )

    assert total == 13.23


def test_sum_outgoing_amount_on_account_details_deduplicates_fixed_table_duplicate_rows() -> None:
    """
    账户明细表格存在冻结列/重复 DOM 时，同一视觉行不应被重复累计。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]

    class _FakeRow:
        def __init__(self, row_text: str, amount_text: str, y: float) -> None:
            self.text = row_text
            self.rect = {"x": 100, "y": y, "width": 800, "height": 32}
            self._amount_cell = _FakeElement(text=amount_text)

        def is_displayed(self) -> bool:
            return True

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "./td[4]":
                return [self._amount_cell]
            return []

    rows = [
        _FakeRow("2026-05-14 交易赔付/违背承诺/违背发货承诺/延迟发货 A001", "5.95", 220),
        _FakeRow("2026-05-14 交易赔付/违背承诺/违背发货承诺/延迟发货 A001 冻结列副本", "5.95", 220),
        _FakeRow("2026-05-14 交易赔付/违背承诺/违背发货承诺/延迟发货 A002", "5.45", 252),
        _FakeRow("2026-05-14 交易赔付/违背承诺/违背发货承诺/延迟发货 A002 冻结列副本", "5.45", 252),
    ]
    exporter.driver = _FakeDriver(  # type: ignore[assignment]
        mapping={
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            ): rows,
        }
    )

    total = exporter._sum_outgoing_amount_on_account_details(
        report_date="2026-05-14",
        reason_text="交易赔付",
    )

    assert total == 11.4


def test_sum_outgoing_amount_on_account_details_uses_reason_cell_not_business_description() -> None:
    """
    账户明细汇总应以“原因”列为准，不能因业务描述含赔付词而把充值/划扣行算进去。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]

    class _FakeRow:
        def __init__(
            self,
            date_text: str,
            reason_text: str,
            operation_text: str,
            amount_text: str,
            business_text: str,
        ) -> None:
            self.text = f"{date_text} {reason_text} {operation_text} {amount_text} {business_text}"
            self.rect = {"x": 100, "y": 220, "width": 900, "height": 32}
            self._cells = [
                _FakeElement(text=date_text),
                _FakeElement(text=reason_text),
                _FakeElement(text=operation_text),
                _FakeElement(text=amount_text),
                _FakeElement(text=business_text),
            ]

        def is_displayed(self) -> bool:
            return True

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "./td":
                return self._cells
            if by == By.XPATH and value == "./td[4]":
                return [self._cells[3]]
            return []

    rows = [
        _FakeRow(
            "2026-05-15 12:00:00",
            "充值/系统划扣充值",
            "出账",
            "634.57",
            "充值（代扣）-物流轨迹异常",
        ),
        _FakeRow(
            "2026-05-15 13:00:00",
            "交易赔付/违背承诺/违背发货承诺/延迟发货",
            "出账",
            "9.03",
            "赔付单",
        ),
        _FakeRow(
            "2026-05-15 14:00:00",
            "交易赔付/违背承诺/违背发货承诺/延迟发货",
            "入账",
            "2.00",
            "退款",
        ),
    ]
    exporter.driver = _FakeDriver(  # type: ignore[assignment]
        mapping={
            (
                By.XPATH,
                "//*[@id='app']/div[1]/div/div/div/div/div/div[2]/div[2]/div/div/div[3]/div[1]/div[2]/div[2]/table/tbody/tr",
            ): rows,
        }
    )

    total = exporter._sum_outgoing_amount_on_account_details(
        report_date="2026-05-15",
        reason_text="交易赔付",
    )

    assert total == 9.03


def test_get_account_reason_control_value_rejects_whole_filter_bar_text() -> None:
    """
    账户明细原因控件不能把整段筛选栏文本误当作当前选中值。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter.selectors = {
        "account_details_reason_dropdown": ((By.XPATH, "//reason-control"),),
    }

    class _Driver:
        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "//reason-control":
                return [
                    _FakeElement(
                        text="- 昨天 今天 7日 30日 本月 本年 资金类型 余额资金 原因 订单编号 业务编号 搜索重置"
                    )
                ]
            return []

        def execute_script(self, *_args, **_kwargs) -> str:
            return ""

    exporter.driver = _Driver()  # type: ignore[assignment]

    assert exporter._get_account_reason_control_value() == ""


def test_get_account_reason_control_value_reads_typed_reason_input() -> None:
    """
    账户明细原因输入框已填“交易赔付”时，应直接视为当前筛选值。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter.selectors = {
        "account_details_reason_dropdown": ((By.XPATH, "//reason-control"),),
    }

    class _ReasonControl(_FakeElement):
        def __init__(self) -> None:
            super().__init__(text="原因")
            self._input = _FakeElement(text="", attrs={"value": "交易赔付"})

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == ".//input":
                return [self._input]
            return []

    class _Driver:
        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "//reason-control":
                return [_ReasonControl()]
            return []

        def execute_script(self, *_args, **_kwargs) -> str:
            return ""

    exporter.driver = _Driver()  # type: ignore[assignment]

    assert exporter._get_account_reason_control_value() == "交易赔付"
    assert exporter._is_account_reason_selected("交易赔付") is True


def test_get_account_reason_control_value_ignores_date_from_broad_fallback() -> None:
    """
    账户明细原因控件不能把日期输入框的值误读成原因值。
    """
    exporter = WebExporter()
    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter.selectors = {
        "account_details_reason_dropdown": ((By.XPATH, "//missing-reason-control"),),
    }

    class _Driver:
        def find_elements(self, _by: str, _value: str) -> list[_FakeElement]:
            return []

        def execute_script(self, *_args, **_kwargs) -> str:
            return "2026-05-15"

    exporter.driver = _Driver()  # type: ignore[assignment]

    assert exporter._get_account_reason_control_value() == ""


def test_select_account_reason_trade_compensation_accepts_staged_input_before_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    直接输入“交易赔付”后即使控件展示值暂未稳定，也应允许后续点击搜索提交。
    """
    exporter = WebExporter()
    input_reason = {"value": "请选择"}
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._ensure_account_details_context = lambda: True  # type: ignore[method-assign]
    exporter._get_account_reason_control_value = lambda: ""  # type: ignore[method-assign]
    exporter._get_account_reason_input_value = lambda: input_reason["value"]  # type: ignore[attr-defined]
    exporter._open_account_reason_dropdown = lambda: True  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: None  # type: ignore[method-assign]
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]
    exporter._list_visible_account_reason_options = lambda: ["交易赔付"]  # type: ignore[method-assign]
    exporter.ui_poll_interval_seconds = 0.0

    def _fake_type_reason(reason_text: str) -> bool:
        calls.append(("type", reason_text))
        input_reason["value"] = reason_text
        return True

    exporter._type_account_reason_text = _fake_type_reason  # type: ignore[attr-defined]
    exporter._click_first_account_reason_result = lambda reason_text: calls.append(("first_result", reason_text)) or False  # type: ignore[attr-defined]

    assert exporter._select_account_reason_trade_compensation() is True
    assert calls == [("type", "交易赔付"), ("first_result", "交易赔付")]


def test_extract_cross_border_monthly_payment_does_not_use_unscoped_page_total() -> None:
    """
    未读到目标业务行时，不应把整页“扣费金额合计”当成跨境服务费。
    """
    exporter = WebExporter()
    exporter._log_step = lambda _message: None  # type: ignore[method-assign]
    exporter._page_contains_text = lambda _text: False  # type: ignore[method-assign]

    class _Driver:
        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if "淘宝天猫跨境服务增值费" in value:
                return []
            if "扣费金额合计" in value:
                return [_FakeElement(text="扣费金额合计：¥ 1584.68")]
            return []

        def execute_script(self, *_args, **_kwargs) -> list[str]:
            return []

    exporter.driver = _Driver()  # type: ignore[assignment]

    assert exporter._extract_cross_border_monthly_payment("淘宝天猫跨境服务增值费") == 0.0


def test_collect_cross_border_value_added_fee_does_not_fallback_to_page_total_after_empty_target_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    目标业务行没有稳定读到时，即使页面总额有值，也不能回退成跨境服务费。
    """
    exporter = WebExporter()
    calls: list[str] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._navigate_to_bill_summary_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter._close_bill_update_mask_if_present = lambda: calls.append("close_mask")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._ensure_bill_summary_expense_day = lambda: calls.append("ensure_expense_day")  # type: ignore[method-assign]
    exporter._set_bill_summary_single_day = lambda report_date: calls.append(f"set_date:{report_date}")  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: calls.append("blank")  # type: ignore[method-assign]
    exporter._set_bill_summary_business_category = lambda business_name: "业务大类"  # type: ignore[method-assign]
    exporter._is_bill_summary_business_selected = lambda business_name, filter_label=None: True  # type: ignore[method-assign]
    exporter._click_search_button = lambda: calls.append("search")  # type: ignore[method-assign]
    exporter._extract_cross_border_monthly_payment = lambda business_name: 0.0  # type: ignore[method-assign]
    exporter._extract_bill_summary_fee_total = lambda: 1584.68  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(f"log:{message}")  # type: ignore[method-assign]
    exporter.interaction_delay_seconds = 0.0

    result = exporter._collect_cross_border_value_added_fee()

    assert result == 0.0
    assert not any("1584.68" in item for item in calls)
    assert any("淘宝天猫跨境服务增值费本月付款：0.0" in item for item in calls)
    assert not any("扣费金额合计" in item for item in calls)


def test_collect_trade_compensation_amount_raises_before_search_when_reason_not_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    账户明细原因未真正选中时，不应点击搜索。
    """
    exporter = WebExporter()
    calls: list[str] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)

    exporter._navigate_to_account_details_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._wait_account_details_filters_ready = lambda: calls.append("wait_ready")  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(f"log:{message}")  # type: ignore[method-assign]
    exporter._select_account_details_yesterday = lambda: calls.append("select_yesterday")  # type: ignore[method-assign]
    exporter._select_account_reason_trade_compensation = lambda: False  # type: ignore[method-assign]
    exporter._click_blank_area = lambda: calls.append("blank")  # type: ignore[method-assign]
    exporter._log_account_details_filter_state = lambda: calls.append("log_filter_state")  # type: ignore[method-assign]
    exporter._snapshot_account_details_rows = lambda: "before rows"  # type: ignore[attr-defined]
    exporter._click_account_details_search_button = lambda: calls.append("search")  # type: ignore[method-assign]
    exporter._sum_outgoing_amount_on_account_details = lambda report_date=None, reason_text=None: 99.0  # type: ignore[method-assign]
    exporter.get_current_url = lambda: "https://myseller.taobao.com/home.htm/whale-accountant/bill/account-details"  # type: ignore[method-assign]
    exporter._page_text_snippet = lambda max_length=180: "账户明细 页面片段"  # type: ignore[method-assign]
    exporter.driver = _FakeDriver(mapping={})  # type: ignore[assignment]
    exporter.interaction_delay_seconds = 0.0

    with pytest.raises(TimeoutException, match="交易赔付"):
        exporter._collect_trade_compensation_amount()

    assert "search" not in calls


def test_collect_trade_compensation_amount_clicks_search_when_reason_text_is_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    原因输入框已填“交易赔付”时，应点击搜索让页面提交筛选，而不是在搜索前中断。
    """
    exporter = WebExporter()
    calls: list[str] = []

    monkeypatch.setattr("qianiu_auto_report.web_export.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "qianiu_auto_report.web_export.DateConfig.default_report_date_str",
        lambda: "2026-05-15",
    )

    exporter._navigate_to_account_details_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._wait_account_details_filters_ready = lambda: calls.append("wait_ready")  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(f"log:{message}")  # type: ignore[method-assign]
    exporter._select_account_details_yesterday = lambda: calls.append("select_yesterday")  # type: ignore[method-assign]
    exporter._select_account_reason_trade_compensation = lambda: True  # type: ignore[method-assign]
    exporter._is_account_reason_selected = lambda _reason: False  # type: ignore[method-assign]
    exporter._get_account_reason_input_value = lambda: "交易赔付"  # type: ignore[attr-defined]
    exporter._click_blank_area = lambda: calls.append("blank")  # type: ignore[method-assign]
    exporter._log_account_details_filter_state = lambda: calls.append("log_filter_state")  # type: ignore[method-assign]
    exporter._click_account_details_search_button = lambda: calls.append("search")  # type: ignore[method-assign]
    exporter._wait_account_details_results_settled = lambda previous_snapshot=None: calls.append("wait_results")  # type: ignore[attr-defined]
    exporter._account_details_visible_rows_match_reason = lambda reason_text: True  # type: ignore[attr-defined]
    exporter._sum_outgoing_amount_on_account_details = lambda report_date=None, reason_text=None: 9.03  # type: ignore[method-assign]
    exporter.interaction_delay_seconds = 0.0

    assert exporter._collect_trade_compensation_amount() == 9.03
    assert "search" in calls
    assert "wait_results" in calls


def test_is_account_reason_selected_rejects_placeholder_mixed_text() -> None:
    """
    账户明细原因值里混着多个下拉选项时，不应算作真正选中。
    """
    exporter = WebExporter()
    exporter._get_account_reason_control_value = lambda: "交易赔付 | 交易售后 | 违约金罚扣"  # type: ignore[method-assign]

    assert exporter._is_account_reason_selected("交易赔付") is False


def test_is_bill_summary_business_selected_rejects_placeholder_mixed_text() -> None:
    """
    收支账单业务大类值里只要还混着“请选择”，就不应算作真正选中。
    """
    exporter = WebExporter()
    exporter.selectors = {
        "bill_summary_business_dropdown_control": ((By.XPATH, "//business-control"),),
    }

    class _Driver:
        def execute_script(self, *_args, **_kwargs) -> bool:
            return True

        def find_elements(self, by: str, value: str) -> list[_FakeElement]:
            if by == By.XPATH and value == "//business-control":
                return [_FakeElement(text="请选择 | 淘宝天猫跨境服务增值费")]
            return []

    exporter.driver = _Driver()  # type: ignore[assignment]

    assert exporter._is_bill_summary_business_selected("淘宝天猫跨境服务增值费") is False


def test_is_wanxiangtai_url_excludes_myseller_and_accepts_alimama() -> None:
    """
    万相台 URL 判定应排除卖家后台域名，避免误判已切换。
    """
    assert WebExporter._is_wanxiangtai_url(
        "https://myseller.taobao.com/home.htm/trade-platform/refund-list"
    ) is False
    assert WebExporter._is_wanxiangtai_url(
        "https://one.alimama.com/index.html#!/report/crowd"
    ) is True
    assert WebExporter._is_wanxiangtai_url(
        "https://example.com/report/crowd"
    ) is False


def test_is_wanxiangtai_ready_context_rejects_blank_alimama_shell() -> None:
    """
    one.alimama.com 的空白中转壳页不应被视为万相台已就绪页面。
    """
    exporter = WebExporter()
    exporter.get_current_url = lambda: "https://one.alimama.com/index.html?strategyPoints=cg%7CadossChannelTrace"  # type: ignore[method-assign]
    exporter._page_text_snippet = lambda max_length=180: "<空白页面>"  # type: ignore[method-assign]
    exporter._is_wanxiangtai_page_by_content = lambda: False  # type: ignore[method-assign]
    exporter._is_promotion_unavailable_page = lambda: False  # type: ignore[method-assign]
    exporter._page_contains_text = lambda text: False  # type: ignore[method-assign]

    assert exporter._is_wanxiangtai_ready_context() is False


def test_open_promotion_report_page_directs_to_crowd_report_when_alimama_shell_is_blank() -> None:
    """
    进入 one.alimama.com 空白壳页后，若找不到【报表】，应直达稳定的人群报表 URL。
    """
    exporter = WebExporter()
    calls: list[tuple[str, str]] = []
    state = {
        "url": "https://one.alimama.com/index.html?strategyPoints=cg%7CadossChannelTrace",
        "directed": False,
    }

    exporter.get_current_url = lambda: state["url"]  # type: ignore[method-assign]
    exporter._close_promotion_mask_by_blank_click = lambda: None  # type: ignore[method-assign]
    exporter._promotion_pause = lambda scale=1.0: None  # type: ignore[method-assign]
    exporter._try_click_selector = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._click_text_with_wait = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._is_promotion_unavailable_page = lambda: False  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(("log", message))  # type: ignore[method-assign]

    def _fake_page_contains_text(text: str) -> bool:
        return bool(state["directed"] and text in {"数据汇总", "花费"})

    def _fake_navigate(url: str) -> None:
        calls.append(("navigate", url))
        state["url"] = url
        state["directed"] = True

    def _fake_wait_until(condition, **_kwargs):
        assert condition() is True

    exporter._page_contains_text = _fake_page_contains_text  # type: ignore[method-assign]
    exporter._navigate_to_url = _fake_navigate  # type: ignore[method-assign]
    exporter._wait_until = _fake_wait_until  # type: ignore[method-assign]

    exporter._open_promotion_report_page()

    assert ("navigate", WebExporter.PROMOTION_CROWD_REPORT_URL) in calls


def test_is_wanxiangtai_page_by_content_requires_non_myseller_url() -> None:
    """
    即便文本包含万相台/报表关键字，若仍在 myseller 域名也不能判定切换成功。
    """
    exporter = WebExporter()
    exporter.get_current_url = lambda: "https://myseller.taobao.com/home.htm/trade-platform/refund-list"  # type: ignore[method-assign]
    exporter._page_contains_text = lambda text: True  # type: ignore[method-assign]
    assert exporter._is_wanxiangtai_page_by_content() is False


def test_get_wanxiangtai_entry_href_uses_selector_fallback() -> None:
    """
    当固定 XPath 未命中时，也应能从通用入口选择器中提取 href 兜底直达。
    """
    exporter = WebExporter()
    exporter.selectors = {
        "wanxiangtai_ai_entry": ((By.XPATH, "//fallback-entry"),),
    }
    exporter.driver = _FakeDriver(
        mapping={
            (By.XPATH, "//*[@id='mx_98']/a"): [],
            (By.XPATH, '//*[@id="mx_98"]/a'): [],
            (By.XPATH, "//fallback-entry"): [
                _FakeElement(attrs={"href": "https://one.alimama.com/index.html#!/report/crowd"})
            ],
        }
    )  # type: ignore[assignment]

    assert exporter._get_wanxiangtai_entry_href().startswith("https://one.alimama.com/")


def test_build_douyin_metrics_maps_compass_values_to_report_fields() -> None:
    """
    抖店罗盘三指标应正确映射到现有报表字段。
    """
    exporter = WebExporter()

    metrics = exporter._build_douyin_metrics_result(
        trade_amount=1234.56,
        trade_order_count=78,
        expense_amount=90.12,
        shop_name="抖店A",
    )

    assert metrics["shop_name"] == "抖店A"
    assert metrics["payment_amount"] == 1234.56
    assert metrics["payment_sub_order_count"] == 78
    # 当前阶段无“成交买家数”独立指标，先与成交订单数保持一致
    assert metrics["payment_buyer_count"] == 78
    assert metrics["promotion_fee"] == 90.12
    assert metrics["trade_compensation"] == 0.0
    assert metrics["cross_border_value_added_fee"] == 0.0


def test_extract_douyin_compass_metric_parses_script_result_tokens() -> None:
    """
    电商罗盘指标读取应能解析页面脚本返回的金额/数量 token。
    """
    exporter = WebExporter()

    class Driver:
        def execute_script(self, _script: str, label: str) -> str:
            values = {
                "成交金额": "¥ 12,345.67",
                "成交订单数": "89",
                "支出金额": "1,234.50",
            }
            return values[label]

    exporter.driver = Driver()  # type: ignore[assignment]

    assert exporter._extract_douyin_compass_metric("成交金额") == 12345.67
    assert exporter._extract_douyin_compass_metric("成交订单数") == 89.0
    assert exporter._extract_douyin_compass_metric("支出金额") == 1234.5


def test_extract_douyin_metric_prefers_value_immediately_after_label() -> None:
    """
    抖店罗盘文本中应读取指标名后紧跟的主数值，不能误取较上期/同行标杆等对比值。
    """
    text = (
        "经营概况 成交金额 ¥108,936.00 较上期 7.08% 同行标杆 ¥14.07万 "
        "用户支付金额 ¥108,429.76 较上期 7.15% 同行标杆 ¥13.99万 "
        "成交订单数 784 较上期 6.81% 同行标杆 1,632 "
        "收支概况 结算金额 ¥8.3万 较上周期 13.08% "
        "支出金额 ¥ 1,745.05 1.78% 投放消耗（店铺被投） ¥ 45.65"
    )

    assert WebExporter._extract_metric_value_after_label_from_text(text, "成交金额") == 108936.0
    assert WebExporter._extract_metric_value_after_label_from_text(text, "成交订单数") == 784.0
    assert WebExporter._extract_metric_value_after_label_from_text(text, "支出金额") == 1745.05


def test_collect_douyin_compass_metrics_reads_three_core_values() -> None:
    """
    抖店采集主流程应读取成交金额、成交订单数、支出金额并映射到报表字段。
    """
    exporter = WebExporter()
    calls: list[str] = []

    exporter.driver = object()  # type: ignore[assignment]
    exporter.validate_runtime_config = lambda: None  # type: ignore[method-assign]
    exporter._ensure_wait = lambda: object()  # type: ignore[method-assign]
    exporter._close_douyin_notice_popup_if_present = lambda: False  # type: ignore[method-assign]
    exporter._open_douyin_compass_page = lambda: calls.append("open_compass")  # type: ignore[method-assign]
    exporter._set_douyin_period_last_1day = lambda: calls.append("set_1day")  # type: ignore[method-assign]
    exporter._promotion_pause = lambda scale=1.0: None  # type: ignore[method-assign]
    exporter._extract_douyin_shop_name = lambda: "抖店A"  # type: ignore[method-assign]
    exporter._collect_douyin_after_sale_refund_summary = lambda download_dir: calls.append("after_sale_refund") or {  # type: ignore[method-assign]
        "douyin_refund_metrics": {"refund_total_order_count": 9}
    }

    def _fake_metric(label: str) -> float:
        calls.append(f"metric:{label}")
        values = {"成交金额": 4567.89, "成交订单数": 123, "支出金额": 456.7}
        return values[label]

    exporter._extract_douyin_compass_metric = _fake_metric  # type: ignore[method-assign]

    metrics = exporter.collect_douyin_compass_metrics(download_dir=None)

    assert calls == [
        "open_compass",
        "set_1day",
        "metric:成交金额",
        "metric:成交订单数",
        "metric:支出金额",
        "after_sale_refund",
    ]
    assert metrics["shop_name"] == "抖店A"
    assert metrics["payment_amount"] == 4567.89
    assert metrics["payment_sub_order_count"] == 123
    assert metrics["payment_buyer_count"] == 123
    assert metrics["promotion_fee"] == 456.7
    assert metrics["refund_summary"]["douyin_refund_metrics"]["refund_total_order_count"] == 9


def test_after_sale_workbench_page_readiness_requires_export_action() -> None:
    """
    售后工作台不能只凭 URL 和部分筛选文案判定加载完成，必须等导出动作也出现。
    """
    exporter = WebExporter()
    exporter.get_current_url = (
        lambda: "https://fxg.jinritemai.com/ffa/merchant-aftersale-workbench/aftersale/list"
    )  # type: ignore[method-assign]

    marker_hits = {"售后工作台", "售后状态", "售后类型", "查询"}
    exporter._page_contains_text = lambda text: text in marker_hits  # type: ignore[method-assign]

    assert exporter._is_douyin_after_sale_workbench_page_by_content() is False


def test_select_douyin_after_sale_date_field_uses_compact_date_control() -> None:
    """
    售后工作台“申请时间/完结时间”是复合日期控件，不能按普通 labelWrapper 字段选择。
    """
    exporter = WebExporter()
    clicks: list[str] = []
    exporter.driver = _AfterSaleShortcutDriver(clicks)  # type: ignore[assignment]
    exporter._promotion_pause = lambda scale=1.0: None  # type: ignore[method-assign]

    assert exporter._select_douyin_after_sale_date_field_option("完结时间") is True
    assert clicks == ["date-field", "end-time-option"]


def test_select_douyin_after_sale_date_shortcut_uses_right_side_quick_select() -> None:
    """
    切到“完结时间”后，应点击日期行右侧“请选择”快捷下拉并选择“昨日”。
    """
    exporter = WebExporter()
    clicks: list[str] = []
    exporter.driver = _AfterSaleShortcutDriver(clicks)  # type: ignore[assignment]
    exporter._promotion_pause = lambda scale=1.0: None  # type: ignore[method-assign]

    assert exporter._select_douyin_after_sale_date_shortcut("昨日") is True
    assert clicks == ["date-shortcut", "yesterday-option"]


def test_open_douyin_compass_page_falls_back_to_direct_url_when_click_does_not_switch() -> None:
    """
    若点击顶部【电商罗盘】后未真正切页，应直接回退到罗盘 URL。
    """
    exporter = WebExporter()
    calls: list[tuple[str, object]] = []

    class _Driver:
        current_url = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"

        def get(self, url: str) -> None:
            calls.append(("get", url))

    exporter.driver = _Driver()  # type: ignore[assignment]
    exporter._ensure_driver = lambda: exporter.driver  # type: ignore[method-assign]
    exporter.get_current_url = lambda: "https://fxg.jinritemai.com/ffa/mshop/homepage/index"  # type: ignore[method-assign]
    exporter._switch_default_content = lambda: calls.append(("switch_default", ""))  # type: ignore[method-assign]
    exporter._close_douyin_notice_popup_if_present = lambda: False  # type: ignore[method-assign]
    exporter._capture_window_handles = lambda: {"a"}  # type: ignore[method-assign]
    exporter._try_click_selector = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._click_text_with_wait = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._wait_switch_to_douyin_compass_page = lambda *args, **kwargs: False  # type: ignore[method-assign]
    exporter._is_douyin_compass_page_by_content = lambda: False  # type: ignore[method-assign]
    exporter._wait_until = lambda *args, **kwargs: None  # type: ignore[method-assign]
    exporter._promotion_pause = lambda scale=1.0: None  # type: ignore[method-assign]
    exporter._log_step = lambda message: calls.append(("log", message))  # type: ignore[method-assign]

    exporter._open_douyin_compass_page()

    assert ("get", "https://compass.jinritemai.com/shop") in calls


def test_collect_douyin_all_shop_metrics_switches_unvisited_shops() -> None:
    """
    抖店多店铺采集应先采当前店，再依次切换到未访问店铺采集，直到没有新店。
    """
    exporter = WebExporter()
    shops = ["高品质裙裤", "咚咚源头女装", "高品专业女裤"]
    state = {"active_index": 0}
    calls: list[tuple[str, object]] = []

    def _fake_collect(download_dir=None, login_handler=None, switch_to_existing_page=True):
        shop_name = shops[state["active_index"]]
        calls.append(("collect", (shop_name, switch_to_existing_page)))
        return {"shop_name": shop_name, "platform": "douyin"}

    def _fake_switch(visited_shop_names):
        calls.append(("switch", tuple(visited_shop_names)))
        for index, shop_name in enumerate(shops):
            if shop_name not in visited_shop_names:
                state["active_index"] = index
                return shop_name
        return ""

    exporter.collect_douyin_compass_metrics = _fake_collect  # type: ignore[method-assign]
    exporter._switch_to_next_unvisited_douyin_shop = _fake_switch  # type: ignore[attr-defined]
    exporter._get_current_douyin_home_shop_name = lambda: ""  # type: ignore[attr-defined]

    metrics_list = exporter.collect_douyin_all_shop_metrics(download_dir=None)

    assert [metrics["shop_name"] for metrics in metrics_list] == shops
    assert calls == [
        ("collect", ("高品质裙裤", True)),
        ("switch", ("高品质裙裤",)),
        ("collect", ("咚咚源头女装", False)),
        ("switch", ("高品质裙裤", "咚咚源头女装")),
        ("collect", ("高品专业女裤", False)),
        ("switch", ("高品质裙裤", "咚咚源头女装", "高品专业女裤")),
    ]


def test_collect_douyin_all_shop_metrics_uses_switch_target_when_page_name_is_noisy() -> None:
    """
    切换店铺后，如果罗盘页正文干扰店铺名识别，应使用切换目标作为报表店铺名。
    """
    exporter = WebExporter()
    collect_names = ["高品质裙裤", "看看我超过谁"]
    switch_targets = ["咚咚源头女装", ""]
    calls: list[tuple[str, object]] = []

    def _fake_collect(download_dir=None, login_handler=None, switch_to_existing_page=True):
        shop_name = collect_names.pop(0)
        calls.append(("collect", (shop_name, switch_to_existing_page)))
        return {"shop_name": shop_name, "platform": "douyin"}

    def _fake_switch(visited_shop_names):
        calls.append(("switch", tuple(visited_shop_names)))
        return switch_targets.pop(0)

    exporter.collect_douyin_compass_metrics = _fake_collect  # type: ignore[method-assign]
    exporter._switch_to_next_unvisited_douyin_shop = _fake_switch  # type: ignore[attr-defined]
    exporter._get_current_douyin_home_shop_name = lambda: ""  # type: ignore[attr-defined]

    metrics_list = exporter.collect_douyin_all_shop_metrics(download_dir=None)

    assert [metrics["shop_name"] for metrics in metrics_list] == ["高品质裙裤", "咚咚源头女装"]
    assert calls == [
        ("collect", ("高品质裙裤", True)),
        ("switch", ("高品质裙裤",)),
        ("collect", ("看看我超过谁", False)),
        ("switch", ("高品质裙裤", "咚咚源头女装")),
    ]


def test_collect_douyin_all_shop_metrics_uses_home_shop_name_for_first_noisy_page_name() -> None:
    """
    第一轮如果罗盘页误识别正文文案，应使用首页右上角真实店铺名，避免多出假店铺。
    """
    exporter = WebExporter()
    collect_names = ["看看我超过谁", "高品专业女裤", "高品质裙裤"]
    switch_targets = ["高品专业女裤", "高品质裙裤", ""]
    calls: list[tuple[str, object]] = []

    def _fake_collect(download_dir=None, login_handler=None, switch_to_existing_page=True):
        shop_name = collect_names.pop(0)
        calls.append(("collect", (shop_name, switch_to_existing_page)))
        return {"shop_name": shop_name, "platform": "douyin"}

    def _fake_switch(visited_shop_names):
        calls.append(("switch", tuple(visited_shop_names)))
        return switch_targets.pop(0)

    exporter.collect_douyin_compass_metrics = _fake_collect  # type: ignore[method-assign]
    exporter._switch_to_next_unvisited_douyin_shop = _fake_switch  # type: ignore[attr-defined]
    exporter._get_current_douyin_home_shop_name = lambda: "咚咚源头女装"  # type: ignore[attr-defined]

    metrics_list = exporter.collect_douyin_all_shop_metrics(download_dir=None)

    assert [metrics["shop_name"] for metrics in metrics_list] == [
        "咚咚源头女装",
        "高品专业女裤",
        "高品质裙裤",
    ]
    assert calls == [
        ("collect", ("看看我超过谁", False)),
        ("switch", ("咚咚源头女装",)),
        ("collect", ("高品专业女裤", False)),
        ("switch", ("咚咚源头女装", "高品专业女裤")),
        ("collect", ("高品质裙裤", False)),
        ("switch", ("咚咚源头女装", "高品专业女裤", "高品质裙裤")),
    ]


def test_is_douyin_compass_url_matches_jinritemai_compass_page() -> None:
    """
    抖店电商罗盘 URL 判定应仅接受 jinritemai 域的罗盘页。
    """
    assert WebExporter._is_douyin_compass_url("https://compass.jinritemai.com/login") is True
    assert WebExporter._is_douyin_compass_url(
        "https://fxg.jinritemai.com/index_v2.html#/ffa/homepage"
    ) is False
    assert WebExporter._is_douyin_compass_url("https://myseller.taobao.com/home.htm/QnworkbenchHome/") is False


def test_douyin_expected_url_accepts_compass_subdomain() -> None:
    """
    抖店附着模式应允许从 fxg 首页切到 compass 罗盘子域名。
    """
    exporter = WebExporter(
        export_url="https://fxg.jinritemai.com/ffa/mshop/homepage/index",
        expected_url_prefix="https://fxg.jinritemai.com/",
    )

    assert exporter._is_expected_url("https://compass.jinritemai.com/shop") is True
