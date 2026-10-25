"""Shows battle Events one line at a time with a typewriter effect, plays each line's sound when it starts, and only
updates the displayed numbers when the line that caused them is finished. Engine-free: the UI calls update(dt) every
frame, plays the returned sound names, and draws lines() and `snap`."""
from collections import deque

HOLD = {"act": 0.30, "result": 0.55, "note": 0.45}      # pause after a finished line, by kind
CURSOR = "_"


class BattlePresenter:
    def __init__(self, snap, lines=(), chars_per_second=70.0):
        self.snap = dict(snap)                  # the numbers currently on screen
        self.done = list(lines)                 # finished lines
        self.cps = chars_per_second
        self._queue = deque()
        self._typing = None                     # (event, characters shown so far)
        self._wait = 0.0

    def push(self, events):
        self._queue.extend(events)

    @property
    def busy(self):
        return bool(self._queue) or self._typing is not None or self._wait > 0

    def update(self, dt):
        """Advance time. Returns the sound names that start now."""
        sounds = []
        if self._typing is not None:
            ev, shown = self._typing
            shown += self.cps * dt
            if shown >= len(ev.text):
                self.done.append(ev.text)
                self.snap = dict(ev.snap)
                self._wait = HOLD.get(ev.kind, 0.4)
                self._typing = None
            else:
                self._typing = (ev, shown)
        elif self._wait > 0:
            self._wait -= dt
        elif self._queue:
            ev = self._queue.popleft()
            self._typing = (ev, 0.0)
            if ev.sound:
                sounds.append(ev.sound)
        return sounds

    def skip(self):
        """Show everything that is still pending at once (silently)."""
        if self._typing is not None:
            self._queue.appendleft(self._typing[0])
            self._typing = None
        while self._queue:
            ev = self._queue.popleft()
            self.done.append(ev.text)
            self.snap = dict(ev.snap)
        self._wait = 0.0

    def lines(self, last=14):
        out = list(self.done)
        if self._typing is not None:
            ev, shown = self._typing
            out.append(ev.text[:int(shown)] + CURSOR)
        return out[-last:]
