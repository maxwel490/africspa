"""
Shared utility functions used across multiple domains.
"""
from datetime import datetime, timedelta


def get_week_start(date_value):
    """Calculate the start of the week (Sunday) for a given date."""
    days_to_subtract = (date_value.weekday() + 1) % 7
    return (date_value - timedelta(days=days_to_subtract)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def get_fourth_sunday_week_start(date_value):
    """Calculate the start of the 4th Sunday week for a given date's month."""
    month_start = datetime(date_value.year, date_value.month, 1)
    first_sunday_offset = (6 - month_start.weekday()) % 7
    fourth_sunday = month_start + timedelta(days=first_sunday_offset + 21)
    return get_week_start(fourth_sunday)


def normalize_specialty(specialty_value):
    """Normalize specialty values for consistent matching."""
    value = (specialty_value or '').strip().lower()
    if 'cornrow' in value or 'conrow' in value:
        return 'Conrows'
    if 'braid' in value:
        return 'Braids'
    if 'undo' in value:
        return 'Undo'
    if 'nail' in value:
        return 'Nails'
    if 'wash' in value:
        return 'Wash'
    if 'makeup' in value:
        return 'Makeup'
    return 'Uncategorized'
