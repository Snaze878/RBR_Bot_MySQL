# 🏁 RBR Discord Bot (MySQL Edition)

Welcome to the **RBR Discord Bot (MySQL Edition)**!  
This bot scrapes online leaderboards from [rallysimfans.hu](https://rallysimfans.hu/) and posts real-time updates to Discord, enhanced with **MySQL database** integration. Designed for rally communities who want historical tracking, leader change announcements, and interactive search features. This is the more complex version of https://github.com/Snaze878/RBR-Bot

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

- **Advanced Commands**  
  Search drivers, compare results, or filter by season/week.

- **Archived Data Support**  
  Past results are cached and accessible via commands.

- **CSV-Based Standings**  
  Reads from `standings.csv` to show season-long point totals.

---

## 💬 Commands

```
!search [driver] [s#w#]       → Search for a driver's results (dropdown if blank)
!leaderboard [s#w#]           → Show general leaderboard
!leg1 to !leg6 [s#w#]         → Display top 5 per stage in a rally leg
!compare driver1 vs driver2   → Head-to-head comparison
!points                       → Show CSV-based driver points
!info                         → Rally name, password, and info URL
!cmd                          → List available commands
```

---

## ⚙️ How It Works

- **Scraping:** Uses `requests`, `selenium`, and `BeautifulSoup` to gather leaderboard data.
- **Storage:** Logs results to MySQL (`leaderboard_log`, `general_leaderboard_log`, `previous_leaders`).
- **Discord Integration:** `discord.py` with rich embeds and dropdown menus.
- **Dynamic Week/Season Handling:** URLs and settings pulled from `.env`.

---

## 📅 Installation Guide

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

- Use OAuth2 Generator (Bot scope, required permissions) to invite the bot to your server.

---

### 5. Configure `.env`

Edit the `.env` file with your values:

```env
DISCORD_BOT_TOKEN=your_token
DISCORD_CHANNEL_ID=your_channel_id
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=rbr_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=rbr_leaderboards
INFO_URL=https://example.com/info
RALLY_NAME=My Rally
RALLY_PASSWORD=secret
S1W1_LEADERBOARD=https://example.com
S1W1_LEG_1_1=https://example.com
...
```

> 🔐 Never share your bot token publicly!

---

### 6. Create the MySQL Database

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

CREATE TABLE previous_leaders (
    track_name VARCHAR(255) PRIMARY KEY,
    leader_name VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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
```

---

### 7. Enable Developer Mode in Discord

- Go to **User Settings > Advanced > Developer Mode**.
- Right-click a channel → **Copy Channel ID** → paste it into `.env`.

---

### 8. Run the Bot

```bash
python RBR_Bot.py
```

You’re all set! The bot will scrape and post updates in your configured channel.

---

## 📃 File Structure

```
📁 your_repo/
🔹 RBR_Bot.py           # Main bot logic
🔹 requirements.txt     # Dependencies
🔹 .env                 # Bot + DB + URL config
🔹 standings.csv        # Season standings
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

