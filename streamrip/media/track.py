import asyncio
import logging
import os
import re
from dataclasses import dataclass

from .. import converter
from ..client import Client, Downloadable
from ..config import Config
from ..db import Database
from ..exceptions import NonStreamableError
# --- IMPORTAMOS LA NUEVA FUNCIÓN ---
from ..filepath_utils import clean_filename, truncate_filepath_to_max, clean_track_title
from ..metadata import AlbumMetadata, Covers, TrackMetadata, tag_file
from ..progress import add_title, get_progress_callback, remove_title
from ..console import console
from .artwork import download_artwork
from .media import Media, Pending
from .semaphore import global_download_semaphore

logger = logging.getLogger("streamrip")

@dataclass(slots=True)
class Track(Media):
    meta: TrackMetadata
    downloadable: Downloadable
    config: Config
    folder: str
    cover_path: str | None
    db: Database
    download_path: str = ""
    is_single: bool = False
    from_playlist: bool = False

    async def rip(self):
        await self.preprocess()
        if not self.download_path: self._set_download_path()

        if os.path.isfile(self.download_path):
            console.print(f"[yellow]Skipped (Exists)[/]: {self.meta.title}")
            if not self.db.downloaded(self.meta.info.id):
                self.db.set_downloaded(self.meta.info.id)
            if self.is_single: remove_title(self.meta.title)
            return

        await self.download()
        await self.postprocess()

    async def preprocess(self):
        self._set_download_path()
        os.makedirs(self.folder, exist_ok=True)
        if self.is_single: add_title(self.meta.title)

    async def download(self):
        if not self.download_path: self._set_download_path()
        if os.path.isfile(self.download_path): return

        async with global_download_semaphore(self.config.session.downloads):
            display_title = self.meta.title
            for attempt in range(1, 3): 
                try:
                    size = await self.downloadable.size()
                    desc = display_title if attempt == 1 else f"{display_title} (retry)"
                    handle = get_progress_callback(self.config.session.cli.progress_bars, size, desc)
                    with handle as update_fn:
                        await self.downloadable.download(self.download_path, update_fn)
                    return
                except Exception as e:
                    if attempt == 1:
                        logger.error(f"Error '{self.meta.title}': {e}. Retrying...")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"Persistent error '{self.meta.title}': {e}")
                        self.db.set_failed(self.downloadable.source, "track", self.meta.info.id)

    async def postprocess(self):
        if self.is_single: remove_title(self.meta.title)
        await tag_file(self.download_path, self.meta, self.cover_path)
        if self.config.session.conversion.enabled: await self._convert()
        self.db.set_downloaded(self.meta.info.id)
        console.print(f"[green]Downloaded[/]: {os.path.basename(self.download_path)}")

    async def _convert(self):
        c = self.config.session.conversion
        engine_class = converter.get(c.codec)
        engine = engine_class(filename=self.download_path, sampling_rate=c.sampling_rate, bit_depth=c.bit_depth, remove_source=True)
        await engine.convert()
        self.download_path = engine.final_fn

    def _set_download_path(self):
        c = self.config.session.filepaths
        formatter = "{artist} - {title} {explicit}" if self.from_playlist else c.track_format
        track_path = self.meta.format_track_path(formatter)
        
        # --- USAMOS LA FUNCIÓN CENTRALIZADA ---
        track_path = clean_track_title(track_path, self.meta.artist)
        
        if self.meta.info.explicit and "explicit" not in track_path.lower():
            track_path += " [explicit]"

        track_path = clean_filename(track_path, restrict=c.restrict_characters)
        if c.truncate_to > 0: track_path = track_path[:c.truncate_to]

        raw_path = os.path.join(self.folder, f"{track_path}.{self.downloadable.extension}")
        self.download_path = truncate_filepath_to_max(raw_path)


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str
    db: Database
    cover_path: str | None
    preloaded_data: dict | None = None

    async def resolve(self) -> Track | None:
        source = self.client.source
        try:
            if self.preloaded_data: resp = self.preloaded_data
            else: resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError: return None

        try: meta = TrackMetadata.from_resp(self.album, source, resp)
        except Exception: return None
        if meta is None:
            self.db.set_failed(source, "track", self.id)
            return None

        downloads_config = self.config.session.downloads
        if downloads_config.disc_subdirectories and self.album.disctotal > 1:
            track_folder = os.path.join(self.folder, f"Disc {meta.discnumber}")
        else:
            track_folder = self.folder

        quality = self.config.session.get_source(source).quality
        try: downloadable = await self.client.get_downloadable(self.id, quality)
        except NonStreamableError: return None

        if self.db.downloaded(self.id):
            c = self.config.session.filepaths
            track_path = meta.format_track_path(c.track_format)
            
            # --- USAMOS LA FUNCIÓN CENTRALIZADA ---
            track_path = clean_track_title(track_path, meta.artist)
            
            if meta.info.explicit and "explicit" not in track_path.lower():
                track_path += " [explicit]"
            
            track_path = clean_filename(track_path, restrict=c.restrict_characters)
            if c.truncate_to > 0: track_path = track_path[:c.truncate_to]
            
            raw_path = os.path.join(track_folder, f"{track_path}.{downloadable.extension}")
            file_path = truncate_filepath_to_max(raw_path)
            
            if os.path.isfile(file_path):
                console.print(f"[dim]   ↪ Skipped (DB+File): {meta.title}[/dim]")
                return None 
            else:
                logger.warning(f"[!] Missing file: {os.path.basename(file_path)}")

        return Track(meta, downloadable, self.config, track_folder, self.cover_path, self.db)

@dataclass(slots=True)
class PendingSingle(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Track | None:
        try: resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError: return None
        try:
            album = AlbumMetadata.from_track_resp(resp, self.client.source)
            meta = TrackMetadata.from_resp(album, self.client.source, resp)
        except Exception: return None
        if album is None or meta is None: return None

        config = self.config.session
        quality = getattr(config, self.client.source).quality
        parent = config.downloads.folder
        folder = os.path.join(parent, self._format_folder(album)) if config.filepaths.add_singles_to_folder else parent
        c = config.filepaths
        track_path = meta.format_track_path(c.track_format)
        
        # --- USAMOS LA FUNCIÓN CENTRALIZADA ---
        track_path = clean_track_title(track_path, meta.artist)

        if meta.info.explicit and "explicit" not in track_path.lower():
            track_path += " [explicit]"

        track_path = clean_filename(track_path, restrict=c.restrict_characters)
        if c.truncate_to > 0: track_path = track_path[:c.truncate_to]

        downloadable = await self.client.get_downloadable(self.id, quality)
        raw_path = os.path.join(folder, f"{track_path}.{downloadable.extension}")
        file_path = truncate_filepath_to_max(raw_path)

        if os.path.isfile(file_path):
            console.print(f"[dim]   ↪ Skipped (Exists): {meta.title}[/dim]")
            if not self.db.downloaded(self.id):
                self.db.set_downloaded(self.id)
            return None
        else:
            if self.db.downloaded(self.id): logger.warning(f"[!] Re-downloading: {os.path.basename(file_path)}")
            os.makedirs(folder, exist_ok=True)
            embedded_cover_path = await self._download_cover(album.covers, folder)
            return Track(meta, downloadable, self.config, folder, embedded_cover_path, self.db, is_single=True)

    def _format_folder(self, meta: AlbumMetadata) -> str:
        c = self.config.session
        parent = os.path.join(c.downloads.folder, self.client.source.capitalize()) if c.downloads.source_subdirectories else c.downloads.folder
        return os.path.join(parent, meta.format_folder_path(c.filepaths.folder_format))

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(self.client.session, folder, covers, self.config.session.artwork, for_playlist=False)
        return embed_path
