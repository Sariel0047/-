"""
`main.py` 平台路由测试。
"""

from __future__ import annotations

from datetime import date
import pytest

from pathlib import Path

from main import (
    collect_attached_browser_platform_urls,
    collect_platform_metrics,
    collect_platform_metrics_batch,
    process_data,
    resolve_startup_mode,
    resolve_target_platform,
    write_business_finance_reports,
)


def test_resolve_target_platform_prefers_explicit_selection() -> None:
    """
    用户显式选择平台时，应优先使用该选择，不受 URL 干扰。
    """
    platform, reason = resolve_target_platform(
        configured_platform="douyin",
        candidate_urls=("https://myseller.taobao.com/home.htm/QnworkbenchHome/",),
    )
    assert platform == "douyin"
    assert "用户显式选择" in reason


def test_startup_mode_defaults_to_gui_for_non_technical_users() -> None:
    """
    直接启动 main.py 时应进入 GUI，保留 --cli 给调试/旧流程使用。
    """
    assert resolve_startup_mode(()) == "gui"
    assert resolve_startup_mode(("--gui",)) == "gui"
    assert resolve_startup_mode(("--cli",)) == "cli"


def test_resolve_target_platform_detects_by_url_in_auto_mode() -> None:
    """
    auto 模式应按 URL 关键字判定平台。
    """
    platform_taobao, _ = resolve_target_platform(
        configured_platform="auto",
        candidate_urls=("https://myseller.taobao.com/home.htm/QnworkbenchHome/",),
    )
    assert platform_taobao == "taobao"

    platform_douyin, _ = resolve_target_platform(
        configured_platform="auto",
        candidate_urls=("https://fxg.jinritemai.com/ffa/morder/order/list",),
    )
    assert platform_douyin == "douyin"


def test_auto_platform_detection_prefers_attached_browser_url_before_config_default() -> None:
    """
    auto 模式应优先使用附着浏览器中的真实抖店 URL，而不是配置里的默认淘宝 URL。
    """

    class _FakeDriver:
        current_window_handle = "current"
        window_handles = ["current", "douyin"]

        def __init__(self) -> None:
            self._active = "current"

        @property
        def current_url(self) -> str:
            urls = {
                "current": "chrome://omnibox-popup.top-chrome/",
                "douyin": "https://fxg.jinritemai.com/ffa/mshop/homepage/index",
            }
            return urls[self._active]

        @property
        def switch_to(self) -> "_FakeDriver":
            return self

        def window(self, handle: str) -> None:
            self._active = handle

    class _FakeExporter:
        attach_to_existing_browser = True
        driver = _FakeDriver()

    browser_urls = collect_attached_browser_platform_urls(
        web_exporter=_FakeExporter(),  # type: ignore[arg-type]
        download_dir=Path("/tmp"),
    )
    platform, reason = resolve_target_platform(
        configured_platform="auto",
        candidate_urls=(
            *browser_urls,
            "https://myseller.taobao.com/home.htm/QnworkbenchHome/",
        ),
    )

    assert platform == "douyin"
    assert "jinritemai" in reason


def test_resolve_target_platform_raises_when_no_hint() -> None:
    """
    auto 模式且 URL 无关键字时，应抛出明确异常。
    """
    with pytest.raises(RuntimeError):
        resolve_target_platform(
            configured_platform="auto",
            candidate_urls=("https://example.com",),
        )


def test_collect_platform_metrics_uses_taobao_flow() -> None:
    """
    taobao 平台应调用天猫业务财务提取方法。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Path]] = []

        def collect_business_finance_metrics(self, download_dir: Path) -> dict[str, int]:
            self.calls.append(("taobao", download_dir))
            return {"ok": 1}

        def collect_douyin_compass_metrics(self, download_dir: Path) -> dict[str, int]:
            self.calls.append(("douyin", download_dir))
            return {"ok": 2}

    exporter = _FakeExporter()
    target_dir = Path("/tmp/a")
    result = collect_platform_metrics(exporter, "taobao", target_dir)

    assert result == {"ok": 1, "platform": "taobao"}
    assert exporter.calls == [("taobao", target_dir)]


def test_collect_platform_metrics_passes_report_date_to_taobao_flow() -> None:
    """
    淘宝指标采集应接收用户选择的报表日期。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, date]] = []

        def collect_business_finance_metrics(
            self,
            download_dir: Path,
            report_date: date,
        ) -> dict[str, object]:
            self.calls.append((download_dir, report_date))
            return {"report_date": report_date.isoformat()}

    exporter = _FakeExporter()
    target_date = date(2026, 3, 29)
    target_dir = Path("/tmp/taobao")

    result = collect_platform_metrics(
        exporter,
        "taobao",
        target_dir,
        report_date=target_date,
    )

    assert result == {"report_date": "2026-03-29", "platform": "taobao"}
    assert exporter.calls == [(target_dir, target_date)]


def test_collect_platform_metrics_uses_douyin_flow() -> None:
    """
    douyin 平台应调用抖店罗盘提取方法。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Path]] = []

        def collect_business_finance_metrics(self, download_dir: Path) -> dict[str, int]:
            self.calls.append(("taobao", download_dir))
            return {"ok": 1}

        def collect_douyin_compass_metrics(self, download_dir: Path) -> dict[str, int]:
            self.calls.append(("douyin", download_dir))
            return {"ok": 2}

    exporter = _FakeExporter()
    target_dir = Path("/tmp/b")
    result = collect_platform_metrics(exporter, "douyin", target_dir)

    assert result == {"ok": 2, "platform": "douyin"}
    assert exporter.calls == [("douyin", target_dir)]


def test_collect_platform_metrics_passes_report_date_to_douyin_flow() -> None:
    """
    抖音罗盘指标采集应接收用户选择的报表日期。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, date]] = []

        def collect_douyin_compass_metrics(
            self,
            download_dir: Path,
            report_date: date,
        ) -> dict[str, object]:
            self.calls.append((download_dir, report_date))
            return {"report_date": report_date.isoformat()}

    exporter = _FakeExporter()
    target_date = date(2026, 6, 15)
    target_dir = Path("/tmp/douyin")

    result = collect_platform_metrics(
        exporter,
        "douyin",
        target_dir,
        report_date=target_date,
    )

    assert result == {"report_date": "2026-06-15", "platform": "douyin"}
    assert exporter.calls == [(target_dir, target_date)]


def test_process_data_passes_explicit_report_date() -> None:
    """
    主流程数据处理包装应把用户选择的报表日期传给 DataProcessor。
    """

    class _FakeProcessor:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, Path, date]] = []

        def process(
            self,
            input_path: Path,
            output_path: Path,
            report_date: date,
        ) -> dict[str, object]:
            self.calls.append((input_path, output_path, report_date))
            return {"ok": True}

    processor = _FakeProcessor()
    target_date = date(2026, 3, 29)
    result = process_data(
        data_processor=processor,
        input_path=Path("/tmp/raw.xlsx"),
        processed_path=Path("/tmp/processed.xlsx"),
        report_date=target_date,
    )

    assert result == {"ok": True}
    assert processor.calls == [
        (Path("/tmp/raw.xlsx"), Path("/tmp/processed.xlsx"), target_date)
    ]


def test_collect_platform_metrics_batch_uses_douyin_all_shop_flow() -> None:
    """
    douyin 平台应优先采集所有可切换店铺，并返回多条待写表指标。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Path]] = []

        def collect_douyin_all_shop_metrics(self, download_dir: Path) -> list[dict[str, object]]:
            self.calls.append(("douyin_all", download_dir))
            return [
                {"shop_name": "高品质裙裤"},
                {"shop_name": "咚咚源头女装"},
                {"shop_name": "高品专业女裤"},
            ]

        def collect_douyin_compass_metrics(self, download_dir: Path) -> dict[str, object]:
            self.calls.append(("douyin_single", download_dir))
            return {"shop_name": "高品质裙裤"}

    exporter = _FakeExporter()
    target_dir = Path("/tmp/douyin")
    result = collect_platform_metrics_batch(exporter, "douyin", target_dir)

    assert [item["shop_name"] for item in result] == ["高品质裙裤", "咚咚源头女装", "高品专业女裤"]
    assert all(item["platform"] == "douyin" for item in result)
    assert exporter.calls == [("douyin_all", target_dir)]


def test_collect_platform_metrics_batch_passes_report_date_to_douyin_all_shop_flow() -> None:
    """
    批量采集抖音店铺时，也应把 GUI 选择的报表日期传给抖音采集入口。
    """

    class _FakeExporter:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, date]] = []

        def collect_douyin_all_shop_metrics(
            self,
            download_dir: Path,
            report_date: date,
        ) -> list[dict[str, object]]:
            self.calls.append((download_dir, report_date))
            return [{"shop_name": "高品质裙裤", "report_date": report_date.isoformat()}]

    exporter = _FakeExporter()
    target_date = date(2026, 6, 15)
    target_dir = Path("/tmp/douyin")

    result = collect_platform_metrics_batch(
        exporter,
        "douyin",
        target_dir,
        report_date=target_date,
    )

    assert result == [{"shop_name": "高品质裙裤", "report_date": "2026-06-15", "platform": "douyin"}]
    assert exporter.calls == [(target_dir, target_date)]


def test_write_business_finance_reports_writes_each_metric_row(tmp_path: Path) -> None:
    """
    多店铺指标应分别生成多份业务财务报表。
    """

    class _FakeWriter:
        def __init__(self) -> None:
            self.calls: list[tuple[dict[str, object], Path]] = []

        def export_business_finance_metrics(self, metrics: dict[str, object], output_path: Path) -> Path:
            self.calls.append((metrics, output_path))
            return output_path / f"{metrics['shop_name']}.xlsx"

    writer = _FakeWriter()
    metrics_list = [
        {"shop_name": "高品质裙裤"},
        {"shop_name": "咚咚源头女装"},
    ]

    outputs = write_business_finance_reports(writer, metrics_list, output_dir=tmp_path)

    assert outputs == [tmp_path / "高品质裙裤.xlsx", tmp_path / "咚咚源头女装.xlsx"]
    assert [call[0]["shop_name"] for call in writer.calls] == ["高品质裙裤", "咚咚源头女装"]
    assert all(call[1] == tmp_path for call in writer.calls)
