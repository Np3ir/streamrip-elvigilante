from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from mutagen.easymp4 import EasyMP4

from ..client import Downloadable
from ..config import Config
from ..db import Database
from ..filepath_utils import clean_filename
from ..progress import add_title, get_progress_callback, remove_title
from ..console import console
from .media import Media, Pending
from .semaphore import global_download_semaphore
from ..client import Client

logger = logging.getLogger("streamrip")

@dataclass(slots=True)
class VideoMetadata:
    title: str
    artists: list[str]
    album: str | None
    release_date: str | None
    track_number: int | None
    volume_number: int | None
    explicit: bool
    id: str

    @classmethod
    def from_dict(cls, data: dict) -> VideoMetadata:
        artists = [a.get("name", "Unknown") for a in data.get("artists", [])]
        return cls(
            title=data.get("title", "Unknown"),
            artists=artists,
            album=data.get("album", {}).get("title"),
            release_date=data.get("releaseDate") or data.get("streamStartDate"),
            track_number=data.get("trackNumber"),
            volume_number=data.get("volumeNumber"),
            explicit=data.get("explicit", False),
            id=str(data.get("id")),
        )

@dataclass(slots=True)
class Video(Media):
    meta: VideoMetadata
    downloadable: Downloadable
    config: Config
    folder: str
    db: Database
    download_path: str = ""

    async def rip(self):
        await self.preprocess()
        if not self.download_path: self._set_download_path()

        if os.path.isfile(self.download_path):
            console.print(f"[dim]   ↪ Skipped (Exists): {self.meta.title}[/dim]")
            if not self.db.downloaded(self.meta.id):
                self.db.set_downloaded(self.meta.id)
            remove_title(self.meta.title)
            return

        await self.download()
        await self.postprocess()

    async def preprocess(self):
        self._set_download_path()
        os.makedirs(self.folder, exist_ok=True)
        add_title(self.meta.title)

    async def download(self):
        if not self.download_path: self._set_download_path()
        if os.path.isfile(self.download_path): return

        async with global_download_semaphore(self.config.session.downloads):
            display_title = self.meta.title
            for attempt in range(1, 3): 
                try:
                    size = await self.downloadable.size()
                    desc = display_title if attempt == 1 else f"{display_title} (retry)"
                    
                    # For videos, we might download to a temp file (like .ts) first
                    # But if downloadable.extension is mp4, we can go direct.
                    # If it is .ts, we download to .ts then convert.
                    
                    target_path = self.download_path
                    if self.downloadable.extension == "ts":
                        target_path = self.download_path.replace(".mp4", ".ts")

                    handle = get_progress_callback(self.config.session.cli.progress_bars, size, desc)
                    with handle as update_fn:
                        await self.downloadable.download(target_path, update_fn)
                    
                    # If we downloaded a TS, we need to convert it here or in postprocess.
                    # Let's assume postprocess handles metadata and conversion if needed.
                    # But the User's code expects a path to a file.
                    if self.downloadable.extension == "ts":
                        # Store the TS path temporarily so postprocess knows
                        self._ts_path = target_path
                    
                    return
                except Exception as e:
                    if attempt == 1:
                        logger.error(f"Error '{self.meta.title}': {e}. Retrying...")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"Persistent error '{self.meta.title}': {e}")
                        self.db.set_failed(self.downloadable.source, "video", self.meta.id)

    async def postprocess(self):
        remove_title(self.meta.title)
        
        target_path = self.download_path
        if hasattr(self, "_ts_path") and os.path.exists(self._ts_path):
            # Convert TS to MP4
            await self._convert_ts_to_mp4(self._ts_path, self.download_path)
            if os.path.exists(self._ts_path):
                os.remove(self._ts_path)
        
        await self._add_video_metadata(Path(self.download_path))
        self.db.set_downloaded(self.meta.id)

    async def _convert_ts_to_mp4(self, input_path: str, output_path: str):
        # ffmpeg -i input.ts -c copy output.mp4
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
            raise Exception("FFmpeg conversion failed")

    async def _add_video_metadata(self, path: Path):
        """
        Adds metadata to an MP4 video file.
        Based on user provided code.
        """
        if not path.exists():
            return

        try:
            mutagen = EasyMP4(path)
        except Exception as e:
            logger.error(f"could not open MP4 for metadata: {path} -> {e}")
            return

        artists_str = ";".join(self.meta.artists)
        
        meta_update = {
            "title": self.meta.title,
            "artist": artists_str,
        }

        if self.meta.album:
            meta_update["album"] = self.meta.album
        
        if self.meta.release_date:
            meta_update["date"] = str(self.meta.release_date)

        if self.meta.track_number:
            meta_update["tracknumber"] = str(self.meta.track_number)

        if self.meta.volume_number:
            meta_update["discnumber"] = str(self.meta.volume_number)

        try:
            clean_update = {k: v for k, v in meta_update.items() if v is not None}
            mutagen.update(clean_update)
            mutagen.save(path)
        except Exception as e:
            logger.error(f"could not save MP4 metadata: {path} -> {e}")

    def _set_download_path(self):
        # Use a simple format for videos: Artist - Title
        # Or reuse track format if suitable
        filename = f"{self.meta.artists[0]} - {self.meta.title}"
        filename = clean_filename(filename)
        self.download_path = os.path.join(self.folder, f"{filename}.mp4")


@dataclass(slots=True)
class PendingVideo(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Video | None:
        try:
            meta_dict = await self.client.get_metadata(self.id, "video")
            meta = VideoMetadata.from_dict(meta_dict)
            
            downloadable = await self.client.get_downloadable(self.id, media_type="video")
            
            folder = os.path.join(self.config.session.filepaths.folder, "Videos")
            
            return Video(
                meta=meta,
                downloadable=downloadable,
                config=self.config,
                folder=folder,
                db=self.db
            )
        except Exception as e:
            logger.error(f"Failed to resolve video {self.id}: {e}")
            return None
