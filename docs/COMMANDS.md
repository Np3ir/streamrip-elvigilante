# Command reference

Streamrip is used through the `rip` command. All sub-commands and options are documented here.

---

## General structure

```
rip [GLOBAL OPTIONS] COMMAND [COMMAND ARGUMENTS AND OPTIONS]
```

---

## Global options

These options are available on **every** command:

| Option | Short | Description |
|--------|-------|-------------|
| `--config-path PATH` | — | Path to an alternative `config.toml` file. |
| `--folder PATH` | `-f` | Download folder (overrides `downloads.folder` in the config). |
| `--no-db` | `-ndb` | Ignore the database. Re-downloads even if the track is already registered. |
| `--quality 0-4` | `-q` | Maximum quality level (applies to all sources simultaneously). |
| `--codec CODEC` | `-c` | Convert downloaded files. Values: `ALAC`, `FLAC`, `MP3`, `AAC`, `OGG`. Temporarily enables `conversion.enabled = true`. |
| `--no-progress` | — | Do not show progress bars. |
| `--no-ssl-verify` | — | Disable SSL certificate verification. Use when you get certificate errors. |
| `--verbose` | `-v` | Debug mode: shows detailed logs and full error traces. |
| `--version` | — | Show the installed version of streamrip. |
| `--help` | — | Show command help. |

---

## `rip url`

Download content directly from one or more URLs.

```bash
rip url URL [URL ...]
```

### Description

Accepts URLs from Qobuz, Tidal, Deezer and SoundCloud. The content type
(track, album, artist, playlist) is detected automatically from the URL.

### Examples

```bash
# A Tidal album
rip url "https://tidal.com/browse/album/12345678"

# A Qobuz track
rip url "https://open.qobuz.com/track/abc123"

# A full Deezer artist (downloads the entire discography)
rip url "https://www.deezer.com/artist/456"

# A SoundCloud playlist
rip url "https://soundcloud.com/user/sets/my-playlist"

# Multiple URLs in one command
rip url "https://tidal.com/browse/album/111" \
        "https://open.qobuz.com/album/222" \
        "https://www.deezer.com/album/333"

# With global options: quality 2, no database, to a specific folder
rip -q 2 -ndb -f /tmp/music url "https://tidal.com/browse/album/12345678"

# Convert to ALAC after downloading
rip -c ALAC url "https://open.qobuz.com/album/abc123"
```

### Supported URLs

**Qobuz**

```
https://open.qobuz.com/track/{id}
https://open.qobuz.com/album/{id}
https://open.qobuz.com/artist/{id}
https://open.qobuz.com/playlist/{id}
https://www.qobuz.com/*/album/*/{id}
```

**Tidal**

```
https://tidal.com/browse/track/{id}
https://tidal.com/browse/album/{id}
https://tidal.com/browse/artist/{id}
https://tidal.com/browse/playlist/{uuid}
https://tidal.com/browse/video/{id}
https://listen.tidal.com/album/{id}
```

**Deezer**

```
https://www.deezer.com/track/{id}
https://www.deezer.com/album/{id}
https://www.deezer.com/artist/{id}
https://www.deezer.com/playlist/{id}
```

**SoundCloud**

```
https://soundcloud.com/{user}/{track-slug}
https://soundcloud.com/{user}/sets/{playlist-slug}
```

---

## `rip file`

Download content from URLs or IDs listed in a text or JSON file.

```bash
rip file FILE_PATH
```

### Supported file formats

**Text file** (`.txt`) — one URL per line:

```
https://tidal.com/browse/album/12345678
https://open.qobuz.com/album/abc123
https://www.deezer.com/album/456789
# Empty lines and duplicates are ignored automatically
```

**JSON file** (`.json`) — list of objects with `source`, `media_type` and `id`:

```json
[
  {"source": "qobuz",      "media_type": "album",    "id": "0060254728697"},
  {"source": "tidal",      "media_type": "track",    "id": "12345678"},
  {"source": "tidal",      "media_type": "playlist",  "id": "uuid-here"},
  {"source": "deezer",     "media_type": "artist",   "id": "456"},
  {"source": "soundcloud", "media_type": "track",    "id": "track-slug"}
]
```

Valid values for `media_type`: `track`, `album`, `artist`, `playlist`.

### Examples

```bash
# Text file with URLs
rip file list.txt

# JSON file with IDs
rip file downloads.json

# With global options
rip -q 3 -f ~/HiResMusic file list.txt
```

> Duplicate URLs in text files are removed automatically and the count is reported.

---

## `rip search`

Interactive or automatic search on a specific source.

```bash
rip search [OPTIONS] SOURCE TYPE QUERY
```

### Parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `SOURCE` | `qobuz` · `tidal` · `deezer` · `soundcloud` | Source to search in |
| `TYPE` | `track` · `album` · `artist` · `playlist` | Content type |
| `QUERY` | free text | Search terms |

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--first` | `-f` | Download the first result automatically without showing the menu. |
| `--output-file PATH` | `-o` | Save results to a JSON file instead of showing the menu. Useful for later processing. |
| `--num-results N` | `-n` | Maximum number of results (default: 100). |

> `--first` and `--output-file` are mutually exclusive.

### Examples

```bash
# Interactive album search on Qobuz
rip search qobuz album "Rumours"

# Track search on Tidal
rip search tidal track "Bohemian Rhapsody"

# Artist search on Deezer
rip search deezer artist "Radiohead"

# Download the first result automatically
rip search --first qobuz album "Dark Side of the Moon"

# Save results to JSON for later processing
rip search --output-file results.json qobuz album "Daft Punk"

# Limit to 20 results
rip search -n 20 tidal album "Mozart"

# With forced quality
rip -q 2 search qobuz album "Miles Davis"
```

### Interactive menu

When using `rip search` without `--first` or `--output-file`, a menu is shown with the
results. Navigate with the arrow keys and press **Enter** to select.
You can select multiple results with **Space** if the mode allows it.

---

## `rip id`

Download an item by its internal source ID.

```bash
rip id SOURCE TYPE ID
```

### Parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `SOURCE` | `qobuz` · `tidal` · `deezer` · `soundcloud` | Source of the item |
| `TYPE` | `track` · `album` · `artist` · `playlist` | Item type |
| `ID` | string | ID of the item in the source |

### Examples

```bash
# Qobuz album by ID
rip id qobuz album "0060254728697"

# Tidal track by ID
rip id tidal track "12345678"

# Deezer artist
rip id deezer artist "456"

# Tidal playlist (ID is usually a UUID)
rip id tidal playlist "01234567-89ab-cdef-0123-456789abcdef"
```

> IDs are found in the URL of each service.
> For example, in `https://tidal.com/browse/album/12345678` the ID is `12345678`.

---

## `rip lastfm`

Download the tracks of a public Last.fm playlist by searching them on Qobuz, Tidal or Deezer.

```bash
rip lastfm [OPTIONS] URL
```

### Description

Reads the track list from the Last.fm URL and searches each track on the configured source
(default `qobuz`). If a track is not found, it searches on the fallback source.

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--source SOURCE` | `-s` | Primary search source (overrides `lastfm.source` in config). |
| `--fallback-source SOURCE` | `-fs` | Fallback source if no results are found. |

### Examples

```bash
# Using the source configured in config.toml
rip lastfm "https://www.last.fm/user/username/playlists/12345"

# Search on Tidal, with Deezer as fallback
rip lastfm -s tidal -fs deezer "https://www.last.fm/user/username/playlists/12345"

# Qobuz only, no fallback
rip lastfm -s qobuz "https://www.last.fm/user/username/playlists/12345"
```

> Last.fm playlists must be **public** for streamrip to access them.

---

## `rip config`

Group of commands for managing the configuration file.

### `rip config open`

Opens `config.toml` in the system default editor.

```bash
rip config open [--vim]
```

| Option | Description |
|--------|-------------|
| `--vim` / `-v` | Open in Neovim (if installed) or Vim. |

```bash
# Default editor
rip config open

# Neovim / Vim
rip config open --vim
```

### `rip config path`

Shows the full path to the active configuration file.

```bash
rip config path
```

Useful for knowing where the config is on your system, especially if you use `--config-path`.

### `rip config reset`

Resets the configuration file to default values.

```bash
rip config reset [--yes]
```

| Option | Description |
|--------|-------------|
| `--yes` / `-y` | Skip the confirmation prompt. |

> **Warning!** This overwrites your current config. Make a backup if you have custom settings.

```bash
# With interactive confirmation
rip config reset

# Without confirmation
rip config reset --yes
```

---

## `rip database`

Group of commands for querying the databases.

### `rip database browse`

Shows the contents of a database table in table format.

```bash
rip database browse TABLE
```

| Table | Description |
|-------|-------------|
| `downloads` | Successfully downloaded tracks. |
| `failed` | Downloads that failed. |

```bash
# View downloaded tracks
rip database browse downloads

# View failed downloads (source, type, ID)
rip database browse failed
```

---

## Workflow examples

### Basic flow: search and download

```bash
# 1. Search interactively
rip search qobuz album "Daft Punk"

# 2. Or download directly by URL
rip url "https://open.qobuz.com/album/0060254728697"
```

### Bulk download flow

```bash
# 1. Prepare a file with URLs
cat > list.txt << EOF
https://tidal.com/browse/album/111
https://tidal.com/browse/album/222
https://open.qobuz.com/album/333
EOF

# 2. Download everything
rip file list.txt
```

### Conversion flow

```bash
# Download FLAC from Qobuz and convert to ALAC (Apple Lossless)
rip -c ALAC url "https://open.qobuz.com/album/abc123"

# Or configure conversion permanently in config.toml:
# [conversion]
# enabled = true
# codec   = "ALAC"
```

### Discography download flow

```bash
# Full discography of an artist on Tidal
rip url "https://tidal.com/browse/artist/123456"

# With filters (studio albums only, no repeats)
# Enable in config.toml:
# [qobuz_filters]
# non_studio_albums = true
# repeats = true
rip url "https://open.qobuz.com/artist/456789"
```

### Last.fm flow

```bash
# Export your Last.fm playlist to Qobuz
rip lastfm "https://www.last.fm/user/yourusername/playlists/12345"

# With Tidal and Deezer as fallback
rip lastfm -s tidal -fs deezer "https://www.last.fm/user/yourusername/playlists/12345"
```

### Debugging flow

```bash
# Show all logs to diagnose a problem
rip -v url "https://tidal.com/browse/album/12345678"

# Disable database and re-download everything
rip -ndb url "https://tidal.com/browse/album/12345678"

# Without SSL verification (on networks with certificate issues)
rip --no-ssl-verify url "https://open.qobuz.com/album/abc123"
```

---

## Help in the terminal

Every command has built-in help:

```bash
rip --help
rip url --help
rip search --help
rip config --help
rip config open --help
rip database --help
rip database browse --help
rip lastfm --help
rip id --help
rip file --help
```
