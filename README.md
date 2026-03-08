# Streamrip — ElVigilante Edition

> Fork of [nathom/streamrip](https://github.com/nathom/streamrip) with enhanced reliability, security improvements, and configurable retry logic.

A powerful, scriptable music and video downloader for **Qobuz**, **Tidal**, **Deezer**, and **SoundCloud**, featuring TiDDL-style colored output.

## What's new in this fork

| Improvement | Details |
|---|---|
| **Tidal credentials via env vars** | Set `TIDAL_CLIENT_ID` / `TIDAL_CLIENT_SECRET` instead of hardcoding |
| **Configurable retries** | `max_retries` and `retry_delay` in `config.toml` |
| **Exponential backoff** | Downloads retry with increasing wait (2 s → 4 s → 8 s …) |
| **Proper exceptions** | `assert` statements replaced by `ValueError` / `KeyError` |
| **Semaphore warning** | Conflicting concurrency settings log a warning instead of crashing |
| **Cleaner startup** | Removed redundant config re-read on startup |
| **Test suite** | 69 unit tests covering config, database, file paths, and semaphore |

## Features

- **High Quality Audio** — FLAC up to 24-bit/192 kHz, AAC, MP3
- **Video Support** — Tidal videos (MP4/HLS) with full metadata
- **Metadata** — Auto-tagging with cover art, lyrics, and credits
- **Playlist / Artist** — Full playlist, album, and discography downloads
- **Concurrent downloads** — Async engine with smart rate limiting
- **TiDDL Styling** — Color-coded output (green = success, yellow = skipped, red = error)

---

## Installation

### From GitHub (recommended)

```bash
pip install git+https://github.com/Np3ir/streamrip-elvigilante
```

### For development

```bash
git clone https://github.com/Np3ir/streamrip-elvigilante
cd streamrip-elvigilante
pip install -e ".[dev]"
```

### Requirements

- Python **3.10** or later
- FFmpeg (required for audio conversion — optional if you don't convert)

---

## Quick start

```bash
# Download a single URL (album, track, artist, or playlist)
rip url "https://tidal.com/browse/album/12345678"
rip url "https://open.qobuz.com/album/0060254728697"
rip url "https://www.deezer.com/album/123456"

# Search interactively
rip search "The Weeknd"

# Open the config file for editing
rip config open

# Authenticate with Tidal
rip config --tidal

# Retry failed downloads
rip repair
```

---

## Configuration

Streamrip reads `config.toml` from your platform's app-config directory.
Run `rip config open` to open it in your default editor.

### Key settings

```toml
[downloads]
folder              = "~/Music"          # where files are saved
concurrency         = true               # download tracks in parallel
max_connections     = 6                  # max simultaneous downloads (-1 = unlimited)
requests_per_minute = 60                 # API rate limit (-1 = unlimited)
verify_ssl          = true

# Retry settings (new in this fork)
max_retries         = 3                  # attempts before giving up
retry_delay         = 2.0               # seconds for first retry (doubles each attempt)

[tidal]
quality         = 3        # 0=AAC 256, 1=AAC 320, 2=FLAC 16/44.1, 3=FLAC 24/96 MQA
download_videos = true

[qobuz]
# 1=MP3 320, 2=FLAC 16/44.1, 3=FLAC 24/<=96, 4=FLAC 24/>=96
quality = 3

[deezer]
quality = 2   # 0=MP3 128, 1=MP3 320, 2=FLAC
arl     = "YOUR_DEEZER_ARL_COOKIE"

[soundcloud]
quality = 0   # only option

[conversion]
enabled       = false
codec         = "ALAC"   # ALAC, FLAC, MP3, AAC, OGG, OPUS
sampling_rate = 48
bit_depth     = 16

[filepaths]
folder_format = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format  = "{tracknumber:02}. {artist} - {title}{explicit}"

[artwork]
embed        = true
embed_size   = "large"   # small, standard, large, max
save_artwork = true
```

### Tidal credentials via environment variables

Instead of storing credentials in the config, export them as environment variables:

```bash
export TIDAL_CLIENT_ID="your_client_id"
export TIDAL_CLIENT_SECRET="your_client_secret"
```

---

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Disclaimer

This tool is intended for **educational and private use only**.
Users are responsible for complying with each service's terms of use.
Please support artists by purchasing their music.

---

## Credits

- Original project: [nathom/streamrip](https://github.com/nathom/streamrip) — GPL-3.0
- This fork: ElVigilante enhancements — GPL-3.0
