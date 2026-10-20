update_sources = [
  '__init__.py',
  'page.py',
  'row.py',
]

install_data(update_sources, install_dir: moduledir / 'widgets' / 'updates')
blueprints += custom_target('updates-blueprints',
  input: files(
    'page.blp',
    'row.blp'
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
