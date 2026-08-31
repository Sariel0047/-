"""
Tkinter 图形界面模块。
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

from qianiu_auto_report.config import (
    BrowserConfig,
    DateConfig,
    ExportConfig,
    PROCESSED_OUTPUT_DIR,
)
from qianiu_auto_report.browser_runtime import summarize_technical_error
from qianiu_auto_report.data_process import DataProcessor
from qianiu_auto_report.excel_writer import ExcelWriter
from qianiu_auto_report.gui_support import (
    build_work_browser_command,
    format_attach_mode_label,
    format_output_dir_label,
    format_platform_label,
    normalize_platform_selection,
)
from qianiu_auto_report.gui_state import (
    EXIT_BUTTON_LABEL,
    GUIState,
    REOPEN_BROWSER_BUTTON_LABEL,
    friendly_error_message,
    get_hint_prompt,
    get_primary_button_label,
    get_status_prompt,
    is_primary_enabled,
    is_reopen_enabled,
)
from qianiu_auto_report.web_export import WebExporter


class AppGUI:
    """
    主界面类。
    """

    BG = "#F3F6FB"
    CARD_BG = "#FFFFFF"
    HERO_BG = "#0F172A"
    HERO_CARD_BG = "#111827"
    HERO_BORDER = "#1F2937"
    BORDER = "#D9E2EF"
    TEXT = "#0F172A"
    MUTED = "#64748B"
    PRIMARY = "#2563EB"
    PRIMARY_DARK = "#1D4ED8"
    SECONDARY_BG = "#E2E8F0"
    SECONDARY_DARK = "#CBD5E1"
    SUCCESS = "#0F766E"
    ERROR = "#B91C1C"
    LOG_HEIGHT = 9

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.font_family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        self.attach_mode = BrowserConfig.ATTACH_TO_EXISTING_BROWSER
        self.ui_state = GUIState.IDLE

        self.output_dir = Path(ExportConfig.DOWNLOAD_DIR).expanduser()
        self.date_var = tk.StringVar(value=self._get_default_date())
        self.platform_var = tk.StringVar(value=format_platform_label(ExportConfig.PLATFORM))
        self.platform_badge_var = tk.StringVar(value=f"平台：{format_platform_label(ExportConfig.PLATFORM)}")
        self.mode_badge_var = tk.StringVar(value=f"连接方式：{format_attach_mode_label(BrowserConfig.ATTACH_TO_EXISTING_BROWSER)}")
        self.output_badge_var = tk.StringVar(value=f"输出：{format_output_dir_label(self.output_dir)}")
        self.status_var = tk.StringVar(value=get_status_prompt(self.ui_state))
        self.hint_var = tk.StringVar(value=get_hint_prompt(self.ui_state))

        self.primary_button: ttk.Button | None = None
        self.reopen_button: ttk.Button | None = None
        self.exit_button: ttk.Button | None = None
        self.open_output_button: ttk.Button | None = None
        self.progressbar: ttk.Progressbar | None = None
        self.status_text: scrolledtext.ScrolledText | None = None
        self.platform_combo: ttk.Combobox | None = None

        self.web_exporter: WebExporter | None = None
        self.order_export_window: object | None = None
        self.douyin_order_file_window: object | None = None
        self.style: ttk.Style | None = None

        self._build_window()
        self._configure_styles()
        self._build_widgets()
        self._build_menu()
        self._bind_events()
        self.platform_var.trace_add("write", self._on_platform_selection_changed)

    def _get_default_date(self) -> str:
        """
        获取默认日期，默认值为前一天。
        """
        return DateConfig.default_report_date_str()

    def _build_window(self) -> None:
        """
        初始化主窗口配置。
        """
        self.root.title("报表助手")
        self.root.geometry("1080x780")
        self.root.minsize(980, 720)
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG)

    def _build_menu(self) -> None:
        """
        构建主菜单。新功能通过独立窗口打开，不改变主界面布局。
        """
        menubar = tk.Menu(self.root)
        feature_menu = tk.Menu(menubar, tearoff=0)
        feature_menu.add_command(
            label="天猫订单表处理",
            command=self.open_order_export_window,
        )
        feature_menu.add_command(
            label="抖音订单表处理",
            command=self.open_douyin_order_file_window,
        )
        menubar.add_cascade(label="功能", menu=feature_menu)
        self.root.config(menu=menubar)

    def _get_task_entries(self) -> tuple[tuple[str, object | None], ...]:
        """
        返回主界面直接展示的任务入口。
        """
        return (
            ("在线自动生成", None),
            ("天猫订单表处理", self.open_order_export_window),
            ("抖音订单表处理", self.open_douyin_order_file_window),
        )

    def open_order_export_window(self) -> None:
        """
        打开独立的天猫订单表离线处理窗口。
        """
        from qianiu_auto_report.order_export_gui import OrderExportWindow

        existing = self.order_export_window
        if existing is not None:
            try:
                window = getattr(existing, "window", None)
                if window is not None and bool(window.winfo_exists()):
                    existing.focus()
                    return
            except Exception:
                pass

        self.order_export_window = OrderExportWindow(self.root)

    def open_douyin_order_file_window(self) -> None:
        """
        打开独立的抖音订单表处理窗口。
        """
        from qianiu_auto_report.douyin_order_file_gui import DouyinOrderFileWindow

        existing = self.douyin_order_file_window
        if existing is not None:
            try:
                window = getattr(existing, "window", None)
                if window is not None and bool(window.winfo_exists()):
                    existing.focus()
                    return
            except Exception:
                pass

        self.douyin_order_file_window = DouyinOrderFileWindow(self.root)

    def _configure_styles(self) -> None:
        """
        配置整体视觉风格。
        """
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=(self.font_family, 10))
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("TEntry", fieldbackground=self.CARD_BG, padding=(8, 6))
        style.configure("TCombobox", fieldbackground=self.CARD_BG, padding=(8, 6))
        style.configure("TButton", padding=(14, 9), relief="flat")
        style.configure(
            "Primary.TButton",
            background=self.PRIMARY,
            foreground="white",
            padding=(18, 12),
            font=(self.font_family, 11, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", self.PRIMARY_DARK), ("pressed", self.PRIMARY_DARK)],
            foreground=[("disabled", "#E2E8F0")],
        )
        style.configure(
            "Secondary.TButton",
            background=self.SECONDARY_BG,
            foreground=self.TEXT,
            padding=(16, 10),
            font=(self.font_family, 10, "bold"),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", self.SECONDARY_DARK), ("pressed", self.SECONDARY_DARK)],
        )
        style.configure(
            "Ghost.TButton",
            background=self.CARD_BG,
            foreground=self.PRIMARY,
            borderwidth=1,
            padding=(12, 8),
            font=(self.font_family, 10, "bold"),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#EFF6FF"), ("pressed", "#DBEAFE")],
        )
        style.configure(
            "HeroTask.TButton",
            background="#334155",
            foreground="white",
            padding=(14, 10),
            font=(self.font_family, 10, "bold"),
        )
        style.map(
            "HeroTask.TButton",
            background=[("active", "#475569"), ("pressed", "#1E293B")],
        )
        self.style = style

    @staticmethod
    def _make_card(
        parent: tk.Misc,
        *,
        bg: str | None = None,
        border: str | None = None,
        padding: int = 18,
    ) -> tk.Frame:
        """
        创建带边框的卡片容器。
        """
        background = bg or AppGUI.CARD_BG
        border_color = border or AppGUI.BORDER
        return tk.Frame(
            parent,
            bg=background,
            highlightbackground=border_color,
            highlightthickness=1,
            padx=padding,
            pady=padding,
        )

    def _make_heading(
        self,
        parent: tk.Misc,
        title: str,
        subtitle: str,
        *,
        title_fg: str | None = None,
        subtitle_fg: str | None = None,
        bg: str | None = None,
    ) -> None:
        """
        创建卡片标题与副标题。
        """
        background = bg or self.CARD_BG
        title_color = title_fg or self.TEXT
        subtitle_color = subtitle_fg or self.MUTED
        tk.Label(
            parent,
            text=title,
            bg=background,
            fg=title_color,
            font=(self.font_family, 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            parent,
            text=subtitle,
            bg=background,
            fg=subtitle_color,
            font=(self.font_family, 10),
        ).pack(anchor="w", pady=(4, 0))

    def _make_badge(
        self,
        parent: tk.Misc,
        text: str = "",
        *,
        bg: str,
        fg: str = "white",
        border: str | None = None,
        textvariable: tk.StringVar | None = None,
    ) -> tk.Label:
        """
        创建顶部信息徽章。
        """
        return tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            bg=bg,
            fg=fg,
            font=(self.font_family, 10, "bold"),
            padx=12,
            pady=6,
            relief="flat",
            highlightthickness=1 if border else 0,
            highlightbackground=border or bg,
        )

    def _build_hero_section(self, parent: tk.Misc) -> tk.Frame:
        """
        顶部英雄区，展示标题和关键状态。
        """
        hero = tk.Frame(
            parent,
            bg=self.HERO_BG,
            highlightbackground=self.HERO_BORDER,
            highlightthickness=1,
            padx=24,
            pady=18,
        )

        top_row = tk.Frame(hero, bg=self.HERO_BG)
        top_row.pack(fill="x")

        left = tk.Frame(top_row, bg=self.HERO_BG)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(
            left,
            text="报表助手",
            bg=self.HERO_BG,
            fg="white",
            font=(self.font_family, 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left,
            textvariable=self.hint_var,
            bg=self.HERO_BG,
            fg="#93C5FD",
            font=(self.font_family, 10),
        ).pack(anchor="w", pady=(10, 0))

        right = tk.Frame(top_row, bg=self.HERO_BG)
        right.pack(side="right")
        self._make_badge(
            right,
            textvariable=self.platform_badge_var,
            bg="#1D4ED8",
            border="#3B82F6",
        ).pack(side="left")
        self._make_badge(
            right,
            textvariable=self.mode_badge_var,
            bg="#334155",
            border="#475569",
        ).pack(side="left", padx=(8, 0))
        self._make_badge(
            right,
            textvariable=self.output_badge_var,
            bg="#0F766E",
            border="#14B8A6",
        ).pack(side="left", padx=(8, 0))

        task_section = tk.Frame(hero, bg=self.HERO_BG)
        task_section.pack(fill="x", pady=(16, 0))
        tk.Label(
            task_section,
            text="选择任务",
            bg=self.HERO_BG,
            fg="#CBD5E1",
            font=(self.font_family, 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        task_row = tk.Frame(task_section, bg=self.HERO_BG)
        task_row.pack(fill="x")
        for index, (label, command) in enumerate(self._get_task_entries()):
            task_row.columnconfigure(index, weight=1)
            padx = (0 if index == 0 else 6, 0 if index == 2 else 6)
            if command is None:
                tk.Label(
                    task_row,
                    text=label,
                    bg=self.PRIMARY,
                    fg="white",
                    font=(self.font_family, 10, "bold"),
                    padx=14,
                    pady=11,
                ).grid(row=0, column=index, sticky="ew", padx=padx)
            else:
                ttk.Button(
                    task_row,
                    text=label,
                    command=command,
                    style="HeroTask.TButton",
                ).grid(row=0, column=index, sticky="ew", padx=padx)

        return hero

    def _build_settings_card(self, parent: tk.Misc) -> tk.Frame:
        """
        运行设置卡片。
        """
        card = self._make_card(parent, padding=20)
        self._make_heading(card, "运行设置", "平台、日期和保存位置都在这里。")

        body = tk.Frame(card, bg=self.CARD_BG)
        body.pack(fill="x", pady=(16, 0))

        body.columnconfigure(1, weight=1)

        tk.Label(
            body,
            text="平台",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.platform_combo = ttk.Combobox(
            body,
            textvariable=self.platform_var,
            values=("自动识别", "淘宝", "抖音"),
            state="readonly",
            width=18,
        )
        self.platform_combo.grid(row=0, column=1, sticky="ew", pady=(0, 10))

        tk.Label(
            body,
            text="报表日期",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(
            body,
            textvariable=self.date_var,
        ).grid(row=1, column=1, sticky="ew", pady=(0, 10))

        tk.Label(
            body,
            text="保存位置",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 10, "bold"),
        ).grid(row=2, column=0, sticky="nw")

        output_wrap = tk.Frame(body, bg=self.CARD_BG)
        output_wrap.grid(row=2, column=1, sticky="ew")
        output_wrap.columnconfigure(0, weight=1)
        tk.Label(
            output_wrap,
            text=format_output_dir_label(self.output_dir),
            bg="#F8FAFC",
            fg=self.TEXT,
            justify="left",
            anchor="w",
            padx=12,
            pady=9,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            wraplength=260,
        ).grid(row=0, column=0, sticky="ew")
        self.open_output_button = ttk.Button(
            output_wrap,
            text="打开输出目录",
            style="Ghost.TButton",
            command=self._open_output_dir,
        )
        self.open_output_button.grid(row=0, column=1, padx=(10, 0))

        tk.Label(
            card,
            text="提示：平台选择为“自动识别”时，会根据当前浏览器页面 URL 判定淘宝或抖音。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 9),
        ).pack(anchor="w", pady=(14, 0))

        return card

    def _build_actions_card(self, parent: tk.Misc) -> tk.Frame:
        """
        执行操作卡片。
        """
        card = self._make_card(parent, padding=20)
        self._make_heading(card, "执行操作", "只需要按提示点按钮，其他事情交给我。")

        button_wrap = tk.Frame(card, bg=self.CARD_BG)
        button_wrap.pack(fill="x", pady=(16, 0))
        button_wrap.columnconfigure(0, weight=1)

        self.primary_button = ttk.Button(
            button_wrap,
            text=get_primary_button_label(self.ui_state),
            command=self.on_primary_clicked,
            style="Primary.TButton",
        )
        self.primary_button.grid(row=0, column=0, sticky="ew")

        aux_wrap = tk.Frame(card, bg=self.CARD_BG)
        aux_wrap.pack(fill="x", pady=(12, 0))
        aux_wrap.columnconfigure(0, weight=1)
        aux_wrap.columnconfigure(1, weight=1)

        self.reopen_button = ttk.Button(
            aux_wrap,
            text=REOPEN_BROWSER_BUTTON_LABEL,
            command=self.on_reopen_browser_clicked,
            style="Secondary.TButton",
        )
        self.reopen_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.exit_button = ttk.Button(
            aux_wrap,
            text=EXIT_BUTTON_LABEL,
            command=self._on_close,
            style="Ghost.TButton",
        )
        self.exit_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        tk.Label(
            card,
            text="如果浏览器已经打开并完成登录，点主按钮开始生成报表；如果浏览器丢了，就点“重新打开工作浏览器”。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(14, 0))

        return card

    def _build_status_card(self, parent: tk.Misc) -> tk.Frame:
        """
        运行状态卡片。
        """
        card = self._make_card(parent, padding=20)
        self._make_heading(card, "当前状态", "这里会用更直白的话告诉你现在到了哪一步。")

        status_box = tk.Frame(card, bg=self.CARD_BG)
        status_box.pack(fill="x", pady=(14, 0))

        tk.Label(
            status_box,
            textvariable=self.status_var,
            bg="#EFF6FF",
            fg=self.PRIMARY_DARK,
            font=(self.font_family, 12, "bold"),
            padx=14,
            pady=10,
            anchor="w",
            justify="left",
            wraplength=280,
            relief="solid",
            borderwidth=1,
        ).pack(fill="x")

        self.progressbar = ttk.Progressbar(card, mode="indeterminate")
        self.progressbar.pack(fill="x", pady=(14, 0))

        tk.Label(
            card,
            text="执行时请尽量不要手动切换浏览器标签页，避免打断自动化流程。",
            bg=self.CARD_BG,
            fg=self.MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=280,
        ).pack(anchor="w", pady=(12, 0))

        return card

    def _build_log_card(self, parent: tk.Misc) -> tk.Frame:
        """
        日志卡片。
        """
        card = self._make_card(parent, padding=20)
        self._make_heading(card, "运行日志", "这里会持续显示系统执行过程。")

        log_wrap = tk.Frame(card, bg=self.CARD_BG)
        log_wrap.pack(fill="both", expand=True, pady=(14, 0))
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        self.status_text = scrolledtext.ScrolledText(
            log_wrap,
            width=70,
            height=self.LOG_HEIGHT,
            wrap=tk.WORD,
            state="disabled",
            bg="#FFFFFF",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            font=(self.font_family, 10),
        )
        self.status_text.grid(row=0, column=0, sticky="nsew")
        self.status_text.tag_configure("error", foreground=self.ERROR)
        self.status_text.tag_configure("success", foreground=self.SUCCESS)
        self.status_text.tag_configure("muted", foreground=self.MUTED)

        return card

    def _build_widgets(self) -> None:
        """
        创建界面组件。
        """
        shell = tk.Frame(self.root, bg=self.BG)
        shell.pack(fill="both", expand=True, padx=22, pady=18)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        hero = self._build_hero_section(shell)
        hero.grid(row=0, column=0, sticky="ew")

        body = tk.Frame(shell, bg=self.BG)
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        left_col = tk.Frame(body, bg=self.BG)
        left_col.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 18))
        left_col.columnconfigure(0, weight=1)

        self._build_settings_card(left_col).pack(fill="x", pady=(0, 18))
        self._build_actions_card(left_col).pack(fill="x")

        right_col = tk.Frame(body, bg=self.BG)
        right_col.grid(row=0, column=1, rowspan=2, sticky="nsew")
        right_col.columnconfigure(0, weight=1)
        right_col.rowconfigure(1, weight=1)

        self._build_status_card(right_col).grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self._build_log_card(right_col).grid(row=1, column=0, sticky="nsew")

        self.append_log("系统已启动。")
        self.append_log(f"默认报表日期：{self.date_var.get()}")
        self.append_log(f"平台模式：{self.platform_var.get()}（可切换 自动识别 / 淘宝 / 抖音）")
        self.append_log("当前模式：先唤起 9222 工作浏览器，登录后再附着执行。")
        self.append_log("请点击“开始生成”，然后在浏览器里自行选择淘宝或抖音页面并登录。")

        self._refresh_header_badges()
        self._set_ui_state(GUIState.IDLE, update_prompt=False)

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

    def _set_busy(self, busy: bool) -> None:
        """
        启停状态进度条。
        """
        if self.progressbar is None:
            return
        if busy:
            self.progressbar.start(12)
        else:
            self.progressbar.stop()

    def _sync_controls(self) -> None:
        """
        根据当前状态刷新按钮和下拉框可用性。
        """
        if self.primary_button is not None:
            self.primary_button.config(
                text=get_primary_button_label(self.ui_state),
                state="normal" if is_primary_enabled(self.ui_state) else "disabled",
            )
        if self.reopen_button is not None:
            self.reopen_button.config(
                state="normal" if is_reopen_enabled(self.ui_state) else "disabled"
            )
        if self.exit_button is not None:
            self.exit_button.config(state="normal")
        if self.open_output_button is not None:
            self.open_output_button.config(state="normal")
        if self.platform_combo is not None:
            self.platform_combo.config(
                state="readonly" if self.ui_state in {GUIState.IDLE, GUIState.FINISHED, GUIState.ERROR} else "disabled"
            )

    def _set_ui_state(
        self,
        state: GUIState | str,
        status: str | None = None,
        *,
        hint: str | None = None,
        update_prompt: bool = True,
    ) -> None:
        """
        统一更新界面状态、提示和按钮。
        """
        self.ui_state = GUIState(state) if not isinstance(state, GUIState) else state
        if update_prompt:
            self.status_var.set(status or get_status_prompt(self.ui_state))
            self.hint_var.set(hint or get_hint_prompt(self.ui_state))
        elif status is not None:
            self.status_var.set(status)
        if hint is not None:
            self.hint_var.set(hint)
        self._sync_controls()
        self._set_busy(self.ui_state in {GUIState.STARTING, GUIState.RUNNING})

    def _reset_to_idle(self, *, append_message: bool = True) -> None:
        """
        将界面恢复到初始状态。
        """
        self._set_ui_state(GUIState.IDLE)
        if append_message:
            self.append_log("我已经帮你恢复到初始状态，可以重新开始。")

    def _open_output_dir(self) -> None:
        """
        打开当前输出目录。
        """
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(self.output_dir)])
            elif os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(str(self.output_dir))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self.output_dir)])
            self.append_log(f"已打开输出目录：{self.output_dir}")
        except Exception:
            self.append_log("我没能打开输出目录，你可以手动到桌面看看。")
            print(traceback.format_exc().strip(), file=sys.stderr)
            self._set_ui_state(GUIState.ERROR, status="我没能打开输出目录，你可以手动到桌面看看。")

    def _refresh_header_badges(self) -> None:
        """
        刷新顶部徽章文案。
        """
        self.platform_badge_var.set(f"平台：{format_platform_label(self._get_selected_platform())}")
        self.mode_badge_var.set(f"连接方式：{format_attach_mode_label(self.attach_mode)}")
        self.output_badge_var.set(f"输出：{format_output_dir_label(self.output_dir)}")

    def _on_platform_selection_changed(self, *_args: object) -> None:
        """
        平台下拉发生变化时同步顶部徽章。
        """
        self._refresh_header_badges()

    def _get_selected_platform(self) -> str:
        """
        读取 GUI 中的平台选择值。
        """
        value = normalize_platform_selection(self.platform_var.get())
        if value in {"taobao", "douyin"}:
            return value
        return "auto"

    def _get_selected_report_date(self) -> str:
        """
        读取并校验 GUI 中的报表日期。
        """
        value = (self.date_var.get() or "").strip()
        try:
            parsed = datetime.strptime(value, DateConfig.DATE_FORMAT)
        except ValueError as exc:
            raise ValueError("报表日期格式不正确，请输入 YYYY-MM-DD，例如 2026-05-13。") from exc
        return parsed.strftime(DateConfig.DATE_FORMAT)

    def _resolve_target_platform(self, current_url: str) -> tuple[str, str]:
        """
        解析 GUI 运行时的目标平台。
        """
        selected = self._get_selected_platform()
        if selected in {"taobao", "douyin"}:
            return selected, f"用户显式选择：{selected}"

        normalized = (current_url or "").strip().lower()
        if "jinritemai" in normalized:
            return "douyin", f"URL判定：{current_url}"
        if "taobao" in normalized:
            return "taobao", f"URL判定：{current_url}"

        raise RuntimeError(
            "无法自动判定平台。请在 GUI 平台下拉中显式选择 taobao 或 douyin，"
            "或先切换到包含 taobao/jinritemai 的页面。"
        )

    def _apply_platform_context(self, exporter: WebExporter, platform: str) -> None:
        """
        将平台上下文注入导出器（主要用于附着模式 URL 校验）。
        """
        if platform == "douyin":
            exporter.export_url = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"
            exporter.expected_url_prefix = "https://fxg.jinritemai.com/"
            if not (exporter.login_url or "").strip():
                exporter.login_url = exporter.export_url
        elif platform == "taobao":
            exporter.export_url = ExportConfig.EXPORT_URL
            exporter.expected_url_prefix = ExportConfig.EXPECTED_URL_PREFIX
            exporter.login_url = ExportConfig.LOGIN_URL
        elif platform == "auto" and getattr(exporter, "attach_to_existing_browser", self.attach_mode):
            exporter.export_url = ""
            exporter.expected_url_prefix = ""

    def _create_web_exporter(self) -> WebExporter:
        """
        创建网页导出器。
        """
        return WebExporter(attach_to_existing_browser=True)

    def _launch_work_browser(self) -> list[str]:
        """
        只唤起带 9222 调试端口的工作浏览器，不做 Selenium 附着。
        """
        command = build_work_browser_command(chrome_binary_path=BrowserConfig.CHROME_BINARY_PATH)
        subprocess.Popen(command)
        return command

    def _begin_browser_flow(self, *, reopen: bool = False) -> None:
        """
        启动或重新打开工作浏览器。
        """
        if self.ui_state in {GUIState.STARTING, GUIState.RUNNING}:
            return

        selected_platform = self._get_selected_platform()
        if reopen:
            self._set_ui_state(GUIState.STARTING)
            self.append_log("我没找到可用的浏览器，我再试一次。")
            self.append_log("我再帮你重新打开一次工作浏览器。")
        else:
            self._set_ui_state(GUIState.STARTING)
            self.append_log("我先帮你打开工作浏览器，请稍等。")
        self.append_log(f"当前平台选择：{format_platform_label(selected_platform)}")

        worker = Thread(target=self._open_login_page_worker, kwargs={"reopen": reopen}, daemon=True)
        worker.start()

    def on_primary_clicked(self) -> None:
        """
        主按钮点击处理。
        """
        if self.ui_state == GUIState.IDLE:
            self._begin_browser_flow()
        elif self.ui_state == GUIState.BROWSER_READY:
            self.on_continue_clicked()
        elif self.ui_state in {GUIState.FINISHED, GUIState.ERROR}:
            self._reset_to_idle()
        else:
            return

    def on_reopen_browser_clicked(self) -> None:
        """
        辅助按钮：重新打开工作浏览器。
        """
        self._begin_browser_flow(reopen=True)

    def _open_login_page_worker(self, *, reopen: bool = False) -> None:
        """
        后台打开登录页，不阻塞界面。
        """
        try:
            download_dir = self.output_dir
            download_dir.mkdir(parents=True, exist_ok=True)

            if self.web_exporter is not None:
                self.web_exporter.close()
                self.web_exporter = None
            self._launch_work_browser()
            self.root.after(0, self._refresh_header_badges)
            self.root.after(0, self._set_ui_state, GUIState.BROWSER_READY, "浏览器已经打开，请在这个窗口里登录。登录完成后，点“我已登录，开始生成报表”。")
            self.root.after(0, self.append_log, "工作浏览器已经唤起，请自行选择淘宝或抖音页面并完成登录。")
            if reopen:
                self.root.after(0, self.append_log, "我已经重新把工作浏览器打开好了。")
        except Exception:
            error_text = traceback.format_exc().strip()
            friendly = friendly_error_message(error_text)
            self.root.after(0, self._set_ui_state, GUIState.ERROR, friendly)
            self.root.after(0, self.append_log, friendly)
            self.root.after(0, self.append_log, "如果愿意，可以点“重新打开工作浏览器”再试一次。")
            print(error_text, file=sys.stderr)
            try:
                if self.web_exporter is not None:
                    self.web_exporter.close()
            finally:
                self.web_exporter = None

    def on_continue_clicked(self) -> None:
        """
        点击“我已登录，开始生成报表”。
        """
        self._set_ui_state(GUIState.RUNNING)
        self.append_log("我正在帮你整理报表，请不要关闭窗口。")

        worker = Thread(target=self._run_after_login_worker, daemon=True)
        worker.start()

    def _run_after_login_worker(self) -> None:
        """
        登录确认后执行导出、处理、写表。
        """
        try:
            download_dir = self.output_dir
            processed_path = PROCESSED_OUTPUT_DIR / "processed_report.xlsx"
            selected_platform = self._get_selected_platform()
            report_date = self._get_selected_report_date()
            if self.web_exporter is None:
                self.web_exporter = self._create_web_exporter()
                self._apply_platform_context(self.web_exporter, selected_platform)
                self.web_exporter.init_driver(download_dir=download_dir)
            current_url = self.web_exporter.get_current_url()
            target_platform, _platform_reason = self._resolve_target_platform(current_url=current_url)
            platform_label = "抖音" if target_platform == "douyin" else "淘宝"
            self.root.after(0, self.append_log, f"我判断当前是{platform_label}流程。")
            self._apply_platform_context(self.web_exporter, target_platform)

            skip_refund_manage_actions = ExportConfig.SKIP_REFUND_MANAGE_ACTIONS or target_platform == "douyin"
            if target_platform == "douyin" and not ExportConfig.SKIP_REFUND_MANAGE_ACTIONS:
                self.root.after(0, self.append_log, "抖音流程不需要千牛退款管理，我直接去电商罗盘取数。")

            metrics_list: list[dict[str, object]] = []
            if skip_refund_manage_actions:
                exported_file = None
                self.root.after(0, self.append_log, "这一段流程我已经自动跳过。")
                if target_platform == "douyin":
                    metrics_list = self.web_exporter.collect_douyin_all_shop_metrics(
                        download_dir=download_dir,
                        report_date=report_date,
                    )
                    metrics = metrics_list[0] if metrics_list else None
                else:
                    metrics = self.web_exporter.collect_business_finance_metrics(
                        download_dir=download_dir,
                        report_date=report_date,
                    )
                    metrics_list = [metrics]
            else:
                exported_file = self.web_exporter.export_after_login(
                    download_dir=download_dir,
                    report_date=report_date,
                )
                self.root.after(0, self.append_log, "我已经把退款明细下载好了。")
                metrics = self.web_exporter.collect_business_finance_metrics(
                    download_dir=download_dir,
                    report_date=report_date,
                )
                metrics_list = [metrics]

            for index, item in enumerate(metrics_list or [], start=1):
                self.root.after(
                    0,
                    self.append_log,
                    (
                        f"第{index}个店铺的数据已经整理好："
                        f"{item.get('shop_name') or '未识别店铺'}，"
                        f"支付金额 {item.get('payment_amount')}，"
                        f"推广费用 {item.get('promotion_fee')}"
                    ),
                )

            require_processed_for_excel = (
                not ExportConfig.SKIP_EXCEL_WRITE and not skip_refund_manage_actions
            )
            skip_data_process_effective = (
                (ExportConfig.SKIP_DATA_PROCESS and not require_processed_for_excel)
                or skip_refund_manage_actions
            )

            if ExportConfig.SKIP_DATA_PROCESS and require_processed_for_excel:
                self.root.after(
                    0,
                    self.append_log,
                    "为了把退款数据写进汇总表，我还是帮你做了数据整理。",
                )

            if skip_data_process_effective:
                summary = None
                if ExportConfig.SKIP_DATA_PROCESS:
                    self.root.after(0, self.append_log, "这一段整理步骤已自动跳过。")
            else:
                if exported_file is None:
                    raise RuntimeError("我没拿到可整理的数据文件。")
                processor = DataProcessor()
                summary = processor.process(
                    input_path=exported_file,
                    output_path=processed_path,
                    report_date=report_date,
                )

            if ExportConfig.SKIP_EXCEL_WRITE:
                report_file = None
                self.root.after(0, self.append_log, "写表步骤已自动跳过。")
            else:
                writer = ExcelWriter()
                if skip_refund_manage_actions:
                    if not metrics_list:
                        raise RuntimeError("我没拿到任何可以写入报表的数据。")
                    report_files = [
                        writer.export_business_finance_metrics(
                            metrics=item,
                            output_path=download_dir,
                        )
                        for item in metrics_list
                    ]
                    report_file = report_files[-1]
                    for item in report_files:
                        self.root.after(0, self.append_log, f"报表已经保存到桌面：{item.name}")
                else:
                    if summary is None:
                        raise RuntimeError("我没拿到可写入的整理结果。")
                    if metrics is None:
                        raise RuntimeError("我没拿到业务数据，没法合并写表。")
                    report_file = writer.export_refund_with_business_finance_metrics(
                        refund_summary=summary,
                        metrics=metrics,
                        output_path=download_dir,
                    )

            self.root.after(
                0,
                self._set_ui_state,
                GUIState.BROWSER_READY,
                "完成了，报表已经保存到桌面。你可以在浏览器里切换店铺或账号，登录完成后再点“我已登录，开始生成报表”。",
            )
            if report_file is not None:
                if skip_refund_manage_actions:
                    self.root.after(0, self.append_log, f"已经完成，共生成 {len(metrics_list)} 份报表。")
                else:
                    self.root.after(0, self.append_log, f"报表已经保存到桌面：{report_file.name}")
            else:
                self.root.after(0, self.append_log, "我已经完成了这次整理。")
        except Exception:
            error_text = traceback.format_exc().strip()
            friendly = friendly_error_message(error_text)
            self.root.after(0, self._set_ui_state, GUIState.ERROR, friendly)
            self.root.after(0, self.append_log, friendly)
            technical_detail = summarize_technical_error(error_text)
            if technical_detail:
                self.root.after(0, self.append_log, f"技术细节：{technical_detail}")
            self.root.after(0, self.append_log, "你可以点“重新打开工作浏览器”再试一次。")
            print(error_text, file=sys.stderr)
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

        raw_text = str(message or "")
        if not raw_text:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        if raw_text.startswith("["):
            formatted = raw_text
        else:
            parts = raw_text.splitlines()
            head = f"[{timestamp}] {parts[0]}"
            formatted = "\n".join([head, *parts[1:]]) if len(parts) > 1 else head

        lower_text = raw_text.lower()
        tag = ""
        if self.ui_state == GUIState.ERROR or (
            "traceback" in lower_text
            or "执行失败" in raw_text
            or "异常" in raw_text
            or "打开登录页失败" in raw_text
            or "附着浏览器失败" in raw_text
            or "我没找到可用的浏览器" in raw_text
            or "我这边遇到了一点问题" in raw_text
            or "我没看懂你现在在哪个平台" in raw_text
        ):
            tag = "error"
        elif (
            "执行成功" in raw_text
            or "报表生成成功" in raw_text
            or "已附着浏览器" in raw_text
            or "已打开输出目录" in raw_text
        ):
            tag = "success"

        self.status_text.config(state="normal")
        if tag:
            self.status_text.insert(tk.END, f"{formatted}\n", tag)
        else:
            self.status_text.insert(tk.END, f"{formatted}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state="disabled")

    def run(self) -> None:
        """
        启动 GUI 主循环。
        """
        self.root.mainloop()


if __name__ == "__main__":
    AppGUI().run()
