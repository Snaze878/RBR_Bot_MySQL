import discord
import asyncio
import requests
import random
import aiohttp
import time
import csv
import logging
import sys
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from discord.ext import commands, tasks
from dotenv import load_dotenv, dotenv_values
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import os
import aiomysql
import re
from collections import defaultdict
from discord.ui import View, Button
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# Reconnect tracking
reconnect_failures = 0
# --- Task Registry ---
running_tasks = {}
last_reconnect_time = None

# --- Logging Setup ---
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# === Function to create a timed rotating logger ===
def create_logger_handler(name, level=logging.DEBUG):
    handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, name),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    handler.setLevel(level)
    handler.setFormatter(log_format)
    handler.suffix = "%Y-%m-%d.txt"
    handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}.txt$")
    return handler

# Discord logger
discord_handler = create_logger_handler("discord_commands_log")
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.DEBUG)
discord_logger.addHandler(discord_handler)

# Scraping logger
scrape_handler = create_logger_handler("scraping_log")
scraping_logger = logging.getLogger("scraping")
scraping_logger.setLevel(logging.DEBUG)
scraping_logger.addHandler(scrape_handler)

# Error logger
error_handler = create_logger_handler("error_log", level=logging.WARNING)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(error_handler)


# --- Environment Loading ---
load_dotenv()
env_data = dotenv_values(".env")
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
INFO_URL = os.getenv("INFO_URL")
RALLY_NAME = os.getenv("RALLY_NAME")
RALLY_PASSWORD = os.getenv("RALLY_PASSWORD")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID"))

# === Points Mapping (Top 10 Scoring System) ===
POINTS_MAP = {
    1: 25,
    2: 17,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1
}

# --- MySQL Connection ---
async def get_db_connection():
    return await aiomysql.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        db=os.getenv("MYSQL_DATABASE"),
        autocommit=True
    )

async def safe_db_call(func, *args, **kwargs):
    max_retries = 999999  # infinite retry loop
    delay = 60  # seconds between retries

    for _ in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except (aiomysql.Error, ConnectionError) as e:
            logging.warning(f"[DB Retry] DB access failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            logging.error(f"[DB Retry] Unexpected error: {e}")
            return None

def reload_env():
    load_dotenv(override=True)
    global env_data
    env_data = dotenv_values(".env")
    print("🔁 Reloaded .env → latest env_data now in memory.")


#Google Spreadsheet Hook

def sync_from_google_sheet():
    try:
        # Setup access to Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        client = gspread.authorize(creds)

        # Open the Google spreadsheet
        spreadsheet = client.open(os.getenv("GOOGLE_SHEET_NAME"))


        # === Get Latest Rally Config from Form Sheet ===
        form_sheet = spreadsheet.sheet1
        records = form_sheet.get_all_records()

        if not records:
            print("⚠️ No data found in main sheet.")
            return False

        latest = records[-1]
        print(f"📥 Syncing rally config: {latest}")

        season = int(latest['Season Number'])
        week = int(latest['Week Number'])
        sw_prefix = f"S{season}W{week}"

        # === Build new environment variables ===
        new_env_vars = {
            f"{sw_prefix}_LEADERBOARD": latest.get("Leaderboard URL", "").strip()
        }

        # Add rally name only if "New Rally Name" exists
        rally_name_from_sheet = latest.get("New Rally Name", "").strip()
        if rally_name_from_sheet:
            new_env_vars["RALLY_NAME"] = rally_name_from_sheet

        # Add leg URLs
        for key, value in latest.items():
            if "LEG" in key.upper() and "URL" in key.upper() and value.strip():
                leg_stage = key.upper().replace("LEG ", "LEG_").replace("STAGE ", "").replace(" URL", "").replace("  ", " ")
                leg_stage = "_".join(leg_stage.split())
                full_key = f"{sw_prefix}_{leg_stage}"
                new_env_vars[full_key] = value.strip()

        # === Load existing .env file ===
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        env_dict = {}
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        env_dict[k] = v

        # Merge with new vars (overwrites if keys exist)
        env_dict.update(new_env_vars)

        # Write the updated .env file
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")

        print(f"✅ .env file updated with S{season}W{week} config")

        # ✅ Reload environment variables into memory
        reload_env()


        return True

    except Exception as e:
        print(f"❌ sync_from_google_sheet() failed: {e}")
        import traceback
        traceback.print_exc()
        return False






# Syncing with Google Handler
# Replace this with your actual Discord ID(s)
# Load allowed sync users from .env
ALLOWED_SYNC_USERS = [
    int(uid.strip()) for uid in os.getenv("ALLOWED_SYNC_USERS", "").split(",") if uid.strip().isdigit()
]


async def handle_sync_command(message):
    if message.author.id not in ALLOWED_SYNC_USERS:
        await message.channel.send("❌ You don’t have permission to use this command.")
        return

    try:
        await message.channel.send("🔄 Syncing latest rally data from Google Sheets...")

        previous_weeks = get_all_season_weeks()
        previous_latest = previous_weeks[-1] if previous_weeks else None

        success = sync_from_google_sheet()

        if not success:
            await message.channel.send("⚠️ Sync failed. Check logs for more details.")
            return

        updated_weeks = get_all_season_weeks()
        updated_latest = updated_weeks[-1] if updated_weeks else None

        summary_lines = []

        # ✅ Reassign points for all previous weeks (not current week)
        for sw_key in updated_weeks[:-1]:
            season, week = parse_season_week_key(sw_key)
            await assign_points_for_week(season, week)
            summary_lines.append(f"🔁 Points rechecked for S{season}W{week}")

        if updated_latest and updated_latest != previous_latest:
            season, week = parse_season_week_key(updated_latest)
            summary_lines.append(f"🆕 **New Week Detected:** Season {season}, Week {week}")
            scraped_tracks = 0
            failed_tracks = 0

            leg_urls = build_urls_for_week(season, week)
            for leg, stages in leg_urls.items():
                for stage, url in stages.items():
                    if url:
                        leaderboard = await scrape_leaderboard(url)
                        if leaderboard:
                            track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                            await safe_db_call(update_previous_leader, track_name, leaderboard[0]["name"])
                            await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week, url)
                            scraped_tracks += 1
                        else:
                            failed_tracks += 1

            leaderboard_url = get_leaderboard_url(season, week)
            if leaderboard_url:
                general_leaderboard, soup = await scrape_general_leaderboard(leaderboard_url)
                if general_leaderboard:
                    await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

                left_leaderboard = await scrape_left_leaderboard(leaderboard_url)
                if left_leaderboard:
                    await safe_db_call(log_left_leaderboard_to_db, "General Leaderboard Left", left_leaderboard, season, week)

            # ✅ Bootstrap new week (like on_ready)
            logging.info(f"🧩 Bootstrapping new week S{season}W{week} into main loop")
            start_background_task("check_current_week_loop", check_current_week_loop(message.channel)) # ✅ runs in background

            track_name = f"S{season}W{week} - General Leaderboard"
            if leaderboard_url and general_leaderboard:
                await safe_db_call(update_previous_leader, track_name, general_leaderboard[0]["name"])

            logging.info(f"✅ Bootstrapped and started tracking S{season}W{week}")
        else:
            summary_lines.append("✅ No new week found. Existing week data remains unchanged.")

        await message.channel.send(
            "✅ Successfully synced from Google Sheets!\n"
            "• `.env` file updated\n"
            "• Points reassigned where needed\n"
            "• `!info` and `!points` now reflect the latest data"
        )

        embed = discord.Embed(
            title="📦 Sync Summary",
            description="\n".join(summary_lines),
            color=discord.Color.green()
        )
        await message.channel.send(embed=embed)

    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"[ERROR] Sync command failed: {e}")
        await message.channel.send("❌ Sync failed due to an internal error.")


def start_background_task(name: str, coro: callable):
    reload_env()
    global running_tasks

    if name in running_tasks and not running_tasks[name].done():
        logging.info(f"🔁 Task '{name}' is already running. Skipping duplicate launch.")
        return

    task = asyncio.create_task(coro)

    def cleanup(_):
        if name in running_tasks and running_tasks[name].done():
            del running_tasks[name]
            logging.info(f"🧹 Task '{name}' finished and was cleaned up.")

    task.add_done_callback(cleanup)
    running_tasks[name] = task
    logging.info(f"🚀 Started task: {name}")



async def get_driver_progress(driver_name):
    try:
        season, week = get_latest_season_and_week()
        urls_by_leg = build_urls_for_week(season, week)

        # ✅ Only consider stages with valid URLs
        expected_tracks = [
            (leg, stage, f"S{season}W{week} - Leg {leg} (Stage {stage})")
            for leg, stages in urls_by_leg.items()
            for stage in stages
        ]

        # ⚠️ If no URLs are defined yet, show message
        if not expected_tracks:
            embed = discord.Embed(
                title=f"📍 Progress for {driver_name}",
                description=f"**Season {season}, Week {week}**\n⚠️ No stage URLs defined for this week yet.",
                color=discord.Color.orange()
            )
            embed.set_footer(text="Progress unavailable")
            return embed

        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT track_name FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND season = %s AND week = %s
            """, (f"%{driver_name.lower()}%", season, week))

            results = await cursor.fetchall()
        await conn.ensure_closed()

        completed_tracks = {row["track_name"] for row in results}
        total = len(expected_tracks)
        done = 0

        leg_blocks = {}
        for leg, stage, track in expected_tracks:
            status = "✅" if track in completed_tracks else "❌"
            if track in completed_tracks:
                done += 1
            leg_blocks.setdefault(leg, []).append(f"{status} Stage {stage}")

        embed = discord.Embed(
            title=f"📍 Progress for {driver_name}",
            description=f"**Season {season}, Week {week}**",
            color=discord.Color.purple()
        )

        for leg in sorted(leg_blocks.keys()):
            embed.add_field(
                name=f"🧭 Leg {leg}",
                value="\n".join(leg_blocks[leg]),
                inline=False
            )

        if done == 0:
            embed.description += "\n\n🚧 This driver hasn’t started any stages yet."

        embed.set_footer(text=f"{done}/{total} stages completed")
        return embed

    except Exception as e:
        logging.error(f"[ERROR] get_driver_progress failed: {e}")
        return None


async def assign_points_for_week(season, week):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # ✅ Check if points were already assigned for this week
            await cursor.execute("""
                SELECT 1 FROM assigned_points_weeks
                WHERE season = %s AND week = %s
                LIMIT 1
            """, (season, week))
            if await cursor.fetchone():
                logging.info(f"[Points] Already assigned for S{season}W{week}. Skipping.")
                await conn.ensure_closed()
                return

            # ✅ Get top 10 from general_leaderboard_log
            await cursor.execute("""
                SELECT driver_name, position
                FROM general_leaderboard_log
                WHERE season = %s AND week = %s AND position <= 10
                ORDER BY position ASC
            """, (season, week))
            rows = await cursor.fetchall()

            if not rows:
                logging.info(f"[Points] No data found for S{season}W{week}.")
                await conn.ensure_closed()
                return

            for row in rows:
                driver = row["driver_name"]
                pos = row["position"]
                points = POINTS_MAP.get(pos, 0)

                await cursor.execute("""
                    INSERT INTO season_points (driver_name, season, points)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE points = points + %s
                """, (driver, season, points, points))

            # ✅ Mark this week as processed
            await cursor.execute("""
                INSERT INTO assigned_points_weeks (season, week)
                VALUES (%s, %s)
            """, (season, week))

        await conn.ensure_closed()
        logging.info(f"[Points] Successfully assigned for S{season}W{week}.")

    except Exception as e:
        logging.error(f"[Points] ERROR in S{season}W{week}: {e}")





async def handle_recalpoints_command(message):
    try:
        all_weeks = get_all_season_weeks()
        if len(all_weeks) < 2:
            await message.channel.send("⚠️ Not enough completed weeks to recalculate points.")
            return

        current_key = all_weeks[-1]
        current_season, current_week = parse_season_week_key(current_key)

        updated = 0
        for sw_key in all_weeks:
            season, week = parse_season_week_key(sw_key)
            if season == current_season and week == current_week:
                continue  # skip current/latest week

            await assign_points_for_week(season, week)
            updated += 1
            logging.info(f"[Points] Recalculated for S{season}W{week}")

        await message.channel.send(f"✅ Recalculated points for **{updated} previous week(s)** (excluding current week S{current_season}W{current_week}).")

    except Exception as e:
        logging.error(f"[ERROR] recalpoints command failed: {e}")
        await message.channel.send("❌ Failed to recalculate previous weeks' points.")





async def get_driver_stats(driver_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # ✅ First check if driver exists in leaderboard_log_left
            await cursor.execute("""
                SELECT COUNT(*) as exists_check
                FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s
            """, (f"%{driver_name.lower()}%",))
            exists_row = await cursor.fetchone()
            if not exists_row or exists_row["exists_check"] == 0:
                return f"❌ No records found for **{driver_name}**. Please check the spelling or try a different name."

            # Total events (exclude 9999)
            await cursor.execute("""
                SELECT COUNT(*) as total_events FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND position < 9999
            """, (f"%{driver_name.lower()}%",))
            total_events = (await cursor.fetchone())["total_events"]

            # Avg Position
            await cursor.execute("""
                SELECT AVG(position) as avg_position FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND position < 9999
            """, (f"%{driver_name.lower()}%",))
            avg_position = (await cursor.fetchone())["avg_position"]

            # Best Finish
            await cursor.execute("""
                SELECT position, track_name FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND position < 9999
                ORDER BY position ASC LIMIT 1
            """, (f"%{driver_name.lower()}%",))
            best_row = await cursor.fetchone()
            best_finish = (
                f"{best_row['position']}{get_position_suffix(best_row['position'])} in {best_row['track_name']}"
                if best_row else "N/A"
            )

            # Podiums
            await cursor.execute("""
                SELECT COUNT(*) as podiums FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND position <= 3
            """, (f"%{driver_name.lower()}%",))
            podiums = (await cursor.fetchone())["podiums"]

            # Wins
            await cursor.execute("""
                SELECT COUNT(*) as wins FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND position = 1
            """, (f"%{driver_name.lower()}%",))
            wins = (await cursor.fetchone())["wins"]

            # Most Used Vehicle (LEFT → fallback RIGHT)
            await cursor.execute("""
                SELECT vehicle, COUNT(*) as count FROM leaderboard_log_left
                WHERE LOWER(driver_name) LIKE %s AND vehicle IS NOT NULL AND vehicle != ''
                GROUP BY vehicle ORDER BY count DESC LIMIT 1
            """, (f"%{driver_name.lower()}%",))
            vehicle_row = await cursor.fetchone()
            if not vehicle_row:
                await cursor.execute("""
                    SELECT vehicle, COUNT(*) as count FROM leaderboard_log
                    WHERE LOWER(driver_name) LIKE %s AND vehicle IS NOT NULL AND vehicle != ''
                    GROUP BY vehicle ORDER BY count DESC LIMIT 1
                """, (f"%{driver_name.lower()}%",))
                vehicle_row = await cursor.fetchone()
            most_vehicle = vehicle_row["vehicle"] if vehicle_row else "Unknown"

        await conn.ensure_closed()

        # ✅ Pull points
        season, _ = get_latest_season_and_week()
        conn2 = await get_db_connection()
        async with conn2.cursor(aiomysql.DictCursor) as cursor2:
            await cursor2.execute("""
                SELECT points FROM season_points
                WHERE LOWER(driver_name) LIKE %s AND season = %s
                LIMIT 1
            """, (f"%{driver_name.lower()}%", season))
            result = await cursor2.fetchone()
            points = result['points'] if result else "N/A"

        await conn2.ensure_closed()

        embed = discord.Embed(
            title=f"📊 Stats for {driver_name}",
            color=discord.Color.teal()
        )
        embed.add_field(name="🎯 Total Events", value=total_events, inline=True)
        embed.add_field(name="📈 Avg Position", value=f"{avg_position:.2f}" if avg_position else "N/A", inline=True)
        embed.add_field(name="🏆 Best Finish", value=best_finish, inline=False)
        embed.add_field(name="🥇 Wins", value=wins, inline=True)
        embed.add_field(name="🥉 Podiums", value=podiums, inline=True)
        embed.add_field(name="🏎️ Most Used Car", value=most_vehicle, inline=False)
        embed.add_field(name="🏁 Points", value=f"{points} pts", inline=False)

        return embed

    except Exception as e:
        logging.error(f"[ERROR] get_driver_stats failed: {e}")
        return "❌ Something went wrong fetching stats."






async def get_driver_trend(driver_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            driver_name_lower = driver_name.lower()
            all_weeks = get_all_season_weeks()
            if not all_weeks:
                return None

            trend_data = []
            previous_position = None

            for sw in all_weeks:
                try:
                    season, week = parse_season_week_key(sw)
                except ValueError:
                    continue

                await cursor.execute("""
                    SELECT position, diff_first, time
                    FROM general_leaderboard_log
                    WHERE LOWER(driver_name) LIKE %s AND season = %s AND week = %s
                    ORDER BY position ASC
                    LIMIT 1
                """, (f"%{driver_name_lower}%", season, week))

                result = await cursor.fetchone()

                label = f"S{season}W{week}"

                if result:
                    pos = result['position']
                    gap = result['diff_first']
                    time_total = result['time']

                    # Icons for position
                    if pos == 1:
                        icon = "🥇"
                    elif pos == 2:
                        icon = "🥈"
                    elif pos == 3:
                        icon = "🥉"
                    else:
                        icon = ""

                    # Arrow based on movement
                    if previous_position is not None:
                        if pos < previous_position:
                            trend = "⬆️"
                        elif pos > previous_position:
                            trend = "⬇️"
                        else:
                            trend = "➡️"
                    else:
                        trend = ""

                    previous_position = pos

                    line = f"{icon} Pos: {pos} {trend}\n⏱️ {time_total}\nGap: {gap}"
                else:
                    line = "❌ Did not complete"
                    previous_position = None  # Reset for skipped week

                trend_data.append((label, line))

        await conn.ensure_closed()

        embed = discord.Embed(
            title=f"📈 Trend for {driver_name}",
            description="Weekly performance breakdown",
            color=discord.Color.orange()
        )

        for label, line in trend_data:
            embed.add_field(name=label, value=line, inline=False)

        return embed

    except Exception as e:
        logging.error(f"[ERROR] get_driver_trend failed: {e}")
        return None




def get_position_suffix(position):
    if 11 <= position % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")



async def search_driver(driver_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = """
                SELECT track_name, position, driver_name, vehicle, time, diff_first, scraped_at
                FROM leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
                ORDER BY scraped_at DESC
                LIMIT 10
            """
            await cursor.execute(query, (f"%{driver_name}%",))
            results = await cursor.fetchall()
        await conn.ensure_closed()

        if results:
            full_name = results[0]['driver_name']
            print(f"🔍 Results for driver: {full_name}")
            results.insert(0, {"full_name": full_name})

        return results
    except Exception as e:
        print(f"❌ Failed to search driver: {e}")
        return []


async def reconnect_watchdog_loop():
    await bot.wait_until_ready()
    global reconnect_failures, last_reconnect_time

    while not bot.is_closed():
        await asyncio.sleep(60)  # Check every 60 seconds
        if reconnect_failures >= 5:
            now = datetime.utcnow()
            elapsed = now - (last_reconnect_time or now)

            if elapsed > timedelta(minutes=2):
                try:
                    channel = bot.get_channel(CHANNEL_ID)
                    if channel:
                        await channel.send(f"<@{BOT_OWNER_ID}> ⚠️ The bot appears to be stuck in a reconnect loop.")
                        logging.info("[Watchdog] Alert sent to channel.")
                    else:
                        logging.warning("[Watchdog] Could not find channel to send reconnect alert.")
                except Exception as e:
                    logging.warning(f"[Watchdog] Failed to send alert: {e}")

                # Reset counters
                reconnect_failures = 0
                last_reconnect_time = None


async def notify_owner_if_stuck():
    global reconnect_failures, last_reconnect_time

    reconnect_failures += 1
    now = datetime.utcnow()

    if last_reconnect_time is None:
        last_reconnect_time = now

    elapsed = now - last_reconnect_time
    if reconnect_failures >= 5 and elapsed > timedelta(minutes=2):
        logging.warning(f"[Watchdog] Bot has failed to reconnect {reconnect_failures} times over {elapsed}.")

        try:
            channel = bot.get_channel(CHANNEL_ID)
            if channel:
                await channel.send(f"<@{BOT_OWNER_ID}> ⚠️ The bot appears to be stuck in a reconnect loop.")
                logging.info("[Watchdog] Sent stuck reconnect alert to channel.")
            else:
                logging.warning("[Watchdog] Channel not found — cannot send reconnect alert.")
        except Exception as e:
            logging.warning(f"[Watchdog] Failed to send reconnect alert in channel: {e}")

        reconnect_failures = 0
        last_reconnect_time = None




# Function to get the previous leader from DB
async def get_previous_leader(track_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT leader_name FROM previous_leaders WHERE track_name = %s", (track_name,))
            result = await cursor.fetchone()
        await conn.ensure_closed()
        return result['leader_name'] if result else None
    except Exception as e:
        print(f"❌ Failed to get previous leader for {track_name}: {e}")
        return None
    

async def get_latest_left_leader(track_name, season, week):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT driver_name FROM leaderboard_log_left
                WHERE track_name = %s AND season = %s AND week = %s
                ORDER BY position ASC LIMIT 1
            """, (track_name, season, week))
            row = await cursor.fetchone()
        await conn.ensure_closed()
        return row["driver_name"] if row else None
    except Exception as e:
        logging.error(f"[ERROR] get_latest_left_leader failed: {e}")
        return None




async def show_driver_results(driver_name, season=None, week=None):
    try:
        if season is None or week is None:
            season, week = get_latest_season_and_week()

        leaderboard_url = get_leaderboard_url(season, week)

        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT vehicle FROM leaderboard_log
                WHERE driver_name LIKE %s AND season = %s AND week = %s
                AND vehicle IS NOT NULL AND vehicle != ''
                LIMIT 1
            """, (f"%{driver_name}%", season, week))

            vehicle_result = await cursor.fetchone()
            vehicle = vehicle_result['vehicle'] if vehicle_result else "Unknown"

            await cursor.execute("""
                SELECT track_name, position, diff_first
                FROM leaderboard_log
                WHERE driver_name LIKE %s AND season = %s AND week = %s
                ORDER BY scraped_at DESC
            """, (f"%{driver_name}%", season, week))

            results = await cursor.fetchall()
        await conn.ensure_closed()

        if not results:
            return f"⚠️ No results found for `{driver_name}` in Season {season}, Week {week}."

        general_leaderboard, _ = await scrape_general_leaderboard(leaderboard_url)
        name_parts = [p.strip() for p in driver_name.split("/") if p.strip()]

        current_overall = next(
            (entry for entry in general_leaderboard
             if any(part.lower() in entry['name'].lower() for part in name_parts)),
            None
        )

        if not current_overall:
            current_overall = next(
                (entry for entry in general_leaderboard if driver_name.lower() in entry["name"].lower()),
                None
            )

        # 🔄 Pull points from season_points table
        points_line = "N/A"
        season, _ = get_latest_season_and_week()

        try:
            conn = await get_db_connection()
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                name_parts = [p.strip().lower() for p in driver_name.split("/") if p.strip()]
                like_clauses = " OR ".join(["LOWER(driver_name) LIKE %s" for _ in name_parts])
                query = f"""
                    SELECT points FROM season_points
                    WHERE season = %s AND ({like_clauses})
                    ORDER BY points DESC LIMIT 1
                """
                await cursor.execute(query, [season] + [f"%{part}%" for part in name_parts])
                row = await cursor.fetchone()
                if row:
                    points_line = row["points"]
            await conn.ensure_closed()
        except Exception as e:
            logging.warning(f"Could not retrieve points from DB: {e}")


        # Organize results per leg
        organized = defaultdict(list)
        for entry in results:
            raw_track = entry.get("track_name", "")
            position = entry.get("position", "?")
            diff_first = entry.get("diff_first", "?")

            match = re.search(r"Leg\s*(\d+).+Stage\s*(\d+)", raw_track)
            if match:
                leg_num = int(match.group(1))
                stage_num = int(match.group(2))
                track_label = f"Stage {stage_num}"
                line = f"**Pos - {position}** {track_label} ⏳ ({diff_first})"
                organized[f"Leg {leg_num}"].append((stage_num, line))

        formatted_blocks = []
        for leg in sorted(organized.keys(), key=lambda x: int(x.split()[1])):
            stage_lines = sorted(organized[leg])
            block = f"{leg}\n" + "\n".join(line for _, line in stage_lines)
            formatted_blocks.append(block)

        matched_name = current_overall['name'] if current_overall else driver_name

        # --- Create Embed ---
        embed = discord.Embed(
            title=f"🔍 Results for {driver_name}",
            description=f"Season {season}, Week {week}",
            color=discord.Color.green()
        )

        if current_overall:
            embed.add_field(name="📊 Current Position", value=current_overall['position'], inline=False)
            embed.add_field(name="⏱️ Time Diff", value=current_overall['diff_first'], inline=False)
        else:
            embed.add_field(name="📊 Current Position", value="Not Found", inline=False)

        embed.add_field(name="🏎️ Vehicle", value=vehicle, inline=False)

        if points_line:
            embed.add_field(name="🏁 Points", value=f"{points_line} pts", inline=False)

        # Add empty line to give spacing before legs
        embed.add_field(name="\u200B", value="\u200B", inline=False)

        # Stage/leg breakdown
        for block in formatted_blocks:
            lines = block.split("\n")
            title = lines[0]
            value = "\n".join(lines[1:])
            embed.add_field(name=title, value=value, inline=False)

        return embed



    except Exception as e:
        logging.error(f"[ERROR] show_driver_results failed: {e}")
        return "❌ An error occurred while building driver results."




# Function to update the leader in DB
async def update_previous_leader(track_name, leader_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute(
                "REPLACE INTO previous_leaders (track_name, leader_name) VALUES (%s, %s)",
                (track_name, leader_name)
            )
        await conn.ensure_closed()
    except Exception as e:
        logging.error(f"❌ Failed to update previous leader for {track_name}: {e}")





def get_leaderboard_url(season, week):
    key = f"S{season}W{week}_LEADERBOARD"
    return env_data.get(key)


def get_all_season_weeks():
    global env_data  # 👈 This is key!
    sw_keys = set()
    for key in env_data:
        if key.startswith("S") and "_LEG_" in key:
            sw_keys.add(key.split("_")[0])

    def sort_key(sw):
        match = re.match(r"S(\d+)W(\d+)", sw)
        return (int(match.group(1)), int(match.group(2))) if match else (0, 0)

    return sorted(sw_keys, key=sort_key)

def get_latest_season_and_week():
    weeks = get_all_season_weeks()
    if not weeks:
        return None, None

    season_week_map = defaultdict(list)
    for sw in weeks:
        season, week = parse_season_week_key(sw)
        season_week_map[season].append(week)

    latest_season = max(season_week_map.keys())
    latest_week = max(season_week_map[latest_season])

    return latest_season, latest_week






async def log_general_leaderboard_to_db(season, week, soup):
    scraping_logger.info(f"🔁 Starting general leaderboard log for Season {season}, Week {week}")
    tables = soup.find_all("table", {"class": "rally_results"})
    if not tables:
        scraping_logger.warning("❌ No tables found for general leaderboard.")
        return

    results_table = next((t for t in tables if len(t.find_all("tr")) > 1), None)
    if not results_table:
        scraping_logger.warning("❌ No valid results table found.")
        return

    rows = results_table.find_all("tr")
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        # 🔥 Delete old general leaderboard entries for this season/week
        await cursor.execute("""
            DELETE FROM general_leaderboard_log
            WHERE season = %s AND week = %s
        """, (season, week))

        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 7:  # changed from 6 to 7 due to extra column
                try:
                    position = int(cols[0].text.strip())
                    driver_name = cols[1].text.strip()
                    vehicle = cols[3].text.strip()       # fixed index
                    time = cols[4].text.strip()
                    diff_prev = cols[5].text.strip()
                    diff_first = cols[6].text.strip()

                    await cursor.execute("""
                        INSERT INTO general_leaderboard_log 
                        (driver_name, position, vehicle, time, diff_prev, diff_first, season, week)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (driver_name, position, vehicle, time, diff_prev, diff_first, season, week))
                except Exception as e:
                    scraping_logger.error(f"⚠️ Failed to insert row: {e}")
    await conn.ensure_closed()
    scraping_logger.info(f"✅ Replaced general leaderboard entries for S{season}W{week}")
    print(f"✅ Logged general leaderboard entries for S{season}W{week}")






def parse_season_week_key(sw_key):
    match = re.match(r"S(\d+)W(\d+)", sw_key)
    if match:
        season, week = int(match.group(1)), int(match.group(2))
        return season, week
    raise ValueError(f"Invalid season/week format: {sw_key}")



# Function to log leaderboard data to MySQL (RIGHT + LEFT)
async def log_leaderboard_to_db(track_name, leaderboard, season=None, week=None, url=None):
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            # === Step 1: Clear existing entries from RIGHT table ===
            await cursor.execute("""
                DELETE FROM leaderboard_log 
                WHERE track_name = %s AND season = %s AND week = %s
            """, (track_name, season, week))

            # === Step 2: Insert new RIGHT table entries ===
            right_query = """
                INSERT INTO leaderboard_log 
                (track_name, position, driver_name, vehicle, time, diff_prev, diff_first, season, week)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            for entry in leaderboard:
                try:
                    await cursor.execute(right_query, (
                        track_name,
                        int(entry.get("position", 0)),
                        entry.get("name"),
                        entry.get("vehicle"),
                        entry.get("time", ""),
                        entry.get("diff_prev", ""),
                        entry.get("diff_first", ""),
                        season,
                        week
                    ))
                except Exception as e:
                    logging.warning(f"⚠️ RIGHT insert failed for {track_name}: {e}")

            # === Step 3: Scrape and insert LEFT leaderboard ===
            if url:
                left_leaderboard = await scrape_left_leaderboard(url)

                # Delete old LEFT entries
                await cursor.execute("""
                    DELETE FROM leaderboard_log_left 
                    WHERE track_name = %s AND season = %s AND week = %s
                """, (track_name, season, week))

                left_query = """
                    INSERT INTO leaderboard_log_left 
                    (track_name, position, driver_name, vehicle, time, diff_prev, diff_first, season, week)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                for entry in left_leaderboard:
                    raw_pos = entry.get("position", "0")
                    try:
                        position = int(raw_pos)
                    except Exception:
                        logging.warning(f"[Fallback] Non-numeric position: '{raw_pos}' in {track_name} — using 9999")
                        position = 9999

                    try:
                        await cursor.execute(left_query, (
                            track_name,
                            position,
                            entry.get("name"),
                            entry.get("vehicle", ""),
                            entry.get("time", ""),
                            entry.get("diff_prev", ""),
                            entry.get("diff_first", ""),
                            season,
                            week
                        ))
                    except Exception as e:
                        logging.error(f"❌ LEFT insert failed for {track_name} entry {entry}: {e}")

        await conn.ensure_closed()
        print(f"✅ Logged RIGHT and LEFT leaderboard entries for {track_name}")

    except Exception as e:
        logging.error(f"❌ Failed to update leaderboard for {track_name}: {e}")




async def handle_points_command(message):
    try:
        season, _ = get_latest_season_and_week()

        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT driver_name, points
                FROM season_points
                WHERE season = %s
                ORDER BY points DESC, driver_name ASC
            """, (season,))
            rows = await cursor.fetchall()
        await conn.ensure_closed()

        if not rows:
            await message.channel.send("⚠️ No points data found for the current season.")
            return

        embed = discord.Embed(
            title=f"🏁 Season {season} RBR Standings",
            color=discord.Color.gold()
        )

        points_lines = []
        podium = {1: "🥇", 2: "🥈", 3: "🥉"}

        for i, row in enumerate(rows, start=1):
            icon = podium.get(i, f"#{i}")
            driver = row["driver_name"]
            points = row["points"]
            points_lines.append(f"{icon} **{driver}** — {points} pts")

        full_points = "\n\n".join(points_lines)
        embed.add_field(name="📋 Driver Points", value="** **\n" + full_points, inline=False)

        await message.channel.send(embed=embed)

    except Exception as e:
        logging.error(f"[ERROR] handle_points_command failed: {e}")
        await message.channel.send("❌ Could not retrieve points.")





# ─── ENV LOADING ───
load_dotenv()


class CompareDriver1Select(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select Driver 1", options=options)

    async def callback(self, interaction: discord.Interaction):
        driver1 = self.values[0].strip()

        await interaction.response.defer()  # ✅ Acknowledge interaction immediately

        # Disable the dropdown in the original view
        for child in self.view.children:
            child.disabled = True

        try:
            await interaction.edit_original_response(view=self.view)

            driver_names = await get_all_driver_names()
            driver_names = [name for name in driver_names if name != driver1]

            view = CompareDriver2View(driver1, driver_names)
            await interaction.followup.send(
                f"🆚 Now pick someone to compare against `{driver1}`:",
                view=view
            )
        except Exception as e:
            logging.error(f"[Compare] Failed to show second dropdown: {e}")
            await interaction.followup.send("❌ Failed to show second dropdown.")



class CompareDriver2Select(discord.ui.Select):
    def __init__(self, driver1, driver_names):
        self.driver1 = driver1
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select Driver 2", options=options)

    async def callback(self, interaction: discord.Interaction):
        driver2 = self.values[0].strip()

        await interaction.response.defer()  # ✅ Acknowledge interaction first

        # Disable the dropdown
        for child in self.view.children:
            child.disabled = True

        try:
            await interaction.edit_original_response(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable CompareDriver2 dropdown: {e}")

        # Simulate a message object so we can call the same handler
        class FakeMessage:
            def __init__(self, content, author, channel):
                self.content = content
                self.author = author
                self.channel = channel

        fake_msg = FakeMessage(
            content=f"!compare {self.driver1} vs {driver2}",
            author=interaction.user,
            channel=interaction.channel
        )

        try:
            await handle_compare_command(fake_msg)
        except Exception as e:
            logging.error(f"[Compare] Failed to process comparison: {e}")
            await interaction.followup.send("❌ Failed to generate comparison.")





class CompareDriver1View(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(CompareDriver1Select(driver_names))


class CompareDriver2View(discord.ui.View):
    def __init__(self, driver1, driver_names):
        super().__init__(timeout=60)
        self.add_item(CompareDriver2Select(driver1, driver_names))



class DriverSelect(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select a driver", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_driver = self.values[0].strip()
        await interaction.response.defer(ephemeral=False)

        # Disable this dropdown
        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable DriverSelect dropdown: {e}")

        # Send Season/Week selector
        try:
            season_weeks = get_all_season_weeks()
            new_view = discord.ui.View(timeout=60)
            new_view.add_item(SeasonWeekSelect(selected_driver, season_weeks))
            await interaction.followup.send(
                f"📆 Select a Season/Week for `{selected_driver}`:",
                view=new_view
            )
        except Exception as e:
            logging.error(f"❌ Failed to show season/week selector: {e}")
            try:
                await interaction.channel.send(f"⚠️ Failed to show selector for `{selected_driver}`.")
            except:
                pass


class StatsDriverSelect(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select a driver", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_driver = self.values[0].strip()
        await interaction.response.defer(ephemeral=False)

        # Disable the dropdown
        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable StatsDriverSelect dropdown: {e}")

        # Fetch stats
        embed = await get_driver_stats(selected_driver)
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to fetch stats.")

class HistoryDriverSelect(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select a driver", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_label = self.values[0].strip()
        await interaction.response.defer(ephemeral=False)

        # Disable dropdown
        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable dropdown: {e}")

        # Extract usable driver name
        name_parts = [p.strip() for p in selected_label.split("/") if p.strip()]
        query_name = name_parts[-1] if name_parts else selected_label  # fallback

        embed = await get_driver_history(query_name)
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Could not fetch driver history.")



class HistoryDriverSearchView(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(HistoryDriverSelect(driver_names))


class TrendDriverSelect(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select a driver to view trend", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_label = self.values[0].strip()
        await interaction.response.defer()

        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable dropdown: {e}")

        # Extract usable search name (e.g., drop prefix/team name if present)
        name_parts = [p.strip() for p in selected_label.split("/") if p.strip()]
        query_name = name_parts[-1] if name_parts else selected_label

        embed = await get_driver_trend(query_name)
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("⚠️ No trend data found.")


class TrendDriverSearchView(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(TrendDriverSelect(driver_names))


class DriverSearchView(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(DriverSelect(driver_names))  # This now points to the second DriverSelect

class StatsDriverSearchView(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(StatsDriverSelect(driver_names))

class ProgressDriverSelect(discord.ui.Select):
    def __init__(self, driver_names):
        options = [
            discord.SelectOption(label=name, value=name)
            for name in sorted(driver_names)[:25]
        ]
        super().__init__(placeholder="Select a driver to view progress", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_driver = self.values[0].strip()
        await interaction.response.defer()

        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable dropdown: {e}")

        embed = await get_driver_progress(selected_driver)
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Could not retrieve progress data.")

class ProgressDriverSearchView(discord.ui.View):
    def __init__(self, driver_names):
        super().__init__(timeout=60)
        self.add_item(ProgressDriverSelect(driver_names))


class SeasonWeekSelect(discord.ui.Select):
    def __init__(self, driver_name, season_weeks):
        options = [
            discord.SelectOption(
                label=sw.replace("S", "Season ").replace("W", " Week "),
                value=sw
            )
            for sw in season_weeks
        ]
        super().__init__(placeholder="Select Season/Week", options=options)
        self.driver_name = driver_name

    async def callback(self, interaction: discord.Interaction):
        selected_sw = self.values[0]
        await interaction.response.defer(ephemeral=False)

        match = re.match(r"S(\d+)W(\d+)", selected_sw)
        if not match:
            await interaction.followup.send("⚠️ Invalid Season/Week selection.")
            return

        season = int(match.group(1))
        week = int(match.group(2))

        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable SeasonWeek dropdown: {e}")

        try:
            result_text = await show_driver_results(self.driver_name, season, week)
            if isinstance(result_text, discord.Embed):
                await interaction.followup.send(embed=result_text)
            else:
                await interaction.followup.send(result_text)
        except Exception as e:
            logging.error(f"❌ Failed to send driver results: {e}")
            await interaction.followup.send("❌ An error occurred showing the results.")








class LeaderboardLinkView(View):
    def __init__(self, links: dict):
        super().__init__(timeout=None)
        for label, url in links.items():
            if isinstance(url, str):
                self.add_item(Button(label=label, url=url))

async def scrape_general_leaderboard(url, table_class="rally_results", max_retries=999999, retry_delay=30):
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        raise Exception(f"Non-200 status code: {response.status}")
                    text = await response.text()
                    break
        except Exception as e:
            logging.warning(f"[GENERAL] Error fetching {url} (Attempt {attempt + 1}): {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
    else:
        logging.error(f"[GENERAL] Max retries exceeded for {url}")
        return [], None

    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table", {"class": table_class})
    if not tables:
        logging.warning(f"[GENERAL] Table not found for {url}!")
        return [], soup

    leaderboard = []

    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue

        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 8:
                entry = {
                    "position": cols[0].text.strip(),
                    "name": cols[1].text.strip(),
                    "vehicle": cols[3].text.strip(),
                    "time": cols[4].text.strip(),
                    "diff_prev": cols[5].text.strip(),
                    "diff_first": cols[6].text.strip()
                }
                leaderboard.append(entry)

        if leaderboard:
            break

    logging.info(f"✅ [GENERAL] Scraped {len(leaderboard)} entries from {url}")
    return leaderboard, soup


async def get_all_driver_names():
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 100")
        results = await cursor.fetchall()
    await conn.ensure_closed()
    return [row[0] for row in results]


async def scrape_left_leaderboard(url, table_class="rally_results_stres_left", max_retries=999999, retry_delay=30):
    headers = {"User-Agent": "Mozilla/5.0"}
    vehicle_starts = ["Citroen", "Ford", "Peugeot", "Opel", "Abarth", "Skoda", "Mitsubishi", "Subaru", "BMW", "GM", "GMC",
                      "Toyota", "Honda", "Suzuki", "Acura", "Audi", "Volkswagen", "Chevrolet", "Volvo", "Kia", "Jeep", "Dodge",
                      "Mazda", "Hyundai", "Buick", "MINI", "Porsche", "Mercedes", "Land Rover", "Alfa Romeo", "Lancia"]

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        raise Exception(f"Non-200 status code: {response.status}")
                    text = await response.text()
                    break
        except Exception as e:
            logging.warning(f"[LEFT] Error fetching {url} (Attempt {attempt + 1}): {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
    else:
        logging.error(f"[LEFT] Max retries exceeded for {url}")
        return []

    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table", {"class": table_class})
    if not tables:
        logging.warning(f"[LEFT] No tables found for {url}")
        return []

    table = tables[1] if len(tables) > 1 else tables[0]
    rows = table.find_all("tr")
    leaderboard = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 5:
            position = cols[0].text.strip()
            name_vehicle = cols[1].text.strip()
            time = cols[2].text.strip()
            diff_prev = cols[3].text.strip()
            diff_first = cols[4].text.strip()

            name_parts = name_vehicle.split(" / ", 1)

            if len(name_parts) > 1:
                name1 = name_parts[0].strip()
                name2_vehicle = name_parts[1].strip()
                for brand in vehicle_starts:
                    if brand in name2_vehicle:
                        name2 = name2_vehicle.split(brand, 1)[0].strip()
                        vehicle = brand + " " + name2_vehicle.split(brand, 1)[1].strip()
                        break
                else:
                    name2 = name2_vehicle
                    vehicle = ""
            else:
                combined = name_parts[0].strip()
                for brand in vehicle_starts:
                    if brand in combined:
                        name1 = combined.split(brand, 1)[0].strip()
                        name2 = ""
                        vehicle = brand + " " + combined.split(brand, 1)[1].strip()
                        break
                else:
                    name1 = combined
                    name2 = ""
                    vehicle = ""

            full_name = f"{name1} / {name2}".strip(" /")
            leaderboard.append({
                "position": position,
                "name": full_name,
                "vehicle": vehicle,
                "time": time,
                "diff_prev": diff_prev,
                "diff_first": diff_first
            })

    logging.info(f"✅ [LEFT] Scraped {len(leaderboard)} entries from {url}")
    return leaderboard






def get_season_week_from_page(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        scraping_logger.warning(f"[Season/Week] Failed to fetch {url} (Status code: {response.status_code})")
        return 1, None  # default season to 1 if page fetch fails

    soup = BeautifulSoup(response.text, "html.parser")
    header = soup.find(class_="fejlec4")

    season = None
    week = None

    if header:
        text = header.text.strip()

        # Try to get both Season and Week
        match = re.search(r"Season\s*(\d+)\s*Week\s*(\d+)", text, re.IGNORECASE)
        if match:
            season = int(match.group(1))
            week = int(match.group(2))
        else:
            # Try to get just the Week
            match = re.search(r"Week\s*(\d+)", text, re.IGNORECASE)
            if match:
                week = int(match.group(1))

        # Fallback if season not found
        if season is None:
            season = 1
            scraping_logger.warning(f"[Season/Week] No season found for {url}, defaulting to Season 1")

        scraping_logger.info(f"[Season/Week] Parsed for {url}: Season {season}, Week {week}")
    else:
        scraping_logger.warning(f"[Season/Week] No .fejlec4 element found in {url}, defaulting Season to 1")
        season = 1

    return season, week


async def scrape_leaderboard(url, table_class="rally_results_stres_right"):
    headers = {"User-Agent": "Mozilla/5.0"}
    leaderboard = []

    max_retries = 999999
    delay = 60

    for _ in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        scraping_logger.warning(f"Unable to fetch {url} (Status code: {response.status})")
                        await asyncio.sleep(delay)
                        continue

                    text = await response.text()

            break  # Exit retry loop if successful

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            scraping_logger.warning(f"Failed to fetch {url}: {e}")
            await asyncio.sleep(delay)
        except Exception as e:
            scraping_logger.error(f"Unexpected error fetching {url}: {e}")
            return []

    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table", {"class": table_class})
    if not tables:
        scraping_logger.warning(f"Table not found for {url}!")
        return []

    table = tables[1] if len(tables) > 1 else tables[0]
    rows = table.find_all("tr")
    scraping_logger.info(f"Found {len(rows)} rows for {url}")

    vehicle_starts = [
        "Citroen", "Ford", "Peugeot", "Opel", "Abarth", "Skoda", "Mitsubishi", "Subaru", "BMW", "GM", "GMC",
        "Toyota", "Honda", "Suzuki", "Acura", "Audi", "Volkswagen", "Chevrolet", "Volvo", "Kia", "Jeep", "Dodge",
        "Mazda", "Hyundai", "Buick", "MINI", "Porsche", "Mercedes", "Land Rover", "Alfa Romeo", "Lancia"
    ]

    for index, row in enumerate(rows):
        cols = row.find_all("td")
        if len(cols) >= 5:
            pos = cols[0].text.strip()
            name_vehicle = cols[1].text.strip()
            time = cols[2].text.strip()
            diff_prev = cols[3].text.strip()
            diff_first = cols[4].text.strip()

            name_parts = name_vehicle.split(" / ", 1)

            if len(name_parts) > 1:
                name1 = name_parts[0].strip()
                name2_vehicle = name_parts[1].strip()
                for brand in vehicle_starts:
                    if brand in name2_vehicle:
                        name2 = name2_vehicle.split(brand, 1)[0].strip()
                        vehicle = brand + " " + name2_vehicle.split(brand, 1)[1].strip()
                        break
                else:
                    name2 = name2_vehicle
                    vehicle = ""
            else:
                combined = name_parts[0].strip()
                for brand in vehicle_starts:
                    if brand in combined:
                        name1 = combined.split(brand, 1)[0].strip()
                        name2 = ""
                        vehicle = brand + " " + combined.split(brand, 1)[1].strip()
                        break
                else:
                    name1 = combined
                    name2 = ""
                    vehicle = ""

            full_name = f"{name1} / {name2}".strip(" /")

            entry = {
                "position": pos,
                "name": full_name,
                "vehicle": vehicle,
                "time": time,
                "diff_prev": diff_prev,
                "diff_first": diff_first
            }
            leaderboard.append(entry)
            scraping_logger.debug(f"Row {index + 1} - Added: {entry} from {url}")

    scraping_logger.info(f"✅ Final leaderboard ({len(leaderboard)} entries) for {url}")
    return leaderboard



# Bot setup
TOKEN = os.getenv("DISCORD_BOT_TOKEN")


def build_urls_for_week(season_num, week_num):
    sw_prefix = f"S{season_num}W{week_num}"
    legs = {}

    for key, val in env_data.items():
        if not key.startswith(sw_prefix) or not val:
            continue

        if "LEADERBOARD" in key:
            continue  # handled separately

        parts = key.split("_")
        # Expecting format: S1W1_LEG_1_2 → parts = ['S1W1', 'LEG', '1', '2']
        if len(parts) < 4 or parts[1] != "LEG":
            continue  # skip malformed keys

        try:
            leg = int(parts[2])
            stage = int(parts[3])
        except ValueError:
            continue  # skip if not valid integers

        if leg not in legs:
            legs[leg] = {}
        legs[leg][stage] = val

    return legs


CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)  


async def process_past_weeks(channel):
    try:
        season_weeks = get_all_season_weeks()
        if not season_weeks:
            logging.warning("No season/week data found in .env.")
            return

        latest = season_weeks[-1]
        logging.info(f"⏳ Skipping latest week {latest} during past-week processing.")

        for sw in season_weeks:
            if sw == latest:
                continue  # Skip live week

            # ✅ Use safe parser instead of slicing sw string
            season, week = parse_season_week_key(sw)

            leg_urls = build_urls_for_week(season, week)
            for leg, stages in leg_urls.items():
                for stage, url in stages.items():
                    if not url:
                        continue

                    leaderboard = await scrape_leaderboard(url)
                    if leaderboard:
                        track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                        await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week, url)

                        # ✅ Now safely pull leader from LEFT table
                        current_leader = await safe_db_call(get_latest_left_leader, track_name, season, week)
                        if current_leader:
                            await safe_db_call(update_previous_leader, track_name, current_leader)



            # ✅ Log general leaderboard for past week
            leaderboard_url = get_leaderboard_url(season, week)
            if leaderboard_url:
                general_leaderboard, soup = await scrape_general_leaderboard(leaderboard_url)
                if general_leaderboard:
                    await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

                    # 🏁 Assign points for this past week
                    await safe_db_call(assign_points_for_week, season, week)


        logging.info("✅ Finished processing past weeks.")
    except Exception as e:
        logging.error(f"Exception in process_past_weeks: {e}")

async def get_driver_history(driver_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            driver_name_lower = driver_name.lower()

            await cursor.execute("""
                SELECT season, week, position, diff_first
                FROM general_leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
                ORDER BY season ASC, week ASC
            """, (f"%{driver_name_lower}%",))

            results = await cursor.fetchall()

        await conn.ensure_closed()

        # Build a lookup for (season, week) to result
        result_lookup = {(row['season'], row['week']): row for row in results}

        all_weeks = get_all_season_weeks()
        if not all_weeks:
            return None

        history_lines = []
        for sw in all_weeks:
            try:
                season, week = parse_season_week_key(sw)
            except ValueError:
                continue

            data = result_lookup.get((season, week))
            if data:
                history_lines.append(f"S{season}W{week} — Pos: {data['position']} ⏳ ({data['diff_first']})")
            else:
                history_lines.append(f"S{season}W{week} — ❌ Did not complete")

        embed = discord.Embed(
            title=f"📜 History for {driver_name}",
            description="\n".join(history_lines),
            color=discord.Color.blurple()
        )

        return embed

    except Exception as e:
        logging.error(f"[ERROR] get_driver_history failed: {e}")
        return None




async def check_current_week_loop(channel):
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            season, week = get_latest_season_and_week()
            if season is None or week is None:
                logging.warning("⚠️ Could not detect latest season/week.")
                await asyncio.sleep(60)
                continue

            leg_urls = build_urls_for_week(season, week)

            for leg, stages in leg_urls.items():
                for stage, url in stages.items():
                    if not url:
                        continue

                    track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                    leaderboard = await scrape_leaderboard(url)
                    if leaderboard:
                        await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week, url)

                    current_leader = await safe_db_call(get_latest_left_leader, track_name, season, week)
                    if not current_leader:
                        continue

                    previous_leader = await safe_db_call(get_previous_leader, track_name)
                    if not previous_leader:
                        # 📍 First stage completion announcement
                        conn = await get_db_connection()
                        async with conn.cursor(aiomysql.DictCursor) as cursor:
                            await cursor.execute("""
                                SELECT driver_name, vehicle, time, diff_first FROM leaderboard_log_left
                                WHERE track_name = %s AND season = %s AND week = %s
                                ORDER BY position ASC LIMIT 1
                            """, (track_name, season, week))
                            row = await cursor.fetchone()
                        await conn.ensure_closed()

                        if row:
                            embed = discord.Embed(
                                title="📍 First Stage Completion!",
                                description=(
                                    f"**{row['driver_name']}** has posted the **first time** on **{track_name}**\n"
                                    f"🏎️ {row['vehicle']}"
                                ),
                                color=discord.Color.teal()
                            )
                            await channel.send(embed=embed)

                    elif previous_leader.strip().lower() != current_leader.strip().lower():
                        conn = await get_db_connection()
                        async with conn.cursor(aiomysql.DictCursor) as cursor:
                            await cursor.execute("""
                                SELECT driver_name, diff_first FROM leaderboard_log_left
                                WHERE track_name = %s AND season = %s AND week = %s
                            """, (track_name, season, week))
                            rows = await cursor.fetchall()
                        await conn.ensure_closed()

                        name_map = {row["driver_name"].lower(): row["diff_first"] for row in rows}
                        old_diff = name_map.get(previous_leader.lower(), "N/A")
                        new_diff = name_map.get(current_leader.lower(), "N/A")

                        try:
                            def to_seconds(t):
                                parts = list(map(float, t.split(":")))
                                return sum(x * 60**i for i, x in enumerate(reversed(parts)))

                            diff_sec = to_seconds(old_diff) - to_seconds(new_diff)
                            gain_line = f"\n🕒 **Gained:** {diff_sec:.3f}s over previous leader"
                        except:
                            gain_line = ""

                        embed = discord.Embed(
                            title="🏆 New Track Leader!",
                            description=(
                                f"**{current_leader}** is now leading **{track_name}**\n"
                                f"(Previously: {previous_leader}){gain_line}"
                            ),
                            color=discord.Color.gold()
                        )
                        await channel.send(embed=embed)

                    await safe_db_call(update_previous_leader, track_name, current_leader)

            # ✅ GENERAL LEADERBOARD CHECK
            leaderboard_url = get_leaderboard_url(season, week)
            if leaderboard_url:
                general_leaderboard, soup = await scrape_general_leaderboard(leaderboard_url)
                if general_leaderboard:
                    await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

                    current_leader = general_leaderboard[0]["name"]
                    track_name = f"S{season}W{week} - General Leaderboard"
                    previous_leader = await safe_db_call(get_previous_leader, track_name)

                    if not previous_leader:
                        embed = discord.Embed(
                            title="📍 First One To Complete All The Stages!",
                            description=(
                                f"**{current_leader}** is the first to post a time on the **general leaderboard** for **S{season}W{week}**!"
                            ),
                            color=discord.Color.teal()
                        )
                        await channel.send(embed=embed)

                    elif previous_leader.strip().lower() != current_leader.strip().lower():
                        name_map = {entry["name"].lower(): entry["diff_first"] for entry in general_leaderboard}
                        old_diff = name_map.get(previous_leader.lower(), "N/A")
                        new_diff = name_map.get(current_leader.lower(), "N/A")

                        try:
                            def to_seconds(t):
                                parts = list(map(float, t.split(":")))
                                return sum(x * 60**i for i, x in enumerate(reversed(parts)))

                            diff_sec = to_seconds(old_diff) - to_seconds(new_diff)
                            gain_line = f"\n🕒 **Gained:** {diff_sec:.3f}s over previous leader"
                        except:
                            gain_line = ""

                        embed = discord.Embed(
                            title="🌐 New Week Leader!",
                            description=(
                                f"**{current_leader}** is now leading the overall standings for **S{season}W{week}**\n"
                                f"(Previously: {previous_leader}){gain_line}"
                            ),
                            color=discord.Color.green()
                        )
                        await channel.send(embed=embed)

                    await safe_db_call(update_previous_leader, track_name, current_leader)

            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"[Loop Error] {e}")
            await notify_owner_if_stuck()
            await asyncio.sleep(60)










# Async task to check for leader changes and update DB
async def check_leader_change():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)

    while not bot.is_closed():
        try:
            for sw in get_all_season_weeks():
                season, week = parse_season_week_key(sw)
                leg_urls = build_urls_for_week(season, week)

                for leg, stages in leg_urls.items():
                    for stage, url in stages.items():
                        if not url:
                            continue

                        track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                        current_leader = await safe_db_call(get_latest_left_leader, track_name, season, week)
                        if not current_leader:
                            continue

                        previous_leader = await safe_db_call(get_previous_leader, track_name)
                        if previous_leader and previous_leader.strip().lower() != current_leader.strip().lower():
                            conn = await get_db_connection()
                            async with conn.cursor(aiomysql.DictCursor) as cursor:
                                await cursor.execute("""
                                    SELECT driver_name, diff_first FROM leaderboard_log_left
                                    WHERE track_name = %s AND season = %s AND week = %s
                                """, (track_name, season, week))
                                rows = await cursor.fetchall()
                            await conn.ensure_closed()

                            name_map = {row["driver_name"].lower(): row["diff_first"] for row in rows}
                            old_diff = name_map.get(previous_leader.lower(), "N/A")
                            new_diff = name_map.get(current_leader.lower(), "N/A")

                            try:
                                def to_seconds(t):
                                    parts = list(map(float, t.split(":")))
                                    return sum(x * 60**i for i, x in enumerate(reversed(parts)))

                                diff_sec = to_seconds(old_diff) - to_seconds(new_diff)
                                gain_line = f"\n🕒 **Gained:** {diff_sec:.3f}s over previous leader"
                            except:
                                gain_line = ""

                            embed = discord.Embed(
                                title="🏆 New Track Leader!",
                                description=f"**{current_leader}** is now leading **{track_name}**\n(Previously: {previous_leader}){gain_line}",
                                color=discord.Color.gold()
                            )
                            await channel.send(embed=embed)

                        await safe_db_call(update_previous_leader, track_name, current_leader)

            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"[Loop Error] {e}")
            await notify_owner_if_stuck()
            await asyncio.sleep(60)





@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    channel = bot.get_channel(CHANNEL_ID)

    # ✅ Check if this was a restart (moved to top before anything else)
    if os.path.exists("restart.flag"):
        try:
            with open("restart.flag", "r") as f:
                restart_channel_id = int(f.read().strip())
            restart_channel = bot.get_channel(restart_channel_id)
            if restart_channel:
                await restart_channel.send("✅ Bot is back up!")
        except Exception as e:
            logging.error(f"[ERROR] Failed to send restart confirmation: {e}")
        finally:
            os.remove("restart.flag")

    await process_past_weeks(channel)

    # 🔍 Debug output
    weeks = get_all_season_weeks()
    print("📋 Season/Week keys found:", weeks)

    if not weeks:
        print("⚠️ No season/week keys found! env_data keys are:", list(env_data.keys()))
        return

    # ✅ Bootstrap current week scraping
    season, week = get_latest_season_and_week()
    leg_urls = build_urls_for_week(season, week)

    for leg, stages in leg_urls.items():
        for stage, url in stages.items():
            if not url:
                continue

            track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
            leaderboard = await scrape_leaderboard(url)
            if leaderboard:
                await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week, url)

                current_leader = await safe_db_call(get_latest_left_leader, track_name, season, week)
                if current_leader:
                    await safe_db_call(update_previous_leader, track_name, current_leader)

    leaderboard_url = get_leaderboard_url(season, week)
    if leaderboard_url:
        general_leaderboard, soup = await scrape_general_leaderboard(leaderboard_url)
        if general_leaderboard:
            await safe_db_call(log_general_leaderboard_to_db, season, week, soup)
            track_name = f"S{season}W{week} - General Leaderboard"
            await safe_db_call(update_previous_leader, track_name, general_leaderboard[0]["name"])

    start_background_task("check_current_week_loop", check_current_week_loop(channel))
    start_background_task("reconnect_watchdog_loop", reconnect_watchdog_loop())




# ---- Command Handlers ----

async def handle_progress_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log_left ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        await conn.ensure_closed()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📍 Select a driver to view their progress:", view=ProgressDriverSearchView(names))
        return

    query_name = " ".join(parts[1:])

    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT DISTINCT driver_name FROM leaderboard_log_left
            WHERE LOWER(driver_name) LIKE %s
            ORDER BY driver_name ASC LIMIT 1
        """, (f"%{query_name.lower()}%",))
        row = await cursor.fetchone()
    await conn.ensure_closed()

    if not row:
        await message.channel.send(f"❌ No progress data found for `{query_name}`.")
        return

    matched_driver = row[0]
    embed = await get_driver_progress(matched_driver)
    if embed:
        embed.set_footer(text=f"Matched: {matched_driver}")
        await message.channel.send(embed=embed)
    else:
        await message.channel.send(f"❌ No progress data found for `{query_name}`.")


async def handle_skillissue_command(message):
    try:
        season, week = get_latest_season_and_week()
        conn = await get_db_connection()

        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT driver_name, vehicle, position, diff_first
                FROM general_leaderboard_log
                WHERE season = %s AND week = %s AND position < 9999
                ORDER BY position DESC
                LIMIT 1
            """, (season, week))

            row = await cursor.fetchone()

        await conn.ensure_closed()

        if not row:
            await message.channel.send("⚠️ No results found for the current week.")
            return

        name = row["driver_name"]
        vehicle = row["vehicle"] or "Unknown"
        pos = row["position"]
        gap = row["diff_first"] or "N/A"

        # 🧠 Motivational tip pool
        tips = [
            "Every legend was once the last on the leaderboard.",
            "Your comeback story starts now. 📈",
            "Even Loeb had to restart stages sometimes.",
            "Next week is a clean slate. Don't lift!",
            "Shake it off — the forest will forgive you.",
            "DNFs build character. Probably.",
            "The only way from here is up! 🚀"
        ]

        tip = random.choice(tips)

        embed = discord.Embed(
            title="💥 Skill Issue Detected!",
            description=(
                f"**{name}** finished in **last place** (Pos {pos}) for Season {season}, Week {week}.\n"
                f"🏎️ Vehicle: {vehicle}\n"
                f"⏱️ Gap to leader: {gap}\n\n"
                f"{tip}"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="See you at the next stage!")

        await message.channel.send(embed=embed)

    except Exception as e:
        logging.error(f"[ERROR] handle_skillissue_command failed: {e}")
        await message.channel.send("❌ Could not determine who had the skill issue.")





async def handle_history_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        # Show dropdown for driver selection
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        await conn.ensure_closed()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📜 Select a driver to view history:", view=HistoryDriverSearchView(names))
        return

    query_name = " ".join(parts[1:])

    # Match the driver name
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT DISTINCT driver_name FROM general_leaderboard_log
            WHERE LOWER(driver_name) LIKE %s
            ORDER BY driver_name ASC LIMIT 1
        """, (f"%{query_name.lower()}%",))
        row = await cursor.fetchone()
    await conn.ensure_closed()

    if not row:
        await message.channel.send(f"❌ No history found for `{query_name}`.")
        return

    matched_driver = row[0]
    embed = await get_driver_history(matched_driver)
    if embed:
        embed.set_footer(text=f"Matched: {matched_driver}")
        await message.channel.send(embed=embed)
    else:
        await message.channel.send(f"❌ No history found for `{query_name}`.")



async def handle_leg_command(message):
    parts = message.content.strip().lower().split()

    # Try to extract leg number from either "!leg1" or "!leg 1"
    leg_number = None
    if parts[0].startswith("!leg") and len(parts[0]) > 4 and parts[0][4:].isdigit():
        leg_number = int(parts[0][4:])
    elif len(parts) > 1 and parts[0] == "!leg" and parts[1].isdigit():
        leg_number = int(parts[1])

    if leg_number is None:
        await message.channel.send("❌ Please use a valid leg number like `!leg1` or `!leg 1`.")
        return


        # Default to latest week
    season, week = get_latest_season_and_week()

    # Check for s#w# argument in parts (even if it's part[2] in "!leg 1 s1w2")
    for part in parts:
        if part.startswith("s") and "w" in part:
            try:
                season = int(re.findall(r's(\d+)', part)[0])
                week = int(re.findall(r'w(\d+)', part)[0])
            except (ValueError, IndexError):
                await message.channel.send("❌ Invalid format. Use `!leg1` or `!leg1 s2w3`")
                return


    try:
        urls_by_leg = build_urls_for_week(season, week)
        leg_stage_urls = urls_by_leg.get(leg_number, {})
        if not leg_stage_urls:
            await message.channel.send(f"⚠️ No leaderboard data available for Leg {leg_number} in S{season}W{week}.")
            return

        embed = discord.Embed(
            title=f"🧭 Results for Leg {leg_number}",
            description=f"Season {season}, Week {week}",
            color=discord.Color.blue()
        )

        button_links = {}

        for stage_num in sorted(leg_stage_urls):
            url = leg_stage_urls[stage_num]
            if not url:
                continue

            leaderboard = await scrape_leaderboard(url)
            if not leaderboard:
                continue

            top_entries = leaderboard[:5]
            results = "\n".join([
                f"**{entry['position']}**. **{entry['name']}** 🏎️ {entry['vehicle']} ⏳ ({entry['diff_first']})"
                for entry in top_entries
            ])

            embed.add_field(
                name=f"Stage {stage_num}",
                value=(results or "❌ No data") + "\n\u200B",
                inline=False
            )


            button_links[f"Stage {stage_num}"] = url

        if not embed.fields:
            await message.channel.send("❌ No leaderboard data found for this leg.")
            return

        view = LeaderboardLinkView(button_links) if button_links else None
        await message.channel.send(embed=embed, view=view)

    except Exception as e:
        logging.error(f"[ERROR] handle_leg_command failed: {e}")
        await message.channel.send(f"❌ An error occurred while processing Leg {leg_number}.")


async def handle_trend_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM general_leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        await conn.ensure_closed()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📉 Select a driver to view trend:", view=TrendDriverSearchView(names))
    else:
        query_name = " ".join(parts[1:])

        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT DISTINCT driver_name FROM general_leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
                ORDER BY driver_name ASC LIMIT 1
            """, (f"%{query_name.lower()}%",))
            row = await cursor.fetchone()
        await conn.ensure_closed()

        if not row:
            await message.channel.send(f"❌ No trend data found for `{query_name}`.")
            return

        matched_driver = row[0]
        embed = await get_driver_trend(matched_driver)
        if embed:
            embed.set_footer(text=f"Matched: {matched_driver}")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"❌ No trend data found for `{query_name}`.")


async def handle_search_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        # Fetch all distinct driver names from DB
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        await conn.ensure_closed()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("🔍 Select a driver from the list below:", view=DriverSearchView(names))
        return

    query_name = []
    season = week = None

    for part in parts[1:]:
        if re.match(r"^s\d+w\d+$", part.lower()):
            season = int(re.findall(r's(\d+)w', part.lower())[0])
            week = int(re.findall(r'w(\d+)', part.lower())[0])
        else:
            query_name.append(part)

    query_name = " ".join(query_name)

    # Match the driver name
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT DISTINCT driver_name FROM leaderboard_log
            WHERE LOWER(driver_name) LIKE %s
            ORDER BY driver_name ASC LIMIT 1
        """, (f"%{query_name.lower()}%",))
        row = await cursor.fetchone()
    await conn.ensure_closed()

    if not row:
        await message.channel.send(f"❌ No results found for `{query_name}`.")
        return

    matched_driver = row[0]

    try:
        result_text = await show_driver_results(matched_driver, season, week)
        if isinstance(result_text, discord.Embed):
            # Count stages for current week to show progress info
            season = season or get_latest_season_and_week()[0]
            week = week or get_latest_season_and_week()[1]
            leg_urls = build_urls_for_week(season, week)
            expected_tracks = [
                f"S{season}W{week} - Leg {leg} (Stage {stage})"
                for leg, stages in leg_urls.items()
                for stage in stages
            ]

            conn = await get_db_connection()
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT track_name FROM leaderboard_log_left
                    WHERE LOWER(driver_name) LIKE %s AND season = %s AND week = %s
                """, (f"%{matched_driver.lower()}%", season, week))
                rows = await cursor.fetchall()
            await conn.ensure_closed()

            completed_tracks = {row[0] for row in rows}
            total = len(expected_tracks)
            done = sum(1 for track in expected_tracks if track in completed_tracks)

            if done < total:
                result_text.add_field(
                    name="⏱️ Stage Progress",
                    value=f"{done}/{total} stages completed",
                    inline=False
                )

            result_text.set_footer(text=f"Matched: {matched_driver}")
            await message.channel.send(embed=result_text)
        else:
            await message.channel.send(result_text)

    except Exception as e:
        logging.error(f"[ERROR] search driver failed: {e}")
        await message.channel.send(f"❌ No results found for `{query_name}`.")




async def handle_stats_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        # Show dropdown specific to stats
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        await conn.ensure_closed()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📊 Select a driver to view stats:", view=StatsDriverSearchView(names))
    else:
        query_name = " ".join(parts[1:])
        embed = await get_driver_stats(query_name)
        if isinstance(embed, discord.Embed):
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(embed)  # it’s a string error message


async def handle_restart_command(message):
    if message.author.id not in ALLOWED_SYNC_USERS:
        await message.channel.send("❌ You don’t have permission to use this command.")
        return

    try:
        # ✅ Write restart flag to disk
        with open("restart.flag", "w") as f:
            f.write(str(message.channel.id))

        await message.channel.send("🔄 Restarting bot...")
        await bot.close()
        sys.exit(0)

    except Exception as e:
        logging.error(f"[ERROR] handle_restart_command failed: {e}")
        await message.channel.send("❌ Restart failed. Check logs for more info.")

async def handle_compare_command(message):
    pattern = r"!compare (.+?) vs (.+)"
    match = re.match(pattern, message.content.strip(), re.IGNORECASE)

    if not match:
        # No drivers provided → show dropdown UI
        driver_names = await get_all_driver_names()
        if not driver_names:
            await message.channel.send("⚠️ No driver names found.")
            return

        await message.channel.send(
            "🧩 Select the first driver to begin comparison:",
            view=CompareDriver1View(driver_names)
        )
        return

    driver1, driver2 = match.group(1).strip(), match.group(2).strip()

    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT l1.track_name, l1.position as pos1, l2.position as pos2
                FROM leaderboard_log l1
                JOIN leaderboard_log l2 ON l1.track_name = l2.track_name
                AND l1.season = l2.season AND l1.week = l2.week
                WHERE l1.driver_name LIKE %s AND l2.driver_name LIKE %s
            """, (f"%{driver1}%", f"%{driver2}%"))

            shared_results = await cursor.fetchall()
        await conn.ensure_closed()

        if not shared_results:
            await message.channel.send(f"⚠️ No shared events found between `{driver1}` and `{driver2}`.")
            return

        driver1_wins = driver2_wins = 0

        for entry in shared_results:
            pos1 = entry['pos1']
            pos2 = entry['pos2']

            if pos1 < pos2:
                driver1_wins += 1
            elif pos2 < pos1:
                driver2_wins += 1

        total_events = driver1_wins + driver2_wins
        driver1_pct = (driver1_wins / total_events * 100) if total_events > 0 else 0
        driver2_pct = (driver2_wins / total_events * 100) if total_events > 0 else 0

        embed = discord.Embed(
            title="⚔️ Head-to-Head Comparison",
            description=f"**{driver1}** vs **{driver2}**",
            color=discord.Color.red()
        )

        embed.add_field(name="📊 Events Compared", value=total_events, inline=False)
        embed.add_field(
            name=f"🏆 {driver1} Wins",
            value=f"{driver1_wins} ({driver1_pct:.1f}%)",
            inline=True
        )
        embed.add_field(
            name=f"🏆 {driver2} Wins",
            value=f"{driver2_wins} ({driver2_pct:.1f}%)",
            inline=True
        )

        if driver1_wins > driver2_wins:
            embed.set_footer(text=f"{driver1} is currently ahead 🏁")
        elif driver2_wins > driver1_wins:
            embed.set_footer(text=f"{driver2} is currently ahead 🏁")
        else:
            embed.set_footer(text="Dead even! Neck and neck 💥")

        await message.channel.send(embed=embed)

    except Exception as e:
        logging.error(f"[ERROR] compare command failed: {e}")
        await message.channel.send("❌ An error occurred while comparing the drivers.")

async def handle_dbcheck_command(message):
    if message.author.id not in ALLOWED_SYNC_USERS:
        await message.channel.send("❌ You don’t have permission to use this command.")
        return

    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Check RIGHT table
            await cursor.execute("SELECT COUNT(*) as total FROM leaderboard_log")
            right_count = (await cursor.fetchone())["total"]

            # Check LEFT table
            await cursor.execute("SELECT COUNT(*) as total FROM leaderboard_log_left")
            left_count = (await cursor.fetchone())["total"]

            # Check General table
            await cursor.execute("SELECT COUNT(*) as total FROM general_leaderboard_log")
            general_count = (await cursor.fetchone())["total"]

            # Check season_points table
            await cursor.execute("SELECT COUNT(*) as total FROM season_points")
            season_points_count = (await cursor.fetchone())["total"]

        await conn.ensure_closed()

        embed = discord.Embed(
            title="🩺 Database Check Passed",
            description="Successfully connected and queried the database.",
            color=discord.Color.green()
        )
        embed.add_field(name="📘 leaderboard_log (RIGHT)", value=f"{right_count} rows", inline=False)
        embed.add_field(name="📗 leaderboard_log_left (LEFT)", value=f"{left_count} rows", inline=False)
        embed.add_field(name="📙 general_leaderboard_log", value=f"{general_count} rows", inline=False)
        embed.add_field(name="📔 season_points", value=f"{season_points_count} rows", inline=False)

        await message.channel.send(embed=embed)

    except Exception as e:
        logging.error(f"[ERROR] handle_dbcheck_command failed: {e}")
        await message.channel.send("❌ Database check failed. See logs for details.")



async def handle_mostwins_command(message):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT driver_name, COUNT(*) as win_count
                FROM leaderboard_log_left
                WHERE position = 1
                GROUP BY driver_name
                ORDER BY win_count DESC
                LIMIT 10
            """)
            rows = await cursor.fetchall()
        await conn.ensure_closed()

        if not rows:
            await message.channel.send("⚠️ No win data found.")
            return

        embed = discord.Embed(
            title="🏆 Top Stage Winners",
            description="Here are the drivers with the most stage wins across all weeks.",
            color=discord.Color.gold()
        )

        podium = {1: "🥇", 2: "🥈", 3: "🥉"}

        for i, row in enumerate(rows, start=1):
            driver = row["driver_name"]
            wins = row["win_count"]
            if i in podium:
                name = f"{podium[i]} {driver}"
            else:
                name = f"{i}. {driver}"
            embed.add_field(name=name, value=f"{wins} wins", inline=False)

        await message.channel.send(embed=embed)

    except Exception as e:
        logging.error(f"[ERROR] handle_mostwins_command failed: {e}")
        await message.channel.send("❌ Could not fetch most wins data.")





async def handle_leaderboard_command(message):
    try:
        parts = message.content.strip().split()
        if len(parts) == 2:
            arg = parts[1].lower()
            if arg.startswith("s") and "w" in arg:
                season = int(re.findall(r's(\d+)', arg)[0])
                week = int(re.findall(r'w(\d+)', arg)[0])
            else:
                await message.channel.send("⚠️ Invalid format. Use `!leaderboard` or `!leaderboard s1w1`")
                return
        else:
            season, week = get_latest_season_and_week()

        leaderboard_url = get_leaderboard_url(season, week)
        if not leaderboard_url:
            await message.channel.send(f"❌ No leaderboard URL found for S{season}W{week}")
            return

        leaderboard, soup = await scrape_general_leaderboard(leaderboard_url)

        if not leaderboard:
            embed = discord.Embed(
                title="📭 No Leaderboard Yet",
                description=(
                    f"No entries found for **Season {season}, Week {week}**.\n"
                    "No drivers have completed the rally or submitted times yet."
                ),
                color=discord.Color.light_grey()
            )
            await message.channel.send(embed=embed)
            return

        try:
            await safe_db_call(log_general_leaderboard_to_db, season, week, soup)
        except Exception as e:
            logging.warning(f"❌ Failed to log general leaderboard: {e}")

        embed = discord.Embed(
            title="🏁 General Leaderboard",
            description=f"**Season {season}, Week {week}**\n\nTop overall times:",
            color=discord.Color.dark_gold()
        )

        podium = {1: "🥇", 2: "🥈", 3: "🥉"}

        for entry in leaderboard:
            pos = int(entry["position"])
            icon = podium.get(pos, f"#{pos}")
            name = entry["name"]
            vehicle = entry["vehicle"]
            diff = entry["diff_first"]
            time = entry["time"]

            field_title = f"{icon} {name}"
            field_value = (
                f"🏎️ {vehicle}\n"
                f"⏱️ {time} (Gap: {diff})\n\u200B"
            )

            embed.add_field(name=field_title, value=field_value, inline=False)

        view = LeaderboardLinkView({f"S{season}W{week} Full Leaderboard": leaderboard_url})
        await message.channel.send(embed=embed, view=view)

    except Exception as e:
        logging.error(f"[ERROR] handle_leaderboard_command failed: {e}")
        await message.channel.send(f"❌ An error occurred: {e}")





async def handle_info_command(message):
    info_url = os.getenv("INFO_URL")
    rally_name = os.getenv("RALLY_NAME")
    rally_password = os.getenv("RALLY_PASSWORD")
    league_name = os.getenv("LEAGUE_NAME", "Rally Info")  # fallback if not set

    if not info_url or not rally_name or not rally_password:
        await message.channel.send("⚠️ Missing one or more values in your `.env` file. Please check `INFO_URL`, `RALLY_NAME`, and `RALLY_PASSWORD`.")
        return

    embed = discord.Embed(
        title=f"ℹ️ {league_name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="🔗 Link To Page", value=f"[Click Here]({info_url})", inline=False)
    embed.add_field(name="🏁 Championship Name", value=rally_name, inline=False)
    embed.add_field(name="🔒 Password", value=rally_password, inline=False)

    await message.channel.send(embed=embed)




async def handle_cmd_command(message):
    commands_list = """
**📋 Available Commands**

🔍 `!search [driver] [s#w#]`  
→ View detailed results for a driver with stage breakdown  
→ Omit name to use dropdown (e.g. `!search`)  
→ Add optional season/week (e.g. `!search trey s1w2`)

📊 `!stats [driver]`  
→ Driver stats: total events, avg position, wins, podiums, best finish, most used car, and points  
→ Use dropdown if no driver specified

📈 `!trend [driver]`  
→ Weekly performance across all events  
→ See movement, gaps, and time totals with icons  
→ Supports dropdown

📜 `!history [driver]`  
→ General leaderboard history (position + gap) for each week  
→ Use dropdown if no driver specified

⚔️ `!compare [driver1] vs [driver2]`  
→ Compare two drivers head-to-head across shared stages  
→ See win %, total events, and who's ahead  
→ Omit names to use dropdown selectors

🧭 `!leg# [s#w#]`  
→ Shows all stage results for a specific leg  
→ Add optional season/week (`!leg2 s2w3`), defaults to current week

📍 `!progress [driver]`  
→ View stage-by-stage completion for a driver  
→ Shows ✅/❌ per stage in each leg  
→ Dropdown support if name omitted

🏁 `!leaderboard [s#w#]`  
→ Full general leaderboard for the week  
→ Includes all drivers and vehicle/time breakdown  
→ Uses embed with leaderboard link

💥 `!skillissue`  
→ Shows last place driver for current week with motivational message

📈 `!points`  
→ Full season standings from database

🔄 `!sync`  
→ (Admin-only) Syncs rally config + standings from Google Sheets and recalculates points

🔁 `!recalpoints`  
→ (Admin-only) Recalculate points for all previous weeks except current

🩺 `!dbcheck`  
→ (Admin-only) Test DB connection and show row counts  

♻️ `!restart`  
→ (Admin-only) Restart the bot

ℹ️ `!info`  
→ Rally info like website, password, and rally name from `.env`

🧪 `!cmd`  
→ This command list
    """
    await message.channel.send(commands_list)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # ✅ Only allow commands from a specific channel
    allowed_channel_id = int(os.getenv("DISCORD_CHANNEL_ID")) # 🔁 Replace this with your actual channel ID
    if message.channel.id != allowed_channel_id:
        return


    if message.content.startswith("!compare"):
        await handle_compare_command(message)
    elif message.content.startswith("!leaderboard"):
        await handle_leaderboard_command(message)
    elif message.content.startswith("!leg"):
        await handle_leg_command(message)
    elif message.content.startswith("!search"):
        await handle_search_command(message)
    elif message.content.startswith("!cmd"):
        await handle_cmd_command(message)
    elif message.content.startswith("!sync"):
        await handle_sync_command(message)
    elif message.content.startswith("!stats"):
        await handle_stats_command(message)
    elif message.content.startswith("!info"):
        await handle_info_command(message)
    elif message.content.startswith("!trend"):
        await handle_trend_command(message)
    elif message.content.startswith("!history"):
        await handle_history_command(message)
    elif message.content.startswith("!progress"):
        await handle_progress_command(message)
    elif message.content.startswith("!skillissue"):
        await handle_skillissue_command(message)
    elif message.content.startswith("!points"):
        await handle_points_command(message)
    elif message.content.startswith("!mostwins"):
        await handle_mostwins_command(message)
    elif message.content.startswith("!dbcheck"):
        await handle_dbcheck_command(message)
    elif message.content.startswith("!restart"):
        await handle_restart_command(message)
    elif message.content.startswith("!recalpoints"):
        await handle_recalpoints_command(message)






    await bot.process_commands(message)


bot.run(TOKEN)
