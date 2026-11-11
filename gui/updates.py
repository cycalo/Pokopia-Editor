"""Background check for a newer GitHub release.

One unauthenticated GET to the public releases API, at most once a day, sending nothing about the user.
Failures (offline, rate limit, odd tag) are ignored."""
import json, re, time
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from version import VERSION, VERSION_STR

REPO = 'cycalo/Pokopia-Save-Editor'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES = f'https://github.com/{REPO}/releases/latest'
INTERVAL = 24 * 3600


def parse(tag):
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', (tag or '').strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def newer(tag, current=VERSION):
    v = parse(tag)
    return bool(v) and v > tuple(current)


class UpdateChecker(QObject):
    """Emits found(tag, url) when the latest release is newer than this build.

    settings keys: check_updates (bool, default on), update_checked (unix time), update_latest (tag)."""
    found = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.net = None

    def start(self, force=False):
        s = self.settings
        if not s.get('check_updates', True):
            return
        known = s.get('update_latest')
        if newer(known):
            self.found.emit(known, s.get('update_url') or RELEASES)
        if not force and time.time() - s.get('update_checked', 0) < INTERVAL:
            return
        self.net = self.net or QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b'Accept', b'application/vnd.github+json')
        req.setRawHeader(b'User-Agent', f'PokopiaSaveEditor/{VERSION_STR}'.encode())
        req.setTransferTimeout(10000)
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._done(reply))

    def _done(self, reply):
        try:
            if reply.error() != reply.NetworkError.NoError:
                return
            d = json.loads(bytes(reply.readAll()).decode('utf-8'))
            tag, url = d.get('tag_name'), d.get('html_url') or RELEASES
            if d.get('draft') or d.get('prerelease') or not parse(tag):
                return
            self.settings.update(update_checked=int(time.time()), update_latest=tag, update_url=url)
            if newer(tag):
                self.found.emit(tag, url)
        except Exception:
            pass
        finally:
            reply.deleteLater()
