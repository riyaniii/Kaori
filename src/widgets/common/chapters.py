from gettext import gettext as _


def chapter_title(name, number):
    if name:
        return name
    return _("Chapter {}").format(f"{number:g}")


def chapter_summary(name, number, is_read, page_count, last_page_read, opened):
    parts = [chapter_title(name, number)]
    if is_read:
        parts.append(_("Finished"))
    elif page_count > 0 and (opened or last_page_read > 0):
        parts.append(_("Page {} of {}").format(last_page_read + 1, page_count))
    return " · ".join(parts)
