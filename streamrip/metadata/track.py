from __future__ import annotations

import logging
import re
import os
from dataclasses import dataclass
from typing import Optional

from .album import AlbumMetadata
from .util import DEFAULT_ARTIST_SEPARATOR, safe_get, typed
from ..filepath_utils import truncate_filepath_to_max, clean_filename, clean_track_title

logger = logging.getLogger("streamrip")


class _Explicit:
    """Supports tidmon-style format specs: {item.explicit:shortparens}."""
    def __init__(self, val: bool):
        self.val = bool(val)

    def __format__(self, fmt: str) -> str:
        if not self.val:
            return ""
        if "shortparens" in fmt:
            return " (explicit)"
        if "parens" in fmt:
            return " (Explicit)"
        if "upper" in fmt:
            return "EXPLICIT" if "long" in fmt else "E"
        return "explicit" if "long" in fmt else "E"

    def __str__(self) -> str:
        return " (explicit)" if self.val else ""

    def __bool__(self) -> bool:
        return self.val


class _ItemProxy:
    """Proxy so tidmon-style {item.field} templates work inside streamrip."""
    __slots__ = (
        "id", "number", "volume", "title", "safe_title", "title_version",
        "artist", "safe_artist", "artists", "safe_artists", "features",
        "artists_with_features", "isrc", "version", "copyright", "bpm",
        "quality", "explicit", "genre",
    )

    def __init__(self, meta: "TrackMetadata") -> None:
        ver = meta.version or ""
        raw_title = meta.title or ""

        # Strip version suffix if it was already embedded in title
        # so {item.title} is always the clean title without version — matching tiddl.
        if ver and raw_title.endswith(f" ({ver})"):
            clean_title = raw_title[: -len(f" ({ver})")]
        else:
            clean_title = raw_title

        # Remove (feat. X) / (with X) from title when X is already captured
        # in the artist string — matching tiddl's clean_track_title behaviour.
        clean_title = clean_track_title(clean_title, meta.artist or "")

        all_artists   = meta.artist or ""
        main_only     = meta.main_artists or all_artists
        featured_only = meta.featured_artists or ""

        self.id          = meta.info.id
        self.number      = meta.tracknumber
        self.volume      = meta.discnumber
        self.title       = clean_title
        self.safe_title  = clean_filename(clean_title)
        self.version     = ver
        # title_version = "Title (Version)" when version exists, else just title.
        self.title_version = f"{clean_title} ({ver})" if ver else clean_title
        self.artist      = all_artists
        self.safe_artist = clean_filename(all_artists)
        # {item.artists} = MAIN artists only (matching tiddl)
        self.artists     = main_only
        self.safe_artists = clean_filename(main_only)
        # {item.features} = FEATURED artists only (matching tiddl)
        self.features    = featured_only
        # {item.artists_with_features} = all artists (MAIN + FEATURED)
        self.artists_with_features = all_artists
        self.isrc        = meta.isrc or ""
        self.copyright   = ""
        self.bpm         = 0
        self.quality     = ""
        self.explicit    = _Explicit(meta.info.explicit)
        # {item.genre} — from album metadata when available
        try:
            self.genre = meta.album.get_genres()
        except Exception:
            self.genre = ""


@dataclass(slots=True)
class TrackInfo:
    id: str
    quality: int
    bit_depth: Optional[int] = None
    explicit: bool = False
    sampling_rate: Optional[int | float] = None
    work: Optional[str] = None


@dataclass(slots=True)
class TrackMetadata:
    info: TrackInfo
    title: str
    album: AlbumMetadata
    artist: str          # All artists joined (MAIN + FEATURED) — used for audio tags
    tracknumber: int
    discnumber: int
    composer: str | None
    isrc: str | None = None
    lyrics: str | None = ""
    version: str | None = None
    # Tidal MAIN-only and FEATURED-only artist strings for {item.artists}/{item.features}
    main_artists: str | None = None
    featured_artists: str | None = None

    def format_track_path(self, formatter: str) -> str:
        none_str = "Unknown"
        title_clean = self.title
        info: dict = {
            "artist": self.artist or none_str,
            "title": title_clean or none_str,
            "albumartist": getattr(self.album, "albumartist", none_str),
            "composer": self.composer or none_str,
            "albumcomposer": getattr(self.album, "albumcomposer", none_str),
            "tracknumber": self.tracknumber,
            "explicit": " (explicit)" if self.info.explicit else "",
            "item": _ItemProxy(self),
        }

        # Use imported clean_filename (respects accents, swaps : for ：)
        formatted_filename = clean_filename(formatter.format(**info))

        if not formatted_filename:
            formatted_filename = "Unknown_Track"

        try:
            base_folder = self.album.folder
        except AttributeError:
            base_folder = ""

        full_path = os.path.join(base_folder, formatted_filename)

        # truncate_filepath_to_max uses UTF-8 byte counting (240 bytes default)
        # matching tiddl's behaviour — no separate char-based limit needed.
        logger.debug(f"[DEBUG] Final track path: {full_path} (bytes={len(full_path.encode('utf-8'))})")
        return truncate_filepath_to_max(full_path)

    @classmethod
    def from_qobuz(cls, album: AlbumMetadata, resp: dict, artist_separator: str) -> TrackMetadata | None:
        def split_feat_artists(name: str) -> list[str]:
            separators = [" feat. ", " featuring ", " feat ", " ft. ", " ft "]
            for sep in separators:
                if sep in name.lower():
                    return [p.strip() for p in re.split(sep, name, flags=re.IGNORECASE)]
            return [name.strip()]

        main_artists = []
        featured_artists = []
        album_artists = resp.get("album", {}).get("artists", [])
        for artist in album_artists:
            roles = artist.get("roles", [])
            name = artist.get("name", "")
            for part in split_feat_artists(name):
                if "main-artist" in roles and part not in main_artists:
                    main_artists.append(part)
                elif "featured-artist" in roles and part not in featured_artists:
                    featured_artists.append(part)

        performers_str = resp.get("performers", "")
        if isinstance(performers_str, str):
            lines = [line.strip() for line in performers_str.split(" - ") if "," in line]
            for line in lines:
                name, roles = line.split(",", 1)
                name = name.strip()
                roles = roles.lower()
                valid_roles = ["mainartist"]
                if any(role.strip() in roles for role in valid_roles):
                    for part in split_feat_artists(name):
                        if part and part not in main_artists and part not in featured_artists:
                            featured_artists.append(part)

        performer_raw = resp.get("performer")
        if isinstance(performer_raw, dict):
            performer_name = performer_raw.get("name", "")
            if performer_name:
                for part in split_feat_artists(performer_name):
                    if part and part not in main_artists and part not in featured_artists:
                        featured_artists.append(part)

        title_and_version = f"{resp.get('title', '')} {resp.get('version', '')}".lower()
        filtered_featured_artists = []
        for artist in featured_artists:
            if artist.lower() not in title_and_version:
                filtered_featured_artists.append(artist)

        all_artists_raw = main_artists + filtered_featured_artists
        seen = set()
        all_artists = []
        for a in all_artists_raw:
            norm = a.lower().strip()
            if norm not in seen:
                all_artists.append(a.strip())
                seen.add(norm)
        artist_string = artist_separator.join(all_artists) if all_artists else "Unknown"

        title = typed(resp["title"].strip(), str)
        for artist in all_artists:
            pattern = rf"\s*[\(\[]?(with|feat\.?|ft\.?|featuring)\s+{re.escape(artist)}[\)\]]?"
            title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s{2,}", " ", title).strip()

        isrc = typed(resp["isrc"], str)
        streamable = typed(resp.get("streamable", False), bool)
        if not streamable:
            return None

        for artist in all_artists:
            variants = [
                f"(with {artist})", f"(feat. {artist})", f"(featuring {artist})",
                f"[with {artist}]", f"[feat. {artist}]", f"[featuring {artist}]"
            ]
            for v in variants:
                if v.lower() in title.lower():
                    title = re.sub(re.escape(v), "", title, flags=re.IGNORECASE).strip()
                    title = re.sub(r"\s{2,}", " ", title).strip()

        version = typed(resp.get("version"), str | None)
        work = typed(resp.get("work"), str | None)
        title_lower = title.lower()
        version_lower = version.lower() if version else ""
        explicit = (
                resp.get("parental_warning") == 1
                or "explicit" in version_lower
                or "explicit" in title_lower
                or "explicit" in resp.get("subtitle", "").lower()
        )

        if version:
            version_clean = version.lower().strip()
            if version_clean == "album version":
                title = title.replace(" (Album Version)", "").replace("(Album Version)", "").strip()
            elif version_clean not in title.lower():
                title = f"{title} ({version})"

        if work and work.lower() not in title.lower():
            title = f"{work}: {title}"

        composer = typed(resp.get("composer", {}).get("name"), str | None)
        tracknumber = typed(resp.get("track_number", 1), int)
        discnumber = typed(resp.get("media_number", 1), int)

        track_id = str(resp["id"])
        bit_depth = typed(resp.get("maximum_bit_depth"), int | None)
        sampling_rate = typed(resp.get("maximum_sampling_rate"), int | float | None)

        info = TrackInfo(
            id=track_id,
            quality=album.info.quality,
            bit_depth=bit_depth,
            explicit=explicit,
            sampling_rate=sampling_rate,
            work=work,
        )

        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist_string,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
            isrc=isrc,
        )

    @classmethod
    def from_tidal(cls, album: AlbumMetadata, resp: dict, artist_separator: str) -> TrackMetadata | None:
        title = typed(resp.get("title", "Unknown Title"), str)
        # Separate MAIN vs FEATURED artists, sort each group alphabetically — matching tiddl.
        artists_raw = resp.get("artists", [])
        main_artists = sorted(
            [a["name"] for a in artists_raw if a.get("type") == "MAIN" or not a.get("type")],
        )
        featured_artists = sorted(
            [a["name"] for a in artists_raw if a.get("type") == "FEATURED"],
        )
        artist = artist_separator.join(main_artists + featured_artists) or "Unknown Artist"
        composer_raw = resp.get("composer")
        composer = typed(composer_raw.get("name") if isinstance(composer_raw, dict) else composer_raw, str | None)
        tracknumber = typed(resp.get("trackNumber", 1), int)
        discnumber = typed(resp.get("volumeNumber", 1), int)
        isrc = typed(resp.get("isrc", ""), str | None)
        version = (resp.get("version") or "").strip() or None
        if version and version.lower() not in title.lower():
            # Heuristic: musician credit lists like "A, B, C & D" have 2+ commas.
            # Skip appending those to the title; they are not real version tags.
            if version.count(",") < 2:
                title = f"{title} ({version})"
            else:
                version = None  # Treat as non-version; don't pollute title

        # Fix: Handle lyrics safely (sometimes it is a string, sometimes a dict)
        lyrics_raw = resp.get("lyrics")
        if isinstance(lyrics_raw, dict):
            lyrics = lyrics_raw.get("text", "")
        elif isinstance(lyrics_raw, str):
            lyrics = lyrics_raw
        else:
            lyrics = ""
        track_id = str(resp.get("id", ""))
        explicit = resp.get("explicit", False)
        quality_map = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES": 3}
        tidal_quality = resp.get("audioQuality", "LOW")
        quality = quality_map.get(tidal_quality, 0)
        sampling_rate = 44100 if quality >= 2 else None
        bit_depth = 24 if tidal_quality == "HI_RES" else (16 if quality >= 2 else None)
        info = TrackInfo(
            id=track_id,
            quality=quality,
            bit_depth=bit_depth,
            explicit=explicit,
            sampling_rate=sampling_rate,
            work=None,
        )
        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
            isrc=isrc,
            lyrics=lyrics,
            version=version,
            main_artists=artist_separator.join(main_artists) or None,
            featured_artists=artist_separator.join(featured_artists) or None,
        )

    @classmethod
    def from_deezer(cls, album: AlbumMetadata, resp: dict, artist_separator: str) -> TrackMetadata | None:
        title = typed(resp.get("title", "Unknown Title"), str)
        version = (resp.get("title_version") or "").strip() or None
        if version and version.lower() not in title.lower():
            title = f"{title} ({version})"
        artist_obj = resp.get("artist", {})
        # Use contributors list when available (may contain multiple artists);
        # fall back to the single artist field. artist_separator joins multiple names.
        contribs = [
            c["name"]
            for c in resp.get("contributors", [])
            if isinstance(c.get("name"), str) and c["name"]
        ]
        if contribs:
            artist = artist_separator.join(contribs)
        else:
            artist = artist_obj.get("name", "Unknown Artist")
        tracknumber = typed(resp.get("track_position", 1), int)
        discnumber = typed(resp.get("disk_number", 1), int)
        isrc = typed(resp.get("isrc"), str | None)
        explicit = resp.get("explicit_lyrics", False)
        composers = [
            c["name"]
            for c in resp.get("contributors", [])
            if c.get("role") == "Composer" and isinstance(c.get("name"), str) and c["name"]
        ]
        composer = ", ".join(composers) if composers else None
        track_id = str(resp.get("id", ""))
        quality = 2
        bit_depth = 16
        sampling_rate = 44100
        info = TrackInfo(
            id=track_id,
            quality=quality,
            bit_depth=bit_depth,
            explicit=explicit,
            sampling_rate=sampling_rate,
            work=None,
        )
        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
            isrc=isrc,
            lyrics="",
            version=version,
        )

    @classmethod
    def from_soundcloud(cls, album: AlbumMetadata, resp: dict) -> TrackMetadata | None:
        raise NotImplementedError("SoundCloud track support not yet implemented")

    @classmethod
    def from_resp(cls, album_or_source, source_or_resp, maybe_resp=None, artist_separator: str = DEFAULT_ARTIST_SEPARATOR) -> TrackMetadata | None:
        if maybe_resp is not None:
            album = album_or_source
            source = source_or_resp
            resp = maybe_resp
        elif isinstance(source_or_resp, dict) and isinstance(album_or_source, str):
            album = AlbumMetadata.dummy()
            source = album_or_source
            resp = source_or_resp
        else:
            logger.error(
                f"[from_resp] Invalid argument types: album_or_source={type(album_or_source)}, source_or_resp={type(source_or_resp)}")
            return None
        if not isinstance(resp, dict):
            logger.error(f"[from_resp] Invalid resp type: expected dict, got {type(resp)} - {resp}")
            return None
        logger.debug(f"[DEBUG] Parsing metadata from source: {source}")
        if source == "qobuz": return cls.from_qobuz(album, resp, artist_separator)
        if source == "tidal": return cls.from_tidal(album, resp, artist_separator)
        if source == "deezer": return cls.from_deezer(album, resp, artist_separator)
        if source == "soundcloud": return cls.from_soundcloud(album, resp)
        logger.error(f"[from_resp] Unknown source: {source}")
        return None
