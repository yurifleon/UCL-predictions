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
