import subprocess
import sys

SERVICE = 'io.github.riyaniii.Kaori'

if sys.platform == 'linux':
    import gi
    gi.require_version('Secret', '1')
    from gi.repository import Secret

    SCHEMA = Secret.Schema.new(
        SERVICE,
        Secret.SchemaFlags.NONE,
        {
            'url': Secret.SchemaAttributeType.STRING,
            'username': Secret.SchemaAttributeType.STRING,
        },
    )


def account_name(url: str, username: str) -> str:
    return f'{username}@{url}'


def save_password(url: str, username: str, password: str) -> None:
    try:
        if sys.platform == 'linux':
            Secret.password_store_sync(
                SCHEMA, {'url': url, 'username': username},
                Secret.COLLECTION_DEFAULT, f'Kaori login for {url}', password, None)
        elif sys.platform == 'darwin':
            subprocess.run(
                ['security', 'add-generic-password', '-U', '-s', SERVICE,
                 '-a', account_name(url, username), '-w', password],
                check=True, capture_output=True)
    except Exception as error:
        print(f'[kaori] saving the password failed: {error}')


def load_password(url: str, username: str) -> str:
    try:
        if sys.platform == 'linux':
            return Secret.password_lookup_sync(
                SCHEMA, {'url': url, 'username': username}, None) or ''
        if sys.platform == 'darwin':
            result = subprocess.run(
                ['security', 'find-generic-password', '-s', SERVICE,
                 '-a', account_name(url, username), '-w'],
                capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else ''
    except Exception as error:
        print(f'[kaori] loading the password failed: {error}')
    return ''


def forget_password(url: str, username: str) -> None:
    try:
        if sys.platform == 'linux':
            Secret.password_clear_sync(SCHEMA, {'url': url, 'username': username}, None)
        elif sys.platform == 'darwin':
            subprocess.run(
                ['security', 'delete-generic-password', '-s', SERVICE,
                 '-a', account_name(url, username)],
                capture_output=True)
    except Exception as error:
        print(f'[kaori] forgetting the password failed: {error}')
