# 🌟 RBR Discord Bot (MySQL Edition)

Welcome to the **RBR Discord Bot (MySQL Edition)**!
This bot scrapes online leaderboards from [rallysimfans.hu](https://rallysimfans.hu/) and posts real-time updates to Discord, powered by **MySQL** integration and advanced stat tracking.

---

## 🏎️ Features

* **Automated Leaderboard Updates** – Scrapes and posts latest standings directly to Discord.
* **Live Leader Change Detection** – Announces when drivers take the lead in any rally stage.
* **MySQL 8.0 Database Backend** – All data logged asynchronously using `aiomysql`.
* **Interactive Dropdowns** – Easily choose drivers or weeks using Discord UI.
* **Google Sheets Integration** – Syncs rally configs from Google Form submissions.
* **Admin-Only Controls** – Run syncs, rescrapes, restarts, and more.
* **Stats, Trends & History** – Track performance over time, podiums, and car usage.
* **Stage Completion Breakdown** – Shows who has/haven't completed each stage.
* **Stage Win Tracker** – Highlights most successful drivers per stage.
* **Season Summaries** – One-command overview of entire season performance.
* **Closest Finishes Tracker** – Finds top 10 closest real-time stage battles per week or season.
* **Custom Points System** – Calculates seasonal points automatically.
* **Full Archived Access** – Query any season/week in history.
* **Left & Right Leaderboards** – Captures both panels from RallySimFans.hu.
* **Reconnect Watchdog** – Alerts if bot fails to reconnect or gets stuck.

---

## 💬 Commands

### 👤 Driver Commands

```
!search [driver] [s#w#]        → Driver's full results by stage (dropdown if blank)
!stats [driver]                → Total events, avg pos, wins, podiums, car, points
!history [driver]             → Week-by-week position and gap on general leaderboard
!trend [driver]               → Performance trend across weeks (time, icons, podiums)
!progress [driver]            → Stage-by-stage completion for current week
```

### 📈 Leaderboard & Season

```
!leaderboard [s#w#]           → General leaderboard for a specific week
!leg1 to !leg6 [s#w#]         → Stage-specific leaderboard for each leg
!points                       → Full season standings
!seasonsummary [s# or now]   → Recap of legs, stages, drivers, points
!mostwins                    → Top 10 most stage wins
!compare driver1 vs driver2   → Head-to-head breakdown
!closestfinishes [s# or s#w#] → Top 10 closest real gaps (week or full season)
```

### 🛠️ Admin Commands

```
!sync                         → Force sync from Google Sheets
!rescrape [s#w# or s#]        → Re-scrape week or season
!recalpoints                  → Recalculate points from DB
!dbcheck                      → Check DB health and row counts
!restart                      → Restart the bot
!shutdown                     → Shut the bot down
```

### 🎯 Fun / Utility

```
!cmd                          → Lists all commands
!info                         → Rally info (name, password, URL)
!skillissue                   → Motivational message for last-place driver
```

> 💡 You can run `!search`, `!stats`, `!history`, `!trend`, or `!progress` with no driver name to open dropdown selection.

---

## ⚙️ How It Works

* **Scraping:** Uses `requests` + `BeautifulSoup` to pull data from rallysimfans.hu.
* **Database:** MySQL schema logs results, stats, and point data.
* **Bot Framework:** Built on `discord.py` with async task loops and UI elements.
* **Environment Driven:** URLs, tokens, and sync data pulled from `.env` and Google Sheets.
* **Offline-Resilient:** DB ops retry automatically if MySQL goes down.
* **Leader Watch:** Background loops check for leaderboard changes and notify.
* **Reconnect Watchdog:** Bot notifies if stuck in a reconnect loop.

---

## 🗓️ Installation Guide

### 🔧 Requirements:

* Python 3.10+
* MySQL 8.0+ running and reachable
* Discord bot token
* Google service account JSON file

### 🛠️ Setup Steps

1. Clone this repo:

```bash
git clone https://github.com/Snaze878/RBR_Bot_MySQL.git
cd RBR_Bot_MySQL
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your `.env` file with:

```
DISCORD_TOKEN=...
DB_HOST=...
DB_USER=...
DB_PASS=...
DB_NAME=...
GOOGLE_SHEET_KEY=...
```

4. Place your `google_creds.json` in the root folder.
5. Run the bot:

```bash
Start_Bot.cmd
```

---

## 📁 File Structure

```
RBR_Bot_MySQL/
├── Start_Bot.cmd              # Launch the bot on Windows
├── RBR_Bot.py                 # Core bot logic
├── .env                       # Secrets and config
├── google_creds.json          # Google Sheets service account
├── requirements.txt           # Python dependencies
├── logs/                      # Output logs (daily rotation)
```

---

## 📸 Example Output

<details>
<summary>Click to expand</summary>

![Leaderboard](https://github.com/user-attachments/assets/90b1d28f-da66-4c3d-802e-830d6a74555c)
![Points](https://github.com/user-attachments/assets/19732ff9-c940-434e-a30d-d2083f5d8f8c)
![Search](https://github.com/user-attachments/assets/ec90fb46-e554-4c52-b394-a3755f76c0d3)
![Leg](https://github.com/user-attachments/assets/250b7ff8-7e20-4422-9538-f18af0a84f6c)
![Stats](https://github.com/user-attachments/assets/7ccdfff6-0e4c-4047-b29c-deb27f43c63f)

</details>

---

## 🤝 Contribute & Support

PRs and suggestions welcome! Join the dev/support community:

**🌐 [Discord Support Server](https://discord.gg/HbRaM2taQG)**

---

## 📜 License

This project is licensed under the **GNU GPL v3**.
