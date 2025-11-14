# bot.py
# D.S.O BOT — Main Core File
# This file links directly with fun.py and runs your full fun command system.
# Version: v3.0 (Offline Owo Engine Edition)
# Author: Senor (for Demon)

import discord
import asyncio
import logging
from fun import handle_message_event   # 👈 connects fun.py here

# Optional: enable simple logs
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# ======================================================================================================================
# CONFIGURATION
# ======================================================================================================================

# 🔑 Your bot token here
TOKEN = ""

# Discord intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

# Create client
client = discord.Client(intents=intents)

# ======================================================================================================================
# EVENTS
# ======================================================================================================================

@client.event
async def on_ready():
    """
    Called when the bot is connected and ready.
    """
    print(f"[DSO INFO] Logged in as {client.user} (id: {client.user.id})")
    print("[DSO INFO] D.S.O Fun Engine ready to roll 😈")

@client.event
async def on_message(message: discord.Message):
    """
    Called when a message is sent in any channel the bot can read.
    Forwards every message to fun.py for processing.
    """
    try:
        await handle_message_event(message)
    except Exception as e:
        print(f"[DSO ERROR] Unhandled exception in on_message: {e}")

# ======================================================================================================================
# RUN THE BOT
# ======================================================================================================================

if __name__ == "__main__":
    print("[DSO INFO] Starting D.S.O Bot Core...")
    try:
        client.run(TOKEN)
    except KeyboardInterrupt:
        print("[DSO INFO] Shutting down (Ctrl+C pressed).")
    except Exception as e:
        print(f"[DSO ERROR] Failed to start bot: {e}")

# ======================================================================================================================
# END OF FILE (bot.py)
# ======================================================================================================================

