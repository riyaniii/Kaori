home_sources = [
  '__init__.py',
  'page.py'
]

install_data(home_sources, install_dir: moduledir / 'widgets' / 'home')
blueprints += custom_target('home-blueprints',
  input: files(
    'page.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
