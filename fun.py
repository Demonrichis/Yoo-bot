# ======================================================================================================================
# IMPORTS
# ======================================================================================================================
import asyncio
import aiohttp
import discord
import re
import random
import time
import json
import os
from typing import List, Optional, Tuple, Dict, Any

# ======================================================================================================================
# CLIENT-SIDE NOTES
# ======================================================================================================================
# This module exposes `handle_message_event(message)` which your main bot should call.
# It intentionally does NOT call client.run() to keep integration flexible.
#
# Example in bot.py:
#   import discord
#   from fun import handle_message_event
#
#   client = discord.Client(intents=discord.Intents.default())
#
#   @client.event
#   async def on_ready():
#       print("Bot ready")
#
#   @client.event
#   async def on_message(message):
#       await handle_message_event(message)
#
#   client.run(TOKEN)
#
# ======================================================================================================================
# GLOBAL DATA STRUCTURES
# ======================================================================================================================

# cooldown store: {(user_id, action): last_timestamp}
_COOLDOWNS: Dict[Tuple[int, str], float] = {}

# per-guild recent GIF list to avoid immediate repeats
_RECENT_GIFS: Dict[str, List[str]] = {}  # key is str(guild_id) -> list of gif urls most recent first

# embed pastel color per action mapping can be customized below
ACTION_COLORS: Dict[str, int] = {}

# small in-memory Tenor cache to reduce repeated API calls {query: (ts, [urls])}
_TENOR_CACHE: Dict[str, Tuple[float, List[str]]] = {}
CACHE_TTL = 60 * 5  # 5 minutes cache TTL

# lock for store persistence (if we add any small disk store later)
_STORE_LOCK = asyncio.Lock()

# ======================================================================================================================
# ACTION DEFINITIONS
# ======================================================================================================================
# Primary action list (we will provide many actions; the user asked for many)
ACTIONS = [
    "hug", "slap", "pat", "kiss", "cuddle", "boop", "highfive", "poke", "bite", "tickle",
    "punch", "kick", "dance", "cry", "blush", "wave", "bonk", "stare", "laugh", "smug",
    "sleep", "holdhands", "feed", "throw", "run", "scared", "comfort", "tease"
]

# Reaction emojis mapping per action for after-send flair
ACTION_REACTIONS: Dict[str, List[str]] = {
    "hug": ["�", "💞"],
    "slap": ["😲", "👋"],
    "pat": ["😊", "🤏"],
    "kiss": ["😘", "💋"],
    "cuddle": ["🥰", "�"],
    "boop": ["👉", "👈"],
    "highfive": ["🙌", "✋"],
    "poke": ["😛", "👉"],
    "bite": ["😈", "🦴"],
    "tickle": ["😂", "🤣"],
    "punch": ["💥", "👊"],
    "kick": ["🥾", "👟"],
    "dance": ["🕺", "💃"],
    "cry": ["😢", "💧"],
    "blush": ["😊", "😳"],
    "wave": ["👋", "🤙"],
    "bonk": ["🔨", "😵"],
    "stare": ["👀", "�"],
    "laugh": ["😆", "🤣"],
    "smug": ["😏", "😼"],
    "sleep": ["😴", "🛌"],
    "holdhands": ["🤝", "♥️"],
    "feed": ["🍪", "🍰"],
    "throw": ["🎯", "💨"],
    "run": ["🏃", "💨"],
    "scared": ["😱", "😨"],
    "comfort": ["🤗", "🫂"],
    "tease": ["😝", "😜"]
}

# pastel colors per action for nicer embeds
for i, action in enumerate(ACTIONS):
    ACTION_COLORS[action] = PASTEL_COLORS[i % len(PASTEL_COLORS)]

# cute suffixes to add Owo flavor
CUTE_SUFFIXES = [
    "uwu", "owo", "nya~", ">w<", ".w.", "^_^", "♥", "💖", "✨", "｡◕‿◕｡",
    "owo~", "♡", "🌸", "�", "💫", "♥️"
]

# ======================================================================================================================
# FALLBACK GIF DICTIONARY
# ======================================================================================================================
# Each action must contain at least 10 links. These are curated anime-style GIF links from public giphy/gif hosts.
# If you want to replace links with Tenor equivalents, feel free to update this list.
# Note: avoid posting copyrighted content in public repos. Keep keys private.
FALLBACK_GIFS: Dict[str, List[str]] = {
    "hug": [
        "https://media.giphy.com/media/l2QDM9Jnim1YVILXa/giphy.gif",
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
        "https://media.giphy.com/media/143v0Z4767T15e/giphy.gif",
        "https://media.giphy.com/media/sUIZWMnfd4Mb6/giphy.gif",
        "https://media.giphy.com/media/3o6Zt8MgUuvSbkZYWc/giphy.gif",
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
        "https://media.giphy.com/media/49mdjsMrH7oze/giphy.gif",
        "https://media.giphy.com/media/5eyhBKLvYhafu/giphy.gif",
        "https://media.giphy.com/media/xT9IgG50Fb7Mi0prBC/giphy.gif",
        "https://media.giphy.com/media/13YrHUvPzUUmkM/giphy.gif"
    ],
    "slap": [
        "https://media.giphy.com/media/Gf3AUz3eBNbTW/giphy.gif",
        "https://media.giphy.com/media/jLeyZWgtwgr2U/giphy.gif",
        "https://media.giphy.com/media/Zau0yrl17uzdK/giphy.gif",
        "https://media.giphy.com/media/11rWoZNpAKw8w/giphy.gif",
        "https://media.giphy.com/media/3o6Mbbs879ozZ9Yic0/giphy.gif",
        "https://media.giphy.com/media/fO6UtDy5pWYwM/giphy.gif",
        "https://media.giphy.com/media/3ohzdIuqJoo8QdKlnW/giphy.gif",
        "https://media.giphy.com/media/LmNwrBhejkK9EFP504/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "pat": [
        "https://media.giphy.com/media/109ltuoSQT212w/giphy.gif",
        "https://media.giphy.com/media/4HP0ddZnNVvKU/giphy.gif",
        "https://media.giphy.com/media/osYdfUptPqV0s/giphy.gif",
        "https://media.giphy.com/media/ArLxZ4PebH2Ug/giphy.gif",
        "https://media.giphy.com/media/ye7OTQgwmVuVy/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/l3vR6D5Q4Z8d2/giphy.gif",
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif"
    ],
    "kiss": [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/FqBTvSNjNzeZG/giphy.gif",
        "https://media.giphy.com/media/bGm9FuBCGg4SY/giphy.gif",
        "https://media.giphy.com/media/11k3oaUjSlFR4I/giphy.gif",
        "https://media.giphy.com/media/l41lQ2UaJ7y2K/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
        "https://media.giphy.com/media/Z1kpfgtHmpR8k/giphy.gif",
        "https://media.giphy.com/media/5b8I6Z9z0b5iQ/giphy.gif",
        "https://media.giphy.com/media/3ohhwytHcusSCXXOUg/giphy.gif",
        "https://media.giphy.com/media/8q0JH2Qh3Vf0k/giphy.gif"
    ],
    "cuddle": [
        "https://media.giphy.com/media/3oriO0OEd9QIDdllqo/giphy.gif",
        "https://media.giphy.com/media/3Z1Yj0iXySA2o/giphy.gif",
        "https://media.giphy.com/media/13YrHUvPzUUmkM/giphy.gif",
        "https://media.giphy.com/media/QGc8RgR0J5Na/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif",
        "https://media.giphy.com/media/1BXa2alBjrCXC/giphy.gif"
    ],
    "boop": [
        "https://media.giphy.com/media/3oriO0OEd9QIDdllqo/giphy.gif",
        "https://media.giphy.com/media/111ebonMs90YLu/giphy.gif",
        "https://media.giphy.com/media/12hvLuZ7uzvCvK/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif",
        "https://media.giphy.com/media/yoJC2Olx0ekMy2b8bW/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/3ornjXbo3g39Ljjgso/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif"
    ],
    "highfive": [
        "https://media.giphy.com/media/3o6ZtpxSZbQRRnwCKQ/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/xT0Gqd2hM4bCj3Q3D6/giphy.gif",
        "https://media.giphy.com/media/3o7TKx3S1KMK1nXyLe/giphy.gif",
        "https://media.giphy.com/media/l0Ex7FJwX9G0qS3a0/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/3o6Zs4p0o6gqg/giphy.gif",
        "https://media.giphy.com/media/1BXa2alBjrCXC/giphy.gif"
    ],
    "poke": [
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/ZqlvCTNHpqrio/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/26u4b45b8KlgAB7iM/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ],
    "bite": [
        "https://media.giphy.com/media/11rWoZNpAKw8w/giphy.gif",
        "https://media.giphy.com/media/KI9oNS4JBemyI/giphy.gif",
        "https://media.giphy.com/media/10UeedrT5MIfPG/giphy.gif",
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3o7btPfuT1ewy8vCAk/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ],
    "tickle": [
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
        "https://media.giphy.com/media/xTiTnBoR36Gzkhp9bG/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif",
        "https://media.giphy.com/media/26u4b45b8KlgAB7iM/giphy.gif",
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif"
    ],
    "punch": [
        "https://media.giphy.com/media/l3q2K5jinAlChoCLS/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/3o6Zt8MgUuvSbkZYWc/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/LmNwrBhejkK9EFP504/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif"
    ],
    "kick": [
        "https://media.giphy.com/media/TgKEpC5NdGvIY/giphy.gif",
        "https://media.giphy.com/media/hvRJCLFzcasrR4ia7z/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/xTiTnJ2m2k0bVb3Gx6/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif"
    ],
    "dance": [
        "https://media.giphy.com/media/3oriO7A7bt1wsEP4cw/giphy.gif",
        "https://media.giphy.com/media/l41YtZOb9EUABnuqA/giphy.gif",
        "https://media.giphy.com/media/5PhDdJfLt4FXe/giphy.gif",
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif"
    ],
    "cry": [
        "https://media.giphy.com/media/d2lcHJTG5Tscg/giphy.gif",
        "https://media.giphy.com/media/ROF8OQvDmxytW/giphy.gif",
        "https://media.giphy.com/media/26gssIytJvy1b1THO/giphy.gif",
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif"
    ],
    "blush": [
        "https://media.giphy.com/media/xUOwGqzY13pWf6I1vi/giphy.gif",
        "https://media.giphy.com/media/fQZX2aoRC1Tqw/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/5PhDdJfLt4FXe/giphy.gif",
        "https://media.giphy.com/media/13YrHUvPzUUmkM/giphy.gif",
        "https://media.giphy.com/media/3o6Zt8MgUuvSbkZYWc/giphy.gif"
    ],
    "wave": [
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif",
        "https://media.giphy.com/media/2YbG2d4pXQGXS/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "bonk": [
        "https://media.giphy.com/media/j3iGKfXRKlLqw/giphy.gif",
        "https://media.giphy.com/media/MWSRkVoNaC30A/giphy.gif",
        "https://media.giphy.com/media/26gssIytJvy1b1THO/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/3o6Zt8MgUuvSbkZYWc/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif"
    ],
    "stare": [
        "https://media.giphy.com/media/XreQmk7ETCak0/giphy.gif",
        "https://media.giphy.com/media/3o7btYFgbkD2MPkzVu/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif"
    ],
    "laugh": [
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/3o7btPfuT1ewy8vCAk/giphy.gif",
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif"
    ],
    "smug": [
        "https://media.giphy.com/media/3o7btNR05vVYlfaU6Y/giphy.gif",
        "https://media.giphy.com/media/VbnUQpnihPSIgIXuZv/giphy.gif",
        "https://media.giphy.com/media/1BXa2alBjrCXC/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "sleep": [
        "https://media.giphy.com/media/fnlXXGImVWB0RYWWQj/giphy.gif",
        "https://media.giphy.com/media/3o7TKsQj4X3cJpGRNm/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "holdhands": [
        "https://media.giphy.com/media/l0MYB8Ory7Hqefo9a/giphy.gif",
        "https://media.giphy.com/media/VbnUQpnihPSIgIXuZv/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "feed": [
        "https://media.giphy.com/media/26uflHj8UQ33JmUqA/giphy.gif",
        "https://media.giphy.com/media/10UeedrT5MIfPG/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ],
    "throw": [
        "https://media.giphy.com/media/13CoXDiaCcCoyk/giphy.gif",
        "https://media.giphy.com/media/3o7TKx3S1KMK1nXyLe/giphy.gif",
        "https://media.giphy.com/media/26gssIytJvy1b1THO/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "run": [
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/3o6ZsX2w6n2CE3Y8VW/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ],
    "scared": [
        "https://media.giphy.com/media/XpgOZHuDfIkoM/giphy.gif",
        "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",
        "https://media.giphy.com/media/26gssIytJvy1b1THO/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif"
    ],
    "comfort": [
        "https://media.giphy.com/media/49mdjsMrH7oze/giphy.gif",
        "https://media.giphy.com/media/13YrHUvPzUUmkM/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/3ornk57KwDXf81rjWM/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ],
    "tease": [
        "https://media.giphy.com/media/xT1XGYy9NPhWRPp6uA/giphy.gif",
        "https://media.giphy.com/media/3o7btYFgbkD2MPkzVu/giphy.gif",
        "https://media.giphy.com/media/3o7qDXK7zK6pt5Q9hW/giphy.gif",
        "https://media.giphy.com/media/26u4b45b8KlgAB7iM/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
    ]
}

# ======================================================================================================================
# VALIDATION: ensure every action has at least 10 gifs; if not, pad with generic gifs
# ======================================================================================================================
for action in ACTIONS:
    arr = FALLBACK_GIFS.get(action, [])
    # ensure uniqueness
    uniq = []
    for u in arr:
        if u and u not in uniq:
            uniq.append(u)
    # pad to at least 10 using GENERIC_FALLBACK_GIFS
    i = 0
    while len(uniq) < 10 and i < len(GENERIC_FALLBACK_GIFS):
        candidate = GENERIC_FALLBACK_GIFS[i]
        if candidate not in uniq:
            uniq.append(candidate)
        i += 1
    FALLBACK_GIFS[action] = uniq[:max(10, len(uniq))]

# ======================================================================================================================
# REGEX FOR PARSING MESSAGES
# ======================================================================================================================
# Support forms:
#   dso hug@user
#   dso hug @user
#   hug@user
#   hug @user
#   dso F.C (help)
# We'll use robust regex to capture target tokens, including mention form <@!12345> and raw id.
ACTION_PATTERN_NO_SPACE = re.compile(
    rf"(?P<prefix>dso\s+)?(?P<action>{'|'.join(re.escape(a) for a in ACTIONS)})@(?P<target><@!?\d+>|\d+|[^\s]+)",
    re.IGNORECASE
)
ACTION_PATTERN_SPACE = re.compile(
    rf"(?P<prefix>dso\s+)?(?P<action>{'|'.join(re.escape(a) for a in ACTIONS)})\s+(?P<target><@!?\d+>|\d+|[^\s]+)",
    re.IGNORECASE
)
HELP_PATTERN = re.compile(r"^dso\s+f\.?c\.?$", re.IGNORECASE)  # matches dso F.C or dso fc or dso f.c

MENTION_RE = re.compile(r"<@!?(?P<id>\d+)>")

# ======================================================================================================================
# UTILITIES
# ======================================================================================================================

def now_ts() -> float:
    return time.time()

def get_cooldown_remaining(user_id: int, action: str) -> float:
    key = (user_id, action)
    last = _COOLDOWNS.get(key, 0.0)
    elapsed = now_ts() - last
    if elapsed < COOLDOWN_SECONDS:
        return COOLDOWN_SECONDS - elapsed
    return 0.0

def set_cooldown(user_id: int, action: str) -> None:
    _COOLDOWNS[(user_id, action)] = now_ts()

def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def owoify_caption(caption: str) -> str:
    caption = compact(caption or "")
    lower = caption.lower()
    for token in ("uwu", "owo", "nya", "♥", "💖", "✨"):
        if token in lower:
            return caption
    r = random.random()
    if r < 0.35:
        caption = f"{caption} {random.choice(CUTE_SUFFIXES)}"
    elif r < 0.65:
        caption = f"{caption} ❤️"
    if len(caption) > 280:
        caption = caption[:277] + "..."
    return caption

def build_header_line(author_name: str, action: str, target_name: str) -> str:
    endings = ["", ".-.", ">w<", ".w.", " owo", " uwu", " ^_^", " ._.", "-.-"]
    end = random.choice(endings)
    header = f"{author_name} {action}s {target_name} {end}"
    return compact(header)

def add_recent_gif(guild_id: int, gif_url: str) -> None:
    key = str(guild_id)
    arr = _RECENT_GIFS.get(key, [])
    if gif_url in arr:
        arr.remove(gif_url)
    arr.insert(0, gif_url)
    if len(arr) > RECENT_GIF_RETENTION:
        arr = arr[:RECENT_GIF_RETENTION]
    _RECENT_GIFS[key] = arr

def get_recent_gifs(guild_id: int) -> List[str]:
    return _RECENT_GIFS.get(str(guild_id), [])

# ======================================================================================================================
# TENOR CACHING & FETCHING (optional, used only if TENOR_API_KEY is set)
# ======================================================================================================================

def tenor_cache_get(query: str) -> Optional[List[str]]:
    ent = _TENOR_CACHE.get(query)
    if not ent:
        return None
    ts, urls = ent
    if now_ts() - ts > CACHE_TTL:
        _TENOR_CACHE.pop(query, None)
        return None
    return list(urls)

def tenor_cache_set(query: str, urls: List[str]) -> None:
    _TENOR_CACHE[query] = (now_ts(), list(urls)[:MAX_GIF_CANDIDATES])

async def fetch_tenor_gifs_async(query: str, limit: int = TENOR_REQUEST_LIMIT) -> List[str]:
    """
    Fetch gif URLs from Tenor v2 API using TENOR_API_KEY.
    If TENOR_API_KEY is empty, returns empty list.
    """
    if not TENOR_API_KEY:
        return []
    cached = tenor_cache_get(query)
    if cached:
        return cached
    params = {
        "q": query,
        "key": TENOR_API_KEY,
        "limit": limit,
        "media_filter": "minimal"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params, timeout=HTTP_TIMEOUT) as resp:
                if resp.status != 200:
                    try:
                        body = await resp.text()
                    except Exception:
                        body = "<no body>"
                    # Do not raise; return empty to fall back to local gifs
                    return []
                data = await resp.json()
                results = data.get("results", []) or []
                urls = []
                for r in results:
                    media = r.get("media_formats", {}) or r.get("media", {})
                    if isinstance(media, dict):
                        for k in ("gif", "mediumgif", "tinygif", "nanogif"):
                            entry = media.get(k)
                            if isinstance(entry, dict):
                                url = entry.get("url")
                                if url:
                                    urls.append(url)
                                    break
                    # fallback try to find any http string
                    if not urls:
                        for v in r.values():
                            if isinstance(v, str) and v.startswith("http"):
                                urls.append(v)
                                break
                # dedupe and trim
                uniq = []
                for u in urls:
                    if u and u not in uniq:
                        uniq.append(u)
                    if len(uniq) >= limit:
                        break
                tenor_cache_set(query, uniq)
                return uniq
    except Exception:
        return []

# ======================================================================================================================
# LOCAL CAPTION TEMPLATES (per action)
# ======================================================================================================================
# Each action has a list of caption templates. Placeholders:
#   {author} -> author display name
#   {target} -> target display name
# The engine will choose one randomly and format it.
CAPTION_TEMPLATES: Dict[str, List[str]] = {
    "hug": [
        "{author} gives {target} the warmest hug ever.",
        "{author} hugs {target} tightly, like a cozy blanket.",
        "{author} wraps {target} in a giant fluffy hug uwu.",
        "{author} hugs {target} softly — so cute!",
        "{author} snuggles {target} warmly {suffix}",
        "{author} holds {target} close and hums a tiny tune.",
        "{author} hugs {target} like there’s no tomorrow.",
        "{author} gives {target} a comforting squeeze {suffix}",
        "{author} embraces {target} with all the love they have.",
        "{author} hugs {target} till the stars come out."
    ],
    "slap": [
        "{author} slaps {target} — dramatic anime style!",
        "{author} gives {target} a light, comedic slap.",
        "{author} slaps {target} across the face — ouch!",
        "{author} executes an epic slap move on {target} {suffix}",
        "{author} lightly slaps {target} — it's just a prank!",
        "{author} delivers a swift anime-style slap to {target}.",
        "{author} slaps {target} and everybody gasps.",
        "{author} slaps {target} gently (not too hard).",
        "{author} performs the legendary slap technique on {target}.",
        "{author} slaps {target} with dramatic sound effects!"
    ],
    "pat": [
        "{author} pats {target} on the head gently.",
        "{author} gives {target} a reassuring pat.",
        "{author} pats {target} — good job!",
        "{author} pats {target} like a proud mentor {suffix}",
        "{author} does a tiny pat for {target}.",
        "{author} pats {target} softly, squeak.",
        "{author} pats {target} with approval.",
        "{author} gives {target} the sweetest little pat.",
        "{author} pats {target} — so wholesome.",
        "{author} gives a gentle pat to {target}."
    ],
    "kiss": [
        "{author} gives {target} a gentle kiss.",
        "{author} kisses {target} softly {suffix}",
        "{author} pecks {target} on the cheek.",
        "{author} steals a kiss from {target}!",
        "{author} gives {target} a cute smooch.",
        "{author} kisses {target} under the stars.",
        "{author} gives {target} a cinematic anime kiss.",
        "{author} kisses {target} gently and blushes.",
        "{author} catches {target} by surprise with a sweet kiss.",
        "{author} pecks {target} and grins."
    ],
    "cuddle": [
        "{author} cuddles {target} like two marshmallows.",
        "{author} cuddles {target} on the couch {suffix}",
        "{author} invites {target} for a cozy cuddle session.",
        "{author} and {target} cuddle and watch anime.",
        "{author} snuggles {target} warmly.",
        "{author} cuddles {target} while humming softly.",
        "{author} cuddles {target} until sleep.",
        "{author} holds {target} close for a long cuddle.",
        "{author} wraps {target} in warm cuddles.",
        "{author} gives {target} the ultimate cuddle."
    ],
    "boop": [
        "{author} boops {target} on the nose {suffix}",
        "{author} gives {target} an adorable boop.",
        "{author} boops {target} — squeak!",
        "{author} gently boops {target}'s nose.",
        "{author} boops {target} with tiny fingers.",
        "{author} executes a perfect nose-boop on {target}.",
        "{author} boops {target} and everything is good.",
        "{author} performs the infamous boop on {target}.",
        "{author} gives {target} a playful boop.",
        "{author} boops {target} and giggles."
    ],
    "highfive": [
        "{author} high-fives {target} — bam!",
        "{author} gives {target} a celebratory highfive {suffix}",
        "{author} high-five for {target} — nice!",
        "{author} slaps hands with {target} in excitement.",
        "{author} and {target} high-five like champs.",
        "{author} high-fives {target} to celebrate.",
        "{author} gives {target} a big high-five.",
        "{author} high-fives {target} energetically.",
        "{author} high-fives {target} with style.",
        "{author} shares a victory highfive with {target}."
    ],
    "poke": [
        "{author} pokes {target} — hey!",
        "{author} gives {target} a tiny poke.",
        "{author} pokes {target} to get attention.",
        "{author} pokes {target} gently {suffix}",
        "{author} pokes {target} and waits.",
        "{author} pokes {target} playfully.",
        "{author} gives {target} a curious poke.",
        "{author} pokes {target} with a feather.",
        "{author} pokes {target} — nothing happens.",
        "{author} pokes {target} again."
    ],
    "bite": [
        "{author} playfully bites {target} {suffix}",
        "{author} gives {target} a tiny nibble.",
        "{author} bites {target} gently like a puppy.",
        "{author} gives {target} a dramatic chomp!",
        "{author} play-bites {target} affectionately.",
        "{author} bites {target} but it's just love.",
        "{author} gives {target} a friendly little bite.",
        "{author} bites {target} and blushes.",
        "{author} gives {target} a soft bite.",
        "{author} attempts a gentle bite on {target}."
    ],
    "tickle": [
        "{author} tickles {target} until they laugh.",
        "{author} tickles {target} mercilessly {suffix}",
        "{author} tickles {target} and both giggle.",
        "{author} tickles {target} — squeals!",
        "{author} tickles {target} playfully.",
        "{author} tickles {target} to cheer them up.",
        "{author} tickles {target} and then hugs them.",
        "{author} tickles {target} softly.",
        "{author} tickles {target} — can't stop laughing.",
        "{author} tickles {target} with delight."
    ],
    "punch": [
        "{author} lands a dramatic punch on {target}!",
        "{author} throws a swift punch at {target}.",
        "{author} punches {target} — anime impact!",
        "{author} gives {target} a playful punch {suffix}",
        "{author} punches {target} with exaggerated force.",
        "{author} lands a heroic punch on {target}.",
        "{author} punches {target} and time slows down.",
        "{author} punches {target} with style.",
        "{author} delivers a quick jab to {target}.",
        "{author} punches {target} dramatically."
    ],
    "kick": [
        "{author} kicks {target} with a flying move!",
        "{author} performs a swift kick on {target}.",
        "{author} kicks {target} — cinematic style!",
        "{author} gives {target} a playful kick {suffix}",
        "{author} kicks {target} and dust flies.",
        "{author} lands a neat kick on {target}.",
        "{author} kicks {target} like a pro.",
        "{author} does a spin-kick on {target}.",
        "{author} gives {target} a friendly kick.",
        "{author} kicks {target} in a dramatic pose."
    ],
    "dance": [
        "{author} dances with {target} joyfully.",
        "{author} pulls {target} into a dance-off {suffix}",
        "{author} and {target} break into synchronized dancing.",
        "{author} shows off moves while dancing with {target}.",
        "{author} dances with {target} like no one's watching.",
        "{author} dances happily with {target}.",
        "{author} invites {target} to a silly dance.",
        "{author} dances with {target} under neon lights.",
        "{author} dances with {target} and smiles.",
        "{author} grooves with {target} to the beat."
    ],
    "cry": [
        "{author} cries with {target} comforting them.",
        "{author} sheds a tear while {target} offers comfort.",
        "{author} cries dramatically (in a cute way).",
        "{author} cries and {target} hands a tissue {suffix}",
        "{author} cries softly while {target} watches.",
        "{author} cries a little and takes a breath.",
        "{author} cries but feels better next to {target}.",
        "{author} cries and {target} gives a hug.",
        "{author} cries but finds hope with {target}.",
        "{author} cries and then laughs it off."
    ],
    "blush": [
        "{author} blushes at {target}'s compliment {suffix}",
        "{author} turns bright red and hides behind a hand.",
        "{author} blushes while {target} grins.",
        "{author} blushes awkwardly but it's cute.",
        "{author} blushes and smiles shyly.",
        "{author} blushes a little seeing {target}.",
        "{author} blushes and looks away coyly.",
        "{author} blushes in an adorable way.",
        "{author} blushes while holding {target}'s hand.",
        "{author} blushes and giggles softly."
    ],
    "wave": [
        "{author} waves at {target} enthusiastically.",
        "{author} gives {target} a friendly wave {suffix}",
        "{author} waves with a big smile.",
        "{author} waves slowly and cutely.",
        "{author} waves from across the room.",
        "{author} waves to catch {target}'s attention.",
        "{author} waves and says hello.",
        "{author} waves with both hands.",
        "{author} waves shyly at {target}.",
        "{author} waves cheerfully."
    ],
    "bonk": [
        "{author} bonks {target} lightly on the head {suffix}",
        "{author} executes a comedic bonk on {target}.",
        "{author} bonks {target} with a soft toy.",
        "{author} bonks {target} — meme style.",
        "{author} bonks {target} for being silly.",
        "{author} gives {target} a playful bonk.",
        "{author} bonks {target} and they both laugh.",
        "{author} bonks {target} with cartoon sound effects.",
        "{author} bonks {target} gently on the noggin.",
        "{author} bonks {target} softly and smiles."
    ],
    "stare": [
        "{author} stares at {target} intensely.",
        "{author} gives {target} a long, meaningful stare {suffix}",
        "{author} stares and raises an eyebrow.",
        "{author} stares like a mysterious anime character.",
        "{author} stares until {target} reacts.",
        "{author} stares playfully at {target}.",
        "{author} stares with curiosity.",
        "{author} stares and waits for {target} to blink.",
        "{author} stares like it's a staring contest.",
        "{author} stares and smiles slowly."
    ],
    "laugh": [
        "{author} laughs with {target} until they cry.",
        "{author} laughs at {target}'s joke {suffix}",
        "{author} laughs loudly and heartily.",
        "{author} laughs and claps with {target}.",
        "{author} laughs so hard they snort.",
        "{author} chuckles and grins at {target}.",
        "{author} laughs with a gleam in their eye.",
        "{author} laughs and pats {target} on the back.",
        "{author} laughs together with {target}.",
        "{author} laughs and spreads joy."
    ],
    "smug": [
        "{author} smirks smugly at {target} {suffix}",
        "{author} looks at {target} with a smug grin.",
        "{author} gives {target} a playful smug stare.",
        "{author} says 'I told you so' with a smug face.",
        "{author} looks quite pleased with themselves around {target}.",
        "{author} smirks and taps their chin.",
        "{author} gives {target} a teasing, smug smile.",
        "{author} looks smugly at {target}.",
        "{author} smirks and walks away victorious.",
        "{author} strikes a smug pose for {target}."
    ],
    "sleep": [
        "{author} dozes off next to {target}. Zzz...",
        "{author} drifts to sleep softly {suffix}",
        "{author} snoozes while {target} watches peacefully.",
        "{author} naps beside {target}.",
        "{author} sleeps like a comfortable kitty.",
        "{author} curls up and sleeps soundly.",
        "{author} falls asleep mid-conversation.",
        "{author} sleeps and dreams of {target}.",
        "{author} sleeps with a soft smile.",
        "{author} dozes peacefully."
    ],
    "holdhands": [
        "{author} holds {target}'s hand warmly.",
        "{author} and {target} hold hands while walking {suffix}",
        "{author} clasps {target}'s hand gently.",
        "{author} holds {target}'s hand and smiles.",
        "{author} squeezes {target}'s hand softly.",
        "{author} links fingers with {target}.",
        "{author} holds hands and feels safe.",
        "{author} holds hands in silence.",
        "{author} holds {target}'s hand tenderly.",
        "{author} holds hands and hums a tune."
    ],
    "feed": [
        "{author} feeds {target} a tasty treat {suffix}",
        "{author} offers {target} a cute snack.",
        "{author} feeds {target} with a spoon.",
        "{author} feeds {target} a slice of cake.",
        "{author} feeds {target} like a loving friend.",
        "{author} shares a snack with {target}.",
        "{author} offers {target} some yummy food.",
        "{author} feeds {target} and they smile.",
        "{author} feeds {target} a chocolate bite.",
        "{author} feeds {target} and they blush."
    ],
    "throw": [
        "{author} throws {target} a playful object!",
        "{author} tosses {target} across the screen (not serious).",
        "{author} throws a plush at {target} {suffix}",
        "{author} launches {target} into a soft tumble.",
        "{author} throws {target} gently, all in fun.",
        "{author} tosses something at {target}.",
        "{author} throws a paper plane at {target}.",
        "{author} playfully throws {target}'s hat.",
        "{author} tosses {target} a ball of yarn.",
        "{author} throws {target} into an imaginary pool."
    ],
    "run": [
        "{author} runs away with {target} in tow!",
        "{author} runs like the wind with {target} {suffix}",
        "{author} and {target} sprint off laughing.",
        "{author} jogs happily beside {target}.",
        "{author} runs to catch {target}.",
        "{author} runs toward an adventure with {target}.",
        "{author} runs with excitement.",
        "{author} dashes off and returns with snacks.",
        "{author} runs and flings arms wide.",
        "{author} runs while singing."
    ],
    "scared": [
        "{author} shivers in fear and clutches {target}.",
        "{author} looks scared and hides behind {target} {suffix}",
        "{author} is startled and jumps.",
        "{author} screams dramatically in fright.",
        "{author} looks wide-eyed and scared.",
        "{author} trembles a little with fear.",
        "{author} gulps and holds {target}'s hand.",
        "{author} hides behind {target} for safety.",
        "{author} flinches and recovers.",
        "{author} is spooked and then laughs it off."
    ],
    "comfort": [
        "{author} comforts {target} with kind words {suffix}",
        "{author} offers a caring embrace to {target}.",
        "{author} sits with {target} and listens.",
        "{author} wraps {target} in a warm blanket of support.",
        "{author} holds {target} and whispers encouragement.",
        "{author} comforts {target} until they smile.",
        "{author} offers a shoulder to cry on.",
        "{author} comforts {target} and offers tea.",
        "{author} shares a calming hug with {target}.",
        "{author} reassures {target} gently."
    ],
    "tease": [
        "{author} teases {target} playfully {suffix}",
        "{author} pokes fun at {target} but it's loving.",
        "{author} teases {target} with a grin.",
        "{author} makes a cheeky comment at {target}.",
        "{author} teases {target} and winks.",
        "{author} jokes around with {target}.",
        "{author} teases {target} gently.",
        "{author} rib-tickles {target} with teasing words.",
        "{author} teases {target} and laughs.",
        "{author} teases {target} in a cute way."
    ]
}

# ======================================================================================================================
# MESSAGE HANDLING PIPELINE
# ======================================================================================================================

async def resolve_member(guild: Optional[discord.Guild], token: str) -> Optional[discord.Member]:
    """
    Resolve a token to a discord.Member. Accepts:
      - mention: <@123456789>
      - id: 123456789
      - username#discriminator
      - display name
    """
    if not guild:
        return None
    token = (token or "").strip()
    m = MENTION_RE.match(token)
    if m:
        try:
            uid = int(m.group("id"))
            member = guild.get_member(uid)
            if member:
                return member
        except Exception:
            pass
    # raw id
    if token.isdigit():
        try:
            member = guild.get_member(int(token))
            if member:
                return member
        except Exception:
            pass
    # username#discriminator exact match
    lowered = token.lower()
    for mem in guild.members:
        combo = f"{mem.name}#{mem.discriminator}".lower()
        if combo == lowered or mem.display_name.lower() == lowered or mem.name.lower() == lowered:
            return mem
    return None

async def choose_gif_for_action(guild: Optional[discord.Guild], action: str, session: Optional[aiohttp.ClientSession]=None) -> Optional[str]:
    """
    Choose a gif URL for the given action.
    Strategy:
      1. If TENOR_API_KEY is set, attempt to fetch Tenor gifs for the action query.
      2. If Tenor returns results, deduplicate and pick one preferring freshness (not in recent list).
      3. If Tenor is unavailable or returns too few, fallback to FALLBACK_GIFS[action].
    """
    gifs: List[str] = []
    query = f"{action} anime"
    if TENOR_API_KEY and session:
        try:
            # Reuse the session to call Tenor
            params = {"q": query, "key": TENOR_API_KEY, "limit": TENOR_REQUEST_LIMIT, "media_filter": "minimal"}
            async with session.get(TENOR_SEARCH_URL, params=params, timeout=HTTP_TIMEOUT) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", []) or []
                    for r in results:
                        media = r.get("media_formats", {}) or r.get("media", {})
                        url = None
                        if isinstance(media, dict):
                            for k in ("gif", "mediumgif", "tinygif", "nanogif"):
                                entry = media.get(k)
                                if isinstance(entry, dict):
                                    url = entry.get("url")
                                    if url:
                                        gifs.append(url)
                                        break
                        if not url:
                            # sniff any http string in r
                            for v in r.values():
                                if isinstance(v, str) and v.startswith("http"):
                                    gifs.append(v)
                                    break
        except Exception:
            # Tenor failed, ignore and fallback
            gifs = []

    # De-duplicate and trim
    uniq = []
    for u in gifs:
        if u and u not in uniq:
            uniq.append(u)
        if len(uniq) >= MAX_GIF_CANDIDATES:
            break
    gifs = uniq

    # If insufficient, use fallback list
    if not gifs or len(gifs) < 3:
        gifs = FALLBACK_GIFS.get(action, [])[:]

    # prefer fresh gifs not in recent
    guild_id = getattr(guild, "id", 0)
    recent = get_recent_gifs(guild_id)
    for u in gifs:
        if u not in recent:
            add_recent_gif(guild_id, u)
            return u
    # all are recent -> rotate and pick first
    chosen = gifs[0] if gifs else (GENERIC_FALLBACK_GIFS[0] if GENERIC_FALLBACK_GIFS else None)
    if chosen:
        add_recent_gif(guild_id, chosen)
    return chosen

async def generate_local_caption(action: str, author: str, target: str) -> str:
    """
    Select a local caption template for an action and format it.
    Adds a random cute suffix occasionally.
    """
    templates = CAPTION_TEMPLATES.get(action, [])
    if not templates:
        # fallback generic
        basic = f"{author} {action}s {target}"
        if random.random() < 0.4:
            basic = f"{basic} {random.choice(CUTE_SUFFIXES)}"
        return basic
    template = random.choice(templates)
    suffix = random.choice(CUTE_SUFFIXES) if random.random() < 0.35 else ""
    out = template.format(author=author, target=target, suffix=suffix)
    out = compact(out)
    out = owoify_caption(out)
    return out

async def send_owo_style(channel: discord.TextChannel, author: discord.Member, target: discord.Member, action: str, session: Optional[aiohttp.ClientSession]=None):
    """
    Compose and send the owo-style response:
      1) Header line (bold) + caption (plain text)
      2) Small sleep (very short) then embed with GIF only
      3) Add reactions to embed message
    """
    if not channel:
        return

    # cooldown enforcement
    rem = get_cooldown_remaining(author.id, action)
    if rem > 0:
        try:
            await channel.send(f"⏳ <@{author.id}>, wait `{int(rem)}`s before using `{action}` again.")
        except Exception:
            pass
        return
    set_cooldown(author.id, action)

    # choose gif
    chosen = None
    try:
        # provide a fresh session if not provided
        if session:
            chosen = await choose_gif_for_action(channel.guild, action, session=session)
        else:
            # open a local session
            async with aiohttp.ClientSession() as s:
                chosen = await choose_gif_for_action(channel.guild, action, session=s)
    except Exception:
        # fallback to local resource
        arr = FALLBACK_GIFS.get(action, []) or GENERIC_FALLBACK_GIFS
        chosen = arr[0] if arr else (GENERIC_FALLBACK_GIFS[0] if GENERIC_FALLBACK_GIFS else None)

    if not chosen:
        chosen = GENERIC_FALLBACK_GIFS[0] if GENERIC_FALLBACK_GIFS else None

    # generate caption
    caption = await generate_local_caption(action, author.display_name, target.display_name)

    # header line
    header = build_header_line(author.display_name, action, target.display_name)

    # send header + caption
    try:
        text_msg = f"**{header}**\n{caption}"
        sent_text = await channel.send(text_msg)
    except Exception:
        sent_text = None

    # send gif embed
    try:
        color = ACTION_COLORS.get(action, random.choice(PASTEL_COLORS))
        embed = discord.Embed(color=color)
        if chosen:
            try:
                embed.set_image(url=chosen)
            except Exception:
                # if embed fails, send as plain url
                try:
                    sent_image = await channel.send(chosen)
                except Exception:
                    sent_image = None
            else:
                sent_image = await channel.send(embed=embed)
        else:
            sent_image = None
    except Exception:
        sent_image = None

    # add recent gif entry (already done inside choose_gif_for_action, but ensure)
    try:
        add_recent_gif(channel.guild.id if channel.guild else 0, chosen)
    except Exception:
        pass

    # add reactions for vibe
    try:
        reactions = ACTION_REACTIONS.get(action, [])[:MAX_REACTIONS]
        if sent_image:
            for r in reactions:
                try:
                    await sent_image.add_reaction(r)
                except Exception:
                    pass
        elif sent_text:
            for r in reactions:
                try:
                    await sent_text.add_reaction(r)
                except Exception:
                    pass
    except Exception:
        pass

# ======================================================================================================================
# HELP EMBED: dso F.C
# ======================================================================================================================
def build_help_embed() -> discord.Embed:
    """
    Build the 'dso F.C' embed listing actions grouped by category.
    """
    title = "💫 D.S.O Fun Command List"
    desc = "**Usage:** `dso <action> @user` or `<action>@user` or `<action> @user`\n\n" \
           "Try commands like `dso hug @user` or `hug@user` — it's Owo-style!\n"
    embed = discord.Embed(title=title, description=desc, color=random.choice(PASTEL_COLORS))
    # categories
    soft = ["hug", "pat", "cuddle", "kiss", "holdhands", "comfort", "feed", "boop"]
    actiony = ["slap", "punch", "kick", "bonk", "bite", "throw", "run", "punch"]
    playful = ["tickle", "tease", "poke", "highfive", "laugh", "dance", "smug"]
    mood = ["cry", "blush", "wave", "stare", "scared", "sleep"]
    # add fields
    embed.add_field(name="🤝 Cute / Soft", value=", ".join(soft), inline=False)
    embed.add_field(name="⚔️ Action / Battle", value=", ".join(actiony), inline=False)
    embed.add_field(name="🎭 Playful / Fun", value=", ".join(playful), inline=False)
    embed.add_field(name="😳 Emotional / Mood", value=", ".join(mood), inline=False)
    embed.set_footer(text=f"{len(ACTIONS)} total fun actions — type `dso <action> @user` to try one! uwu")
    return embed

# ======================================================================================================================
# MAIN ENTRYPOINT: handle_message_event(message)
# ======================================================================================================================
async def handle_message_event(message: discord.Message) -> None:
    """
    This function is the main export of this module.
    Call it from your bot's on_message event.
    It will:
      - ignore bots
      - ignore DMs
      - respond to dso F.C help
      - parse prefixless fun commands (dso hug@user, hug@user, hug @user)
      - call send_owo_style for valid actions
    """
    # basic guards
    if not message or not getattr(message, "content", None):
        return
    if message.author.bot:
        return
    if message.channel.type == discord.ChannelType.private:
        # ignore DMs
        return

    content = message.content.strip()
    lc = content.lower()

    # help command
    if HELP_PATTERN.match(lc):
        try:
            embed = build_help_embed()
            await message.channel.send(embed=embed)
        except Exception:
            try:                                                  await message.channel.send("D.S.O Fun Commands:\n" + ", ".join(ACTIONS))
            except Exception:                                     pass                                      return                                                                                          # Try no-space pattern: hug@user or dso hug@user
    m = ACTION_PATTERN_NO_SPACE.match(content)        if m:                                                 action = m.group("action").lower()                token = m.group("target")                         member = await resolve_member(message.guild, token)                                                 if member:
            # open a session for Tenor (if needed)            if TENOR_API_KEY:                                     async with aiohttp.ClientSession() as session:
                    await send_owo_style(message.channel, message.author, member, action, session=session)                                                        else:
                await send_owo_style(message.channel, message.author, member, action, session=None)
            return

    # Try space-separated pattern: hug @user
    m2 = ACTION_PATTERN_SPACE.match(content)
    if m2:
        action = m2.group("action").lower()
        token = m2.group("target")
        member = await resolve_member(message.guild, token)
        if member:                                            if TENOR_API_KEY:
                async with aiohttp.ClientSession() as session:
                    await send_owo_style(message.channel, message.author, member, action, session=session)                                                        else:
                await send_owo_style(message.channel, message.author, member, action, session=None)
            return                                
    # No fun match found — ignore                     return

# ======================================================================================================================
# EXTRA: optional command to list all actions as plain text (for environments where embeds fail)    # ======================================================================================================================                              async def send_plain_actions_list(channel: discord.TextChannel) -> None:
    try:
        text = "D.S.O Fun Actions:\n" + ", ".join(ACTIONS)
        await channel.send(text)                      except Exception:
        pass                                      
# ======================================================================================================================
# UTILITY: convenience function to quickly test this module
# (Only used if someone runs this file directly - not recommended in production)
# ======================================================================================================================
if __name__ == "__main__":
    print("This module is meant to be imported by your main bot file (bot.py).")
    print("Place it next to bot.py and call `await handle_message_event(message)` from your on_message event.")
    print(f"This fun module defines {len(ACTIONS)} actions and includes at least 10 gifs per action.")
    # Print a short sample of GIFs for quick verification
    for act in ACTIONS:
        print(f"{act}: {len(FALLBACK_GIFS.get(act, []))} gifs (sample: {FALLBACK_GIFS.get(act, [GENERIC_FALLBACK_GIFS[0]])[0]})")                     
# ======================================================================================================================
# END OF FILE (fun.py)                            # ======================================================================================================================