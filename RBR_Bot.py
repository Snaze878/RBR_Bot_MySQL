import discord
import asyncio
import requests
import time
import csv
import logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from discord.ext import commands, tasks
from dotenv import load_dotenv, dotenv_values
from logging.handlers import TimedRotatingFileHandler
import os
import aiomysql
import re
from collections import defaultdict
from discord.ui import View, Button
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Logging Setup ---
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Discord logger
discord_handler = TimedRotatingFileHandler(
    filename=os.path.join(log_dir, "discord_commands.log"),
    when="midnight", interval=1, backupCount=7, encoding='utf-8'
)
discord_handler.setLevel(logging.DEBUG)
discord_handler.setFormatter(log_format)

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.DEBUG)
discord_logger.addHandler(discord_handler)

# Scraping logger
scrape_handler = TimedRotatingFileHandler(
    filename=os.path.join(log_dir, "scraping.log"),
    when="midnight", interval=1, backupCount=7, encoding='utf-8'
)
scrape_handler.setLevel(logging.DEBUG)
scrape_handler.setFormatter(log_format)

scraping_logger = logging.getLogger("scraping")
scraping_logger.setLevel(logging.DEBUG)
scraping_logger.addHandler(scrape_handler)

# Error logger
error_handler = TimedRotatingFileHandler(
    filename=os.path.join(log_dir, "error.log"),
    when="midnight", interval=1, backupCount=7, encoding='utf-8'
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(log_format)

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

#Google Spreadsheet hook

def sync_from_google_sheet():
    try:
        # Setup access to Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        client = gspread.authorize(creds)

        # Open the RBR_Tracking spreadsheet
        spreadsheet = client.open("RBR_Tracking")

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

        # 🔁 Re-load the updated env values into memory
        load_dotenv(override=True)
        print("🧪 Reloaded .env → RALLY_NAME =", os.getenv("RALLY_NAME"))

        # === Write standings from "Standings" tab to standings.csv ===
        try:
            standings_sheet = spreadsheet.worksheet("Standings")
            standings_data = standings_sheet.get_all_values()

            standings_path = os.path.join(os.path.dirname(__file__), "standings.csv")
            with open(standings_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in standings_data:
                    writer.writerow(row)

            print(f"✅ standings.csv updated from 'Standings' tab")
        except Exception as e:
            print(f"❌ Failed to update standings.csv: {e}")

        return True

    except Exception as e:
        print(f"❌ sync_from_google_sheet() failed: {e}")
        import traceback
        traceback.print_exc()
        return False





# Syncing with Google Handler
# Replace this with your actual Discord ID(s)
ALLOWED_SYNC_USERS = [
    111111111111111111,  # User 1
    222222222222222222,  # User 2
    333333333333333333   # User 3
]

async def handle_sync_command(message):
    if message.author.id not in ALLOWED_SYNC_USERS:
        await message.channel.send("❌ You don’t have permission to use this command.")
        return

    try:
        await message.channel.send("🔄 Syncing latest rally data from Google Sheets...")

        # Detect current latest week before sync
        previous_weeks = get_all_season_weeks()
        previous_latest = previous_weeks[-1] if previous_weeks else None

        # Perform sync
        success = sync_from_google_sheet()

        if not success:
            await message.channel.send("⚠️ Sync failed. Check logs for more details.")
            return

        # Check if a new week was added
        updated_weeks = get_all_season_weeks()
        updated_latest = updated_weeks[-1] if updated_weeks else None

        summary_lines = []
        if updated_latest and updated_latest != previous_latest:
            season, week = parse_season_week_key(updated_latest)
            summary_lines.append(f"🆕 **New Week Detected:** Season {season}, Week {week}")
            scraped_tracks = 0
            failed_tracks = 0

            # Scrape leg stages
            leg_urls = build_urls_for_week(season, week)
            for leg, stages in leg_urls.items():
                for stage, url in stages.items():
                    if url:
                        leaderboard = scrape_leaderboard(url)
                        if leaderboard:
                            track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                            await safe_db_call(update_previous_leader, track_name, leaderboard[0]["name"])
                            await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week)
                            scraped_tracks += 1
                        else:
                            failed_tracks += 1

            # Scrape general leaderboard
            leaderboard_url = get_leaderboard_url(season, week)
            if leaderboard_url:
                general_leaderboard, soup = scrape_general_leaderboard(leaderboard_url)
                if general_leaderboard:
                    await safe_db_call(log_general_leaderboard_to_db, season, week, soup)
                    summary_lines.append(f"📊 General leaderboard scraped and logged.")
                else:
                    summary_lines.append(f"⚠️ Failed to scrape general leaderboard.")

            summary_lines.append(f"📈 Leg stages scraped: {scraped_tracks}")
            if failed_tracks:
                summary_lines.append(f"⚠️ Failed to scrape {failed_tracks} leg stage(s).")

        else:
            summary_lines.append("✅ No new week found. Existing week data remains unchanged.")

        await message.channel.send(
            "✅ Successfully synced from Google Sheets!\n"
            "• `.env` file updated\n"
            "• `standings.csv` updated\n"
            "• `!info` and `!points` now reflect the latest data"
        )

        # Send detailed summary
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


# (Rest of the code continues, properly cleaned up...)

async def get_driver_stats(driver_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Total entries
            await cursor.execute("""
                SELECT COUNT(*) as total_events FROM leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
            """, (f"%{driver_name}%",))
            total_events = (await cursor.fetchone())["total_events"]

            # Average position
            await cursor.execute("""
                SELECT AVG(position) as avg_position FROM leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
            """, (f"%{driver_name}%",))
            avg_position = (await cursor.fetchone())["avg_position"]

            # Best finish
            await cursor.execute("""
                SELECT position, track_name FROM leaderboard_log
                WHERE LOWER(driver_name) LIKE %s
                ORDER BY position ASC LIMIT 1
            """, (f"%{driver_name}%",))
            best_row = await cursor.fetchone()
            best_finish = f"{best_row['position']}th in {best_row['track_name']}" if best_row else "N/A"

            # Podiums
            await cursor.execute("""
                SELECT COUNT(*) as podiums FROM leaderboard_log
                WHERE driver_name LIKE %s AND position <= 3
            """, (f"%{driver_name}%",))
            podiums = (await cursor.fetchone())["podiums"]

            # Wins
            await cursor.execute("""
                SELECT COUNT(*) as wins FROM leaderboard_log
                WHERE driver_name LIKE %s AND position = 1
            """, (f"%{driver_name}%",))
            wins = (await cursor.fetchone())["wins"]

            # Most used vehicle
            await cursor.execute("""
                SELECT vehicle, COUNT(*) as count FROM leaderboard_log
                WHERE driver_name LIKE %s AND vehicle IS NOT NULL AND vehicle != ''
                GROUP BY vehicle ORDER BY count DESC LIMIT 1
            """, (f"%{driver_name}%",))
            vehicle_row = await cursor.fetchone()
            most_vehicle = vehicle_row["vehicle"] if vehicle_row else "Unknown"

        conn.close()

        # Read from standings.csv for total points
        points = "N/A"
        standings_path = os.path.join(os.path.dirname(__file__), "standings.csv")
        try:
            with open(standings_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if driver_name.lower() in row["Driver"].lower():
                        points = row["Points"]
                        break
        except Exception as e:
            logging.warning(f"Could not read standings.csv: {e}")

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
        return None


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
                    line = "❌ Did not participate"
                    previous_position = None  # Reset for skipped week

                trend_data.append((label, line))

        conn.close()

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
        conn.close()

        if results:
            full_name = results[0]['driver_name']
            print(f"🔍 Results for driver: {full_name}")
            results.insert(0, {"full_name": full_name})

        return results
    except Exception as e:
        print(f"❌ Failed to search driver: {e}")
        return []


# Function to get the previous leader from DB
async def get_previous_leader(track_name):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT leader_name FROM previous_leaders WHERE track_name = %s", (track_name,))
            result = await cursor.fetchone()
        conn.close()
        return result['leader_name'] if result else None
    except Exception as e:
        print(f"❌ Failed to get previous leader for {track_name}: {e}")
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

        general_leaderboard, _ = scrape_general_leaderboard(leaderboard_url)
        # Try to get exact match first
        # Add this line before using name_parts
        name_parts = [p.strip() for p in driver_name.split("/") if p.strip()]

        # Try to get exact match first
        current_overall = next(
            (entry for entry in general_leaderboard
            if any(part.lower() in entry['name'].lower() for part in name_parts)),
            None
        )

        # Fallback to fuzzy match
        if not current_overall:
            current_overall = next(
                (entry for entry in general_leaderboard if driver_name.lower() in entry["name"].lower()),
                None
        )



        points_line = ""
        standings_path = os.path.join(os.path.dirname(__file__), "standings.csv")
        try:
            with open(standings_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                
                # Break the name down into lowercased parts
                name_parts = [p.strip().lower() for p in driver_name.split("/") if p.strip()]

                for row in reader:
                    driver_lower = row["Driver"].lower()

                    # Match any part of the driver name
                    if any(part in driver_lower for part in name_parts):
                        points_line = f"🏁 **Points:** {row['Points']} pts"
                        break

        except Exception as e:
            logging.warning(f"Could not read standings.csv: {e}")



        organized = defaultdict(list)
        for entry in results:
            raw_track = entry.get("track_name", "")
            position = entry.get("position", "?")
            diff_first = entry.get("diff_first", "?")

            match = re.search(r"Leg\s*(\d+).+Stage\s*(\d+)", raw_track)
            if match:
                leg_num = int(match.group(1))
                stage_num = int(match.group(2))
                track_label = f"Track {stage_num}"
                line = f"**Pos - {position}** {track_label} ⏳ ({diff_first})"
                organized[f"Leg {leg_num}"].append((stage_num, line))

        formatted_blocks = []
        for leg in sorted(organized.keys(), key=lambda x: int(x.split()[1])):
            stage_lines = sorted(organized[leg])
            block = f"{leg}\n" + "\n".join(line for _, line in stage_lines)
            formatted_blocks.append(block)

        matched_name = current_overall['name'] if current_overall else driver_name
        header = (
            f"🔍 Results for `{driver_name}` — Season {season} Week {week}"
            f"\n👤 **Matched Driver:** {matched_name}"
        )

        if current_overall:
            header += (
                f"\n\n📊 **Current Overall Position:** {current_overall['position']}"
                f"\n⏱️ **Overall Time Diff:** {current_overall['diff_first']}"
            )
        else:
            header += "\n\n📊 **Current Overall Position:** Not Found"

        header += f"\n🏎️ **Vehicle:** {vehicle}"
        header += f"\n{points_line}" if points_line else ""


        return f"{header}\n\n" + "\n────────────────────\n".join(formatted_blocks)

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
        conn.close()
    except Exception as e:
        print(f"❌ Failed to update previous leader for {track_name}: {e}")




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
    conn.close()
    scraping_logger.info(f"✅ Replaced general leaderboard entries for S{season}W{week}")





import re

def parse_season_week_key(sw_key):
    match = re.match(r"S(\d+)W(\d+)", sw_key)
    if match:
        season, week = int(match.group(1)), int(match.group(2))
        return season, week
    raise ValueError(f"Invalid season/week format: {sw_key}")



# Function to log leaderboard data to MySQL
async def log_leaderboard_to_db(track_name, leaderboard, season=None, week=None):
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            # First delete all old entries for this track, season, and week
            await cursor.execute("""
                DELETE FROM leaderboard_log 
                WHERE track_name = %s AND season = %s AND week = %s
            """, (track_name, season, week))

            # Now insert the fresh leaderboard
            query = """
                INSERT INTO leaderboard_log 
                (track_name, position, driver_name, vehicle, time, diff_prev, diff_first, season, week)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            for entry in leaderboard:
                await cursor.execute(query, (
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

        await conn.ensure_closed()
        print(f"✅ Replaced leaderboard entries for {track_name}.")
    except Exception as e:
        print(f"❌ Failed to update leaderboard for {track_name}: {e}")





# ─── ENV LOADING ───
load_dotenv()


from discord.ui import View, Button

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
            try:
                await interaction.followup.send("⚠️ Invalid Season/Week selection.")
            except discord.NotFound:
                await interaction.channel.send("⚠️ Invalid Season/Week selection.")
            return

        season = int(match.group(1))
        week = int(match.group(2))

        # Disable dropdown
        for child in self.view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.view)
        except Exception as e:
            logging.warning(f"⚠️ Failed to disable SeasonWeek dropdown: {e}")

        try:
            result_text = await show_driver_results(self.driver_name, season, week)
            await interaction.followup.send(result_text)
        except Exception as e:
            logging.error(f"❌ Failed to send driver results: {e}")
            await interaction.channel.send("❌ An error occurred showing the results.")








class LeaderboardLinkView(View):
    def __init__(self, links: dict):
        super().__init__(timeout=None)
        for label, url in links.items():
            if isinstance(url, str):
                self.add_item(Button(label=label, url=url))

def scrape_general_leaderboard(url, table_class="rally_results"):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        scraping_logger.warning(f"Unable to fetch the page for {url} (Status code: {response.status_code})")
        return [], None

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table", {"class": table_class})

    if not tables:
        scraping_logger.warning(f"Table not found for {url}!")
        return [], soup

    leaderboard = []

    # Find the correct table with enough rows (skip headers etc.)
    for t_index, t in enumerate(tables):
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue

        for i, row in enumerate(rows):
            cols = row.find_all("td")
            if not cols:
                continue  # Skip header rows

            # Adjust this to match actual layout of the website
            if len(cols) >= 8:
                entry = {
                    "position": cols[0].text.strip(),
                    "name": cols[1].text.strip(),
                    # Skip cols[2] — unknown/unneeded
                    "vehicle": cols[3].text.strip(),
                    "time": cols[4].text.strip(),
                    "diff_prev": cols[5].text.strip(),
                    "diff_first": cols[6].text.strip()
                }
                leaderboard.append(entry)
                #print(f"✅ Added entry: {entry}")

        # Only use the first valid table
        if leaderboard:
            break

    scraping_logger.info(f"✅ Final leaderboard ({len(leaderboard)} entries) for {url}")
    return leaderboard, soup


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
        import re
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




def scrape_leaderboard(url, table_class="rally_results_stres_right"):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        scraping_logger.warning(f"Unable to fetch the page for {url} (Status code: {response.status_code})")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    leaderboard = []
    tables = soup.find_all("table", {"class": table_class})

    if not tables:
        scraping_logger.warning(f"Table not found for {url}!")
        return []

    table = tables[1]
    table_rows = table.find_all("tr")
    scraping_logger.info(f"Found {len(table_rows)} rows for {url}")

    for index, row in enumerate(table_rows[0:]):
        columns = row.find_all("td")
        if len(columns) >= 5:
            position = columns[0].text.strip()
            name_vehicle = columns[1].text.strip()
            time = columns[2].text.strip()
            diff_prev = columns[3].text.strip()
            diff_first = columns[4].text.strip()

            name_parts = name_vehicle.split(" / ", 1)
            vehicle_starts = [
                "Citroen", "Ford", "Peugeot", "Opel", "Abarth", "Skoda", "Mitsubishi", "Subaru", "BMW", "GM", "GMC",
                "Toyota", "Honda", "Suzuki", "Acura", "Audi", "Volkswagen", "Chevrolet", "Volvo", "Kia", "Jeep", "Dodge",
                "Mazda", "Hyundai", "Buick", "MINI", "Porsche", "Mercedes", "Land Rover", "Alfa Romeo", "Lancia"
            ]

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
                        vehicle = brand + " " + combined.split(brand, 1)[1].strip()
                        name2 = ""
                        break
                else:
                    name1 = combined
                    name2 = ""
                    vehicle = ""

            full_name = f"{name1} / {name2}"
            entry = {
                "position": position,
                "name": full_name,
                "vehicle": vehicle,
                "diff_prev": diff_prev,
                "diff_first": diff_first
            }
            leaderboard.append(entry)
            scraping_logger.debug(f"Row {index + 1} - Added: {entry} from {url}")

    scraping_logger.info(f"Final leaderboard ({len(leaderboard)} entries) for {url}")
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

                    leaderboard = scrape_leaderboard(url)
                    if leaderboard:
                        track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                        await safe_db_call(update_previous_leader, track_name, leaderboard[0]["name"])
                        await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week)

            # ✅ Log general leaderboard for past week
            leaderboard_url = get_leaderboard_url(season, week)
            if leaderboard_url:
                general_leaderboard, soup = scrape_general_leaderboard(leaderboard_url)
                if general_leaderboard:
                    await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

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

        conn.close()

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
                history_lines.append(f"S{season}W{week} — ❌ Did not participate")

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

                    leaderboard = scrape_leaderboard(url)
                    if leaderboard:
                        current_leader = leaderboard[0]["name"]
                        track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                        previous_leader = await safe_db_call(get_previous_leader, track_name)
                        if previous_leader is None:
                            continue  # Skip this loop iteration if DB is still down

                        if previous_leader is None:
                            embed = discord.Embed(
                                title="📢 Leader Detected",
                                description=f"**{current_leader}** is leading **{track_name}**\n(First driver)",
                                color=discord.Color.blue()
                            )
                            await channel.send(embed=embed)
                        elif previous_leader != current_leader:
                            time_diff = leaderboard[1]["diff_first"] if len(leaderboard) > 1 else "N/A"
                            embed = discord.Embed(
                                title="🏆 New Track Leader!",
                                description=f"**{current_leader}** is now leading **{track_name}**\n(Previously: {previous_leader})\n**Time Diff:** {time_diff}",
                                color=discord.Color.gold()
                            )
                            await channel.send(embed=embed)

                        await safe_db_call(update_previous_leader, track_name, current_leader)
                        await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week)

            # 🧠 FIXED: Use current season/week instead of stale globals
            leaderboard_url = get_leaderboard_url(season, week)
            general_leaderboard, soup = scrape_general_leaderboard(leaderboard_url)

            if general_leaderboard:
                current_leader = general_leaderboard[0]["name"]
                track_name = "General Leaderboard"
                previous_leader = await safe_db_call(get_previous_leader, track_name)
                if previous_leader is None:
                    continue  # Skip this loop iteration if DB is still down

                if previous_leader is None:
                    embed = discord.Embed(
                        title="📢 General Leader Detected",
                        description=f"**{current_leader}** is leading **{track_name}**\n(First driver)",
                        color=discord.Color.blue()
                    )
                    await channel.send(embed=embed)
                elif previous_leader != current_leader:
                    time_diff = general_leaderboard[1]["diff_first"] if len(general_leaderboard) > 1 else "N/A"
                    embed = discord.Embed(
                        title="🏆 New General Leader!",
                        description=f"**{current_leader}** is now leading **{track_name}**\n(Previously: {previous_leader})\n**Time Diff:** {time_diff}",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=embed)

                await safe_db_call(update_previous_leader, track_name, current_leader)
                await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"[Loop] Error: {e}")
            await asyncio.sleep(60)





# Async task to check for leader changes and update DB
async def check_leader_change():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        logging.error("Discord channel not found!")
        return

    while not bot.is_closed():
        try:
            # Scrape leg-specific leaderboards
            for sw in get_all_season_weeks():
                try:
                    season, week = parse_season_week_key(sw)
                except ValueError as e:
                    logging.warning(f"Skipping invalid season/week key: {sw} → {e}")
                    continue

                leg_urls = build_urls_for_week(season, week)

                for leg, stages in leg_urls.items():
                    for stage, url in stages.items():
                        if not url:
                            continue

                        leaderboard = scrape_leaderboard(url)
                        if leaderboard:
                            current_leader = leaderboard[0]["name"]
                            track_name = f"S{season}W{week} - Leg {leg} (Stage {stage})"
                            previous_leader = await safe_db_call(get_previous_leader, track_name)

                            if previous_leader is None:
                                embed = discord.Embed(
                                    title="📢 Leader Detected",
                                    description=f"**{current_leader}** is leading **{track_name}**\n(First driver)",
                                    color=discord.Color.blue()
                                )
                                await channel.send(embed=embed)
                            elif previous_leader != current_leader:
                                time_diff = leaderboard[1]["diff_first"] if len(leaderboard) > 1 else "N/A"
                                embed = discord.Embed(
                                    title="🏆 New Track Leader!",
                                    description=f"**{current_leader}** is now leading **{track_name}**\n(Previously: {previous_leader})\n**Time Diff:** {time_diff}",
                                    color=discord.Color.gold()
                                )
                                await channel.send(embed=embed)

                            await safe_db_call(update_previous_leader, track_name, current_leader)
                            await safe_db_call(log_leaderboard_to_db, track_name, leaderboard, season, week)

            # Scrape general leaderboard
            season, week = get_latest_season_and_week()
            leaderboard_url = get_leaderboard_url(season, week)
            general_leaderboard, soup = scrape_general_leaderboard(leaderboard_url)

            if general_leaderboard:
                current_leader = general_leaderboard[0]["name"]
                track_name = "General Leaderboard"
                previous_leader = await safe_db_call(get_previous_leader, track_name)

                if previous_leader is None:
                    embed = discord.Embed(
                        title="📢 General Leader Detected",
                        description=f"**{current_leader}** is leading **{track_name}**\n(First driver)",
                        color=discord.Color.blue()
                    )
                    await channel.send(embed=embed)
                elif previous_leader != current_leader:
                    time_diff = general_leaderboard[1]["diff_first"] if len(general_leaderboard) > 1 else "N/A"
                    embed = discord.Embed(
                        title="🏆 New General Leader!",
                        description=f"**{current_leader}** is now leading **{track_name}**\n(Previously: {previous_leader})\n**Time Diff:** {time_diff}",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=embed)

                await safe_db_call(update_previous_leader, track_name, current_leader)

                # ⛏️ Fix here: LEADERBOARD_URL → leaderboard_url
                season, week = get_season_week_from_page(leaderboard_url)
                scraping_logger.debug(f"[General] Season: {season}, Week: {week} for {leaderboard_url}")
                await safe_db_call(log_leaderboard_to_db, track_name, general_leaderboard, season, week)

                scraping_logger.info(f"✅ Logged general leaderboard for S{season if season else 'None'}W{week if week else 'None'}")

            await asyncio.sleep(60)

        except Exception as e:
            import traceback
            error_msg = f"Exception in check_leader_change:\n{traceback.format_exc()}"
            logging.error(error_msg)
            await channel.send("⚠️ An error occurred while checking leaderboards.")



@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    channel = bot.get_channel(CHANNEL_ID)

    await process_past_weeks(channel)

    # 🔍 Debug output
    weeks = get_all_season_weeks()
    print("📋 Season/Week keys found:", weeks)

    if not weeks:
        print("⚠️ No season/week keys found! env_data keys are:", list(env_data.keys()))
        return  # Optional: prevent crash if list is empty

    # ✅ Start the loop task — now dynamic, no need for CURRENT_SEASON/WEEK
    bot.loop.create_task(check_current_week_loop(channel))



# ---- Command Handlers ----

async def handle_history_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        # Show dropdown for driver selection
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        conn.close()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📜 Select a driver to view history:", view=HistoryDriverSearchView(names))
        return

    query_name = " ".join(parts[1:])
    embed = await get_driver_history(query_name)
    if embed:
        await message.channel.send(embed=embed)
    else:
        await message.channel.send("❌ Could not retrieve history.")


async def handle_leg_command(message):
    parts = message.content.strip().split()

    if not parts[0][4:].isdigit():
        await message.channel.send("❌ Please use a valid leg number like `!leg1`, `!leg2`, etc.")
        return

    leg_number = int(parts[0][4:])

    if len(parts) == 2:
        arg = parts[1].lower()
        if arg.startswith("s") and "w" in arg:
            try:
                season = int(re.findall(r's(\d+)w', arg)[0])
                week = int(re.findall(r'w(\d+)', arg)[0])
            except (ValueError, IndexError):
                await message.channel.send("❌ Invalid format. Use `!leg1` or `!leg1 s2w3`")
                return
        else:
            await message.channel.send("❌ Invalid format. Use `!leg1` or `!leg1 s2w3`")
            return
    else:
        all_weeks = get_all_season_weeks()
        if not all_weeks:
            await message.channel.send("❌ No rally data available.")
            return
        season, week = get_latest_season_and_week()

    try:
        urls_by_leg = build_urls_for_week(season, week)
        leg_stage_urls = urls_by_leg.get(leg_number, {})
        if not leg_stage_urls:
            await message.channel.send(f"⚠️ No leaderboard data available for Leg {leg_number} in S{season}W{week}.")
            return

        def scrape_and_format(url, source):
            leaderboard = scrape_leaderboard(url)
            if not leaderboard:
                return f"❌ No leaderboard data available from {source}.", None

            top_entries = leaderboard[:5]
            formatted_results = "\n".join(
                [f"**{entry['position']}**. **{entry['name']}** 🏎️ {entry['vehicle']} ⏳ ({entry['diff_first']})"
                for entry in top_entries]
            )
            return f"🏁 **Top 5 for {source}:**\n{formatted_results}", url

        leaderboard_messages = []
        button_links = {}

        for stage_num in sorted(leg_stage_urls):
            url = leg_stage_urls[stage_num]
            source_label = f"Leg {leg_number} (Stage {stage_num})"
            result_text, result_url = scrape_and_format(url, source_label)

            if result_text:
                leaderboard_messages.append(result_text)
                if result_url:
                    button_links[source_label] = result_url

        response_header = f"📍 **Results for Season {season}, Week {week}**\n\n"
        response = response_header + "\n\n────────────────────\n\n".join(leaderboard_messages)

        if button_links:
            response += "\n\u200B"

        view = LeaderboardLinkView(button_links) if button_links else None

        await message.channel.send(response, view=view)

    except Exception as e:
        await message.channel.send(f"❌ An error occurred while processing Leg {leg_number}: {e}")

async def handle_trend_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM general_leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        conn.close()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📉 Select a driver to view trend:", view=TrendDriverSearchView(names))
    else:
        query_name = " ".join(parts[1:])
        embed = await get_driver_trend(query_name)
        if embed:
            await message.channel.send(embed=embed)
        else:
            await message.channel.send("⚠️ No trend data found for that driver.")



async def handle_search_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
    # Fetch all distinct driver names from DB
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        conn.close()

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

    try:
        result_text = await show_driver_results(query_name, season, week)
        await message.channel.send(result_text)

    except Exception as e:
        logging.error(f"[ERROR] search driver failed: {e}")
        await message.channel.send("❌ An error occurred while searching for the driver.")


async def handle_stats_command(message):
    parts = message.content.strip().split()

    if len(parts) < 2:
        # Show dropdown specific to stats
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT driver_name FROM leaderboard_log ORDER BY driver_name ASC LIMIT 25")
            result = await cursor.fetchall()
        conn.close()

        if not result:
            await message.channel.send("⚠️ No driver names found.")
            return

        names = [row[0] for row in result]
        await message.channel.send("📊 Select a driver to view stats:", view=StatsDriverSearchView(names))

    else:
        query_name = " ".join(parts[1:])
        embed = await get_driver_stats(query_name)
        if embed:
            await message.channel.send(embed=embed)
        else:
            await message.channel.send("❌ Could not retrieve stats.")




async def handle_compare_command(message):
    pattern = r"!compare (.+?) vs (.+)"
    match = re.match(pattern, message.content.strip(), re.IGNORECASE)

    if not match:
        await message.channel.send("❌ Please use the format `!compare driver1 vs driver2`.")
        return

    driver1, driver2 = match.group(1).strip(), match.group(2).strip()

    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT l1.track_name, l1.position as pos1, l2.position as pos2
                FROM leaderboard_log l1
                JOIN leaderboard_log l2 ON l1.track_name = l2.track_name AND l1.season = l2.season AND l1.week = l2.week
                WHERE l1.driver_name LIKE %s AND l2.driver_name LIKE %s
            """, (f"%{driver1}%", f"%{driver2}%"))

            shared_results = await cursor.fetchall()

        conn.close()

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

        header = f"⚔️ **Head-to-Head Comparison:** `{driver1}` vs `{driver2}`\n\n"
        stats = (
            f"**Events compared:** {total_events}\n"
            f"🏆 `{driver1}` wins: **{driver1_wins}**\n"
            f"🏆 `{driver2}` wins: **{driver2_wins}**"
        )

        await message.channel.send(header + stats)

    except Exception as e:
        logging.error(f"[ERROR] compare command failed: {e}")
        await message.channel.send("❌ An error occurred while comparing the drivers.")




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
            all_weeks = get_all_season_weeks()
            if not all_weeks:
                await message.channel.send("❌ No season/week data found.")
                return
            season, week = get_latest_season_and_week()

        leaderboard_url = get_leaderboard_url(season, week)
        if not leaderboard_url:
            await message.channel.send(f"❌ No leaderboard URL found for S{season}W{week}")
            return

        leaderboard, soup = scrape_general_leaderboard(leaderboard_url)
        season, week = get_season_week_from_page(leaderboard_url)

        if leaderboard:
            top10 = "\n".join([
                f"**{entry['position']}**. **{entry['name']}** 🏎️ {entry['vehicle']} ⏳ ({entry['diff_first']})"
                for entry in leaderboard[:10]
            ])
            await message.channel.send(f"**General Leaderboard (S{season}W{week}):**\n{top10}")

            try:
                await safe_db_call(log_general_leaderboard_to_db, season, week, soup)

            except Exception as e:
                logging.warning(f"❌ Failed to log general leaderboard: {e}")
        else:
            await message.channel.send("Couldn't retrieve the general leaderboard.")

    except Exception as e:
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
**📋 Available Commands:**  

🔍 `!search [driver] [s#w#]`  
→ Opens a driver dropdown if no name is provided  
→ You can skip the season/week (like `!search trey`) and it’ll use the current one  

📊 `!stats [driver]`  
→ View a driver’s total events, avg position, best finish, wins, podiums, most used car, and points  
→ Use with dropdown or a name (e.g. `!stats Trey`)  

📜 `!history [driver]`  
→ Shows general leaderboard history per week with position and gap  
→ Use with dropdown or a name (e.g. `!history Garreth`)  

📈 `!trend [driver]`  
→ See weekly trends with icons, movement arrows, and total time/gap  
→ Use with dropdown or a name (e.g. `!trend Chris`)  

🏁 `!leaderboard [s#w#]`  
→ Shows the general leaderboard for the specified or current week  

🧭 `!leg# [s#w#]`  
→ Shows leg results, e.g. `!leg2 s2w3` or just `!leg2` for current week  

⚔️ `!compare driver1 vs driver2`  
→ Compare two drivers head-to-head across shared events  

🎯 `!points`  
→ View full standings from `standings.csv`  

ℹ️ `!info`  
→ Rally info pulled from `.env`  

🔄 `!sync`  
→ Admins only: syncs latest config + standings from Google Sheets  

🧪 `!cmd`  
→ Shows this list of commands
    """
    await message.channel.send(commands_list)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
        # ✅ Only allow commands from a specific channel
        allowed_channel_id = 1348069119685296220  # 🔁 Replace this with your actual channel ID
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
    elif message.content.startswith("!points"):
        file_path = os.path.join(os.path.dirname(__file__), "standings.csv")
        if not os.path.exists(file_path):
            await message.channel.send("❌ Could not find `standings.csv`. Make sure it’s in the same folder as your bot script.")
            return
        try:
            with open(file_path, "r", newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)

            if not rows:
                await message.channel.send("⚠️ The standings file is empty.")
                return

            header = "**🏁 Season One RBR Leaderboard 🏁**\n"
            standings = "\n".join(
                [f"**{row['Position']}**. **{row['Driver']}** - {row['Points']} pts" for row in rows]
            )
            await message.channel.send(header + standings)
        except Exception as e:
            await message.channel.send(f"⚠️ Error reading standings: {e}")

    await bot.process_commands(message)


bot.run(TOKEN)
