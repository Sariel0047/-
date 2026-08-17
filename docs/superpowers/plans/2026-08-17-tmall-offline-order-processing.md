# Tmall Offline Order Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser-driven Tmall sold-order window with a local report picker that summarizes every valid product ID in the selected report.

**Architecture:** Keep `OrderExportWindow` as the main-window integration point, but make it a thin offline controller modeled on `DouyinOrderFileWindow`. Reuse `DataProcessor.save_tmall_sold_order_summary` without a product filter, keep Selenium modules unchanged, and make Tk window closure impossible while its worker is active.

**Tech Stack:** Python 3.11, Tkinter/ttk, pandas, openpyxl, xlrd, pytest

---

## File Structure

- Modify `pyproject.toml`: declare the already-required `xlrd` runtime dependency.
- Modify `qianiu_auto_report/order_export_gui.py`: replace browser/date/product controls and worker behavior with an offline file-processing controller.
- Modify `qianiu_auto_report/gui.py`: rename the feature menu entry and its docstring.
- Create `tests/test_order_export_gui.py`: cover offline request validation, output naming, worker delegation, running state, and close behavior without constructing real Tk windows.
- Modify `tests/test_gui_state.py`: update the existing behavioral main-menu test for the new Tmall label.

The aggregation implementation in `qianiu_auto_report/data_process.py` and browser implementation in `qianiu_auto_report/sold_order_exporter.py` remain unchanged.

### Task 1: Preserve Legacy Excel/WPS Support in Installed Builds

**Files:**
- Modify: `pyproject.toml:10-15`
- Test: `tests/test_data_process.py`

- [ ] **Step 1: Write the failing dependency metadata test**

Add an import for `tomllib` and a test that reads project metadata rather than relying on the current virtual environment:

```python
import tomllib


def test_project_dependencies_include_xlrd_for_legacy_tables() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dependencies = metadata["project"]["dependencies"]
    assert any(str(item).startswith("xlrd>=") for item in dependencies)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv-arm64/bin/python -m pytest -q tests/test_data_process.py::test_project_dependencies_include_xlrd_for_legacy_tables
```

Expected: FAIL because `pyproject.toml` does not currently list `xlrd`.

- [ ] **Step 3: Add the runtime dependency**

Add the same constraint already present in `requirements.txt`:

```toml
dependencies = [
    "selenium>=4.0.0",
    "pandas>=2.0.0",
    "openpyxl>=3.1.0",
    "xlrd>=2.0.1",
]
```

- [ ] **Step 4: Run the focused test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit the dependency metadata change**

```bash
git add pyproject.toml tests/test_data_process.py
git commit -m "build: include xlrd in project dependencies"
```

### Task 2: Convert the Tmall Window Controller to Offline Processing

**Files:**
- Modify: `qianiu_auto_report/order_export_gui.py`
- Create: `tests/test_order_export_gui.py`

- [ ] **Step 1: Write failing request-validation tests**

Create `tests/test_order_export_gui.py` with a lightweight variable double and table-suffix coverage:

```python
from datetime import datetime
from pathlib import Path

import pytest

from qianiu_auto_report.order_export_gui import OrderExportWindow


class _FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


@pytest.mark.parametrize("suffix", [".csv", ".xlsx", ".xls", ".xlsm", ".et"])
def test_get_request_accepts_supported_tmall_table_files(tmp_path: Path, suffix: str) -> None:
    input_file = tmp_path / f"tmall-orders{suffix}"
    input_file.write_bytes(b"placeholder")
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_file))})()

    assert OrderExportWindow._get_request(fake) == {"input_file": input_file}


def test_get_request_rejects_unsupported_file(tmp_path: Path) -> None:
    input_file = tmp_path / "tmall-orders.txt"
    input_file.write_text("placeholder", encoding="utf-8")
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_file))})()

    with pytest.raises(ValueError, match="csv/.xlsx/.xls/.xlsm/.et"):
        OrderExportWindow._get_request(fake)


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_get_request_rejects_paths_that_are_not_files(tmp_path: Path, kind: str) -> None:
    input_path = tmp_path / "orders.xlsx"
    if kind == "directory":
        input_path.mkdir()
    fake = type("FakeWindow", (), {"input_file_var": _FakeVar(str(input_path))})()

    with pytest.raises(ValueError, match="请选择一份天猫订单明细表"):
        OrderExportWindow._get_request(fake)
```

- [ ] **Step 2: Write failing output-name and worker-delegation tests**

Add tests that verify no product filter is passed:

```python
def test_build_output_path_uses_timestamp_only(tmp_path: Path, monkeypatch) -> None:
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 17, 12, 34, 56)

    monkeypatch.setattr("qianiu_auto_report.order_export_gui.datetime", _FixedDatetime)
    fake = type("FakeWindow", (), {"output_dir": tmp_path})()

    output = OrderExportWindow._build_output_path(fake)

    assert output == tmp_path / "天猫订单汇总_20260817_123456.xlsx"


def test_process_worker_summarizes_entire_input_file(tmp_path: Path, monkeypatch) -> None:
    input_file = tmp_path / "orders.xlsx"
    input_file.write_bytes(b"placeholder")
    output_file = tmp_path / "summary.xlsx"
    calls: list[tuple[Path, Path]] = []

    def fake_save(self, input_path: Path, output_path: Path) -> Path:
        calls.append((input_path, output_path))
        return output_path

    monkeypatch.setattr(
        "qianiu_auto_report.order_export_gui.DataProcessor.save_tmall_sold_order_summary",
        fake_save,
    )

    fake = _build_worker_window_double(tmp_path, output_file)
    OrderExportWindow._process_worker(fake, {"input_file": input_file})

    assert calls == [(input_file, output_file)]
    assert all(len(call) == 2 for call in calls)
```

Implement `_build_worker_window_double` in the same test file with an `after` method that immediately invokes callbacks, `_build_output_path` returning `output_file`, a `_FakeVar` status, a log collector, and a `_set_running` recorder. This keeps the test independent of a graphical display.

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```bash
.venv-arm64/bin/python -m pytest -q tests/test_order_export_gui.py
```

Expected: FAIL because the current window expects product IDs/dates and has no offline worker.

- [ ] **Step 4: Replace the controller state and request handling**

In `qianiu_auto_report/order_export_gui.py`:

- Import `filedialog` from Tkinter.
- Remove `BrowserConfig`, `DateConfig`, `build_work_browser_command`, and `SoldOrderExporter` imports.
- Replace product/date variables and exporter state with `self.input_file_var = tk.StringVar(value="")`.
- Initialize status with `请选择天猫宝贝销售明细报表，然后点击开始处理。`.
- Replace browser/export button fields with `choose_file_button` and `start_button`.
- Implement `_get_request` using `DataProcessor.SUPPORTED_TABLE_SUFFIXES` and the same supported-format message used by the Douyin window, adjusted for Tmall. Before checking the suffix, require both `input_file.exists()` and `input_file.is_file()` so missing paths and directories fail on the UI thread before worker startup.
- Implement `on_choose_file_clicked` with the supported suffix filters.
- Implement `on_start_clicked` to validate the request, enter running state, and launch `_process_worker` in a daemon thread.
- Implement `_build_output_path` as `天猫订单汇总_{timestamp}.xlsx`.

- [ ] **Step 5: Replace browser automation with the offline worker**

The worker must pass exactly the input and output paths so the processor includes all products:

```python
def _process_worker(self, request: dict[str, Path]) -> None:
    try:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        input_file = Path(request["input_file"])
        self.window.after(0, self.append_log, f"开始处理：{input_file.name}")
        output_file = self._build_output_path()
        DataProcessor().save_tmall_sold_order_summary(
            input_path=input_file,
            output_path=output_file,
        )
        self.window.after(0, self.status_var.set, "天猫订单汇总表已生成到桌面。")
        self.window.after(0, self.append_log, f"天猫订单汇总表已生成：{output_file.name}", "success")
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
```

- [ ] **Step 6: Run the offline controller tests**

Run the command from Step 3.

Expected: request, naming, and worker tests PASS.

- [ ] **Step 7: Run existing processor tests**

Run:

```bash
.venv-arm64/bin/python -m pytest -q tests/test_data_process.py tests/test_sold_order_exporter.py
```

Expected: PASS; aggregation behavior and preserved browser modules remain unchanged.

- [ ] **Step 8: Commit the offline controller**

```bash
git add qianiu_auto_report/order_export_gui.py tests/test_order_export_gui.py
git commit -m "feat: process tmall orders from local files"
```

### Task 3: Build the Offline UI and Protect Its Lifecycle

**Files:**
- Modify: `qianiu_auto_report/order_export_gui.py`
- Modify: `qianiu_auto_report/gui.py`
- Modify: `tests/test_order_export_gui.py`
- Modify: `tests/test_gui_state.py`

- [ ] **Step 1: Write failing lifecycle tests**

Use button, progress, status, and window doubles to call methods without Tk:

```python
def test_set_running_disables_all_actions_including_close() -> None:
    fake = _build_running_state_double()

    OrderExportWindow._set_running(fake, True, "正在处理")

    assert fake.running is True
    assert all(button.state == "disabled" for button in fake.buttons)
    assert fake.progressbar.started is True


def test_close_request_is_ignored_while_processing() -> None:
    fake = _build_close_window_double(running=True)

    OrderExportWindow._on_close(fake)

    assert fake.window.destroyed is False
    assert "处理完成" in fake.status_var.value


def test_close_request_destroys_idle_window() -> None:
    fake = _build_close_window_double(running=False)

    OrderExportWindow._on_close(fake)

    assert fake.window.destroyed is True
```

- [ ] **Step 2: Update the existing main-menu test to the new expected label**

In `tests/test_gui_state.py::test_build_menu_adds_independent_order_export_entry`, change the existing label assertion to:

```python
assert labels == ["天猫订单表处理", "抖音订单表处理"]
```

- [ ] **Step 3: Run the lifecycle and menu tests to verify they fail**

Run:

```bash
.venv-arm64/bin/python -m pytest -q tests/test_order_export_gui.py tests/test_gui_state.py
```

Expected: FAIL because close stays enabled, running close destroys the window, and the menu still says "已卖出宝贝订单导出".

- [ ] **Step 4: Rebuild the visible Tmall form**

Update `_build_window` and `_build_widgets`:

- Use title/header `天猫订单表处理`.
- Use description `导入天猫/淘宝宝贝销售明细报表，按商品 ID 汇总订单、金额和退款数据。`.
- Build an `订单明细表` row with a path entry and `选择文件` button.
- Retain the existing output-directory row.
- Use one primary `开始处理并生成汇总表` button and one `关闭` button.
- Retain status, progress, and log sections.
- Log `天猫订单表处理助手已打开。` after construction.
- Remove obsolete product/date widget helper methods.

- [ ] **Step 5: Implement the running and close policy**

In `_set_running`, set the same `disabled` or `normal` state on `choose_file_button`, `start_button`, `open_output_button`, and `close_button`. Start/stop the progressbar as before.

In `_on_close`:

```python
def _on_close(self) -> None:
    if self.running:
        self.status_var.set("订单表正在处理，请等待处理完成后再关闭。")
        return
    self.window.destroy()
```

- [ ] **Step 6: Rename the main-menu entry**

In `qianiu_auto_report/gui.py`, change the menu label to `天猫订单表处理` and update `open_order_export_window`'s docstring to describe the offline window. Keep the existing method and cached-window attribute names to avoid unrelated integration churn.

- [ ] **Step 7: Run lifecycle and menu tests**

Run the command from Step 3.

Expected: PASS.

- [ ] **Step 8: Run syntax and import checks**

Run:

```bash
.venv-arm64/bin/python -m compileall -q qianiu_auto_report tests
.venv-arm64/bin/python -c "from qianiu_auto_report.order_export_gui import OrderExportWindow; from qianiu_auto_report.gui import AppGUI"
```

Expected: both commands exit 0 with no output.

- [ ] **Step 9: Commit the UI and lifecycle change**

```bash
git add qianiu_auto_report/order_export_gui.py qianiu_auto_report/gui.py tests/test_order_export_gui.py tests/test_gui_state.py
git commit -m "feat: replace tmall export UI with offline processing"
```

### Task 4: Full Regression Verification

**Files:**
- No production changes expected
- Update tests only if verification exposes an in-scope regression

- [ ] **Step 1: Run the focused offline workflow suite**

```bash
.venv-arm64/bin/python -m pytest -q tests/test_order_export_gui.py tests/test_data_process.py tests/test_gui_state.py tests/test_main_platform.py
```

Expected: all tests PASS.

- [ ] **Step 2: Run the complete test suite**

```bash
.venv-arm64/bin/python -m pytest -q
```

Expected: all tests PASS with no failures.

- [ ] **Step 3: Check formatting and unintended changes**

```bash
git diff --check
git status --short
git diff --stat HEAD~3..HEAD
```

Expected: no whitespace errors; only the planned dependency, Tmall window, main-menu, and test files changed in the implementation commits.

- [ ] **Step 4: Perform a local GUI smoke test**

Run:

```bash
.venv-arm64/bin/python main.py
```

Verify manually:

1. `功能 -> 天猫订单表处理` opens the offline window.
2. The window contains a report picker and no browser, product-ID, or date controls.
3. A representative Tmall report generates `天猫订单汇总_<timestamp>.xlsx`.
4. All product IDs from the report appear in the output.
5. Controls are disabled while processing and restored afterward.

Stop the GUI after the smoke test. If no representative source report is available, record that the interactive file-processing check remains unverified rather than fabricating a result.

- [ ] **Step 5: Commit any verification-only test adjustment**

Only if Step 1 or Step 2 required an in-scope test correction:

```bash
git add tests
git commit -m "test: cover tmall offline workflow regression"
```

Otherwise, do not create an empty commit.
