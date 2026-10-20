search_sources = [
  '__init__.py',
  'page.py'
]

install_data(search_sources, install_dir: moduledir / 'widgets' / 'search')
blueprints += custom_target('search-blueprints',
  input: files(
    'page.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
