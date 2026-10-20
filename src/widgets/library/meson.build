library_sources = [
  '__init__.py',
  'page.py',
  'category_panel.py',
  'category_row.py',
  'category_manager.py',
  'category_edit.py'
]

install_data(library_sources, install_dir: moduledir / 'widgets' / 'library')
blueprints += custom_target('library-blueprints',
  input: files(
    'page.blp',
    'category_panel.blp',
    'category_row.blp',
    'category_manager.blp',
    'category_edit.blp'
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
