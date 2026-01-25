import asyncio
import html
import logging
import os
import random
import re
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from rich.text import Text

from .. import progress
from ..client import Client
from ..config import Config
from ..console import console
from ..db import Database
from ..exceptions import NonStreamableError
# --- IMPORTAMOS LA NUEVA FUNCIÓN ---
from ..filepath_utils import clean_filepath, clean_filename, clean_track_title
from ..metadata import (
    AlbumMetadata,
    Covers,
    PlaylistMetadata,
    SearchResults,
    TrackMetadata,
)
from ..utils.ssl_utils import get_aiohttp_connector_kwargs
from .artwork import download_artwork
from .media import Media, Pending
from .track import Track

logger = logging.getLogger("streamrip")


def _get_custom_playlist_folder() -> str | None:
    possible_paths = [
        Path(os.environ.get("APPDATA", "")) / "streamrip" / "config.toml",
        Path.home() / ".config" / "streamrip" / "config.toml",
        Path("config.toml"),
    ]

    config_path = None
    for p in possible_paths:
        if p.exists() and p.is_file():
            config_path = p
            break
    
    if not config_path:
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r'^\s*#?\s*playlist_folder\s*=\s*"(.*)"', line)
                if match:
                    path = match.group(1)
                    return path.replace("\\\\", "\\")
    except Exception:
        pass
    
    return None


@dataclass(slots=True)
class PendingPlaylistTrack(Pending):
    id: str
    client: Client
    config: Config
    folder: str
    playlist_name: str
    position: int
    db: Database
    preloaded_data: dict | None = None

    async def resolve(self) -> Track | None:
        if self.preloaded_data:
            resp = self.preloaded_data
        else:
            try:
                resp = await self.client.get_metadata(self.id, "track")
            except NonStreamableError as e:
                logger.error(f"Could not stream track {self.id}: {e}")
                return None

        album = AlbumMetadata.from_track_resp(resp, self.client.source)
        if album is None:
            logger.error(f"Track ({self.id}) not available.")
            self.db.set_failed(self.client.source, "track", self.id)
            return None
        
        meta = TrackMetadata.from_resp(album, self.client.source, resp)
        if meta is None:
            logger.error(f"Track metadata error ({self.id}).")
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        c = self.config.session.metadata
        if c.renumber_playlist_tracks:
            meta.tracknumber = self.position
        if c.set_playlist_to_album:
            album.album = self.playlist_name

        # --- CARPETA POR ÁLBUM ---
        restrict_chars = self.config.session.filepaths.restrict_characters
        safe_album_name = clean_filename(meta.album, restrict=restrict_chars)
        track_folder = os.path.join(self.folder, safe_album_name)
        os.makedirs(track_folder, exist_ok=True)

        # --- LIMPIEZA DE NOMBRES UNIFICADA ---
        formatter = self.config.session.filepaths.track_format
        track_path = meta.format_track_path(formatter)
        
        # USAMOS LA FUNCIÓN CENTRALIZADA
        track_path = clean_track_title(track_path, meta.artist)
        
        if meta.info.explicit and "explicit" not in track_path.lower():
            track_path += " [explicit]"
        
        track_path = clean_filename(track_path, restrict=restrict_chars)
        if self.config.session.filepaths.truncate_to > 0:
            track_path = track_path[:self.config.session.filepaths.truncate_to]
        
        expected_paths = [
            os.path.join(track_folder, f"{track_path}.flac"),
            os.path.join(track_folder, f"{track_path}.m4a"),
            os.path.join(track_folder, f"{track_path}.mp3"),
        ]
        
        file_exists = any(os.path.isfile(path) for path in expected_paths)
        
        if self.db.downloaded(self.id):
            if file_exists:
                console.print(f"[dim]   ↪ Skipped (Exists): {meta.artist} - {meta.title}[/dim]")
                return None
            else:
                console.print(f"[yellow]   ! File missing in DB, re-downloading: {meta.title}[/yellow]")
        elif file_exists:
            console.print(f"[dim]   ↪ Skipped (Found on disk): {meta.artist} - {meta.title}[/dim]")
            self.db.set_downloaded(self.id)
            return None

        quality = self.config.session.get_source(self.client.source).quality
        try:
            embedded_cover_path, downloadable = await asyncio.gather(
                self._download_cover(album.covers, track_folder),
                self.client.get_downloadable(self.id, quality),
            )
        except NonStreamableError as e:
            logger.error(f"Error fetching download info: {e}")
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        return Track(
            meta,
            downloadable,
            self.config,
            track_folder, 
            embedded_cover_path,
            self.db,
            from_playlist=True
        )

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(
            self.client.session,
            folder,
            covers,
            self.config.session.artwork,
            for_playlist=True,
        )
        return embed_path


@dataclass(slots=True)
class Playlist(Media):
    name: str
    config: Config
    client: Client
    tracks: list[PendingPlaylistTrack]

    async def preprocess(self):
        progress.add_title(self.name)

    async def postprocess(self):
        progress.remove_title(self.name)

    async def download(self):
        track_resolve_chunk_size = 20

        async def _resolve_download(item: PendingPlaylistTrack):
            try:
                track = await item.resolve()
                if track is None:
                    return
                await track.rip()
            except Exception as e:
                logger.error(f"Error downloading track: {e}")

        batches = self.batch(
            [_resolve_download(track) for track in self.tracks],
            track_resolve_chunk_size,
        )

        for batch in batches:
            results = await asyncio.gather(*batch, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Batch processing error: {result}")

    @staticmethod
    def batch(iterable, n=1):
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


@dataclass(slots=True)
class PendingPlaylist(Pending):
    id: str
    client: Client
    config: Config
    db: Database
    media_type: str = "playlist"

    async def resolve(self) -> Playlist | None:
        try:
            resp = await self.client.get_metadata(self.id, self.media_type)
        except NonStreamableError as e:
            logger.error(f"Playlist unavailable: {e}")
            return None

        try:
            meta = PlaylistMetadata.from_resp(resp, self.client.source)
        except Exception as e:
            logger.error(f"Error creating playlist: {e}")
            return None
        
        name = meta.name
        
        custom_path = _get_custom_playlist_folder()
        if custom_path:
            parent = custom_path
        else:
            parent = self.config.session.downloads.folder
        
        restrict_chars = self.config.session.filepaths.restrict_characters
        safe_name = clean_filename(name, restrict=restrict_chars)
        
        folder = os.path.join(parent, safe_name)
        
        raw_tracks = resp.get("tracks", [])
        ids = meta.ids()
        
        tracks = []
        for i, track_id in enumerate(ids):
            cached = raw_tracks[i] if i < len(raw_tracks) else None
            tracks.append(PendingPlaylistTrack(
                track_id, self.client, self.config, folder, name, i + 1, self.db, preloaded_data=cached
            ))
        
        return Playlist(name, self.config, self.client, tracks)


@dataclass(slots=True)
class PendingLastfmPlaylist(Pending):
    lastfm_url: str
    client: Client
    fallback_client: Client | None
    config: Config
    db: Database

    @dataclass(slots=True)
    class Status:
        found: int
        failed: int
        total: int

        def text(self) -> Text:
            return Text.assemble(
                "Searching Last.fm (",
                (f"{self.found} found", "green"),
                ", ",
                (f"{self.failed} failed", "red"),
                ")",
            )

    async def resolve(self) -> Playlist | None:
        try:
            playlist_title, titles_artists = await self._parse_lastfm_playlist(self.lastfm_url)
        except Exception as e:
            logger.error(f"Last.fm parse error: {e}")
            return None

        requests = []
        s = self.Status(0, 0, len(titles_artists))
        
        if self.config.session.cli.progress_bars:
            with console.status(s.text(), spinner="moon") as status:
                def callback(): status.update(s.text())
                for title, artist in titles_artists:
                    requests.append(self._make_query(f"{title} {artist}", s, callback))
                results = await asyncio.gather(*requests)
        else:
            def callback(): pass
            for title, artist in titles_artists:
                requests.append(self._make_query(f"{title} {artist}", s, callback))
            results = await asyncio.gather(*requests)

        custom_path = _get_custom_playlist_folder()
        if custom_path:
            parent = custom_path
        else:
            parent = self.config.session.downloads.folder

        restrict = self.config.session.filepaths.restrict_characters
        safe_title = clean_filename(playlist_title, restrict=restrict)
        folder = os.path.join(parent, safe_title)

        pending_tracks = []
        for pos, (id, from_fallback) in enumerate(results, start=1):
            if id is None: continue
            client = self.fallback_client if from_fallback else self.client
            pending_tracks.append(PendingPlaylistTrack(
                id, client, self.config, folder, playlist_title, pos, self.db
            ))

        return Playlist(playlist_title, self.config, self.client, pending_tracks)

    async def _make_query(self, query: str, search_status: Status, callback) -> tuple[str | None, bool]:
        with ExitStack() as stack:
            stack.callback(callback)
            pages = await self.client.search("track", query, limit=1)
            if len(pages) > 0:
                search_status.found += 1
                return (SearchResults.from_pages(self.client.source, "track", pages).results[0].id), False

            if self.fallback_client:
                pages = await self.fallback_client.search("track", query, limit=1)
                if len(pages) > 0:
                    search_status.found += 1
                    return (SearchResults.from_pages(self.fallback_client.source, "track", pages).results[0].id), True

            search_status.failed += 1
        return None, True

    async def _parse_lastfm_playlist(self, playlist_url: str) -> tuple[str, list[tuple[str, str]]]:
        title_tags = re.compile(r'<a\s+href="[^"]+"\s+title="([^"]+)"')
        re_total_tracks = re.compile(r'data-playlisting-entry-count="(\d+)"')
        re_playlist_title = re.compile(r'<h1 class="playlisting-playlist-header-title">([^<]+)</h1>')

        def find_pairs(text):
            info = []
            titles = title_tags.findall(text)
            for i in range(0, len(titles) - 1, 2):
                info.append((html.unescape(titles[i]), html.unescape(titles[i + 1])))
            return info

        async def fetch(session, url, **kwargs):
            async with session.get(url, **kwargs) as resp: return await resp.text("utf-8")

        verify_ssl = getattr(self.config.session.downloads, "verify_ssl", True)
        connector = aiohttp.TCPConnector(**get_aiohttp_connector_kwargs(verify_ssl=verify_ssl))

        async with aiohttp.ClientSession(connector=connector) as session:
            page = await fetch(session, playlist_url)
            title_match = re_playlist_title.search(page)
            if not title_match: raise Exception("Title not found")
            playlist_title = html.unescape(title_match.group(1))
            
            pairs = find_pairs(page)
            total_match = re_total_tracks.search(page)
            
            if total_match:
                total = int(total_match.group(1))
                if total > 50:
                    last = 1 + int((total - 50) // 50) + int((total - 50) % 50 != 0)
                    reqs = [fetch(session, playlist_url, params={"page": p}) for p in range(2, last + 1)]
                    res = await asyncio.gather(*reqs)
                    for r in res: pairs.extend(find_pairs(r))

        return playlist_title, pairs
