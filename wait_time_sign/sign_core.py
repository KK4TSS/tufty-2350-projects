"""Park catalog, validated snapshots, preferences and shared navigation."""
import json
import os
import time

PARKS = (
    (6, 'Magic Kingdom', 'Walt Disney World'),
    (5, 'EPCOT', 'Walt Disney World'),
    (7, 'Hollywood Studios', 'Walt Disney World'),
    (8, 'Animal Kingdom', 'Walt Disney World'),
    (16, 'Disneyland', 'Disneyland Resort'),
    (17, 'California Adventure', 'Disneyland Resort'),
    (65, 'Universal Studios', 'Universal Orlando'),
    (64, 'Islands of Adventure', 'Universal Orlando'),
    (334, 'Epic Universe', 'Universal Orlando'),
    (67, 'Volcano Bay', 'Universal Orlando'),
    # Append new parks: stored preferences refer to the original list indices.
    (66, 'Universal Studios Hollywood', 'Universal Hollywood'),
    (21, 'SeaWorld Orlando', 'SeaWorld'),
)
STATE = '/state/wait_time_sign'
SAVE_ERRORS = ('Park not saved', 'Favorite not saved')

# Verified seasonal ride versions. Names guard against a provider reusing an
# ID for its regular version (notably Disneyland's Haunted Mansion).
SEASONAL_VERSIONS = {
    (6, 17950): 'jinglecruise',
    (5, 17914): 'livingwiththelandglimmeringgreenhouses',
    (16, 325): 'hauntedmansionholiday',
    (17, 2608): 'luigishonkinhauloween',
    (17, 4723): 'matersgraveyardjambooree',
    (17, 5146): 'guardiansofthegalaxymonstersafterdark',
}


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, value):
    try:
        try:
            os.mkdir('/state')
        except OSError:
            pass
        try:
            os.mkdir(STATE)
        except OSError:
            pass
        with open(path + '.tmp', 'w') as f:
            json.dump(value, f)
        os.rename(path + '.tmp', path)
        return True
    except OSError:
        return False


def preferences():
    result = read_json(STATE + '/preferences.json', {})
    if not isinstance(result, dict):
        result = {}
    park = result.get('park', 0)
    result['park'] = park if type(park) is int and 0 <= park < len(PARKS) else 0
    favorites = result.get('favorites', [])
    result['favorites'] = [x for x in favorites if isinstance(x, str)][:200] if isinstance(favorites, list) else []
    return result


def clean(text):
    text = str(text).replace('\u2019', "'").replace('\u2013', '-').replace('\u2014', '-')
    return ''.join(c if 32 <= ord(c) <= 126 else ' ' for c in text)


def is_seasonal(park_id, ride):
    expected = SEASONAL_VERSIONS.get((park_id, ride.get('id')))
    if expected is None:
        return False
    # Match the whole name, ignoring typography/punctuation, not holiday words.
    name = ''.join(c for c in clean(ride.get('name', '')).lower() if 'a' <= c <= 'z' or '0' <= c <= '9')
    return name == expected


def parse(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('lands'), list) or not isinstance(payload.get('rides', []), list):
        raise ValueError('Invalid park response')
    groups = [payload.get('rides', [])]
    for land in payload['lands']:
        if not isinstance(land, dict) or not isinstance(land.get('rides'), list):
            raise ValueError('Invalid land response')
        groups.append(land['rides'])
    rides, seen = [], set()
    for group in groups:
        for row in group:
            if not isinstance(row, dict):
                continue
            ident, wait, opened = row.get('id'), row.get('wait_time'), row.get('is_open')
            name, updated = row.get('name'), row.get('last_updated')
            if type(ident) is not int or ident in seen or not isinstance(name, str) or type(opened) is not bool:
                continue
            # Unknown waits must never look like a zero-minute queue.
            if type(wait) is not int or not 0 <= wait <= 600:
                wait = None
            if not isinstance(updated, str) or len(updated) < 19:
                updated = ''
            seen.add(ident)
            rides.append({'id': ident, 'name': clean(name)[:180], 'open': opened,
                          'wait': wait, 'updated': updated[:19]})
    if not rides:
        raise ValueError('No valid rides in feed')
    rides.sort(key=lambda r: r['name'].lower())
    return rides


def key(park_id, ride):
    return '%s:%s' % (park_id, ride['id'])


def visible(rides, park_id, favorites, only_favorites=False):
    rows = [r for r in rides if not only_favorites or key(park_id, r) in favorites]
    rows.sort(key=lambda r: (key(park_id, r) not in favorites, r['name'].lower()))
    return rows


def wait_label(ride):
    if not ride['open']:
        return 'CLOSED'
    return str(ride['wait']) if ride['wait'] is not None else '--'


def wait_changes(previous, current):
    """Observed minute differences for the same open ride, never predictions."""
    before = {ride['id']:ride for ride in previous}
    changes = {}
    for ride in current:
        old = before.get(ride['id'])
        if not old or old['name'] != ride['name'] or not old['open'] or not ride['open']:
            continue
        first, last = old.get('wait'), ride.get('wait')
        if type(first) is not int or type(last) is not int or not (0 <= first <= 600 and 0 <= last <= 600):
            continue
        # Repeated or regressing provider timestamps cannot establish a change.
        if old.get('updated') and ride.get('updated') and ride['updated'] <= old['updated']:
            continue
        if last != first:
            changes[ride['id']] = last-first
    return changes


def stamp():
    return '%04d-%02d-%02dT%02d:%02d:%02d' % time.gmtime()[:6]


def snapshot(park_id):
    data = read_json(STATE + '/park_%s.json' % park_id, None)
    if not isinstance(data, dict) or data.get('park') != park_id or not isinstance(data.get('rides'), list):
        return None
    if not isinstance(data.get('checked'), str) or len(data['checked']) != 19:
        return None
    if not data['rides']:
        return None
    for ride in data['rides']:
        if (not isinstance(ride, dict) or type(ride.get('id')) is not int
                or not isinstance(ride.get('name'), str) or type(ride.get('open')) is not bool
                or not isinstance(ride.get('updated'), str) or 'wait' not in ride
                or (ride.get('wait') is not None and (type(ride['wait']) is not int or not 0 <= ride['wait'] <= 600))):
            return None
    return data


class Battery:
    """Approximate voltage-derived charge; no inferred charging/full state."""
    def __init__(self):
        self.level = None
        self.usb = None
        self.low = False
        self.sampled = None
        self.samples = []

    def display(self):
        if self.usb:
            return 'USB', 'usb'
        if self.level is None:
            return '--%', 'unknown'
        return ('LOW %s%%' if self.low else '~%s%%') % self.level, 'low' if self.low else 'battery'

    def update(self, now, read_level, usb):
        before = self.display()
        changed_power = self.usb != bool(usb)
        self.usb = bool(usb)
        if changed_power:
            self.samples = []
            self.level = None
            self.low = False
            self.sampled = None
        if not self.usb and (self.sampled is None or time.ticks_diff(now, self.sampled) >= 30000):
            self.sampled = now
            try:
                level = read_level()
            except (OSError, ValueError, TypeError):
                level = None
            if type(level) in (int, float) and 0 <= level <= 100:
                self.samples.append(level)
                self.samples = self.samples[-3:]
                values = sorted(self.samples)
                # A three-reading median reduces brief radio/load fluctuations.
                value = values[len(values)//2]
                self.level = int((value+2.5)//5)*5
                if value <= 15:
                    self.low = True
                elif value >= 20:
                    self.low = False
            else:
                self.level = None
                self.low = False
                self.samples = []
        return before != self.display()


class Model:
    """Four views and shared states; rebuild ride ordering only on changes."""
    VIEWS = ('sign', 'board', 'favorites')

    def __init__(self):
        self.prefs = preferences()
        self.park = self.prefs['park']
        self.candidate = self.park
        self.mode = 'sign'
        self.return_mode = 'sign'
        self.index = 0
        self.data = snapshot(PARKS[self.park][0])
        self.offline = bool(self.data)
        self.busy = False
        self.message = ''
        self.battery = Battery()
        self.changes = {}
        self.rows = []
        self.rebuild()

    def rebuild(self, selected=None):
        self.rows = visible((self.data or {}).get('rides', []), PARKS[self.park][0],
                            self.prefs['favorites'],
                            (self.return_mode if self.mode == 'parks' else self.mode) == 'favorites')
        if selected is not None:
            for i, ride in enumerate(self.rows):
                if ride['id'] == selected:
                    self.index = i
                    break
        self.index %= max(1, len(self.rows))

    def selected(self):
        return self.rows[self.index] if self.rows else None

    def event(self, button):
        if self.mode == 'parks':
            if button in ('UP', 'DOWN'):
                self.candidate = (self.candidate + (-1 if button == 'UP' else 1)) % len(PARKS)
            elif button == 'B':
                group = PARKS[self.candidate][2]
                while PARKS[self.candidate][2] == group:
                    self.candidate = (self.candidate + 1) % len(PARKS)
            elif button == 'A':
                self.mode = self.return_mode
            elif button == 'C':
                changed = self.park != self.candidate
                self.park = self.candidate
                self.mode = self.return_mode
                if changed:
                    self.changes = {}
                    self.prefs['park'] = self.park
                    self.message = '' if write_json(STATE + '/preferences.json', self.prefs) else 'Park not saved'
                    self.data = snapshot(PARKS[self.park][0])
                    self.offline = bool(self.data)
                    self.index = 0
                    self.rebuild()
                    return 'park'
            return None
        selected = self.selected()
        ident = selected['id'] if selected else None
        self.message = ''
        if button == 'A':
            self.return_mode, self.mode, self.candidate = self.mode, 'parks', self.park
        elif button == 'B':
            self.mode = self.VIEWS[(self.VIEWS.index(self.mode) + 1) % len(self.VIEWS)]
            self.index = 0
            self.rebuild(ident)
        elif button in ('UP', 'DOWN') and self.rows:
            self.index = (self.index + (-1 if button == 'UP' else 1)) % len(self.rows)
        elif button == 'REFRESH':
            return 'refresh'
        elif button == 'C':
            if self.mode != 'sign':
                self.mode = 'sign'
                self.rebuild(ident)
            elif selected:
                favorite = key(PARKS[self.park][0], selected)
                saved = self.prefs['favorites']
                if favorite in saved:
                    saved.remove(favorite)
                    self.message = 'Favorite removed'
                elif len(saved) < 200:
                    saved.append(favorite)
                    self.message = 'Favorite saved'
                else:
                    self.message = 'Favorites full (200)'
                    return None
                if not write_json(STATE + '/preferences.json', self.prefs):
                    self.message = 'Favorite not saved'
                self.rebuild(ident)
        return None

    def accept(self, rides, checked):
        selected = self.selected()
        previous = self.data or {}
        self.changes = (wait_changes(previous.get('rides', []), rides)
                        if not self.offline and previous.get('park') == PARKS[self.park][0] else {})
        self.data = {'park': PARKS[self.park][0], 'checked': checked, 'rides': rides}
        self.offline = False
        saved = write_json(STATE + '/park_%s.json' % self.data['park'], self.data)
        if self.message not in SAVE_ERRORS:
            self.message = '' if saved else 'Updated / not saved'
        self.rebuild(selected['id'] if selected else None)

    def failed(self, message):
        self.offline = True
        self.changes = {}
        self.message = message

    def status(self):
        if self.busy:
            if self.message:
                return self.message + ' / Refreshing...'
            checked = (self.data or {}).get('checked', '')
            if checked:
                return ('SAVED ' if self.offline else 'Fetched ') + checked[11:16] + ' UTC / Refreshing...'
            return 'Refreshing...'
        if self.message:
            if self.offline and self.data:
                detail = 'Hold B: Retry' if self.message.startswith('Update failed') else self.message
                return 'SAVED ' + self.data.get('checked', '')[11:16] + ' UTC / ' + detail
            return self.message
        checked = (self.data or {}).get('checked', '')
        if checked:
            return ('SAVED ' if self.offline else 'Fetched ') + checked[11:16] + ' UTC'
        return 'Hold B: Refresh / UP/DOWN: Ride'


class Controls:
    """B tap changes view; B hold refreshes once and consumes the tap."""
    HOLD_MS = 700

    def __init__(self):
        self.reset()

    def reset(self):
        self.started = None
        self.long_press = False

    def event(self, now, pressed, held, released):
        if 'B' in pressed:
            self.started, self.long_press = now, False
        if self.started is not None:
            if (('B' in held or 'B' in released) and not self.long_press
                    and time.ticks_diff(now, self.started) >= self.HOLD_MS):
                self.long_press = True
                if 'B' in released:
                    self.started = None
                return 'REFRESH'
            if 'B' in released:
                short = not self.long_press
                self.started = None
                if short:
                    return 'B'
        for button in ('A', 'C', 'UP', 'DOWN'):
            if button in pressed:
                return button
        return None
