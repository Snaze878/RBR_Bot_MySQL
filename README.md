# 🌟 RBR Discord Bot (MySQL Edition)

Welcome to the **RBR Discord Bot (MySQL Edition)**!  
This bot scrapes online leaderboards from [rallysimfans.hu](https://rallysimfans.hu/) and posts real-time updates to Discord, enhanced with **MySQL database** integration. Designed for rally communities who want historical tracking, leader change announcements, and interactive search features.

---

## 🏎️ Features

- **Automated Leaderboard Updates**  
  Continuously scrapes and posts the latest standings to your Discord server.

- **Live Leader Change Detection**  
  Announces when a new driver takes the lead in any rally leg or general standings.

- **MySQL 8.0 Database Backend**  
  All data is logged asynchronously to a MySQL database using `aiomysql`.

- **Interactive Dropdowns**  
  Driver and week selection via Discord UI elements.

- **Google Sheets Integration**  
  Dynamically syncs new rally weeks and configuration from a form submission.

- **Admin-Only Control**  
  Sync from Google Sheets, force restarts, recalculate points, and database checks.

- **Driver Stats, Trends & History**  
  Track individual performance, podiums, weekly progression, and vehicle usage.

- **Stage Completion Progress**  
  Monitor stage-by-stage progress with ✅/❌ breakdowns.

- **Most Wins Tracker**  
  Displays top drivers with the most stage wins.

- **Custom Points System**  
  Built-in seasonal points system that calculates driver standings each week. Points are recalculated automatically when a new active week begins.

- **Archived Data Support**  
  Past results are cached and accessible via commands.

- **Two Leaderboard Tables**  
  Logs both LEFT and RIGHT table data from the rallysimfans website.

- **Stability Watchdog**  
  Auto-alerts if the bot enters a reconnect loop.

---

## 💬 Commands

```
!search [driver] [s#w#]       → Search for a driver's results (dropdown if blank)
!stats [driver]               → View driver's stats: total events, avg pos, wins, podiums, vehicle, points
!history [driver]             → View week-by-week positions & gaps on general leaderboard
!trend [driver]               → See performance trend: arrows, medals, time gaps per week
!progress [driver]            → Show stage-by-stage completion for current week (dropdown if blank)
!mostwins                     → List top 10 drivers with the most stage wins
!leaderboard [s#w#]           → Show general leaderboard
!leg1 to !leg6 [s#w#]         → Display top 5 per stage in a rally leg
!compare driver1 vs driver2   → Head-to-head comparison
!points                       → Show full season points from DB
!info                         → Rally name, password, and info URL
!sync                         → Pull new config & data from Google Sheets
!recalpoints                  → Recalculate points for all previous weeks
!dbcheck                      → Check DB connection and row counts
!restart                      → Restart the bot
!cmd                          → List available commands
!skillissue                   → Shows who finished last this week with a motivational quote
```

> 🧠 You can also run `!stats`, `!history`, `!search`, `!trend`, or `!progress` without a name to use a dropdown menu.

---

## 📸 Example Bot Output

<!-- Add your screenshots or bot output examples here -->

---

## ⚙️ How It Works

- **Scraping:** Uses `requests`, `selenium`, and `BeautifulSoup` to gather leaderboard data.
- **Storage:** Logs results to MySQL (`leaderboard_log`, `leaderboard_log_left`, `general_leaderboard_log`, `season_points`, `assigned_points_weeks`, `previous_leaders`).
- **Discord Integration:** `discord.py` with rich embeds and dropdown menus.
- **Dynamic Week/Season Handling:** URLs and settings pulled from `.env` and synced via Google Sheets.
- **Data Retry:** All DB operations retry if MySQL is temporarily down.
- **Leader Change Loop:** Bot constantly monitors for leader changes in all active rally stages.
- **Reconnect Watchdog:** Alerts bot owner if it gets stuck in a loop.

---

## 🗓️ Installation Guide

### 1. Install Python

Download it from [python.org](https://www.python.org/downloads/).  
Make sure to check **"Add Python to PATH"** during installation.

---

### 2. Install Required Packages

```bash
pip install -r requirements.txt
```

---

### 3. Create a Discord Bot

1. Visit [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **"New Application"**.
3. Navigate to **Bot**, click **"Add Bot"**, and enable **Message Content Intent**.

---

### 4. Set Permissions & Invite Bot

- **Permissions Needed:**
  - Send Messages
  - Embed Links
  - Read Message History
  - Use External Emojis

Use the OAuth2 URL Generator to get an invite link and add the bot to your server.

---

### 5. Configure `.env`

```env
DISCORD_BOT_TOKEN=your_token
DISCORD_CHANNEL_ID=your_channel_id
BOT_OWNER_ID=your_discord_user_id
ALLOWED_SYNC_USERS=comma_separated_user_ids
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=rbr_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=rbr_leaderboards
GOOGLE_SHEET_NAME=RBR_Tracking
LEAGUE_NAME=Your League Name
INFO_URL=https://example.com/info
RALLY_NAME=My Rally
RALLY_PASSWORD=secret
S1W1_LEADERBOARD=https://example.com
S1W1_LEG_1_1=https://example.com
...
```

> 🔐 Never share your bot token publicly!

---

### 6. Google Sheets Integration

Allows you to dynamically manage rally config + update `.env` with a Google Form.

#### a. Create Google Sheet
1. Create a new sheet called **`RBR_Tracking`**.
2. Sheet1 should collect rally details:
   - Season Number
   - Week Number
   - Leaderboard URL
   - New Rally Name (optional)
   - LEG 1 STAGE 1 URL, LEG 1 STAGE 2 URL, ...

#### b. Set Up Service Account
1. Visit [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable **Google Sheets API** & **Google Drive API**.
3. Create a **Service Account**, download its JSON credentials.
4. Rename the file to `google_creds.json` and place it in your bot directory.
5. Share your Google Sheet with the service account email.

#### c. Run the Sync
```bash
!sync
```
This will update `.env` and load rally configuration from the sheet.

---

### 7. MySQL Database Setup

```sql
CREATE DATABASE rbr_leaderboards CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rbr_leaderboards;

CREATE TABLE leaderboard_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_name VARCHAR(255),
    position INT,
    driver_name VARCHAR(255),
    vehicle VARCHAR(255),
    time VARCHAR(50),
    diff_prev VARCHAR(50),
    diff_first VARCHAR(50),
    season INT,
    week INT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE leaderboard_log_left (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_name VARCHAR(255),
    position INT,
    driver_name VARCHAR(255),
    vehicle VARCHAR(255),
    time VARCHAR(50),
    diff_prev VARCHAR(50),
    diff_first VARCHAR(50),
    season INT,
    week INT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE general_leaderboard_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(255),
    position INT,
    vehicle VARCHAR(255),
    time VARCHAR(50),
    diff_prev VARCHAR(50),
    diff_first VARCHAR(50),
    season INT,
    week INT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE previous_leaders (
    track_name VARCHAR(255) PRIMARY KEY,
    leader_name VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE season_points (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(255),
    season INT,
    points INT
);

CREATE TABLE assigned_points_weeks (
    season INT,
    week INT,
    PRIMARY KEY (season, week)
);
```

---

### 8. Enable Developer Mode in Discord

- Go to **User Settings > Advanced > Developer Mode**.
- Right-click a channel → **Copy Channel ID** → paste it into `.env`.

---

### 9. Run the Bot

```bash
python RBR_Bot.py
```

The bot will initialize past week scraping, post to Discord, and begin watching for updates.

---

## 📃 File Structure

```
🔍 your_repo/
🔹 RBR_Bot.py           # Main bot logic
🔹 requirements.txt     # Dependencies
🔹 .env                 # Config from Discord/MySQL/Google
🔹 google_creds.json    # Service account credentials
🔹 logs/                # Daily logs (commands, scraping, errors)
```

---

## 🤝 Contribute & Get Support

Want to contribute or report a bug? Pull requests and issue reports are welcome!  
Join the support community here:

**[🌐 Discord Support Server](https://discord.gg/HbRaM2taQG)**

---

## 📜 License

This project is open-source and licensed under the **GNU General Public License v3**.  
Feel free to modify and distribute it under the terms of the license.

