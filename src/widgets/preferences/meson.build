preference_sources = [
  '__init__.py',
  'preferences.py',
  'extension_stores.py'
]

install_data(preference_sources, install_dir: moduledir / 'widgets' / 'preferences')
blueprints += custom_target('preferences-blueprints',
  input: files(
    'extension_stores.blp',
    'preferences.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
