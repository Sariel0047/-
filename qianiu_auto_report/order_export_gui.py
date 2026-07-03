"""
已卖出宝贝订单导出独立窗口。
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from threading import Thread
import tkinter as tk
from tkinter import scrolledtext, ttk

from qianiu_auto_report.browser_runtime import summarize_technical_error
from qianiu_auto_report.config import BrowserConfig, DateConfig, ExportConfig
from qianiu_auto_report.data_process import DataProcessor
from qianiu_auto_report.gui_support import build_work_browser_command, format_output_dir_label
from qianiu_auto_report.gui_state import friendly_error_message
from qianiu_auto_report.sold_order_exporter import SoldOrderExporter


class OrderExportWindow:
    """
    独立的“已卖出宝贝订单导出”窗口。
    """

    BG = "#F3F6FB"
    CARD_BG = "#FFFFFF"
    BORDER = "#D9E2EF"
    TEXT = "#0F172A"
    MUTED = "#64748B"
    PRIMARY = "#2563EB"
    SUCCESS = "#0F766E"
    ERROR = "#B91C1C"

    def __init__(self, parent: tk.Tk | tk.Toplevel) -> None:
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.font_family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        self.output_dir = Path(ExportConfig.DOWNLOAD_DIR).expanduser()
        default_date = DateConfig.default_report_date_str()

        self.product_ids_var = tk.StringVar(value="")
        self.start_date_var = tk.StringVar(value=default_date)
        self.end_date_var = tk.StringVar(value=default_date)
        self.status_var = tk.StringVar(value="请先打开 9222 工作浏览器并登录千牛/天猫商家后台。")

        self.open_browser_button: ttk.Button | None = None
        self.start_export_button: ttk.Button | None = None
        self.open_output_button: ttk.Button | None = None
        self.close_button: ttk.Button | None = None
        self.progressbar: ttk.Progressbar | None = None
        self.product_ids_text: tk.Text | None = None
        self.log_text: scrolledtext.ScrolledText | None = None

        self.exporter: SoldOrderExporter | None = None
        self.running = False

        self._build_window()
        self._configure_styles()
        self._build_widgets()
        self._bind_events()

    def _build_window(self) -> None:
        self.window.title("已卖出宝贝订单导出")
        self.window.geometry("820x660")
        self.window.minsize(760, 600)
        self.window.resizable(True, True)
        self.window.configure(bg=self.BG)
        self.window.transient(self.parent)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(self.font_family, 10))
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("TEntry", fieldbackground=self.CARD_BG, padding=(8, 6))
        style.configure("TButton", padding=(14, 9), relief="flat")
        style.configure(
            "OrderPrimary.TButton",
            background=self.PRIMARY,
            foreground="white",
            padding=(16, 11),
            font=(self.font_family, 10, "bold"),
        )
        style.configure(
            "OrderSecondary.TButton",
            background="#E2E8F0",
            foreground=self.TEXT,
            padding=(14, 10),
            font=(self.font_family, 10, "bold"),
        )

    def _make_card(self, parent: tk.Misc, padding: int = 18) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=self.CARD_BG,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            padx=padding,
            pady=padding,
        )

    def _build_widgets(self) -> None:
        shell = tk.Frame(self.window, bg=self.BG)
        shell.pack(fill="both", expand=True, padx=20, pady=20)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)

        header = self._make_card(shell, padding=20)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header,
            text="已卖出宝贝订单导出",
            bg=self.CARD_BG,
            fg=self.TEXT,
            font=(self.font_family, 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="按商品 ID 和付款时间导出【宝贝销售明细报表】，并生成订单汇总表。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10),
        ).pack(anchor="w", pady=(8, 0))

        form = self._make_card(shell, padding=20)
        form.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        form.columnconfigure(1, weight=1)

        self._add_product_ids_text(form, 0)
        self._add_labeled_entry(form, 1, "付款开始日期", self.start_date_var)
        self._add_labeled_entry(form, 2, "付款结束日期", self.end_date_var)

        tk.Label(
            form,
            text="保存位置",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))
        output_row = tk.Frame(form, bg=self.CARD_BG)
        output_row.grid(row=3, column=1, sticky="ew", pady=(0, 10))
        output_row.columnconfigure(0, weight=1)
        tk.Label(
            output_row,
            text=format_output_dir_label(self.output_dir),
            bg="#F8FAFC",
            fg=self.TEXT,
            anchor="w",
            padx=12,
            pady=9,
            relief="solid",
            borderwidth=1,
        ).grid(row=0, column=0, sticky="ew")
        self.open_output_button = ttk.Button(
            output_row,
            text="打开目录",
            style="OrderSecondary.TButton",
            command=self._open_output_dir,
        )
        self.open_output_button.grid(row=0, column=1, padx=(10, 0))

        tk.Label(
            form,
            text="商品 ID 可一行一个，或用逗号、空格分隔；程序会按英文逗号提交。日期格式为 YYYY-MM-DD。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 9),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        actions = self._make_card(shell, padding=20)
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=0)
        self.open_browser_button = ttk.Button(
            actions,
            text="打开 9222 工作浏览器",
            style="OrderSecondary.TButton",
            command=self.on_open_browser_clicked,
        )
        self.open_browser_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.start_export_button = ttk.Button(
            actions,
            text="我已登录，开始导出订单表",
            style="OrderPrimary.TButton",
            command=self.on_start_export_clicked,
        )
        self.start_export_button.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.close_button = ttk.Button(
            actions,
            text="关闭",
            style="OrderSecondary.TButton",
            command=self._on_close,
        )
        self.close_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        tk.Label(
            actions,
            textvariable=self.status_var,
            bg=self.CARD_BG,
            fg=self.PRIMARY,
            font=(self.font_family, 10, "bold"),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        self.progressbar = ttk.Progressbar(actions, mode="indeterminate")
        self.progressbar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        log_card = self._make_card(shell, padding=20)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)
        tk.Label(
            log_card,
            text="执行日志",
            bg=self.CARD_BG,
            fg=self.TEXT,
            font=(self.font_family, 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.log_text = scrolledtext.ScrolledText(
            log_card,
            height=13,
            wrap=tk.WORD,
            state="disabled",
            bg="#FFFFFF",
            fg=self.TEXT,
            relief="solid",
            borderwidth=1,
            font=(self.font_family, 10),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.log_text.tag_configure("error", foreground=self.ERROR)
        self.log_text.tag_configure("success", foreground=self.SUCCESS)

        self.append_log("订单导出助手已打开。")

    def _add_product_ids_text(self, parent: tk.Misc, row: int) -> None:
        tk.Label(
            parent,
            text="商品 ID",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=row, column=0, sticky="nw", pady=(0, 10))
        self.product_ids_text = tk.Text(
            parent,
            height=4,
            wrap=tk.WORD,
            bg=self.CARD_BG,
            fg=self.TEXT,
            relief="solid",
            borderwidth=1,
            font=(self.font_family, 10),
            padx=8,
            pady=6,
        )
        self.product_ids_text.grid(row=row, column=1, sticky="ew", pady=(0, 10))

    def _add_labeled_entry(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=(0, 10))

    def _bind_events(self) -> None:
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _set_running(self, running: bool, status: str = "") -> None:
        self.running = running
        if status:
            self.status_var.set(status)
        state = "disabled" if running else "normal"
        for button in (self.open_browser_button, self.start_export_button, self.close_button, self.open_output_button):
            if button is not None:
                button.config(state=state if button is not self.close_button else "normal")
        if self.product_ids_text is not None:
            self.product_ids_text.config(state=state)
        if self.progressbar is not None:
            if running:
                self.progressbar.start(12)
            else:
                self.progressbar.stop()

    def _get_request(self) -> dict[str, str]:
        if self.product_ids_text is not None:
            product_ids = self.product_ids_text.get("1.0", tk.END).strip()
        else:
            product_ids = (self.product_ids_var.get() or "").strip()
        start_value = (self.start_date_var.get() or "").strip()
        end_value = (self.end_date_var.get() or "").strip()

        if not product_ids:
            raise ValueError("请先输入至少一个商品 ID。")
        normalized_product_ids = ",".join(SoldOrderExporter.normalize_product_ids(product_ids))
        if not normalized_product_ids:
            raise ValueError("请先输入至少一个商品 ID。")
        try:
            start_date = datetime.strptime(start_value, DateConfig.DATE_FORMAT)
        except ValueError as exc:
            raise ValueError("付款开始日期格式不正确，请输入 YYYY-MM-DD。") from exc
        try:
            end_date = datetime.strptime(end_value, DateConfig.DATE_FORMAT)
        except ValueError as exc:
            raise ValueError("付款结束日期格式不正确，请输入 YYYY-MM-DD。") from exc
        if end_date < start_date:
            raise ValueError("付款结束日期不能早于付款开始日期。")

        return {
            "product_ids": normalized_product_ids,
            "start_date": start_date.strftime(DateConfig.DATE_FORMAT),
            "end_date": end_date.strftime(DateConfig.DATE_FORMAT),
        }

    def on_open_browser_clicked(self) -> None:
        if self.running:
            return
        try:
            command = build_work_browser_command(chrome_binary_path=BrowserConfig.CHROME_BINARY_PATH)
            subprocess.Popen(command)
            self.status_var.set("浏览器已打开，请登录千牛/天猫商家后台后再点击开始导出。")
            self.append_log("已打开 9222 工作浏览器。")
        except Exception:
            error_text = traceback.format_exc().strip()
            self.status_var.set("我没能打开工作浏览器。")
            self.append_log(friendly_error_message(error_text), tag="error")
            technical = summarize_technical_error(error_text)
            if technical:
                self.append_log(f"技术细节：{technical}", tag="error")
            print(error_text, file=sys.stderr)

    def on_start_export_clicked(self) -> None:
        if self.running:
            return
        try:
            request = self._get_request()
        except Exception as exc:
            self.status_var.set(str(exc))
            self.append_log(str(exc), tag="error")
            return

        self._set_running(True, "正在导出订单表，请不要切换浏览器标签页。")
        worker = Thread(target=self._export_worker, kwargs={"request": request}, daemon=True)
        worker.start()

    def _export_worker(self, request: dict[str, str]) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if self.exporter is not None:
                self.exporter.close()
                self.exporter = None
            self.exporter = SoldOrderExporter(attach_to_existing_browser=True)
            self.exporter.init_driver(download_dir=self.output_dir)
            self.window.after(0, self.append_log, "已连接 9222 工作浏览器。")
            self.window.after(
                0,
                self.append_log,
                (
                    "准备导出："
                    f"商品ID={request['product_ids']}，"
                    f"付款时间={request['start_date']} ~ {request['end_date']}"
                ),
            )
            exported_file = self.exporter.export_after_login(
                download_dir=self.output_dir,
                product_ids=request["product_ids"],
                start_date=request["start_date"],
                end_date=request["end_date"],
            )
            summary_file = self._build_summary_output_path(request)
            DataProcessor().save_tmall_sold_order_summary(
                input_path=exported_file,
                output_path=summary_file,
                product_ids=request["product_ids"],
            )
            self.window.after(0, self.status_var.set, "订单原始表和汇总表已生成到桌面。")
            self.window.after(0, self.append_log, f"原始订单表已下载：{exported_file.name}", "success")
            self.window.after(0, self.append_log, f"订单汇总表已生成：{summary_file.name}", "success")
        except Exception:
            error_text = traceback.format_exc().strip()
            friendly = friendly_error_message(error_text)
            self.window.after(0, self.status_var.set, friendly)
            self.window.after(0, self.append_log, friendly, "error")
            technical = summarize_technical_error(error_text)
            if technical:
                self.window.after(0, self.append_log, f"技术细节：{technical}", "error")
            print(error_text, file=sys.stderr)
        finally:
            try:
                if self.exporter is not None:
                    self.exporter.close()
            finally:
                self.exporter = None
            self.window.after(0, self._set_running, False)

    def _build_summary_output_path(self, request: dict[str, str]) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.output_dir / (
            f"天猫订单汇总_{request['start_date']}_{request['end_date']}_{timestamp}.xlsx"
        )

    def _open_output_dir(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(self.output_dir)])
            elif os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(str(self.output_dir))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self.output_dir)])
        except Exception:
            self.append_log("我没能打开输出目录，你可以手动到桌面查看。", tag="error")

    def append_log(self, message: str, tag: str = "") -> None:
        if self.log_text is None:
            return
        text = str(message or "").strip()
        if not text:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {text}"
        self.log_text.config(state="normal")
        if tag:
            self.log_text.insert(tk.END, f"{formatted}\n", tag)
        else:
            self.log_text.insert(tk.END, f"{formatted}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _on_close(self) -> None:
        try:
            if self.exporter is not None:
                self.exporter.close()
        finally:
            self.window.destroy()
