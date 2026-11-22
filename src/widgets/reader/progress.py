import asyncio

from gi.repository import GLib

PROGRESS_SAVE_DELAY = 1000


class ReaderProgress:
    def __init__(self, page):
        self.page = page
        self.suwayomi = page.suwayomi
        self.dirty = []
        self.save_id = 0

    def update(self):
        page = self.page
        chapter = page.chapter_model
        if chapter is None or page.loading() or chapter.page_count <= 0:
            return

        page_number = page.position + 1
        if page_number <= chapter.last_page_read:
            return

        seen = page.position + page.active_reader.step
        chapter.update_data(
            last_page_read=page_number,
            is_read=chapter.is_read or seen >= chapter.page_count,
        )
        self.queue(chapter)

    def queue(self, chapter):
        if chapter not in self.dirty:
            self.dirty.append(chapter)
        if not self.save_id:
            self.save_id = GLib.timeout_add(PROGRESS_SAVE_DELAY, self.flush)

    def flush(self):
        self.save_id = 0
        for chapter in self.dirty:
            asyncio.create_task(
                self.suwayomi.updateChapter(
                    chapter_id=chapter.id,
                    is_read=chapter.is_read,
                    last_page_read=chapter.last_page_read,
                )
            )
        self.dirty = []
        return GLib.SOURCE_REMOVE

    def finish(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.flush()
