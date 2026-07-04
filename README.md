# Telegram Video Downloader Bot

Send a direct video link, get the video back in Telegram.

## Deploy to Render (Free, No Credit Card)

### Step 1: Push Code to GitHub

1. Go to https://github.com/new
2. **Repository name:** `telegram-video-bot`
3. Click **Create repository**
4. Open PowerShell and run:

```powershell
cd D:\AI\mimo
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/telegram-video-bot.git
git push -u origin main
```

### Step 2: Deploy on Render

1. Go to https://render.com > **Sign up with GitHub**
2. Click **New +** > **Web Service**
3. Connect your `telegram-video-bot` repo
4. Settings:
   - **Name:** `telegram-video-bot`
   - **Runtime:** Docker
   - **Plan:** Free
5. Add env variable: `TELEGRAM_BOT_TOKEN` = your bot token
6. Click **Create Web Service**

Wait 3 minutes for it to build.

### Step 3: Use Your Bot

Bot sleeps after 15 min idle. To wake it up:
- Go to Render dashboard > your service > **Manual Deploy** > **Deploy latest commit**

## How to Use the Bot

1. Open your bot in Telegram
2. Send a direct video URL
3. Pick a quality (best/720p/480p/360p)
4. Bot downloads and sends the video back
5. Large files (>45MB) are split into parts automatically
