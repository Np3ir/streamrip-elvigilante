import asyncio
import base64
import json
import logging
import random
import re
import time
from datetime import datetime
from json import JSONDecodeError

import aiohttp
from aiohttp import TCPConnector, CookieJar, ClientSession, ClientTimeout

from ..config import Config
from ..exceptions import NonStreamableError
from .client import Client
from .downloadable import TidalDownloadable, TidalVideoDownloadable

logger = logging.getLogger("streamrip")

API_BASE = "https://api.tidal.com/v1"
VIDEO_BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = "4N3n6Q1x95LL5K7p"
CLIENT_SECRET = "oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik="

AUTH = aiohttp.BasicAuth(login=CLIENT_ID, password=CLIENT_SECRET)

STREAM_URL_REGEX = re.compile(
    r"#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS=\"(?!jpeg)[^\"]+\",RESOLUTION=\d+x\d+\n(.+)"
)

QUALITY_MAP = {
    0: "LOW", 1: "HIGH", 2: "LOSSLESS", 3: "HI_RES",
}

QUALITY_PRIORITY = [3, 2, 1, 0]


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

        self.rate_limiter = self.get_rate_limiter(safe_rpm)
        self.semaphore = asyncio.Semaphore(safe_conn)
        # --------------------------------------------
        
        self.auth_lock = asyncio.Lock()
        self._flac_downloaded = set()

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
        self.token_expiry = float(c.token_expiry) if c.token_expiry else 0
        self.refresh_token = c.refresh_token

        if self.token_expiry - time.time() < 86400:
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
            if media_type == "album": params['includeContributors'] = 'true'

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
        async with self.session.get(f"{API_BASE}/sessions", headers=headers) as _resp: resp = await _resp.json()
        if resp.get("status", 200) != 200: raise Exception(f"Login failed {resp}")
        c = self.config; c.user_id = resp["userId"]; c.country_code = resp["countryCode"]; c.access_token = token
        self._update_authorization_from_config()

    def _update_authorization_from_config(self):
        self.session.headers.update({"authorization": f"Bearer {self.config.access_token}"})

    async def _refresh_access_token(self):
        async with self.auth_lock:
            if self.config.token_expiry and (float(self.config.token_expiry) - time.time() > 600): return
            logger.info("Refreshing Tidal token...")
            data = {"client_id": CLIENT_ID, "refresh_token": self.refresh_token, "grant_type": "refresh_token", "scope": "r_usr+w_usr+w_sub"}
            try:
                # --- FIX CRÍTICO: NO USAR SEMÁFORO AQUÍ ---
                # Usamos self.session.post directamente.
                # _api_post usa el semáforo, y si todas las conexiones están ocupadas esperando 
                # que este token se refresque, se produce un bloqueo mutuo (deadlock).
                async with self.session.post(f"{AUTH_URL}/token", data=data, auth=AUTH) as resp:
                    resp_data = await resp.json()
                
                if resp_data.get("status", 200) != 200: 
                    raise Exception(f"Refresh failed: {resp_data}")
                
                c = self.config
                c.access_token = resp_data["access_token"]
                c.token_expiry = resp_data["expires_in"] + time.time()
                self._update_authorization_from_config()
                logger.info("Token refreshed.")
            except Exception as e:
                logger.error(f"Refresh failed: {e}"); raise e

    async def _api_post(self, url, data, auth: aiohttp.BasicAuth | None = None) -> dict:
        async with self.semaphore:
            async with self.session.post(url, data=data, auth=auth) as resp: return await resp.json()

    async def _api_request(self, path: str, params=None, base: str = API_BASE, retries: int = 10) -> dict:
        if params is None: params = {}
        if "countryCode" not in params: params["countryCode"] = self.config.country_code
        if "limit" not in params: params["limit"] = 100

        for attempt in range(retries + 1):
            # Jitter outside the semaphore to avoid blocking
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            async with self.semaphore:
                # Rate limiter
                if self.rate_limiter:
                    await self.rate_limiter.acquire()

                url = path if path.startswith("http") else f"{base}/{path}"
                try:
                    async with self.session.get(url, params=params, timeout=ClientTimeout(total=30)) as resp:
                        if resp.status == 429:
                            wait = int(resp.headers.get("Retry-After", 10)) + random.randint(5, 10)
                            logger.warning(f"Rate Limit hit. Backing off {wait}s...")
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