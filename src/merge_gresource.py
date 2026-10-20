import re
import sys
from pathlib import Path

top = Path(sys.argv[1])
out = Path(sys.argv[2])
base = top.parent

text = top.read_text()


def include(match):
    part = (base / match.group(1)).read_text()
    inner = re.search(r"<gresource>(.*)</gresource>", part, re.S).group(1)
    return inner.strip()


text = re.sub(r'<xi:include href="([^"]+)"[^>]*/>', include, text)
text = text.replace(' xmlns:xi="http://www.w3.org/2001/XInclude"', "")
out.write_text(text)
