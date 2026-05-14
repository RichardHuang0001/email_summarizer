#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的终端输出模块 - 提供美观、清晰、结构化的控制台输出
"""

import os
import sys
import shutil
import textwrap


# --- ANSI 颜色定义 ---
class _Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"

    @staticmethod
    def supports_color():
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("FORCE_COLOR"):
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# --- 图标定义 ---
class _Icon:
    CHECK = "✓"
    CROSS = "✗"
    WARN = "⚠"
    INFO = "ℹ"
    ARROW = "↳"
    DOT = "•"
    STAR = "★"
    MAIL = "📧"
    GEAR = "⚙"
    CLOCK = "⏱"
    ROCKET = "🚀"
    PACKAGE = "📦"
    FILE = "📄"
    SEND = "📤"
    GLASS = "🔍"
    KEY = "🔐"
    LINK = "🔗"
    FOLDER = "📁"


class Console:
    """统一终端输出接口，所有方法均为静态方法"""

    _term_width = None
    _indent_level = 0

    # ============================================================
    # 内部工具
    # ============================================================

    @classmethod
    def _color(cls, text: str, color: str) -> str:
        if not _Color.supports_color():
            return text
        return f"{color}{text}{_Color.RESET}"

    @classmethod
    def _width(cls) -> int:
        if cls._term_width is None:
            cls._term_width = shutil.get_terminal_size((80, 24)).columns
        return cls._term_width

    @classmethod
    def _write(cls, text: str, end: str = "\n"):
        sys.stdout.write(text + end)
        sys.stdout.flush()

    @classmethod
    def _indent(cls) -> str:
        return "  " * cls._indent_level

    # ============================================================
    # 标题与分隔
    # ============================================================

    @classmethod
    def banner(cls, title: str):
        """渲染顶部横幅"""
        width = min(cls._width(), 58)
        inner = f"  {title}  "
        padded = inner.center(width - 2)
        line_top = "╔" + "═" * (width - 2) + "╗"
        line_bot = "╚" + "═" * (width - 2) + "╝"
        cls._write("")
        cls._write(cls._color(line_top, _Color.CYAN))
        cls._write(cls._color("║", _Color.CYAN) + cls._color(padded, _Color.BOLD) + cls._color("║", _Color.CYAN))
        cls._write(cls._color(line_bot, _Color.CYAN))
        cls._write("")

    @classmethod
    def step_header(cls, step: str):
        """渲染步骤标题，如: ── STEP 2/5  智能总结 ──"""
        width = min(cls._width() - 4, 54)
        text = f"  {step}  "
        line = "─" * max(4, (width - len(text)) // 2)
        header = line + text + line
        if len(header) < width:
            header += "─" * (width - len(header))
        cls._write("")
        cls._write(cls._color(header, _Color.BLUE + _Color.BOLD))

    @classmethod
    def divider(cls):
        """轻量分割线"""
        width = min(cls._width() - 4, 54)
        cls._write(cls._color("─" * width, _Color.DIM))

    @classmethod
    def blank(cls):
        cls._write("")

    # ============================================================
    # 状态消息
    # ============================================================

    @classmethod
    def ok(cls, message: str):
        cls._write(f"{cls._indent()}{cls._color(_Icon.CHECK, _Color.GREEN)}  {message}")

    @classmethod
    def fail(cls, message: str):
        cls._write(f"{cls._indent()}{cls._color(_Icon.CROSS, _Color.RED)}  {message}")

    @classmethod
    def warn(cls, message: str):
        cls._write(f"{cls._indent()}{cls._color(_Icon.WARN, _Color.YELLOW)}  {message}")

    @classmethod
    def info(cls, message: str):
        cls._write(f"{cls._indent()}{cls._color(_Icon.DOT, _Color.CYAN)}  {message}")

    @classmethod
    def step_ok(cls, message: str):
        """步骤级别的成功消息，缩进更多"""
        cls._write(f"{cls._indent()}  {cls._color(_Icon.CHECK, _Color.GREEN)}  {message}")

    @classmethod
    def step_fail(cls, message: str):
        cls._write(f"{cls._indent()}  {cls._color(_Icon.CROSS, _Color.RED)}  {message}")

    @classmethod
    def step_warn(cls, message: str):
        cls._write(f"{cls._indent()}  {cls._color(_Icon.WARN, _Color.YELLOW)}  {message}")

    @classmethod
    def step_info(cls, message: str):
        """子步骤提示"""
        cls._write(f"{cls._indent()}  {cls._color(_Icon.ARROW, _Color.DIM)}  {cls._color(message, _Color.DIM)}")

    # ============================================================
    # 结构化信息展示
    # ============================================================

    @classmethod
    def kv(cls, key: str, value: str):
        """键值对"""
        cls._write(f"{cls._indent()}  {cls._color(key, _Color.DIM)}: {value}")

    @classmethod
    def result_box(cls, title: str, lines: list):
        """成功/完成的结果框"""
        width = min(cls._width(), 58)
        cls._write("")
        cls._write(cls._color("╔" + "═" * (width - 2) + "╗", _Color.GREEN))
        cls._write(
            cls._color("║", _Color.GREEN)
            + cls._color(f"  {title}".ljust(width - 2), _Color.BOLD)
            + cls._color("║", _Color.GREEN)
        )
        cls._write(cls._color("╠" + "─" * (width - 2) + "╣", _Color.GREEN))
        for line in lines:
            cls._write(
                cls._color("║", _Color.GREEN)
                + f"  {line}".ljust(width - 2)
                + cls._color("║", _Color.GREEN)
            )
        cls._write(cls._color("╚" + "═" * (width - 2) + "╝", _Color.GREEN))
        cls._write("")

    @classmethod
    def error_box(cls, title: str, lines: list):
        """错误信息框"""
        width = min(cls._width(), 58)
        cls._write("")
        cls._write(cls._color("╔" + "═" * (width - 2) + "╗", _Color.RED))
        cls._write(
            cls._color("║", _Color.RED)
            + cls._color(f"  {title}".ljust(width - 2), _Color.BOLD)
            + cls._color("║", _Color.RED)
        )
        for line in lines:
            wrapped = textwrap.wrap(line, width=width - 4)
            for w in wrapped:
                cls._write(
                    cls._color("║", _Color.RED)
                    + f"  {w}".ljust(width - 2)
                    + cls._color("║", _Color.RED)
                )
        cls._write(cls._color("╚" + "═" * (width - 2) + "╝", _Color.RED))
        cls._write("")

    # ============================================================
    # 进度条
    # ============================================================

    @classmethod
    def progress_bar(cls, completed: int, total: int, elapsed: float = 0, prefix: str = ""):
        """渲染单行进度条: ▌▌▌▌▌▌▌░░░░  7/10  70%  12.3s"""
        if total == 0:
            return

        bar_width = 20
        filled = int(bar_width * completed / total)
        pct = int(completed * 100 / total)

        bar_filled = cls._color("█" * filled, _Color.CYAN)
        bar_empty = cls._color("░" * (bar_width - filled), _Color.DIM)
        bar = bar_filled + bar_empty

        status = f"{completed}/{total}  {pct}%"
        if elapsed > 0:
            status += f"  {_Icon.CLOCK} {elapsed:.1f}s"

        if prefix:
            line = f"{cls._indent()}  {prefix}  {bar}  {status}"
        else:
            line = f"{cls._indent()}  {bar}  {status}"

        # 使用 \r 实现同行刷新
        sys.stdout.write("\r" + line.ljust(cls._width()))
        sys.stdout.flush()

    @classmethod
    def progress_done(cls, completed: int, total: int, elapsed: float = 0):
        """进度条完成后的最终输出（换行）"""
        bar_width = 20
        pct = 100 if completed == total else int(completed * 100 / total)
        bar = cls._color("█" * bar_width, _Color.GREEN)

        parts = [f"{completed}/{total}  {pct}%"]
        if elapsed > 0:
            parts.append(f"{_Icon.CLOCK} {elapsed:.1f}s")

        line = f"{cls._indent()}  {bar}  {'  '.join(parts)}"
        sys.stdout.write("\r" + line.ljust(cls._width()) + "\n")
        sys.stdout.flush()

    @classmethod
    def progress_clear(cls):
        """清除当前进度行"""
        sys.stdout.write("\r" + " " * cls._width() + "\r")
        sys.stdout.flush()

    # ============================================================
    # 计数/统计
    # ============================================================

    @classmethod
    def count_badge(cls, count: int, label: str):
        """例如: 找到 [5] 封新邮件"""
        cls._write(
            f"{cls._indent()}  {cls._color(str(count), _Color.CYAN + _Color.BOLD)}  {label}"
        )

    @classmethod
    def stat_line(cls, items: list):
        """一行内的统计信息，用 | 分隔"""
        parts = []
        for label, value in items:
            parts.append(f"{cls._color(label, _Color.DIM)}: {cls._color(str(value), _Color.BOLD)}")
        cls._write(f"{cls._indent()}  {'  │  '.join(parts)}")

    # ============================================================
    # 错误展示（简短内联版，用于流程中）
    # ============================================================

    @classmethod
    def inline_error(cls, message: str):
        """流程中出现的错误，不打断流程"""
        cls._write(f"{cls._indent()}  {cls._color(_Icon.WARN, _Color.RED)}  {cls._color(message, _Color.RED)}")

    @classmethod
    def inline_warning(cls, message: str):
        """流程中的警告"""
        cls._write(f"{cls._indent()}  {cls._color(_Icon.WARN, _Color.YELLOW)}  {cls._color(message, _Color.YELLOW)}")
