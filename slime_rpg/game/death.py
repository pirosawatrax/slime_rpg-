"""Death (design 8.6): everything carried is lost. Where you wake up is decided by the caller."""


def apply_death(inventory, stats):
    """Empties the inventory and restores HP. Level, XP, colour and the world are kept. Returns slots lost."""
    lost = inventory.used_slots()
    inventory.slots = [None] * len(inventory.slots)
    inventory.version += 1
    stats.restore_full()
    return lost
