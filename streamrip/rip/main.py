import asyncio
import json
import logging
import platform
import sys
import re
import os
import aiofiles
import tomllib  # Native in Python 3.11+

# --- NEW IMPORTS FOR DASHBOARD ---
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich import box
# ---------------------------------

from .. import db
from ..client import Client, DeezerClient, QobuzClient, SoundcloudClient, TidalClient
from ..config import Config
from ..console import console
from ..media import (
    Media,
    Pending,
    PendingAlbum,
    PendingArtist,
    PendingLabel,
    PendingLastfmPlaylist,
    PendingPlaylist,
    PendingSingle,
    remove_artwork_tempdirs,
)
from ..metadata import SearchResults
from ..progress import clear_progress
from .parse_url import parse_url
from .prompter import get_prompter

logger = logging.getLogger("streamrip")

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Main:
    def __init__(self, config: Config):
        self.config = config

        # --- BRUTE FORCE: LOAD CONFIG.TOML FROM APPDATA ---
        try:
            appdata = os.environ.get("APPDATA")
            manual_config_path = os.path.join(appdata, "streamrip", "config.toml")

            # Default values in case reading fails
            target_folder = config.session.downloads.folder
            db_path = os.path.join(target_folder, "downloads.db")
            failed_db_path = os.path.join(target_folder, "failed_downloads.db")

            if os.path.exists(manual_config_path):
                with open(manual_config_path, "rb") as f:
                    data = tomllib.load(f)

                # 1. Force Download Folder
                if "downloads" in data and "folder" in data["downloads"]:
                    target_folder = data["downloads"]["folder"]
                    self.config.session.downloads.folder = target_folder

                # 2. Force Folder Format
                if "filepaths" in data:
                    if "folder_format" in data["filepaths"]:
                        self.config.session.filepaths.folder_format = data["filepaths"]["folder_format"]
                    if "track_format" in data["filepaths"]:
                        self.config.session.filepaths.track_format = data["filepaths"]["track_format"]

                # 3. Read Database Paths
                if "database" in data:
                    if "downloads_path" in data["database"]:
                        db_path = data["database"]["downloads_path"]
                    if "failed_downloads_path" in data["database"]:
                        failed_db_path = data["database"]["failed_downloads_path"]
            else:
                os.makedirs(target_folder, exist_ok=True)

        except Exception as e:
            target_folder = config.session.downloads.folder
            db_path = os.path.join(target_folder, "downloads.db")
            failed_db_path = os.path.join(target_folder, "failed_downloads.db")

        # Initialize Clients
        self.clients: dict[str, Client] = {
            "qobuz": QobuzClient(config),
            "tidal": TidalClient(config),
            "deezer": DeezerClient(config),
            "soundcloud": SoundcloudClient(config),
        }

        # Initialize Database with correct paths
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(os.path.dirname(failed_db_path), exist_ok=True)

        downloads_db = db.Downloads(db_path)
        failed_downloads_db = db.Failed(failed_db_path)
        self.database = db.Database(downloads_db, failed_downloads_db)

        # --- DASHBOARD & WORKER CONFIG ---
        self.queue = asyncio.Queue()
        self.producer_tasks = []
        self.worker_status = {}  # Stores status for visual table
        self.total_workers = 4  # Set number of parallel downloads here

    # --- DASHBOARD GENERATOR ---
    def generate_dashboard(self) -> Table:
        """Creates the Rich table for the live dashboard."""
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Worker", style="dim", width=8)
        table.add_column("Status", width=12)
        table.add_column("Current Item / Detail", style="white")

        # Loop through defined workers to populate rows
        for i in range(self.total_workers):
            # Default state if worker hasn't reported yet
            status = self.worker_status.get(i, ("Idle", "Waiting..."))
            status_text = status[0]
            item_text = status[1]

            # Dynamic styling based on status
            style = "white"
            if "Downloading" in status_text:
                style = "bold green"
            elif "Resolving" in status_text:
                style = "bold yellow"
            elif "Error" in status_text:
                style = "bold red"
            elif "Finished" in status_text:
                style = "green"

            table.add_row(f"#{i + 1}", f"[{style}]{status_text}[/]", item_text)

        return Panel(table, title="[bold white]Orpheus Multi-Downloader[/]", border_style="blue")

    async def add(self, url: str):
        # Background streaming for Tidal artists
        tidal_artist_match = re.search(r'tidal\.com.*/artist/(\d+)', url)

        if tidal_artist_match:
            artist_id = tidal_artist_match.group(1)
            task = asyncio.create_task(self._background_search_artist(artist_id))
            self.producer_tasks.append(task)
            return

        parsed = parse_url(url)
        if parsed is None: raise Exception(f"Unable to parse url {url}")
        client = await self.get_logged_in_client(parsed.source)
        item = await parsed.into_pending(client, self.config, self.database)
        await self.queue.put(item)

    async def _background_search_artist(self, artist_id):
        try:
            client = await self.get_logged_in_client("tidal")

            display_name = artist_id
            try:
                artist_meta = await client.get_metadata(artist_id, "artist")
                if "name" in artist_meta:
                    display_name = artist_meta["name"]
            except:
                pass

            console.print(f"[green]Streaming started: Searching releases for {display_name}...[/green]")

            async for album_batch in client.get_artist_albums_stream(artist_id):
                count = 0
                for album in album_batch:
                    if 'id' in album:
                        item = PendingAlbum(str(album['id']), client, self.config, self.database)
                        await self.queue.put(item)
                        count += 1
                console.print(f"[dim]>> Queue fed: +{count} albums[/dim]")
        except Exception as e:
            logger.error(f"Error in background search: {e}")

    async def add_by_id(self, source: str, media_type: str, id: str):
        client = await self.get_logged_in_client(source)
        if media_type == "track":
            item = PendingSingle(id, client, self.config, self.database)
        elif media_type == "album":
            item = PendingAlbum(id, client, self.config, self.database)
        elif media_type == "playlist":
            item = PendingPlaylist(id, client, self.config, self.database)
        elif media_type == "label":
            item = PendingLabel(id, client, self.config, self.database)
        elif media_type == "artist":
            item = PendingArtist(id, client, self.config, self.database)
        else:
            raise Exception(media_type)
        await self.queue.put(item)

    async def add_all(self, urls: list[str]):
        for url in urls:
            try:
                await self.add(url)
            except Exception as e:
                console.print(f"[red]Error adding {url}: {e}[/red]")

    async def resolve(self):
        pass

        # --- UPDATED RIP METHOD WITH DASHBOARD ---

    async def rip(self):
        # Create tasks for workers with their specific ID
        workers = [asyncio.create_task(self.worker_loop(i)) for i in range(self.total_workers)]

        if self.producer_tasks:
            await asyncio.gather(*self.producer_tasks)

        # Use Rich Live to render the table continuously
        with Live(self.generate_dashboard(), refresh_per_second=4) as live:
            while not self.queue.empty():
                live.update(self.generate_dashboard())
                await asyncio.sleep(0.25)  # Refresh rate

            # Wait for workers to finish the last items
            await self.queue.join()
            live.update(self.generate_dashboard())

        for w in workers: w.cancel()

    # --- UPDATED WORKER LOOP ---
    async def worker_loop(self, worker_id: int):
        self.worker_status[worker_id] = ("Idle", "Waiting for queue...")

        while True:
            # Update status to searching
            self.worker_status[worker_id] = ("Idle", "Checking queue...")
            pending_item = await self.queue.get()

            try:
                # Try to get a preliminary name
                display_name = "Unknown Item"
                if hasattr(pending_item, 'id'): display_name = f"ID: {pending_item.id}"

                # Update status: Resolving metadata
                self.worker_status[worker_id] = ("Resolving", display_name)

                media_item = await pending_item.resolve()

                if media_item is not None:
                    # Update name with real metadata if available
                    if hasattr(media_item, 'title'): display_name = media_item.title
                    if hasattr(media_item, 'artist') and hasattr(media_item.artist, 'name'):
                        display_name = f"{media_item.artist.name} - {display_name}"

                    # Update status: Downloading
                    # Truncate long names to keep table clean
                    short_name = (display_name[:45] + '..') if len(display_name) > 45 else display_name
                    self.worker_status[worker_id] = ("Downloading", short_name)

                    await media_item.rip()

                    # Update status: Done
                    self.worker_status[worker_id] = ("Finished", short_name)
                    await asyncio.sleep(0.5)  # Brief pause so user sees "Finished"
                else:
                    self.worker_status[worker_id] = ("Skipped", display_name)

            except Exception as e:
                logger.error(f"Error processing item: {e}")
                self.worker_status[worker_id] = ("Error", str(e)[:30])
                await asyncio.sleep(3)  # Show error for a moment
            finally:
                self.queue.task_done()

    async def get_logged_in_client(self, source: str):
        client = self.clients.get(source)
        if client is None: raise Exception(f"No client named {source}")
        if not client.logged_in:
            prompter = get_prompter(client, self.config)
            if not prompter.has_creds():
                await prompter.prompt_and_login()
                prompter.save()
            else:
                await client.login()
        return client

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        for client in self.clients.values():
            if hasattr(client, "session"): await client.session.close()
        try:
            if hasattr(self.database, "downloads") and hasattr(self.database.downloads, "close"):
                self.database.downloads.close()
            if hasattr(self.database, "failed") and hasattr(self.database.failed, "close"):
                self.database.failed.close()
        except Exception:
            pass
        remove_artwork_tempdirs()


def run_main():
    async def main():
        config = Config()
        async with Main(config) as ripper:
            target_urls = sys.argv[1:] if len(sys.argv) > 1 else []
            if target_urls:
                await ripper.add_all(target_urls)
                await ripper.rip()
            else:
                print("No URLs provided.")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception("Error:", exc_info=e)


if __name__ == "__main__":
    run_main()