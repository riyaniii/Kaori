from gettext import gettext as _

from gi.repository import Gdk, Gio, GObject


OPTION_NAMES = (
    "sort-key",
    "reverse",
    "filter-unread",
    "filter-started",
    "filter-downloaded",
    "filter-bookmarked",
    "filter-duplicates",
    "status-cancelled",
    "status-completed",
    "status-licensed",
    "status-ongoing",
    "status-hiatus",
    "status-finished",
    "status-unknown",
    "source-id",
)

STATUS_PROPERTIES = {
    "CANCELLED": "status_cancelled",
    "COMPLETED": "status_completed",
    "LICENSED": "status_licensed",
    "ONGOING": "status_ongoing",
    "ON_HIATUS": "status_hiatus",
    "PUBLISHING_FINISHED": "status_finished",
    "UNKNOWN": "status_unknown",
}


def to_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def chapter_time(chapter, name):
    if chapter is None:
        return 0
    return to_number(getattr(chapter, name))


def compare(first, second):
    return (first > second) - (first < second)


def title_key(manga):
    return (manga.title or "").lower()


def chapter_title(name, number):
    if name:
        return name
    return _("Chapter {}").format(f"{number:g}")


class BasicModel(GObject.Object):
    __gtype_name__ = 'KaoriBasicModel'

    def update_data(self, **kwargs):
        for name, value in kwargs.items():
            if getattr(self, name) != value:
                setattr(self, name, value)


class Page(BasicModel):
    __gtype_name__ = 'KaoriPage'
    index = GObject.Property(type=int, default=0)
    chapter_id = GObject.Property(type=int, default=0)
    url = GObject.Property(type=str, default="")
    paintable = GObject.Property(type=Gdk.Paintable, default=None)
    ratio = GObject.Property(type=float, default=0.68)


class Chapter(BasicModel):
    __gtype_name__ = 'KaoriChapter'
    id = GObject.Property(type=int, default=0)
    manga_id = GObject.Property(type=int, default=0)
    manga = GObject.Property(type=object, default=None)
    source_order = GObject.Property(type=int, default=0)
    chapter_number = GObject.Property(type=float, default=0.0)
    name = GObject.Property(type=str, default="")
    page_count = GObject.Property(type=int, default=0)
    upload_date = GObject.Property(type=str, default="")
    fetched_at = GObject.Property(type=str, default="")
    last_read_at = GObject.Property(type=str, default="")
    is_bookmarked = GObject.Property(type=bool, default=False)
    is_downloaded = GObject.Property(type=bool, default=False)
    is_read = GObject.Property(type=bool, default=False)
    last_page_read = GObject.Property(type=int, default=0)

    @property
    def title(self):
        return chapter_title(self.name, self.chapter_number)


class Manga(BasicModel):
    __gtype_name__ = 'KaoriManga'
    id = GObject.Property(type=int, default=0)
    title = GObject.Property(type=str, default="")
    author = GObject.Property(type=str, default="")
    artist = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    genre = GObject.Property(type=object, default=None)
    status = GObject.Property(type=str, default="")
    initialized = GObject.Property(type=bool, default=False)
    in_library = GObject.Property(type=bool, default=False)
    in_library_at = GObject.Property(type=str, default="")
    unread_count = GObject.Property(type=int, default=0)
    download_count = GObject.Property(type=int, default=0)
    bookmark_count = GObject.Property(type=int, default=0)
    has_duplicate_chapters = GObject.Property(type=bool, default=False)
    source_id = GObject.Property(type=str, default="")
    first_unread_chapter = GObject.Property(type=object, default=None)
    last_read_chapter = GObject.Property(type=object, default=None)
    latest_fetched_chapter = GObject.Property(type=object, default=None)
    latest_uploaded_chapter = GObject.Property(type=object, default=None)
    real_url = GObject.Property(type=str, default="")
    thumbnail_url = GObject.Property(type=str, default="")
    paintable = GObject.Property(type=Gdk.Paintable, default=None)
    chapters = GObject.Property(type=Gio.ListStore, default=None)
    total_chapters = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__(chapters=Gio.ListStore(item_type=Chapter))
        self.connect("notify::description", lambda *args: self.notify("short-description"))

    @GObject.Property(type=str)
    def short_description(self):
        return (self.description or "").strip().split("\n\n")[0].strip()

    def sorted_chapters(self):
        return sorted(self.chapters, key=lambda chapter: chapter.source_order)

    def first_unread_index(self):
        chapters = self.sorted_chapters()
        for index, chapter in enumerate(chapters):
            if not chapter.is_read:
                return index
        return len(chapters)


class Category(BasicModel):
    __gtype_name__ = 'KaoriCategory'
    id = GObject.Property(type=int, default=0)
    name = GObject.Property(type=str, default="")
    order = GObject.Property(type=int, default=0)
    is_default = GObject.Property(type=bool, default=False)
    manga_count = GObject.Property(type=int, default=0)


class Extension(BasicModel):
    __gtype_name__ = 'KaoriExtension'
    pkg_name = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    lang = GObject.Property(type=str, default="")
    version_name = GObject.Property(type=str, default="")
    icon_url = GObject.Property(type=str, default="")
    apk_url = GObject.Property(type=str, default="")
    jar_url = GObject.Property(type=str, default="")
    is_installed = GObject.Property(type=bool, default=False)
    is_nsfw = GObject.Property(type=bool, default=False)
    content_warning = GObject.Property(type=str, default="")
    has_update = GObject.Property(type=bool, default=False)
    is_obsolete = GObject.Property(type=bool, default=False)
    paintable = GObject.Property(type=Gdk.Paintable, default=None)
    is_busy = GObject.Property(type=bool, default=False)


class Source(BasicModel):
    __gtype_name__ = 'KaoriSource'
    id = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    lang = GObject.Property(type=str, default="")
    icon_url = GObject.Property(type=str, default="")
    is_configurable = GObject.Property(type=bool, default=False)
    is_nsfw = GObject.Property(type=bool, default=False)
    extension_pkg_name = GObject.Property(type=str, default="")
    extension_name = GObject.Property(type=str, default="")
    paintable = GObject.Property(type=Gdk.Paintable, default=None)


class Download(BasicModel):
    __gtype_name__ = 'KaoriDownload'
    chapter_id = GObject.Property(type=int, default=0)
    chapter_name = GObject.Property(type=str, default="")
    manga_id = GObject.Property(type=int, default=0)
    manga_title = GObject.Property(type=str, default="")
    progress = GObject.Property(type=float, default=0.0)
    state = GObject.Property(type=str, default="")
    tries = GObject.Property(type=int, default=0)


class LibraryOptions(GObject.Object):
    __gtype_name__ = 'KaoriLibraryOptions'
    sort_key = GObject.Property(type=str, default="alphabetical")
    reverse = GObject.Property(type=bool, default=False)
    filter_unread = GObject.Property(type=bool, default=False)
    filter_started = GObject.Property(type=bool, default=False)
    filter_downloaded = GObject.Property(type=bool, default=False)
    filter_bookmarked = GObject.Property(type=bool, default=False)
    filter_duplicates = GObject.Property(type=bool, default=False)
    status_cancelled = GObject.Property(type=bool, default=False)
    status_completed = GObject.Property(type=bool, default=False)
    status_licensed = GObject.Property(type=bool, default=False)
    status_ongoing = GObject.Property(type=bool, default=False)
    status_hiatus = GObject.Property(type=bool, default=False)
    status_finished = GObject.Property(type=bool, default=False)
    status_unknown = GObject.Property(type=bool, default=False)
    source_id = GObject.Property(type=str, default="")
    display_mode = GObject.Property(type=str, default="comfortable")
    show_unread_badge = GObject.Property(type=bool, default=True)
    show_download_badge = GObject.Property(type=bool, default=False)

    def make_actions(self):
        group = Gio.SimpleActionGroup()
        for name in OPTION_NAMES:
            group.add_action(Gio.PropertyAction.new(name, self, name))
        return group

    def matches(self, manga):
        if self.filter_unread and manga.unread_count <= 0:
            return False
        if self.filter_started and manga.last_read_chapter is None:
            return False
        if self.filter_downloaded and manga.download_count <= 0:
            return False
        if self.filter_bookmarked and manga.bookmark_count <= 0:
            return False
        if self.filter_duplicates and not manga.has_duplicate_chapters:
            return False
        if self.source_id and manga.source_id != self.source_id:
            return False

        chosen = []
        for status, name in STATUS_PROPERTIES.items():
            if getattr(self, name):
                chosen.append(status)
        if chosen and (manga.status or "UNKNOWN") not in chosen:
            return False
        return True

    def sort_number(self, manga):
        key = self.sort_key
        if key == "unread":
            return manga.unread_count
        if key == "total":
            return manga.total_chapters
        if key == "added":
            return to_number(manga.in_library_at)
        if key == "read":
            return chapter_time(manga.last_read_chapter, "last_read_at")
        if key == "fetched":
            return chapter_time(manga.latest_fetched_chapter, "fetched_at")
        return chapter_time(manga.latest_uploaded_chapter, "upload_date")

    def compare_manga(self, first, second):
        if self.sort_key == "alphabetical":
            result = compare(title_key(first), title_key(second))
        else:
            result = compare(self.sort_number(second), self.sort_number(first))
            if result == 0:
                result = compare(title_key(first), title_key(second))
        if self.reverse:
            result = -result
        return result


class HistoryEntry(BasicModel):
    __gtype_name__ = 'KaoriHistoryEntry'
    manga = GObject.Property(type=Manga)
    chapter = GObject.Property(type=Chapter)
    chapter_count = GObject.Property(type=int, default=0)
    day_number = GObject.Property(type=int, default=0)
    day_title = GObject.Property(type=str, default="")
    expanded = GObject.Property(type=bool, default=False)
    revision = GObject.Property(type=int, default=0)

    def __init__(self, manga, day_number, day_title):
        super().__init__(manga=manga, day_number=day_number, day_title=day_title)
        self.chapters = []

    def add_chapter(self, chapter):
        if chapter in self.chapters:
            return
        self.chapters.append(chapter)
        self.update_data(
            chapter=self.chapters[0],
            chapter_count=len(self.chapters),
            revision=self.revision + 1,
        )

    def set_chapters(self, chapters):
        chapters = list(chapters)
        if chapters == self.chapters:
            return
        self.chapters = chapters
        self.update_data(
            chapter=self.chapters[0],
            chapter_count=len(self.chapters),
            revision=self.revision + 1,
        )


class UpdatesEntry(BasicModel):
    __gtype_name__ = 'KaoriUpdatesEntry'
    manga = GObject.Property(type=Manga)
    chapter = GObject.Property(type=Chapter)
    chapter_count = GObject.Property(type=int, default=0)
    day_number = GObject.Property(type=int, default=0)
    day_title = GObject.Property(type=str, default="")
    expanded = GObject.Property(type=bool, default=False)
    revision = GObject.Property(type=int, default=0)

    def __init__(self, manga, day_number, day_title):
        super().__init__(manga=manga, day_number=day_number, day_title=day_title)
        self.chapters = []

    def add_chapter(self, chapter):
        if chapter in self.chapters:
            return
        self.chapters.append(chapter)
        self.update_data(
            chapter=self.first_unread(),
            chapter_count=len(self.chapters),
            revision=self.revision + 1,
        )

    def set_chapters(self, chapters):
        chapters = list(chapters)
        if chapters == self.chapters:
            return
        self.chapters = chapters
        self.update_data(
            chapter=self.first_unread(),
            chapter_count=len(self.chapters),
            revision=self.revision + 1,
        )

    def first_unread(self):
        for chapter in reversed(self.chapters):
            if not chapter.is_read:
                return chapter
        return self.chapters[0]
