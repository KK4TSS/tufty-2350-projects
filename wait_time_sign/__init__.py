# Copyright (c) 2026 Chris Parrish
# SPDX-License-Identifier: GPL-3.0-only
"""Showtime: a native Tufty park companion with cooperative refresh motion."""
import gc
import time
import sign_core as core

BG = (3, 16, 49)
INK = (245, 246, 248)
MUTED = (169, 189, 211)
GOLD = (255, 207, 91)
CYAN = (95, 232, 247)
AQUA = (86, 230, 211)
PANEL = (8, 29, 64)
SELECTED = (20, 54, 83)
GREEN = (127, 234, 187)
AMBER = (255, 197, 81)
CORAL = (255, 139, 144)
ART_RECT = (0, 26, 320, 64)
_serif = _sans = _art = _effects = None
_art_park = None
_title_window = None
BOARD_ROWS = 4

# BEGIN ARTWORK INDEX
ASSETS = {'park_6': (0, 40793, 320, 64), 'park_5': (40793, 36609, 320, 64), 'park_7': (77402, 42552, 320, 64), 'park_8': (119954, 41415, 320, 64), 'park_16': (161369, 36787, 320, 64), 'park_17': (198156, 41932, 320, 64), 'park_65': (240088, 44338, 320, 64), 'park_64': (284426, 38712, 320, 64), 'park_334': (323138, 37257, 320, 64), 'park_67': (360395, 40818, 320, 64), 'park_66': (401213, 49866, 320, 64), 'park_21': (451079, 48053, 320, 64), 'spark_gold': (499132, 568, 24, 12), 'spark_cyan': (499700, 435, 24, 12)}
# END ARTWORK INDEX


def asset(name):
    offset, length, width, height = ASSETS[name]
    with open('art.bin', 'rb') as artwork:
        artwork.seek(offset)
        data = artwork.read(length)
    if len(data) != length:
        raise ValueError('Incomplete art.bin')
    sprite = image.load(data)
    if (sprite.width, sprite.height) != (width, height):
        raise ValueError('Artwork size mismatch')
    return sprite


def release():
    global _serif, _sans, _art, _effects, _art_park, _title_window
    _serif = _sans = _art = _effects = _art_park = None
    _title_window = None
    gc.collect()


def is_disney(park):
    return core.PARKS[park][2] in ('Walt Disney World', 'Disneyland Resort')


def accent(park):
    if is_disney(park):
        return GOLD
    return AQUA if core.PARKS[park][2] == 'SeaWorld' else CYAN


def fonts():
    global _serif, _sans
    if _serif is None:
        _sans = font.load('/system/assets/fonts/MonaSans-Medium.af')
        _serif = font.load('./display.af')
    screen.antialias = image.X4


def set_font(serif=False):
    fonts()
    screen.font = _serif if serif else _sans


def width(label, size=12, serif=False):
    set_font(serif)
    return screen.measure_text(core.clean(label), size)[0]


def fit(label, size, maximum, serif=False):
    label = core.clean(label)
    if width(label, size, serif) <= maximum:
        return label
    while label and width(label + '...', size, serif) > maximum:
        label = label[:-1]
    return label + '...' if label else ''


def text(label, x, y, size=12, maximum=296, foreground=INK, serif=False, center=None):
    label = fit(label, size, maximum, serif)
    set_font(serif)
    screen.pen = color.rgb(*foreground)
    if center is not None:
        x = center - screen.measure_text(label, size)[0] / 2
    screen.text(label, x, y, size)


def wrapped(label, size, maximum, serif=False):
    words = core.clean(label).split()
    result, line = [], ''
    for word in words:
        trial = (line + ' ' + word).strip()
        if line and width(trial, size, serif) > maximum:
            result.append(line)
            line = word
        else:
            line = trial
    if line:
        result.append(line)
    return result


def lines(label, x, y, size=14, maximum=296, count=2, foreground=INK, serif=False, center=None):
    rows = wrapped(label, size, maximum, serif)
    for i, row in enumerate(rows[:count]):
        if i == count-1 and len(rows) > count:
            row = row.rstrip()
            while row and width(row+'...', size, serif) > maximum:
                row = row[:-1]
            row = row.rstrip()+ '...'
        text(row, x, y+i*(size+3), size, maximum, foreground, serif, center)


def rectangle(x, y, w, h, rgb):
    screen.pen = color.rgb(*rgb)
    screen.rectangle(x, y, w, h)


def background(park, show_art=True):
    global _art, _art_park
    screen.alpha = 255
    screen.pen = color.rgb(*BG)
    screen.clear()
    if not show_art:
        return
    if _art_park != park:
        _art = None
        gc.collect()
        _art = asset('park_%s' % core.PARKS[park][0])
        if (_art.width, _art.height) != (320, 64):
            raise ValueError('Showtime panorama must be 320x64')
        _art_park = park
    screen.blit(_art, rect(*ART_RECT))


def has_scene(model):
    return model.mode in ('sign', 'parks') or not model.rows



def wait_style(ride):
    if not ride['open']:
        return MUTED, 'REPORTED CLOSED'
    wait = ride['wait']
    if wait is None:
        return MUTED, 'WAIT UNAVAILABLE'
    if wait <= 20:
        return GREEN, 'SHORT WAIT'
    if wait <= 45:
        return AMBER, 'MODERATE WAIT'
    return CORAL, 'LONG WAIT'


def draw_battery(battery):
    rectangle(236, 228, 74, 12, BG)
    label, state = battery.display()
    foreground = CORAL if state == 'low' else CYAN if state == 'usb' else MUTED
    rectangle(240, 231, 15, 8, foreground)
    rectangle(241, 232, 13, 6, BG)
    rectangle(255, 233, 2, 4, foreground)
    if state == 'usb':
        rectangle(242, 233, 11, 4, foreground)
    elif battery.level is not None:
        filled = max(1, int(11*battery.level/100))
        rectangle(242, 233, filled, 4, foreground)
    text(label, 263, 229, 9, 45, foreground)


def frame(model):
    park = model.candidate if model.mode == 'parks' else model.park
    theme = accent(park)
    background(park, has_scene(model))
    title = 'CHOOSE YOUR PARK' if model.mode == 'parks' else core.PARKS[park][1].upper()
    text(title, 12, 3, 14, 296, theme, True)
    if model.mode == 'parks':
        labels = ('A Back', 'B Resort', 'C Choose')
    else:
        action = 'Open'
        if model.mode == 'sign':
            saved = model.selected() and core.key(core.PARKS[model.park][0], model.selected()) in model.prefs['favorites']
            action = 'Unsave' if saved else 'Save'
        labels = ('A Parks', 'B Views', 'C '+action)
    rectangle(0, 206, 320, 1, theme)
    for label, x in zip(labels, (12, 118, 226)):
        key, action = label.split(' ', 1)
        rectangle(x, 209, 15, 16, theme)
        rectangle(x+1, 210, 13, 14, BG)
        text(key, x+2, 210, 12, 12, INK, center=x+7.5)
        text(action, x+21, 209, 13, 75, INK)
    text('Powered by Queue-Times.com', 10, 229, 9, 220, MUTED, center=122)
    draw_battery(model.battery)


def draw_change(change, x, y, maximum=26, size=9, right=None):
    if not change:
        return
    label = str(abs(change))
    while size > 7 and width(label, size)+8 > maximum:
        size -= 1
    if right is not None:
        x = right-width(label,size)-8
    foreground = GREEN if change < 0 else CORAL
    # Native primitives keep arrows visible with the app's ASCII-only text path.
    tip = y+8 if change < 0 else y+2
    direction = -1 if change < 0 else 1
    rectangle(x+2,y+2,1,7,foreground)
    rectangle(x+1,tip+direction,1,1,foreground)
    rectangle(x+3,tip+direction,1,1,foreground)
    rectangle(x,tip+2*direction,1,1,foreground)
    rectangle(x+4,tip+2*direction,1,1,foreground)
    text(label,x+8,y,size,maximum-8,foreground)


def board_row(ride, y, selected, theme=GOLD, park_id=None, change=None):
    rectangle(10, y, 300, 31, SELECTED if selected else PANEL)
    if selected:
        rectangle(10, y, 3, 31, theme)
    lines(ride['name'], 19, y+1, 12, 200, 2)
    value = core.wait_label(ride)
    foreground, _ = wait_style(ride)
    size = 11 if value == 'CLOSED' else 20
    seasonal = core.is_seasonal(park_id, ride)
    if seasonal:
        text('SEASONAL', 302-width('SEASONAL', 9), y, 9, 64, MUTED)
    value_y = y+(18 if value == 'CLOSED' else 10) if seasonal else y+6
    text(value, 302-width(value, size), value_y, size, 64, foreground)
    if ride['open'] and ride['wait'] is not None:
        draw_change(change, 232, y+18, 24)


def draw_status(model):
    if model.busy:
        # The right-hand strip is reserved for activity, not a progress estimate.
        label = model.message or 'Updating waits...'
        if not model.message and model.offline and model.data:
            label = 'Updating / SAVED '+model.data['checked'][11:16]
        text(label, 12, 191, 11, 149, MUTED)
    else:
        label = model.status()
        if label == 'Hold B: Refresh / UP/DOWN: Ride':
            label = 'Ready to explore'
        text(label, 12, 191, 11, 296, MUTED)


def draw(model):
    frame(model)
    if model.mode == 'parks':
        park = core.PARKS[model.candidate]
        lines(park[1], 12, 98, 22, 190, 3, INK, True)
        text('%s / %s' % (model.candidate+1, len(core.PARKS)), 212, 119, 22, 96, accent(model.candidate))
        text(park[2], 12, 176, 11, 296, MUTED)
    elif not model.rows:
        if model.mode == 'favorites' and model.data:
            heading, detail = 'Your favorites await', 'Open a ride and press C to save it.'
        elif model.offline:
            heading, detail = 'Waits unavailable', 'Saved waits stay here. Hold B to retry.'
        else:
            heading, detail = 'Welcome to the park', 'Waits refresh in the background.'
        lines(heading, 12, 98, 22, 296, 2, INK, True)
        lines(detail, 12, 154, 12, 296, 2, MUTED)
    elif model.mode in ('board', 'favorites'):
        text('YOUR FAVORITES' if model.mode == 'favorites' else 'ATTRACTION WAITS', 12, 31, 11, 224, accent(model.park))
        text('%s / %s' % (model.index+1, len(model.rows)), 243, 31, 10, 66, MUTED)
        rectangle(10, 47, 300, 132, PANEL)
        start = (model.index//BOARD_ROWS)*BOARD_ROWS
        for slot, ride in enumerate(model.rows[start:start+BOARD_ROWS]):
            board_row(ride, 49+slot*32, start+slot == model.index, accent(model.park), core.PARKS[model.park][0], model.changes.get(ride['id']))
    else:
        ride = model.selected()
        # This entire column is below the panorama. Even a maximum-length name
        # receives three fixed lines and a single ellipsis, never scenery.
        lines(ride['name'], 12, 98, 22, 180, 3, INK, True)
        value = core.wait_label(ride)
        foreground, description = wait_style(ride)
        if value == 'CLOSED':
            text('CLOSED', 212, 119, 16, 96, foreground)
        else:
            size = 74
            while width(value, size, True) > 96:
                size -= 2
            text(value, 308-width(value, size, True), 98, size, 96, foreground, True)
            if value != '--':
                change = model.changes.get(ride['id'])
                text('MIN', 212, 172, 14, 96, INK, center=238 if change else 260)
                draw_change(change, 274, 176, 34, 10, right=308)
        seasonal = core.is_seasonal(core.PARKS[model.park][0], ride)
        text(('SEASONAL / ' if seasonal else '')+description, 12, 176,
             9 if seasonal else 11, 190, foreground)
    draw_status(model)


def paint_motion(model, phase, success=False, quiet=False):
    """Redraw only the scene and reserved activity strip; never layout live text."""
    global _effects
    park = model.candidate if model.mode == 'parks' else model.park
    scene = has_scene(model)
    scene_effect = scene and (model.mode != 'parks' or model.candidate == model.park)
    if scene and _art is not None and _art_park == park:
        screen.blit(_art, rect(*ART_RECT))
    if model.busy:
        rectangle(169, 190, 139, 14, BG)
    if quiet:
        return
    if _effects is None:
        _effects = (asset('spark_gold'), asset('spark_cyan'))
    disney = is_disney(park)
    effect = _effects[0 if disney else 1]
    # Phase is elapsed time, so a delayed TLS computation skips ahead instead
    # of replaying old frames. Native blit handles the tiny alpha sprite.
    pulse = 80 + int(175 * (1-abs(phase*2-1)))
    try:
        if model.busy and not scene_effect:
            screen.alpha = pulse
            x = 171 + int(111*phase)
            screen.blit(effect, rect(x, 191, 24, 12))
        if scene_effect:
            screen.alpha = pulse if success else min(210, pulse)
            x = 12 + int(272*phase)
            y = 34 + int(17*phase) if disney else 63-int(22*phase)
            screen.blit(effect, rect(x, y, 24, 12))
    finally:
        screen.alpha = 255


def paint_title(label, offset):
    """An actual framebuffer window clips text away from the wait column."""
    global _title_window
    if _title_window is None:
        _title_window = screen.window(12, 148, 180, 26)
    fonts()
    _title_window.alpha = 255
    _title_window.pen = color.rgb(*BG)
    _title_window.clear()
    _title_window.font = _serif
    _title_window.antialias = image.X4
    _title_window.pen = color.rgb(*INK)
    _title_window.text(label, -offset, 0, 22)


class TitleScroll:
    """Only overflowing third lines move; layout is cached per selected ride."""
    def __init__(self):
        self.key = None
        self.label = None
        self.elapsed = 0
        self.tick = None
        self.painted = None
        self.force = False
        self.last_paint = None

    def invalidate(self):
        self.force = True

    def step(self, model, now, dimmed=False):
        ride = model.selected() if model.mode == 'sign' else None
        if ride is None:
            self.key = self.label = None
            self.tick = now
            return False
        key = (model.park, ride['id'], ride['name'])
        if key != self.key:
            self.key = key
            rows = wrapped(ride['name'], 22, 180, True)
            tail = ' '.join(rows[2:])
            distance = max(0, int(width(tail, 22, True)+.999)-180) if tail else 0
            self.label = tail if distance else None
            self.distance = distance
            self.travel_ms = (distance*1000+23)//24
            self.elapsed, self.tick, self.painted = 0, now, None
            self.last_paint = None
            self.force = True
        delta = max(0, time.ticks_diff(now, self.tick))
        self.tick = now
        if self.label is None or dimmed:
            return False
        self.elapsed = (self.elapsed+delta) % (4000+self.travel_ms)
        offset = min(self.distance, max(0, (self.elapsed-2000)*24//1000))
        if not self.force and offset == self.painted:
            return False
        if not self.force and self.last_paint is not None and time.ticks_diff(now, self.last_paint) < 100:
            return False
        paint_title(self.label, offset)
        self.painted, self.force = offset, False
        self.last_paint = now
        return True


class Motion:
    """One bounded clock shared with UI/network work; no nested animation loop."""
    def __init__(self):
        self.last = None
        self.epoch = None
        self.phase_ms = 0
        self.finished = None
        self.visible = False
        self.force = True

    def invalidate(self):
        self.force = True

    def finish(self, now, success):
        self.finished = now if success else None
        self.force = True

    def step(self, model, now, dimmed=False):
        if self.epoch is None:
            self.epoch = now
        # Measure between loop iterations so the origin never ages past the
        # ticks_diff half-period. 24000 is divisible by both motion periods.
        self.phase_ms = (self.phase_ms + max(0, time.ticks_diff(now, self.epoch))) % 24000
        self.epoch = now
        elapsed = self.phase_ms
        completed = None if self.finished is None else time.ticks_diff(now, self.finished)
        success = completed is not None and 0 <= completed < 700
        if completed is not None and not success:
            self.finished = None
        # Occasional, brief idle sparkle; work at10fps only during refresh.
        idle = not model.busy and not success and elapsed % 12000 < 650 and has_scene(model)
        active = not dimmed and (model.busy or success or idle)
        if not active:
            if self.visible:
                paint_motion(model, 0, quiet=True)
                self.visible = False
                self.force = False
                return True
            return False
        cadence = 100 if model.busy or success else 200
        if not self.force and self.last is not None and time.ticks_diff(now, self.last) < cadence:
            return False
        phase = (completed/700 if success else elapsed % (1600 if model.busy else 12000)/(1600 if model.busy else 650))
        paint_motion(model, min(1, max(0, phase)), success)
        self.last = now
        self.visible = True
        self.force = False
        return True


_refresh = None
_previous_clear = None


def on_exit():
    global _refresh
    if _refresh is not None:
        _refresh.close()
        _refresh = None
    screen.alpha = 255
    badge.caselights(0)
    badge.default_clear = _previous_clear
    display.backlight(.7)
    release()


def main():
    import secrets as wifi
    import sign_net as net
    global _refresh, _previous_clear
    _previous_clear = badge.default_clear
    badge.mode(HIRES | VSYNC)
    badge.default_clear = None
    screen.alpha = 255
    badge.caselights(0)
    display.backlight(.7)
    model = core.Model()
    dirty, pending = True, True
    last_input = time.ticks_ms()
    # Attempt times belong to each park, so switching cannot bypass cooldowns.
    attempts = {}
    controls = core.Controls()
    motion = Motion()
    title_scroll = TitleScroll()
    read_battery = getattr(badge, 'battery_level', lambda: None)
    dimmed = False
    keys = ((BUTTON_A, 'A'), (BUTTON_B, 'B'), (BUTTON_C, 'C'),
            (BUTTON_UP, 'UP'), (BUTTON_DOWN, 'DOWN'))

    try:
        while True:
            badge.poll()
            tick = time.ticks_ms()
            battery_dirty = model.battery.update(tick, read_battery, badge.usb_connected())
            woke = False
            if badge.pressed():
                last_input = tick
                if dimmed:
                    display.backlight(.7)
                    dimmed = False
                    # Consume the first key when waking the dimmed screen.
                    woke = True
            if woke:
                controls.reset()
                command = None
            else:
                command = controls.event(tick,
                    [name for key, name in keys if badge.pressed(key)],
                    [name for key, name in keys if badge.held(key)],
                    [name for key, name in keys if badge.released(key)])
            action = model.event(command) if command is not None else None
            if command is not None:
                dirty = True
            park_id = core.PARKS[model.park][0]
            if action == 'park':
                if _refresh is not None:
                    _refresh.close()
                    _refresh = None
                model.busy = False
                pending = True
            last_attempt = attempts.get(park_id)
            due = last_attempt is not None and time.ticks_diff(tick, last_attempt) >= 300000
            ready = last_attempt is None or time.ticks_diff(tick, last_attempt) >= 60000
            if _refresh is None and model.mode != 'parks' and ((pending and ready) or due or action == 'refresh'):
                if not ready:
                    if action == 'refresh':
                        model.message = 'Wait 60s between updates'
                else:
                    pending = False
                    attempts[park_id] = tick
                    if model.message not in core.SAVE_ERRORS:
                        model.message = ''
                    _refresh = net.Refresh(park_id, getattr(wifi, 'WIFI_SSID', ''),
                                           getattr(wifi, 'WIFI_PASSWORD', ''), rtc)
                    model.busy = True
                dirty = True
            # Draw navigation before advancing the cooperative network job. No
            # job owns the display, input polling, favorites or model snapshots.
            if dirty:
                draw(model)
                title_scroll.invalidate()
                title_scroll.step(model, time.ticks_ms(), dimmed)
                display.update()
                dirty = False
                battery_dirty = False
                motion.invalidate()
            if _refresh is not None:
                job = _refresh
                job.step()
                if job.done:
                    _refresh = None
                    model.busy = False
                    if job.park_id == core.PARKS[model.park][0]:
                        if job.error:
                            model.failed(job.error)
                        else:
                            model.accept(job.rides, job.checked)
                    job.close()
                    motion.finish(time.ticks_ms(), not job.error)
                    dirty = True
            should_dim = not model.battery.usb and time.ticks_diff(time.ticks_ms(), last_input) >= 30000
            if should_dim != dimmed:
                display.backlight(.12 if should_dim else .7)
                dimmed = should_dim
            if not dirty:
                if battery_dirty:
                    draw_battery(model.battery)
                moving = motion.step(model, time.ticks_ms(), dimmed)
                scrolling = title_scroll.step(model, time.ticks_ms(), dimmed)
                if battery_dirty or moving or scrolling:
                    display.update()
            time.sleep_ms(50)
    finally:
        on_exit()


try:
    badge
except NameError:
    pass
else:
    main()
