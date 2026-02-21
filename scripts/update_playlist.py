#!/usr/bin/env python3
"""
IPTV Playlist Updater
Automatically updates M3U playlist URLs from upstream sources while preserving metadata
"""

import re
import sys
import urllib.request
import urllib.error
import ssl
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict


@dataclass
class Channel:
    """Represents a single channel entry in an M3U playlist"""
    extinf_line: str  # Full #EXTINF line with metadata
    url: str  # Stream URL
    tvg_id: str = ""
    tvg_name: str = ""
    tvg_logo: str = ""
    group_title: str = ""
    channel_name: str = ""  # Name after comma in EXTINF
    is_commented: bool = False
    raw_lines: List[str] = field(default_factory=list)  # Original lines including comments
    
    def __post_init__(self):
        """Extract metadata from EXTINF line"""
        if not self.extinf_line:
            return
            
        # Extract tvg-id
        tvg_id_match = re.search(r'tvg-id="([^"]*)"', self.extinf_line)
        if tvg_id_match:
            self.tvg_id = tvg_id_match.group(1)
        
        # Extract tvg-name
        tvg_name_match = re.search(r'tvg-name="([^"]*)"', self.extinf_line)
        if tvg_name_match:
            self.tvg_name = tvg_name_match.group(1)
        
        # Extract tvg-logo
        tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', self.extinf_line)
        if tvg_logo_match:
            self.tvg_logo = tvg_logo_match.group(1)
        
        # Extract group-title
        group_match = re.search(r'group-title="([^"]*)"', self.extinf_line)
        if group_match:
            self.group_title = group_match.group(1)
        
        # Extract channel name (text after last comma)
        if ',' in self.extinf_line:
            self.channel_name = self.extinf_line.split(',', 1)[1].strip()
    
    def get_match_key(self) -> str:
        """Return the key used for matching channels (tvg-id or normalized name)"""
        if self.tvg_id and self.tvg_id != "(no tvg-id)(m3u4u)":
            return f"id:{self.tvg_id}"
        # Normalize channel name for matching
        normalized = re.sub(r'\s+', ' ', self.channel_name.lower().strip())
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove special chars
        return f"name:{normalized}"
    
    def to_m3u_lines(self) -> List[str]:
        """Convert channel back to M3U format lines"""
        lines = []
        
        # Add any comment lines that came before this entry
        for line in self.raw_lines:
            if line.startswith('#') and not line.startswith('#EXTINF'):
                lines.append(line)
        
        # Add EXTINF line
        lines.append(self.extinf_line)
        
        # Add URL only if present
        if self.url:
            if self.is_commented:
                lines.append(f"#{self.url}")
            else:
                lines.append(self.url)
        
        return lines


class M3UParser:
    """Parse M3U playlist files with robust error handling"""
    
    @staticmethod
    def parse(content: str) -> List[Channel]:
        """Parse M3U content into Channel objects"""
        channels = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and M3U header
            if not line or line == '#EXTM3U':
                i += 1
                continue
            
            # Collect comment lines
            comment_lines = []
            while i < len(lines) and lines[i].strip().startswith('#') and not lines[i].strip().startswith('#EXTINF'):
                comment_lines.append(lines[i].strip())
                i += 1
            
            # Check if we have an EXTINF line
            if i < len(lines) and lines[i].strip().startswith('#EXTINF'):
                extinf_line = lines[i].strip()
                i += 1
                
                # Next non-empty, non-comment line should be the URL
                url = ""
                is_commented = False
                url_comment_lines = []
                
                while i < len(lines):
                    url_line = lines[i].strip()
                    
                    if not url_line:
                        # Empty line - might signal end of entry or just spacing
                        i += 1
                        # If we don't have a URL yet, continue looking
                        if not url:
                            continue
                        else:
                            # We have a URL, this empty line ends the entry
                            break
                    
                    # Check if it's a commented URL
                    if url_line.startswith('#http'):
                        if not url:  # Only take first URL
                            url = url_line[1:]  # Remove leading #
                            is_commented = True
                        else:
                            url_comment_lines.append(url_line)
                        i += 1
                    elif url_line.startswith('http'):
                        if not url:  # Only take first URL
                            url = url_line
                            is_commented = False
                        i += 1
                        break  # Active URL found, end of this channel
                    elif url_line.startswith('#EXTINF'):
                        # Next channel starting, don't consume this line
                        break
                    elif url_line.startswith('#'):
                        # Another comment
                        url_comment_lines.append(url_line)
                        i += 1
                    else:
                        # Unexpected content, skip
                        i += 1
                        break
                
                # Create channel even without URL to preserve metadata
                channel = Channel(
                    extinf_line=extinf_line,
                    url=url if url else "",
                    is_commented=is_commented if url else True,
                    raw_lines=comment_lines + url_comment_lines
                )
                channels.append(channel)
            else:
                i += 1
        
        return channels


class PlaylistUpdater:
    """Main class for updating playlists"""
    
    def __init__(self, curated_playlist_path: str, upstream_urls: List[str]):
        self.curated_playlist_path = curated_playlist_path
        self.upstream_urls = upstream_urls
        self.timeout = 10
    
    def fetch_url(self, url: str) -> Optional[str]:
        """Fetch content from a URL with error handling"""
        try:
            print(f"Fetching: {url}")
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (IPTV-Updater/1.0)'}
            )
            # Create SSL context that doesn't verify certificates (for macOS compatibility)
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=self.timeout, context=context) as response:
                content = response.read().decode('utf-8', errors='ignore')
                print(f"✓ Fetched {len(content)} bytes")
                return content
        except Exception as e:
            print(f"✗ Failed to fetch {url}: {e}")
            return None
    
    def validate_stream_url(self, url: str) -> bool:
        """Check if a stream URL is accessible"""
        if not url or url.startswith('#'):
            return False
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Try HEAD request first (faster)
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent', 'Mozilla/5.0 (IPTV-Updater/1.0)')
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                return response.status == 200
        except:
            try:
                # Try small GET request
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0 (IPTV-Updater/1.0)')
                req.add_header('Range', 'bytes=0-1024')
                with urllib.request.urlopen(req, timeout=5, context=context) as response:
                    return response.status in (200, 206)
            except:
                return False
    
    def load_curated_playlist(self) -> List[Channel]:
        """Load and parse the curated playlist"""
        print(f"\nLoading curated playlist: {self.curated_playlist_path}")
        try:
            with open(self.curated_playlist_path, 'r', encoding='utf-8') as f:
                content = f.read()
            channels = M3UParser.parse(content)
            print(f"✓ Loaded {len(channels)} channels from curated playlist")
            return channels
        except Exception as e:
            print(f"✗ Failed to load curated playlist: {e}")
            sys.exit(1)
    
    def load_upstream_channels(self) -> Dict[str, List[Channel]]:
        """Load all upstream playlists and create a lookup map with ALL matches"""
        print("\n=== Loading Upstream Playlists ===")
        upstream_map = {}  # key -> list of channels
        
        for url in self.upstream_urls:
            content = self.fetch_url(url)
            if not content:
                continue
            
            channels = M3UParser.parse(content)
            print(f"Parsed {len(channels)} channels from upstream")
            
            # Add to map (collect ALL matches, not just latest)
            for channel in channels:
                if not channel.url:  # Skip channels without URLs
                    continue
                key = channel.get_match_key()
                if key not in upstream_map:
                    upstream_map[key] = []
                upstream_map[key].append(channel)
        
        total_channels = sum(len(v) for v in upstream_map.values())
        print(f"\n✓ Total upstream channel entries: {total_channels} ({len(upstream_map)} unique names)")
        return upstream_map
    
    def update_channels(self, curated_channels: List[Channel], 
                       upstream_map: Dict[str, List[Channel]], 
                       validate_urls: bool = False) -> Tuple[List[Channel], int]:
        """Update curated channels with upstream URLs"""
        print("\n=== Updating Channels ===")
        updated_count = 0
        added_count = 0
        backup_added_count = 0
        updated_channels = []
        
        # Track seen keys to remove duplicates (keep first occurrence)
        seen_keys = set()
        
        # Track which channels we've added backups for
        channels_with_backups = set()
        
        for channel in curated_channels:
            key = channel.get_match_key()
            
            # Skip if duplicate (already seen this channel)
            if key in seen_keys:
                print(f"⊘ Skipping duplicate: {channel.channel_name}")
                continue
            seen_keys.add(key)
            
            # Check if this is a backup channel (has "Backup", "-[2]", "(2)", etc. in name)
            is_backup = any(marker in channel.channel_name for marker in ['Backup', '-[2]', '-[3]', '(2)', '(3)', ' 2'])
            if is_backup:
                channels_with_backups.add(key)
            
            # Try to find upstream match
            if key in upstream_map:
                upstream_channels = upstream_map[key]
                
                # Find best URL (first working one if validating, otherwise first one)
                best_upstream = None
                if validate_urls:
                    # Try to find a working URL
                    for upstream_channel in upstream_channels:
                        if self.validate_stream_url(upstream_channel.url):
                            best_upstream = upstream_channel
                            break
                    if not best_upstream and upstream_channels:
                        # No working URL found, use first one anyway
                        best_upstream = upstream_channels[0]
                else:
                    # No validation, just use first alternative
                    best_upstream = upstream_channels[0] if upstream_channels else None
                
                if not best_upstream:
                    continue
                
                # If channel has no URL, try to add from upstream
                if not channel.url or channel.url == "":
                    print(f"✓ Adding URL: {channel.channel_name}")
                    print(f"  New: {best_upstream.url[:80] if len(best_upstream.url) > 80 else best_upstream.url}")
                    if len(upstream_channels) > 1:
                        print(f"  ({len(upstream_channels)} alternatives available)")
                    channel.url = best_upstream.url
                    channel.is_commented = False
                    added_count += 1
                # Update if URL is different and channel is not manually commented
                elif channel.url != best_upstream.url:
                    if not channel.is_commented:
                        print(f"↻ Updating: {channel.channel_name}")
                        print(f"  Old: {channel.url[:80]}...")
                        print(f"  New: {best_upstream.url[:80]}...")
                        if len(upstream_channels) > 1:
                            print(f"  ({len(upstream_channels)} alternatives available)")
                        channel.url = best_upstream.url
                        channel.is_commented = False  # Re-enable if was disabled
                        updated_count += 1
                    else:
                        print(f"⊘ Keeping (manually disabled): {channel.channel_name}")
            else:
                # No upstream match
                if not channel.url or channel.url == "":
                    print(f"⊘ Waiting for source: {channel.channel_name}")
                elif channel.is_commented:
                    print(f"⊘ Keeping (manually disabled): {channel.channel_name}")
                else:
                    print(f"ℹ No upstream match: {channel.channel_name}")
            
            # Validate URL if requested (only for channels with active URLs)
            if validate_urls and channel.url and not channel.is_commented:
                if not self.validate_stream_url(channel.url):
                    print(f"⚠ Unreachable: {channel.channel_name}")
                    # Try to find a working alternative from upstream
                    if key in upstream_map and len(upstream_map[key]) > 1:
                        print(f"  Trying {len(upstream_map[key])-1} alternative(s)...")
                        for alt_idx, upstream_channel in enumerate(upstream_map[key][1:], 1):
                            print(f"    [{alt_idx}] Testing: {upstream_channel.url[:60]}...")
                            if self.validate_stream_url(upstream_channel.url):
                                print(f"    ✓ Found working alternative!")
                                channel.url = upstream_channel.url
                                channel.is_commented = False
                                updated_count += 1
                                break
                        else:
                            # No working alternative found
                            print(f"    ✗ No working alternatives found")
                            channel.is_commented = True
                            channel.url += " # disabled: unreachable"
                    else:
                        channel.is_commented = True
                        channel.url += " # disabled: unreachable"
            
            # Always keep the channel
            updated_channels.append(channel)
            
            # Auto-create backup channels if multiple alternatives exist and no backups yet
            if not is_backup and key in upstream_map and len(upstream_map[key]) > 1:
                # Check if we already have backup channels for this
                base_name = channel.channel_name
                existing_backups = [c for c in curated_channels if base_name in c.channel_name and c.channel_name != base_name]
                
                # Only create backups if we don't have any yet and there are good alternatives
                if len(existing_backups) == 0 and len(upstream_map[key]) >= 2:
                    # Add one backup channel (using second alternative)
                    backup_channel = Channel(
                        extinf_line=channel.extinf_line.replace(f',{base_name}', f',{base_name} (Backup)'),
                        url=upstream_map[key][1].url,
                        is_commented=False,
                        raw_lines=[]
                    )
                    print(f"  ➕ Adding backup: {base_name} (Backup)")
                    print(f"     URL: {backup_channel.url[:70]}...")
                    updated_channels.append(backup_channel)
                    backup_added_count += 1
        
        print(f"\n✓ Kept {len(updated_channels)} channels ({added_count} URLs added, {updated_count} URLs updated, {backup_added_count} backups created)")
        return updated_channels, updated_count + added_count + backup_added_count
    
    def write_playlist(self, channels: List[Channel], output_path: str):
        """Write channels back to M3U file"""
        print(f"\n=== Writing Playlist ===")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                
                for channel in channels:
                    lines = channel.to_m3u_lines()
                    for line in lines:
                        f.write(line + '\n')
                    f.write('\n')  # Blank line between entries
            
            print(f"✓ Written {len(channels)} channels to {output_path}")
        except Exception as e:
            print(f"✗ Failed to write playlist: {e}")
            sys.exit(1)
    
    def run(self, validate_urls: bool = False) -> bool:
        """Run the complete update process"""
        print("=" * 60)
        print("IPTV Playlist Updater")
        print("=" * 60)
        
        # Load curated playlist
        curated_channels = self.load_curated_playlist()
        
        # Load upstream channels
        upstream_map = self.load_upstream_channels()
        
        # Update channels
        updated_channels, update_count = self.update_channels(
            curated_channels, 
            upstream_map, 
            validate_urls
        )
        
        # Write updated playlist
        self.write_playlist(updated_channels, self.curated_playlist_path)
        
        print("\n" + "=" * 60)
        print(f"✓ Update Complete - {update_count} URLs updated")
        print("=" * 60)
        
        return update_count > 0


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Update IPTV playlist from upstream sources'
    )
    parser.add_argument(
        '--playlist',
        default='my',
        help='Path to curated playlist file (default: my)'
    )
    parser.add_argument(
        '--upstream',
        nargs='+',
        default=[
            'https://raw.githubusercontent.com/sydul104/main04/refs/heads/main/my',
            'https://raw.githubusercontent.com/musfiqeee/iptv-m3u-bot/main/output/all.m3u'
        ],
        help='Upstream playlist URLs'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate stream URLs (slower but recommended)'
    )
    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip URL validation (faster)'
    )
    
    args = parser.parse_args()
    
    # Determine validation setting
    validate = args.validate
    if args.no_validate:
        validate = False
    
    # Run updater
    updater = PlaylistUpdater(args.playlist, args.upstream)
    has_changes = updater.run(validate_urls=validate)
    
    # Exit code: 0 if changes made, 1 if no changes
    sys.exit(0 if has_changes else 1)


if __name__ == '__main__':
    main()
