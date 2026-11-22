import uuid
from urllib.parse import urlparse

from gettext import gettext as _

from .passwords import forget_password

LOCAL_URL = 'http://localhost:4567'


def profile_url(profile: dict) -> str:
    if profile['mode'] == 'local':
        return LOCAL_URL
    return profile['url']


def default_name(mode: str, url: str, username: str) -> str:
    if username:
        return username
    if mode == 'local':
        return _('This Computer')
    return urlparse(url).hostname or url


def describe(profile: dict) -> str:
    if profile['mode'] == 'local':
        return _('This computer')
    return urlparse(profile['url']).hostname or profile['url']


def load_profiles(settings) -> list:
    return [dict(profile) for profile in settings.get_value('profiles').unpack()]


def save_profiles(settings, profiles: list) -> None:
    from gi.repository import GLib
    settings.set_value('profiles', GLib.Variant('aa{ss}', profiles))


def find_profile(settings, profile_id: str) -> dict | None:
    for profile in load_profiles(settings):
        if profile['id'] == profile_id:
            return profile
    return None


def same_account(first: dict, second: dict) -> bool:
    return (first['mode'], first['url'], first['username']) == (second['mode'], second['url'], second['username'])


def remember_profile(settings, mode: str, url: str, username: str) -> dict:
    profile = {
        'id': uuid.uuid4().hex,
        'name': default_name(mode, url, username),
        'mode': mode,
        'url': '' if mode == 'local' else url,
        'username': username,
    }
    profiles = load_profiles(settings)
    for saved in profiles:
        if same_account(saved, profile):
            return saved
    for saved in profiles:
        same_server = (saved['mode'], saved['url']) == (profile['mode'], profile['url'])
        if same_server and not saved['username']:
            if saved['name'] == default_name(saved['mode'], saved['url'], ''):
                saved['name'] = profile['name']
            saved['username'] = username
            save_profiles(settings, profiles)
            return saved
    profiles.append(profile)
    save_profiles(settings, profiles)
    return profile


def remove_profile(settings, profile_id: str) -> None:
    profiles = load_profiles(settings)
    kept = []
    for profile in profiles:
        if profile['id'] == profile_id:
            if profile['username']:
                forget_password(profile_url(profile), profile['username'])
        else:
            kept.append(profile)
    save_profiles(settings, kept)
    if settings.get_string('last-profile') == profile_id:
        settings.set_string('last-profile', '')


def move_old_settings(settings) -> None:
    mode = settings.get_string('suwayomi-mode')
    if load_profiles(settings) or mode not in ('local', 'remote'):
        return
    profile = remember_profile(settings, mode, settings.get_string('suwayomi-url'),
                               settings.get_string('suwayomi-username'))
    settings.set_string('last-profile', profile['id'])
