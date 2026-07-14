"""
抖音订单表离线处理独立窗口。
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
from tkinter import filedialog, scrolledtext, ttk

from qianiu_auto_report.browser_runtime import summarize_technical_error
from qianiu_auto_report.config import ExportConfig
from qianiu_auto_report.data_process import DataProcessor
from qianiu_auto_report.gui_support import format_output_dir_label
from qianiu_auto_report.gui_state import friendly_error_message


class DouyinOrderFileWindow:
    """
    独立的“抖音订单表处理”窗口。
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

        self.input_file_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="请选择抖音订单明细表，然后点击开始处理。")

        self.choose_file_button: ttk.Button | None = None
        self.start_button: ttk.Button | None = None
        self.open_output_button: ttk.Button | None = None
        self.close_button: ttk.Button | None = None
        self.progressbar: ttk.Progressbar | None = None
        self.log_text: scrolledtext.ScrolledText | None = None
        self.running = False

        self._build_window()
        self._configure_styles()
        self._build_widgets()
        self._bind_events()

    def _build_window(self) -> None:
        self.window.title("抖音订单表处理")
        self.window.geometry("820x620")
        self.window.minsize(760, 560)
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
            "DouyinFilePrimary.TButton",
            background=self.PRIMARY,
            foreground="white",
            padding=(16, 11),
            font=(self.font_family, 10, "bold"),
        )
        style.configure(
            "DouyinFileSecondary.TButton",
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
            text="抖音订单表处理",
            bg=self.CARD_BG,
            fg=self.TEXT,
            font=(self.font_family, 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="导入抖音订单明细表，按商品 ID 汇总订单、金额和退款数据。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10),
        ).pack(anchor="w", pady=(8, 0))

        form = self._make_card(shell, padding=20)
        form.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        form.columnconfigure(1, weight=1)

        tk.Label(
            form,
            text="订单明细表",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        file_row = tk.Frame(form, bg=self.CARD_BG)
        file_row.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.input_file_var).grid(row=0, column=0, sticky="ew")
        self.choose_file_button = ttk.Button(
            file_row,
            text="选择文件",
            style="DouyinFileSecondary.TButton",
            command=self.on_choose_file_clicked,
        )
        self.choose_file_button.grid(row=0, column=1, padx=(10, 0))

        tk.Label(
            form,
            text="保存位置",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        output_row = tk.Frame(form, bg=self.CARD_BG)
        output_row.grid(row=1, column=1, sticky="ew", pady=(0, 10))
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
            style="DouyinFileSecondary.TButton",
            command=self._open_output_dir,
        )
        self.open_output_button.grid(row=0, column=1, padx=(10, 0))

        actions = self._make_card(shell, padding=20)
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=0)
        self.start_button = ttk.Button(
            actions,
            text="开始处理并生成汇总表",
            style="DouyinFilePrimary.TButton",
            command=self.on_start_clicked,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.close_button = ttk.Button(
            actions,
            text="关闭",
            style="DouyinFileSecondary.TButton",
            command=self._on_close,
        )
        self.close_button.grid(row=0, column=1, sticky="ew")
        tk.Label(
            actions,
            textvariable=self.status_var,
            bg=self.CARD_BG,
            fg=self.PRIMARY,
            font=(self.font_family, 10, "bold"),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        self.progressbar = ttk.Progressbar(actions, mode="indeterminate")
        self.progressbar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

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
            height=11,
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
        self.append_log("抖音订单表处理助手已打开。")

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
        for button in (self.choose_file_button, self.start_button, self.close_button, self.open_output_button):
            if button is not None:
                button.config(state=state if button is not self.close_button else "normal")
        if self.progressbar is not None:
            if running:
                self.progressbar.start(12)
            else:
                self.progressbar.stop()

    def _get_request(self) -> dict[str, Path | str]:
        input_file = Path((self.input_file_var.get() or "").strip()).expanduser()
        if not input_file.exists() or not input_file.is_file():
            raise ValueError("请先选择一份抖音订单明细表。")
        if input_file.suffix.lower() not in DataProcessor.SUPPORTED_TABLE_SUFFIXES:
            raise ValueError("请选择表格文件（.csv/.xlsx/.xls/.xlsm/.et）。")

        return {
            "input_file": input_file,
        }

    def on_choose_file_clicked(self) -> None:
        if self.running:
            return
        file_path = filedialog.askopenfilename(
            parent=self.window,
            title="选择抖音订单明细表",
            filetypes=(
                ("表格文件", "*.csv *.xlsx *.xls *.xlsm *.et"),
                ("CSV 文件", "*.csv"),
                ("Excel/WPS 文件", "*.xlsx *.xls *.xlsm *.et"),
                ("所有文件", "*.*"),
            ),
        )
        if file_path:
            self.input_file_var.set(file_path)
            self.append_log(f"已选择文件：{Path(file_path).name}")

    def on_start_clicked(self) -> None:
        if self.running:
            return
        try:
            request = self._get_request()
        except Exception as exc:
            self.status_var.set(str(exc))
            self.append_log(str(exc), tag="error")
            return

        self._set_running(True, "正在处理抖音订单明细表。")
        worker = Thread(target=self._process_worker, kwargs={"request": request}, daemon=True)
        worker.start()

    def _process_worker(self, request: dict[str, Path | str]) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            input_file = Path(request["input_file"])
            self.window.after(0, self.append_log, f"开始处理：{input_file.name}")
            output_file = self._build_output_path()
            DataProcessor().save_douyin_order_detail_summary(
                input_path=input_file,
                output_path=output_file,
            )
            self.window.after(0, self.status_var.set, "抖音订单汇总表已生成到桌面。")
            self.window.after(0, self.append_log, f"抖音订单汇总表已生成：{output_file.name}", "success")
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
            self.window.after(0, self._set_running, False)

    def _build_output_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.output_dir / f"抖音订单汇总_{timestamp}.xlsx"

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
        self.window.destroy()
