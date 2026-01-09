import logging
import sys
import os
from dataclasses import dataclass
from typing import Callable
import threading
import queue
import time

# Enable ANSI colors on Windows consoles
os.system("")

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
)
from rich.rule import Rule
from rich.text import Text

logger = logging.getLogger("streamrip")

_console = Console(file=sys.stderr, force_terminal=True, force_interactive=True)


class ProgressManager:
    """
    Progress manager con auto-eliminación de barras completadas.
    """

    def __init__(self):
        self.started = False
        self.task_titles: list[str] = []
        
        # Contadores de sesión
        self.completed_count = 0
        self.skipped_count = 0
        self.error_count = 0

        self.progress = Progress(
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=None),
            console=_console,
        )

        self.prefix = Text.assemble(("Downloading ", "bold cyan"), overflow="ellipsis")
        self._text_cache = self.gen_title_text()
        self.live = Live(
            Group(self._text_cache, self.progress),
            console=_console,
            refresh_per_second=8
        )
        
        # Thread-safety
        self._lock = threading.RLock()
        self._live_lock = threading.Lock()
        
        # Queue para updates no-bloqueantes
        self._update_queue = queue.Queue(maxsize=1000)
        self._stop_worker = threading.Event()
        
        # Worker thread
        self._worker_thread = None
        
        # Fallback mode
        self._use_fallback = False
        self._live_failures = 0

    def get_callback(self, total: int, desc: str):
        if not self.started:
            try:
                self.live.start()
                self.started = True
                
                # Iniciar worker thread
                if self._worker_thread is None:
                    self._worker_thread = threading.Thread(
                        target=self._update_worker_loop,
                        daemon=True
                    )
                    self._worker_thread.start()
            except Exception:
                self._use_fallback = True

        if self._use_fallback:
            return Handle(lambda _: None, lambda: None)

        task_id = self.progress.add_task(f"[cyan]{desc}", total=total)

        def _callback_update(x: int):
            if self._use_fallback:
                return
            try:
                self._update_queue.put_nowait({
                    "type": "advance",
                    "task_id": task_id,
                    "advance": x
                })
            except queue.Full:
                pass

        def _callback_done():
            if self._use_fallback:
                return
            try:
                # ================================================================
                # FIX: Marcar como completado y OCULTAR la barra
                # ================================================================
                self._update_queue.put_nowait({
                    "type": "complete",
                    "task_id": task_id
                })
                self.completed_count += 1
            except queue.Full:
                pass

        return Handle(_callback_update, _callback_done)

    def _update_worker_loop(self):
        """Worker thread que procesa updates en background."""
        batch_updates = []
        last_live_update = time.time()
        min_interval = 0.15
        
        while not self._stop_worker.is_set():
            try:
                # Recolectar hasta 5 updates
                timeout = max(0.01, min_interval - (time.time() - last_live_update))
                update = self._update_queue.get(timeout=timeout)
                batch_updates.append(update)
                
                # Recolectar más si hay disponibles
                while len(batch_updates) < 5:
                    try:
                        update = self._update_queue.get_nowait()
                        batch_updates.append(update)
                    except queue.Empty:
                        break
                
                # Procesar batch
                if batch_updates:
                    with self._lock:
                        for upd in batch_updates:
                            try:
                                if upd["type"] == "advance":
                                    self.progress.update(
                                        upd["task_id"],
                                        advance=upd["advance"]
                                    )
                                elif upd["type"] == "complete":
                                    # ================================================
                                    # FIX: Ocultar barra al completar
                                    # ================================================
                                    self.progress.update(
                                        upd["task_id"],
                                        visible=False
                                    )
                                    # También remover la tarea para liberar memoria
                                    try:
                                        self.progress.remove_task(upd["task_id"])
                                    except:
                                        pass
                            except Exception as e:
                                logger.debug(f"Progress update error: {e}")
                    
                    batch_updates.clear()
                    
                    # Update Live display
                    now = time.time()
                    if now - last_live_update >= min_interval:
                        self._safe_live_update()
                        last_live_update = now
                        
            except queue.Empty:
                # Timeout - update display si hay cambios pendientes
                if time.time() - last_live_update >= min_interval:
                    self._safe_live_update()
                    last_live_update = time.time()
            except Exception as e:
                logger.debug(f"Worker loop error: {e}")

    def _safe_live_update(self):
        """Update Live con manejo de errores."""
        if self._use_fallback:
            return
            
        try:
            with self._live_lock:
                self.live.update(Group(self.get_title_text(), self.progress))
        except Exception as e:
            self._live_failures += 1
            logger.debug(f"Live update error: {e}")
            
            if self._live_failures >= 3:
                logger.warning("Rich Live failing, switching to fallback mode")
                self._use_fallback = True

    def cleanup(self):
        """Cleanup y mostrar resumen final."""
        self._stop_worker.set()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)
        
        if self.started and not self._use_fallback:
            try:
                self.live.stop()
            except Exception:
                pass
        
        # Mostrar resumen final
        if self.completed_count > 0 or self.skipped_count > 0 or self.error_count > 0:
            summary = Text()
            summary.append("✓ Completed: ", style="bold green")
            summary.append(str(self.completed_count), style="green")
            summary.append("  ⊘ Skipped: ", style="bold yellow")
            summary.append(str(self.skipped_count), style="yellow")
            summary.append("  ✖ Errors: ", style="bold red")
            summary.append(str(self.error_count), style="red")
            _console.print(summary)

    def add_title(self, title: str):
        title = (title or "").strip()
        if title:
            with self._lock:
                self.task_titles.append(title)
                self._text_cache = self.gen_title_text()

    def remove_title(self, title: str):
        title = (title or "").strip()
        if title:
            with self._lock:
                if title in self.task_titles:
                    self.task_titles.remove(title)
                    self._text_cache = self.gen_title_text()

    def gen_title_text(self) -> Rule:
        titles = ", ".join(self.task_titles[:3])
        if len(self.task_titles) > 3:
            titles += "..."
        
        # Agregar contadores al título
        stats = f" • ✓ {self.completed_count} ⊘ {self.skipped_count} ✖ {self.error_count}"
        t = self.prefix + Text(titles) + Text(stats, style="dim")
        return Rule(t)

    def get_title_text(self) -> Rule:
        with self._lock:
            return self.gen_title_text()


@dataclass(slots=True)
class Handle:
    update: Callable[[int], None]
    done: Callable[[], None]

    def __enter__(self):
        return self.update

    def __exit__(self, *_):
        self.done()


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