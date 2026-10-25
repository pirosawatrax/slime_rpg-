"""What each village offers, decided by the seed and the village alone (no stored state): the merchant's offers, the
villager's request and the post-boss service prices. Colours are picked per village so every village wants different
colours, which gives colours their value (design 4.4, 9.2)."""
from dataclasses import dataclass

import config as C
import items
from blocks import WOOD, ROCK
from world.noise import hash2


@dataclass(frozen=True)
class Offer:
    want_item: int
    want_qty: int
    give_item: int
    give_qty: int


def _u(seed, v, k):
    return float(hash2(v.rx * 131 + k, v.rz * 977 + 3 * k + 1, seed + 9100 + k))


def _color(pool, u):
    return items.item_of(int(pool[min(int(u * len(pool)), len(pool) - 1)]))


def trade_offers(seed, v):
    """Three offers: a bundle of Wood (for bridges) and a bundle of Rock, each for minerals this village likes, and one rare
    mineral of the village's own colour in exchange for several uncommon ones."""
    common, uncommon, rare = items.TIER_CODES
    return [
        Offer(_color(common, _u(seed, v, 1)), 2, WOOD, 24),
        Offer(_color(uncommon, _u(seed, v, 2)), 1, ROCK, 32),
        Offer(_color(uncommon, _u(seed, v, 3)), 3, _color(rare, _u(seed, v, 4)), 1),
    ]


def client_request(seed, v):
    """(item, quantity) the villager wants: two minerals of a rare colour."""
    return _color(items.TIER_CODES[2], _u(seed, v, 5)), 2


def service_costs(seed, v):
    """Post-boss services, paid in post-boss colours: {'expand': (item, qty), 'tonic': (item, qty)}."""
    _, new_uncommon, new_rare = items.NEW_TIER_CODES
    return {"expand": (_color(new_uncommon, _u(seed, v, 6)), 3), "tonic": (_color(new_rare, _u(seed, v, 7)), 2)}
