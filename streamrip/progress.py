import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.text import Text
from rich.logging import RichHandler

from .console import console

logger = logging.getLogger("streamrip")


def _now() -> float:
    return time.monotonic()


# ============================================================
# LOGGING INTEGRATION
# ============================================================
def _setup_rich_logging():
    root_logger = logging.getLogger("streamrip")
    
    # Limpiamos handlers viejos
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    
    # Configuramos el handler bonito (Rich)
    rh = RichHandler(
        console=console, 
        show_time=True, 
        show_path=False, 
        markup=True,
        rich_tracebacks=True
    )
    root_logger.addHandler(rh)
    root_logger.setLevel(logging.INFO)
    
    # --- FIX: EVITAR DUPLICADOS ---
    # Esto evita que el mensaje suba al sistema base de Python
    root_logger.propagate = False 

_setup_rich_logging()


# ============================================================
# GLOBAL BUFFER
# ============================================================

_PM_REF: Optional["ProgressManager"] = None
_PENDING_ALBUM: Dict[str, Tuple[int, int, int]] = {}
_PENDING_GLOBAL: Dict[str, int] = {}


def _pending_bump_album(album: str, kind: str) -> None:
    album = (album or "Unknown album").strip() or "Unknown album"
    r, a, rd = _PENDING_ALBUM.get(album, (0, 0, 0))
    if kind == "registered":
        r += 1
    elif kind == "already":
        a += 1
    elif kind == "redownloaded":
        rd += 1
    _PENDING_ALBUM[album] = (r, a, rd)


def _pending_bump_global(label: str) -> None:
    label = (label or "").strip() or "Event"
    _PENDING_GLOBAL[label] = _PENDING_GLOBAL.get(label, 0) + 1


# ============================================================
# PROGRESS MANAGER
# ============================================================

class ProgressManager:
    def __init__(self):
        global _PM_REF

        self._lock = threading.Lock()
        self.started = False

        self.task_titles: list[str] = []
        self._current_album: Optional[str] = None

        self.album_stats: Dict[str, Tuple[int, int, int]] = {}
        self.album_last_touch: Dict[str, float] = {}

        self.global_stats: Dict[str, int] = {}

        self._stats_last_update = 0.0
        self._stats_refresh_interval = 0.25
        self._last_activity = _now()

        # --- PROGRESS BARS (Cyan/TiDDL Style) ---
        self.progress = Progress(
            SpinnerColumn(style="bold cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=None, style="dim cyan", complete_style="bold cyan", finished_style="bold green"),
            TransferSpeedColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            console=console,
        )

        self.prefix = Text.assemble(("Downloading ", "bold cyan"))

        self.live = Live(
            self._renderable(),
            console=console,
            refresh_per_second=10,
            transient=True,
            auto_refresh=True,
            redirect_stdout=False,
            redirect_stderr=False,
        )

        self._last_task_update: dict[int, float] = {}
        self._min_update_interval = 0.04

        _PM_REF = self
        self._merge_pending()

    def _merge_pending(self):
        try:
            for album, (r, a, rd) in list(_PENDING_ALBUM.items()):
                cr, ca, crd = self.album_stats.get(album, (0, 0, 0))
                self.album_stats[album] = (cr + r, ca + a, crd + rd)
                self.album_last_touch[album] = _now()
            _PENDING_ALBUM.clear()

            for label, cnt in list(_PENDING_GLOBAL.items()):
                self.global_stats[label] = self.global_stats.get(label, 0) + cnt
            _PENDING_GLOBAL.clear()
        except Exception:
            pass

    def _touch(self):
        self._last_activity = _now()

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _renderable(self):
        blocks = []
        rule = self._gen_title_rule()
        if rule is not None:
            blocks.append(rule)
        stats_block = self._gen_stats_block()
        if stats_block is not None:
            blocks.append(stats_block)
        blocks.append(self.progress)
        return Group(*blocks)

    def _update_live(self, force: bool = False):
        try:
            if self.started:
                self.live.update(self._renderable(), refresh=force)
        except Exception:
            pass

    def _album_key(self) -> str:
        if self._current_album:
            return self._current_album
        if self.task_titles:
            return self.task_titles[-1]
        return "Unknown album"

    def bump_album(self, kind: str):
        album = self._truncate(self._album_key().strip(), 48)
        with self._lock:
            r, a, rd = self.album_stats.get(album, (0, 0, 0))
            if kind == "registered":
                r += 1
            elif kind == "already":
                a += 1
            elif kind == "redownloaded":
                rd += 1
            self.album_stats[album] = (r, a, rd)
            self.album_last_touch[album] = _now()
        self._touch()
        self._maybe_refresh_stats()

    def bump_global(self, label: str):
        label = self._truncate(label.strip(), 48)
        with self._lock:
            self.global_stats[label] = self.global_stats.get(label, 0) + 1
        self._touch()
        self._maybe_refresh_stats()

    def _maybe_refresh_stats(self):
        now = _now()
        if now - self._stats_last_update >= self._stats_refresh_interval:
            self._stats_last_update = now
            self._update_live(force=False)

    def _gen_stats_block(self) -> Optional[Group]:
        lines = []
        active = len(getattr(self.progress, "tasks", []))
        if active > 0:
            lines.append(Text(f"🔵 Active downloads: {active}", style="bold cyan"))
        else:
            lines.append(Text("⚪ Waiting for downloads…", style="dim white"))

        if self.global_stats:
            label, count = sorted(self.global_stats.items(), key=lambda kv: kv[1], reverse=True)[0]
            suffix = f" (x{count})" if count > 1 else ""
            lines.append(Text(f"{label}{suffix}", style="yellow"))

        if self.album_stats:
            current = self._truncate((self._current_album or "").strip(), 48) or None
            albums_sorted = sorted(self.album_last_touch.items(), key=lambda kv: kv[1], reverse=True)
            recent = [name for name, _t in albums_sorted]
            shown = []
            if current and current in self.album_stats:
                shown.append(current)
            for name in recent:
                if name not in shown:
                    shown.append(name)
                if len(shown) >= 2:
                    break
            for album in shown:
                r, a, rd = self.album_stats.get(album, (0, 0, 0))
                parts = [f"reg {r}", f"exists {a}"]
                if rd:
                    parts.append(f"redl {rd}")
                style = "yellow" if rd else "cyan" 
                lines.append(Text(f"📀 {album} → " + " • ".join(parts), style=style))
            if len(self.album_stats) > len(shown):
                lines.append(Text("…more albums counted (hidden)", style="dim"))

        return Group(*lines) if lines else None

    def get_callback(self, total: int, desc: str):
        desc = self._truncate((desc or "").strip() or "Downloading...", 52)
        with self._lock:
            if not self.started:
                try:
                    self.live.start()
                    self.started = True
                except Exception:
                    pass

        # Add task with cyan coloring implied by initialization
        task_id = self.progress.add_task(desc, total=total)
        self._touch()
        self._update_live(force=False)

        def _callback_update(x: int):
            try:
                now = _now()
                last = self._last_task_update.get(task_id, 0.0)
                if now - last < self._min_update_interval:
                    return
                self._last_task_update[task_id] = now
                self.progress.update(task_id, advance=x)
                self._touch()
                
                # --- FIX: SAFE TASK LOOKUP (No get_task) ---
                task_completed = False
                for t in self.progress.tasks:
                    if t.id == task_id:
                        if t.total is not None and t.completed >= t.total:
                            task_completed = True
                        break
                
                if task_completed:
                    self.progress.remove_task(task_id)
                    self._last_task_update.pop(task_id, None)
                    self._touch()
                    self._update_live(force=False)
            except Exception:
                pass

        def _callback_done():
            try:
                self.progress.remove_task(task_id)
                self._last_task_update.pop(task_id, None)
                self._touch()
                self._update_live(force=False)
            except Exception:
                pass

        return Handle(_callback_update, _callback_done)

    def cleanup(self):
        global _PM_REF
        with self._lock:
            if self.started and not self.progress.tasks:
                try:
                    self.live.stop()
                except Exception:
                    pass
                finally:
                    self.started = False
                    self._last_task_update.clear()
                    self.task_titles.clear()
                    self._current_album = None
                    _PM_REF = None

    def add_title(self, title: str):
        title = (title or "").strip()
        if not title:
            return
        with self._lock:
            if title not in self.task_titles:
                self.task_titles.append(title)
            self._current_album = title
        self._touch()
        self._update_live(force=False)

    def remove_title(self, title: str):
        title = (title or "").strip()
        if not title:
            return
        with self._lock:
            if title in self.task_titles:
                self.task_titles.remove(title)
            if self._current_album == title:
                self._current_album = self.task_titles[-1] if self.task_titles else None
        self._touch()
        self._update_live(force=False)

    def _gen_title_rule(self):
        if not self.task_titles:
            return None
        shown = [self._truncate(t, 34) for t in self.task_titles[:2]]
        titles = ", ".join(shown)
        if len(self.task_titles) > 2:
            titles += "..."
        # Rule line in Cyan
        return Rule(self.prefix + Text(titles), style="cyan")


# --- BACKWARD COMPATIBILITY FUNCTION ---
def print_skipped(name: str, reason: str):
    console.print(f"[yellow]Skipped ({reason})[/]: {name}")


@dataclass(slots=True)
class Handle:
    update: Callable[[int], None]
    done: Callable[[], None]

    def __enter__(self):
        return self.update

    def __exit__(self, *_):
        self.done()


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
