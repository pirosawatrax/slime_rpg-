"""The village commands as a small state machine (engine-free). The UI shows `session.screen()` and calls
`session.choose(i)` when the player picks option i. Everything a village does lives here: inn (heal + respawn point),
storage, trade, guide, request and the post-boss services."""
from dataclasses import dataclass, field

import config as C
import items
import strings as T
from game import daytime, village_data as data
from game.inventory import Inventory
from world import boss_arena, villages

PAGE = 8                     # list entries per page (plus "More..." and "Back" = at most 10 options)


@dataclass
class Flags:
    boss_defeated: bool = False
    boss_known: bool = False          # the guide has told you where the Slime King lives


class VillageState:
    """What changes in one village: its storage and the things you have done there."""

    def __init__(self, extra_slots=0):
        self.storage = Inventory(C.STORAGE_SLOTS + extra_slots)
        self.request_done = False
        self.expanded = False
        self.tonic = False


class VillageBook:
    def __init__(self):
        self.states = {}

    def get(self, village_id):
        if village_id not in self.states:
            self.states[village_id] = VillageState()
        return self.states[village_id]


class Context:
    """Everything a village needs from the running game."""

    def __init__(self, seed, inventory, stats, flags, book, name_of, respawn=None, world_time=0.0):
        self.seed, self.inventory, self.stats, self.flags, self.book, self.name_of = seed, inventory, stats, flags, book, name_of
        self.respawn = respawn            # (x, y, z) of the last inn you slept at, or None
        self.world_time = world_time      # seconds; the inn moves it to the morning (the caller copies it back)


@dataclass
class Screen:
    title: str
    lines: list
    options: list                          # labels, in order; the player picks by position
    note: str = ""


def _fee_slot(inv, exclude=None, need=1):
    """Which stack pays a fee: the plainest mineral you carry (common colours first, then uncommon, then rare; smaller
    stacks first). With FEE_ANY_MINERAL off, only common (muted) minerals are accepted. None if nothing can pay."""
    best = None
    for i, s in enumerate(inv.slots):
        if i == exclude or s is None or not items.is_mineral(s[0]) or s[1] < need:
            continue
        tier = items.tier(items.code_of(s[0]))
        if tier > 0 and not C.FEE_ANY_MINERAL:
            continue
        key = (tier, s[1])
        if best is None or key < best[0]:
            best = (key, i)
    return None if best is None else best[1]


def _need_fee_text(fee):
    return (T.V_NEED_FEE if C.FEE_ANY_MINERAL else T.V_NEED_FEE_COMMON).format(fee=fee)


class VillageSession:
    def __init__(self, village, ctx):
        self.v, self.ctx = village, ctx
        self.state = ctx.book.get(village.id)
        self.page = "main"
        self.offset = 0                    # paging inside long lists
        self.note = ""
        self.closed = False
        self._actions = []

    # ---- helpers ------------------------------------------------------
    def _name(self, item, n=None):
        return self.ctx.name_of(item) + (f" x{n}" if n is not None else "")

    def _pays_with(self, fee):
        slot = _fee_slot(self.ctx.inventory, need=fee)
        if slot is None:
            return T.V_FEE_NONE
        return T.V_FEE_WITH.format(name=self.ctx.name_of(self.ctx.inventory.slots[slot][0]))

    def _go(self, page):
        self.page, self.offset = page, 0

    def _paged(self, entries):
        """entries: [(label, action)]. Returns options for the current page including More... / Back."""
        chunk = entries[self.offset:self.offset + PAGE]
        opts = list(chunk)
        if self.offset + PAGE < len(entries):
            opts.append((T.V_MORE, ("more",)))
        opts.append((T.V_BACK, ("back_to", "storage" if self.page in ("deposit", "withdraw") else "main")))
        return opts

    # ---- the screen for the current page --------------------------------
    def screen(self):
        c, st = self.ctx, self.state
        lines, opts = [], []
        if self.page == "main":
            lines = list(T.V_MAIN_LINES)
            opts = [(T.V_INN, ("goto", "inn")), (T.V_STORAGE, ("goto", "storage")), (T.V_TRADE, ("goto", "trade")),
                    (T.V_GUIDE, ("goto", "guide")), (T.V_REQUEST, ("goto", "request"))]
            if c.flags.boss_defeated:
                opts.append((T.V_SERVICES, ("goto", "services")))
            opts.append((T.V_LEAVE, ("leave",)))
        elif self.page == "inn":
            where = (T.V_INN_START if c.respawn is None
                     else T.V_INN_HERE if tuple(c.respawn) == tuple(self.v.stand) else T.V_INN_ELSEWHERE)
            lines = ([t.format(fee=C.INN_FEE) for t in T.V_INN_LINES] + [self._pays_with(C.INN_FEE)]
                     + [T.V_INN_STATUS.format(where=where)])
            opts = [(T.V_STAY, ("stay",)), (T.V_BACK, ("goto", "main"))]
        elif self.page == "storage":
            lines = [t.format(used=st.storage.used_slots(), cap=len(st.storage.slots), fee=C.STORAGE_FEE) for t in T.V_STORAGE_LINES]
            opts = [(T.V_DEPOSIT, ("goto", "deposit")), (T.V_WITHDRAW, ("goto", "withdraw")), (T.V_BACK, ("goto", "main"))]
        elif self.page == "deposit":
            lines = [t.format(fee=C.STORAGE_FEE) for t in T.V_DEPOSIT_LINES] + [self._pays_with(C.STORAGE_FEE)]
            entries = [(self._name(s[0], s[1]), ("deposit", i)) for i, s in enumerate(c.inventory.slots) if s is not None]
            opts = self._paged(entries) if entries else [(T.V_EMPTY, ("noop",)), (T.V_BACK, ("goto", "storage"))]
        elif self.page == "withdraw":
            lines = list(T.V_WITHDRAW_LINES)
            entries = [(self._name(s[0], s[1]), ("withdraw", i)) for i, s in enumerate(st.storage.slots) if s is not None]
            opts = self._paged(entries) if entries else [(T.V_EMPTY, ("noop",)), (T.V_BACK, ("goto", "storage"))]
        elif self.page == "trade":
            lines = list(T.V_TRADE_LINES)
            for k, o in enumerate(data.trade_offers(c.seed, self.v)):
                opts.append((T.V_TRADE_OFFER.format(qty=o.want_qty, want=self._name(o.want_item),
                                                    give=self._name(o.give_item, o.give_qty)), ("trade", k)))
            opts.append((T.V_BACK, ("goto", "main")))
        elif self.page == "guide":
            lines = list(T.V_GUIDE_LINES)
            opts = [(T.V_G_DANGER, ("guide", "danger")), (T.V_G_COLOURS, ("guide", "colours")), (T.V_G_MINERALS, ("guide", "minerals")),
                    (T.V_G_BOSS, ("guide", "boss")), (T.V_BACK, ("goto", "main"))]
        elif self.page == "guide_text":
            lines, opts = self._guide_lines(), [(T.V_BACK, ("goto", "guide"))]
        elif self.page == "request":
            item, qty = data.client_request(c.seed, self.v)
            if st.request_done:
                lines, opts = list(T.V_REQUEST_DONE_LINES), [(T.V_BACK, ("goto", "main"))]
            else:
                lines = [t.format(qty=qty, want=self._name(item), reward=T.V_REQUEST_REWARD.format(n=C.STORAGE_REQUEST_BONUS))
                         for t in T.V_REQUEST_LINES]
                opts = [(T.V_HAND_OVER, ("request",)), (T.V_BACK, ("goto", "main"))]
        elif self.page == "services":
            lines = list(T.V_SERVICES_LINES)
            costs = data.service_costs(c.seed, self.v)
            e, t = costs["expand"], costs["tonic"]
            opts = [(T.V_S_EXPAND.format(n=C.STORAGE_EXPAND_BONUS, qty=e[1], want=self._name(e[0])), ("service", "expand")),
                    (T.V_S_TONIC.format(n=C.TONIC_HP, qty=t[1], want=self._name(t[0])), ("service", "tonic")),
                    (T.V_BACK, ("goto", "main"))]
        self._actions = [a for _, a in opts]
        return Screen(T.V_TITLE.format(id=self.v.id), lines, [label for label, _ in opts], self.note)

    def _guide_lines(self):
        topic = self._topic
        if topic == "danger":
            return list(T.V_G_DANGER_TEXT)
        if topic == "colours":
            return list(T.V_G_COLOURS_TEXT)
        if topic == "minerals":
            return list(T.V_G_MINERALS_TEXT)
        if self.ctx.flags.boss_defeated:
            return list(T.V_G_BOSS_DONE)
        ax, az = boss_arena.arena_center(self.ctx.seed)
        self.ctx.flags.boss_known = True
        dx, dz = ax - self.v.x, az - self.v.z
        return [t.format(dist=(dx * dx + dz * dz) ** 0.5, dir=villages.direction_name(dx, dz), x=ax, z=az, level=C.BOSS_LEVEL)
                for t in T.V_G_BOSS_TEXT]

    # ---- choosing -----------------------------------------------------
    def choose(self, index):
        """Pick option `index` (0-based) of the screen last returned by screen()."""
        if not 0 <= index < len(self._actions):
            return
        self.note = ""
        act = self._actions[index]
        getattr(self, "_do_" + act[0])(*act[1:])

    def _do_noop(self):
        pass

    def _do_leave(self):
        self.closed = True
        self.note = T.V_LEFT

    def _do_goto(self, page):
        self._go(page)

    def _do_back_to(self, page):
        self._go(page)

    def _do_more(self):
        self.offset += PAGE

    def _do_guide(self, topic):
        self._topic = topic
        self._go("guide_text")

    def _do_stay(self):
        c = self.ctx
        here = c.respawn is not None and tuple(c.respawn) == tuple(self.v.stand)
        night = daytime.is_night(c.world_time)
        if here and c.stats.hp >= c.stats.max_hp and not night:
            self.note = T.V_STAY_NOTHING
            return
        fee = _fee_slot(c.inventory, need=C.INN_FEE)
        if fee is None:
            self.note = _need_fee_text(C.INN_FEE)
            return
        c.inventory.take(fee, C.INN_FEE)
        c.stats.restore_full()
        c.respawn = tuple(self.v.stand)
        if night:
            c.world_time = daytime.wake_time(c.world_time)       # a night at the inn ends in the morning
            self.note = T.V_STAY_OK_MORNING
        else:
            self.note = T.V_STAY_OK

    def _do_deposit(self, slot):
        c, store = self.ctx, self.state.storage
        s = c.inventory.slots[slot]
        if s is None:
            return
        item = s[0]
        if store.free_space_for(item) <= 0:
            self.note = T.V_STORAGE_FULL
            return
        fee = _fee_slot(c.inventory, need=C.STORAGE_FEE)
        if fee == slot and s[1] <= C.STORAGE_FEE:           # the fee may come from the stored stack only if something is left to store
            fee = _fee_slot(c.inventory, exclude=slot, need=C.STORAGE_FEE)
        if fee is None:
            self.note = _need_fee_text(C.STORAGE_FEE)
            return
        c.inventory.take(fee, C.STORAGE_FEE)
        s = c.inventory.slots[slot]
        n = s[1]
        left = store.add(item, n)
        moved = n - left
        c.inventory.take(slot, moved)
        self.note = (T.V_STORED if left == 0 else T.V_STORED_PART).format(name=self._name(item), n=moved)

    def _do_withdraw(self, slot):
        c, store = self.ctx, self.state.storage
        s = store.slots[slot]
        if s is None:
            return
        item, n = s
        take = min(n, c.inventory.free_space_for(item))
        if take <= 0:
            self.note = T.V_NO_ROOM
            return
        c.inventory.add(item, take)
        store.take(slot, take)
        self.note = (T.V_TOOK if take == n else T.V_TOOK_PART).format(name=self._name(item), n=take)

    def _do_trade(self, k):
        c = self.ctx
        o = data.trade_offers(c.seed, self.v)[k]
        if c.inventory.count(o.want_item) < o.want_qty:
            self.note = T.V_TRADE_MISSING.format(qty=o.want_qty, want=self._name(o.want_item))
            return
        c.inventory.remove_item(o.want_item, o.want_qty)
        if c.inventory.free_space_for(o.give_item) < o.give_qty:
            c.inventory.add(o.want_item, o.want_qty)          # no room for the goods: undo, nothing is lost
            self.note = T.V_NO_ROOM
            return
        c.inventory.add(o.give_item, o.give_qty)
        self.note = T.V_TRADED.format(give=self._name(o.give_item, o.give_qty))

    def _do_request(self):
        c, st = self.ctx, self.state
        item, qty = data.client_request(c.seed, self.v)
        if st.request_done:
            return
        if not c.inventory.remove_item(item, qty):
            self.note = T.V_TRADE_MISSING.format(qty=qty, want=self._name(item))
            return
        st.request_done = True
        st.storage.grow(C.STORAGE_REQUEST_BONUS)
        self.note = T.V_REQUEST_DONE

    def _do_service(self, which):
        c, st = self.ctx, self.state
        if not c.flags.boss_defeated:
            return
        item, qty = data.service_costs(c.seed, self.v)[which]
        if (which == "expand" and st.expanded) or (which == "tonic" and st.tonic):
            self.note = T.V_S_BOUGHT
            return
        if not c.inventory.remove_item(item, qty):
            self.note = T.V_TRADE_MISSING.format(qty=qty, want=self._name(item))
            return
        if which == "expand":
            st.expanded = True
            st.storage.grow(C.STORAGE_EXPAND_BONUS)
            self.note = T.V_S_EXPANDED.format(n=C.STORAGE_EXPAND_BONUS)
        else:
            st.tonic = True
            c.stats.base["hp"] += C.TONIC_HP
            c.stats.hp += C.TONIC_HP
            c.stats.version += 1
            self.note = T.V_S_TONIC_OK.format(n=C.TONIC_HP)


class BossGate:
    """The question you are asked when you step on the Wood tile in the lair. Same interface as VillageSession."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.closed = False
        self.fight = False
        self._actions = []

    def screen(self):
        if self.ctx.flags.boss_defeated:
            lines, opts = [T.BOSS_GONE], [(T.V_LEAVE, "leave")]
        else:
            lines = [t.format(level=C.BOSS_LEVEL) for t in T.BOSS_ASK_LINES]
            opts = [(T.BOSS_FIGHT, "fight"), (T.BOSS_LEAVE, "leave")]
        self._actions = [a for _, a in opts]
        return Screen(T.BOSS_NAME.upper(), lines, [label for label, _ in opts], "")

    def choose(self, index):
        if 0 <= index < len(self._actions):
            self.fight = self._actions[index] == "fight"
            self.closed = True


class ConfirmGate:
    """A yes / no question shown on the same screen as the village commands (same interface as VillageSession)."""

    def __init__(self, title, lines, yes, no):
        self.title, self.lines, self.yes, self.no = title, list(lines), yes, no
        self.closed = False
        self.confirmed = False

    def screen(self):
        return Screen(self.title, list(self.lines), [self.yes, self.no], "")

    def choose(self, index):
        if index in (0, 1):
            self.confirmed = index == 0
            self.closed = True
