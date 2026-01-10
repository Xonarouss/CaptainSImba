# XonarousLIVE Discord Bot — v3 (hardcore admin + fun + streamer utilities)

## What's in v3
### Hardcore admin
- AutoMod:
  - deletes Discord invite links (configurable)
  - mention spam, caps spam, flood spam → auto-timeout + logs to #mod-log
- Moderation slash commands:
  - `/mod clear`, `/mod warn`, `/mod timeout`, `/mod kick`, `/mod ban`
- Mod logging to `#mod-log`

### Fun + leveling
- Automatic leveling from chatting:
  - `/rank`, `/leaderboard`
  - reward roles auto-created at set levels (see config.yaml -> leveling.reward_roles)
- Giveaway system (admins only):
  - `/giveaway start minutes winners prize [channel]`
  - `/giveaway end`

### Streamer utilities
- Twitch “go live” notification (optional, polling every 2 min):
  - posts in `#live-now`
  - requires TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET
- Social media notifications:
  - via **RSS/Atom feeds** (no API keys): `/feeds add|remove|list`
  - posts to `#announcements` when a feed changes (lightweight parser)

### Rotating bot status
- Rotates between custom funny statuses + aviation facts (config.yaml)

### Welcome messages
- Auto-welcome in `#welcome` (configurable message template)

## IMPORTANT
This bot reads message content for leveling + automod, so enable:
- Developer Portal -> Bot -> **Message Content Intent**
- **Server Members Intent** recommended

## Run (Windows)
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## Setup checklist
1) Copy `.env.example` -> `.env` and fill DISCORD_TOKEN (and optional GEMINI/Twitch).
2) Configure your server channels via `/rebuild` (keeps #rules).
3) Create or ensure channels: #rules (required), #welcome, #announcements, #live-now, #mod-log (rebuild creates most of these).
4) Test:
- `/rank` and chat a bit
- `/giveaway start 5 1 "Test prize"`
- Post an invite link to see automod (in a test server!)

## What I need from you for “social media auto posts”
Best/easiest approach is RSS:
- YouTube channel RSS
- Instagram/TikTok/Twitter are harder without paid APIs; if you have official API access, we can add it.

If you send me which platforms + links you want, I’ll wire the RSS list + polish posting formatting.

## Your feeds
Add these via `/feeds add` (admins only). Recommended:
- name: youtube, url: https://www.youtube.com/@xonarous
- name: twitch, url: https://twitchrss.com/feeds/?username=xonarouslive&feed=streams
- name: tiktok, url: https://rss.app/feeds/s5OW7gDkBfYwzBJ1.xml
- name: instagram, url: https://rss.app/feeds/ars3x3e7nKX6ATSb.xml
- name: x, url: https://rss.app/feeds/4W0lQm2W2jfCMLla.xml


### Feeds are preconfigured
Your RSS feeds are already included in `data/feeds.json`. The bot will post only on *new* items.


## Music (Voice) setup (Pure Python)

This bot uses **FFmpeg** + **yt-dlp** for voice music.

### FFmpeg on Windows (easy options)
Option A (recommended): install FFmpeg and add it to PATH so `ffmpeg -version` works.
Option B (portable): drop `ffmpeg.exe` into the **same folder as `bot.py`**.
You can also set `FFMPEG_PATH` in `.env` to an explicit path.

Example:
FFMPEG_PATH=C:\\ffmpeg\\bin\\ffmpeg.exe


Note: The music bot auto-disconnects after **3 minutes** of inactivity or if the voice channel stays empty for 3 minutes.


### YouTube note (yt-dlp)
Sometimes YouTube may require a browser verification ("Sign in to confirm you're not a bot").
If that happens:
- Use SoundCloud search: `/music play sc:artist song`
- Or play a SoundCloud URL / direct radio stream URL
- Optional (advanced): set `YTDLP_COOKIES` to a `cookies.txt` path on your host.
