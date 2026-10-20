source_sources = [
  '__init__.py',
  'sources.py',
  'card.py',
  'page.py',
  'filter.py'
]

install_data(source_sources, install_dir: moduledir / 'widgets' / 'source')
blueprints += custom_target('source-blueprints',
  input: files(
    'card.blp',
    'filter.blp',
    'page.blp',
    'sources.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
