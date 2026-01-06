import asyncio
import json
import logging
import platform
import sys
import re
import os
import aiofiles
import tomllib  # Native in Python 3.11+

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
                console.print(f"[green]Reading configuration from: {manual_config_path}[/green]")
                with open(manual_config_path, "rb") as f:
                    data = tomllib.load(f)
                
                # 1. Force Download Folder
                if "downloads" in data and "folder" in data["downloads"]:
                    target_folder = data["downloads"]["folder"]
                    self.config.session.downloads.folder = target_folder
                    console.print(f"[cyan]>> Download folder forced to: {target_folder}[/cyan]")

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
                console.print(f"[red]Config.toml not found at: {manual_config_path}[/red]")
                os.makedirs(target_folder, exist_ok=True)

        except Exception as e:
            console.print(f"[red]Error reading manual config.toml: {e}[/red]")
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
        # Ensure DB folders exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(os.path.dirname(failed_db_path), exist_ok=True)

        downloads_db = db.Downloads(db_path)
        failed_downloads_db = db.Failed(failed_db_path)
        self.database = db.Database(downloads_db, failed_downloads_db)
        # -----------------------------------------------------------
        
        self.queue = asyncio.Queue()
        self.producer_tasks = [] 

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
            console.print(f"[green]Streaming started: Searching releases for {artist_id}...[/green]")
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
        if media_type == "track": item = PendingSingle(id, client, self.config, self.database)
        elif media_type == "album": item = PendingAlbum(id, client, self.config, self.database)
        elif media_type == "playlist": item = PendingPlaylist(id, client, self.config, self.database)
        elif media_type == "label": item = PendingLabel(id, client, self.config, self.database)
        elif media_type == "artist": item = PendingArtist(id, client, self.config, self.database)
        else: raise Exception(media_type)
        await self.queue.put(item)

    async def add_all(self, urls: list[str]):
        for url in urls:
            try: await self.add(url)
            except Exception as e: console.print(f"[red]Error adding {url}: {e}[/red]")

    async def resolve(self):
        pass 

    async def rip(self):
        workers = [asyncio.create_task(self.worker_loop()) for _ in range(4)]
        if self.producer_tasks:
            await asyncio.gather(*self.producer_tasks)
        await self.queue.join()
        for w in workers: w.cancel()

    async def worker_loop(self):
        while True:
            pending_item = await self.queue.get()
            try:
                media_item = await pending_item.resolve()
                if media_item is not None:
                    await media_item.rip()
            except Exception as e:
                logger.error(f"Error processing item: {e}")
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

    async def __aenter__(self): return self
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
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as e: logger.exception("Error:", exc_info=e)

if __name__ == "__main__":
    run_main()