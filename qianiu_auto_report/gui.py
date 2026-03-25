"""
Tkinter 图形界面模块。
"""

from __future__ import annotations

import traceback
from pathlib import Path
from threading import Thread
import tkinter as tk
from tkinter import scrolledtext, ttk

from qianiu_auto_report.config import (
    BrowserConfig,
    DateConfig,
    EXCEL_OUTPUT_DIR,
    ExportConfig,
    PROCESSED_OUTPUT_DIR,
)
from qianiu_auto_report.data_process import DataProcessor
from qianiu_auto_report.excel_writer import ExcelWriter
from qianiu_auto_report.web_export import WebExporter


class AppGUI:
    """
    主界面类。
    """

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.date_var = tk.StringVar(value=self._get_default_date())
        self.status_var = tk.StringVar(value="等待操作")
        self.attach_mode = BrowserConfig.ATTACH_TO_EXISTING_BROWSER

        self.open_login_button: ttk.Button | None = None
        self.continue_button: ttk.Button | None = None
        self.status_text: scrolledtext.ScrolledText | None = None

        self.web_exporter: WebExporter | None = None

        self._build_window()
        self._build_widgets()
        self._bind_events()

    def _get_default_date(self) -> str:
        """
        获取默认日期，默认值为前一天。
        """
        return DateConfig.default_report_date_str()

    def _build_window(self) -> None:
        """
        初始化主窗口配置。
        """
        self.root.title("千牛自动报表系统")
        self.root.geometry("620x420")
        self.root.resizable(False, False)
        self.root.configure(padx=20, pady=20)

    def _build_widgets(self) -> None:
        """
        创建界面组件。
        """
        title_label = ttk.Label(
            self.root,
            text="千牛自动报表系统",
            font=("Microsoft YaHei", 16, "bold"),
        )
        title_label.pack(anchor="center", pady=(0, 16))

        form_frame = ttk.Frame(self.root)
        form_frame.pack(fill="x", pady=(0, 12))

        date_label = ttk.Label(form_frame, text="报表日期：")
        date_label.pack(side="left")

        date_entry = ttk.Entry(
            form_frame,
            textvariable=self.date_var,
            width=18,
            state="readonly",
        )
        date_entry.pack(side="left", padx=(8, 12))

        download_label = ttk.Label(form_frame, text=f"下载目录：{Path(ExportConfig.DOWNLOAD_DIR)}")
        download_label.pack(side="left")

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", pady=(0, 12))

        open_button_text = (
            "1. 附着已打开浏览器"
            if self.attach_mode
            else "1. 打开登录页"
        )
        self.open_login_button = ttk.Button(
            button_frame,
            text=open_button_text,
            command=self.on_open_login_clicked,
        )
        self.open_login_button.pack(side="left")

        self.continue_button = ttk.Button(
            button_frame,
            text="2. 登录成功，继续执行",
            command=self.on_continue_clicked,
            state="disabled",
        )
        self.continue_button.pack(side="left", padx=(10, 0))

        status_label = ttk.Label(self.root, textvariable=self.status_var)
        status_label.pack(anchor="w", pady=(0, 8))

        self.status_text = scrolledtext.ScrolledText(
            self.root,
            width=76,
            height=14,
            wrap=tk.WORD,
            state="disabled",
        )
        self.status_text.pack(fill="both", expand=True)

        self.append_log("系统已启动。")
        self.append_log(f"默认报表日期：{self.date_var.get()}")
        if self.attach_mode:
            self.append_log("当前模式：仅附着已打开浏览器。")
            self.append_log(
                "请先启动 Chrome 远程调试并登录千牛页面，再点击【1. 附着已打开浏览器】。"
            )
            self.append_log(
                "系统会校验当前网址是否属于千牛域名，校验通过后你再点【2. 登录成功，继续执行】。"
            )
        else:
            self.append_log("请先点击【1. 打开登录页】，登录成功后点击【2. 登录成功，继续执行】。")
            self.append_log("若出现滑块失败，请关闭所有 Chrome 窗口后重试，并优先使用扫码登录。")

    def _bind_events(self) -> None:
        """
        绑定事件。
        """
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        """
        关闭窗口时释放资源。
        """
        try:
            if self.web_exporter is not None:
                self.web_exporter.close()
        finally:
            self.root.destroy()

    def _set_buttons_state(self, open_login_state: str, continue_state: str) -> None:
        """
        统一设置按钮状态。
        """
        if self.open_login_button is not None:
            self.open_login_button.config(state=open_login_state)
        if self.continue_button is not None:
            self.continue_button.config(state=continue_state)

    def on_open_login_clicked(self) -> None:
        """
        点击“打开登录页”。
        """
        if self.attach_mode:
            self.update_status("正在附着已打开浏览器...")
            self.append_log("正在附着已打开浏览器，并校验页面网址...")
        else:
            self.update_status("正在打开登录页...")
            self.append_log("正在启动浏览器并打开页面...")
        self._set_buttons_state(open_login_state="disabled", continue_state="disabled")

        worker = Thread(target=self._open_login_page_worker, daemon=True)
        worker.start()

    def _open_login_page_worker(self) -> None:
        """
        后台打开登录页，不阻塞界面。
        """
        try:
            download_dir = Path(ExportConfig.DOWNLOAD_DIR)
            download_dir.mkdir(parents=True, exist_ok=True)

            if self.web_exporter is not None:
                self.web_exporter.close()
            self.web_exporter = WebExporter()
            self.web_exporter.init_driver(download_dir=download_dir)
            self.web_exporter.open_login_page()

            current_url = self.web_exporter.get_current_url()
            if self.attach_mode:
                self.root.after(0, self.update_status, "附着成功，请点击“登录成功，继续执行”")
                self.root.after(0, self.append_log, "已附着浏览器，网址校验通过。")
                self.root.after(0, self.append_log, f"当前页面：{current_url}")
            else:
                self.root.after(0, self.update_status, "请手动登录后点击“登录成功，继续执行”")
                self.root.after(0, self.append_log, "浏览器已打开，请先完成登录。")
                self.root.after(0, self.append_log, f"当前页面：{current_url}")
            self.root.after(0, self._set_buttons_state, "disabled", "normal")
        except Exception:
            error_text = traceback.format_exc().strip()
            failed_status = "附着浏览器失败" if self.attach_mode else "打开登录页失败"
            self.root.after(0, self.update_status, failed_status)
            self.root.after(0, self.append_log, error_text)
            self.root.after(0, self._set_buttons_state, "normal", "disabled")

    def on_continue_clicked(self) -> None:
        """
        点击“登录成功，继续执行”。
        """
        if self.web_exporter is None:
            self.update_status("请先打开登录页")
            self.append_log("尚未初始化浏览器，请先点击【1. 打开登录页】。")
            return

        self.update_status("正在执行自动化流程...")
        self.append_log("检测到你已确认登录，系统开始接管执行。")
        self._set_buttons_state(open_login_state="disabled", continue_state="disabled")

        worker = Thread(target=self._run_after_login_worker, daemon=True)
        worker.start()

    def _run_after_login_worker(self) -> None:
        """
        登录确认后执行导出、处理、写表。
        """
        try:
            assert self.web_exporter is not None
            download_dir = Path(ExportConfig.DOWNLOAD_DIR)
            processed_path = PROCESSED_OUTPUT_DIR / "processed_report.xlsx"

            if ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
                metrics = self.web_exporter.collect_business_finance_metrics(download_dir=download_dir)
                exported_file = None
                self.root.after(0, self.append_log, "已跳过：退款管理网页自动化步骤。")
                self.root.after(
                    0,
                    self.append_log,
                    (
                        "提取结果："
                        f"支付买家数={metrics.get('payment_buyer_count')}，"
                        f"支付金额={metrics.get('payment_amount')}，"
                        f"支付子订单数={metrics.get('payment_sub_order_count')}，"
                        f"交易赔付={metrics.get('trade_compensation')}，"
                        f"淘宝天猫跨境服务增值费={metrics.get('cross_border_value_added_fee')}"
                    ),
                )
            else:
                metrics = None
                exported_file = self.web_exporter.export_after_login(download_dir=download_dir)
                self.root.after(0, self.append_log, f"导出文件：{exported_file}")

            if ExportConfig.SKIP_DATA_PROCESS or ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
                summary = None
                if ExportConfig.SKIP_DATA_PROCESS:
                    self.root.after(0, self.append_log, "已跳过：数据处理步骤。")
            else:
                if exported_file is None:
                    raise RuntimeError("数据处理已开启，但未获取到导出文件。")
                processor = DataProcessor()
                summary = processor.process(input_path=exported_file, output_path=processed_path)

            if ExportConfig.SKIP_EXCEL_WRITE:
                report_file = None
                self.root.after(0, self.append_log, "已跳过：Excel写入步骤。")
            else:
                writer = ExcelWriter()
                if ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
                    if metrics is None:
                        raise RuntimeError("业务财务提取结果为空，无法写入 Excel。")
                    report_file = writer.export_business_finance_metrics(
                        metrics=metrics,
                        output_path=Path.home() / "Desktop",
                    )
                else:
                    if summary is None:
                        raise RuntimeError("Excel写入已开启，但未获取到处理结果。")
                    report_file = writer.export(df=summary, output_path=EXCEL_OUTPUT_DIR)

            self.root.after(0, self.update_status, "完成")
            if report_file is not None:
                self.root.after(0, self.append_log, f"报表生成成功：{report_file}")
            else:
                self.root.after(0, self.append_log, "执行成功（简化流程）。")
            self.root.after(0, self._set_buttons_state, "normal", "disabled")
        except Exception:
            error_text = traceback.format_exc().strip()
            self.root.after(0, self.update_status, "执行失败")
            self.root.after(0, self.append_log, error_text)
            self.root.after(0, self._set_buttons_state, "normal", "disabled")
        finally:
            try:
                if self.web_exporter is not None:
                    self.web_exporter.close()
            finally:
                self.web_exporter = None

    def update_status(self, message: str) -> None:
        """
        更新状态显示。
        """
        self.status_var.set(message)

    def append_log(self, message: str) -> None:
        """
        追加状态文本内容。
        """
        if self.status_text is None:
            return

        self.status_text.config(state="normal")
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state="disabled")

    def run(self) -> None:
        """
        启动 GUI 主循环。
        """
        self.root.mainloop()


if __name__ == "__main__":
    AppGUI().run()
