"""Random encounters by steps walked (design 6.2). Engine-free."""
import config as C


class EncounterTracker:
    def __init__(self, safe_steps=C.ENCOUNTER_SAFE_STEPS, chance=C.ENCOUNTER_CHANCE):
        self.safe_steps = safe_steps
        self.chance = chance
        self.steps = 0                 # whole steps since the last battle (or since loading)
        self._carry = 0.0

    def reset(self):
        self.steps = 0
        self._carry = 0.0

    def walk(self, distance, on_safe_ground, rng, chance_multiplier=1.0):
        """Report `distance` blocks walked on the ground. Returns True when a battle should start.
        Safe ground (a Wood floor or bridge) neither counts steps nor triggers anything.
        chance_multiplier scales the per-step chance (it is higher at night)."""
        if on_safe_ground or distance <= 0:
            return False
        self._carry += distance
        while self._carry >= 1.0:
            self._carry -= 1.0
            self.steps += 1
            if self.steps > self.safe_steps and rng.random() < min(1.0, self.chance * chance_multiplier):
                self.reset()
                return True
        return False
