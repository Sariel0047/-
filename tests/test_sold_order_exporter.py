"""
已卖出宝贝订单导出独立流程测试。
"""

from __future__ import annotations

from pathlib import Path

from qianiu_auto_report.sold_order_exporter import SoldOrderExporter


def test_normalize_product_ids_accepts_batch_text() -> None:
    """
    商品 ID 支持逗号、中文逗号、空白和换行批量输入。
    """
    assert SoldOrderExporter.normalize_product_ids(" 785178549966，\n906669497660,, ") == (
        "785178549966",
        "906669497660",
    )


def test_payment_time_selected_reads_range_picker_input_values() -> None:
    """
    付款时间校验应读取控件 input value，而不是只依赖页面正文文本。
    """
    exporter = SoldOrderExporter()

    class FakeDriver:
        def execute_script(self, *_args: object) -> list[str]:
            return ["2026-06-15 00:00:00", "2026-06-30 23:59:59"]

    exporter.driver = FakeDriver()  # type: ignore[assignment]

    assert exporter._payment_time_selected("2026-06-15 00:00:00", "2026-06-30 23:59:59")


def test_payment_time_selected_does_not_trust_page_text_when_inputs_are_blank() -> None:
    """
    页面正文或弹层里残留日期时，付款时间也必须以控件 input value 为准。
    """
    exporter = SoldOrderExporter()

    class FakeDriver:
        def execute_script(self, *_args: object) -> list[str]:
            return ["", ""]

    exporter.driver = FakeDriver()  # type: ignore[assignment]
    exporter._page_text_snippet = lambda max_length=6000: "2026-06-15 00:00:00 2026-06-30 23:59:59"  # type: ignore[method-assign]

    assert not exporter._payment_time_selected("2026-06-15 00:00:00", "2026-06-30 23:59:59")


def test_select_sales_detail_report_option_requires_selected_state() -> None:
    """
    报表类型点击后必须读回选中状态，避免只点中文字但 radio 未切换。
    """
    exporter = SoldOrderExporter()

    class FakeDriver:
        def __init__(self) -> None:
            self.calls = 0

        def execute_script(self, script: str, *_args: object) -> bool:
            self.calls += 1
            assert "宝贝销售明细报表" in script
            return True

    driver = FakeDriver()
    exporter.driver = driver  # type: ignore[assignment]

    assert exporter._select_sales_detail_report_option()
    assert driver.calls == 2


def test_export_after_login_runs_sold_order_steps(tmp_path: Path) -> None:
    """
    已登录后订单导出应按页面导航、设置条件、提交报表、等待下载执行。
    """
    exporter = SoldOrderExporter()
    calls: list[object] = []

    exporter.validate_runtime_config = lambda: calls.append("validate")  # type: ignore[method-assign]
    exporter._ensure_driver = lambda: calls.append("driver") or object()  # type: ignore[method-assign]
    exporter._ensure_wait = lambda: calls.append("waiter") or object()  # type: ignore[method-assign]
    exporter.navigate_to_sold_orders_page = lambda: calls.append("navigate")  # type: ignore[method-assign]
    exporter.set_export_conditions = lambda **kwargs: calls.append(("conditions", kwargs))  # type: ignore[method-assign]
    exporter.submit_export_task = lambda: calls.append("submit") or 123.0  # type: ignore[method-assign]
    exporter.wait_for_download = lambda download_dir, trigger_ts, snapshot: calls.append(  # type: ignore[method-assign]
        ("download", download_dir, trigger_ts, isinstance(snapshot, dict))
    ) or (tmp_path / "orders.xlsx")

    result = exporter.export_after_login(
        download_dir=tmp_path,
        product_ids="785178549966,906669497660",
        start_date="2026-06-15",
        end_date="2026-06-30",
    )

    assert result == tmp_path / "orders.xlsx"
    assert calls[:5] == [
        "validate",
        "driver",
        "waiter",
        "navigate",
        (
            "conditions",
            {
                "product_ids": "785178549966,906669497660",
                "start_date": "2026-06-15",
                "end_date": "2026-06-30",
            },
        ),
    ]
    assert calls[-2:] == ["submit", ("download", tmp_path, 123.0, True)]


def test_set_export_conditions_runs_batch_search_before_payment_time() -> None:
    """
    批量商品 ID 搜索应先填商品 ID，再设置付款时间，最后由提交阶段点击搜索订单。
    """
    exporter = SoldOrderExporter()
    calls: list[object] = []

    exporter._close_corner_popup_if_present = lambda: calls.append("close_popup")  # type: ignore[method-assign]
    exporter._ensure_sold_order_filters_expanded = lambda: calls.append("expand_filters")  # type: ignore[method-assign]
    exporter._set_payment_time_range = lambda **kwargs: calls.append(("payment_time", kwargs))  # type: ignore[method-assign]
    exporter._set_batch_product_id_search = lambda product_ids: calls.append(("batch_search", product_ids))  # type: ignore[method-assign]

    exporter.set_export_conditions(
        product_ids="953384660197,806014088993",
        start_date="2026-05-15",
        end_date="2026-06-15",
    )

    assert calls == [
        "close_popup",
        "expand_filters",
        ("batch_search", "953384660197,806014088993"),
        (
            "payment_time",
            {
                "start_date": "2026-05-15",
                "end_date": "2026-06-15",
            },
        ),
    ]


def test_set_batch_product_id_search_uses_english_comma_values() -> None:
    """
    商品 ID 批量搜索弹窗中应写入英文逗号分隔的商品 ID。
    """
    exporter = SoldOrderExporter()
    calls: list[object] = []

    exporter._open_batch_search_dialog = lambda: calls.append("open") or True  # type: ignore[method-assign]
    exporter._select_batch_search_product_id_radio = lambda: calls.append("select_product_id") or True  # type: ignore[method-assign]
    exporter._set_batch_search_product_ids = lambda value: calls.append(("fill", value)) or True  # type: ignore[method-assign]
    exporter._confirm_batch_search_dialog = lambda: calls.append("confirm") or True  # type: ignore[method-assign]

    exporter._set_batch_product_id_search("953384660197，806014088993\n903584416527")

    assert calls == [
        "open",
        "select_product_id",
        ("fill", "953384660197,806014088993,903584416527"),
        "confirm",
    ]


def test_wait_switch_to_export_list_uses_new_handle_without_scanning_old_tabs() -> None:
    """
    切到报表页时应优先锁定本次新打开的标签，避免在旧标签之间反复横跳。
    """
    exporter = SoldOrderExporter()
    exporter.export_list_switch_timeout_seconds = 5
    exporter.ui_poll_interval_seconds = 0.01
    calls: list[str] = []

    class FakeDriver:
        def __init__(self) -> None:
            self.window_handles = ["sold", "export"]
            self.current = "sold"

        class SwitchTo:
            def __init__(self, outer: "FakeDriver") -> None:
                self.outer = outer

            def window(self, handle: str) -> None:
                calls.append(handle)
                self.outer.current = handle

        @property
        def switch_to(self) -> "FakeDriver.SwitchTo":
            return self.SwitchTo(self)

    driver = FakeDriver()
    exporter.driver = driver  # type: ignore[assignment]
    exporter._capture_window_handles = lambda: set(driver.window_handles)  # type: ignore[method-assign]
    exporter._is_export_list_page = lambda: driver.current == "export"  # type: ignore[method-assign]

    assert exporter._wait_switch_to_export_list_page(previous_handles={"sold"})
    assert calls == ["export"]


def test_wait_report_ready_returns_to_sold_orders_page_after_download_click() -> None:
    """
    触发下载后应回到原已卖出宝贝标签页，避免停在报表页继续切换。
    """
    exporter = SoldOrderExporter()
    exporter.report_ready_timeout_seconds = 60

    class FakeDriver:
        def __init__(self) -> None:
            self.current_window_handle = "sold"
            self.switched: list[str] = []
            self.closed = False

        class SwitchTo:
            def __init__(self, outer: "FakeDriver") -> None:
                self.outer = outer

            def window(self, handle: str) -> None:
                self.outer.switched.append(handle)
                self.outer.current_window_handle = handle

        @property
        def switch_to(self) -> "FakeDriver.SwitchTo":
            return self.SwitchTo(self)

        def close(self) -> None:
            self.closed = True

    class FakeButton:
        pass

    driver = FakeDriver()
    button = FakeButton()
    exporter.driver = driver  # type: ignore[assignment]
    exporter._is_export_list_page = lambda: True  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: None  # type: ignore[method-assign]
    exporter._find_download_button = lambda request_time="": button  # type: ignore[method-assign]
    exporter._click_with_retry = lambda element: None  # type: ignore[method-assign]
    driver.current_window_handle = "export"

    assert isinstance(exporter._wait_report_ready_and_click_download(origin_handle="sold"), float)
    assert driver.closed is True
    assert driver.switched == ["sold"]


def test_wait_report_ready_navigates_back_when_export_page_reuses_origin_tab() -> None:
    """
    如果报表页复用了原标签，触发下载后应回到已卖出宝贝页面。
    """
    exporter = SoldOrderExporter()
    exporter.report_ready_timeout_seconds = 60

    class FakeDriver:
        current_window_handle = "sold"

        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str) -> None:
            self.urls.append(url)

    class FakeButton:
        pass

    driver = FakeDriver()
    exporter.driver = driver  # type: ignore[assignment]
    exporter._is_export_list_page = lambda: True  # type: ignore[method-assign]
    exporter._close_corner_popup_if_present = lambda: None  # type: ignore[method-assign]
    exporter._find_download_button = lambda request_time="": FakeButton()  # type: ignore[method-assign]
    exporter._click_with_retry = lambda element: None  # type: ignore[method-assign]
    exporter._wait_dom_ready = lambda: None  # type: ignore[method-assign]

    assert isinstance(exporter._wait_report_ready_and_click_download(origin_handle="sold"), float)
    assert driver.urls == [exporter.SOLD_ORDERS_URL]
