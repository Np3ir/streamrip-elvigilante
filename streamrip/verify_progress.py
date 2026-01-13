import time
import sys
import random
import threading
from pathlib import Path

# --- Try to add the current Python's site-packages automatically (no hardcode) ---
def _add_site_packages() -> None:
    base = Path(sys.executable).resolve().parent
    candidate = base / "Lib" / "site-packages"
    if candidate.exists():
        p = str(candidate)
        if p not in sys.path:
            sys.path.append(p)

_add_site_packages()

from progress import get_progress_callback, clear_progress, add_title, remove_title
from console import console  # same Rich console used by streamrip


def simulate_download(filename: str, size: int, base_delay: float, jitter: float = 0.02) -> None:
    """
    Simulates a download with variable chunk sizes + delay jitter.
    Runs safely in a thread.
    """
    console.print(f"[bold]Starting:[/bold] {filename}")

    handle = get_progress_callback(True, size, filename)

    downloaded = 0
    base_chunk = 1024 * 512  # 512KB base chunk (more updates -> stresses progress)

    with handle as update:
        while downloaded < size:
            # jitter makes each thread behave differently
            time.sleep(max(0.0, base_delay + random.uniform(-jitter, jitter)))

            # variable chunk size
            chunk_size = base_chunk + random.randint(0, base_chunk)

            # prevent overshoot
            step = min(chunk_size, size - downloaded)
            downloaded += step
            update(step)

    console.print(f"[green]Finished:[/green] {filename}")


def main() -> None:
    album_title = "Stress Test: Multi-thread Downloads (Long Names + Concurrency)"

    files = [
        ("01. Artist With a Very Long Name Indeed - This Song Title Is Also Extremely Long and Should Be Truncated.flac", 30 * 1024 * 1024, 0.015),
        ("02. Normal Artist - Short Song.flac", 22 * 1024 * 1024, 0.020),
        ("03. Another Very Very Long Artist Name - Another Incredibly Long Track Title That Must Be Truncated Properly.flac", 28 * 1024 * 1024, 0.018),
        ("04. DJELVIGILANTE - Club Edit Extended Mix With Extra Long Name.flac", 18 * 1024 * 1024, 0.024),
    ]

    threads: list[threading.Thread] = []

    try:
        console.print("[bold]Starting concurrent progress demonstration...[/bold]")
        add_title(album_title)

        # Start all threads
        for name, size, delay in files:
            t = threading.Thread(target=simulate_download, args=(name, size, delay), daemon=True)
            threads.append(t)
            t.start()

        # Wait all
        for t in threads:
            t.join()

        console.print("[bold green]All downloads completed.[/bold green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted (CTRL+C). Cleaning up...[/yellow]")

    finally:
        # Ensure the Live gets stopped and title cache updated
        try:
            remove_title(album_title)
        except Exception:
            pass
        try:
            clear_progress()
        except Exception:
            pass


if __name__ == "__main__":
    main()
