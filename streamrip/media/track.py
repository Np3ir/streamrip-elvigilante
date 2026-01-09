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

        # Verificar si el archivo existe físicamente
        if os.path.isfile(self.download_path):
            # Archivo existe - registrar en DB si no está
            if not self.db.downloaded(self.meta.info.id):
                logger.info(f"[!] Track exists on disk but not in database. Registering: {os.path.basename(self.download_path)}")
                self.db.set_downloaded(self.meta.info.id)
            return

        # Si llegamos aquí, el archivo NO existe - proceder con descarga
        async with global_download_semaphore(self.config.session.downloads):
            # Formato simple: número, artista y título
            artist = self.meta.artist if (self.meta.artist and self.meta.artist.strip()) else "Unknown Artist"
            title = self.meta.title if (self.meta.title and self.meta.title.strip()) else f"Track {self.meta.tracknumber}"
            
            track_num = str(self.meta.tracknumber).zfill(2)
            full_desc = f"{track_num} {artist} - {title}"

            callback = get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                full_desc
            )
            
            retry = False
            try:
                await self.downloadable.download(self.download_path, callback)
            except Exception as e:
                logger.error(f"Error downloading '{self.meta.title}', retrying: {e}")
                retry = True

            if not retry:
                return

            callback_retry = get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                f"{full_desc} (retry)"
            )
            
            try:
                await self.downloadable.download(self.download_path, callback_retry)
            except Exception as e:
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
        
        # Eliminar featuring duplicado
        match = re.search(r"\s*\(f(?:ea)?t\.?\s+(.*?)\)", track_path, flags=re.IGNORECASE)
        
        if match:
            feat_artist = match.group(1)
            if feat_artist.lower() in self.meta.artist.lower():
                track_path = track_path.replace(match.group(0), "")

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
        
        # ================================================================
        # OPCIÓN C: HÍBRIDO - Verificar DB primero
        # ================================================================
        if self.db.downloaded(self.id):
            # Está en DB - necesitamos verificar archivo físico
            # Para eso necesitamos construir la ruta del archivo
            
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

            # Construir ruta del archivo para verificar
            downloads_config = self.config.session.downloads
            if downloads_config.disc_subdirectories and self.album.disctotal > 1:
                folder = os.path.join(self.folder, f"Disc {meta.discnumber}")
            else:
                folder = self.folder
            
            c = self.config.session.filepaths
            formatter = c.track_format
            track_path = meta.format_track_path(formatter)
            
            # Eliminar featuring duplicado
            match = re.search(r"\s*\(f(?:ea)?t\.?\s+(.*?)\)", track_path, flags=re.IGNORECASE)
            if match:
                feat_artist = match.group(1)
                if feat_artist.lower() in meta.artist.lower():
                    track_path = track_path.replace(match.group(0), "")

            if meta.info.explicit and "explicit" not in track_path.lower():
                track_path += " [Explicit]"

            track_path = clean_filename(track_path, restrict=c.restrict_characters)
            if c.truncate_to > 0 and len(track_path) > c.truncate_to:
                track_path = track_path[: c.truncate_to]

            # Necesitamos saber la extensión - obtener downloadable
            quality = self.config.session.get_source(source).quality
            try:
                downloadable = await self.client.get_downloadable(self.id, quality)
            except NonStreamableError as e:
                logger.error(f"Error getting download info {self.id}: {e}")
                return None

            file_path = os.path.join(folder, f"{track_path}.{downloadable.extension}")
            
            # Verificar si el archivo existe físicamente
            if os.path.isfile(file_path):
                # Archivo existe y está en DB - Skip silencioso
                logger.info(f"[✓] Track already exists and registered: {os.path.basename(file_path)}")
                return None
            else:
                # Archivo NO existe pero está en DB - Re-descarga
                logger.warning(f"[!] Track in database but file missing. Re-downloading: {os.path.basename(file_path)}")
                # Continuar y crear Track para re-descargar
                try:
                    cover_path = self.cover_path
                except:
                    cover_path = None
                
                return Track(meta, downloadable, self.config, folder, cover_path, self.db)
        
        # ================================================================
        # NO está en DB - Descarga normal
        # ================================================================
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
        # Para singles, aplicar misma lógica híbrida
        if self.db.downloaded(self.id):
            # Verificar archivo físico
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
            
            # Eliminar featuring duplicado
            match = re.search(r"\s*\(f(?:ea)?t\.?\s+(.*?)\)", track_path, flags=re.IGNORECASE)
            if match:
                feat_artist = match.group(1)
                if feat_artist.lower() in meta.artist.lower():
                    track_path = track_path.replace(match.group(0), "")

            if meta.info.explicit and "explicit" not in track_path.lower():
                track_path += " [Explicit]"

            track_path = clean_filename(track_path, restrict=c.restrict_characters)
            if c.truncate_to > 0 and len(track_path) > c.truncate_to:
                track_path = track_path[: c.truncate_to]

            # Obtener downloadable para extensión
            downloadable = await self.client.get_downloadable(self.id, quality)
            file_path = os.path.join(folder, f"{track_path}.{downloadable.extension}")
            
            if os.path.isfile(file_path):
                logger.info(f"[✓] Single already exists and registered: {os.path.basename(file_path)}")
                return None
            else:
                logger.warning(f"[!] Single in database but file missing. Re-downloading: {os.path.basename(file_path)}")
                # Continuar para re-descargar
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