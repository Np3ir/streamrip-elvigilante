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
from ..filepath_utils import clean_filename
from ..metadata import AlbumMetadata, Covers, TrackMetadata, tag_file
from ..progress import add_title, get_progress_callback, remove_title
from .artwork import download_artwork
from .media import Media, Pending
from .semaphore import global_download_semaphore

logger = logging.getLogger("streamrip")

# Helper function to compare names ignoring dots, commas and symbols
def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Remove anything that is NOT a letter or number and convert to lowercase
    # Ex: "fun., Janelle Monáe" -> "funjanellemonae"
    return re.sub(r'[\W_]+', '', text).lower()

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

    async def preprocess(self):
        self._set_download_path()
        os.makedirs(self.folder, exist_ok=True)
        if self.is_single:
            add_title(self.meta.title)

    async def download(self):
        if not self.download_path:
            self._set_download_path()

        # Check physical file
        if os.path.isfile(self.download_path):
            if not self.db.downloaded(self.meta.info.id):
                logger.info(f"[!] Track exists on disk but not in database. Registering: {os.path.basename(self.download_path)}")
                self.db.set_downloaded(self.meta.info.id)
            return

        async with global_download_semaphore(self.config.session.downloads):
            # Truncate artist and title for the progress bar if too long
            artist = self.meta.artist if (self.meta.artist and self.meta.artist.strip()) else "Unknown Artist"
            if len(artist) > 25:
                artist = artist[:22] + "..."
                
            title = self.meta.title if (self.meta.title and self.meta.title.strip()) else f"Track {self.meta.tracknumber}"
            if len(title) > 35:
                title = title[:32] + "..."
            
            track_num = str(self.meta.tracknumber).zfill(2)
            full_desc = f"{track_num} {artist} - {title}"

            # Use Handle correctly with context manager
            handle = get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                full_desc
            )
            
            # First attempt
            try:
                with handle as update_fn:
                    await self.downloadable.download(self.download_path, update_fn)
                return  # Success
            except (asyncio.TimeoutError, Exception) as e:
                logger.error(f"Error downloading '{self.meta.title}', retrying: {e}")
                # Short pause before retry
                await asyncio.sleep(2)
            
            # Second attempt (Retry)
            handle_retry = get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                full_desc
            )
            
            try:
                with handle_retry as update_fn:
                    await self.downloadable.download(self.download_path, update_fn)
            except (asyncio.TimeoutError, Exception) as e:
                logger.error(f"Persistent error '{self.meta.title}', skipping: {e}")
                self.db.set_failed(self.downloadable.source, "track", self.meta.info.id)

    async def postprocess(self):
        if self.is_single:
            remove_title(self.meta.title)

        await tag_file(self.download_path, self.meta, self.cover_path)
        if self.config.session.conversion.enabled:
            await self._convert()

        self.db.set_downloaded(self.meta.info.id)

    async def _convert(self):
        c = self.config.session.conversion
        engine_class = converter.get(c.codec)
        engine = engine_class(
            filename=self.download_path,
            sampling_rate=c.sampling_rate,
            bit_depth=c.bit_depth,
            remove_source=True,
        )
        await engine.convert()
        self.download_path = engine.final_fn

    def _set_download_path(self):
        c = self.config.session.filepaths
        formatter = c.track_format
        track_path = self.meta.format_track_path(formatter)
        
        # --- SMART "FUZZY" LOGIC TO REMOVE FEATURINGS ---
        # Detects (feat. X), (ft. X), (with X), (starring X)
        match = re.search(r"\s*\((?:f(?:ea)?t\.?|with|starring)\s+(.*?)\)", track_path, flags=re.IGNORECASE)
        
        if match:
            full_match_text = match.group(0)  # "(feat. Janelle Monae)"
            feat_artist_name = match.group(1)  # "Janelle Monae"
            
            # Normalize both names (remove dots, accents, symbols)
            simple_feat = normalize_text(feat_artist_name)
            simple_main_artist = normalize_text(self.meta.artist)
            
            # Compare simplified versions
            # If "janellemonae" is inside "funjanellemonae", remove.
            if len(simple_feat) > 2 and simple_feat in simple_main_artist:
                track_path = track_path.replace(full_match_text, "")
                # Clean double spaces that might have been left
                track_path = re.sub(r'\s+', ' ', track_path).strip()
        # ----------------------------------------------------

        if self.meta.info.explicit and "explicit" not in track_path.lower():
            track_path += " [Explicit]"

        track_path = clean_filename(track_path, restrict=c.restrict_characters)

        if c.truncate_to > 0 and len(track_path) > c.truncate_to:
            track_path = track_path[: c.truncate_to]

        self.download_path = os.path.join(self.folder, f"{track_path}.{self.downloadable.extension}")


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str
    db: Database
    cover_path: str | None

    async def resolve(self) -> Track | None:
        source = self.client.source
        
        # Verificación híbrida (DB + Disponibilidad online)
        if self.db.downloaded(self.id):
            try:
                resp = await self.client.get_metadata(self.id, "track")
            except NonStreamableError as e:
                logger.error(f"Track {self.id} unavailable on {source}: {e}")
                return None

            try:
                meta = TrackMetadata.from_resp(self.album, source, resp)
            except Exception as e:
                logger.error(f"Error building metadata {self.id}: {e}")
                return None

            if meta is None:
                self.db.set_failed(source, "track", self.id)
                return None

            downloads_config = self.config.session.downloads
            if downloads_config.disc_subdirectories and self.album.disctotal > 1:
                folder = os.path.join(self.folder, f"Disc {meta.discnumber}")
            else:
                folder = self.folder
            
            c = self.config.session.filepaths
            formatter = c.track_format
            track_path = meta.format_track_path(formatter)
            
            # --- FEATURING LOGIC FOR PENDING ---
            match = re.search(r"\s*\((?:f(?:ea)?t\.?|with|starring)\s+(.*?)\)", track_path, flags=re.IGNORECASE)
            if match:
                full_match_text = match.group(0)
                feat_artist_name = match.group(1)
                
                simple_feat = normalize_text(feat_artist_name)
                simple_main_artist = normalize_text(meta.artist)
                
                if len(simple_feat) > 2 and simple_feat in simple_main_artist:
                    track_path = track_path.replace(full_match_text, "")
                    track_path = re.sub(r'\s+', ' ', track_path).strip()
            # -------------------------------------

            if meta.info.explicit and "explicit" not in track_path.lower():
                track_path += " [Explicit]"

            track_path = clean_filename(track_path, restrict=c.restrict_characters)
            if c.truncate_to > 0 and len(track_path) > c.truncate_to:
                track_path = track_path[: c.truncate_to]

            quality = self.config.session.get_source(source).quality
            try:
                downloadable = await self.client.get_downloadable(self.id, quality)
            except NonStreamableError as e:
                logger.error(f"Error getting download info {self.id}: {e}")
                return None

            file_path = os.path.join(folder, f"{track_path}.{downloadable.extension}")
            
            if os.path.isfile(file_path):
                logger.info(f"[✓] Track already exists and registered: {os.path.basename(file_path)}")
                return None
            else:
                logger.warning(f"[!] Track in database but file missing. Re-downloading: {os.path.basename(file_path)}")
                try:
                    cover_path = self.cover_path
                except:
                    cover_path = None
                
                return Track(meta, downloadable, self.config, folder, cover_path, self.db)
        
        # NO está en DB, proceder descarga normal
        try:
            resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError as e:
            logger.error(f"Track {self.id} unavailable on {source}: {e}")
            return None

        try:
            meta = TrackMetadata.from_resp(self.album, source, resp)
        except Exception as e:
            logger.error(f"Error building metadata {self.id}: {e}")
            return None

        if meta is None:
            self.db.set_failed(source, "track", self.id)
            return None

        quality = self.config.session.get_source(source).quality
        try:
            downloadable = await self.client.get_downloadable(self.id, quality)
        except NonStreamableError as e:
            logger.error(f"Error getting download info {self.id}: {e}")
            return None

        downloads_config = self.config.session.downloads
        if downloads_config.disc_subdirectories and self.album.disctotal > 1:
            folder = os.path.join(self.folder, f"Disc {meta.discnumber}")
        else:
            folder = self.folder

        return Track(meta, downloadable, self.config, folder, self.cover_path, self.db)


@dataclass(slots=True)
class PendingSingle(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Track | None:
        # Verificación híbrida para singles también
        if self.db.downloaded(self.id):
            try:
                resp = await self.client.get_metadata(self.id, "track")
            except NonStreamableError as e:
                logger.error(f"Error fetching track {self.id}: {e}")
                return None

            try:
                album = AlbumMetadata.from_track_resp(resp, self.client.source)
            except Exception as e:
                logger.error(f"Error building album meta {self.id}: {e}")
                return None

            if album is None:
                self.db.set_failed(self.client.source, "track", self.id)
                return None

            try:
                meta = TrackMetadata.from_resp(album, self.client.source, resp)
            except Exception as e:
                logger.error(f"Error building track meta {self.id}: {e}")
                return None

            if meta is None:
                self.db.set_failed(self.client.source, "track", self.id)
                return None

            config = self.config.session
            quality = getattr(config, self.client.source).quality
            parent = config.downloads.folder
            folder = os.path.join(parent, self._format_folder(album)) if config.filepaths.add_singles_to_folder else parent
            
            c = config.filepaths
            formatter = c.track_format
            track_path = meta.format_track_path(formatter)
            
            # --- FEATURING LOGIC FOR SINGLE ---
            match = re.search(r"\s*\((?:f(?:ea)?t\.?|with|starring)\s+(.*?)\)", track_path, flags=re.IGNORECASE)
            if match:
                full_match_text = match.group(0)
                feat_artist_name = match.group(1)
                
                simple_feat = normalize_text(feat_artist_name)
                simple_main_artist = normalize_text(meta.artist)
                
                if len(simple_feat) > 2 and simple_feat in simple_main_artist:
                    track_path = track_path.replace(full_match_text, "")
                    track_path = re.sub(r'\s+', ' ', track_path).strip()
            # ------------------------------------

            if meta.info.explicit and "explicit" not in track_path.lower():
                track_path += " [Explicit]"

            track_path = clean_filename(track_path, restrict=c.restrict_characters)
            if c.truncate_to > 0 and len(track_path) > c.truncate_to:
                track_path = track_path[: c.truncate_to]

            downloadable = await self.client.get_downloadable(self.id, quality)
            file_path = os.path.join(folder, f"{track_path}.{downloadable.extension}")
            
            if os.path.isfile(file_path):
                logger.info(f"[✓] Single already exists and registered: {os.path.basename(file_path)}")
                return None
            else:
                logger.warning(f"[!] Single in database but file missing. Re-downloading: {os.path.basename(file_path)}")
                os.makedirs(folder, exist_ok=True)
                embedded_cover_path = await self._download_cover(album.covers, folder)
                return Track(meta, downloadable, self.config, folder, embedded_cover_path, self.db, is_single=True)
        
        # NO está en DB - descarga normal
        try:
            resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError as e:
            logger.error(f"Error fetching track {self.id}: {e}")
            return None

        try:
            album = AlbumMetadata.from_track_resp(resp, self.client.source)
        except Exception as e:
            logger.error(f"Error building album meta {self.id}: {e}")
            return None

        if album is None:
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        try:
            meta = TrackMetadata.from_resp(album, self.client.source, resp)
        except Exception as e:
            logger.error(f"Error building track meta {self.id}: {e}")
            return None

        if meta is None:
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        config = self.config.session
        quality = getattr(config, self.client.source).quality
        parent = config.downloads.folder

        folder = os.path.join(parent, self._format_folder(album)) if config.filepaths.add_singles_to_folder else parent
        os.makedirs(folder, exist_ok=True)

        embedded_cover_path, downloadable = await asyncio.gather(
            self._download_cover(album.covers, folder),
            self.client.get_downloadable(self.id, quality),
        )
        return Track(meta, downloadable, self.config, folder, embedded_cover_path, self.db, is_single=True)

    def _format_folder(self, meta: AlbumMetadata) -> str:
        c = self.config.session
        parent = os.path.join(c.downloads.folder,
                              self.client.source.capitalize()) if c.downloads.source_subdirectories else c.downloads.folder
        return os.path.join(parent, meta.format_folder_path(c.filepaths.folder_format))

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(
            self.client.session,
            folder,
            covers,
            self.config.session.artwork,
            for_playlist=False,
        )
        return embed_path