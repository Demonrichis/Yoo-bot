# Fun.py — D.S.O BOT — Fun Command System v1.2 (Auto-Tenor Edition)
# ------------------------------------------------------------------------------------
# Upgrades from v1.1:
#   • Automatic Tenor fetching on every action (OWO-like), with small persistent cache.
#   • OWO-style captions: "<Author> <action>s <Target>!! <random tail>"
#   • Sender avatar displayed in embed author (circular in Discord UI).
#   • Prefers 1:1 (square) Tenor GIFs when available; otherwise falls back.
#   • Footer updated exactly as requested.
#
# Requirements (Python 3.10+):
#   pip install -U discord.py aiohttp
#
# Configure secrets (RECOMMENDED via environment):
#   export DISCORD_BOT_TOKEN="xxx"
#   export TENOR_API_KEY="xxx"
# ------------------------------------------------------------------------------------

import asyncio
import json
import os
import random
import re
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands

# ------------------------------------------------------------------------------------
# Tokens (env first, fallback to literals if you prefer)
# ------------------------------------------------------------------------------------
DISCORD_BOT_TOKEN=""
TENOR_API_KEY="AIzaSyA-zr6XaXQIjkcpEAfMALzujwD0jEnqt7o"

# ------------------------------------------------------------------------------------
# Constants / Files
# ------------------------------------------------------------------------------------
ACTIONS_FILE      = "actions.json"        # { action_name: {"gifs":[url,...], "aliases":[...]} }
GUILD_FILE        = "fun_config.json"     # { str(gid): {"enabled":bool,"fun_channel":id,"auto_react":bool,"cooldown":int} }
STATS_FILE        = "fun_stats.json"      # { "global":{"uses":int,"actions":{name:int}}, "guilds":{gid:{...}}, "users":{uid:{"uses":int}} }
FAVS_FILE         = "favorites.json"      # { str(uid): { action: [gif_url,...] } }
SUGGEST_FILE      = "suggestions.json"    # [ {"guild":gid,"user":uid,"action":"...","time":epoch} ]

EMBED_FOOTER      = "Version 1.2 • Demon Dev • Powered by DEMON'S SERVER"

# Seed actions (admins can add more with add-action / alias)
DEFAULT_ACTION_NAMES = [
    "hug", "kiss", "slap", "punch", "pat",
    "poke", "dance", "cry", "laugh", "blush",
    "cuddle", "wink", "highfive", "kick", "bonk",
    "stare", "wave", "bite", "smug", "sleep",
    "handhold", "cheer", "sip", "tease", "boop",
    "headpat", "nom", "clap", "spin", "glare",
    "apologize", "thank", "salute", "bark", "meow",
    "hide", "peek", "spin2", "spin3", "flex",
    "twerk", "chill", "vibe", "confess", "protect"
]

# Big auto-reaction pool (80+)
REACTION_POOL = [
    "❤️","😂","😳","💀","🔥","✨","😼","😎","🤝","🎭",
    "😏","😇","🤡","🙃","😈","👀","😱","🥶","🤯","🫠",
    "🫡","🤌","🙏","🙌","👏","💯","🎯","🌶️","🍿","🧨",
    "🎉","🥳","🤗","🥹","😤","😮‍💨","😌","😴","😪","🫶",
    "💘","💫","⚡","🌟","🌈","💥","🫵","🫣","🫢","🫡",
    "🤝","🤍","💙","💚","💛","🧡","💜","🖤","🤎","🩷",
    "🩵","🩶","💢","💤","💬","🗯️","🔔","🔊","🎶","🎵",
    "🥷","🦾","🦿","🦄","🐉","🪽","🐱","🐶","🐧","🦊",
    "🍭","🍩","🍔","🍟","🍕","🌮","🍜","🍣","🍫","☕"
]

# ------------------------------------------------------------------------------------
# OWO-style caption tails per action (short, expressive)
# ------------------------------------------------------------------------------------
CAPTION_TAILS: Dict[str, List[str]] = {
    "hug": [
        "Don't squeeze too hard!", "So warm!", "Aww, that's adorable!",
        "Tight and cozy!", "Such a wholesome hug!"
    ],
    "kiss": [
        "So sweet!", "Mwah~", "Love is in the air!",
        "Blushing intensifies!", "Too cute!"
    ],
    "slap": [
        "Ouch!! That must’ve hurt!", "That’s gotta sting!", "Someone’s mad!",
        "Yikes!", "That left a mark!"
    ],
    "pat": [
        "There there~", "Good job!", "Such a gentle pat!",
        "Headpats for the win!", "So comfy!"
    ],
    "bonk": [
        "Bonk! Go to horny jail!", "Behave!", "Stay wholesome!",
        "That was deserved!", "Discipline time!"
    ],
    # Fallback defaults used for any action not listed above
    "_default": [
        "That's cute!", "Wow!", "How sweet!", "Legendary!", "Nice one!"
    ],
}

def pick_tail(action: str) -> str:
    arr = CAPTION_TAILS.get(action.lower()) or CAPTION_TAILS["_default"]
    return random.choice(arr)

# ------------------------------------------------------------------------------------
# Intents / Bot
# ------------------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="none", intents=intents)

# Optional: console logging
discord.utils.setup_logging()

# ------------------------------------------------------------------------------------
# Utilities: File I/O
# ------------------------------------------------------------------------------------
def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ------------------------------------------------------------------------------------
# Global Stores
# ------------------------------------------------------------------------------------
# actions_store: { action_name: {"gifs":[...], "aliases":[...]} }
actions_store: Dict[str, Dict[str, List[str]]] = load_json(ACTIONS_FILE, {})

# Ensure defaults exist
_changed = False
for name in DEFAULT_ACTION_NAMES:
    if name not in actions_store:
        actions_store[name] = {"gifs": [], "aliases": []}
        _changed = True
if _changed:
    save_json(ACTIONS_FILE, actions_store)

# guild_store: { str(gid): {"enabled":bool,"fun_channel":int|None,"auto_react":bool,"cooldown":int} }
guild_store: Dict[str, Dict] = load_json(GUILD_FILE, {})

# stats_store structure:
# { "global":{"uses":0,"actions":{...}}, "guilds":{gid:{"uses":0,"actions":{...}}}, "users":{uid:{"uses":0}} }
stats_store: Dict = load_json(STATS_FILE, {"global": {"uses": 0, "actions": {}}, "guilds": {}, "users": {}})

# favorites: { uid: { action: [gif_url,...] } }
favorites_store: Dict[str, Dict[str, List[str]]] = load_json(FAVS_FILE, {})

# suggestions: [ { "guild": gid, "user": uid, "action": text, "time": epoch } ]
suggestions_store: List[Dict] = load_json(SUGGEST_FILE, [])

# ------------------------------------------------------------------------------------
# Tenor API
# ------------------------------------------------------------------------------------
TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"

async def fetch_tenor_gifs(query: str, limit: int = 15) -> List[dict]:
    """Return a list of media_formats blocks (we'll pick best match for 1:1)."""
    if not TENOR_API_KEY or TENOR_API_KEY == "YOUR_TENOR_API_KEY":
        return []

    params = {
        "q": query,
        "key": TENOR_API_KEY,
        "limit": str(limit),
        "media_filter": "gif",        # request at least the 'gif' format
        "contentfilter": "high",
        "random": "true"              # diversify results
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params, timeout=20) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    out = []
    for item in data.get("results", []):
        mf = item.get("media_formats", {})
        if mf:
            out.append(mf)
    return out

def pick_best_gif_url(media_formats: dict) -> Optional[str]:
    """
    Try to prefer a square (1:1) GIF if Tenor provides dims. Otherwise, return 'gif' url.
    Tenor v2 'gif' object may include 'dims': [w, h]. Not always present, so be defensive.
    """
    # If there are multiple gif-like keys, check them all for dims.
    candidates = []
    for key, obj in media_formats.items():
        if not isinstance(obj, dict):
            continue
        url = obj.get("url")
        dims = obj.get("dims") or obj.get("size")  # dims is usually [w, h]; size is bytes
        if url and isinstance(media_formats.get("gif", {}), dict):  # ensure gif exists
            if isinstance(dims, list) and len(dims) == 2:
                w, h = dims
                candidates.append((abs(int(w) - int(h)), url))  # diff from square
            else:
                # unknown dims, treat as non-square candidate with large diff
                candidates.append((10_000, url))

    if candidates:
        candidates.sort(key=lambda t: t[0])  # smallest diff first -> closest to 1:1
        return candidates[0][1]

    # Fallback: plain gif url if present
    gif_obj = media_formats.get("gif")
    if isinstance(gif_obj, dict) and gif_obj.get("url"):
        return gif_obj["url"]
    return None

async def ensure_action_gifs_cached(action: str, force_min: int = 1, refill_to: int = 10) -> None:
    """
    Ensure we hold a small cache for this action. If below force_min, fetch and cache up to refill_to.
    We still fetch fresh sets on demand during usage; this is just to keep it snappy like OWO.
    """
    entry = actions_store.setdefault(action, {"gifs": [], "aliases": []})
    have = entry.get("gifs", [])
    if len(have) >= force_min:
        return

    media_sets = await fetch_tenor_gifs(f"anime {action} gif", limit=max(refill_to, 10))
    picked_urls: List[str] = []
    for mf in media_sets:
        url = pick_best_gif_url(mf)
        if url:
            picked_urls.append(url)

    if picked_urls:
        # merge + dedupe, keep most recent first
        merged = picked_urls + have
        deduped, seen = [], set()
        for u in merged:
            if u not in seen:
                deduped.append(u)
                seen.add(u)
        entry["gifs"] = deduped[:refill_to]
        save_json(ACTIONS_FILE, actions_store)

# ------------------------------------------------------------------------------------
# Anti-Spam / Cooldown
# ------------------------------------------------------------------------------------
USER_LAST_USE: Dict[int, float] = {}
USER_BURST: Dict[int, List[float]] = defaultdict(list)
BURST_WINDOW = 8.0
BURST_LIMIT  = 5

def guild_cooldown(gid: int) -> int:
    cfg = guild_store.get(str(gid), {})
    return int(cfg.get("cooldown", 5))

def can_use_now(uid: int, gid: int) -> Tuple[bool, Optional[str]]:
    now = time.time()
    last = USER_LAST_USE.get(uid, 0.0)
    cd = guild_cooldown(gid)
    if now - last < cd:
        return False, f"Cooldown {cd}s — slow down."

    q = USER_BURST[uid]
    q[:] = [t for t in q if now - t <= BURST_WINDOW]
    if len(q) >= BURST_LIMIT:
        return False, "Too many actions at once. Take a breath 😮‍💨"
    return True, None

def record_use(uid: int):
    now = time.time()
    USER_LAST_USE[uid] = now
    USER_BURST[uid].append(now)

# ------------------------------------------------------------------------------------
# Stats Helpers
# ------------------------------------------------------------------------------------
def inc_stats(gid: int, action: str, uid: int):
    # Global
    g = stats_store.setdefault("global", {"uses": 0, "actions": {}})
    g["uses"] = int(g.get("uses", 0)) + 1
    ga = g.setdefault("actions", {})
    ga[action] = int(ga.get(action, 0)) + 1

    # Guild
    gkey = str(gid)
    gg = stats_store.setdefault("guilds", {}).setdefault(gkey, {"uses": 0, "actions": {}})
    gg["uses"] = int(gg.get("uses", 0)) + 1
    gga = gg.setdefault("actions", {})
    gga[action] = int(gga.get(action, 0)) + 1

    # User
    ukey = str(uid)
    u = stats_store.setdefault("users", {}).setdefault(ukey, {"uses": 0})
    u["uses"] = int(u.get("uses", 0)) + 1

    save_json(STATS_FILE, stats_store)

# ------------------------------------------------------------------------------------
# Paginator View (unchanged, correct signatures)
# ------------------------------------------------------------------------------------
class Paginator(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.author_id = author_id

    async def _ensure(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requester can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        self.index = (self.index - 1) % len(self.pages)
        await interaction.followup.edit_message(interaction.message.id, embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        self.index = (self.index + 1) % len(self.pages)
        await interaction.followup.edit_message(interaction.message.id, embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="🔒", label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)

# ------------------------------------------------------------------------------------
# Action View (buttons under action embeds) — unchanged behavior, fixed signatures
# ------------------------------------------------------------------------------------
class ActionView(discord.ui.View):
    """
    Buttons:
      • ❤️ React back  -> swap author/target and send embed (same/new gif)
      • 🔁 Repeat      -> same direction, new random gif
      • ⭐ Favorite    -> save current gif into user favorites for this action
      • 🔀 Shuffle     -> edit current embed's image with a new gif
      • 💀 Hide       -> delete message (ephemeral ack)
      • 🔒 Close      -> disable all buttons
    """

    def __init__(self, author_id: int, target_id: int, action: str, gif_url: str, message_author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.target_id = target_id
        self.action = action
        self.gif_url = gif_url or ""
        self.owner_id = message_author_id  # original sender

    def _allowed_any(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id in (self.author_id, self.target_id, self.owner_id)

    async def _deny(self, interaction: discord.Interaction):
        await interaction.response.send_message("You can’t use these buttons for this action.", ephemeral=True)

    def _guild_members(self, interaction: discord.Interaction) -> Tuple[Optional[discord.Member], Optional[discord.Member], Optional[discord.Member]]:
        guild = interaction.guild
        if not guild:
            return None, None, None
        author = guild.get_member(self.author_id)
        target = guild.get_member(self.target_id)
        invoker = guild.get_member(self.owner_id)
        return author, target, invoker

    def _random_gif(self) -> str:
        gifs = actions_store.get(self.action, {}).get("gifs", [])
        return random.choice(gifs) if gifs else (self.gif_url or "")

    @discord.ui.button(label="❤️ React back", style=discord.ButtonStyle.primary)
    async def react_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer(thinking=True)
        author, target, _ = self._guild_members(interaction)
        if not author or not target:
            return await interaction.followup.send("Context lost.", ephemeral=True)
        embed = discord.Embed(
            color=discord.Color.random(),
        )
        caption = f"{target.display_name} {self.action}s {author.display_name}!! {pick_tail(self.action)}"
        embed.set_author(name=caption, icon_url=target.display_avatar.url if target else discord.Embed.Empty)
        embed.set_image(url=self.gif_url or self._random_gif())
        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="🔁 Repeat", style=discord.ButtonStyle.secondary)
    async def repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer(thinking=True)
        author, target, _ = self._guild_members(interaction)
        if not author or not target:
            return await interaction.followup.send("Context lost.", ephemeral=True)
        pick = self._random_gif()
        embed = discord.Embed(color=discord.Color.random())
        caption = f"{author.display_name} {self.action}s {target.display_name}!! {pick_tail(self.action)}"
        embed.set_author(name=caption, icon_url=author.display_avatar.url if author else discord.Embed.Empty)
        embed.set_image(url=pick)
        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="⭐ Favorite", style=discord.ButtonStyle.success)
    async def favorite(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer(ephemeral=True)
        uid = str(interaction.user.id)
        favs = favorites_store.setdefault(uid, {})
        arr = favs.setdefault(self.action, [])
        url = self.gif_url or self._random_gif()
        if url in arr:
            return await interaction.followup.send("Already in your favorites.", ephemeral=True)
        if len(arr) >= 25:
            return await interaction.followup.send("Favorites limit reached for this action (25).", ephemeral=True)
        arr.append(url)
        save_json(FAVS_FILE, favorites_store)
        await interaction.followup.send("Added to your favorites ⭐", ephemeral=True)

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer()
        new_url = self._random_gif()
        if not interaction.message:
            return await interaction.followup.send("No message context.", ephemeral=True)
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(color=discord.Color.random())
        embed.set_image(url=new_url)
        embed.set_footer(text=EMBED_FOOTER)
        self.gif_url = new_url
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)

    @discord.ui.button(label="💀 Hide", style=discord.ButtonStyle.danger)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.delete()
                await interaction.followup.send("🫥 Message hidden.", ephemeral=True)
            else:
                await interaction.followup.send("Nothing to hide.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don’t have permission to delete that.", ephemeral=True)
        except Exception:
            await interaction.followup.send("Couldn’t hide the message.", ephemeral=True)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_any(interaction):
            return await self._deny(interaction)
        await interaction.response.defer()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if interaction.message:
            await interaction.followup.edit_message(interaction.message.id, view=self)

# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------
def is_admin(member: discord.Member) -> bool:
    return bool(member.guild_permissions.administrator)

def parse_mention_id(text: str) -> Optional[int]:
    m = re.search(r"<@!?(\d+)>", text)
    return int(m.group(1)) if m else None

def split_chained_parts(after_dso: str) -> List[str]:
    return re.split(r"\s+then\s+", after_dso.strip(), flags=re.IGNORECASE)

def resolve_action(name: str) -> Optional[str]:
    """Resolve an action from its name or alias; returns canonical action name."""
    name = name.lower()
    if name in actions_store:
        return name
    for act, data in actions_store.items():
        aliases = data.get("aliases", [])
        if name in [a.lower() for a in aliases]:
            return act
    return None

async def build_and_send_action(
    channel: discord.abc.Messageable,
    author: discord.Member,
    target: discord.Member,
    action: str,
    auto_record_stats: bool = True
):
    """
    Sends an OWO-style embed:
      [Author Avatar] "<Author> <action>s <Target>!! <random tail>"
      GIF below (prefer 1:1)
      Footer fixed
    """
    # Make sure we have some cached GIFs; if not, fetch & cache
    await ensure_action_gifs_cached(action, force_min=1, refill_to=10)

    # Pick a URL from cache; if cache somehow empty, fetch live once
    gifs = actions_store.get(action, {}).get("gifs", [])
    if not gifs:
        media_sets = await fetch_tenor_gifs(f"anime {action} gif", limit=12)
        picks = []
        for mf in media_sets:
            u = pick_best_gif_url(mf)
            if u:
                picks.append(u)
        if picks:
            actions_store[action]["gifs"] = picks[:10]
            save_json(ACTIONS_FILE, actions_store)
            gifs = actions_store[action]["gifs"]

    gif = random.choice(gifs) if gifs else None

    caption = f"{author.display_name} {action}s {target.display_name}!! {pick_tail(action)}"
    embed = discord.Embed(color=discord.Color.random())
    embed.set_author(name=caption, icon_url=author.display_avatar.url if author else discord.Embed.Empty)
    if gif:
        embed.set_image(url=gif)
    embed.set_footer(text=EMBED_FOOTER)

    view = ActionView(author.id, target.id, action, gif or "", message_author_id=author.id)
    msg = await channel.send(embed=embed, view=view)

    if auto_record_stats:
        inc_stats(author.guild.id, action, author.id)
    return msg

# ------------------------------------------------------------------------------------
# Help text
# ------------------------------------------------------------------------------------
HELP_TEXT = (
    "**D.S.O Fun Commands (prefixless / slashless):**\n"
    "`dso enable F.C` — set fun channel via mention prompt (admin)\n"
    "`dso disable F.C` — disable fun commands in guild (admin)\n"
    "`dso settings` — view/edit settings (auto-react, cooldown)\n"
    "`dso add-action <name>` — fetch 15 Tenor GIFs and add globally (admin)\n"
    "`dso remove-action <name>` — remove an action globally (admin)\n"
    "`dso alias <action> <alias>` — add alias for action (admin)\n"
    "`dso action-list` — list all actions with gif counts (paged)\n"
    "`dso stats` — show usage stats (guild + global)\n"
    "`dso suggest <action>` — suggest a new action\n"
    "`dso favs` — your favorites (paged)\n"
    "`dso fav-use <action>` — send a random favorite gif of that action\n"
    "\n**Use an action:**\n"
    "`dso <action> @user` — e.g., `dso hug @user`\n"
    "`dso <action> @user then <action> then <action>` — chaining with the same target\n"
)

def build_settings_embed(gid: int) -> discord.Embed:
    cfg = guild_store.get(str(gid), {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5})
    ch = cfg.get("fun_channel")
    e = discord.Embed(title="D.S.O Settings", color=discord.Color.blurple())
    e.add_field(name="Enabled", value=str(bool(cfg.get("enabled", False))), inline=True)
    e.add_field(name="Fun Channel", value=f"<#{ch}>" if ch else "Not set", inline=True)
    e.add_field(name="Auto React", value="On" if cfg.get("auto_react", True) else "Off", inline=True)
    e.add_field(name="Cooldown (s)", value=str(cfg.get("cooldown", 5)), inline=True)
    e.set_footer(text=EMBED_FOOTER)
    return e

class SettingsView(discord.ui.View):
    def __init__(self, guild_id: int, author_id: int):
        super().__init__(timeout=120)
        self.gid = str(guild_id)
        self.author_id = author_id

    async def _ensure(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the admin who opened settings can modify them.", ephemeral=True)
            return False
        if not is_admin(interaction.user):
            await interaction.response.send_message("Only admins can change settings.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Toggle Auto-React", style=discord.ButtonStyle.primary)
    async def toggle_auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        cfg = guild_store.setdefault(self.gid, {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5})
        cfg["auto_react"] = not cfg.get("auto_react", True)
        save_json(GUILD_FILE, guild_store)
        await interaction.followup.edit_message(interaction.message.id, embed=build_settings_embed(int(self.gid)), view=self)

    @discord.ui.button(label="Cooldown -1s", style=discord.ButtonStyle.secondary)
    async def cd_dec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        cfg = guild_store.setdefault(self.gid, {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5})
        cfg["cooldown"] = max(0, int(cfg.get("cooldown", 5)) - 1)
        save_json(GUILD_FILE, guild_store)
        await interaction.followup.edit_message(interaction.message.id, embed=build_settings_embed(int(self.gid)), view=self)

    @discord.ui.button(label="Cooldown +1s", style=discord.ButtonStyle.secondary)
    async def cd_inc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        cfg = guild_store.setdefault(self.gid, {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5})
        cfg["cooldown"] = min(30, int(cfg.get("cooldown", 5)) + 1)
        save_json(GUILD_FILE, guild_store)
        await interaction.followup.edit_message(interaction.message.id, embed=build_settings_embed(int(self.gid)), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure(interaction):
            return
        await interaction.response.defer()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)

# ------------------------------------------------------------------------------------
# Single on_message handler (prefixless "dso ..." flow)
# ------------------------------------------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if not message.guild or message.author.bot:
        return

    content = message.content.strip()

    # Quick "dso help"
    if content.lower() == "dso help":
        e = discord.Embed(title="D.S.O — Help", description=HELP_TEXT, color=discord.Color.green())
        e.set_footer(text=EMBED_FOOTER)
        try:
            await message.channel.send(embed=e)
        except Exception:
            pass
        # continue to allow other "dso ..." to be handled too

    if not content.lower().startswith("dso"):
        return

    gid = message.guild.id
    gkey = str(gid)
    cfg = guild_store.get(gkey, {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5})

    after = content[3:].strip()

    # --- Admin: enable F.C ----------------------------------------------------------
    if re.fullmatch(r"enable\s+F\.C", after, flags=re.IGNORECASE):
        if not is_admin(message.author):
            return await message.channel.send("Only admins can run setup.")
        await message.channel.send("Mention the channel where fun commands should work (e.g. #fun):")

        def ch_check(m: discord.Message):
            return m.author.id == message.author.id and m.channel.id == message.channel.id and m.channel_mentions

        try:
            reply = await bot.wait_for("message", check=ch_check, timeout=90)
        except asyncio.TimeoutError:
            return await message.channel.send("Setup timed out.")

        fun_channel = reply.channel_mentions[0]
        guild_store[gkey] = {"enabled": True, "fun_channel": fun_channel.id, "auto_react": True, "cooldown": 5}
        save_json(GUILD_FILE, guild_store)
        return await message.channel.send(f"✅ Fun Commands enabled in {fun_channel.mention}.")

    # --- Admin: disable F.C ---------------------------------------------------------
    if re.fullmatch(r"disable\s+F\.C", after, flags=re.IGNORECASE):
        if not is_admin(message.author):
            return await message.channel.send("Only admins can do that.")
        guild_store[gkey] = {"enabled": False, "fun_channel": None, "auto_react": True, "cooldown": 5}
        save_json(GUILD_FILE, guild_store)
        return await message.channel.send("🚫 Fun Commands disabled for this server.")

    # --- Settings card --------------------------------------------------------------
    if re.fullmatch(r"settings", after, flags=re.IGNORECASE):
        if not is_admin(message.author):
            return await message.channel.send("Only admins can view/edit settings.")
        embed = build_settings_embed(gid)
        view = SettingsView(gid, message.author.id)
        return await message.channel.send(embed=embed, view=view)

    # --- Admin: add-action <name> ---------------------------------------------------
    m_add = re.match(r"add-action\s+([a-zA-Z0-9_-]{2,24})$", after, flags=re.IGNORECASE)
    if m_add:
        if not is_admin(message.author):
            return await message.channel.send("Only admins can add actions.")
        action_name = m_add.group(1).lower()

        await message.channel.send(f"Adding action `{action_name}`… fetching GIFs.")
        media_sets = await fetch_tenor_gifs(f"anime {action_name} gif", limit=15)
        urls: List[str] = []
        for mf in media_sets:
            u = pick_best_gif_url(mf)
            if u:
                urls.append(u)
        if not urls:
            return await message.channel.send("Couldn’t find GIFs right now. Try another action or later.")

        entry = actions_store.setdefault(action_name, {"gifs": [], "aliases": []})
        merged = urls + entry["gifs"]
        deduped, seen = [], set()
        for u in merged:
            if u not in seen:
                deduped.append(u)
                seen.add(u)
        entry["gifs"] = deduped[:15]
        save_json(ACTIONS_FILE, actions_store)

        return await message.channel.send(f"✅ Action `{action_name}` added with {len(entry['gifs'])} GIFs.")

    # --- Admin: remove-action <name> -----------------------------------------------
    m_rem = re.match(r"remove-action\s+([a-zA-Z0-9_-]{2,24})$", after, flags=re.IGNORECASE)
    if m_rem:
        if not is_admin(message.author):
            return await message.channel.send("Only admins can remove actions.")
        name = m_rem.group(1).lower()
        canonical = resolve_action(name)
        if not canonical:
            return await message.channel.send("No such action.")
        actions_store.pop(canonical, None)
        save_json(ACTIONS_FILE, actions_store)
        return await message.channel.send(f"🗑️ Removed action `{canonical}`.")

    # --- Admin: alias <action> <alias> ---------------------------------------------
    m_alias = re.match(r"alias\s+([a-zA-Z0-9_-]{2,24})\s+([a-zA-Z0-9_-]{2,24})$", after, flags=re.IGNORECASE)
    if m_alias:
        if not is_admin(message.author):
            return await message.channel.send("Only admins can add aliases.")
        action = resolve_action(m_alias.group(1))
        alias  = m_alias.group(2).lower()
        if not action:
            return await message.channel.send("Base action not found.")
        if alias in actions_store:
            return await message.channel.send("Alias name conflicts with an existing action.")
        entry = actions_store[action]
        aliases = entry.setdefault("aliases", [])
        if alias in [a.lower() for a in aliases]:
            return await message.channel.send("Alias already present.")
        aliases.append(alias)
        save_json(ACTIONS_FILE, actions_store)
        return await message.channel.send(f"🔗 Alias `{alias}` added for action `{action}`.")

    # --- action-list (paged) --------------------------------------------------------
    if re.fullmatch(r"action-list", after, flags=re.IGNORECASE):
        names = sorted(actions_store.keys())
        lines = []
        for n in names:
            cnt = len(actions_store[n].get("gifs", []))
            aliases = actions_store[n].get("aliases", [])
            alias_str = f" — aliases: {', '.join(aliases)}" if aliases else ""
            lines.append(f"• **{n}** ({cnt}){alias_str}")
        pages = []
        for i in range(0, len(lines), 12):
            chunk = lines[i:i+12]
            e = discord.Embed(title="D.S.O Actions", description="\n".join(chunk) if chunk else "No entries.", color=discord.Color.purple())
            e.set_footer(text=f"{EMBED_FOOTER} • Page {i//12 + 1}/{(len(lines)-1)//12 + 1}")
            pages.append(e)
        if not pages:
            pages = [discord.Embed(title="D.S.O Actions", description="No entries.", color=discord.Color.purple())]
        view = Paginator(pages, author_id=message.author.id)
        return await message.channel.send(embed=pages[0], view=view)

    # --- stats ----------------------------------------------------------------------
    if re.fullmatch(r"stats", after, flags=re.IGNORECASE):
        g = stats_store.get("guilds", {}).get(str(gid), {"uses": 0, "actions": {}})
        g_actions: Dict[str,int] = g.get("actions", {})
        g_top = ", ".join([f"{k}({v})" for k,v in Counter(g_actions).most_common(10)]) or "No data."

        gl = stats_store.get("global", {"uses": 0, "actions": {}})
        gg_actions: Dict[str,int] = gl.get("actions", {})
        gg_top = ", ".join([f"{k}({v})" for k,v in Counter(gg_actions).most_common(10)]) or "No data."

        e = discord.Embed(title="D.S.O Stats", color=discord.Color.gold())
        e.add_field(name=f"Guild Uses ({message.guild.name})", value=str(g.get("uses", 0)), inline=False)
        e.add_field(name="Top Guild Actions", value=g_top, inline=False)
        e.add_field(name="Global Uses", value=str(gl.get("uses", 0)), inline=False)
        e.add_field(name="Top Global Actions", value=gg_top, inline=False)
        e.set_footer(text=EMBED_FOOTER)
        return await message.channel.send(embed=e)

    # --- suggest <action> -----------------------------------------------------------
    m_sug = re.match(r"suggest\s+([a-zA-Z0-9_-]{2,24})$", after, flags=re.IGNORECASE)
    if m_sug:
        action = m_sug.group(1).lower()
        suggestions_store.append({"guild": gid, "user": message.author.id, "action": action, "time": int(time.time())})
        save_json(SUGGEST_FILE, suggestions_store)
        return await message.channel.send(f"📨 Suggestion received for `{action}`. Thanks!")

    # --- favorites list -------------------------------------------------------------
    if re.fullmatch(r"favs", after, flags=re.IGNORECASE):
        uid = str(message.author.id)
        favs = favorites_store.get(uid, {})
        lines = []
        for act, urls in favs.items():
            lines.append(f"**{act}** — {len(urls)}")
        pages = []
        for i in range(0, len(lines), 15):
            chunk = lines[i:i+15]
            e = discord.Embed(title=f"{message.author.display_name}'s Favorites", description="\n".join(chunk) if chunk else "No entries.", color=discord.Color.purple())
            e.set_footer(text=f"{EMBED_FOOTER} • Page {i//15 + 1}/{(len(lines)-1)//15 + 1}")
            pages.append(e)
        if not pages:
            pages = [discord.Embed(title=f"{message.author.display_name}'s Favorites", description="No entries.", color=discord.Color.purple())]
        view = Paginator(pages, author_id=message.author.id)
        return await message.channel.send(embed=pages[0], view=view)

    # --- fav-use <action> -----------------------------------------------------------
    m_favu = re.match(r"fav-use\s+([a-zA-Z0-9_-]{2,24})$", after, flags=re.IGNORECASE)
    if m_favu:
        act = m_favu.group(1).lower()
        canon = resolve_action(act) or act
        uid = str(message.author.id)
        arr = favorites_store.get(uid, {}).get(canon, [])
        if not arr:
            return await message.channel.send("You have no favorites saved for that action.")
        url = random.choice(arr)
        embed = discord.Embed(color=discord.Color.random())
        caption = f"{message.author.display_name} {canon}s … {pick_tail(canon)}"
        embed.set_author(name=caption, icon_url=message.author.display_avatar.url)
        embed.set_image(url=url)
        embed.set_footer(text=EMBED_FOOTER)
        view = ActionView(message.author.id, message.author.id, canon, url, message_author_id=message.author.id)
        inc_stats(gid, canon, message.author.id)
        return await message.channel.send(embed=embed, view=view)

    # --- Gate by channel if enabled -------------------------------------------------
    if cfg.get("enabled") and cfg.get("fun_channel"):
        if message.channel.id != cfg["fun_channel"]:
            return  # silent outside configured fun channel

    # --------------------------------------------------------------------------------
    # Action execution: "dso <action> @user [then <action> then <action> ...]"
    # --------------------------------------------------------------------------------
    parts = split_chained_parts(after)
    target_member: Optional[discord.Member] = None

    ok, why = can_use_now(message.author.id, message.guild.id)
    if not ok:
        try:
            await message.add_reaction("💢")
        except Exception:
            pass
        return await message.channel.send(why)

    first_valid = True
    for i, part in enumerate(parts):
        segment = part.strip()
        if not segment:
            continue

        m = re.match(r"([a-zA-Z0-9_-]+)(?:\s+<@!?(\d+)>)?$", segment)
        if not m:
            # Try to find mention anywhere
            mention_id = parse_mention_id(segment)
            if mention_id:
                m2 = re.match(r"([a-zA-Z0-9_-]+)", segment)
                if not m2:
                    continue
                action_raw = m2.group(1).lower()
                mid = mention_id
            else:
                continue
        else:
            action_raw = m.group(1).lower()
            mid = m.group(2)

        action = resolve_action(action_raw) or action_raw

        # First part must establish target
        if i == 0:
            if not mid:
                mid2 = parse_mention_id(segment)
                if mid2:
                    mid = str(mid2)
        if i == 0 and not mid:
            return

        if mid:
            try:
                target_member = await message.guild.fetch_member(int(mid))
            except Exception:
                target_member = None

        if not target_member:
            return

        # create action slot if not present (admin can fill GIFs later)
        actions_store.setdefault(action, {"gifs": [], "aliases": []})
        save_json(ACTIONS_FILE, actions_store)

        ok2, why2 = can_use_now(message.author.id, message.guild.id)
        if not ok2:
            await message.channel.send(why2)
            break

        # React on the original message once for the first valid action
        if first_valid and cfg.get("auto_react", True):
            first_valid = False
            try:
                e1 = random.choice(REACTION_POOL)
                e2 = random.choice(REACTION_POOL)
                await message.add_reaction(e1)
                await message.add_reaction(e2)
            except Exception:
                pass

        await build_and_send_action(message.channel, message.author, target_member, action)
        record_use(message.author.id)

    # Allow any extension cogs to still process
    await bot.process_commands(message)

# ------------------------------------------------------------------------------------
# Events
# ------------------------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Fun Command System v1.2 (Auto-Tenor) ready.")
    # Flush stores to disk
    save_json(ACTIONS_FILE, actions_store)
    save_json(GUILD_FILE, guild_store)
    save_json(STATS_FILE, stats_store)
    save_json(FAVS_FILE, favorites_store)
    save_json(SUGGEST_FILE, suggestions_store)

@bot.event
async def on_error(event_method, *args, **kwargs):
    print(f"[on_error] in {event_method}")

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # No re-trigger on edits
    return

@bot.event
async def on_message_delete(message: discord.Message):
    # Reserved for future cleanups
    return

# ------------------------------------------------------------------------------------
# Run
# ------------------------------------------------------------------------------------
def start_fun_system():
    if DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN" or TENOR_API_KEY == "YOUR_TENOR_API_KEY":
        raise SystemExit("Set DISCORD_BOT_TOKEN and TENOR_API_KEY in the script or environment.")
    return bot
