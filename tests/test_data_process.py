"""
`data_process.py` 测试骨架。
"""

from __future__ import annotations

from datetime import date

from openpyxl import Workbook
import pandas as pd

import qianiu_auto_report.data_process as data_process_module
from qianiu_auto_report.data_process import DataProcessor


def test_placeholder() -> None:
    """
    占位测试。
    """
    pass


def test_validate_columns_prefers_refund_finished_time_column() -> None:
    """
    同时存在申请时间与退款完结时间时，应优先按退款完结时间筛选。
    """
    df = pd.DataFrame(
        {
            "申请时间": ["2026-03-30 08:00:00"],
            "退款完结时间": ["2026-03-31 09:00:00"],
            "货物状态": ["未发货"],
            "退款总额": [12.5],
        }
    )
    processor = DataProcessor()
    processor.validate_columns(df)
    assert processor.date_column == "退款完结时间"


def test_summarize_refund_metrics_by_goods_status_and_finished_date(monkeypatch) -> None:
    """
    按“退款完结时间=昨天”筛选后，统计三类货物状态的数量与退款总额。
    """
    monkeypatch.setattr(
        data_process_module,
        "get_previous_date",
        lambda: date(2026, 3, 31),
    )

    raw_df = pd.DataFrame(
        {
            "退款完结时间": [
                "2026-03-31 08:00:00",
                "2026-03-31 09:00:00",
                "2026-03-31 10:00:00",
                "2026-03-31 11:00:00",
                "2026-03-30 12:00:00",
            ],
            "货物状态": [
                "未收到货",
                "已收到货",
                "未发货",
                "已寄回",
                "未收到货",
            ],
            "退款总额": [
                "¥10.00",
                "20.00",
                "30",
                "40",
                "999",
            ],
            "售后类型": [
                "其他",
                "其他",
                "其他",
                "其他",
                "其他",
            ],
        }
    )

    processor = DataProcessor()
    cleaned_df = processor.clean_data(raw_df)
    processor.validate_columns(cleaned_df)
    transformed_df = processor.transform_data(cleaned_df)
    summary = processor.summarize_data(transformed_df)

    shipped_only_refund = summary["categories"]["已发货仅退款"]
    unshipped_only_refund = summary["categories"]["未发货仅退款"]
    return_refund = summary["categories"]["退货退款"]

    assert shipped_only_refund["count"] == 2
    assert shipped_only_refund["amount"] == 30.0

    assert unshipped_only_refund["count"] == 1
    assert unshipped_only_refund["amount"] == 30.0

    assert return_refund["count"] == 1
    assert return_refund["amount"] == 40.0


def test_summarize_douyin_refund_analysis_detail_by_stage_columns(tmp_path) -> None:
    """
    抖音罗盘退款分析明细应按“本店数据”阶段列求和。
    """
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "本店数据"
    worksheet.append(
        [
            "日期",
            "退款口径",
            "售卖类型",
            "载体",
            "全部退款阶段-退款人数",
            "全部退款阶段-退款订单数",
            "全部退款阶段-退款金额",
            "全部退款阶段-退款率",
            "发货前退款阶段-退款人数",
            "发货前退款阶段-退款订单数",
            "发货前退款阶段-退款金额",
            "发货前退款阶段-退款率",
            "未收货退款阶段-退款人数",
            "未收货退款阶段-退款订单数",
            "未收货退款阶段-退款金额",
            "未收货退款阶段-退款率",
            "已收货退款阶段-退款人数",
            "已收货退款阶段-退款订单数",
            "已收货退款阶段-退款金额",
            "已收货退款阶段-退款率",
            "已收货退货退款阶段-退款人数",
            "已收货退货退款阶段-退款订单数",
            "已收货退货退款阶段-退款金额",
            "已收货退货退款阶段-退款率",
        ]
    )
    worksheet.append(
        [
            "2026/05/13",
            "订单支付时间",
            "自营",
            "商品卡",
            10,
            11,
            "¥100.50",
            "10%",
            8,
            9,
            "80.25",
            "8%",
            1,
            2,
            "20",
            "2%",
            3,
            4,
            "40",
            "4%",
            5,
            6,
            "60",
            "6%",
        ]
    )
    worksheet.append(
        [
            "2026/05/13",
            "订单支付时间",
            "合作",
            "短视频",
            20,
            21,
            200,
            "20%",
            18,
            19,
            180,
            "18%",
            11,
            12,
            120,
            "12%",
            13,
            14,
            140,
            "14%",
            15,
            16,
            160,
            "16%",
        ]
    )
    input_file = tmp_path / "douyin_refund.xlsx"
    workbook.save(input_file)

    summary = DataProcessor().summarize_douyin_refund_analysis(input_file)
    refund_metrics = summary["douyin_refund_metrics"]

    assert summary["report_date"] == "2026-05-13"
    assert refund_metrics["refund_total_order_count"] == 32
    assert refund_metrics["refund_total_amount"] == 300.5
    assert refund_metrics["pre_shipment_refund_order_count"] == 28
    assert refund_metrics["pre_shipment_refund_amount"] == 260.25
    assert refund_metrics["unreceived_refund_order_count"] == 14
    assert refund_metrics["unreceived_refund_amount"] == 140.0
    assert refund_metrics["received_refund_order_count"] == 18
    assert refund_metrics["received_refund_amount"] == 180.0
    assert refund_metrics["return_refund_order_count"] == 22
    assert refund_metrics["return_refund_amount"] == 220.0


def test_summarize_douyin_refund_analysis_empty_detail_defaults_to_zero(tmp_path) -> None:
    """
    抖音退款分析明细无数据时，缺少阶段列也应按 0 汇总，而不是中断流程。
    """
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "本店数据"
    worksheet.append(["暂无数据"])
    input_file = tmp_path / "empty_douyin_refund.xlsx"
    workbook.save(input_file)

    summary = DataProcessor().summarize_douyin_refund_analysis(input_file)
    refund_metrics = summary["douyin_refund_metrics"]

    assert refund_metrics == {
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
    assert summary["total_count"] == 0
    assert summary["total_amount"] == 0.0


def test_summarize_douyin_refund_analysis_uses_title_date_when_empty(tmp_path) -> None:
    """
    抖音报表日期应以退款明细文件标题中的日期为准，哪怕明细无数据。
    """
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "本店数据"
    worksheet.append(["暂无数据"])
    input_file = tmp_path / "抖音电商罗盘-退款分析-2026_05_13.xlsx"
    workbook.save(input_file)

    summary = DataProcessor().summarize_douyin_refund_analysis(input_file)

    assert summary["report_date"] == "2026-05-13"
    assert summary["douyin_refund_metrics"]["refund_total_order_count"] == 0


def test_summarize_douyin_after_sale_orders_by_after_sale_type(tmp_path) -> None:
    """
    抖音售后工作台导出的售后单应按“售后类型”和“退商品金额（元）”汇总三类退款。
    """
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(
        [
            "售后单号",
            "商品发货状态",
            "售后类型",
            "退商品金额（元）",
            "售后状态",
            "售后完结时间",
        ]
    )
    worksheet.append(["A001", "1/1已发货", "退货退款", "159", "同意退款，退款成功", "2026-05-16 15:03:52"])
    worksheet.append(["A002", "1/1已发货", "已发货退款", "¥89.50", "同意退款，退款成功", "2026-05-16 18:00:00"])
    worksheet.append(["A003", "未发货", "未发货退款", "100.25", "同意退款，退款成功", "2026-05-16 20:00:00"])
    worksheet.append(["A004", "未发货", "未发货退款", "-", "同意退款，退款成功", "2026-05-16 21:00:00"])
    input_file = tmp_path / "售后单-2026-05-18 00_34_04.xlsx"
    workbook.save(input_file)

    summary = DataProcessor().summarize_douyin_after_sale_orders(input_file)
    refund_metrics = summary["douyin_refund_metrics"]

    assert summary["report_date"] == "2026-05-16"
    assert refund_metrics["refund_total_order_count"] == 4
    assert refund_metrics["refund_total_amount"] == 348.75
    assert refund_metrics["pre_shipment_refund_order_count"] == 2
    assert refund_metrics["pre_shipment_refund_amount"] == 100.25
    assert refund_metrics["received_refund_order_count"] == 1
    assert refund_metrics["received_refund_amount"] == 89.5
    assert refund_metrics["return_refund_order_count"] == 1
    assert refund_metrics["return_refund_amount"] == 159.0

    assert summary["categories"]["未发货仅退款"]["count"] == 2
    assert summary["categories"]["未发货仅退款"]["amount"] == 100.25
    assert summary["categories"]["已发货仅退款"]["count"] == 1
    assert summary["categories"]["已发货仅退款"]["amount"] == 89.5
    assert summary["categories"]["退货退款"]["count"] == 1
    assert summary["categories"]["退货退款"]["amount"] == 159.0


def test_summarize_douyin_after_sale_orders_empty_uses_previous_date(
    tmp_path,
    monkeypatch,
) -> None:
    """
    售后单文件名是下载时间；空表时统计日期应按“昨日”，不能误用文件名日期。
    """
    monkeypatch.setattr(
        data_process_module,
        "get_previous_date",
        lambda: date(2026, 5, 17),
    )
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["售后类型", "退商品金额（元）", "售后完结时间"])
    input_file = tmp_path / "售后单-2026-05-18 00_34_04.xlsx"
    workbook.save(input_file)

    summary = DataProcessor().summarize_douyin_after_sale_orders(input_file)

    assert summary["report_date"] == "2026-05-17"
    assert summary["douyin_refund_metrics"]["refund_total_order_count"] == 0
