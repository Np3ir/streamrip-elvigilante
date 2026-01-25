# Streamrip (TiDDL Edition)

A powerful, scriptable music and video downloader for Qobuz, Tidal, Deezer, and SoundCloud, featuring the new TiDDL styling.

## Features

- **High Quality Audio**: Downloads FLAC (up to 24-bit/192kHz) and AAC/MP3.
- **Video Support**: **NEW!** Downloads Tidal videos (MP4) with full metadata and HLS support.
- **Metadata**: Automatically tags files with cover art, lyrics, and credits.
- **Playlist Support**: Downloads entire playlists, albums, and artist discographies.
- **TiDDL Styling**: Enhanced console output with color-coded status messages (Green for success, Yellow for skipped, Red for errors).
- **Efficient**: Asynchronous downloads with smart concurrency.

## Installation

```bash
pip install streamrip
```

## Configuration

Streamrip uses a `config.toml` file to manage your credentials and preferences. You can open it for editing by running:

```bash
rip config open
```

### Complete Configuration Reference

Below is a complete example of the configuration file with placeholders. You can copy this structure if you need to reset your configuration.

```toml
[downloads]
# Folder where tracks are downloaded to
folder = "C:/Downloads/Music"
# Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc.
source_subdirectories = false
# Put tracks in an album with 2 or more discs into a subfolder named `Disc N` 
disc_subdirectories = true
# Download (and convert) tracks all at once, instead of sequentially.
concurrency = true
# The maximum number of tracks to download at once (-1 for no limit)
max_connections = 6
# Max number of API requests per source to handle per minute (-1 for no limit)
requests_per_minute = 60
# Verify SSL certificates for API connections
verify_ssl = true

[qobuz]
# 1: 320kbps MP3, 2: 16/44.1, 3: 24/<=96, 4: 24/>=96
quality = 3
# This will download booklet pdfs that are included with some albums
download_booklets = true
# Authenticate to Qobuz using auth token? Value can be true/false only
use_auth_token = false
# Enter your userid if the above use_auth_token is set to true, else enter your email
email_or_userid = "YOUR_EMAIL_OR_USERID"
# Enter your auth token if the above use_auth_token is set to true, else enter the md5 hash of your plaintext password
password_or_token = "YOUR_PASSWORD_OR_TOKEN"
app_id = "YOUR_APP_ID"
secrets = ["YOUR_APP_SECRET"]

[tidal]
# 0: 256kbps AAC, 1: 320kbps AAC, 2: 16/44.1 "HiFi" FLAC, 3: 24/44.1 "MQA" FLAC
quality = 3
# This will download videos included in Video Albums.
download_videos = true
user_id = "YOUR_TIDAL_USER_ID"
country_code = "US"
access_token = "YOUR_ACCESS_TOKEN"
refresh_token = "YOUR_REFRESH_TOKEN"
token_expiry = "EXPIRY_TIMESTAMP"

[deezer]
# 0, 1, or 2 (2 is FLAC)
quality = 2
# An authentication cookie that allows streamrip to use your Deezer account
arl = "YOUR_DEEZER_ARL_COOKIE"
# This allows for free 320kbps MP3 downloads from Deezer
use_deezloader = true
deezloader_warnings = true

[soundcloud]
quality = 0 # Only 0 is available
client_id = "YOUR_SOUNDCLOUD_CLIENT_ID"
app_version = "YOUR_APP_VERSION"

[youtube]
quality = 0
download_videos = false
video_downloads_folder = "C:/Downloads/Videos"

[database]
downloads_enabled = true
downloads_path = "C:/Users/You/AppData/Local/streamrip/downloads.db"
failed_downloads_enabled = true
failed_downloads_path = "C:/Users/You/AppData/Local/streamrip/failed_downloads.db"

[conversion]
# Convert tracks to a codec after downloading them.
enabled = false
# ALAC, FLAC, MP3, AAC, OGG, OPUS
codec = "ALAC"
# 44.1, 48, 88.2, 96, 176.4, 192
sampling_rate = 48
# 16, 24
bit_depth = 16

[filepaths]
# Available keys: album, albumartist, title, year, tracknumber, artist, container, bit_depth, sampling_rate, explicit
folder_format = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format = "{tracknumber:02}. {artist} - {title}{explicit}"
# Characters to remove from filenames (Windows restrictions are handled automatically)
restrict_characters = ":\"*?<>|,"

[artwork]
# Embed artwork into audio files
embed = true
# small (200x200), standard (600x600), large (1200x1200), max (original)
embed_size = "large"
# Save cover.jpg in the album folder
save_artwork = true

[cli]
# Show progress bars in the terminal
progress_bars = true
```

## Usage

### Basic Commands

Download a single URL (Album, Track, Artist, or Playlist):
```bash
rip url "https://tidal.com/browse/album/12345678"
```

Search for an artist or album:
```bash
rip search "The Weeknd"
```

### Advanced Usage

Check your configuration status:
```bash
rip config
```

Login to Tidal (interactive):
```bash
rip config --tidal
```

Repair failed downloads:
```bash
rip repair
```

## Disclaimer

This tool is intended for educational and private use only. Users are responsible for complying with the terms of service of the content providers. Please support the artists by purchasing their music.
