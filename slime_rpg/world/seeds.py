"""World seeds. A new game gets a random seed (a different map every time); a saved game keeps its own seed, because its
villages, caves and your edits all belong to that map. `--seed N` (or the SLIME_SEED environment variable) picks one on purpose."""
import random

MAX_SEED = 2 ** 31 - 2


def random_seed(rng=None):
    return (rng or random.SystemRandom()).randrange(1, MAX_SEED)


def seed_from_args(argv, environ):
    """The seed asked for on the command line (`--seed 123` or `--seed=123`) or in SLIME_SEED, else None."""
    value = None
    for i, arg in enumerate(argv):
        if arg == "--seed" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--seed="):
            value = arg.split("=", 1)[1]
    if value is None:
        value = environ.get("SLIME_SEED")
    try:
        seed = int(value)
    except (TypeError, ValueError):
        return None
    return seed if 1 <= seed <= MAX_SEED else None
