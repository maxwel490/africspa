from yourapp import db, app
from yourapp.models import *  # import all models

with app.app_context():
    db.create_all()
# DEBUG:     print("Database tables created/updated successfully")