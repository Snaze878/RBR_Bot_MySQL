# 🧰 Advanced Setup: MySQL Database + Google Sheets Integration

This guide provides **step-by-step** instructions to properly configure the MySQL database and Google Sheets integration used by the RBR Discord Bot.

---

## 🔧 Part 1: MySQL Database Setup

### ✅ Requirements
- MySQL Server (8.0 recommended)
- A MySQL user with permissions to create and modify tables

### 🏗️ Setup Process

1. **Log into MySQL**
```bash
mysql -u root -p
```

2. **Create the database and switch to it**
```sql
CREATE DATABASE rbr_leaderboards CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rbr_leaderboards;
```

3. **Create tables**
```sql
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

4. **Create MySQL User (Optional)**
```sql
CREATE USER 'rbr_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON rbr_leaderboards.* TO 'rbr_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## 📊 Part 2: Google Sheets Integration

### ✅ Requirements
- Google Account
- Access to Google Cloud Console
- Discord Bot running in a directory with `google_creds.json`

### 📄 Sheet Format
Create a sheet named `RBR_Tracking`. The first sheet (Sheet1) should include:

| Season | Week | Leaderboard URL | Rally Name | LEG 1 STAGE 1 | LEG 1 STAGE 2 | ... |
|--------|------|------------------|------------|----------------|----------------|-----|

You can add up to 6 legs and 12 stages. The bot will dynamically detect and apply these.

### 🛠️ Setup Steps

1. **Create Google Cloud Project**
   - Visit: https://console.cloud.google.com/
   - Create a new project

2. **Enable APIs**
   - Google Sheets API
   - Google Drive API

3. **Create Service Account**
   - IAM & Admin → Service Accounts → New Service Account
   - Create and download the JSON credentials
   - Rename to `google_creds.json` and place it in your bot folder

4. **Share Sheet Access**
   - Open your `RBR_Tracking` sheet
   - Share with the email in your `google_creds.json`

5. **Update .env**
```env
GOOGLE_SHEET_NAME=RBR_Tracking
```

6. **Run the Sync Command**
```bash
!sync
```
The bot will load all environment variables and rally configuration from the sheet.

---

## ⚙️ Optional: Auto-Restart Script for Bot

To support the `!restart` command, create a `.cmd` file in your bot folder:

### `run_bot.cmd`
```cmd
@echo off
:loop
echo [BOT] Starting...
python RBR_Bot.py
echo [BOT] Restarting in 3 seconds...
timeout /t 3 >nul
goto loop
```

Run this file instead of `python RBR_Bot.py` to allow restart functionality.

---

## 🔁 Ongoing Use
- Add a new row in your Google Sheet for each new rally week.
- Run `!sync` to update.
- The bot will scrape and update the database, generate point totals, and post results automatically.

For issues, check `logs/sync_errors.log` or use the `!dbcheck` command.

---

Need help? Join the [Support Discord Server](https://discord.gg/HbRaM2taQG).

