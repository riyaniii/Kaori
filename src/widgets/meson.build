widget_sources = [
  '__init__.py',
  'window.py',
  'shortcuts.py',
  'setup.py',
]

install_data(widget_sources, install_dir: moduledir / 'widgets')

subdir('containers')
subdir('home')
subdir('browse')

subdir('preferences')
subdir('manga')
subdir('source')
subdir('extension')
subdir('chapter')
subdir('reader')
subdir('download')
subdir('updates')
subdir('history')
subdir('search')
subdir('library')
subdir('common')

blueprints += custom_target('widgets-blueprints',
  input: files(
    'setup.blp',
    'shortcuts.blp',
    'window.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
)
