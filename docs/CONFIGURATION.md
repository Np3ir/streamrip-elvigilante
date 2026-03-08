# Configuration reference

This document covers every option available in `config.toml`.

Use `rip config path` to locate your config file and `rip config open` to edit it.

---

## Table of contents

- [`[downloads]`](#downloads)
- [`[qobuz]`](#qobuz)
- [`[tidal]`](#tidal)
- [`[deezer]`](#deezer)
- [`[soundcloud]`](#soundcloud)
- [`[lastfm]`](#lastfm)
- [`[conversion]`](#conversion)
- [`[artwork]`](#artwork)
- [`[metadata]`](#metadata)
- [`[filepaths]`](#filepaths)
- [`[qobuz_filters]`](#qobuz_filters)
- [`[cli]`](#cli)
- [Path templates](#path-templates)
- [Artist separator](#artist-separator)

---

## Config file location

| OS | Default path |
|----|-------------|
| Windows | `%APPDATA%\streamrip\config.toml` |
| macOS | `~/Library/Application Support/streamrip/config.toml` |
| Linux | `~/.config/streamrip/config.toml` |

You can use a custom path with `rip --config-path /path/to/config.toml ...`.

---

## `[downloads]`

Controls where and how files are downloaded.

```toml
[downloads]
folder               = "~/Music"
source_subdirectories = false
disc_subdirectories  = true
concurrency          = true
max_connections      = 6
requests_per_minute  = 60
verify_ssl           = true
max_retries          = 3
retry_delay          = 2.0
max_wait             = 60.0
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `folder` | string | `~/Music` | Root download folder. |
| `source_subdirectories` | bool | `false` | Create a sub-folder per source (`Qobuz/`, `Tidal/`, …). |
| `disc_subdirectories` | bool | `true` | Create `Disc 1/`, `Disc 2/` sub-folders for multi-disc albums. |
| `concurrency` | bool | `true` | Enable parallel downloads. |
| `max_connections` | int | `6` | Maximum simultaneous connections. `-1` = unlimited. |
| `requests_per_minute` | int | `60` | API calls per minute. `-1` = unlimited. |
| `verify_ssl` | bool | `true` | Verify SSL certificates. Set to `false` only on trusted networks. |
| `max_retries` | int | `3` | Number of retries before giving up. `0` = no retries. |
| `retry_delay` | float | `2.0` | Initial wait in seconds between retries (doubles on each attempt). |
| `max_wait` | float | `60.0` | Maximum wait in seconds between retries. |

---

## `[qobuz]`

```toml
[qobuz]
quality           = 3
download_booklets = true
use_auth_token    = false
email_or_userid   = ""
password_or_token = ""
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `quality` | int | `3` | `1` = MP3 320 kbps · `2` = FLAC 16/44.1 kHz · `3` = FLAC 24/≤96 kHz · `4` = FLAC 24/≥96 kHz |
| `download_booklets` | bool | `true` | Download PDF booklets included with some albums. |
| `use_auth_token` | bool | `false` | `true` = use token, `false` = use email + password. |
| `email_or_userid` | string | `""` | Your Qobuz email address or user ID. |
| `password_or_token` | string | `""` | MD5 hash of your password (if `use_auth_token = false`) or your auth token. |

**Getting your Qobuz password hash:**

```bash
python3 -c "import hashlib; print(hashlib.md5('YOUR_PASSWORD'.encode()).hexdigest())"
```

---

## `[tidal]`

```toml
[tidal]
quality         = 3
download_videos = true
user_id         = ""
country_code    = ""
access_token    = ""
refresh_token   = ""
token_expiry    = ""
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `quality` | int | `3` | `0` = AAC 256 kbps · `1` = AAC 320 kbps · `2` = FLAC 16/44.1 kHz · `3` = FLAC 24/44.1 kHz (MQA) |
| `download_videos` | bool | `true` | Download video albums. |
| `user_id` | string | `""` | Filled in automatically when you authenticate. |
| `country_code` | string | `""` | Filled in automatically when you authenticate. |
| `access_token` | string | `""` | Filled in automatically when you authenticate. |
| `refresh_token` | string | `""` | Filled in automatically when you authenticate. |
| `token_expiry` | string | `""` | Filled in automatically when you authenticate. |

**Environment variables (alternative to config):**

```bash
export TIDAL_CLIENT_ID="your_client_id"
export TIDAL_CLIENT_SECRET="your_client_secret"
```

Tokens expire roughly every week. If you see authentication errors, clear the token fields and re-authenticate.

---

## `[deezer]`

```toml
[deezer]
quality             = 2
arl                 = ""
use_deezloader      = true
deezloader_warnings = true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `quality` | int | `2` | `0` = MP3 128 kbps · `1` = MP3 320 kbps · `2` = FLAC |
| `arl` | string | `""` | Your Deezer ARL cookie (needed for FLAC quality). |
| `use_deezloader` | bool | `true` | Enable free 320 kbps downloads. |
| `deezloader_warnings` | bool | `true` | Warn when no active account is detected. |

**Getting your ARL:**

1. Open [deezer.com](https://www.deezer.com) and log in
2. Open Developer Tools (`F12`) → **Application → Cookies → deezer.com**
3. Copy the value of the `arl` cookie (a long string)
4. Paste it into config.toml:

```toml
[deezer]
arl = "YOUR_ARL_COOKIE"
```

> ARLs typically last several months but can be invalidated if you change your password or log out of all devices.

---

## `[soundcloud]`

```toml
[soundcloud]
quality     = 0
client_id   = ""
app_version = ""
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `quality` | int | `0` | Only available value. |
| `client_id` | string | `""` | Updated periodically. Obtained automatically or extracted manually from the site source. |
| `app_version` | string | `""` | Same as above. |

SoundCloud does not require an account to download.

---

## `[lastfm]`

```toml
[lastfm]
source          = "qobuz"
fallback_source = ""
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `source` | string | `"qobuz"` | Primary source for searching Last.fm playlist tracks. |
| `fallback_source` | string | `""` | Fallback source if no results are found on the primary. |

---

## `[conversion]`

Converts downloaded files to a different format. Requires FFmpeg.

```toml
[conversion]
enabled       = false
codec         = "ALAC"
sampling_rate = 48000
bit_depth     = 24
lossy_bitrate = 320
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable automatic conversion after download. |
| `codec` | string | `"ALAC"` | Target codec: `FLAC` · `ALAC` · `MP3` · `AAC` · `OGG` · `OPUS` |
| `sampling_rate` | int | `48000` | Target sample rate in Hz. Files above this are down-sampled. |
| `bit_depth` | int | `24` | Target bit depth. Only `16` and `24` are available. |
| `lossy_bitrate` | int | `320` | Target bitrate in kbps (only for lossy codecs). |

> Conversion cannot improve quality — only maintain or reduce it.
> Use `-c CODEC` on the command line to convert for a single download without changing the config.

---

## `[artwork]`

Controls cover art embedding and saving.

```toml
[artwork]
embed           = true
embed_size      = "large"
embed_max_width = -1
save_artwork    = true
saved_max_width = -1
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `embed` | bool | `true` | Embed cover art in the audio file. |
| `embed_size` | string | `"large"` | Embedded cover size: `thumbnail` · `small` · `large` · `original` |
| `embed_max_width` | int | `-1` | Maximum width in pixels for embedded covers. `-1` = no limit. |
| `save_artwork` | bool | `true` | Save cover art as a separate JPG file. |
| `saved_max_width` | int | `-1` | Maximum width in pixels for saved covers. `-1` = no limit. |

> If covers are not being embedded, try changing `embed_size` from `"original"` to `"large"` or set `embed_max_width = 600`.

---

## `[metadata]`

Controls how metadata is written to audio files and how playlists are handled.

```toml
[metadata]
set_playlist_to_album    = true
renumber_playlist_tracks = true
exclude                  = []
artist_separator         = ", "
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `set_playlist_to_album` | bool | `true` | Use the playlist name as the `ALBUM` tag in playlist downloads. |
| `renumber_playlist_tracks` | bool | `true` | Use the position in the playlist as the track number instead of the original album track number. |
| `exclude` | list | `[]` | List of tags to exclude from writing (e.g. `["lyrics", "isrc"]`). |
| `artist_separator` | string | `", "` | Separator used to join multiple artists in file names and embedded tags. See [Artist separator](#artist-separator). |

---

## `[filepaths]`

Controls how files and folders are named.

```toml
[filepaths]
add_singles_to_folder = false
folder_format         = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format          = "{tracknumber:02}. {artist} - {title}{explicit}"
restrict_characters   = false
truncate_to           = 120
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `add_singles_to_folder` | bool | `false` | Create a folder even for a single track. |
| `folder_format` | string | see above | Template for album folder names. |
| `track_format` | string | see above | Template for track file names (without extension). |
| `restrict_characters` | bool | `false` | Restrict file names to printable ASCII only. |
| `truncate_to` | int | `120` | Maximum file name length in characters. |

---

## `[qobuz_filters]`

Filters applied when downloading a Qobuz artist discography (`rip url qobuz_artist_url`).

```toml
[qobuz_filters]
extras            = false
repeats           = false
non_albums        = false
features          = false
non_studio_albums = false
non_remaster      = false
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `extras` | bool | `false` | Exclude collector's editions, live recordings, etc. |
| `repeats` | bool | `false` | Only keep the highest-quality version when there are duplicate titles. |
| `non_albums` | bool | `false` | Exclude EPs and singles. |
| `features` | bool | `false` | Exclude albums where the artist is a collaborator. |
| `non_studio_albums` | bool | `false` | Exclude live albums. |
| `non_remaster` | bool | `false` | Only keep remastered albums. |

---

## `[cli]`

Controls the command-line output.

```toml
[cli]
text_output        = true
progress_bars      = true
max_search_results = 100
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text_output` | bool | `true` | Show status messages. |
| `progress_bars` | bool | `true` | Show progress bars. |
| `max_search_results` | int | `100` | Maximum number of results in the interactive search menu. |

---

## Path templates

### Variables for `folder_format`

| Variable | Description | Example |
|----------|-------------|---------|
| `{albumartist}` | Album artist | `Daft Punk` |
| `{title}` | Album title | `Random Access Memories` |
| `{year}` | Release year | `2013` |
| `{container}` | File format | `FLAC` |
| `{bit_depth}` | Bit depth | `24` |
| `{sampling_rate}` | Sample rate in kHz | `44.1` |
| `{id}` | Internal source ID | `0060254728697` |
| `{albumcomposer}` | Album composer | `Thomas Bangalter` |
| `{artist_initials}` | First letter of the artist (A–Z or `#`) | `D` |
| `{release_date}` | Full release date | `2013-05-17` |

> `{artist_initials}` puts non-Latin characters and symbols under `#`.

### Variables for `track_format`

| Variable | Description | Example |
|----------|-------------|---------|
| `{tracknumber}` | Track number | `1` or `{tracknumber:02}` → `01` |
| `{artist}` | Track artist(s) | `Daft Punk` |
| `{albumartist}` | Album artist | `Daft Punk` |
| `{title}` | Track title | `Get Lucky` |
| `{composer}` | Composer | `Thomas Bangalter` |
| `{albumcomposer}` | Album composer | `Thomas Bangalter` |
| `{explicit}` | `(explicit)` or empty string | `(explicit)` |

### Example configurations

```toml
# Simple artist/album organisation
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"

# Quality in folder name
folder_format = "{albumartist} - {title} ({year}) [{container}]"
track_format  = "{tracknumber:02}. {artist} - {title}"

# Organised by initial (A/, B/, C/, …)
folder_format = "{artist_initials}/{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}{explicit}"
```

---

## Artist separator

When a track or album has multiple artists, `artist_separator` controls how they are joined
in both the file name and the embedded `ARTIST` / `ALBUMARTIST` tag.

```toml
[metadata]
artist_separator = " & "
```

| Value | Result |
|-------|--------|
| `", "` (default) | `Calvin Harris, Dua Lipa` |
| `" & "` | `Calvin Harris & Dua Lipa` |
| `" / "` | `Calvin Harris / Dua Lipa` |
| `"; "` | `Calvin Harris; Dua Lipa` |

The change applies to:
- The `ARTIST` tag of every track
- The `ALBUMARTIST` tag
- The generated file name (via `{artist}` and `{albumartist}` in `track_format` / `folder_format`)

Applies to Qobuz, Tidal and Deezer. SoundCloud has only a single artist per track.
