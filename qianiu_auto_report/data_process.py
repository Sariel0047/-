"""
数据处理模块。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Any, Optional

import pandas as pd

from qianiu_auto_report.utils import get_latest_file, get_previous_date


class DataProcessor:
    """
    数据清洗与整理处理器。
    """

    SUPPORTED_EXCEL_SUFFIXES = (".xlsx", ".xls", ".xlsm")
    DATE_COLUMN_CANDIDATES = (
        "退款完结时间",
        "退款成功时间",
        "完结时间",
        "申请时间",
        "售后申请时间",
        "创建时间",
        "申请日期",
        "日期",
        "时间",
    )
    AMOUNT_COLUMN_CANDIDATES = (
        "退款总额",
        "退款总金额",
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
    DOUYIN_REFUND_DETAIL_SHEET_NAME = "本店数据"
    DOUYIN_AFTER_SALE_TYPE_COLUMN = "售后类型"
    DOUYIN_AFTER_SALE_AMOUNT_COLUMN = "退商品金额（元）"
    DOUYIN_AFTER_SALE_FINISHED_TIME_COLUMN = "售后完结时间"
    DOUYIN_REFUND_METRIC_COLUMNS = {
        "refund_total_order_count": "全部退款阶段-退款订单数",
        "refund_total_amount": "全部退款阶段-退款金额",
        "pre_shipment_refund_order_count": "发货前退款阶段-退款订单数",
        "pre_shipment_refund_amount": "发货前退款阶段-退款金额",
        "unreceived_refund_order_count": "未收货退款阶段-退款订单数",
        "unreceived_refund_amount": "未收货退款阶段-退款金额",
        "received_refund_order_count": "已收货退款阶段-退款订单数",
        "received_refund_amount": "已收货退款阶段-退款金额",
        "return_refund_order_count": "已收货退货退款阶段-退款订单数",
        "return_refund_amount": "已收货退货退款阶段-退款金额",
    }
    DOUYIN_ZERO_REFUND_METRICS = {
        "refund_total_order_count": 0,
        "refund_total_amount": 0.0,
        "pre_shipment_refund_order_count": 0,
        "pre_shipment_refund_amount": 0.0,
        "unreceived_refund_order_count": 0,
        "unreceived_refund_amount": 0.0,
        "received_refund_order_count": 0,
        "received_refund_amount": 0.0,
        "return_refund_order_count": 0,
        "return_refund_amount": 0.0,
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

    def _build_zero_douyin_refund_summary(self, report_date: str = "") -> dict[str, Any]:
        """
        构建抖音退款分析无数据时的 0 汇总。
        """
        summary = self._build_empty_summary()
        summary["douyin_refund_metrics"] = dict(self.DOUYIN_ZERO_REFUND_METRICS)
        if report_date:
            summary["report_date"] = report_date
        return summary

    @staticmethod
    def _extract_report_date_from_title(title: str) -> str:
        """
        从抖音退款明细标题/文件名中提取日期，支持 2026_05_13 / 2026-05-13 / 2026年05月13日。
        """
        text = str(title or "")
        patterns = (
            r"(20\d{2})[_\-.年/](\d{1,2})[_\-.月/](\d{1,2})",
            r"(20\d{2})(\d{2})(\d{2})",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                try:
                    parsed = date(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                except ValueError:
                    continue
                return parsed.strftime("%Y-%m-%d")
        return ""

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

        # 按用户业务口径：优先由“货物状态”直接归类
        if "未发货" in status_text:
            return "未发货仅退款", "未发货"
        if "已寄回" in status_text:
            return "退货退款", "已寄回"
        if "未收到货" in status_text:
            return "已发货仅退款", "未收到货"
        if "已收到货" in status_text:
            return "已发货仅退款", "已收到货"

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

    @staticmethod
    def _normalize_column_name(name: Any) -> str:
        """
        标准化列名，去掉多余空白。
        """
        return re.sub(r"\s+", "", str(name or "")).strip()

    def _find_normalized_column(self, df: pd.DataFrame, target_name: str) -> Optional[str]:
        """
        按标准化列名查找真实列名。
        """
        normalized_target = self._normalize_column_name(target_name)
        for column in df.columns:
            if self._normalize_column_name(column) == normalized_target:
                return str(column)
        return None

    def _sum_numeric_column(self, df: pd.DataFrame, column_name: str) -> float:
        """
        汇总指定列的数值，兼容金额符号与千分位。
        """
        if column_name not in df.columns:
            return 0.0
        values = self._parse_amount(df[column_name])
        return round(float(values.sum()), 2)

    def _sum_count_column(self, df: pd.DataFrame, column_name: str) -> int:
        """
        汇总指定列的订单数。
        """
        return int(round(self._sum_numeric_column(df=df, column_name=column_name)))

    def summarize_douyin_refund_analysis(self, input_path: Path) -> dict[str, Any]:
        """
        汇总抖音电商罗盘“退款分析 -> 下载明细”文件中的本店数据。
        """
        target_file = self._resolve_excel_file(Path(input_path))
        excel_file = pd.ExcelFile(target_file)
        if self.DOUYIN_REFUND_DETAIL_SHEET_NAME not in excel_file.sheet_names:
            sheets = "、".join(excel_file.sheet_names)
            raise ValueError(
                f"未找到抖音退款分析工作表【{self.DOUYIN_REFUND_DETAIL_SHEET_NAME}】，当前工作表：{sheets}"
            )

        df = pd.read_excel(target_file, sheet_name=self.DOUYIN_REFUND_DETAIL_SHEET_NAME)
        df.columns = [str(column).strip() for column in df.columns]
        report_date = self._extract_report_date_from_title(target_file.stem)
        date_column = self._find_normalized_column(df, "日期")
        if not report_date and date_column is not None:
            parsed_dates = pd.to_datetime(df[date_column], errors="coerce")
            valid_dates = parsed_dates.dropna()
            if not valid_dates.empty:
                report_date = valid_dates.dt.date.max().strftime("%Y-%m-%d")

        resolved_columns: dict[str, str] = {}
        missing_columns: list[str] = []
        for metric_key, expected_column in self.DOUYIN_REFUND_METRIC_COLUMNS.items():
            actual_column = self._find_normalized_column(df, expected_column)
            if actual_column is None:
                missing_columns.append(expected_column)
            else:
                resolved_columns[metric_key] = actual_column

        if missing_columns:
            all_metric_columns_missing = len(missing_columns) == len(self.DOUYIN_REFUND_METRIC_COLUMNS)
            if all_metric_columns_missing or df.empty:
                return self._build_zero_douyin_refund_summary(report_date=report_date)
            raise ValueError(f"抖音退款分析明细缺少列：{'、'.join(missing_columns)}")

        metrics = {
            "refund_total_order_count": self._sum_count_column(
                df, resolved_columns["refund_total_order_count"]
            ),
            "refund_total_amount": self._sum_numeric_column(
                df, resolved_columns["refund_total_amount"]
            ),
            "pre_shipment_refund_order_count": self._sum_count_column(
                df, resolved_columns["pre_shipment_refund_order_count"]
            ),
            "pre_shipment_refund_amount": self._sum_numeric_column(
                df, resolved_columns["pre_shipment_refund_amount"]
            ),
            "unreceived_refund_order_count": self._sum_count_column(
                df, resolved_columns["unreceived_refund_order_count"]
            ),
            "unreceived_refund_amount": self._sum_numeric_column(
                df, resolved_columns["unreceived_refund_amount"]
            ),
            "received_refund_order_count": self._sum_count_column(
                df, resolved_columns["received_refund_order_count"]
            ),
            "received_refund_amount": self._sum_numeric_column(
                df, resolved_columns["received_refund_amount"]
            ),
            "return_refund_order_count": self._sum_count_column(
                df, resolved_columns["return_refund_order_count"]
            ),
            "return_refund_amount": self._sum_numeric_column(
                df, resolved_columns["return_refund_amount"]
            ),
        }

        summary = self._build_empty_summary()
        summary["total_count"] = metrics["refund_total_order_count"]
        summary["total_amount"] = metrics["refund_total_amount"]
        summary["douyin_refund_metrics"] = metrics
        if report_date:
            summary["report_date"] = report_date

        summary["categories"]["未发货仅退款"]["count"] = metrics[
            "pre_shipment_refund_order_count"
        ]
        summary["categories"]["未发货仅退款"]["amount"] = metrics["pre_shipment_refund_amount"]
        summary["categories"]["未发货仅退款"]["sub_categories"]["未发货"]["count"] = metrics[
            "pre_shipment_refund_order_count"
        ]
        summary["categories"]["未发货仅退款"]["sub_categories"]["未发货"]["amount"] = metrics[
            "pre_shipment_refund_amount"
        ]

        shipped_count = (
            metrics["unreceived_refund_order_count"] + metrics["received_refund_order_count"]
        )
        shipped_amount = round(
            metrics["unreceived_refund_amount"] + metrics["received_refund_amount"],
            2,
        )
        summary["categories"]["已发货仅退款"]["count"] = shipped_count
        summary["categories"]["已发货仅退款"]["amount"] = shipped_amount
        summary["categories"]["已发货仅退款"]["sub_categories"]["未收到货"]["count"] = metrics[
            "unreceived_refund_order_count"
        ]
        summary["categories"]["已发货仅退款"]["sub_categories"]["未收到货"]["amount"] = metrics[
            "unreceived_refund_amount"
        ]
        summary["categories"]["已发货仅退款"]["sub_categories"]["已收到货"]["count"] = metrics[
            "received_refund_order_count"
        ]
        summary["categories"]["已发货仅退款"]["sub_categories"]["已收到货"]["amount"] = metrics[
            "received_refund_amount"
        ]

        summary["categories"]["退货退款"]["count"] = metrics["return_refund_order_count"]
        summary["categories"]["退货退款"]["amount"] = metrics["return_refund_amount"]
        summary["categories"]["退货退款"]["sub_categories"]["已寄回"]["count"] = metrics[
            "return_refund_order_count"
        ]
        summary["categories"]["退货退款"]["sub_categories"]["已寄回"]["amount"] = metrics[
            "return_refund_amount"
        ]
        return summary

    def summarize_douyin_after_sale_orders(self, input_path: Path) -> dict[str, Any]:
        """
        汇总抖店“售后工作台 -> 导出”的售后单。
        """
        target_file = self._resolve_excel_file(Path(input_path))
        df = pd.read_excel(target_file)
        df.columns = [str(column).strip() for column in df.columns]

        type_column = self._find_normalized_column(df, self.DOUYIN_AFTER_SALE_TYPE_COLUMN)
        amount_column = self._find_normalized_column(df, self.DOUYIN_AFTER_SALE_AMOUNT_COLUMN)
        if type_column is None or amount_column is None:
            missing_columns = []
            if type_column is None:
                missing_columns.append(self.DOUYIN_AFTER_SALE_TYPE_COLUMN)
            if amount_column is None:
                missing_columns.append(self.DOUYIN_AFTER_SALE_AMOUNT_COLUMN)
            raise ValueError(f"抖音售后单缺少列：{'、'.join(missing_columns)}")

        finished_time_column = self._find_normalized_column(
            df, self.DOUYIN_AFTER_SALE_FINISHED_TIME_COLUMN
        )
        report_date = get_previous_date().strftime("%Y-%m-%d")
        if finished_time_column is not None:
            parsed_dates = pd.to_datetime(df[finished_time_column], errors="coerce")
            valid_dates = parsed_dates.dropna()
            if not valid_dates.empty:
                report_date = valid_dates.dt.date.max().strftime("%Y-%m-%d")

        type_series = df[type_column].fillna("").astype(str).str.strip()
        amount_series = self._parse_amount(df[amount_column])

        def count_amount(type_name: str) -> tuple[int, float]:
            mask = type_series == type_name
            return int(mask.sum()), round(float(amount_series.loc[mask].sum()), 2)

        return_count, return_amount = count_amount("退货退款")
        shipped_count, shipped_amount = count_amount("已发货退款")
        unshipped_count, unshipped_amount = count_amount("未发货退款")
        total_count = int(return_count + shipped_count + unshipped_count)
        total_amount = round(float(return_amount + shipped_amount + unshipped_amount), 2)

        metrics = {
            "refund_total_order_count": total_count,
            "refund_total_amount": total_amount,
            "pre_shipment_refund_order_count": unshipped_count,
            "pre_shipment_refund_amount": unshipped_amount,
            "unreceived_refund_order_count": 0,
            "unreceived_refund_amount": 0.0,
            "received_refund_order_count": shipped_count,
            "received_refund_amount": shipped_amount,
            "return_refund_order_count": return_count,
            "return_refund_amount": return_amount,
        }

        summary = self._build_empty_summary()
        summary["total_count"] = total_count
        summary["total_amount"] = total_amount
        summary["douyin_refund_metrics"] = metrics
        if report_date:
            summary["report_date"] = report_date

        summary["categories"]["未发货仅退款"]["count"] = unshipped_count
        summary["categories"]["未发货仅退款"]["amount"] = unshipped_amount
        summary["categories"]["未发货仅退款"]["sub_categories"]["未发货"]["count"] = unshipped_count
        summary["categories"]["未发货仅退款"]["sub_categories"]["未发货"]["amount"] = unshipped_amount

        summary["categories"]["已发货仅退款"]["count"] = shipped_count
        summary["categories"]["已发货仅退款"]["amount"] = shipped_amount
        summary["categories"]["已发货仅退款"]["sub_categories"]["已收到货"]["count"] = shipped_count
        summary["categories"]["已发货仅退款"]["sub_categories"]["已收到货"]["amount"] = shipped_amount

        summary["categories"]["退货退款"]["count"] = return_count
        summary["categories"]["退货退款"]["amount"] = return_amount
        summary["categories"]["退货退款"]["sub_categories"]["已寄回"]["count"] = return_count
        summary["categories"]["退货退款"]["sub_categories"]["已寄回"]["amount"] = return_amount
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
