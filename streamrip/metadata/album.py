from __future__ import annotations

import logging
import re
import os
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone, timedelta

from ..filepath_utils import clean_filename, clean_filepath
from .covers import Covers
from .util import get_quality_id, safe_get, typed

PHON_COPYRIGHT = "℗"
COPYRIGHT = "©"

logger = logging.getLogger("streamrip")

genre_clean = re.compile(r"([^→\/]+)")


@dataclass(slots=True)
class AlbumInfo:
    id: str
    quality: int
    container: str
    label: Optional[str] = None
    explicit: bool = False
    sampling_rate: int | float | None = None
    bit_depth: int | None = None
    booklets: list[dict] | None = None


@dataclass(slots=True)
class AlbumMetadata:
    info: AlbumInfo
    album: str
    albumartist: str
    year: str
    genre: list[str]
    covers: Covers
    tracktotal: int
    disctotal: int = 1
    albumcomposer: str | None = None
    comment: str | None = None
    compilation: str | None = None
    copyright: str | None = None
    date: str | None = None
    description: str | None = None
    encoder: str | None = None
    grouping: str | None = None
    lyrics: str | None = None
    purchase_date: str | None = None
    release_date: str = "Unknown"

    def get_genres(self) -> str:
        return ", ".join(self.genre)

    def get_copyright(self) -> str | None:
        if self.copyright is None:
            return None
        _copyright = re.sub(r"(?i)\(P\)", PHON_COPYRIGHT, self.copyright)
        _copyright = re.sub(r"(?i)\(C\)", COPYRIGHT, _copyright)
        return _copyright

    def format_folder_path(self, formatter: str) -> str:
        none_str = "Unknown"
        # Date correction for folders
        release_date_clean = self.release_date.replace(":", "-").replace("/", "-")

        # --- INITIALS LOGIC (A-Z vs #) ---
        raw_artist = self.albumartist.strip()
        # Ignore "The " at the start
        if raw_artist.lower().startswith("the "):
            sort_name = raw_artist[4:].strip()
        else:
            sort_name = raw_artist

        # Calculate initial
        if sort_name:
            initial = sort_name[0].upper()
            # If NOT a Latin letter (A-Z, etc), goes to "#" folder
            if not re.match(r'^[A-Z\u00C0-\u00FF]$', initial):
                initial = "#"
        else:
            initial = "Unknown"

        initials_clean = clean_filename(initial)
        # --------------------------------------

        # Prepare clean variables
        artist_clean = clean_filename(self.albumartist)
        album_clean = clean_filename(self.album)

        info: dict[str, str | int | float] = {
            # New variable requested in config
            "artist_initials": initials_clean,

            # Standard variables
            "id": self.info.id,
            "year": self.year,
            "container": self.info.container,
            "bit_depth": self.info.bit_depth or none_str,
            "sampling_rate": self.info.sampling_rate or none_str,
            "release_date": release_date_clean or none_str,
            "albumartist": artist_clean,
            "title": album_clean,
            "albumcomposer": clean_filename(self.albumcomposer or "") or none_str,

            # Extra aliases for easier config
            "artist": artist_clean,
            "album": album_clean
        }
        return clean_filepath(formatter.format(**info))

    @staticmethod
    def correct_release_date(raw_date: str | None) -> tuple[str, str]:
        """Corrects date by subtracting one day and returns (full_date, year)."""
        try:
            if raw_date:
                # Adjustment: subtract 1 day from original date
                dt = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
                dt -= timedelta(days=1)
                return str(dt), str(dt.year)
        except Exception as e:
            logger.warning(f"Invalid release_date: {raw_date} ({e})")

        # Fallback if conversion fails
        year = raw_date[:4] if raw_date else "Unknown"
        return raw_date or "Unknown", year

    @classmethod
    def from_qobuz(cls, resp: dict) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        tracktotal = resp.get("tracks_count", 1)
        genre = resp.get("genres_list") or resp.get("genre") or []
        genres = list(set(genre_clean.findall("/".join(genre))))
        raw_date = resp.get("release_date_original") or resp.get("release_date")
        release_date, year = cls.correct_release_date(raw_date)
        _copyright = resp.get("copyright", "")
        if artists := resp.get("artists"):
            albumartist = artists[0]["name"]
        else:
            albumartist = typed(safe_get(resp, "artist", "name"), str)
        albumcomposer = typed(safe_get(resp, "composer", "name", default=""), str)
        _label = resp.get("label")
        if isinstance(_label, dict):
            _label = _label["name"]
        label = typed(_label or "", str)
        description = typed(resp.get("description", ""), str)
        disctotal = typed(
            max(track.get("media_number", 1) for track in safe_get(resp, "tracks", "items", default=[{}])) or 1,
            int,
        )
        explicit = typed(resp.get("parental_warning", False), bool)
        cover_urls = Covers.from_qobuz(resp)
        bit_depth = typed(resp.get("maximum_bit_depth", -1), int)
        sampling_rate = typed(resp.get("maximum_sampling_rate", -1.0), int | float)
        quality = get_quality_id(bit_depth, sampling_rate)
        booklets = typed(resp.get("goodies", None) or None, list | None)
        item_id = str(resp.get("qobuz_id"))
        container = "FLAC" if sampling_rate and bit_depth else "MP3"
        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=label,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=booklets,
        )
        return AlbumMetadata(
            info, album, albumartist, year, genre=genres, covers=cover_urls,
            albumcomposer=albumcomposer, comment=None, compilation=None,
            copyright=_copyright, date=release_date, description=description,
            disctotal=disctotal, encoder=None, grouping=None, lyrics=None,
            purchase_date=None, tracktotal=tracktotal, release_date=release_date,
        )

    @classmethod
    def from_tidal(cls, resp: dict) -> AlbumMetadata:
        """Parses standard Tidal album response."""
        album = resp.get("title", "Unknown Album")
        # Date handling with correction (-1 day)
        raw_date = resp.get("releaseDate") or resp.get("streamStartDate")
        release_date, year = cls.correct_release_date(raw_date)

        tracktotal = resp.get("numberOfTracks", 1)
        disctotal = resp.get("numberOfVolumes", 1)
        explicit = resp.get("explicit", False)
        copyright = resp.get("copyright")

        # Artist
        artist_obj = resp.get("artist", {})
        albumartist = artist_obj.get("name", "Unknown Artist")

        # Quality and Container
        tidal_quality = resp.get("audioQuality", "LOW")
        # Simple quality mapping
        quality_map = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES": 3}
        quality = quality_map.get(tidal_quality, 0)

        # Tech estimation
        sampling_rate = 44100 if quality >= 2 else None
        bit_depth = 24 if tidal_quality == "HI_RES" else (16 if quality >= 2 else None)
        container = "FLAC" if quality >= 2 else "MP4"

        item_id = str(resp.get("id"))
        covers = Covers.from_tidal(resp)

        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=None,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=None,
        )

        return AlbumMetadata(
            info=info,
            album=album,
            albumartist=albumartist,
            year=year,
            genre=[],
            covers=covers,
            albumcomposer=None,
            comment=None,
            compilation=None,
            copyright=copyright,
            date=release_date,
            description=None,
            disctotal=disctotal,
            encoder=None,
            grouping=None,
            lyrics=None,
            purchase_date=None,
            tracktotal=tracktotal,
            release_date=release_date,
        )

    @classmethod
    def from_deezer(cls, resp: dict) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        item_id = str(resp.get("id"))
        raw_date = resp.get("release_date")
        release_date, year = cls.correct_release_date(raw_date)
        tracktotal = resp.get("nb_tracks", 1)
        disctotal = 1
        explicit = resp.get("explicit_lyrics", False)
        artist_obj = resp.get("artist", {})
        albumartist = artist_obj.get("name", "Unknown Artist")
        genres_data = resp.get("genres", {}).get("data", [])
        genres = [g["name"] for g in genres_data]
        label = resp.get("label")
        copyright = resp.get("copyright")
        covers = Covers.from_deezer(resp)
        # Assume standard FLAC quality for Deezer
        quality = 2
        container = "FLAC"
        sampling_rate = 44100
        bit_depth = 16

        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=label,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=None,
        )

        return AlbumMetadata(
            info=info,
            album=album,
            albumartist=albumartist,
            year=year,
            genre=genres,
            covers=covers,
            albumcomposer=None,
            comment=None,
            compilation=None,
            copyright=copyright,
            date=release_date,
            description=None,
            disctotal=disctotal,
            encoder=None,
            grouping=None,
            lyrics=None,
            purchase_date=None,
            tracktotal=tracktotal,
            release_date=release_date,
        )

    @classmethod
    def from_soundcloud(cls, resp: dict) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        item_id = str(resp.get("id"))
        raw_date = resp.get("created_at")
        release_date, year = cls.correct_release_date(raw_date)
        tracktotal = resp.get("track_count", 1)
        user = resp.get("user", {})
        albumartist = user.get("username", "Unknown Artist")
        genre = resp.get("genre", "")
        genres = [genre] if genre else []
        description = resp.get("description")
        covers = Covers.from_soundcloud(resp)
        quality = 1
        container = "MP3"
        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=None,
            explicit=False,
            sampling_rate=None,
            bit_depth=None,
            booklets=None,
        )
        return AlbumMetadata(
            info=info,
            album=album,
            albumartist=albumartist,
            year=year,
            genre=genres,
            covers=covers,
            tracktotal=tracktotal,
            date=release_date,
            description=description,
            release_date=release_date,
        )

    @classmethod
    def from_tidal_playlist_track_resp(cls, resp: dict) -> AlbumMetadata | None:
        """Handles single track responses containing album info."""
        album_resp = resp.get("album", {})
        if not resp.get("allowStreaming", False):
            return None
        item_id = str(resp.get("id", ""))
        album = album_resp.get("title", "Unknown Album")
        tracktotal = 1
        raw_date = resp.get("streamStartDate") or resp.get("dateAdded")
        release_date, year = cls.correct_release_date(raw_date)
        copyright = resp.get("copyright", "")
        artists = resp.get("artists", [])
        albumartist = ", ".join(a["name"] for a in artists) or album_resp.get("artist", {}).get("name",
                                                                                                "Unknown Artist")
        disctotal = resp.get("volumeNumber", 1)
        explicit = resp.get("explicit", False)
        tidal_quality = resp.get("audioQuality", "LOW")
        quality_map = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES": 3}
        quality = quality_map.get(tidal_quality, 0)
        sampling_rate = 44100 if quality >= 2 else None
        bit_depth = 24 if tidal_quality == "HI_RES" else (16 if quality >= 2 else None)
        covers = Covers.from_tidal(album_resp) or Covers()
        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container="FLAC" if quality >= 2 else "MP4",
            label=None,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=None,
        )
        return AlbumMetadata(
            info=info,
            album=album,
            albumartist=albumartist,
            year=year,
            genre=[],
            covers=covers,
            albumcomposer=None,
            comment=None,
            compilation=None,
            copyright=copyright,
            date=release_date,
            description=None,
            disctotal=disctotal,
            encoder=None,
            grouping=None,
            lyrics=None,
            purchase_date=None,
            tracktotal=tracktotal,
            release_date=release_date,
        )

    @classmethod
    def from_album_resp(cls, resp: dict, source: str) -> AlbumMetadata | None:
        if source == "qobuz": return cls.from_qobuz(resp)
        if source == "tidal": return cls.from_tidal(resp)
        if source == "soundcloud": return cls.from_soundcloud(resp)
        if source == "deezer": return cls.from_deezer(resp)
        raise Exception("Invalid source")

    @classmethod
    def from_track_resp(cls, resp: dict, source: str) -> AlbumMetadata | None:
        if not source: raise Exception("Invalid source: None or empty")
        source = source.strip().lower()
        if source == "qobuz": return cls.from_qobuz(resp["album"])
        if source == "tidal": return cls.from_tidal_playlist_track_resp(resp)
        if source == "soundcloud": return cls.from_soundcloud(resp)
        if source == "deezer":
            if "tracks" not in resp["album"]: return cls.from_incomplete_deezer_track_resp(resp)
            return cls.from_deezer(resp["album"])
        raise Exception(f"Invalid source: '{source}'")

    @classmethod
    def from_incomplete_deezer_track_resp(cls, resp: dict) -> AlbumMetadata:
        return cls.from_deezer(resp["album"])