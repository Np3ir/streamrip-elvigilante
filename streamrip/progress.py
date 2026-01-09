import logging
import re
import time
import threading
import queue
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.text import Text

from .console import console

logger = logging.getLogger("streamrip")


class ProgressManager:
    """
    Anti-freeze progress manager with:
      - Queue-based updates (no direct Live calls from callbacks)
      - Thread-safe operations with locks
      - Aggressive error handling (never crash)
      - Batch updates to reduce CPU
      - Fallback to simple prints if Rich fails
      - Automatic recovery from Live crashes
    """

    def __init__(self):
        self.started = False
        self.task_titles: list[str] = []
        self.next_track_number: dict[str, int] = {}

        # Session counters
        self.completed_count = 0
        self.skipped_count = 0
        self.error_count = 0

        # Per-task state
        self._task_total: dict[int, int] = {}
        self._task_last: dict[int, int] = {}
        self._task_mode: dict[int, str | None] = {}  # None, "delta", "absolute"
        self._task_samples: dict[int, list[int]] = defaultdict(list)

        # ==================== ANTI-FREEZE MECHANISMS ====================
        
        # Thread safety
        self._lock = threading.RLock()  # Recursive lock for nested calls
        self._live_lock = threading.Lock()  # Separate lock for Live operations
        
        # Queue for batched updates (like gui.py line 102)
        self._update_queue = queue.Queue(maxsize=1000)
        
        # Update throttling
        self._last_live_refresh = 0.0
        self._min_refresh_interval = 0.15  # Increased from 0.12
        self._batch_size = 5  # Process multiple updates at once
        
        # Fallback mode
        self._use_fallback = False
        self._live_failures = 0
        self._max_live_failures = 3  # Switch to fallback after 3 failures
        
        # Update worker thread
        self._update_thread = None
        self._stop_update_thread = False
        
        # ================================================================

        self.progress = self._new_progress()

        self.prefix = Text.assemble(("Downloading ", "bold cyan"), overflow="ellipsis")
        self._text_cache = self.gen_title_text()

        # Try to create Live, but handle failure gracefully
        try:
            self.live = Live(
                Group(self._text_cache, self.progress),
                refresh_per_second=6,  # Reduced from 8
                console=console,
            )
        except Exception as e:
            logger.error(f"[PROGRESS] Failed to create Live display: {e}")
            self.live = None
            self._use_fallback = True

    def _new_progress(self) -> Progress:
        """Create new Progress instance with error handling."""
        try:
            return Progress(
                TextColumn("[green]{task.description}", justify="left"),
                BarColumn(bar_width=40),
                "[progress.percentage]{task.percentage:>5.1f}%",
                "•",
                TransferSpeedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console,
                transient=False,
            )
        except Exception as e:
            logger.error(f"[PROGRESS] Failed to create Progress: {e}")
            # Return a dummy progress that won't crash
            return Progress(console=console)

    # ==================== UPDATE WORKER THREAD ====================
    
    def _start_update_worker(self):
        """Start background thread to process updates."""
        if self._update_thread is None or not self._update_thread.is_alive():
            self._stop_update_thread = False
            self._update_thread = threading.Thread(
                target=self._update_worker_loop,
                daemon=True,
                name="ProgressUpdateWorker"
            )
            self._update_thread.start()
            logger.debug("[PROGRESS] Update worker thread started")

    def _update_worker_loop(self):
        """Background worker that processes queued updates."""
        while not self._stop_update_thread:
            try:
                # Wait for updates with timeout
                updates = []
                try:
                    # Get first update (blocking with timeout)
                    first_update = self._update_queue.get(timeout=0.5)
                    if first_update == "STOP":
                        break
                    updates.append(first_update)
                    
                    # Get additional updates (non-blocking) up to batch size
                    for _ in range(self._batch_size - 1):
                        try:
                            update = self._update_queue.get_nowait()
                            if update == "STOP":
                                self._stop_update_thread = True
                                break
                            updates.append(update)
                        except queue.Empty:
                            break
                
                except queue.Empty:
                    continue
                
                # Process batched updates
                if updates and not self._stop_update_thread:
                    self._process_updates_batch(updates)
                    
            except Exception as e:
                logger.debug(f"[PROGRESS] Update worker error: {e}")
                time.sleep(0.1)  # Prevent tight loop on errors

    def _process_updates_batch(self, updates: list):
        """Process a batch of updates safely."""
        try:
            with self._lock:
                for update in updates:
                    update_type = update.get("type")
                    
                    if update_type == "advance":
                        task_id = update.get("task_id")
                        advance = update.get("advance", 0)
                        try:
                            self.progress.update(task_id, advance=advance)
                        except Exception:
                            pass
                    
                    elif update_type == "complete":
                        task_id = update.get("task_id")
                        try:
                            total = self._task_total.get(task_id, 0)
                            self.progress.update(task_id, completed=total)
                            self.progress.remove_task(task_id)
                        except Exception:
                            try:
                                self.progress.update(task_id, visible=False)
                            except Exception:
                                pass
                    
                    elif update_type == "refresh_title":
                        self._refresh_title_cache()
                
                # Try to update Live display
                self._safe_live_update()
                
        except Exception as e:
            logger.debug(f"[PROGRESS] Batch processing error: {e}")

    # ================================================================

    # ---------------- Track label parsing ----------------

    def _extract_track_number(self, desc: str) -> int | None:
        """Try to extract track number from description."""
        patterns = [
            r"^\s*(\d{1,2})\s*[.)-]\s+",
            r"^\s*Track[:\s]+(\d{1,2})\b",
            r"\b-\s*(\d{1,2})\s*-\s*",
            r"\b(\d{1,2})\.\s+",
        ]
        for pattern in patterns:
            m = re.search(pattern, desc or "", re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    return None
        return None

    def _clean_track_title(self, desc: str) -> str:
        """Extract a readable title from desc."""
        s = (desc or "").strip()

        s = re.sub(r"^\s*Track[:\s]+\d{1,2}\s*[-:]\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^\s*\d{1,2}\s*[.)-]\s*", "", s)

        parts = [p.strip() for p in s.split(" - ") if p.strip()]
        if len(parts) >= 3 and re.fullmatch(r"\d{1,2}", parts[1] or ""):
            s = parts[-1]

        s = s.strip()
        if not s:
            return "Unknown"

        if len(s) > 500:
            s = s[:500]
        return s

    def _truncate_title(self, title: str, max_len: int = 50) -> str:
        """Safe truncation with word-boundary preference."""
        title = (title or "").strip()
        if len(title) <= max_len:
            return title

        cut = title[:max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
            cut = cut.strip()
        if not cut:
            cut = title[:max_len].strip()
        return cut + "..."

    def _get_track_label(self, desc: str, album: str) -> str:
        """Label format: "NN Title" """
        try:
            track_num = self._extract_track_number(desc)
            title = self._clean_track_title(desc)

            if track_num is None:
                if album not in self.next_track_number:
                    self.next_track_number[album] = 1
                track_num = self.next_track_number[album]
                self.next_track_number[album] += 1

            if not title or title == "Unknown":
                title = "Unknown Title"

            title = self._truncate_title(title, max_len=50)
            return f"{track_num:02d} {title}"
        except Exception as e:
            logger.debug(f"[PROGRESS] Label generation error: {e}")
            return "Unknown Track"

    # ---------------- Title / Live UI ----------------

    def gen_title_text(self) -> Rule:
        """Generate title line with counters."""
        try:
            if not self.task_titles:
                titles = "Ready"
            else:
                titles = ", ".join(self.task_titles[:2])
                if len(self.task_titles) > 2:
                    titles += "..."

            counters = f"  •  ✓ {self.completed_count}  ⊘ {self.skipped_count}  ✖ {self.error_count}"
            t = self.prefix + Text(titles) + Text(counters, style="dim")
            return Rule(t, style="cyan")
        except Exception as e:
            logger.debug(f"[PROGRESS] Title generation error: {e}")
            return Rule("Downloading...", style="cyan")

    def get_title_text(self) -> Rule:
        return self._text_cache

    def _refresh_title_cache(self) -> None:
        """Thread-safe title cache refresh."""
        try:
            with self._lock:
                self._text_cache = self.gen_title_text()
        except Exception as e:
            logger.debug(f"[PROGRESS] Title cache refresh error: {e}")

    def _safe_live_update(self, force: bool = False) -> None:
        """
        Safely update Live display with multiple fallback strategies.
        Like gui.py's error handling approach.
        """
        if not self.started:
            return
        
        # Check if we should use fallback mode
        if self._use_fallback:
            return
        
        if not self.live:
            self._use_fallback = True
            return
        
        # Throttle updates
        now = time.monotonic()
        if (not force) and (now - self._last_live_refresh) < self._min_refresh_interval:
            return
        
        # Try to update with timeout protection
        try:
            with self._live_lock:
                self.live.update(Group(self.get_title_text(), self.progress))
                self._last_live_refresh = now
                self._live_failures = 0  # Reset failure counter on success
        
        except Exception as e:
            self._live_failures += 1
            logger.debug(f"[PROGRESS] Live update error ({self._live_failures}/{self._max_live_failures}): {e}")
            
            # Switch to fallback mode if too many failures
            if self._live_failures >= self._max_live_failures:
                logger.warning("[PROGRESS] Too many Live failures, switching to fallback mode")
                self._use_fallback = True
                try:
                    if self.live:
                        self.live.stop()
                except Exception:
                    pass
                self.live = None

    # ---------------- Callback byte handling ----------------

    def _decide_mode(self, task_id: int, x: int, total: int) -> str | None:
        """Decide whether callback values are delta or absolute."""
        if total <= 0:
            return "delta"

        samples = self._task_samples[task_id]
        samples.append(max(0, int(x)))
        if len(samples) > 6:
            del samples[:-6]

        if x >= int(0.25 * total):
            return "absolute"

        if len(samples) >= 4:
            mn, mx = min(samples), max(samples)
            span = mx - mn
            nondecreasing = all(samples[i] <= samples[i + 1] for i in range(len(samples) - 1))

            if nondecreasing and mx >= int(0.10 * total):
                return "absolute"

            if mx < int(0.20 * total) and span < int(0.05 * total):
                return "delta"

        return None

    def _compute_advance(self, task_id: int, x: int) -> int:
        """Compute advance with thread safety."""
        try:
            total = self._task_total.get(task_id, 0)
            x = max(0, int(x))

            mode = self._task_mode.get(task_id)
            if mode is None:
                mode = self._decide_mode(task_id, x, total)
                if mode is not None:
                    self._task_mode[task_id] = mode

            if mode is None or mode == "delta":
                advance = x
            else:
                last = self._task_last.get(task_id, 0)
                advance = x - last
                if advance < 0:
                    advance = 0
                self._task_last[task_id] = x

            if total > 0:
                try:
                    task = self.progress.tasks[task_id]
                    remaining = int(total - task.completed)
                    if remaining < 0:
                        remaining = 0
                    if advance > remaining:
                        advance = remaining
                except Exception:
                    pass

            return advance
        except Exception as e:
            logger.debug(f"[PROGRESS] Advance computation error: {e}")
            return 0

    # ---------------- Public API ----------------

    def get_callback(self, total: int, desc: str):
        """
        Get progress callback with anti-freeze guarantees.
        Never blocks, never crashes.
        """
        # Fallback mode: return dummy handlers
        if self._use_fallback or self.live is None:
            return Handle(lambda _: None, lambda: None)

        # Start Live and worker thread if needed
        if not self.started:
            try:
                with self._live_lock:
                    self.live.start()
                    self.started = True
                    self._last_live_refresh = time.monotonic()
                self._start_update_worker()
            except Exception as e:
                logger.error(f"[PROGRESS] Failed to start Live: {e}")
                self.error_count += 1
                self._use_fallback = True
                return Handle(lambda _: None, lambda: None)

        current_album = self.task_titles[-1] if self.task_titles else "Unknown"
        track_label = self._get_track_label(desc, current_album)

        try:
            with self._lock:
                task_id = self.progress.add_task(track_label, total=total)
        except Exception as e:
            logger.error(f"[PROGRESS] Failed to create task: {e}")
            self.error_count += 1
            return Handle(lambda _: None, lambda: None)

        # Init per-task state
        with self._lock:
            self._task_total[task_id] = int(total) if total is not None else 0
            self._task_last[task_id] = 0
            self._task_mode[task_id] = None
            self._task_samples[task_id].clear()

        def _callback_update(x: int):
            """Queue-based update (never blocks)."""
            try:
                advance = self._compute_advance(task_id, x)
                if advance > 0:
                    # Queue update instead of direct call
                    try:
                        self._update_queue.put_nowait({
                            "type": "advance",
                            "task_id": task_id,
                            "advance": advance
                        })
                    except queue.Full:
                        # If queue is full, skip this update (it's OK, next one will catch up)
                        pass
            except Exception as e:
                logger.debug(f"[PROGRESS] Update callback error: {e}")

        def _callback_done():
            """Queue-based completion (never blocks)."""
            try:
                with self._lock:
                    self.completed_count += 1
                
                # Queue completion
                try:
                    self._update_queue.put_nowait({
                        "type": "complete",
                        "task_id": task_id
                    })
                    self._update_queue.put_nowait({
                        "type": "refresh_title"
                    })
                except queue.Full:
                    # If queue is full, try direct cleanup
                    try:
                        with self._lock:
                            self.progress.remove_task(task_id)
                    except Exception:
                        pass
                
                # Cleanup task state
                with self._lock:
                    self._task_total.pop(task_id, None)
                    self._task_last.pop(task_id, None)
                    self._task_mode.pop(task_id, None)
                    self._task_samples.pop(task_id, None)
                
            except Exception as e:
                logger.debug(f"[PROGRESS] Done callback error: {e}")

        return Handle(_callback_update, _callback_done)

    def cleanup(self):
        """Stop everything safely (idempotent)."""
        try:
            # Stop update worker thread
            if self._update_thread and self._update_thread.is_alive():
                try:
                    self._update_queue.put("STOP", timeout=1.0)
                    self._stop_update_thread = True
                    self._update_thread.join(timeout=2.0)
                except Exception as e:
                    logger.debug(f"[PROGRESS] Worker thread stop error: {e}")

            # Stop Live
            if self.live and self.started:
                try:
                    with self._live_lock:
                        self.live.stop()
                except Exception as e:
                    logger.debug(f"[PROGRESS] Live stop error: {e}")

            # Print summary
            if (self.completed_count or self.skipped_count or self.error_count) > 0:
                try:
                    console.print(
                        f"\n[green]✓ Completed:[/green] {self.completed_count}  "
                        f"[yellow]⊘ Skipped:[/yellow] {self.skipped_count}  "
                        f"[red]✖ Errors:[/red] {self.error_count}"
                    )
                except Exception:
                    print(f"\n✓ Completed: {self.completed_count}  ⊘ Skipped: {self.skipped_count}  ✖ Errors: {self.error_count}")

            # Reset state
            with self._lock:
                self.started = False
                self.task_titles.clear()
                self.next_track_number.clear()
                self._task_total.clear()
                self._task_last.clear()
                self._task_mode.clear()
                self._task_samples.clear()
                self._last_live_refresh = 0.0

            # Clear queue
            while not self._update_queue.empty():
                try:
                    self._update_queue.get_nowait()
                except queue.Empty:
                    break

            # Reset progress
            try:
                self.progress = self._new_progress()
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"[PROGRESS] Cleanup error: {e}")

    def add_title(self, title: str):
        """Thread-safe title addition."""
        try:
            title = title.strip()
            if title:
                with self._lock:
                    self.task_titles.append(title)
                    self.next_track_number[title] = 1
                self._update_queue.put_nowait({"type": "refresh_title"})
        except Exception as e:
            logger.debug(f"[PROGRESS] Add title error: {e}")

    def remove_title(self, title: str):
        """Thread-safe title removal."""
        try:
            title = title.strip()
            with self._lock:
                if title in self.task_titles:
                    self.task_titles.remove(title)
                self.next_track_number.pop(title, None)
            self._update_queue.put_nowait({"type": "refresh_title"})
        except Exception as e:
            logger.debug(f"[PROGRESS] Remove title error: {e}")

    def mark_skipped(self):
        """Thread-safe skip marking."""
        try:
            with self._lock:
                self.skipped_count += 1
            self._update_queue.put_nowait({"type": "refresh_title"})
        except Exception as e:
            logger.debug(f"[PROGRESS] Mark skipped error: {e}")

    def mark_error(self):
        """Thread-safe error marking."""
        try:
            with self._lock:
                self.error_count += 1
            self._update_queue.put_nowait({"type": "refresh_title"})
        except Exception as e:
            logger.debug(f"[PROGRESS] Mark error error: {e}")


@dataclass(slots=True)
class Handle:
    update: Callable[[int], None]
    done: Callable[[], None]

    def __enter__(self):
        return self.update

    def __exit__(self, *_):
        try:
            self.done()
        except Exception as e:
            logger.debug(f"Handle exit error: {e}")

    def __call__(self, advance: int):
        """Make callable for callback(bytes) usage."""
        try:
            self.update(advance)
        except Exception as e:
            logger.debug(f"Handle call error: {e}")


# Global instance
_p = ProgressManager()


def get_progress_callback(enabled: bool, total: int, desc: str) -> Handle:
    global _p
    if not enabled:
        return Handle(lambda _: None, lambda: None)
    return _p.get_callback(total, desc)


def add_title(title: str):
    global _p
    _p.add_title(title)


def remove_title(title: str):
    global _p
    _p.remove_title(title)


def clear_progress():
    global _p
    _p.cleanup()


def print_skipped(filename: str, reason: str = "already downloaded"):
    """Print skipped file message (and count it)."""
    global _p
    try:
        _p.mark_skipped()
        console.print(
            f"[dim yellow]⊘[/dim yellow] [dim]{filename}[/dim] [dim cyan]({reason})[/dim cyan]"
        )
    except Exception as e:
        logger.debug(f"Error printing skipped: {e}")