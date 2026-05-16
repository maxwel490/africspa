import os
import sys

# 1. Add your project directory to the sys.path
# This ensures Python can find your 'app' folder
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 2. Point to your virtual environment (if needed by your host)
# Usually cPanel handles this, but adding it here is a safe backup
# For local development, add the virtual environment site-packages
VENV_PATH = os.path.join(PROJECT_ROOT, 'venv/lib/python3.13/site-packages')
if os.path.exists(VENV_PATH):
    sys.path.insert(1, VENV_PATH)

# 3. Import your app factory
from app import create_app

# 4. Create the 'application' object that Passenger looks for
application = create_app()