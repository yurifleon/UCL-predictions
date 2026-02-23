# UCL Forecast

UCL Champions League Quarterfinal Prediction Game

## Running the App

```bash
# Create virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Start the app
python3 app.py
```

The app runs at **http://localhost:5000**

## Deploying to Render.com

This repo includes a `Procfile` and is intended to auto-deploy from GitHub.

```bash
# Commit and push changes to the branch tracked by Render (commonly master)
git add .
git commit -m "<clear change summary>"
git push origin master
```

If auto-deploy is disabled, trigger deploy in the Render dashboard:
- Service -> **Manual Deploy** -> **Deploy latest commit**

## Production Smoke Test (Render)

After deployment finishes, test core routes on the live service:

```bash
export PROD_BASE_URL="https://<your-service>.onrender.com"

# Expect HTTP 200
curl -i "$PROD_BASE_URL/"
curl -i "$PROD_BASE_URL/leaderboard"

# Optional content checks
curl -fsS "$PROD_BASE_URL/" | grep -qi "UCL"
curl -fsS "$PROD_BASE_URL/leaderboard" | grep -qi "leaderboard"
```

Render free instances can cold-start; wait 30-60 seconds and retry if needed.

## Registering a New User

1. Open http://localhost:5000 in your browser
2. Enter a username in the login form
3. Click "Enter" - this automatically registers you if the username is new
4. You'll be redirected to the dashboard

**Note:** Maximum 12 users allowed. Usernames are case-insensitive (stored lowercase).

## Admin Access

Default admin credentials:
- Username: `admin`
- Password: `admin123`

To access the admin panel, log in as `admin` and click "Admin" in the navigation.
