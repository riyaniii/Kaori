pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'kaghez'
gnome = import('gnome')

blueprints = files(
  'ui/window.blp',
  'ui/shortcuts.blp',
  'ui/setup.blp',
  'ui/preferences/preferences.blp',
  'ui/preferences/extension_stores.blp',

  'ui/pages/home.blp',
  'ui/pages/library.blp',
  'ui/pages/search.blp',
  'ui/pages/browse.blp',
  'ui/pages/sources.blp',
  'ui/pages/extensions.blp',

  'ui/manga/card.blp',
  'ui/manga/overview.blp',
  'ui/manga/page.blp',

  'ui/chapter/row.blp',
  'ui/chapter/panel.blp',

  'ui/source/card.blp',
  'ui/source/page.blp',
  'ui/source/filter.blp',

  'ui/extension/card.blp',
  'ui/extension/dialog.blp',

  'ui/download/row.blp',
  'ui/download/page.blp',
  'ui/download/dialog.blp',

  'ui/containers/manga_grid.blp',
  'ui/containers/row.blp',

  'ui/reader/page.blp',
  'ui/reader/dialog.blp',
  'ui/reader/single.blp',
  'ui/reader/double.blp',
  'ui/reader/webtoon.blp',
)

blueprints = custom_target('blueprints',
  input: blueprints,
  output: '.',
  command: [
    find_program('blueprint-compiler', version: '>= 0.18.0'),
    'batch-compile',
    '@OUTPUT@',
    '@CURRENT_SOURCE_DIR@',
    '@INPUT@'
  ],
)

gnome.compile_resources('kaghez',
  'kaghez.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
  source_dir: meson.current_source_dir(),
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'kaghez.in',
  output: 'kaghez',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

kaghez_sources = [
  '__init__.py',
  'main.py',
  'actions.py',
  'constants.py'
]

install_data(kaghez_sources, install_dir: moduledir)
install_data(
  'Suwayomi-Server-v2.4.2373.jar',
  install_dir: pkgdatadir,
  rename: 'Suwayomi-Server.jar',
)


subdir('integrations')
subdir('widgets')