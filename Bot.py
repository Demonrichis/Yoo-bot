# ------------------------------------------------------------------------------------
# D.S.O BOT — Main Launcher (Linked with Fun.py)
# Version 1.2 • Demon Dev • Powered by DEMON'S SERVER
# ------------------------------------------------------------------------------------
# Description:
#   This is the main startup file for your D.S.O BOT.
#   It imports the full Fun Command System (Auto-Tenor Edition)
#   from fun.py and starts the bot from there.
#
# Folder structure example:
#   D_S_O_BOT/
#   ├── bot.py
#   ├── fun.py
#   ├── actions.json
#   ├── fun_config.json
#   ├── fun_stats.json
#   ├── favorites.json
#   └── suggestions.json
# ------------------------------------------------------------------------------------

from fun import start_fun_system  # import function from fun.py

# ------------------------------------------------------------------------------------
# MAIN BOT LAUNCHER
# ------------------------------------------------------------------------------------
def main():
    print("🚀 Starting D.S.O BOT (linked with fun.py)...")

    # Start the bot instance from fun.py
    bot = start_fun_system()

    # Run the bot — make sure your token is inside fun.py
    bot.run("YOUR_DISCORD_BOT_TOKEN")  # <-- Replace this or keep it empty if set inside fun.py


# ------------------------------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
