import logging
from dataclasses import dataclass

from ..client import Client
from ..config import Config
from ..db import Database
from ..exceptions import NonStreamableError
from .media import Media, Pending
from .playlist import PendingPlaylist, Playlist

logger = logging.getLogger("streamrip")

@dataclass(slots=True)
class User(Media):
    """Represents a user's collection (playlists)."""
    name: str
    playlists: list[PendingPlaylist]
    client: Client
    config: Config

    async def preprocess(self):
        pass

    async def download(self):
        # Resolve and download each playlist
        # We process them sequentially or in batches?
        # Playlists are usually large, so sequential resolution might be safer for rate limits
        # but parallel download is better.
        # Let's use batching similar to Artist
        
        chunk_size = 5
        
        async def _rip(item: PendingPlaylist):
            playlist = await item.resolve()
            if playlist:
                await playlist.rip()

        batches = self.batch(
            [_rip(p) for p in self.playlists],
            chunk_size,
        )
        for batch in batches:
            import asyncio
            await asyncio.gather(*batch)

    async def postprocess(self):
        pass
    
    @staticmethod
    def batch(iterable, n=1):
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


@dataclass(slots=True)
class PendingUser(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> User | None:
        try:
            # We treat "user" as a media type that returns a list of playlists
            resp = await self.client.get_metadata(self.id, "user")
        except NonStreamableError as e:
            logger.error(f"User {self.id} not available: {e}")
            return None
        
        name = resp.get("username", f"User {self.id}")
        raw_playlists = resp.get("playlists", [])
        
        playlists = []
        for p in raw_playlists:
            if "uuid" in p:
                pid = p["uuid"]
                playlists.append(PendingPlaylist(pid, self.client, self.config, self.db))
        
        return User(name, playlists, self.client, self.config)
