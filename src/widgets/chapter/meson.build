chapter_sources = [
  '__init__.py',
  'row.py',
  'panel.py'
]

install_data(chapter_sources, install_dir: moduledir / 'widgets' / 'chapter')
blueprints += custom_target('chapter-blueprints',
  input: files(
    'panel.blp',
    'row.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
