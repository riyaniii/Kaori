browse_sources = [
  '__init__.py',
  'page.py'
]

install_data(browse_sources, install_dir: moduledir / 'widgets' / 'browse')
blueprints += custom_target('browse-blueprints',
  input: files(
    'page.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
