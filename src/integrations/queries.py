from gql import gql

CHAPTER_FIELDS = {
    'sourceOrder': 'source_order',
    'chapterNumber': 'chapter_number',
    'name': 'name',
    'pageCount': 'page_count',
    'uploadDate': 'upload_date',
    'isBookmarked': 'is_bookmarked',
    'isDownloaded': 'is_downloaded',
    'isRead': 'is_read',
    'lastPageRead': 'last_page_read',
}
CHAPTER_FULL_FIELDS = "id\n" + "\n".join(CHAPTER_FIELDS)

EXTENSION_FIELDS = {
    'name': 'name',
    'lang': 'lang',
    'versionName': 'version_name',
    'apkUrl': 'apk_url',
    'jarUrl': 'jar_url',
    'isInstalled': 'is_installed',
    'isNsfw': 'is_nsfw',
    'contentWarning': 'content_warning',
    'hasUpdate': 'has_update',
    'isObsolete': 'is_obsolete',
}
EXTENSION_FULL_FIELDS = "pkgName\niconUrl\n" + "\n".join(EXTENSION_FIELDS)

MANGA_CORE_FIELDS = """
  id
  title
  author
  artist
  description
  genre
  status
  initialized
  inLibrary
  unreadCount
  realUrl
  thumbnailUrl
"""

GET_LIBRARY = gql("""
query GetLibrary($first: Int, $after: Cursor) {
  mangas(condition: { inLibrary: true }, first: $first, after: $after) {
    nodes {
      """ + MANGA_CORE_FIELDS + """
      firstUnreadChapter { """ + CHAPTER_FULL_FIELDS + """ }
      lastReadChapter { """ + CHAPTER_FULL_FIELDS + """ }
      chapters { totalCount }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""")

GET_EXTENSIONS = gql("""
query GetExtensions($first: Int, $after: Cursor) {
  extensions(first: $first, after: $after) {
    nodes {
      """ + EXTENSION_FULL_FIELDS + """
    }
    pageInfo { hasNextPage endCursor }
  }
}
""")

GET_SOURCES = gql("""
query GetSources($first: Int, $after: Cursor) {
  sources(filter: { lang: { in: ["en", "all"] } }, first: $first, after: $after) {
    nodes {
      id
      name
      lang
      iconUrl
      isConfigurable
      isNsfw
      extension {
        pkgName
        name
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""")

FETCH_MANGA = gql("""
mutation FetchMangaAndChapters($id: Int!, $fetchManga: Boolean!, $fetchChapters: Boolean!) {
  fetchMangaAndChapters(input: { id: $id, fetchManga: $fetchManga, fetchChapters: $fetchChapters }) {
    manga @include(if: $fetchManga) {
      """ + MANGA_CORE_FIELDS + """
      firstUnreadChapter { id }
      lastReadChapter { id }
    }
    chapters @include(if: $fetchChapters) {
      """ + CHAPTER_FULL_FIELDS + """
    }
  }
}
""")

GET_CHAPTERS_MANGA = gql("""
query GetChaptersManga($mangaId: Int!, $first: Int, $after: Cursor) {
  chapters(condition: { mangaId: $mangaId }, first: $first, after: $after) {
    nodes {
      """ + CHAPTER_FULL_FIELDS + """
    }
    pageInfo { hasNextPage endCursor }
    totalCount
  }
}
""")

FETCH_EXTENSIONS = gql("""
mutation FetchExtensions($input: FetchExtensionsInput = {}) {
  fetchExtensions(input: $input) {
    extensions {
      """ + EXTENSION_FULL_FIELDS + """
    }
  }
}
""")

UPDATE_EXTENSION = gql("""
mutation UpdateExtension($pkgName: String!, $install: Boolean, $update: Boolean, $uninstall: Boolean) {
  updateExtension(
    input: { id: $pkgName, patch: { install: $install, update: $update, uninstall: $uninstall } }
  ) {
    extension {
      """ + EXTENSION_FULL_FIELDS + """
    }
  }
}
""")

FETCH_CHAPTER_PAGES = gql("""
mutation FetchChapterPages($chapterId: Int!) {
  fetchChapterPages(input: { chapterId: $chapterId }) {
    chapter {
      id
      pageCount
      isDownloaded
      manga {
        id
        downloadCount
      }
    }
    pages
  }
}
""")

UPDATE_CHAPTER = gql("""
mutation UpdateChapter($id: Int!, $isRead: Boolean, $isBookmarked: Boolean, $lastPageRead: Int) {
  updateChapter(
    input: { id: $id, patch: { isRead: $isRead, isBookmarked: $isBookmarked, lastPageRead: $lastPageRead } }
  ) {
    chapter {
      """ + CHAPTER_FULL_FIELDS + """
      manga {
        id
        unreadCount
      }
    }
  }
}
""")

DELETE_DOWNLOADED_CHAPTER = gql("""
mutation DeleteDownloadedChapter($id: Int!) {
  deleteDownloadedChapter(input: { id: $id }) {
    chapters {
      id
      isDownloaded
      manga {
        id
        downloadCount
      }
    }
  }
}
""")

SET_MANGA_LIBRARY = gql("""
mutation SetMangaLibrary($id: Int!, $inLibrary: Boolean!) {
  updateManga(input: { id: $id, patch: { inLibrary: $inLibrary } }) {
    manga {
      id
      title
      inLibrary
      inLibraryAt
      unreadCount
    }
  }
}
""")

GET_READER_META = gql("""
query GetReaderMeta($id: Int!) {
  manga(id: $id) { id meta { key value } }
  metas { nodes { key value } }
}
""")

SET_MANGA_META = gql("""
mutation SetMangaMeta($mangaId: Int!, $key: String!, $value: String!) {
  setMangaMeta(input: { meta: { mangaId: $mangaId, key: $key, value: $value } }) {
    meta { mangaId key value }
  }
}
""")

GET_GLOBAL_READER_META = gql("""
query GetGlobalReaderMeta {
  metas { nodes { key value } }
}
""")

SET_GLOBAL_META = gql("""
mutation SetGlobalMeta($key: String!, $value: String!) {
  setGlobalMeta(input: { meta: { key: $key, value: $value } }) {
    meta { key value }
  }
}
""")

GET_DOWNLOAD_STATUS = gql("""
query GetDownloadStatus {
  downloadStatus {
    state
    queue {
      chapter { id name }
      manga { id title }
      progress
      state
      tries
    }
  }
}
""")

ENQUEUE_CHAPTER_DOWNLOAD = gql("""
mutation EnqueueChapterDownload($id: Int!) {
  enqueueChapterDownload(input: { id: $id }) { downloadStatus { state } }
}
""")

DEQUEUE_CHAPTER_DOWNLOAD = gql("""
mutation DequeueChapterDownload($id: Int!) {
  dequeueChapterDownload(input: { id: $id }) { downloadStatus { state } }
}
""")

REORDER_CHAPTER_DOWNLOAD = gql("""
mutation ReorderChapterDownload($chapterId: Int!, $to: Int!) {
  reorderChapterDownload(input: { chapterId: $chapterId, to: $to }) { downloadStatus { state } }
}
""")

CLEAR_DOWNLOADER = gql("""
mutation ClearDownloader {
  clearDownloader(input: {}) { downloadStatus { state } }
}
""")

START_DOWNLOADER = gql("""
mutation StartDownloader {
  startDownloader(input: {}) { downloadStatus { state } }
}
""")

STOP_DOWNLOADER = gql("""
mutation StopDownloader {
  stopDownloader(input: {}) { downloadStatus { state } }
}
""")

GET_SOURCE_MANGA = gql("""
mutation GetSourceManga(
  $source: LongString!
  $type: FetchSourceMangaType!
  $page: Int!
  $query: String
  $filters: [FilterChangeInput!]
) {
  fetchSourceManga(
    input: {
      source: $source
      type: $type
      page: $page
      query: $query
      filters: $filters
    }
  ) {
    hasNextPage
    mangas {
      """ + MANGA_CORE_FIELDS + """
      firstUnreadChapter { id }
      lastReadChapter { id }
      chapters {
        totalCount
      }
    }
  }
}
""")

FILTER_LEAVES = """
  ... on CheckBoxFilter { type: __typename name checkBoxDefault: default }
  ... on HeaderFilter { type: __typename name }
  ... on SelectFilter { type: __typename name values selectDefault: default }
  ... on TriStateFilter { type: __typename name triStateDefault: default }
  ... on TextFilter { type: __typename name textDefault: default }
  ... on SortFilter { type: __typename name values sortDefault: default { index ascending } }
  ... on SeparatorFilter { type: __typename name }
"""

def filter_tree(depth):
    if depth == 0:
        return FILTER_LEAVES
    return FILTER_LEAVES + "... on GroupFilter { type: __typename name filters { " + filter_tree(depth - 1) + " } }"

GET_SOURCE_FILTERS = gql("""
query GetSourceFilters($id: LongString!) {
  source(id: $id) {
    filters { """ + filter_tree(2) + """ }
  }
}
""")

GET_SERVER_SETTINGS = gql("""
query GetServerSettings {
  settings {
    downloadAsCbz
    downloadsPath
    extensionRepos
  }
}
""")

SET_SERVER_SETTINGS = gql("""
mutation SetServerSettings($settings: PartialSettingsTypeInput!) {
  setSettings(input: {settings: $settings}) {
    settings {
      downloadAsCbz
      downloadsPath
      extensionRepos
    }
  }
}
""")
