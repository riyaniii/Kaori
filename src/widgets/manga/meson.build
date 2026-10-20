manga_sources = [
  '__init__.py',
  'card.py',
  'overview.py',
  'page.py',
]

install_data(manga_sources, install_dir: moduledir / 'widgets' / 'manga')
blueprints += custom_target('manga-blueprints',
  input: files(
    'card.blp',
    'overview.blp',
    'page.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
