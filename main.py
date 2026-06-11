"""
项目启动入口。
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
import sys
import traceback
from typing import TYPE_CHECKING, Any

from qianiu_auto_report.config import (
    DateConfig,
    EXCEL_OUTPUT_DIR,
    ExportConfig,
    PROCESSED_OUTPUT_DIR,
)

if TYPE_CHECKING:
    from qianiu_auto_report.data_process import DataProcessor
    from qianiu_auto_report.excel_writer import ExcelWriter
    from qianiu_auto_report.web_export import WebExporter


def resolve_startup_mode(argv: tuple[str, ...] | None = None) -> str:
    """
    解析启动模式。

    默认面向非技术用户打开 GUI；调试和历史命令行流程可用 --cli 保留。
    """
    args = tuple(sys.argv[1:] if argv is None else argv)
    if "--cli" in args:
        return "cli"
    return "gui"


def _detect_platform_from_url(url: str) -> str | None:
    """
    依据 URL 关键字识别平台。
    """
    normalized = (url or "").strip().lower()
    if not normalized:
        return None
    if "jinritemai" in normalized:
        return "douyin"
    if "taobao" in normalized:
        return "taobao"
    return None


def resolve_target_platform(
    configured_platform: str,
    candidate_urls: tuple[str, ...],
) -> tuple[str, str]:
    """
    解析最终执行平台。
    规则：
    1) 用户显式选择（taobao/douyin）优先；
    2) 其余情况按 URL 关键字自动判定。
    """
    normalized = (configured_platform or "auto").strip().lower()
    if normalized in {"taobao", "douyin"}:
        return normalized, f"用户显式选择：{normalized}"

    for url in candidate_urls:
        detected = _detect_platform_from_url(url)
        if detected is not None:
            return detected, f"URL判定：{url}"

    raise RuntimeError(
        "无法自动判定平台。请显式设置 QIANNIU_PLATFORM=taobao 或 QIANNIU_PLATFORM=douyin，"
        "或在 URL 中包含 taobao/jinritemai。"
    )


def collect_attached_browser_platform_urls(
    web_exporter: "WebExporter",
    download_dir: Path,
) -> tuple[str, ...]:
    """
    附着模式下读取当前浏览器标签页 URL，供 auto 平台判定优先使用。
    """
    if not getattr(web_exporter, "attach_to_existing_browser", False):
        return tuple()

    original_export_url = getattr(web_exporter, "export_url", "")
    original_expected_url_prefix = getattr(web_exporter, "expected_url_prefix", "")
    urls: list[str] = []

    try:
        if getattr(web_exporter, "driver", None) is None:
            # 平台尚未判定时先放宽域名校验，避免默认淘宝 URL 挡住抖店标签页。
            web_exporter.export_url = ""
            web_exporter.expected_url_prefix = ""
            web_exporter.init_driver(download_dir=download_dir)
    finally:
        web_exporter.export_url = original_export_url
        web_exporter.expected_url_prefix = original_expected_url_prefix

    driver = getattr(web_exporter, "driver", None)
    if driver is None:
        return tuple()

    def add_url(value: str) -> None:
        clean = (value or "").strip()
        if clean and clean not in urls:
            urls.append(clean)

    try:
        add_url(driver.current_url)
    except Exception:
        pass

    try:
        current_handle = driver.current_window_handle
        handles = list(driver.window_handles)
    except Exception:
        return tuple(urls)

    ordered_handles = [current_handle, *[handle for handle in handles if handle != current_handle]]
    for handle in ordered_handles:
        try:
            driver.switch_to.window(handle)
            add_url(driver.current_url)
        except Exception:
            continue

    return tuple(urls)


def ensure_runtime_directories() -> None:
    """
    确保运行时所需目录存在。
    """
    for directory in (Path(ExportConfig.DOWNLOAD_DIR), PROCESSED_OUTPUT_DIR, EXCEL_OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def normalize_report_date(report_date: date | datetime | str | None = None) -> date:
    """
    将报表日期统一为 date；未传时使用默认“昨天”。
    """
    if report_date is None:
        return DateConfig.default_report_date()
    if isinstance(report_date, datetime):
        return report_date.date()
    if isinstance(report_date, date):
        return report_date
    return datetime.strptime(str(report_date).strip(), DateConfig.DATE_FORMAT).date()


def build_output_paths() -> dict[str, Path]:
    """
    生成处理结果和最终报表输出路径。
    """
    return {
        "download_dir": Path(ExportConfig.DOWNLOAD_DIR),
        "processed_path": PROCESSED_OUTPUT_DIR / "processed_report.xlsx",
        "excel_dir": EXCEL_OUTPUT_DIR,
    }


def export_data(web_exporter: "WebExporter", download_dir: Path) -> Path:
    """
    调用网页导出模块导出原始数据。
    """
    exported_file = web_exporter.export_report(download_dir=download_dir)
    if not isinstance(exported_file, Path):
        raise TypeError("web_export.export_report 必须返回 Path 对象。")
    return exported_file


def collect_business_finance_metrics(
    web_exporter: "WebExporter",
    download_dir: Path,
    report_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """
    提取退款管理之外的业务/财务指标。
    """
    if report_date is None:
        metrics = web_exporter.collect_business_finance_metrics(download_dir=download_dir)
    else:
        metrics = web_exporter.collect_business_finance_metrics(
            download_dir=download_dir,
            report_date=normalize_report_date(report_date),
        )
    if not isinstance(metrics, dict):
        raise TypeError("web_export.collect_business_finance_metrics 必须返回 dict。")
    return metrics


def collect_platform_metrics(
    web_exporter: "WebExporter",
    target_platform: str,
    download_dir: Path,
    report_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """
    按平台路由采集指标。
    """
    if target_platform == "douyin":
        metrics = web_exporter.collect_douyin_compass_metrics(download_dir=download_dir)
        if not isinstance(metrics, dict):
            raise TypeError("web_export.collect_douyin_compass_metrics 必须返回 dict。")
        metrics.setdefault("platform", "douyin")
        return metrics

    if target_platform == "taobao":
        metrics = collect_business_finance_metrics(
            web_exporter=web_exporter,
            download_dir=download_dir,
            report_date=report_date,
        )
        metrics.setdefault("platform", "taobao")
        return metrics

    raise ValueError(f"不支持的平台：{target_platform}")


def collect_platform_metrics_batch(
    web_exporter: "WebExporter",
    target_platform: str,
    download_dir: Path,
    report_date: date | datetime | str | None = None,
) -> list[dict[str, Any]]:
    """
    按平台采集一组指标。抖音支持切换多个店铺，淘宝保持单店铺流程。
    """
    if target_platform == "douyin":
        collect_all = getattr(web_exporter, "collect_douyin_all_shop_metrics", None)
        if callable(collect_all):
            metrics_list = collect_all(download_dir=download_dir)
            if not isinstance(metrics_list, list):
                raise TypeError("web_export.collect_douyin_all_shop_metrics 必须返回 list。")
            for metrics in metrics_list:
                if not isinstance(metrics, dict):
                    raise TypeError("web_export.collect_douyin_all_shop_metrics 中每一项必须为 dict。")
                metrics.setdefault("platform", "douyin")
            return metrics_list

    return [
        collect_platform_metrics(
            web_exporter=web_exporter,
            target_platform=target_platform,
            download_dir=download_dir,
            report_date=report_date,
        )
    ]


def write_business_finance_reports(
    excel_writer: "ExcelWriter",
    metrics_list: list[dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    """
    将一组业务/财务指标分别写成独立 Excel 文件。
    """
    report_files: list[Path] = []
    for metrics in metrics_list:
        report_file = excel_writer.export_business_finance_metrics(
            metrics=metrics,
            output_path=output_dir,
        )
        report_files.append(report_file)
    return report_files


def process_data(
    data_processor: "DataProcessor",
    input_path: Path,
    processed_path: Path,
    report_date: date | datetime | str | None = None,
) -> Any:
    """
    调用数据处理模块处理原始数据。
    """
    return data_processor.process(
        input_path=input_path,
        output_path=processed_path,
        report_date=normalize_report_date(report_date),
    )


def write_excel(
    excel_writer: "ExcelWriter",
    processed_data: Any,
    output_dir: Path,
) -> Path:
    """
    调用 Excel 写入模块生成最终报表。
    """
    return excel_writer.export(df=processed_data, output_path=output_dir)


def build_components() -> tuple["WebExporter", "DataProcessor", "ExcelWriter"]:
    """
    延迟加载业务模块，避免导入阶段直接崩溃。
    """
    from qianiu_auto_report.data_process import DataProcessor
    from qianiu_auto_report.excel_writer import ExcelWriter
    from qianiu_auto_report.web_export import WebExporter

    return WebExporter(), DataProcessor(), ExcelWriter()


def _unwrap_exception(exc: Exception) -> Exception:
    """
    获取最底层异常，便于输出真实失败原因。
    """
    root = exc
    while getattr(root, "__cause__", None) is not None and isinstance(root.__cause__, Exception):
        root = root.__cause__
    return root


def format_failure_message(stage: str, exc: Exception) -> str:
    """
    构建可读的失败信息。
    """
    root = _unwrap_exception(exc)
    root_message = str(root) or "无详细错误信息"

    lines = [
        "执行失败",
        f"失败阶段：{stage}",
        f"异常类型：{type(root).__name__}",
        f"异常信息：{root_message}",
    ]

    if isinstance(root, ModuleNotFoundError):
        missing_module = getattr(root, "name", "") or "未知依赖"
        lines.extend(
            [
                f"缺失依赖：{missing_module}",
                "建议执行：python3 -m pip install -r requirements.txt",
            ]
        )
    elif isinstance(root, NotImplementedError):
        lines.append("当前模块仍是模板占位实现，请先补全对应模块逻辑。")

    lines.extend(
        [
            "详细堆栈：",
            traceback.format_exc().strip(),
        ]
    )
    return "\n".join(lines)


def run_pipeline(report_date: date | datetime | str | None = None) -> bool:
    """
    串联导出、处理、写入三个模块并返回执行状态。
    """
    web_exporter: "WebExporter | None" = None
    stage = "初始化"

    try:
        ensure_runtime_directories()
        selected_report_date = normalize_report_date(report_date)
        paths = build_output_paths()

        stage = "加载业务模块"
        web_exporter, data_processor, excel_writer = build_components()

        stage = "平台判定"
        browser_candidate_urls = collect_attached_browser_platform_urls(
            web_exporter=web_exporter,
            download_dir=paths["download_dir"],
        )
        target_platform, platform_reason = resolve_target_platform(
            configured_platform=ExportConfig.PLATFORM,
            candidate_urls=(
                *browser_candidate_urls,
                ExportConfig.EXPORT_URL,
                ExportConfig.LOGIN_URL,
                ExportConfig.EXPECTED_URL_PREFIX,
            ),
        )
        print(f"平台判定：{target_platform}（{platform_reason}）")
        skip_refund_manage_actions = ExportConfig.SKIP_REFUND_MANAGE_ACTIONS or target_platform == "douyin"
        if target_platform == "douyin" and not ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
            print("检测到抖店流程：跳过千牛退款管理，改采集罗盘退款分析明细。")

        if skip_refund_manage_actions:
            stage = "网页数据提取"
            metrics_list = collect_platform_metrics_batch(
                web_exporter=web_exporter,
                target_platform=target_platform,
                download_dir=paths["download_dir"],
                report_date=selected_report_date,
            )
            for index, metrics in enumerate(metrics_list, start=1):
                print(
                    f"提取结果[{index}/{len(metrics_list)}]："
                    f"店铺名={metrics.get('shop_name') or '<未识别>'}，"
                    f"支付买家数={metrics.get('payment_buyer_count')}，"
                    f"支付金额={metrics.get('payment_amount')}，"
                    f"支付子订单数={metrics.get('payment_sub_order_count')}，"
                    f"交易赔付={metrics.get('trade_compensation')}，"
                    f"淘宝天猫跨境服务增值费={metrics.get('cross_border_value_added_fee')}，"
                    f"推广费用={metrics.get('promotion_fee')}"
                )

            if ExportConfig.SKIP_EXCEL_WRITE:
                print("已跳过：Excel写入步骤（SKIP_EXCEL_WRITE=True）")
                print("执行成功（仅完成网页数据提取）。")
                return True

            stage = "Excel写入"
            report_files = write_business_finance_reports(
                excel_writer=excel_writer,
                metrics_list=metrics_list,
                output_dir=Path.home() / "Desktop",
            )
            for report_file in report_files:
                print(f"报表已生成：{report_file}")
            print(f"执行成功，共生成 {len(report_files)} 份报表。")
            return True
        else:
            stage = "网页导出"
            exported_file = export_data(
                web_exporter=web_exporter,
                download_dir=paths["download_dir"],
            )
            print(f"退款管理导出文件：{exported_file}")

            stage = "网页数据提取"
            metrics = collect_platform_metrics(
                web_exporter=web_exporter,
                target_platform=target_platform,
                download_dir=paths["download_dir"],
                report_date=selected_report_date,
            )
            print(
                "提取结果："
                f"店铺名={metrics.get('shop_name') or '<未识别>'}，"
                f"支付买家数={metrics.get('payment_buyer_count')}，"
                f"支付金额={metrics.get('payment_amount')}，"
                f"支付子订单数={metrics.get('payment_sub_order_count')}，"
                f"交易赔付={metrics.get('trade_compensation')}，"
                f"淘宝天猫跨境服务增值费={metrics.get('cross_border_value_added_fee')}，"
                f"推广费用={metrics.get('promotion_fee')}"
            )

        # 当需要输出“退款模板+A/B合并报表”时，数据处理是必需步骤；
        # 即使配置为跳过，也自动降级为执行处理，避免最终写表失败。
        require_processed_for_excel = (
            not ExportConfig.SKIP_EXCEL_WRITE and not skip_refund_manage_actions
        )
        skip_data_process_effective = ExportConfig.SKIP_DATA_PROCESS and not require_processed_for_excel
        if ExportConfig.SKIP_DATA_PROCESS and require_processed_for_excel:
            print("检测到 SKIP_DATA_PROCESS=True，但当前需写入合并报表，已自动执行数据处理。")

        if skip_data_process_effective:
            print("已跳过：数据处理步骤（SKIP_DATA_PROCESS=True）")
            processed_data = None
        else:
            if exported_file is None:
                raise RuntimeError("数据处理已开启，但未获取到导出文件。请关闭 SKIP_REFUND_MANAGE_ACTIONS。")
            stage = "数据处理"
            processed_data = process_data(
                data_processor=data_processor,
                input_path=exported_file,
                processed_path=paths["processed_path"],
                report_date=selected_report_date,
            )

        if ExportConfig.SKIP_EXCEL_WRITE:
            print("已跳过：Excel写入步骤（SKIP_EXCEL_WRITE=True）")
            print("执行成功（简化流程）。")
            return True

        if processed_data is None:
            raise RuntimeError("Excel写入已开启，但未获取到处理结果。请关闭 SKIP_DATA_PROCESS。")

        stage = "Excel写入"
        if skip_refund_manage_actions:
            report_file = write_excel(
                excel_writer=excel_writer,
                processed_data=processed_data,
                output_dir=Path.home() / "Desktop",
            )
        else:
            report_file = excel_writer.export_refund_with_business_finance_metrics(
                refund_summary=processed_data,
                metrics=metrics,
                output_path=Path.home() / "Desktop",
            )
        print(f"执行成功，报表已生成：{report_file}")
        return True
    except Exception as exc:
        print(format_failure_message(stage=stage, exc=exc))
        return False
    finally:
        if web_exporter is not None:
            try:
                web_exporter.close()
            except Exception:
                pass


def main(argv: tuple[str, ...] | None = None) -> bool:
    """
    应用程序主入口。
    """
    if os.getenv("QIANNIU_SELF_CHECK", "").strip() in {"1", "true", "True", "yes", "on"}:
        from selenium import webdriver as _webdriver
        from selenium.webdriver.chrome.webdriver import WebDriver as _ChromeWebDriver

        _ = (_webdriver, _ChromeWebDriver)
        print("SELF_CHECK_OK")
        return True

    if resolve_startup_mode(argv) == "gui":
        from qianiu_auto_report.gui import AppGUI

        AppGUI().run()
        return True
    return run_pipeline()


if __name__ == "__main__":
    raise SystemExit(0 if main(tuple(sys.argv[1:])) else 1)
