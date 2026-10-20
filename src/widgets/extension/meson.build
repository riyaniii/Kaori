extension_sources = [
  '__init__.py',
  'extensions.py',
  'card.py',
  'dialog.py',
]

install_data(extension_sources, install_dir: moduledir / 'widgets' / 'extension')
blueprints += custom_target('extension-blueprints',
  input: files(
    'card.blp',
    'dialog.blp',
    'extensions.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
