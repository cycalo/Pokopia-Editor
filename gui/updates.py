"""Background check for a newer GitHub release.

One unauthenticated GET to the public releases API each time the app starts, sending nothing about the user.
Failures (offline, rate limit, odd tag) are ignored.

The last result is remembered so the update button can appear before the request returns, and while offline.
That memory must not skip the request: a check can record "latest is v1.1.0", and v1.2.1 can be published
later the same day. Skipping for 24 hours after a check hid that release from anyone still on v1.2.0.
"""
import json, re, time
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from version import VERSION, VERSION_STR

REPO = 'cycalo/Pokopia-Editor'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES = f'https://github.com/{REPO}/releases/latest'


def parse(tag):
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', (tag or '').strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def newer(tag, current=None):
    v = parse(tag)
    if current is None:
        current = VERSION
    return bool(v) and v > tuple(current)


class UpdateChecker(QObject):
    """Emits found(tag, url) when the latest release is newer than this build.

    settings keys: check_updates (bool, default on), update_checked (unix time), update_latest (tag)."""
    found = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.net = None
        self._reply = None

    def start(self, force=False):
        # force is how the settings toggle asks for a check. Every start asks GitHub now.
        del force
        s = self.settings
        if not s.get('check_updates', True):
            return
        known = s.get('update_latest')
        if newer(known):
            self.found.emit(known, s.get('update_url') or RELEASES)
        self.net = self.net or QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(API))
        # Qt 6 does not follow redirects unless asked. GitHub answers a renamed repo with 301.
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setRawHeader(b'Accept', b'application/vnd.github+json')
        req.setRawHeader(b'User-Agent', f'PokopiaEditor/{VERSION_STR}'.encode())
        req.setTransferTimeout(10000)
        reply = self.net.get(req)
        # Keep a Python reference. A reply that only the signal holds can be collected before finished fires.
        self._reply = reply
        reply.finished.connect(lambda reply=reply: self._done(reply))

    def _done(self, reply):
        try:
            if not self.settings.get('check_updates', True):
                return
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
            if self._reply is reply:
                self._reply = None
            reply.deleteLater()
