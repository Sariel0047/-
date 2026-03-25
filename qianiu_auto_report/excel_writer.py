"""
Excel 输出模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from qianiu_auto_report.config import (
    DateConfig,
    EXCEL_OUTPUT_DIR,
    REPORT_TEMPLATE_PATH,
    TEMPLATE_DIR,
)


class ExcelWriter:
    """
    Excel 报表写入器。
    """

    SUMMARY_CELL_MAPPING = {
        "total_count": "B2",
        "total_amount": "C2",
        "已发货仅退款.count": "B4",
        "已发货仅退款.amount": "C4",
        "已发货仅退款.未收到货.count": "B5",
        "已发货仅退款.未收到货.amount": "C5",
        "已发货仅退款.已收到货.count": "B6",
        "已发货仅退款.已收到货.amount": "C6",
        "未发货仅退款.count": "B8",
        "未发货仅退款.amount": "C8",
        "未发货仅退款.未发货.count": "B9",
        "未发货仅退款.未发货.amount": "C9",
        "退货退款.count": "B11",
        "退货退款.amount": "C11",
        "退货退款.已寄回.count": "B12",
        "退货退款.已寄回.amount": "C12",
    }

    def __init__(self, template_path: Optional[Path] = None) -> None:
        self.template_path = template_path
        self.workbook: Optional[Workbook] = None
        self.worksheet: Optional[Worksheet] = None

    def _resolve_template_path(self) -> Path:
        """
        解析模板路径，优先使用 `template.xlsx`。
        """
        if self.template_path is not None:
            resolved = Path(self.template_path)
            if not resolved.exists():
                raise FileNotFoundError(f"模板文件不存在：{resolved}")
            return resolved

        candidates = [
            TEMPLATE_DIR / "template.xlsx",
            REPORT_TEMPLATE_PATH,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        searched = "、".join(str(path) for path in candidates)
        raise FileNotFoundError(f"未找到模板文件，请准备 template.xlsx。已检查路径：{searched}")

    def create_workbook(self) -> None:
        """
        创建工作簿（当模板不存在时可作为扩展入口）。
        """
        self.workbook = Workbook()
        self.worksheet = self.workbook.active

    def load_template(self) -> None:
        """
        加载 Excel 模板。
        """
        template_file = self._resolve_template_path()
        self.workbook = load_workbook(template_file)
        self.worksheet = self.workbook.active

    def prepare_sheet(self, sheet_name: str = "") -> None:
        """
        准备工作表，默认使用激活页。
        """
        if self.workbook is None:
            raise RuntimeError("工作簿未加载，请先调用 load_template。")

        if sheet_name and sheet_name in self.workbook.sheetnames:
            self.worksheet = self.workbook[sheet_name]
        elif self.worksheet is None:
            self.worksheet = self.workbook.active

    def _extract_value(self, stats: dict[str, Any], key_path: str) -> Any:
        """
        从统计字典中按路径提取值，不存在时返回 0。
        """
        if key_path == "total_count":
            return stats.get("total_count", 0)
        if key_path == "total_amount":
            return stats.get("total_amount", 0.0)

        categories = stats.get("categories", {})
        parts = key_path.split(".")
        if len(parts) == 2:
            category_name, metric = parts
            category_data = categories.get(category_name, {})
            return category_data.get(metric, 0 if metric == "count" else 0.0)

        if len(parts) == 3:
            category_name, sub_name, metric = parts
            category_data = categories.get(category_name, {})
            sub_data = category_data.get("sub_categories", {}).get(sub_name, {})
            return sub_data.get(metric, 0 if metric == "count" else 0.0)

        return 0

    def write_summary(self, stats: dict[str, Any]) -> None:
        """
        将统计结果写入指定单元格。
        """
        if self.worksheet is None:
            raise RuntimeError("工作表未初始化，请先调用 prepare_sheet。")

        for key_path, cell in self.SUMMARY_CELL_MAPPING.items():
            value = self._extract_value(stats, key_path)
            self.worksheet[cell] = value

            if key_path.endswith(".amount") or key_path == "total_amount":
                self.worksheet[cell].number_format = "0.00"

    def _build_output_file_path(self, output_path: Optional[Path] = None) -> Path:
        """
        生成输出文件路径，文件名固定为 `报表_YYYY-MM-DD.xlsx`。
        """
        report_date = DateConfig.default_report_date_str()
        file_name = f"报表_{report_date}.xlsx"

        if output_path is None:
            target_dir = EXCEL_OUTPUT_DIR
        else:
            path_obj = Path(output_path)
            target_dir = path_obj if path_obj.suffix == "" else path_obj.parent

        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / file_name

    def save(self, output_path: Optional[Path] = None) -> Path:
        """
        保存 Excel 文件，不修改原模板。
        """
        if self.workbook is None:
            raise RuntimeError("工作簿未初始化，无法保存。")

        target_file = self._build_output_file_path(output_path)
        self.workbook.save(target_file)
        return target_file

    def export(
        self,
        df: dict[str, Any],
        output_path: Optional[Path] = None,
        sheet_name: str = "",
    ) -> Path:
        """
        执行完整 Excel 导出流程并返回新文件路径。
        """
        self.load_template()
        self.prepare_sheet(sheet_name=sheet_name)
        self.write_summary(stats=df)
        return self.save(output_path=output_path)

    def export_business_finance_metrics(
        self,
        metrics: dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        输出业务/财务提取结果为独立 Excel 报表。
        """
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "业务财务汇总"

        report_date = str(metrics.get("report_date", DateConfig.default_report_date_str()))
        headers = [
            "统计日期",
            "支付买家数",
            "支付金额",
            "支付子订单数",
            "交易赔付",
            "淘宝天猫跨境服务增值费",
            "推广费用",
        ]
        values = [
            report_date,
            metrics.get("payment_buyer_count", 0),
            metrics.get("payment_amount", 0.0),
            metrics.get("payment_sub_order_count", 0),
            metrics.get("trade_compensation", 0.0),
            metrics.get("cross_border_value_added_fee", 0.0),
            metrics.get("promotion_fee", 0.0),
        ]

        for column_index, header in enumerate(headers, start=1):
            worksheet.cell(row=1, column=column_index, value=header)
        for column_index, value in enumerate(values, start=1):
            cell = worksheet.cell(row=2, column=column_index, value=value)
            if column_index in (3, 5, 6, 7):
                cell.number_format = "0.00"
            if column_index in (2, 4):
                cell.number_format = "0"

        worksheet.column_dimensions["A"].width = 14
        worksheet.column_dimensions["B"].width = 12
        worksheet.column_dimensions["C"].width = 14
        worksheet.column_dimensions["D"].width = 14
        worksheet.column_dimensions["E"].width = 12
        worksheet.column_dimensions["F"].width = 26
        worksheet.column_dimensions["G"].width = 12

        if output_path is None:
            target_dir = Path.home() / "Desktop"
        else:
            path_obj = Path(output_path)
            target_dir = path_obj if path_obj.suffix == "" else path_obj.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"业务财务汇总_{report_date}.xlsx"
        target_file = target_dir / filename
        workbook.save(target_file)
        return target_file
