"""
项目启动入口。
"""

from __future__ import annotations

from pathlib import Path
import traceback
from typing import TYPE_CHECKING, Any

from qianiu_auto_report.config import (
    EXCEL_OUTPUT_DIR,
    ExportConfig,
    PROCESSED_OUTPUT_DIR,
)

if TYPE_CHECKING:
    from qianiu_auto_report.data_process import DataProcessor
    from qianiu_auto_report.excel_writer import ExcelWriter
    from qianiu_auto_report.web_export import WebExporter


def ensure_runtime_directories() -> None:
    """
    确保运行时所需目录存在。
    """
    for directory in (Path(ExportConfig.DOWNLOAD_DIR), PROCESSED_OUTPUT_DIR, EXCEL_OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


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


def collect_business_finance_metrics(web_exporter: "WebExporter", download_dir: Path) -> dict[str, Any]:
    """
    提取退款管理之外的业务/财务指标。
    """
    metrics = web_exporter.collect_business_finance_metrics(download_dir=download_dir)
    if not isinstance(metrics, dict):
        raise TypeError("web_export.collect_business_finance_metrics 必须返回 dict。")
    return metrics


def process_data(
    data_processor: "DataProcessor",
    input_path: Path,
    processed_path: Path,
) -> Any:
    """
    调用数据处理模块处理原始数据。
    """
    return data_processor.process(input_path=input_path, output_path=processed_path)


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


def run_pipeline() -> bool:
    """
    串联导出、处理、写入三个模块并返回执行状态。
    """
    web_exporter: "WebExporter | None" = None
    stage = "初始化"

    try:
        ensure_runtime_directories()
        paths = build_output_paths()

        stage = "加载业务模块"
        web_exporter, data_processor, excel_writer = build_components()

        if ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
            stage = "网页数据提取"
            metrics = collect_business_finance_metrics(
                web_exporter=web_exporter,
                download_dir=paths["download_dir"],
            )
            print(
                "提取结果："
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
            report_file = excel_writer.export_business_finance_metrics(
                metrics=metrics,
                output_path=Path.home() / "Desktop",
            )
            print(f"执行成功，报表已生成：{report_file}")
            return True
        else:
            stage = "网页导出"
            exported_file = export_data(
                web_exporter=web_exporter,
                download_dir=paths["download_dir"],
            )

        if ExportConfig.SKIP_DATA_PROCESS:
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
            )

        if ExportConfig.SKIP_EXCEL_WRITE:
            print("已跳过：Excel写入步骤（SKIP_EXCEL_WRITE=True）")
            print("执行成功（简化流程）。")
            return True

        if processed_data is None:
            raise RuntimeError("Excel写入已开启，但未获取到处理结果。请关闭 SKIP_DATA_PROCESS。")

        stage = "Excel写入"
        report_file = write_excel(
            excel_writer=excel_writer,
            processed_data=processed_data,
            output_dir=paths["excel_dir"],
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


def main() -> bool:
    """
    应用程序主入口。
    """
    return run_pipeline()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
