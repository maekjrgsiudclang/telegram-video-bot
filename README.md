# Telegram Video Downloader Bot

Send a direct video link, get the video back in Telegram. Supports quality selection and automatic splitting for large files.

## Setup (Local)

1. Get a bot token from [@BotFather](https://t.me/BotFather) on Telegram
2. Install [ffmpeg](https://ffmpeg.org/download.html)
3. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Set your token:
   ```
   set TELEGRAM_BOT_TOKEN=your_token
   ```
5. Run:
   ```
   python bot.py
   ```

## Deploy to Render (Free, 24/7, No Credit Card)

Render's free tier spins down after 15 min of no HTTP traffic. We fix this with a free cron job that pings the bot every 10 minutes to keep it alive.

### Step 1: Push Code to GitHub

Create a new GitHub repo and push your code:
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/telegram-video-bot.git
git push -u origin main
```

### Step 2: Create Render Account

1. Go to https://render.com and sign up with GitHub (no credit card needed)
2. Click **New +** > **Web Service**
3. Connect your GitHub repo
4. Settings:
   - **Name:** `telegram-video-bot`
   - **Runtime:** Docker
   - **Plan:** Free
5. Add environment variable:
   - **Key:** `TELEGRAM_BOT_TOKEN`
   - **Value:** your bot token
6. Click **Create Web Service**

Wait 2-3 minutes for it to build and deploy.

### Step 3: Keep It Alive (Important!)

Without this, the bot sleeps after 15 min of inactivity.

1. Go to https://cron-job.org (free, no credit card)
2. Create an account
3. Click **Create Job**
4. Settings:
   - **URL:** `https://telegram-video-bot.onrender.com/health`
   - **Schedule:** `*/10 * * * *` (every 10 minutes)
   - **Request Method:** GET
5. Save

Your bot now stays awake 24/7.

### Useful Render Commands

- **Redeploy:** Go to your service > **Manual Deploy** > **Deploy latest commit**
- **Logs:** Go to your service > **Logs** tab
- **Update token:** Go to **Environment** > edit `TELEGRAM_BOT_TOKEN`

## Commands

- `/start` — Welcome message
- `/help` — Usage instructions
- Send any direct video URL — Bot downloads and sends it back

## Supported Sites

Any direct HTTP/HTTPS video link (e.g., from webtor.io, direct `.mp4` links, etc.)

## How It Works

1. You send a direct video URL
2. Bot shows file size and quality options (best/720p/480p/360p)
3. You pick a quality
4. Bot downloads the video
5. If quality isn't "best", bot compresses with ffmpeg
6. If file > 45MB, bot splits into parts
7. Bot sends all parts as Telegram video messages
8. Temp files are cleaned up automatically
