download_sources = [
  '__init__.py',
  'page.py',
  'row.py',
  'dialog.py'
]

install_data(download_sources, install_dir: moduledir / 'widgets' / 'download')
blueprints += custom_target('download-blueprints',
  input: files(
    'dialog.blp',
    'page.blp',
    'row.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
