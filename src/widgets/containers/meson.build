container_sources = [
  '__init__.py',
  'manga_grid.py',
  'row.py',
]

install_data(container_sources, install_dir: moduledir / 'widgets' / 'containers')
blueprints += custom_target('containers-blueprints',
  input: files(
    'manga_grid.blp',
    'row.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
