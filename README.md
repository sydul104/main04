# IPTV Playlist Auto-Updater

Automated system for maintaining a curated IPTV M3U playlist using GitHub Actions.

## 🎯 Overview

This system automatically:
- ✅ Downloads upstream playlists every 6 hours
- ✅ Updates stream URLs for channels in your curated playlist
- ✅ **Collects multiple URL alternatives per channel**
- ✅ **Validates URLs and switches to working alternatives**
- ✅ Preserves your metadata (logos, groups, names, ordering)
- ✅ Prevents unwanted channels from being added
- ✅ Removes duplicates
- ✅ Keeps channels as placeholders even without URLs
- ✅ Auto-commits changes to GitHub

## 📁 Files

```
.
├── my                                    # Your curated playlist (source of truth)
├── scripts/
│   └── update_playlist.py               # Python updater script
└── .github/
    └── workflows/
        └── update-playlist.yml          # GitHub Actions workflow
```

## 🚀 How It Works

### 1. **Curated Playlist is the Allowlist**
Your `my` file defines which channels to maintain. The script will:
- ONLY update channels already in this file
- NOT add new channels from upstream
- Keep your custom metadata and ordering

### 2. **Channel Matching**
Channels are matched using:
1. **tvg-id** (if present and valid)
2. **Channel name** (normalized text after comma in `#EXTINF`)

### 3. **URL Updates**
When a match is found upstream:
- Collects ALL available alternative URLs (not just one)
- Stream URL is updated to best available option
- With validation: automatically picks first working URL
- Your metadata (logo, group, name) is preserved
- Shows how many alternatives are available

### 4. **Smart URL Selection**
The system prioritizes working URLs:
1. If validation enabled: tests each alternative until one works
2. If current URL fails: automatically tries other alternatives  
3. Falls back to first alternative if none validate
4. Keeps broken URLs commented as last resort
Duplicate entries (same tvg-id or name) are automatically removed.

## 🔧 Setup

### Prerequisites
- GitHub repository with your `my` playlist file
- GitHub Actions enabled (free for public repos)
- Python 3.7+ (use `python3` on macOS)

### Installation

1. **Add the files to your repository:**
   ```bash
   # Copy the files to your repo
   mkdir -p scripts .github/workflows
   cp scripts/update_playlist.py scripts/
   cp .github/workflows/update-playlist.yml .github/workflows/
   ```

2. **Configure upstream sources** (optional):
   Edit `.github/workflows/update-playlist.yml` to customize upstream URLs:
   ```yaml
   --upstream \
     "https://raw.githubusercontent.com/sydul104/main04/refs/heads/main/my" \
     "https://raw.githubusercontent.com/musfiqeee/iptv-m3u-bot/main/output/all.m3u"
   ```

3. **Commit and push:**
   ```bash
   git add .
   git commit -m "Add IPTV playlist auto-updater"
   git push
   ```

4. **Enable GitHub Actions:**
   - Go to your repository on GitHub
   - Click **Actions** tab
   - Enable workflows if prompted

## 📅 Automation Schedule

The workflow runs automatically:
- **Every 6 hours** (at 00:00, 06:00, 12:00, 18:00 UTC)
- On **manual trigger** (see below)

### Manual Trigger

1. Go to **Actions** tab in your GitHub repository
2. Click **Update IPTV Playlist** workflow
3. Click **Run workflow**
4. Optionally enable **Validate stream URLs** for health checking
5. Click **Run workflow**

## 🛠️ Local Usage

You can also run the script locally:

### Basic update (no validation):
```bash
python3 scripts/update_playlist.py --playlist my --no-validate
```

### With URL validation (slower):
```bash
python3 scripts/update_playlist.py --playlist my --validate
```

### Custom upstream sources:
```bash
python3 scripts/update_playlist.py \
  --playlist my \
  --upstream \
    "https://example.com/playlist1.m3u" \
    "https://example.com/playlist2.m3u"
```

### Help:
```bash
python3 scripts/update_playlist.py --help
```

> **Note for macOS users:** Use `python3` instead of `python`

## ⚙️ Configuration Options

### URL Validation

**Enabled (--validate flag):**
- Checks if each stream URL is accessible
- Automatically switches to working alternatives when available
- Comments out unreachable URLs with `# disabled: unreachable`
- Tries all available alternatives before giving up
- Does NOT delete channels
- **Recommended for manual runs to fix broken links**

**Disabled (default for scheduled runs):**
- Updates URLs without checking accessibility
- Much faster execution (~10 seconds vs several minutes)
- Good for frequent automated updates

### Workflow Schedule

To change update frequency, edit `.github/workflows/update-playlist.yml`:

```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
  # Examples:
  # - cron: '0 */12 * * *'  # Every 12 hours
  # - cron: '0 0 * * *'     # Daily at midnight
  # - cron: '0 0 * * 0'     # Weekly on Sunday
```

[Learn cron syntax](https://crontab.guru/)

## 📊 Understanding the Output

### Script Output

```
============================================================
IPTV Playlist Updater
============================================================

Loading curated playlist: my
✓ Loaded 150 channels from curated playlist

=== Loading Upstream Playlists ===
Fetching: https://raw.githubusercontent.com/...
✓ Fetched 245678 bytes
Parsed 180 channels from upstream

✓ Total unique upstream channels: 180

=== Updating Channels ===
↻ Updating: Star Jalsha HD
  Old: http://old-url.com/stream...
  New: http://new-url.com/stream...
⊘ Skipping duplicate: Star Jalsha HD
⚠ Unreachable: BTV News

✓ Updated 5 channel URLs

=== Writing Playlist ===
✓ Written 150 channels to my

============================================================
✓ Update Complete - 5 URLs updated
============================================================
```

### GitHub Actions Summary

After each run, check the Actions tab for:
- ✅ Success/failure status
- 📝 Number of changes
- 📊 Commit details
- ⏱️ Execution time

## 🔍 Troubleshooting

### No changes detected
- Check if upstream sources have updated
- Verify channel names match between your playlist and upstream
- Check Actions logs for matching details

### Some channels not updating
- Ensure `tvg-id` or channel name matches upstream
- Check if upstream still has that channel
- Verify channel isn't commented in your playlist

### Workflow not running
- Check if Actions are enabled in repository settings
- Verify the workflow file is in `.github/workflows/`
- Check for syntax errors in YAML file

### Invalid M3U format errors
- The parser is defensive and handles most issues
- Check for malformed `#EXTINF` lines
- Ensure URLs are on separate lines after `#EXTINF`

## 📝 How Channels Are Matched

### Example 1: Match by tvg-id
```m3u
Your playlist:
#EXTINF:-1 tvg-id="star-jalsha" tvg-logo="..." group-title="Indian-Bangla",Star Jalsha HD
http://old-url.com/stream

Upstream:
#EXTINF:-1 tvg-id="star-jalsha",Star Jalsha
http://new-url.com/stream

Result: URL updated to http://new-url.com/stream
```

### Example 2: Match by name
```m3u
Your playlist:
#EXTINF:-1 tvg-logo="..." group-title="BANGLA",Jamuna TV
http://old-url.com/stream

Upstream:
#EXTINF:-1,Jamuna TV
http://new-url.com/stream

Result: URL updated to http://new-url.com/stream
```

### Example 3: No match found
```m3u
Your playlist:
#EXTINF:-1 group-title="BANGLA",My Custom Channel
http://my-url.com/stream

Upstream: (no matching channel)

Result: URL unchanged, channel preserved
```

## 🔒 Security & Privacy

- **No sensitive data:** Script uses standard library only
- **Read-only upstream access:** Only reads from upstream URLs
- **Safe commits:** Only commits to your own repository
- **Transparent:** All changes visible in commit history

## 📦 Dependencies

**None!** The script uses only Python standard library:
- `urllib` for HTTP requests
- `re` for regex parsing
- `dataclasses` for data structures

Works with **Python 3.7+** (GitHub Actions uses Python 3.11).

## 🤝 Contributing

Suggestions and improvements welcome! Feel free to:
- Open issues for bugs or feature requests
- Submit pull requests
- Share your configuration examples

## 📄 License

This is free and unencumbered software released into the public domain. Use it however you want!

## 🙏 Acknowledgments

- Upstream playlist providers
- GitHub Actions for free automation
- M3U format specification

---

**Questions?** Open an issue in the repository!

**Happy streaming! 📺✨**
