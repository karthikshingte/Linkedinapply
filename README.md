# LinkedIn Easy Apply Bot

A desktop GUI app that automates LinkedIn Easy Apply job applications using Selenium — no LinkedIn API required.

## Features

- Tkinter GUI with tabbed interface
- Searches multiple job roles in sequence
- Filters to **Easy Apply** jobs only
- **Ignore list** — skip any job title containing specified words (e.g. "Senior", "Manager")
- Configurable **random delays** between actions to avoid bot detection
- Filters by date posted and experience level
- Headless mode (browser runs in background)
- Real-time colour-coded logs
- Saves your settings to `config.json`

## Screenshots

```
┌─────────────────────────────────────────┐
│  LinkedIn Easy Apply Bot                │
│  [Settings] [Job Roles] [Ignore] [Logs] │
│                                         │
│  Email: ________________                │
│  Password: _____________                │
│  Location: United States                │
│  Max Apps: 50                           │
│  Min Delay: 3s  Max Delay: 7s           │
│                                         │
│  [Start Automation]  [Stop]  [Save]     │
└─────────────────────────────────────────┘
```

## Requirements

- Python 3.10+
- Google Chrome (latest)
- ChromeDriver is downloaded automatically by `webdriver-manager`

## Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/linkedin-easy-apply-bot.git
cd linkedin-easy-apply-bot

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

## Usage

1. **Settings tab** — Enter your LinkedIn email/password, location, and delay settings.
2. **Job Roles tab** — Add the job titles you want to apply for (e.g. `Python Developer`, `Data Analyst`).
3. **Ignore List tab** — Add words to skip. Any job title containing these words will be ignored (e.g. `Senior`, `Lead`, `Manager`).
4. Click **Save Config** to persist your settings.
5. Click **Start Automation** — a Chrome window opens, logs in, and starts applying.
6. Click **Stop** at any time to gracefully end the session.

## How It Works

The bot uses Selenium to:

1. Open Chrome and log in to LinkedIn
2. Navigate to `/jobs/search/?f_LF=f_AL` (Easy Apply filter built into the URL)
3. Iterate through job cards on each page
4. Skip any job whose title contains an ignore-list word
5. Click the job, click **Easy Apply**, and navigate the multi-step form
6. Submit and move on; applies a random human-like delay between each action

## Important Notes

- **Delays matter**: Keep `Min Delay ≥ 3s` and `Max Delay ≥ 6s` to reduce the risk of LinkedIn rate-limiting your account.
- **Security checks**: If LinkedIn shows a CAPTCHA or email verification, complete it manually in the open browser window — the bot waits up to 90 seconds.
- **Easy Apply forms vary**: Some jobs have complex multi-step forms with custom questions. The bot handles standard navigation; jobs with unusual form structures are skipped and logged.
- **LinkedIn ToS**: Use responsibly and only for your own account. Excessive automation may trigger restrictions.

## Project Structure

```
├── app.py            # Tkinter GUI
├── linkedin_bot.py   # Selenium automation engine
├── requirements.txt  # Dependencies
├── config.json       # Your saved settings (gitignored — never committed)
└── .gitignore
```

## License

MIT
