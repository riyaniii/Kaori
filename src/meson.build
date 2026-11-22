pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'kaori'
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler', version: '>= 0.18.0')
src_dir = meson.current_source_dir()

python = import('python')
python3 = python.find_installation('python3')

conf = configuration_data()
conf.set('PYTHON', python3.full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'kaori.in',
  output: 'kaori',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

kaori_sources = [
  '__init__.py',
  'main.py',
  'actions.py',
  'constants.py',
  'server.py',
  'passwords.py',
  'tray.py'
]

install_data(kaori_sources, install_dir: moduledir)
install_data(
  'Suwayomi-Server-v2.4.2366.jar',
  install_dir: pkgdatadir,
  rename: 'Suwayomi-Server.jar',
)

subdir('integrations')
subdir('widgets')

blueprint_files = [
  'widgets/setup.blp',
  'widgets/shortcuts.blp',
  'widgets/window.blp',
  'widgets/main_view.blp',
  'widgets/donate.blp',
  'widgets/browse/page.blp',
  'widgets/chapter/panel.blp',
  'widgets/chapter/row.blp',
  'widgets/containers/manga_grid.blp',
  'widgets/containers/row.blp',
  'widgets/download/dialog.blp',
  'widgets/download/page.blp',
  'widgets/download/row.blp',
  'widgets/extension/card.blp',
  'widgets/extension/dialog.blp',
  'widgets/extension/extensions.blp',
  'widgets/history/page.blp',
  'widgets/history/row.blp',
  'widgets/home/page.blp',
  'widgets/library/page.blp',
  'widgets/library/category_panel.blp',
  'widgets/library/category_row.blp',
  'widgets/library/category_manager.blp',
  'widgets/library/category_edit.blp',
  'widgets/manga/card.blp',
  'widgets/manga/overview.blp',
  'widgets/manga/page.blp',
  'widgets/manga/tracking.blp',
  'widgets/preferences/extension_stores.blp',
  'widgets/preferences/preferences.blp',
  'widgets/preferences/tracking.blp',
  'widgets/reader/dialog.blp',
  'widgets/reader/guide.blp',
  'widgets/reader/double.blp',
  'widgets/reader/page.blp',
  'widgets/reader/single.blp',
  'widgets/reader/webtoon.blp',
  'widgets/search/page.blp',
  'widgets/source/card.blp',
  'widgets/source/filter.blp',
  'widgets/source/page.blp',
  'widgets/source/sources.blp',
  'widgets/updates/page.blp',
  'widgets/updates/row.blp',
]

blueprints = custom_target('blueprints',
  input: files(blueprint_files),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
  build_always_stale: true,
)

gnome.compile_resources('kaori',
  'kaori.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: [blueprints, appstream_file],
  source_dir: [meson.current_source_dir(), meson.project_build_root() / 'data'],
)