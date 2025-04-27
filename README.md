# 🌟 RBR Discord Bot (MySQL Edition)

Welcome to the **RBR Discord Bot (MySQL Edition)**!  
This bot scrapes online leaderboards from [rallysimfans.hu](https://rallysimfans.hu/) and posts real-time updates to Discord, enhanced with **MySQL database** integration. Designed for rally communities who want historical tracking, live stat summaries, and automated season management.

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
  Sync from Google Sheets, rescrape weeks, recalculate points, restart, and shutdown the bot.

- **Driver Stats, Trends & History**  
  Track individual performance, podiums, weekly progression, and vehicle usage.

- **Stage Completion Progress**  
  Monitor stage-by-stage progress with ✅/❌ breakdowns.

- **Most Wins Tracker**  
  Displays top drivers with the most stage wins.

- **Season Summaries**  
  Recap total legs, stages, drivers, points, and track time at the end of a season.

- **Closest Finishes Tracker**  
  Highlights the tightest stage battles across an entire season (skipping fake SR times).

- **Custom Points System**  
  Built-in seasonal points system that calculates standings automatically each week.

- **Archived Data Support**  
  Past results are cached and accessible via commands.

- **Two Leaderboard Tables**  
  Logs both LEFT and RIGHT leaderboard panels from rallysimfans.

- **Improved Startup and Scraping Stability**  
  Optimized backend logic for faster loading and smarter week closure detection.

- **Stability Watchdog**  
  Auto-alerts if the bot enters a reconnect loop.

---

## 💬 Commands

```
!search [driver] [s#w#]       → Search for a driver's results (dropdown if blank)
!stats [driver]               → View driver's stats: total events, avg pos, wins, podiums, vehicle, points
!history [driver]             → Week-by-week positions & gaps on general leaderboard
!trend [driver]               → Performance trend: arrows, medals, time gaps per week
!progress [driver]            → Stage-by-stage completion for current week (dropdown if blank)
!mostwins                     → List top 10 drivers with most stage wins
!leaderboard [s#w#]           → Show general leaderboard for a week
!leg1 to !leg6 [s#w#]         → Display top 5 per stage in a rally leg
!compare driver1 vs driver2   → Head-to-head comparison
!points                       → Show full season points
!seasonsummary [optional now or s#] → Summarize a season’s stats (drivers, legs, stages, points, etc.)
!closestfinishes [optional s#] → Top 10 closest real stage finishes
!info                         → Rally name, password, and info URL
!sync                         → Pull new config & data from Google Sheets
!recalpoints                  → Recalculate points for previous weeks
!dbcheck                      → Check DB connection and row counts
!restart                      → Restart the bot
!shutdown                     → Safely shut down the bot
!rescrape [s#w# or s#]        → Re-scrape specific week or season
!cmd                          → List available commands
!skillissue                   → Show last place driver this week with a motivational message
```

> 🧠 You can also run `!search`, `!stats`, `!history`, `!trend`, or `!progress` with no driver name to use dropdowns!

---

## 📸 Example Bot Output

<details>
<summary>📸 Click to view example bot output</summary>

![General Leaderboard](https://github.com/user-attachments/assets/90b1d28f-da66-4c3d-802e-830d6a74555c)
![Points Standings](https://github.com/user-attachments/assets/19732ff9-c940-434e-a30d-d2083f5d8f8c)
![Search](https://github.com/user-attachments/assets/ec90fb46-e554-4c52-b394-a3755f76c0d3)
![Leg](https://github.com/user-attachments/assets/250b7ff8-7e20-4422-9538-f18af0a84f6c)
![Stats](https://github.com/user-attachments/assets/7ccdfff6-0e4c-4047-b29c-deb27f43c63f)

</details>

---

## ⚙️ How It Works

- **Scraping:** Uses `requests`, `selenium`, and `BeautifulSoup` to gather leaderboard data.
- **Storage:** Logs results to MySQL tables (`leaderboard_log`, `leaderboard_log_left`, `general_leaderboard_log`, `season_points`, etc.).
- **Discord Integration:** `discord.py` with rich embeds and dropdown menus.
- **Dynamic Week/Season Handling:** URLs and settings pulled from `.env` and synced via Google Sheets.
- **Data Retry:** All DB operations retry if MySQL is temporarily down.
- **Leader Change Monitoring:** Bot constantly watches for leader swaps during active rallies.
- **Reconnect Watchdog:** Alerts bot owner if it gets stuck.

---

## 🗓️ Installation Guide

*(Your install guide steps stay the same — very good already.)*

---

## 📃 File Structure

```
🔍 your_repo/
🔹 RBR_Bot.py           # Main bot logic
🔹 Start_Bot.cmd        # Simple launcher for Windows
🔹 requirements.txt     # Dependencies
🔹 .env                 # Config for Discord/MySQL/Google
🔹 google_creds.json    # Google Sheets service account credentials
🔹 logs/                # Folder for daily logs (commands, scraping, errors)
```


---

## 🤝 Contribute & Get Support

Pull requests and bug reports are welcome!  
Join the support community here:

**[🌐 Discord Support Server](https://discord.gg/HbRaM2taQG)**

---

## 📜 License

This project is open-source and licensed under the **GNU General Public License v3**.

