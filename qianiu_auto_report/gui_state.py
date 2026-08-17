"""
GUI 状态与文案映射。
"""

from __future__ import annotations

from enum import Enum


class GUIState(str, Enum):
    """
    GUI 主流程状态。
    """

    IDLE = "idle"
    STARTING = "starting"
    BROWSER_READY = "browser_ready"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


PRIMARY_BUTTON_LABELS: dict[GUIState, str] = {
    GUIState.IDLE: "开始生成",
    GUIState.STARTING: "正在处理，请稍等",
    GUIState.BROWSER_READY: "我已登录，开始生成报表",
    GUIState.RUNNING: "正在处理，请稍等",
    GUIState.FINISHED: "重新开始",
    GUIState.ERROR: "重新开始",
}

STATUS_PROMPTS: dict[GUIState, str] = {
    GUIState.IDLE: '请先点击“开始生成”，我会帮你打开工作浏览器。',
    GUIState.STARTING: '我先帮你打开工作浏览器，请稍等。',
    GUIState.BROWSER_READY: '浏览器已经打开，请在这个窗口里登录。登录完成后，点“我已登录，开始生成报表”。',
    GUIState.RUNNING: '我正在帮你整理报表，请不要关闭窗口。',
    GUIState.FINISHED: '完成了，报表已经保存到桌面。',
    GUIState.ERROR: '我这边遇到了一点问题，你可以点“重新打开工作浏览器”再试一次。',
}

HINT_PROMPTS: dict[GUIState, str] = {
    GUIState.IDLE: "平台不确定就保持自动识别，默认会自动判断淘宝或抖音。",
    GUIState.STARTING: "我会先打开工作浏览器，你只需要等我一下。",
    GUIState.BROWSER_READY: "登录完成后回到这里点开始生成报表，我会接着帮你跑完。",
    GUIState.RUNNING: "运行中请不要手动切换页面，避免打断流程。",
    GUIState.FINISHED: "你可以先查看桌面上的文件，再重新开始。",
    GUIState.ERROR: "如果刚才没成功，可以点重新打开工作浏览器再试一次。",
}

REOPEN_BROWSER_BUTTON_LABEL = "重新打开工作浏览器"
EXIT_BUTTON_LABEL = "退出"


def normalize_state(state: GUIState | str) -> GUIState:
    """
    统一把状态值转成 GUIState。
    """
    if isinstance(state, GUIState):
        return state
    normalized = (state or "").strip().lower()
    try:
        return GUIState(normalized)
    except ValueError:
        return GUIState.IDLE


def get_primary_button_label(state: GUIState | str) -> str:
    """
    返回主按钮文案。
    """
    return PRIMARY_BUTTON_LABELS.get(normalize_state(state), "开始生成")


def get_status_prompt(state: GUIState | str) -> str:
    """
    返回状态提示文案。
    """
    return STATUS_PROMPTS.get(normalize_state(state), STATUS_PROMPTS[GUIState.IDLE])


def get_hint_prompt(state: GUIState | str) -> str:
    """
    返回辅助提示文案。
    """
    return HINT_PROMPTS.get(normalize_state(state), HINT_PROMPTS[GUIState.IDLE])


def is_primary_enabled(state: GUIState | str) -> bool:
    """
    判断主按钮是否可点击。
    """
    normalized = normalize_state(state)
    return normalized not in {GUIState.STARTING, GUIState.RUNNING}


def is_reopen_enabled(state: GUIState | str) -> bool:
    """
    判断“重新打开工作浏览器”是否可点击。
    """
    normalized = normalize_state(state)
    return normalized not in {GUIState.STARTING, GUIState.RUNNING}


def friendly_error_message(message: str) -> str:
    """
    将技术异常转成用户更容易理解的提示。
    """
    text = (message or "").strip()
    if not text:
        return "我这边遇到了一点问题，你可以点“重新打开工作浏览器”再试一次。"

    normalized = text.lower()
    if (
        "无法自动判定平台" in text
        or "平台判定" in text
        or "target_platform" in normalized
        or "jinritemai" in normalized
        or "taobao" in normalized
    ):
        return '我没看懂你现在在哪个平台，请手动选择“淘宝”或“抖音”。'

    if (
        "xlrd" in normalized
        or "openpyxl" in normalized
        or "excel file format" in normalized
        or "unsupported format" in normalized
        or "表格兼容组件" in text
    ):
        return "这份表格文件暂时无法读取，请确认已安装表格兼容组件，或另存为 .xlsx 后再试。"

    if (
        "调试端口" in text
        or "附着已打开浏览器失败" in text
        or "打开登录页失败" in text
        or "未检测到可用浏览器" in text
        or "chrome" in normalized
        or "driver" in normalized
    ):
        return "我没找到可用的浏览器，我再试一次。"

    if "下载超时" in text or "导出" in text:
        return "我这次没等到文件准备好，你可以点“重新打开工作浏览器”再试一次。"

    return "我这边遇到了一点问题，你可以点“重新打开工作浏览器”再试一次。"


def friendly_offline_error_message(message: str) -> str:
    """
    将离线表格处理异常转换为不依赖浏览器操作的提示。
    """
    text = (message or "").strip()
    normalized = text.lower()
    if not text:
        return "处理这份表格时遇到问题，请检查文件格式和内容后再试。"

    if (
        "xlrd" in normalized
        or "openpyxl" in normalized
        or "excel file format" in normalized
        or "unsupported format" in normalized
        or "表格兼容组件" in text
    ):
        return "这份表格文件暂时无法读取，请确认已安装表格兼容组件，或另存为 .xlsx 后再试。"

    if (
        "permission denied" in normalized
        or "errno 13" in normalized
        or "read-only" in normalized
        or "只读" in text
        or "被占用" in text
    ):
        return "无法写入汇总表，请关闭正在打开的同名文件，并确认输出目录可以写入后再试。"

    detail = text.splitlines()[-1].strip()
    if ":" in detail:
        prefix, candidate = detail.split(":", 1)
        if prefix.strip().endswith(("Error", "Exception")):
            detail = candidate.strip()
    if "缺少" in detail or "未找到" in detail:
        return f"{detail}。请确认选择的是平台导出的订单明细表。"

    return "处理这份表格时遇到问题，请检查文件格式、表格内容和文件是否被占用后再试。"
