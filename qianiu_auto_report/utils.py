"""
通用工具模块。
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from qianiu_auto_report.config import DateConfig


def ensure_directory(path: Path) -> Path:
    """
    确保目录存在并返回目录路径。
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_previous_date(
    now: date | datetime | None = None,
    offset_days: int = 1,
) -> date:
    """
    获取前 N 天日期，默认前一天。
    """
    if offset_days < 0:
        raise ValueError("offset_days 不能为负数。")

    if now is None:
        base_date = date.today()
    elif isinstance(now, datetime):
        base_date = now.date()
    else:
        base_date = now

    return base_date - timedelta(days=offset_days)


def get_previous_date_str(
    now: date | datetime | None = None,
    offset_days: int = 1,
    date_format: str = DateConfig.DATE_FORMAT,
) -> str:
    """
    获取前 N 天日期字符串，默认格式 YYYY-MM-DD。
    """
    return get_previous_date(now=now, offset_days=offset_days).strftime(date_format)


def get_timestamp_str(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """
    获取当前时间字符串。
    """
    return datetime.now().strftime(fmt)


def build_output_filename(prefix: str, suffix: str) -> str:
    """
    生成输出文件名，自动附加时间戳。
    """
    safe_prefix = normalize_text(prefix) or "output"
    safe_suffix = normalize_text(suffix) or ".txt"
    if not safe_suffix.startswith("."):
        safe_suffix = f".{safe_suffix}"
    return f"{safe_prefix}_{get_timestamp_str()}{safe_suffix}"


def resolve_resource_path(relative_path: str) -> Path:
    """
    解析资源文件路径，兼容开发环境和 exe 打包环境。
    """
    if hasattr(sys, "_MEIPASS"):
        base_dir = Path(getattr(sys, "_MEIPASS"))
    else:
        base_dir = Path(__file__).resolve().parent.parent
    return (base_dir / relative_path).resolve()


def validate_file_exists(file_path: Path) -> bool:
    """
    校验文件是否存在且为普通文件。
    """
    return Path(file_path).is_file()


def get_latest_file(
    directory: Path,
    suffixes: tuple[str, ...] = (".xlsx", ".xls", ".xlsm", ".et"),
    ignore_prefixes: tuple[str, ...] = ("~$",),
    recursive: bool = False,
) -> Path:
    """
    获取目录中最新文件。
    """
    target = Path(directory)
    if not target.exists():
        raise FileNotFoundError(f"目录不存在：{target}")
    if not target.is_dir():
        raise ValueError(f"不是目录：{target}")

    iterator = target.rglob("*") if recursive else target.iterdir()
    candidates: list[Path] = []
    allowed_suffixes = tuple(item.lower() for item in suffixes)

    for file_path in iterator:
        if not file_path.is_file():
            continue
        if ignore_prefixes and file_path.name.startswith(ignore_prefixes):
            continue
        if allowed_suffixes and file_path.suffix.lower() not in allowed_suffixes:
            continue
        candidates.append(file_path)

    if not candidates:
        suffix_text = ", ".join(allowed_suffixes) if allowed_suffixes else "任意"
        raise FileNotFoundError(f"目录 {target} 下未找到匹配文件（后缀：{suffix_text}）。")

    return max(candidates, key=lambda item: item.stat().st_mtime)


def snapshot_directory(directory: Path) -> dict[str, tuple[int, int]]:
    """
    获取目录文件快照。
    返回值结构：{文件名: (文件大小, 修改时间纳秒)}
    """
    snapshot: dict[str, tuple[int, int]] = {}
    for file_path in Path(directory).iterdir():
        try:
            if file_path.is_file():
                stat = file_path.stat()
                snapshot[file_path.name] = (stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            continue
    return snapshot


def wait_for_download_complete(
    directory: Path,
    timeout_seconds: int = 60,
    poll_interval_seconds: float = 1.0,
    start_time: Optional[float] = None,
    previous_snapshot: Optional[dict[str, tuple[int, int]]] = None,
    temp_suffixes: tuple[str, ...] = (".crdownload", ".part", ".tmp"),
    file_filter: Optional[Callable[[Path], bool]] = None,
) -> Path:
    """
    等待目录中新下载文件完成并返回文件路径。
    """
    target_dir = Path(directory)
    if not target_dir.exists():
        raise FileNotFoundError(f"目录不存在：{target_dir}")
    if not target_dir.is_dir():
        raise ValueError(f"不是目录：{target_dir}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须大于 0。")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds 必须大于 0。")

    timeout_at = time.time() + timeout_seconds
    trigger_ts = start_time if start_time is not None else time.time()
    trigger_ts_ns = int(trigger_ts * 1_000_000_000)
    baseline = previous_snapshot if previous_snapshot is not None else snapshot_directory(target_dir)
    stable_size_cache: dict[str, int] = {}

    while time.time() < timeout_at:
        all_files: list[Path] = []
        for file_path in target_dir.iterdir():
            try:
                if file_path.is_file():
                    all_files.append(file_path)
            except FileNotFoundError:
                continue
        active_temp_files: list[Path] = []
        for file_path in all_files:
            if file_path.suffix.lower() not in temp_suffixes:
                continue
            try:
                stat = file_path.stat()
            except FileNotFoundError:
                # Chrome 可能在本轮轮询中刚好把临时文件重命名掉，属于正常竞态。
                continue
            old_size, old_mtime_ns = baseline.get(file_path.name, (None, None))
            # 仅把“本次任务期间新增或发生变化”的临时文件视作阻塞条件。
            if old_size is None or old_mtime_ns is None:
                if stat.st_mtime_ns >= trigger_ts_ns - int(3e9):
                    active_temp_files.append(file_path)
                continue
            if stat.st_size != old_size or stat.st_mtime_ns != old_mtime_ns:
                active_temp_files.append(file_path)

        candidates: list[Path] = []
        for file_path in all_files:
            if file_path.suffix.lower() in temp_suffixes:
                continue
            if file_filter is not None and not file_filter(file_path):
                continue

            try:
                stat = file_path.stat()
            except FileNotFoundError:
                continue
            if file_path.name not in baseline:
                candidates.append(file_path)
                continue

            old_size, old_mtime_ns = baseline.get(file_path.name, (None, None))
            if old_size is None or old_mtime_ns is None:
                continue
            if stat.st_size != old_size or stat.st_mtime_ns != old_mtime_ns:
                candidates.append(file_path)

        if not candidates or active_temp_files:
            time.sleep(poll_interval_seconds)
            continue

        latest: Path | None = None
        latest_mtime: float | None = None
        for item in candidates:
            try:
                item_stat = item.stat()
            except FileNotFoundError:
                continue
            if latest is None or item_stat.st_mtime > (latest_mtime or float("-inf")):
                latest = item
                latest_mtime = item_stat.st_mtime

        if latest is None:
            time.sleep(poll_interval_seconds)
            continue

        try:
            current_size = latest.stat().st_size
        except FileNotFoundError:
            time.sleep(poll_interval_seconds)
            continue
        previous_size = stable_size_cache.get(latest.name)
        if previous_size is not None and previous_size == current_size:
            return latest

        stable_size_cache[latest.name] = current_size
        time.sleep(poll_interval_seconds)

    raise TimeoutError(f"下载超时：{target_dir}")


def safe_log(message: str, level: str = "info") -> None:
    """
    日志打印函数。
    """
    logger = logging.getLogger("qianiu_auto_report")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    normalized_level = normalize_text(level).lower()
    log_method = getattr(logger, normalized_level, logger.info)
    log_method(message)


def normalize_text(value: Optional[str]) -> str:
    """
    统一文本清洗。
    """
    if value is None:
        return ""
    return str(value).strip()
