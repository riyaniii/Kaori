history_sources = [
  '__init__.py',
  'page.py',
  'row.py'
]

install_data(history_sources, install_dir: moduledir / 'widgets' / 'history')
blueprints += custom_target('history-blueprints',
  input: files(
    'page.blp',
    'row.blp'
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
