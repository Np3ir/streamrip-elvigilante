import logging
import sys
import os
from typing import Callable

# Enable ANSI colors on Windows consoles
os.system("")

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.rule import Rule
from rich.text import Text

logger = logging.getLogger("streamrip")

# Use stderr and force terminal to ensure visibility on Windows/PowerShell
_console = Console(file=sys.stderr, force_terminal=True, force_interactive=True)


class ProgressManager:
    """
    Rich 'Live' progress manager - Text Only (White).
    
    No bars, no numbers. Just the list of what's happening.
    ── Processing: 3 items... ──
    ⠋ [FLAC 24/96] Artist - Track
    """

    def __init__(self):
        self.started = False
        self.task_titles: list[str] = []

        self.progress = Progress(
            # 1. Spinner in White (Indicator of life)
            SpinnerColumn(spinner_name="dots", style="bold white"),
            
            # 2. Description in White (The only info)
            TextColumn("[bold white]{task.description}"),
            
            # REMOVED: BarColumn. 
            # Now it's just text.
            
            console=_console,
            transient=False,
            expand=False, # Don't stretch, just list them nicely
        )

        self._header = self._build_header()

        self.live = Live(
            Group(self._header, self.progress),
            console=_console,
            refresh_per_second=10,
            transient=False,
        )

    def _build_header(self) -> Rule:
        titles = ", ".join(self.task_titles[:3])
        if len(self.task_titles) > 3:
            titles += "..."
        
        # Clean White Header
        header_text = Text("Processing: ", style="dim white") + Text(titles, style="bold white")
        return Rule(header_text, style="white")

    def _refresh(self):
        self._header = self._build_header()
        if self.started:
            try:
                self.live.update(Group(self._header, self.progress))
            except Exception:
                pass

    def _ensure_started(self):
        if not self.started:
            try:
                self.live.start()
                self.started = True
            except Exception:
                pass

    def add_title(self, title: str):
        title = (title or "").strip()
        if title:
            self.task_titles.append(title)
            self._refresh()

    def remove_title(self, title: str):
        title = (title or "").strip()
        if title in self.task_titles:
            self.task_titles.remove(title)
            self._refresh()

    def cleanup(self):
        if self.started:
            try:
                self.live.stop()
            except Exception:
                pass
        self.started = False

    def get_callback(self, total: int, description: str) -> Callable[[int], None]:
        self._ensure_started()

        # Handle unknown totals safely
        rich_total = int(total) if total and total > 0 else None
        
        task_id = self.progress.add_task(description, total=rich_total)

        # State to track the last absolute position
        state = {"last_abs": 0}

        def callback(current_bytes: int):
            try:
                current = int(current_bytes or 0)
            except Exception:
                current = 0

            # FORCE ABSOLUTE LOGIC
            delta = current - state["last_abs"]
            if delta < 0: 
                delta = 0
            state["last_abs"] = current

            try:
                # We still 'advance' the task internally so Rich knows it's working
                self.progress.update(task_id, advance=delta)
            except Exception:
                pass

            # Finish detection
            if rich_total is not None and current >= rich_total:
                try:
                    self.progress.update(task_id, visible=False)
                except Exception:
                    pass

            self._refresh()

        return callback


# Global Instance
_pm = ProgressManager()


def get_progress():
    return _pm.progress


def add_title(description: str):
    _pm.add_title(description)


def remove_title(description: str):
    _pm.remove_title(description)


def get_progress_callback(enabled: bool, total_size: int, description: str = ""):
    return _pm.get_callback(int(total_size or 0), str(description or ""))


def clear_progress():
    _pm.cleanup()