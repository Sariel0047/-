"""
GUI 状态流转与文案回归测试。
"""

from __future__ import annotations

import importlib
import sys
import types

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


def _load_gui_with_dependency_stubs(monkeypatch: object) -> type:
    """
    GUI 状态测试不需要真实 Selenium/pandas，只加载界面方法本身。
    """
    for module_name, class_name in (
        ("qianiu_auto_report.web_export", "WebExporter"),
        ("qianiu_auto_report.data_process", "DataProcessor"),
        ("qianiu_auto_report.excel_writer", "ExcelWriter"),
    ):
        module = types.ModuleType(module_name)
        setattr(
            module,
            class_name,
            type(class_name, (), {"__init__": lambda self, *args, **kwargs: None}),
        )
        monkeypatch.setitem(sys.modules, module_name, module)  # type: ignore[attr-defined]

    sys.modules.pop("qianiu_auto_report.gui", None)
    gui_module = importlib.import_module("qianiu_auto_report.gui")
    return gui_module.AppGUI


class _FakeVar:
    """
    避免创建真实 Tk 窗口，只模拟 StringVar 的 set 行为。
    """

    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _FakeGUI:
    """
    只提供 _set_ui_state 需要访问的最小界面对象。
    """

    def __init__(self) -> None:
        self.ui_state = GUIState.IDLE
        self.status_var = _FakeVar()
        self.hint_var = _FakeVar()
        self.synced = False
        self.busy = False

    def _sync_controls(self) -> None:
        self.synced = True

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy


class _FakeExporter:
    """
    模拟浏览器导出器，用于验证附着失败后的自动打开浏览器兜底。
    """

    def __init__(self, *, attach_to_existing_browser: bool, fail_on_init: bool = False) -> None:
        self.attach_to_existing_browser = attach_to_existing_browser
        self.fail_on_init = fail_on_init
        self.init_called = False
        self.open_called = False
        self.closed = False

    def init_driver(self, download_dir: object) -> None:
        self.init_called = True
        if self.fail_on_init:
            raise RuntimeError("附着已打开浏览器失败：调试端口不可连接。")

    def open_login_page(self) -> None:
        self.open_called = True

    def close(self) -> None:
        self.closed = True


class _FakeBrowserGUI:
    """
    只模拟报表执行前附着浏览器需要的 AppGUI 属性和方法。
    """

    def __init__(self) -> None:
        self.attach_mode = True
        self.created: list[_FakeExporter] = []
        self.platforms: list[str] = []

    def _create_web_exporter(self, *, attach_to_existing_browser: bool | None = None) -> _FakeExporter:
        attach = True if attach_to_existing_browser is None else attach_to_existing_browser
        exporter = _FakeExporter(
            attach_to_existing_browser=attach,
            fail_on_init=attach,
        )
        self.created.append(exporter)
        return exporter

    def _apply_platform_context(self, exporter: _FakeExporter, platform: str) -> None:
        self.platforms.append(platform)


class _FakeRoot:
    """
    Tk root.after 的同步测试替身。
    """

    def __init__(self) -> None:
        self.configured_menu = None

    def after(self, delay_ms: int, callback: object, *args: object) -> None:
        callback(*args)  # type: ignore[misc]

    def config(self, **kwargs: object) -> None:
        self.configured_menu = kwargs.get("menu")


class _FakeLaunchGUI:
    """
    模拟“开始生成”阶段：只唤起浏览器，不初始化 Selenium。
    """

    def __init__(self, output_dir: object) -> None:
        self.output_dir = output_dir
        self.web_exporter = None
        self.root = _FakeRoot()
        self.launched = 0
        self.states: list[tuple[GUIState, str | None]] = []
        self.logs: list[str] = []
        self.refreshed = False

    def _get_selected_platform(self) -> str:
        return "auto"

    def _launch_work_browser(self) -> list[str]:
        self.launched += 1
        return ["open", "-na", "Google Chrome"]

    def _refresh_header_badges(self) -> None:
        self.refreshed = True

    def _set_ui_state(self, state: GUIState, status: str | None = None) -> None:
        self.states.append((state, status))

    def append_log(self, message: str) -> None:
        self.logs.append(message)


class _ContextExporter:
    """
    模拟平台上下文写入时需要的导出器字段。
    """

    def __init__(self, *, attach_to_existing_browser: bool) -> None:
        self.attach_to_existing_browser = attach_to_existing_browser
        self.export_url = "https://myseller.taobao.com/home.htm/QnworkbenchHome/"
        self.expected_url_prefix = "https://myseller.taobao.com/"
        self.login_url = ""


def test_gui_state_labels_match_formal_copy() -> None:
    """
    主按钮和状态提示应与正式文案一致。
    """
    assert get_primary_button_label(GUIState.IDLE) == "开始生成"
    assert get_primary_button_label(GUIState.BROWSER_READY) == "我已登录，开始生成报表"
    assert get_primary_button_label(GUIState.RUNNING) == "正在处理，请稍等"
    assert get_primary_button_label(GUIState.FINISHED) == "重新开始"

    assert get_status_prompt(GUIState.IDLE) == '请先点击“开始生成”，我会帮你打开工作浏览器。'
    assert get_status_prompt(GUIState.STARTING) == '我先帮你打开工作浏览器，请稍等。'
    assert get_status_prompt(GUIState.BROWSER_READY) == '浏览器已经打开，请在这个窗口里登录。登录完成后，点“我已登录，开始生成报表”。'
    assert get_status_prompt(GUIState.RUNNING) == '我正在帮你整理报表，请不要关闭窗口。'
    assert get_status_prompt(GUIState.FINISHED) == '完成了，报表已经保存到桌面。'


def test_gui_state_hints_and_buttons_follow_expected_flow() -> None:
    """
    辅助提示与按钮可用性应符合状态流转表。
    """
    assert get_hint_prompt(GUIState.IDLE).startswith("平台不确定")
    assert get_hint_prompt(GUIState.RUNNING).startswith("运行中")
    assert is_primary_enabled(GUIState.IDLE) is True
    assert is_primary_enabled(GUIState.STARTING) is False
    assert is_primary_enabled(GUIState.RUNNING) is False
    assert is_reopen_enabled(GUIState.IDLE) is True
    assert is_reopen_enabled(GUIState.RUNNING) is False
    assert REOPEN_BROWSER_BUTTON_LABEL == "重新打开工作浏览器"
    assert EXIT_BUTTON_LABEL == "退出"


def test_gui_state_friendly_error_messages_hide_technical_terms() -> None:
    """
    错误提示应转成人话，不直接暴露 Selenium/端口/URL 术语。
    """
    assert friendly_error_message("无法自动判定平台。请显式选择...") == '我没看懂你现在在哪个平台，请手动选择“淘宝”或“抖音”。'
    assert friendly_error_message("附着已打开浏览器失败：调试端口不可连接。") == "我没找到可用的浏览器，我再试一次。"
    assert friendly_error_message("TimeoutException: 下载超时，未检测到完整文件") == "我这次没等到文件准备好，你可以点“重新打开工作浏览器”再试一次。"


def test_set_ui_state_accepts_root_after_style_status_argument(monkeypatch: object) -> None:
    """
    root.after 会把回调参数按位置传入，状态文案必须支持这种调用方式。
    """
    AppGUI = _load_gui_with_dependency_stubs(monkeypatch)
    fake = _FakeGUI()
    AppGUI._set_ui_state(fake, GUIState.BROWSER_READY, "浏览器已经打开")

    assert fake.ui_state == GUIState.BROWSER_READY
    assert fake.status_var.value == "浏览器已经打开"
    assert fake.synced is True
    assert fake.busy is False


def test_open_login_worker_only_launches_debug_browser(monkeypatch: object, tmp_path: object) -> None:
    """
    点击开始时只唤起 9222 工作浏览器，不提前初始化 Selenium。
    """
    AppGUI = _load_gui_with_dependency_stubs(monkeypatch)
    fake = _FakeLaunchGUI(tmp_path)

    AppGUI._open_login_page_worker(fake)

    assert fake.launched == 1
    assert fake.web_exporter is None
    assert fake.refreshed is True
    assert fake.states == [
        (GUIState.BROWSER_READY, '浏览器已经打开，请在这个窗口里登录。登录完成后，点“我已登录，开始生成报表”。')
    ]


def test_build_menu_adds_independent_order_export_entry(monkeypatch: object) -> None:
    """
    主界面应只通过菜单打开独立订单导出窗口，不改原运行设置板块。
    """
    AppGUI = _load_gui_with_dependency_stubs(monkeypatch)

    created_commands: list[tuple[str, object]] = []

    class _FakeMenu:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.items: list[tuple[str, object]] = []

        def add_cascade(self, **kwargs: object) -> None:
            self.items.append(("cascade", kwargs))

        def add_command(self, **kwargs: object) -> None:
            self.items.append(("command", kwargs))
            created_commands.append((str(kwargs.get("label")), kwargs.get("command")))

    fake = type("FakeGUI", (), {})()
    fake.root = _FakeRoot()
    fake.order_export_window = None
    fake.open_order_export_window = lambda: None

    monkeypatch.setattr("qianiu_auto_report.gui.tk.Menu", _FakeMenu)

    AppGUI._build_menu(fake)

    assert fake.root.configured_menu is not None
    assert created_commands
    assert created_commands[0][0] == "已卖出宝贝订单导出"
    assert callable(created_commands[0][1])


def test_auto_platform_context_keeps_default_url_for_managed_browser(monkeypatch: object) -> None:
    """
    兜底打开新浏览器时，自动识别模式不能清空默认入口 URL。
    """
    AppGUI = _load_gui_with_dependency_stubs(monkeypatch)
    fake = _FakeBrowserGUI()
    exporter = _ContextExporter(attach_to_existing_browser=False)

    AppGUI._apply_platform_context(fake, exporter, "auto")

    assert exporter.export_url == "https://myseller.taobao.com/home.htm/QnworkbenchHome/"
    assert exporter.expected_url_prefix == "https://myseller.taobao.com/"


def test_taobao_platform_context_restores_default_urls_after_auto_attach(monkeypatch: object) -> None:
    """
    附着模式自动识别会先放宽 URL；识别为淘宝后必须恢复默认入口，避免导出配置为空。
    """
    AppGUI = _load_gui_with_dependency_stubs(monkeypatch)
    fake = _FakeBrowserGUI()
    exporter = _ContextExporter(attach_to_existing_browser=True)
    exporter.export_url = ""
    exporter.expected_url_prefix = ""

    AppGUI._apply_platform_context(fake, exporter, "taobao")

    assert exporter.export_url == "https://myseller.taobao.com/home.htm/QnworkbenchHome/"
    assert exporter.expected_url_prefix == "https://myseller.taobao.com/"
