from gql import gql

CHAPTER_FIELDS = {
    'mangaId': 'manga_id',
    'sourceOrder': 'source_order',
    'chapterNumber': 'chapter_number',
    'name': 'name',
    'pageCount': 'page_count',
    'uploadDate': 'upload_date',
    'fetchedAt': 'fetched_at',
    'lastReadAt': 'last_read_at',
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

SERVER_SETTINGS = (
    'downloadAsCbz',
    'downloadsPath',
    'globalUpdateInterval',
    'backupPath',
    'backupTime',
    'backupInterval',
    'backupTTL',
    'maxSourcesInParallel',
    'localSourcePath',
    'flareSolverrEnabled',
    'flareSolverrUrl',
    'flareSolverrTimeout',
    'flareSolverrSessionName',
    'flareSolverrSessionTtl',
    'flareSolverrAsResponseFallback',
    'socksProxyEnabled',
    'socksProxyVersion',
    'socksProxyHost',
    'socksProxyPort',
    'socksProxyUsername',
    'socksProxyPassword',
)
SERVER_SETTINGS_FIELDS = "\n".join(SERVER_SETTINGS)

MANGA_FIELDS = {
    'title': 'title',
    'author': 'author',
    'artist': 'artist',
    'description': 'description',
    'genre': 'genre',
    'status': 'status',
    'initialized': 'initialized',
    'inLibrary': 'in_library',
    'unreadCount': 'unread_count',
    'realUrl': 'real_url',
    'thumbnailUrl': 'thumbnail_url',
}
MANGA_CORE_FIELDS = "id\n" + "\n".join(MANGA_FIELDS)

MANGA_LIBRARY_FIELDS = {
    'inLibraryAt': 'in_library_at',
    'bookmarkCount': 'bookmark_count',
    'downloadCount': 'download_count',
    'hasDuplicateChapters': 'has_duplicate_chapters',
    'sourceId': 'source_id',
}

MANGA_CHAPTER_LINKS = {
    'firstUnreadChapter': 'first_unread_chapter',
    'lastReadChapter': 'last_read_chapter',
    'latestFetchedChapter': 'latest_fetched_chapter',
    'latestUploadedChapter': 'latest_uploaded_chapter',
}

MANGA_LIBRARY_QUERY = "\n".join(MANGA_LIBRARY_FIELDS) + """
  latestFetchedChapter { id fetchedAt }
  latestUploadedChapter { id uploadDate }
"""

GET_LIBRARY = gql("""
query GetLibrary {
  mangas(condition: { inLibrary: true }) {
    nodes {
      """ + MANGA_CORE_FIELDS + """
      firstUnreadChapter { id sourceOrder }
      lastReadChapter { id sourceOrder lastReadAt }
      chapters { totalCount }
      """ + MANGA_LIBRARY_QUERY + """
    }
  }
}
""")

GET_CATEGORIES = gql("""
query GetCategories {
  categories {
    nodes {
      id
      name
      order
      default
      mangas { nodes { id } }
    }
  }
}
""")

UPDATE_LIBRARY = gql("""
mutation UpdateLibrary($categories: [Int!]) {
  updateLibrary(input: { categories: $categories }) {
    updateStatus { jobsInfo { isRunning totalJobs finishedJobs } }
  }
}
""")

GET_LIBRARY_UPDATE_STATUS = gql("""
query GetLibraryUpdateStatus {
  libraryUpdateStatus { jobsInfo { isRunning totalJobs finishedJobs } }
}
""")

GET_EXTENSION_STORES = gql("""
query GetExtensionStores {
  extensionStores {
    nodes { name indexUrl isLegacy }
  }
}
""")

ADD_EXTENSION_STORE = gql("""
mutation AddExtensionStore($indexUrl: String!) {
  addExtensionStore(input: { indexUrl: $indexUrl }) {
    extensionStore { name indexUrl }
  }
}
""")

REMOVE_EXTENSION_STORE = gql("""
mutation RemoveExtensionStore($indexUrl: String!) {
  removeExtensionStore(input: { indexUrl: $indexUrl }) {
    extensionStore { indexUrl }
  }
}
""")

GET_SOURCES = gql("""
query GetSources {
  sources {
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
query GetChaptersManga($mangaId: Int!) {
  chapters(condition: { mangaId: $mangaId }) {
    nodes {
      """ + CHAPTER_FULL_FIELDS + """
    }
    totalCount
  }
}
""")

CHAPTER_FEED_FIELDS = CHAPTER_FULL_FIELDS + """
manga {
  """ + MANGA_CORE_FIELDS + """
  firstUnreadChapter { id }
  lastReadChapter { id }
}
"""

GET_RECENTLY_READ_CHAPTERS = gql("""
query GetRecentlyReadChapters($first: Int, $offset: Int) {
  chapters(
    filter: { lastReadAt: { greaterThan: "0" } }
    order: [{ by: LAST_READ_AT, byType: DESC }]
    first: $first
    offset: $offset
  ) {
    nodes {
      """ + CHAPTER_FEED_FIELDS + """
    }
    pageInfo { hasNextPage }
  }
}
""")

GET_RECENTLY_UPDATED_CHAPTERS = gql("""
query GetRecentlyUpdatedChapters($first: Int, $offset: Int) {
  chapters(
    filter: { inLibrary: { equalTo: true } }
    order: [{ by: FETCHED_AT, byType: DESC }, { by: SOURCE_ORDER, byType: DESC }]
    first: $first
    offset: $offset
  ) {
    nodes {
      """ + CHAPTER_FEED_FIELDS + """
    }
    pageInfo { hasNextPage }
  }
}
""")

GET_LAST_UPDATE_TIMESTAMP = gql("""
query GetLastUpdateTimestamp {
  lastUpdateTimestamp { timestamp }
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
    """ + SERVER_SETTINGS_FIELDS + """
  }
}
""")

SET_SERVER_SETTINGS = gql("""
mutation SetServerSettings($settings: PartialSettingsTypeInput!) {
  setSettings(input: {settings: $settings}) {
    settings {
      """ + SERVER_SETTINGS_FIELDS + """
    }
  }
}
""")

SET_MANGA_CATEGORIES = gql("""
mutation SetMangaCategories($id: Int!, $add: [Int!], $remove: [Int!]) {
  updateMangaCategories(
    input: { id: $id, patch: { addToCategories: $add, removeFromCategories: $remove } }
  ) {
    manga { id }
  }
}
""")

CREATE_CATEGORY = gql("""
mutation CreateCategory($name: String!) {
  createCategory(input: { name: $name }) {
    category { id }
  }
}
""")

UPDATE_CATEGORY = gql("""
mutation UpdateCategory($id: Int!, $name: String!) {
  updateCategory(input: { id: $id, patch: { name: $name } }) {
    category { id name }
  }
}
""")

DELETE_CATEGORY = gql("""
mutation DeleteCategory($id: Int!) {
  deleteCategory(input: { categoryId: $id }) {
    category { id }
  }
}
""")

REORDER_CATEGORY = gql("""
mutation ReorderCategory($id: Int!, $position: Int!) {
  updateCategoryOrder(input: { id: $id, position: $position }) {
    categories { id order }
  }
}
""")

SET_CATEGORY_DEFAULT = gql("""
mutation SetCategoryDefault($id: Int!, $default: Boolean!) {
  updateCategory(input: { id: $id, patch: { default: $default } }) {
    category { id default }
  }
}
""")
