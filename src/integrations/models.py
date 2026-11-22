from gi.repository import Gdk, Gio, GObject


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
    scanlator = GObject.Property(type=str, default="")
    page_count = GObject.Property(type=int, default=0)
    upload_date = GObject.Property(type=str, default="")
    fetched_at = GObject.Property(type=str, default="")
    last_read_at = GObject.Property(type=str, default="")
    is_bookmarked = GObject.Property(type=bool, default=False)
    is_downloaded = GObject.Property(type=bool, default=False)
    is_read = GObject.Property(type=bool, default=False)
    last_page_read = GObject.Property(type=int, default=0)


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


class CardOptions(GObject.Object):
    __gtype_name__ = 'KaoriCardOptions'
    display_mode = GObject.Property(type=str, default="comfortable")
    show_unread_badge = GObject.Property(type=bool, default=True)
    show_download_badge = GObject.Property(type=bool, default=False)


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.card = CardOptions()


class ChapterOptions(GObject.Object):
    __gtype_name__ = 'KaoriChapterOptions'
    sort_key = GObject.Property(type=str, default="source")
    descending = GObject.Property(type=bool, default=True)
    filter_unread = GObject.Property(type=bool, default=False)
    filter_downloaded = GObject.Property(type=bool, default=False)
    filter_bookmarked = GObject.Property(type=bool, default=False)
    scanlator = GObject.Property(type=str, default="")
    display_mode = GObject.Property(type=str, default="title")

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
