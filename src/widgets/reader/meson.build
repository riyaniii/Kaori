reader_sources = [
  '__init__.py',
  'page.py',
  'dialog.py',
  'base.py',
  'single.py',
  'double.py',
  'webtoon.py',
  'canvas.py'
]

install_data(reader_sources, install_dir: moduledir / 'widgets' / 'reader')
blueprints += custom_target('reader-blueprints',
  input: files(
    'dialog.blp',
    'double.blp',
    'page.blp',
    'single.blp',
    'webtoon.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
