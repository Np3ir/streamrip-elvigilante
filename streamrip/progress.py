import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.text import Text

from .console import console

logger = logging.getLogger("streamrip")


class _MissingFileWarningFilter(logging.Filter):
    """
    Captures + suppresses the noisy warning:
      "Track in database but file missing. Re-downloading: ..."
    so it doesn't spam the console while Live is running.

    It also forwards a clean deduped message into ProgressManager.
    """

    def __init__(self, pm: "ProgressManager"):
        super().__init__()
        self.pm = pm

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.levelno < logging.WARNING:
                return True

            msg = record.getMessage() or ""
            if "Track in database but file missing" in msg:
                # Clean it up (keep it short + useful)
                clean = "Track in DB but file missing — re-downloading"
                self.pm.add_warning(clean)
                return False  # suppress printing
        except Exception:
            # If anything goes wrong, do not break logging
            return True

        return True


class ProgressManager:
    """
    Clean + compatible UI (works on older Rich too):
    - Manual truncation (no overflow/no_wrap args)
    - Header + bars in one Live
    - Throttled updates to reduce flicker
    - Deduped warning summary shown above progress bars
    - Suppresses the specific noisy warning via logging.Filter (progress.py only)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.started = False

        self.task_titles: list[str] = []

        # warning_cache: message -> count
        self.warning_cache: Dict[str, int] = {}
        self._warning_last_update = 0.0
        self._warning_refresh_interval = 0.25  # reduce re-render spam

        # Use ONLY ProgressColumn objects here
        self.progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(text_format="{task.percentage:>3.0f}%"),
            TextColumn("•", style="dim"),
            TransferSpeedColumn(),
            TextColumn("•", style="dim"),
            TimeRemainingColumn(),
            console=console,
        )

        # Header prefix (minimal color)
        self.prefix = Text.assemble(("Downloading ", "bold cyan"))

        self.live = Live(
            self._renderable(),
            console=console,
            refresh_per_second=10,
            transient=True,
            auto_refresh=True,
        )

        # Throttle per task to reduce heavy redraw spam
        self._last_task_update: dict[int, float] = {}
        self._min_update_interval = 0.04  # seconds

        # Install filter to suppress the noisy warning from anywhere in streamrip
        self._install_warning_filter()

    # ---------- logging filter installation ----------

    def _install_warning_filter(self):
        try:
            target_logger = logging.getLogger("streamrip")
            # Avoid double-install if module reloaded
            for f in list(getattr(target_logger, "filters", [])):
                if isinstance(f, _MissingFileWarningFilter):
                    return
            target_logger.addFilter(_MissingFileWarningFilter(self))
        except Exception as e:
            logger.debug(f"Failed to install warning filter: {e}")

    # ---------- helpers ----------

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _renderable(self):
        blocks = []

        rule = self._gen_title_rule()
        if rule is not None:
            blocks.append(rule)

        warn_block = self._gen_warning_block()
        if warn_block is not None:
            blocks.append(warn_block)

        blocks.append(self.progress)
        return Group(*blocks)

    def _update_live(self, force: bool = False):
        try:
            if self.started:
                self.live.update(self._renderable(), refresh=force)
        except Exception as e:
            logger.debug(f"Live update failed: {e}")

    # ---------- warnings UI ----------

    def add_warning(self, message: str):
        """
        Dedup + count warnings and show a short summary above progress bars.
        Safe to call even before Live starts.
        """
        message = self._truncate((message or "").strip() or "Warning", 78)

        with self._lock:
            self.warning_cache[message] = self.warning_cache.get(message, 0) + 1

        now = time.monotonic()
        # Throttle UI refresh
        if now - self._warning_last_update >= self._warning_refresh_interval:
            self._warning_last_update = now
            self._update_live(force=False)

    def _gen_warning_block(self) -> Optional[Group]:
        if not self.warning_cache:
            return None

        # Show up to 2 lines to keep UI clean
        items = list(self.warning_cache.items())
        shown = items[:2]
        more = len(items) - len(shown)

        lines = []
        for msg, count in shown:
            suffix = f" (x{count})" if count > 1 else ""
            lines.append(Text(f"⚠ {msg}{suffix}", style="yellow"))

        if more > 0:
            lines.append(Text(f"⚠ {more} more warning(s) hidden…", style="dim yellow"))

        return Group(*lines)

    # ---------- public API ----------

    def get_callback(self, total: int, desc: str):
        desc = self._truncate((desc or "").strip() or "Downloading...", 52)

        with self._lock:
            if not self.started:
                try:
                    self.live.update(self._renderable(), refresh=True)
                    self.live.start()
                    self.started = True
                except Exception as e:
                    logger.debug(f"Failed to start Live: {e}")

        task = self.progress.add_task(desc, total=total)

        def _callback_update(x: int):
            try:
                now = time.monotonic()
                last = self._last_task_update.get(task, 0.0)
                if now - last < self._min_update_interval:
                    return
                self._last_task_update[task] = now

                self.progress.update(task, advance=x)
            except Exception as e:
                logger.debug(f"Progress update failed: {e}")

        def _callback_done():
            try:
                self.progress.remove_task(task)
                self._last_task_update.pop(task, None)
            except Exception as e:
                logger.debug(f"Progress cleanup failed: {e}")

        return Handle(_callback_update, _callback_done)

    def cleanup(self):
        with self._lock:
            if self.started:
                try:
                    self.live.stop()
                except Exception as e:
                    logger.debug(f"Failed to stop Live: {e}")
                finally:
                    self.started = False
                    self._last_task_update.clear()
                    # keep warning_cache? usually yes, but cleanup should reset UI
                    self.warning_cache.clear()

    def add_title(self, title: str):
        title = (title or "").strip()
        if not title:
            return

        with self._lock:
            if title not in self.task_titles:
                self.task_titles.append(title)

        self._update_live()

    def remove_title(self, title: str):
        title = (title or "").strip()
        if not title:
            return

        with self._lock:
            if title in self.task_titles:
                self.task_titles.remove(title)

        self._update_live()

    def _gen_title_rule(self):
        if not self.task_titles:
            return None

        shown = [self._truncate(t, 34) for t in self.task_titles[:2]]
        titles = ", ".join(shown)
        if len(self.task_titles) > 2:
            titles += "..."

        return Rule(self.prefix + Text(titles))


@dataclass(slots=True)
class Handle:
    update: Callable[[int], None]
    done: Callable[[], None]

    def __enter__(self):
        return self.update

    def __exit__(self, *_):
        self.done()


# -------- global API --------

_p = ProgressManager()


def get_progress_callback(enabled: bool, total: int, desc: str) -> Handle:
    if not enabled:
        return Handle(lambda _: None, lambda: None)
    return _p.get_callback(total, desc)


def add_title(title: str):
    _p.add_title(title)


def remove_title(title: str):
    _p.remove_title(title)


def clear_progress():
    _p.cleanup()
