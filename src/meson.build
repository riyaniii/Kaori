pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'kaori'
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler', version: '>= 0.18.0')
src_dir = meson.current_source_dir()
blueprints = []

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
  'tray.py'
]

install_data(kaori_sources, install_dir: moduledir)
install_data(
  'Suwayomi-Server-v2.4.2422.jar',
  install_dir: pkgdatadir,
  rename: 'Suwayomi-Server.jar',
)

subdir('integrations')
subdir('widgets')

gresource_parts = files(
  'widgets/widgets.gresource.part.xml',
  'widgets/preferences/preferences.gresource.part.xml',
  'widgets/home/home.gresource.part.xml',
  'widgets/browse/browse.gresource.part.xml',
  'widgets/source/source.gresource.part.xml',
  'widgets/extension/extension.gresource.part.xml',
  'widgets/library/library.gresource.part.xml',
  'widgets/search/search.gresource.part.xml',
  'widgets/history/history.gresource.part.xml',
  'widgets/updates/updates.gresource.part.xml',
  'widgets/manga/manga.gresource.part.xml',
  'widgets/chapter/chapter.gresource.part.xml',
  'widgets/download/download.gresource.part.xml',
  'widgets/containers/containers.gresource.part.xml',
  'widgets/reader/reader.gresource.part.xml',
)

merged_gresource = custom_target('kaori-gresource-xml',
  input: 'kaori.gresource.xml',
  output: 'kaori.merged.gresource.xml',
  command: [python3, files('merge_gresource.py'), '@INPUT@', '@OUTPUT@'],
  depend_files: gresource_parts,
)

gnome.compile_resources('kaori',
  merged_gresource,
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
  source_dir: meson.current_source_dir(),
)
