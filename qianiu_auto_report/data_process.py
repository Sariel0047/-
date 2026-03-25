"""
数据处理模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from qianiu_auto_report.utils import get_latest_file, get_previous_date


class DataProcessor:
    """
    数据清洗与整理处理器。
    """

    SUPPORTED_EXCEL_SUFFIXES = (".xlsx", ".xls", ".xlsm")
    DATE_COLUMN_CANDIDATES = (
        "申请时间",
        "售后申请时间",
        "创建时间",
        "申请日期",
        "日期",
        "时间",
    )
    AMOUNT_COLUMN_CANDIDATES = (
        "退款金额",
        "金额",
        "申请退款金额",
        "实退金额",
    )
    REFUND_TYPE_COLUMN_CANDIDATES = (
        "售后类型",
        "服务类型",
        "退款类型",
        "申请类型",
        "维权类型",
    )
    GOODS_STATUS_COLUMN_CANDIDATES = (
        "货物状态",
        "收货状态",
        "退货状态",
        "物流状态",
    )
    CATEGORY_STRUCTURE = {
        "已发货仅退款": ("未收到货", "已收到货"),
        "未发货仅退款": ("未发货",),
        "退货退款": ("已寄回",),
    }

    def __init__(self) -> None:
        self.raw_df: Optional[pd.DataFrame] = None
        self.processed_df: Optional[pd.DataFrame] = None
        self.latest_file_path: Optional[Path] = None
        self.date_column: Optional[str] = None
        self.amount_column: Optional[str] = None
        self.refund_type_column: Optional[str] = None
        self.goods_status_column: Optional[str] = None

    def _build_empty_summary(self) -> dict[str, Any]:
        """
        构建空统计结果。
        """
        categories: dict[str, Any] = {}
        for category, sub_categories in self.CATEGORY_STRUCTURE.items():
            categories[category] = {
                "count": 0,
                "amount": 0.0,
                "sub_categories": {
                    sub_name: {"count": 0, "amount": 0.0} for sub_name in sub_categories
                },
            }

        return {
            "total_count": 0,
            "total_amount": 0.0,
            "categories": categories,
        }

    def _find_column(self, df: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
        """
        在候选列名中查找实际存在的列。
        """
        for name in candidates:
            if name in df.columns:
                return name
        return None

    def _resolve_excel_file(self, input_path: Path) -> Path:
        """
        解析输入路径，并自动定位最新 Excel 文件。
        """
        if input_path.is_file():
            if input_path.suffix.lower() not in self.SUPPORTED_EXCEL_SUFFIXES:
                raise ValueError(f"不支持的文件格式：{input_path.suffix}")
            return input_path
        return get_latest_file(
            directory=input_path,
            suffixes=self.SUPPORTED_EXCEL_SUFFIXES,
            ignore_prefixes=("~$",),
            recursive=False,
        )

    def load_data(self, file_path: Path) -> pd.DataFrame:
        """
        读取原始数据。
        支持传入目录（自动读取最新 Excel）或单个 Excel 文件。
        """
        target_file = self._resolve_excel_file(Path(file_path))
        self.latest_file_path = target_file
        df = pd.read_excel(target_file)
        self.raw_df = df
        return df

    def validate_columns(self, df: pd.DataFrame) -> None:
        """
        校验必要字段。
        """
        self.date_column = self._find_column(df, self.DATE_COLUMN_CANDIDATES)
        self.amount_column = self._find_column(df, self.AMOUNT_COLUMN_CANDIDATES)
        self.refund_type_column = self._find_column(df, self.REFUND_TYPE_COLUMN_CANDIDATES)
        self.goods_status_column = self._find_column(df, self.GOODS_STATUS_COLUMN_CANDIDATES)

        if self.date_column is None:
            candidates_text = "、".join(self.DATE_COLUMN_CANDIDATES)
            raise ValueError(f"未找到日期列，候选列名：{candidates_text}")

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗原始数据。
        """
        cleaned = df.copy()
        cleaned.columns = [str(column).strip() for column in cleaned.columns]

        object_columns = cleaned.select_dtypes(include=["object"]).columns
        for column in object_columns:
            cleaned[column] = cleaned[column].where(
                cleaned[column].isna(),
                cleaned[column].astype(str).str.strip(),
            )

        return cleaned

    def _parse_amount(self, series: pd.Series) -> pd.Series:
        """
        将金额列标准化为浮点数。
        """
        cleaned = (
            series.fillna("")
            .astype(str)
            .str.replace(r"[^\d\.\-]", "", regex=True)
            .replace("", pd.NA)
        )
        return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)

    def _classify_row(self, refund_type: str, goods_status: str) -> tuple[Optional[str], Optional[str]]:
        """
        按分类规则识别一级/二级分类。
        """
        refund_text = str(refund_type or "").strip()
        status_text = str(goods_status or "").strip()
        combined_text = f"{refund_text}|{status_text}"

        if "未发货仅退款" in combined_text or "未发货" == status_text:
            return "未发货仅退款", "未发货"

        if "已发货仅退款" in combined_text:
            if "已收到货" in combined_text:
                return "已发货仅退款", "已收到货"
            if "未收到货" in combined_text:
                return "已发货仅退款", "未收到货"

        if "退货退款" in combined_text and "已寄回" in combined_text:
            return "退货退款", "已寄回"

        if "仅退款" in refund_text:
            if "未发货" in status_text:
                return "未发货仅退款", "未发货"
            if "已收到货" in status_text:
                return "已发货仅退款", "已收到货"
            if "未收到货" in status_text:
                return "已发货仅退款", "未收到货"

        if "已寄回" in status_text:
            return "退货退款", "已寄回"

        return None, None

    def transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        转换数据结构并筛选前一天数据。
        """
        transformed = df.copy()

        transformed["_parsed_date"] = pd.to_datetime(
            transformed[self.date_column],
            errors="coerce",
        )
        target_date = get_previous_date()
        transformed = transformed.loc[transformed["_parsed_date"].dt.date == target_date].copy()

        if transformed.empty:
            transformed["_amount"] = pd.Series(dtype="float64")
            transformed["_category"] = pd.Series(dtype="object")
            transformed["_sub_category"] = pd.Series(dtype="object")
            return transformed

        if self.amount_column and self.amount_column in transformed.columns:
            transformed["_amount"] = self._parse_amount(transformed[self.amount_column])
        else:
            transformed["_amount"] = 0.0

        if self.refund_type_column and self.refund_type_column in transformed.columns:
            refund_series = transformed[self.refund_type_column].fillna("").astype(str)
        else:
            refund_series = pd.Series("", index=transformed.index)

        if self.goods_status_column and self.goods_status_column in transformed.columns:
            status_series = transformed[self.goods_status_column].fillna("").astype(str)
        else:
            status_series = pd.Series("", index=transformed.index)

        category_pairs = [
            self._classify_row(refund_type=refund, goods_status=status)
            for refund, status in zip(refund_series, status_series)
        ]
        transformed["_category"] = [pair[0] for pair in category_pairs]
        transformed["_sub_category"] = [pair[1] for pair in category_pairs]
        return transformed

    def summarize_data(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        汇总统计数据，返回字典结果。
        """
        summary = self._build_empty_summary()
        if df.empty:
            return summary

        summary["total_count"] = int(len(df))
        summary["total_amount"] = round(float(df["_amount"].sum()), 2)

        for category_name, sub_categories in self.CATEGORY_STRUCTURE.items():
            category_df = df.loc[df["_category"] == category_name]
            summary["categories"][category_name]["count"] = int(len(category_df))
            summary["categories"][category_name]["amount"] = round(
                float(category_df["_amount"].sum()),
                2,
            )

            for sub_name in sub_categories:
                sub_df = category_df.loc[category_df["_sub_category"] == sub_name]
                summary["categories"][category_name]["sub_categories"][sub_name]["count"] = int(
                    len(sub_df)
                )
                summary["categories"][category_name]["sub_categories"][sub_name]["amount"] = round(
                    float(sub_df["_amount"].sum()),
                    2,
                )

        return summary

    def save_processed_data(self, df: pd.DataFrame, output_path: Path) -> None:
        """
        保存处理后的中间结果。
        """
        export_df = df.copy()
        if "_category" in export_df.columns:
            export_df["一级分类"] = export_df["_category"]
        if "_sub_category" in export_df.columns:
            export_df["二级分类"] = export_df["_sub_category"]
        if "_amount" in export_df.columns:
            export_df["标准化金额"] = export_df["_amount"]

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_df.to_excel(output_path, index=False)

    def process(self, input_path: Path, output_path: Optional[Path] = None) -> dict[str, Any]:
        """
        执行完整数据处理流程。
        """
        loaded_df = self.load_data(Path(input_path))
        cleaned_df = self.clean_data(loaded_df)
        if cleaned_df.empty:
            self.processed_df = cleaned_df
            if output_path is not None:
                self.save_processed_data(cleaned_df, Path(output_path))
            return self._build_empty_summary()

        self.validate_columns(cleaned_df)
        transformed_df = self.transform_data(cleaned_df)
        self.processed_df = transformed_df

        if output_path is not None:
            self.save_processed_data(transformed_df, Path(output_path))

        return self.summarize_data(transformed_df)
