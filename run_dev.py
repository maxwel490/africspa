#!/usr/bin/env python3
import os

# Manually load environment variables from .env.local (development config)
env_file = os.path.join(os.path.dirname(__file__), '.env.local')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if line and not line.startswith('#'):
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from app import create_app

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    # Run in development mode
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
