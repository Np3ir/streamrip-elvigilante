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
from .downloadable import TidalDownloadable

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


class TidalClient(Client):
    """
    TidalClient 'Smart-Regulated' (Compatibility Fix).
    - Uses native get_rate_limiter(100) to satisfy streamrip internals (media.py).
    - Uses Semaphore(5) and logic for real traffic control.
    """

    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.logged_in = False
        self.global_config = config
        self.config = config.session.tidal

        # --- FIX: COMPATIBILIDAD NATIVA ---
        # Usamos el método original de la clase padre para crear el limitador.
        # Ponemos 100 (muy alto) para que no frene nada; el freno real
        # lo ponemos nosotros abajo con el Semaphore y la lógica 429.
        self.rate_limiter = self.get_rate_limiter(100)

        # Semáforo para controlar concurrencia real (5 descargas a la vez)
        self.semaphore = asyncio.Semaphore(5)

        # Candado para renovación de token
        self.auth_lock = asyncio.Lock()

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def login(self):
        jar = CookieJar(unsafe=True)
        # Connector robusto
        connector = TCPConnector(limit=10, force_close=True, enable_cleanup_closed=True)
        # Timeouts generosos
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
            (f"artists/{artist_id}/albums", {'limit': 100}),
            (f"artists/{artist_id}/albums", {"filter": "EPSANDSINGLES", 'limit': 100})
        ]

        async def producer(ep, params):
            try:
                async for batch in self._fetch_pages_generator(ep, params):
                    await queue.put(batch)
            except Exception as e:
                logger.error(f"Error in stream producer ({ep}): {e}")
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
        except Exception as e:
            logger.error(f"Error fetching page 0: {e}")
            return

        total = resp.get("totalNumberOfItems", 0)
        items = resp.get("items", [])
        yield items

        if total <= 100:
            return

        page_tasks = []
        for offset in range(100, total, 100):
            p = base_params.copy()
            p['offset'] = offset
            page_tasks.append(self._api_request(endpoint, params=p, base=API_BASE))

        if page_tasks:
            for completed_task in asyncio.as_completed(page_tasks):
                try:
                    page_resp = await completed_task
                    if "items" in page_resp:
                        yield page_resp["items"]
                except Exception as e:
                    logger.error(f"Error fetching offset page: {e}")

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        url = f"{media_type}s/{item_id}"
        item = await self._api_request(url, base=API_BASE)

        if "releaseDate" in item:
            item["date"] = item["releaseDate"]
        elif "streamStartDate" in item:
            item["date"] = item["streamStartDate"]
        elif "dateAdded" in item:
            item["date"] = item["dateAdded"]

        if media_type in ("playlist", "album"):
            endpoint = f"{url}/items"
            params = {'limit': 100}
            if media_type == "album": params['includeContributors'] = 'true'

            fetched_items = await self._turbo_fetch_list(endpoint, params)

            clean_tracks = []
            for t in fetched_items:
                target = t.get("item", t)
                target["lyrics"] = ""
                clean_tracks.append(target)
            item["tracks"] = clean_tracks

        elif media_type == "artist":
            item["albums"] = []

        elif media_type == "track":
            item["lyrics"] = ""

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

        total_items = resp.get("totalNumberOfItems", 0)
        items = resp.get("items", [])
        if total_items <= 100: return items

        tasks = []
        for offset in range(100, total_items, 100):
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

    async def get_downloadable(self, track_id: str, quality: int):
        q_val = QUALITY_MAP.get(quality, "HIGH")
        params = {"audioquality": q_val, "playbackmode": "STREAM", "assetpresentation": "FULL", "prefetch": "false"}
        try:
            resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall/v4", params, base=API_BASE)
        except:
            resp = await self._api_request(f"tracks/{track_id}/playbackinfopostpaywall", params, base=API_BASE)

        try:
            if "manifest" in resp:
                manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
            else:
                manifest = resp
        except:
            return await self.get_downloadable(track_id, quality - 1)

        enc_key = manifest.get("keyId")
        if manifest.get("encryptionType") == "NONE": enc_key = None
        download_url = manifest.get("urls", [])[0] if "urls" in manifest else ""

        return TidalDownloadable(self.session, url=download_url, codec=manifest.get("codecs", "flac"),
                                 encryption_key=enc_key, restrictions=manifest.get("restrictions"))

    async def get_video_file_url(self, video_id: str) -> str:
        params = {"videoquality": "HIGH", "playbackmode": "STREAM", "assetpresentation": "FULL"}
        resp = await self._api_request(f"videos/{video_id}/playbackinfopostpaywall", params=params, base=VIDEO_BASE)
        manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        async with self.session.get(manifest["urls"][0]) as resp: available_urls = await resp.text()
        *_, last_match = STREAM_URL_REGEX.finditer(available_urls)
        return last_match.group(1) if last_match else manifest["urls"][0]

    async def _login_by_access_token(self, token: str, user_id: str):
        headers = {"authorization": f"Bearer {token}"}
        async with self.session.get(f"{API_BASE}/sessions", headers=headers) as _resp: resp = await _resp.json()
        if resp.get("status", 200) != 200: raise Exception(f"Login failed {resp}")
        c = self.config;
        c.user_id = resp["userId"];
        c.country_code = resp["countryCode"];
        c.access_token = token
        self._update_authorization_from_config()

    async def _get_login_link(self) -> str:
        data = {"client_id": CLIENT_ID, "scope": "r_usr+w_usr+w_sub"}
        resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)
        return f"https://{resp['deviceCode']}"

    def _update_authorization_from_config(self):
        self.session.headers.update({"authorization": f"Bearer {self.config.access_token}"})

    async def _get_auth_status(self, device_code):
        data = {"client_id": CLIENT_ID, "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "scope": "r_usr+w_usr+w_sub"}
        resp = await self._api_post(f"{AUTH_URL}/token", data, AUTH)
        if "status" in resp and resp["status"] != 200: return (
            2 if resp["status"] == 400 and resp["sub_status"] == 1002 else 1), {}
        return 0, {"user_id": resp["user"]["userId"], "country_code": resp["user"]["countryCode"],
                   "access_token": resp["access_token"], "refresh_token": resp["refresh_token"],
                   "token_expiry": resp["expires_in"] + time.time()}

    async def _refresh_access_token(self):
        async with self.auth_lock:
            if self.config.token_expiry and (float(self.config.token_expiry) - time.time() > 600):
                return

            logger.info("Refreshing Tidal access token...")
            data = {"client_id": CLIENT_ID, "refresh_token": self.refresh_token, "grant_type": "refresh_token",
                    "scope": "r_usr+w_usr+w_sub"}
            try:
                resp = await self._api_post(f"{AUTH_URL}/token", data, AUTH)
                if resp.get("status", 200) != 200:
                    raise Exception("Refresh failed")

                c = self.config
                c.access_token = resp["access_token"]
                c.token_expiry = resp["expires_in"] + time.time()
                self._update_authorization_from_config()
                logger.info("Tidal token refreshed successfully.")
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                raise e

    async def _get_device_code(self):
        if not hasattr(self, "session"): self.session = await self.get_session()
        data = {"client_id": CLIENT_ID, "scope": "r_usr+w_usr+w_sub"}
        resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)
        return resp["deviceCode"], resp["verificationUriComplete"]

    async def _api_post(self, url, data, auth: aiohttp.BasicAuth | None = None) -> dict:
        async with self.semaphore:
            async with self.session.post(url, data=data, auth=auth) as resp: return await resp.json()

    async def _api_request(self, path: str, params=None, base: str = API_BASE, retries: int = 10) -> dict:
        if params is None: params = {}
        if "countryCode" not in params: params["countryCode"] = self.config.country_code
        if "limit" not in params: params["limit"] = 100

        for attempt in range(retries + 1):
            async with self.semaphore:
                url = path if path.startswith("http") else f"{base}/{path}"

                try:
                    async with self.session.get(url, params=params) as resp:
                        # --- 1. SMART AUTO-REGULATION (Backoff) ---
                        if resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                wait = int(retry_after) + 1
                                logger.warning(f"Tidal says STOP. Cooling down for {wait}s...")
                            else:
                                jitter = random.uniform(0.5, 2.0)
                                wait = (5 * (2 ** attempt)) + jitter
                                logger.warning(f"Rate Limit hit. Backing off for {wait:.1f}s...")

                            await asyncio.sleep(wait)
                            continue

                        # --- 2. AUTHENTICATION REFRESH ---
                        if resp.status == 401:
                            if attempt < 2:
                                logger.warning("Token expired (401). refreshing...")
                                await asyncio.sleep(1)
                                await self._refresh_access_token()
                                continue
                            else:
                                raise Exception("Tidal returned 401 (Unauthorized) repeatedly.")

                        # --- 3. RESOURCE MISSING ---
                        if resp.status == 404:
                            raise NonStreamableError("TIDAL: Resource not found (404)")

                        resp.raise_for_status()
                        try:
                            return await resp.json()
                        except:
                            return json.loads(await resp.text())

                except aiohttp.ClientOSError:
                    await asyncio.sleep(1)
                    continue
                except Exception as e:
                    if "401" in str(e) and attempt < 2:
                        await self._refresh_access_token()
                        continue
                    if attempt == retries:
                        raise e

        raise Exception(f"Connection failed after {retries} retries.")