import asyncio
import re

from gi.repository import Gtk, Pango, GLib, GObject, Gio

from ...integrations import models

CONTENT_LABELS = {"synopsis", "summary", "description", "plot", "overview", "story"}

LABEL_LINE = re.compile(
    r'^(?:#{1,6}\s*)?'
    r'(?:\*{1,2}|_{1,2})?'
    r'([A-Za-z][A-Za-z \-\'&/]{1,40}?)'
    r'(?:\*{1,2}|_{1,2})?'
    r'\s*:\s*(.*)$'
)
BULLET_LINE = re.compile(r'^\s*(?:[•\-\*]|\d+[\.\)])\s+')
SOURCE_LINE = re.compile(r'^\(.*\)$')
MD_LINK = re.compile(r'\[([^\]]*)\]\([^)]*\)')
MD_EMPHASIS = re.compile(r'(\*{1,3}|_{1,3})(.+?)\1')
MD_HEADER = re.compile(r'^#{1,6}\s*')
MD_INLINE_CODE = re.compile(r'`([^`]*)`')


def strip_markdown_inline(text: str) -> str:
    text = MD_HEADER.sub('', text)
    text = MD_LINK.sub(r'\1', text)
    text = MD_INLINE_CODE.sub(r'\1', text)
    text = MD_EMPHASIS.sub(r'\2', text)
    text = MD_EMPHASIS.sub(r'\2', text)
    return text


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r'\n\s*\n+', text.strip()) if p.strip()]


def is_bullet_list(paragraph: str) -> bool:
    lines = paragraph.split('\n')
    bulletish = sum(1 for line in lines if BULLET_LINE.match(line))
    return bulletish > 0 and bulletish >= len(lines) / 2


def strip_bullet(line: str) -> str:
    return BULLET_LINE.sub('', line)


def parse_label(raw_line: str) -> tuple[str | None, str]:
    match = LABEL_LINE.match(raw_line.strip())
    if match:
        return match.group(1).strip().lower(), match.group(2)
    return None, raw_line


def strip_labels(lines: list[str]) -> str:
    cleaned = []
    for line in lines:
        _, rest = parse_label(line)
        rest = strip_markdown_inline(strip_bullet(rest)).strip()
        if rest:
            cleaned.append(rest)
    return '\n'.join(cleaned).strip()

def extract_meat(description: str) -> str:
    paragraphs = split_paragraphs(description)
    labeled = []      # paragraphs explicitly marked Synopsis/Summary/etc.
    unlabeled = []    # plain prose paragraphs with no label
    fallback_chunks = []

    for para in paragraphs:
        if SOURCE_LINE.match(para) or is_bullet_list(para):
            continue

        lines = para.split('\n')
        first_label, first_rest = parse_label(lines[0])

        if first_label is None:
            cleaned = strip_labels(lines)
            if cleaned:
                unlabeled.append(cleaned)
            continue

        if first_label in CONTENT_LABELS:
            cleaned = strip_labels([first_rest] + lines[1:])
            if cleaned:
                labeled.append(cleaned)
            continue

        cleaned = strip_labels(lines)
        if cleaned:
            fallback_chunks.append(cleaned)

    if labeled:
        return max(labeled, key=len)
    if unlabeled:
        return max(unlabeled, key=len)
    if fallback_chunks:
        return max(fallback_chunks, key=len)
    return strip_labels(description.strip().split('\n'))


@Gtk.Template(resource_path='/com/rini/kaghez/manga/overview.ui')
class MangaOverview(Gtk.Box):
    __gtype_name__ = "KaghezMangaOverview"

    model = GObject.Property(type=models.Manga)

    genres = Gtk.Template.Child()

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.populate_genres()

        if self.model.paintable is None and self.model.thumbnail_url:
            self.suwayomi = Gio.Application.get_default().suwayomi
            asyncio.create_task(self.load_thumbnail())

    async def load_thumbnail(self):
        paintable = await self.suwayomi.getPaintable(self.model.thumbnail_url)
        if paintable:
            self.model.paintable = paintable

    def populate_genres(self):
        for genre in self.model.genre[:6]:
            button = Gtk.Button(
                child=Gtk.Label(
                    label=genre,
                    ellipsize=Pango.EllipsizeMode.END
                )
            )
            self.genres.append(button)

    @Gtk.Template.Callback()
    def get_shortened_description(self, obj, description):
        if not description:
            return ""

        meat = extract_meat(description)

        l = 600
        if len(meat) <= l:
            return meat
        return meat[:l].rstrip() + "…"

    @Gtk.Template.Callback()
    def on_overview_clicked(self, *_args):
        manga_id = self.model.id
        self.activate_action("app.show_manga", GLib.Variant("i", manga_id))
