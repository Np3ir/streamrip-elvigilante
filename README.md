# Streamrip — ElVigilante Edition

> Fork of [nathom/streamrip](https://github.com/nathom/streamrip) with improved reliability, enhanced security and extended configuration options.

A powerful, scriptable music and video downloader for **Qobuz**, **Tidal**, **Deezer** and **SoundCloud**, with TiDDL-style colour output.

---

## Table of contents

- [What's new in this fork](#whats-new-in-this-fork)
- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Artist separator](#artist-separator)
- [Path templates](#path-templates)
- [Authentication](#authentication)
- [Tests](#tests)
- [Additional documentation](#additional-documentation)
- [Legal notice](#legal-notice)
- [Credits](#credits)

---

## What's new in this fork

| Improvement | Description |
|-------------|-------------|
| **Tidal credentials via env vars** | Use `TIDAL_CLIENT_ID` / `TIDAL_CLIENT_SECRET` instead of hard-coding values |
| **Configurable retries** | `max_retries`, `retry_delay` and `max_wait` in `config.toml` |
| **Exponential back-off** | Retries wait 2 s → 4 s → 8 s … up to `max_wait` |
| **Configurable artist separator** | Choose `", "`, `" & "`, `" / "`, etc. for file names and audio tags |
| **Safe post-process** | If a file is missing after all retries, post-processing is skipped instead of crashing |
| **Playlist folder fix** | `set_playlist_to_album = true` no longer duplicates the folder name |
| **Proper exceptions** | `assert` statements replaced by `ValueError` / `KeyError` |
| **Semaphore warning** | Conflicting concurrency settings emit a warning instead of crashing |
| **Test suite** | 69 unit tests: config, database, paths, semaphore and retries |
| **Code-reviewed** | Multiple rounds of review with Sourcery AI |

---

## Features

- **High-quality audio** — FLAC up to 24-bit/192 kHz, AAC, MP3
- **Video support** — Tidal videos (MP4/HLS) with full metadata
- **Automatic metadata** — Full tags, cover art, lyrics and credits embedded
- **Playlist / Artist** — Download playlists, full albums and entire discographies
- **Concurrent downloads** — Async engine with intelligent rate limiting
- **TiDDL output** — Green = success, yellow = skipped, red = error
- **Local database** — Avoids re-downloading already downloaded tracks
- **Last.fm** — Download Last.fm playlists by searching Qobuz / Tidal / Deezer

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

| Requirement | Minimum version | Notes |
|-------------|----------------|-------|
| Python | 3.10 | 3.11+ recommended |
| FFmpeg | any | Only needed if you use audio conversion |

**Install FFmpeg:**

- **Windows:** `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg` / `sudo dnf install ffmpeg`

---

## Quick start

```bash
# 1. Open the config file to edit it
rip config open

# 2. Download by URL (album, track, artist or playlist)
rip url "https://tidal.com/browse/album/12345678"
rip url "https://open.qobuz.com/album/0060254728697"
rip url "https://www.deezer.com/album/123456"
rip url "https://soundcloud.com/artist/track-name"

# 3. Search interactively
rip search qobuz album "Rumours"
rip search tidal track "Bohemian Rhapsody"

# 4. Download multiple URLs from a text file
rip file urls.txt

# 5. Browse the downloads database
rip database browse downloads
```

---

## Commands

See [`docs/COMMANDS.md`](docs/COMMANDS.md) for the full command reference.

### Global options (apply to all commands)

```
rip [OPTIONS] COMMAND [ARGS]

Options:
  --config-path PATH    Path to an alternative config file
  -f, --folder PATH     Download folder (overrides config.toml)
  -ndb, --no-db         Ignore the database (re-downloads everything)
  -q, --quality 0-4     Maximum allowed quality
  -c, --codec CODEC     Convert to: ALAC, FLAC, MP3, AAC, OGG
  --no-progress         Do not show progress bars
  --no-ssl-verify       Disable SSL certificate verification
  -v, --verbose         Debug mode (shows detailed logs)
  --version             Show version
```

---

### `rip url`

Download content from one or more URLs.

```bash
rip url URL [URL ...]
```

```bash
# An album
rip url "https://tidal.com/browse/album/12345678"

# Multiple URLs at once
rip url "https://tidal.com/browse/album/12345678" \
        "https://open.qobuz.com/album/abc123"

# Force a maximum quality level
rip -q 2 url "https://www.deezer.com/album/456789"

# Convert to MP3 after downloading
rip -c MP3 url "https://tidal.com/browse/track/99999"
```

**Supported URL types:**

| Source | Types |
|--------|-------|
| Qobuz | album, track, artist, playlist |
| Tidal | album, track, artist, playlist, video |
| Deezer | album, track, artist, playlist |
| SoundCloud | track, playlist |

---

### `rip search`

Interactive search with a menu.

```bash
rip search [OPTIONS] SOURCE TYPE QUERY
```

```bash
# Interactive search
rip search qobuz album "Rumours"
rip search tidal track "Bohemian Rhapsody"

# Download the first result automatically
rip search -f qobuz album "Dark Side of the Moon"

# Save results to JSON for later processing
rip search -o results.json qobuz album "Daft Punk"
```

---

### `rip config`

Manage the configuration file.

```bash
rip config open        # Open in the system default editor
rip config open --vim  # Open in Vim / Neovim
rip config path        # Show the config file path
rip config reset       # Reset to defaults
rip config reset --yes # Reset without confirmation
```

---

### `rip database`

Browse the download databases.

```bash
rip database browse downloads  # Successfully downloaded tracks
rip database browse failed     # Failed downloads
```

---

## Configuration

`config.toml` is created automatically the first time you run `rip`.
Use `rip config path` to find its location and `rip config open` to edit it.

For the complete reference of all configuration options, see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

### Config file location

| OS | Path |
|----|------|
| Windows | `%APPDATA%\streamrip\config.toml` |
| macOS | `~/Library/Application Support/streamrip/config.toml` |
| Linux | `~/.config/streamrip/config.toml` |

### Key sections at a glance

```toml
[downloads]
folder            = "~/Music"
concurrency       = true
max_connections   = 6
max_retries       = 3
retry_delay       = 2.0
max_wait          = 60.0

[metadata]
set_playlist_to_album    = true
renumber_playlist_tracks = true
artist_separator         = ", "   # see Artist separator below

[filepaths]
folder_format = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format  = "{tracknumber:02}. {artist} - {title}{explicit}"
```

---

## Artist separator

When a track has multiple artists, you can control how they are joined in both the file name and the embedded `ARTIST` / `ALBUMARTIST` tag:

```toml
[metadata]
artist_separator = " & "   # e.g. "Calvin Harris & Dua Lipa"
```

| Value | Result |
|-------|--------|
| `", "` (default) | `Calvin Harris, Dua Lipa` |
| `" & "` | `Calvin Harris & Dua Lipa` |
| `" / "` | `Calvin Harris / Dua Lipa` |
| `"; "` | `Calvin Harris; Dua Lipa` |

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
| `{artist_initials}` | First letter of artist | `D` |
| `{release_date}` | Full release date | `2013-05-17` |

### Variables for `track_format`

| Variable | Description | Example |
|----------|-------------|---------|
| `{tracknumber}` | Track number | `1` or `{tracknumber:02}` → `01` |
| `{artist}` | Track artist(s) | `Daft Punk` |
| `{albumartist}` | Album artist | `Daft Punk` |
| `{title}` | Track title | `Get Lucky` |
| `{composer}` | Composer | `Thomas Bangalter` |
| `{albumcomposer}` | Album composer | `Thomas Bangalter` |
| `{explicit}` | `(explicit)` or empty | `(explicit)` |

---

## Authentication

### Qobuz

1. Run `rip config open`
2. Fill in `email_or_userid` and `password_or_token` (MD5 hash of the password)
3. Or use `use_auth_token = true` and put your token in `password_or_token`

### Tidal

Credentials are filled in automatically when you authenticate. You can also use environment variables:

```bash
export TIDAL_CLIENT_ID="your_client_id"
export TIDAL_CLIENT_SECRET="your_client_secret"
```

Tokens expire roughly every week. If you see authentication errors, you may need to renew the token.

### Deezer

1. Open [deezer.com](https://deezer.com) in your browser
2. Open Developer Tools (F12)
3. Go to **Application → Cookies → deezer.com**
4. Copy the value of the `arl` cookie
5. Paste it in `config.toml`:

```toml
[deezer]
arl = "YOUR_ARL_COOKIE_HERE"
```

### SoundCloud

SoundCloud does not require an account to download. The `client_id` and `app_version` are obtained automatically.

---

## Tests

```bash
pip install -e ".[dev]"
pytest              # all tests
pytest -v           # verbose
pytest tests/test_config.py  # a specific module
```

**Test modules:**

| File | What it tests |
|------|---------------|
| `test_config.py` | Config loading, validation and updates |
| `test_db.py` | Downloads and failed-downloads database |
| `test_filepath_utils.py` | Path cleaning and truncation |
| `test_semaphore_behavior.py` | Concurrency semaphore |
| `test_track_retry_behavior.py` | Retry logic and exponential back-off |

---

## Additional documentation

| Document | Contents |
|----------|----------|
| [`docs/COMMANDS.md`](docs/COMMANDS.md) | Full reference for all commands |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Full reference for all configuration options |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Solutions for common problems |
| [`CHANGELOG.md`](CHANGELOG.md) | Change history |

---

## Legal notice

This software is for **educational and personal use only**.
Users are responsible for complying with the terms of service of each platform.
Please support artists by purchasing their music.

---

## Credits

- Original project: [nathom/streamrip](https://github.com/nathom/streamrip) — GPL-3.0
- This fork: ElVigilante — GPL-3.0
