# Cross-Border Log Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cross-border fee collection flow say what it actually reads: the target business row amount, not the page total.

**Architecture:** Keep the accounting logic unchanged. Only align the final user-facing log label with the existing bounded extraction path, and add a regression assertion so the message cannot drift back to “扣费金额合计” when the code is reading the business row.

**Tech Stack:** Python, pytest, Selenium test doubles.

---

### Task 1: Align the cross-border fee log message

**Files:**
- Modify: `qianiu_auto_report/web_export.py:6359-6364`
- Modify: `tests/test_web_export_status.py:465-490`

- [ ] **Step 1: Write the failing test**

```python
assert any("淘宝天猫跨境服务增值费本月付款" in item for item in calls)
```

- [ ] **Step 2: Run the focused test to verify the old wording is missing**

Run: `python -m pytest -q tests/test_web_export_status.py -k cross_border`
Expected: PASS after the log label is corrected, with no assertion on the old “扣费金额合计” wording.

- [ ] **Step 3: Update the production log line**

```python
self._log_step(f"收支账单淘宝天猫跨境服务增值费本月付款：{fee_total}")
```

- [ ] **Step 4: Run the focused regression plus broader smoke tests**

Run: `python -m pytest -q tests/test_web_export_status.py tests/test_main_platform.py tests/test_excel_writer.py tests/test_utils.py tests/test_gui_state.py tests/test_gui_text.py`
Expected: all tests pass.

