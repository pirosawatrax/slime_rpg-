"""Decides which background track plays and keeps it playing. Engine-free: the game gives it a `make_player(stem)` that
returns an object with start(), stop(), is_playing() and destroy().

  * a new tune every launch, and a new field tune and battle tune are prepared in a background thread each time one is used,
    so the next fight and the next stretch of exploring sound different;
  * a watchdog restarts the active track if the sound system lets it fall silent (checked every CHECK_EVERY seconds)."""
import threading
from pathlib import Path

from audio import music as M

CHECK_EVERY = 1.5


class MusicDirector:
    def __init__(self, directory, make_player, seed_fn=M.new_seed, threaded=True, log=print):
        self.directory = Path(directory)
        self.make_player = make_player
        self.seed_fn = seed_fn
        self.threaded = threaded
        self.log = log
        self.current = {}                 # track name -> (stem, player) in use
        self.ready = {}                   # track name -> (stem, player) prepared for the next time
        self.active = None                # 'field' | 'battle' | None
        self.restarts = 0                 # how many times the watchdog had to restart a silent track
        self._queue = []
        self._thread = None
        self._done = []                   # (name, stem or None) from the worker
        self._lock = threading.Lock()
        self._timer = 0.0

    # ---- start up -----------------------------------------------------
    def start(self):
        """Compose the first field and battle tunes now (about a second); later ones are made in the background."""
        for name in ("field", "battle"):
            stem = M.write_track(name, self.seed_fn(), self.directory)
            self.current[name] = (stem, self.make_player(stem))
        self._tidy()

    # ---- which track plays --------------------------------------------
    def set_track(self, name):
        """Switch to 'field' or 'battle' (each always starts from its beginning). Using a track retires it and queues a new
        tune of that kind, so next time it is different."""
        if name == self.active:
            return
        if self.active in self.current:
            self.current[self.active][1].stop()
        self.active = name
        if name in self.ready:                                   # a fresh tune is waiting: use it
            old = self.current.get(name)
            self.current[name] = self.ready.pop(name)
            if old is not None:
                old[1].stop()
                old[1].destroy()
        if name in self.current:
            self.current[name][1].start()
        self._queue.append(name)
        self._pump()
        self._tidy()

    # ---- every frame --------------------------------------------------
    def update(self, dt):
        self._collect()
        self._pump()
        self._timer += dt
        if self._timer >= CHECK_EVERY:
            self._timer = 0.0
            if self.active in self.current:
                player = self.current[self.active][1]
                if not player.is_playing():                       # fell silent: start it again
                    self.restarts += 1
                    self.log(f"music: '{self.active}' had stopped; restarting it ({self.restarts} so far)")
                    player.start()

    def wait(self):
        """Block until the background work is finished and its results are collected (tests, shutdown)."""
        while True:
            if self._thread is not None:
                self._thread.join()
            self._collect()
            self._pump()
            with self._lock:
                pending = bool(self._done)
            if self._thread is None and not self._queue and not pending:
                return

    # ---- background composing -----------------------------------------
    def _pump(self):
        if self._thread is not None or not self._queue:
            return
        name = self._queue.pop(0)
        seed = self.seed_fn()

        def job():
            try:
                stem = M.write_track(name, seed, self.directory)
            except Exception as exc:                              # a failed tune must never matter to the game
                self.log(f"music: could not make a new {name} tune: {exc}")
                stem = None
            with self._lock:
                self._done.append((name, stem))

        if self.threaded:
            self._thread = threading.Thread(target=job, daemon=True)
            self._thread.start()
        else:
            job()                                                 # (tests) do the work right here; update() collects it

    def _collect(self):
        with self._lock:
            done, self._done = self._done, []
        if not done:
            return
        for name, stem in done:
            self._thread = None
            if stem is None:
                continue
            if name in self.ready:                                # an older spare is replaced
                self.ready[name][1].destroy()
            self.ready[name] = (stem, self.make_player(stem))
        self._tidy()

    def _tidy(self):
        keep = {stem for stem, _ in list(self.current.values()) + list(self.ready.values())}
        with self._lock:
            unclaimed = bool(self._done)                          # finished but not yet picked up: its file is not "unused"
        if self._thread is None and not unclaimed:                # (nor may a file that is still being written be deleted)
            M.cleanup(self.directory, keep)
