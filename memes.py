import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
from googleapiclient.discovery import build
from datetime import datetime, timezone
import os
import logging

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s"
)

# ---------------- LOAD CONFIG ----------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

DISCORD_TOKEN = config["DISCORD_TOKEN"]
YOUTUBE_API_KEY = config["YOUTUBE_API_KEY"]
MEME_CHANNEL_ID = int(config["MEME_CHANNEL_ID"])
POST_INTERVAL_HOURS = float(config["POST_INTERVAL_HOURS"])
SEARCH_KEYWORDS = config["SEARCH_KEYWORDS"]
MAX_RESULTS = int(config["MAX_RESULTS"])

POSTED_FILE = "posted_memes.json"
MAX_STORED_MEMES = 500  # safety limit

# ---------------- POSTED MEMES ----------------
def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("posted_video_ids", [])
    except Exception:
        return []

def save_posted(video_ids):
    video_ids = video_ids[-MAX_STORED_MEMES:]
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump({"posted_video_ids": video_ids}, f, indent=4)

posted_memes = load_posted()

# ---------------- YOUTUBE CLIENT ----------------
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# ---------------- DISCORD BOT ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="pb ", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    restart_meme_task()

# ---------------- YOUTUBE FETCH (NON BLOCKING) ----------------
def _youtube_search(keyword):
    request = youtube.search().list(
        part="snippet",
        q=keyword,
        maxResults=MAX_RESULTS,
        type="video",
        videoDuration="short",
        safeSearch="moderate"
    )
    return request.execute()

async def fetch_random_meme():
    keyword = random.choice(SEARCH_KEYWORDS)

    try:
        response = await asyncio.to_thread(_youtube_search, keyword)
    except Exception as e:
        logging.error(f"YouTube API error: {e}")
        return None

    candidates = [
        item for item in response.get("items", [])
        if item["id"]["videoId"] not in posted_memes
    ]

    return random.choice(candidates) if candidates else None

# ---------------- EMBED BUILDER ----------------
def build_embed(item):
    video_id = item["id"]["videoId"]
    url = f"https://www.youtube.com/watch?v={video_id}"

    embed = discord.Embed(
        title="😂 Meme Drop",
        description=item["snippet"]["title"],
        color=discord.Color.random(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_image(url=item["snippet"]["thumbnails"]["high"]["url"])
    embed.add_field(
        name="🎬 Channel",
        value=item["snippet"]["channelTitle"],
        inline=True
    )
    embed.add_field(
        name="▶️ Watch",
        value=f"[Click Here]({url})",
        inline=True
    )
    embed.set_footer(text="Next meme auto drop incoming 👀")

    return embed, video_id

# ---------------- TASK LOOP ----------------
@tasks.loop(hours=POST_INTERVAL_HOURS)
async def meme_task():
    channel = bot.get_channel(MEME_CHANNEL_ID)
    if not channel:
        logging.error("Meme channel not found")
        return

    item = await fetch_random_meme()
    if not item:
        logging.warning("No new memes available")
        return

    try:
        embed, video_id = build_embed(item)
        await channel.send(embed=embed)

        posted_memes.append(video_id)
        save_posted(posted_memes)

        logging.info(f"Meme posted: {video_id}")

    except Exception as e:
        logging.error(f"Meme send error: {e}")

# ---------------- TASK CONTROL ----------------
def restart_meme_task():
    if meme_task.is_running():
        meme_task.cancel()
    meme_task.change_interval(hours=POST_INTERVAL_HOURS)
    meme_task.start()
    logging.info(f"Meme task started | Interval: {POST_INTERVAL_HOURS}h")

# ---------------- MANUAL COMMAND ----------------
@bot.command()
@commands.has_permissions(administrator=True)
async def dropmeme(ctx):
    item = await fetch_random_meme()
    if not item:
        await ctx.send("⚠️ No new memes right now.")
        return

    embed, video_id = build_embed(item)
    await ctx.send(embed=embed)

    posted_memes.append(video_id)
    save_posted(posted_memes)

# ---------------- ERROR HANDLING ----------------
@dropmeme.error
async def dropmeme_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Admin only command.")
    else:
        logging.error(error)

# ---------------- RUN ----------------
bot.run(DISCORD_TOKEN)