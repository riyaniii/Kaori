NAME = "Kaori"
VERSION = ""

GUIDE_URL = "https://mihon.app/docs/guides/getting-started"
WELCOME_BODY = (
    "Kaori doesn't come with any sources. You need to install extensions "
    "to find and read manga.\n\n"
    "Kaori is compatible with Mihon sources, so the Mihon getting started "
    "guide is a good place to begin."
)

def set_version(version):
    global VERSION
    VERSION = version

def get_version():
    global VERSION
    return VERSION
