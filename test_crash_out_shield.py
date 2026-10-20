import unittest

import CrashOut_Resources as rules


class ShieldCardTests(unittest.TestCase):
    def test_crafted_shield_has_no_damage_or_healing(self) -> None:
        shield = rules.craft_card(1, 0, 100, [], shields=True)

        self.assertEqual((shield.damage, shield.heal), (0, 0))
        self.assertEqual(rules.effective_card_stats(shield), (0, 0))
        self.assertIn("no damage or healing", shield.effect.lower())
        self.assertEqual(shield.face_stats(), ("SHIELD", "block next hit"))

    def test_using_shield_does_not_heal_caster(self) -> None:
        shield = rules.craft_card(1, 0, 100, [], shields=True)
        caster = rules.Player("Caster", 400, 1000)
        target = rules.Player("Target", 500, 1000)

        rules.resolve_card(shield, [caster, target], 0, 1)

        self.assertEqual(caster.hp, 400)
        self.assertEqual(caster.shield_charges, 1)
        self.assertEqual(target.hp, 500)

    def test_legacy_shield_card_healing_is_removed_when_loaded(self) -> None:
        legacy = rules.card_from_dict(
            {
                "name": "Shield",
                "damage": 0,
                "heal": 50,
                "shields": True,
            },
            1,
        )

        self.assertEqual(legacy.heal, 0)
        self.assertEqual(rules.effective_card_stats(legacy), (0, 0))


if __name__ == "__main__":
    unittest.main()
