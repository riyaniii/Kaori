from datetime import date, datetime
from gettext import gettext as _

MILLISECONDS_LIMIT = 1e11


def to_datetime(value) -> datetime | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number <= 0:
        return None

    if number > MILLISECONDS_LIMIT:
        number /= 1000

    try:
        return datetime.fromtimestamp(number)
    except (OverflowError, OSError, ValueError):
        return None


def day_title(day: date | None) -> str:
    if day is None:
        return _("Unknown date")

    today = date.today()
    delta = (today - day).days
    if delta == 0:
        return _("Today")
    if delta == 1:
        return _("Yesterday")

    text = f"{day:%A}, {day:%B} {day.day}"
    if day.year != today.year:
        text += f", {day.year}"
    return text
