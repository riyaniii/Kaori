def to_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
