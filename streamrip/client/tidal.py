import asyncio
import base64
import json
import logging
import random
import re
import time
from datetime import datetime
from json import JSONDecodeError

import os

import aiohttp
import click
from aiohttp import TCPConnector, CookieJar, ClientSession, ClientTimeout

from ..config import Config
from ..exceptions import NonStreamableError
from .client import Client
from .downloadable import TidalDownloadable, TidalVideoDownloadable

logger = logging.getLogger("streamrip")

API_BASE = "https://api.tidal.com/v1"
VIDEO_BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

# Tidal app credentials.
# To use your own credentials set TIDAL_CLIENT_ID and TIDAL_CLIENT_SECRET:
#   export TIDAL_CLIENT_ID=your_id
#   export TIDAL_CLIENT_SECRET=your_secret
# If not set, bundled defaults are used (same approach as tiddl).
_BUNDLED_B64 = "NE4zbjZRMXg5NUxMNUs3cDtvS09YZkpXMzcxY1g2eGFaMFB5aGdHTkJkTkxsQlpkNEFLS1lvdWdNamlrPQ=="


def _get_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env vars or bundled defaults.

    Mirrors tiddl's ``get_auth_credentials()`` pattern: env vars take priority;
    bundled defaults (base64-encoded) are used as a fallback so the tool works
    out of the box without any configuration.
    """
    env_id = os.environ.get("TIDAL_CLIENT_ID")
    env_secret = os.environ.get("TIDAL_CLIENT_SECRET")
    if env_id and env_secret:
        return env_id, env_secret
    logger.debug(
        "TIDAL_CLIENT_ID / TIDAL_CLIENT_SECRET not set — using bundled default "
        "credentials. These may be revoked at any time. "
        "Set the env vars to use your own Tidal app credentials."
    )
    decoded = base64.b64decode(_BUNDLED_B64).decode()
    bundled_id, bundled_secret = decoded.split(";", 1)
    return bundled_id, bundled_secret


CLIENT_ID, CLIENT_SECRET = _get_client_credentials()
AUTH = aiohttp.BasicAuth(login=CLIENT_ID, password=CLIENT_SECRET)

STREAM_URL_REGEX = re.compile(
    r"#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS=\"(?!jpeg)[^\"]+\",RESOLUTION=\d+x\d+\n(.+)"
)

QUALITY_MAP = {
    0: "LOW", 1: "HIGH", 2: "LOSSLESS", 3: "HI_RES",
}

QUALITY_PRIORITY = [3, 2, 1, 0]

# Dedicated token file — separate from config.toml, with restricted permissions
_TOKEN_FILE = os.path.join(click.get_app_dir("streamrip"), "tidal_token.json")

# Refresh threshold: refresh when less than 1 hour remains (like tiddl)
_REFRESH_THRESHOLD = 3600


class TidalTokenStore:
    """Persists Tidal tokens to a dedicated JSON file with restricted permissions.

    Keeps tokens out of config.toml so they are not accidentally committed or
    shared, and sets chmod 0o600 so only the current user can read the file.
    """

    def __init__(self, path: str = _TOKEN_FILE):
        self.path = path

    def load(self) -> dict | None:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save(self, access_token: str, refresh_token: str, token_expiry: float,
             user_id: str, country_code: str) -> None:
        data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": token_expiry,
            "user_id": user_id,
            "country_code": country_code,
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass  # Windows has a different permission model; best-effort only


class TidalClient(Client):
    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.logged_in = False
        self.global_config = config
        self.config = config.session.tidal
        
        # --- CONFIGURACIÓN DE SEGURIDAD ---
        rpm = config.session.downloads.requests_per_minute
        max_conn = config.session.downloads.max_connections
        
        # Safe values if not defined or too high
        safe_rpm = rpm if rpm > 0 else 60
        # Allow up to 12 concurrent connections if configured, otherwise default to 2
        safe_conn = max_conn if (0 < max_conn <= 12) else 2

        self.semaphore = asyncio.Semaphore(safe_conn)
        self._rate_lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._min_interval = 60.0 / safe_rpm  # e.g. 1.0s at 60 RPM
        self._rate_limit_delay: float = 0.0  # Adaptive: grows on 429, shrinks on success
        # --------------------------------------------

        self.auth_lock = asyncio.Lock()
        self._flac_downloaded = set()
        self.token_store = TidalTokenStore()

    async def login(self):
        jar = CookieJar(unsafe=True)
        connector = TCPConnector(limit=10, force_close=True, enable_cleanup_closed=True)
        timeout = ClientTimeout(total=3600, connect=30, sock_read=60)

        self.session = ClientSession(
            connector=connector,
            cookie_jar=jar,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )

        if not self.global_config.session.downloads.verify_ssl:
            self.session.connector._ssl = False

        c = self.config

        # Load tokens from dedicated file if available; fall back to config.toml
        stored = self.token_store.load()
        if stored:
            c.access_token  = stored.get("access_token", c.access_token)
            c.refresh_token = stored.get("refresh_token", c.refresh_token)
            c.token_expiry  = stored.get("token_expiry", c.token_expiry)
            c.user_id       = stored.get("user_id", c.user_id)
            c.country_code  = stored.get("country_code", c.country_code)

        self.token_expiry  = float(c.token_expiry) if c.token_expiry else 0
        self.refresh_token = c.refresh_token

        if self.token_expiry - time.time() < _REFRESH_THRESHOLD:
            if self.refresh_token:
                await self._refresh_access_token()
        else:
            if c.access_token:
                await self._login_by_access_token(c.access_token, c.user_id)
        self.logged_in = True

    async def get_artist_albums_stream(self, artist_id: str):
        queue = asyncio.Queue()
        sentinel = object()

        endpoints = [
            (f"artists/{artist_id}/albums", {'limit': 100, 'includeContributors': 'true'}),
            (f"artists/{artist_id}/albums", {"filter": "EPSANDSINGLES", 'limit': 100})
        ]

        async def producer(ep, params):
            try:
                async for batch in self._fetch_pages_generator(ep, params):
                    if batch: await queue.put(batch)
            except Exception as e:
                logger.error(f"Stream producer error ({ep}): {e}")
            finally:
                await queue.put(sentinel)

        for ep, params in endpoints:
            asyncio.create_task(producer(ep, params))

        active_producers = len(endpoints)
        while active_producers > 0:
            item = await queue.get()
            if item is sentinel:
                active_producers -= 1
            else:
                yield item

    async def _fetch_pages_generator(self, endpoint: str, base_params: dict):
        p = base_params.copy()
        p['offset'] = 0
        try:
            resp = await self._api_request(endpoint, params=p, base=API_BASE)
        except Exception:
            return

        total = resp.get("totalNumberOfItems", 0)
        items = resp.get("items", [])
        yield items

        if total <= 100: return

        for offset in range(100, total, 100):
            p = base_params.copy()
            p['offset'] = offset
            try:
                page_resp = await self._api_request(endpoint, params=p, base=API_BASE)
                if "items" in page_resp: yield page_resp["items"]
            except Exception:
                continue

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        url = f"{media_type}s/{item_id}"
        if media_type == "mix":
            url = f"mixes/{item_id}"
        item = await self._api_request(url, base=API_BASE)

        if "releaseDate" in item: item["date"] = item["releaseDate"]
        elif "streamStartDate" in item: item["date"] = item["streamStartDate"]
        elif "dateAdded" in item: item["date"] = item["dateAdded"]

        if media_type == "track":
            if "title" not in item: item["title"] = f"Track {item.get('trackNumber', '?')}"
            if "artists" not in item: item["artists"] = [{"name": "Unknown Artist"}]
            if "lyrics" not in item: item["lyrics"] = ""

        elif media_type in ("playlist", "album", "mix"):
            endpoint = f"{url}/items"
            params = {'limit': 100}
            if media_type in ("album", "playlist"): params['includeContributors'] = 'true'

            fetched_items = await self._turbo_fetch_list(endpoint, params)
            
            clean = []
            for t in fetched_items:
                target = t.get("item", t)
                target["lyrics"] = ""
                if "title" not in target: target["title"] = f"Track {target.get('trackNumber', '?')}"
                if "artists" not in target: target["artists"] = [{"name": "Unknown Artist"}]
                clean.append(target)
            item["tracks"] = clean

        elif media_type == "artist":
            all_albums = []
            async for batch in self.get_artist_albums_stream(item_id):
                all_albums.extend(batch)
            item["albums"] = all_albums

        return item

    async def _turbo_fetch_list(self, endpoint: str, base_params: dict) -> list:
        params = base_params.copy()
        params['offset'] = 0
        try:
            resp = await self._api_request(endpoint, params=params, base=API_BASE)
        except:
            if 'includeContributors' in params:
                del params['includeContributors']
                if 'includeContributors' in base_params: del base_params['includeContributors']
                resp = await self._api_request(endpoint, params=params, base=API_BASE)
            else:
                return []

        total = resp.get("totalNumberOfItems", 0)
        items = resp.get("items", [])
        if total <= 100: return items

        tasks = []
        for offset in range(100, total, 100):
            p = base_params.copy()
            p['offset'] = offset
            tasks.append(self._api_request(endpoint, params=p, base=API_BASE))

        if tasks:
            pages = await asyncio.gather(*tasks, return_exceptions=True)
            for page in pages:
                if isinstance(page, dict) and "items" in page: items.extend(page["items"])
        return items

    async def search(self, media_type: str, query: str, limit: int = 100) -> list[dict]:
        params = {"query": query, "limit": limit, "includeContributors": "true"}
        resp = await self._api_request(f"search/{media_type}s", params=params, base=API_BASE)
        if "items" in resp:
            for i in resp["items"]:
                if "releaseDate" in i: i["date"] = i["releaseDate"]
        if len(resp["items"]) > 1: return [resp]
        return []

    async def get_downloadable(self, track_id: str, quality: int = 3, media_type: str = "track"):
        if media_type == "video":
            return await self._get_video_downloadable(track_id, quality)

        tid_str = str(track_id)
        if tid_str in self._flac_downloaded:
            raise NonStreamableError(f"Track {track_id} already downloaded")

        qualities = [q for q in QUALITY_PRIORITY if q <= quality]
        if not qualities: qualities = QUALITY_PRIORITY
        
        last_err = None
        
        # Phase 1: Try FLAC
        for q in qualities:
            try:
                q_val = QUALITY_MAP.get(q, "HIGH")
                params = {"audioquality": q_val, "playbackmode": "STREAM", "assetpresentation": "FULL", "prefetch": "false"}
                try:
                    resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall/v4", params, base=API_BASE)
                except:
                    resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall", params, base=API_BASE)

                if "manifest" in resp:
                    manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
                else:
                    manifest = resp
                
                url = manifest.get("urls", [])[0] if "urls" in manifest else ""
                if not url: continue
                
                codec = manifest.get("codecs", "flac")
                if not codec or not isinstance(codec, str): continue
                
                codecs_list = [c.strip().lower() for c in codec.split(",")]
                if "flac" in codecs_list:
                    enc = manifest.get("keyId")
                    if manifest.get("encryptionType") == "NONE": enc = None
                    self._flac_downloaded.add(tid_str)
                    return TidalDownloadable(self.session, url=url, codec="flac", encryption_key=enc, restrictions=manifest.get("restrictions"))
                
            except NonStreamableError: raise
            except Exception as e:
                last_err = e
                continue
        
        # Phase 2: Try M4A/AAC
        for q in qualities:
            try:
                q_val = QUALITY_MAP.get(q, "HIGH")
                params = {"audioquality": q_val, "playbackmode": "STREAM", "assetpresentation": "FULL", "prefetch": "false"}
                try:
                    resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall/v4", params, base=API_BASE)
                except:
                    resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall", params, base=API_BASE)

                if "manifest" in resp:
                    manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
                else:
                    manifest = resp
                
                url = manifest.get("urls", [])[0] if "urls" in manifest else ""
                if not url: continue
                
                codec = manifest.get("codecs", "flac")
                if not codec or not isinstance(codec, str): continue
                
                codecs_list = [c.strip().lower() for c in codec.split(",")]
                if "m4a" in codecs_list or "aac" in codecs_list:
                    enc = manifest.get("keyId")
                    if manifest.get("encryptionType") == "NONE": enc = None
                    self._flac_downloaded.add(tid_str)
                    return TidalDownloadable(self.session, url=url, codec="m4a", encryption_key=enc, restrictions=manifest.get("restrictions"))
                
            except NonStreamableError: raise
            except Exception as e:
                last_err = e
                continue
        
        raise NonStreamableError(f"No FLAC or M4A available: {last_err}")

    async def _get_video_downloadable(self, video_id: str, quality: int):
        q_map = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "HIGH"}
        q_val = q_map.get(quality, "HIGH")

        params = {
            "videoquality": q_val,
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
            "prefetch": "false"
        }
        
        try:
            resp = await self._api_request(f"videos/{video_id}/playbackinfopostpaywall/v4", params, base=API_BASE)
        except:
            resp = await self._api_request(f"videos/{video_id}/playbackinfopostpaywall", params, base=API_BASE)

        if "manifest" in resp:
            manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        else:
            manifest = resp

        url = manifest.get("urls", [])[0] if "urls" in manifest else ""
        if not url:
            raise NonStreamableError(f"No video URL found for {video_id}")

        return TidalVideoDownloadable(self.session, url)

    async def _login_by_access_token(self, token: str, user_id: str):
        headers = {"authorization": f"Bearer {token}"}
        async with self.session.get(f"{API_BASE}/sessions", headers=headers) as _resp:
            resp = await _resp.json()
        if resp.get("status", 200) != 200:
            raise Exception(f"Login failed {resp}")
        c = self.config
        c.user_id = resp["userId"]
        c.country_code = resp["countryCode"]
        c.access_token = token
        self._update_authorization_from_config()
        self._persist_token()

    def _update_authorization_from_config(self):
        self.session.headers.update({"authorization": f"Bearer {self.config.access_token}"})

    def _persist_token(self) -> None:
        """Write current tokens to the dedicated token file immediately."""
        c = self.config
        try:
            self.token_store.save(
                access_token=c.access_token or "",
                refresh_token=c.refresh_token or "",
                token_expiry=float(c.token_expiry) if c.token_expiry else 0,
                user_id=str(c.user_id or ""),
                country_code=str(c.country_code or ""),
            )
        except Exception as e:
            logger.warning(f"Could not persist Tidal token: {e}")

    async def _refresh_access_token(self):
        async with self.auth_lock:
            # Skip if token was already refreshed by a concurrent request
            if self.config.token_expiry and (float(self.config.token_expiry) - time.time() > _REFRESH_THRESHOLD): return
            logger.info("Refreshing Tidal token...")
            data = {"client_id": CLIENT_ID, "refresh_token": self.refresh_token, "grant_type": "refresh_token", "scope": "r_usr+w_usr+w_sub"}
            try:
                # Do NOT use the semaphore here: if all connections are waiting for
                # this refresh to complete, using the semaphore would deadlock.
                async with self.session.post(f"{AUTH_URL}/token", data=data, auth=AUTH) as resp:
                    resp_data = await resp.json()

                if resp_data.get("status", 200) != 200:
                    raise Exception(f"Refresh failed: {resp_data}")

                c = self.config
                c.access_token = resp_data["access_token"]
                c.token_expiry = resp_data["expires_in"] + time.time()
                if resp_data.get("refresh_token"):
                    c.refresh_token = resp_data["refresh_token"]
                    self.refresh_token = c.refresh_token
                self._update_authorization_from_config()
                self._persist_token()
                logger.info("Token refreshed.")
            except Exception as e:
                logger.error(f"Refresh failed: {e}")
                raise e

    async def get_lyrics(self, track_id: str) -> str | None:
        """Fetch timed lyrics for a track and return them in LRC format.

        Calls the Tidal ``/v1/tracks/{id}/lyrics`` endpoint.  If the response
        contains timed subtitle data (``subtitles`` field) it is converted to
        standard LRC format.  Plain-text lyrics (``lyrics`` field) are returned
        as-is when no timed data is available.  Returns ``None`` if no lyrics
        are found or the endpoint returns an error.
        """
        try:
            resp = await self._api_request(f"tracks/{track_id}/lyrics", base=API_BASE)
        except Exception as e:
            logger.debug("Could not fetch Tidal lyrics for %s: %s", track_id, e)
            return None

        subtitles_json = resp.get("subtitles")
        if subtitles_json:
            return self._subtitles_to_lrc(subtitles_json)

        # Fall back to plain text (no timestamps)
        plain = resp.get("lyrics", "")
        return plain.strip() or None

    @staticmethod
    def _subtitles_to_lrc(subtitles_json: str | list) -> str:
        """Convert Tidal's subtitle JSON string (or pre-parsed list) to LRC format.

        The API may return ``subtitles`` as a JSON-encoded string **or** as an
        already-parsed list.  Both forms are accepted so that ``get_lyrics``
        always returns a ``str`` regardless of how the API serialises the data.

        Each element must have ``startTimeMs`` (ms as str/int) and ``words``.

        Example input::

            [{"startTimeMs": "5530", "words": "I'm in love with the world"}, ...]

        Example output::

            [00:05.53]I'm in love with the world
        """
        if isinstance(subtitles_json, list):
            lines = subtitles_json
        elif isinstance(subtitles_json, str):
            try:
                lines = json.loads(subtitles_json)
            except (json.JSONDecodeError, TypeError):
                # Not valid JSON — return the raw string (better than nothing)
                return subtitles_json
        else:
            return ""

        if not isinstance(lines, list):
            # Unexpected shape — convert to string as a last resort
            return str(lines)

        lrc_lines = []
        for line in lines:
            try:
                start_ms = int(line.get("startTimeMs", 0))
            except (TypeError, ValueError):
                start_ms = 0
            words = line.get("words", "")
            # Pure integer arithmetic avoids floating-point rounding artifacts
            # (e.g. 59999 ms must not produce [MM:60.00] due to float drift)
            minutes = start_ms // 60000
            remaining_ms = start_ms % 60000
            seconds = remaining_ms // 1000
            centiseconds = (remaining_ms % 1000) // 10
            lrc_lines.append(f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]{words}")
        return "\n".join(lrc_lines)

    async def _api_post(self, url, data, auth: aiohttp.BasicAuth | None = None) -> dict:
        async with self.semaphore:
            async with self.session.post(url, data=data, auth=auth) as resp: return await resp.json()

    async def _api_request(self, path: str, params=None, base: str = API_BASE, retries: int = 10) -> dict:
        if params is None: params = {}
        if "countryCode" not in params: params["countryCode"] = self.config.country_code
        if "limit" not in params: params["limit"] = 100

        for attempt in range(retries + 1):
            # Adaptive delay from previous 429s
            if self._rate_limit_delay > 0:
                await asyncio.sleep(self._rate_limit_delay)

            # Fixed interval + small jitter (global, no burst)
            async with self._rate_lock:
                now = asyncio.get_event_loop().time()
                elapsed = now - self._last_request_time
                wait = self._min_interval - elapsed + random.uniform(0, 0.3)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_request_time = asyncio.get_event_loop().time()

            async with self.semaphore:

                url = path if path.startswith("http") else f"{base}/{path}"
                try:
                    async with self.session.get(url, params=params, timeout=ClientTimeout(total=30)) as resp:
                        if resp.status == 429:
                            self._rate_limit_delay = min(5.0, self._rate_limit_delay + 1.0)
                            wait = int(resp.headers.get("Retry-After", 10)) + random.randint(5, 10)
                            logger.debug(f"Rate Limit hit. Backing off {wait}s... (adaptive_delay={self._rate_limit_delay:.1f}s)")
                            await asyncio.sleep(wait)
                            continue
                        if resp.status == 401:
                            if attempt < 2:
                                await self._refresh_access_token()
                                continue
                            else:
                                raise Exception("Unauthorized (401)")
                        if resp.status == 404:
                            raise NonStreamableError("Not Found")
                        resp.raise_for_status()
                        self._rate_limit_delay = max(0.0, self._rate_limit_delay - 0.1)
                        try:
                            return await resp.json()
                        except:
                            return json.loads(await resp.text())
                except (aiohttp.ClientOSError, asyncio.TimeoutError):
                    await asyncio.sleep(2)
                    continue
                except Exception as e:
                    if "401" in str(e) and attempt < 2:
                        await self._refresh_access_token()
                        continue
                    if attempt == retries:
                        raise e
        
        raise Exception("Connection failed.")