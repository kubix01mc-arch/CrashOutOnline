import unittest
from unittest.mock import patch

import CrashOut_Resources as rules
import crash_out_window as ui
from server.session import MatchSession


class FreezeCardTests(unittest.TestCase):
    def test_freeze_card_immediately_freezes_target_for_three_turns(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        caster = rules.Player("Caster", 500, 1000)
        target = rules.Player("Target", 500, 1000)

        logs = rules.resolve_card(freeze, [caster, target], 0, 1)
        self.assertEqual(target.freeze_skip_turns, 3)
        self.assertIn("frozen", " ".join(logs).lower())
        self.assertIn("for 3 turns", " ".join(logs).lower())

    def test_freeze_does_not_stack_on_an_already_frozen_target(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        caster = rules.Player("Caster", 500, 1000, hand=[freeze])
        target = rules.Player("Target", 500, 1000, freeze_skip_turns=2)

        logs = rules.resolve_card(freeze, [caster, target], 0, 1)

        self.assertEqual(target.freeze_skip_turns, 2)
        self.assertIn("Freeze does not stack", " ".join(logs))
        self.assertTrue(rules.card_is_cooling(caster, freeze))

    def test_damage_is_halved_while_target_is_frozen(self) -> None:
        target = rules.Player("Frozen", 500, 1000, freeze_skip_turns=3)

        logs = rules.apply_damage(target, 100)

        self.assertEqual(target.hp, 450)
        self.assertIn("takes 50 damage", " ".join(logs))

    def test_frozen_player_can_use_cards_with_half_damage_and_healing(self) -> None:
        attack_heal = rules.craft_card(1, 50, 100, [])
        caster = rules.Player("Frozen", 400, 1000, freeze_skip_turns=3)
        target = rules.Player("Target", 500, 1000)

        logs = rules.resolve_card(attack_heal, [caster, target], 0, 1)

        self.assertEqual(target.hp, 475)
        self.assertEqual(caster.hp, 425)
        self.assertTrue(any("takes 25 damage" in line for line in logs))
        self.assertTrue(any("heals 25 HP" in line for line in logs))

    def test_frozen_player_can_use_mercy_for_half_healing(self) -> None:
        mercy = rules.make_mercy_card(1)
        caster = rules.Player("Frozen", 500, 1000, freeze_skip_turns=3)
        target = rules.Player("Target", 400, 1000)

        rules.resolve_card(mercy, [caster, target], 0, 1)

        self.assertEqual(target.hp, 425)

    def test_healing_a_frozen_player_is_halved(self) -> None:
        target = rules.Player("Frozen", 400, 1000, freeze_skip_turns=3)

        rules.apply_heal(target, 50)

        self.assertEqual(target.hp, 425)

    def test_frozen_player_applies_half_strength_poison(self) -> None:
        poison = rules.craft_card(1, 100, 100, [], poisons=True)
        caster = rules.Player("Frozen", 500, 1000, freeze_skip_turns=3)
        target = rules.Player("Target", 500, 1000)

        rules.resolve_card(poison, [caster, target], 0, 1)
        logs = rules.tick_poisons_on_turn_start(target)

        self.assertEqual(target.hp, 445)
        self.assertIn("5 damage", " ".join(logs))

    def test_frozen_shield_does_not_block_or_activate(self) -> None:
        target = rules.Player(
            "Frozen",
            500,
            1000,
            shield_charges=1,
            freeze_skip_turns=3,
        )
        shield = rules.craft_card(1, 0, 100, [], shields=True)
        caster = rules.Player("Shield user", 400, 1000, freeze_skip_turns=3)

        rules.apply_damage(target, 100)
        rules.resolve_card(shield, [caster, target], 0, 0)

        self.assertEqual(target.hp, 450)
        self.assertEqual(target.shield_charges, 1)
        self.assertEqual(caster.shield_charges, 0)

    def test_lava_mark_prevents_freeze_use(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        marked = rules.craft_card(2, 50, 100, [])
        marked.lava_marked = True
        caster = rules.Player("Caster", 500, 1000, hand=[freeze, marked])
        target = rules.Player("Target", 500, 1000)

        self.assertTrue(rules.card_is_cooling(caster, freeze))
        logs = rules.resolve_card(freeze, [caster, target], 0, 1)

        self.assertEqual(target.freeze_skip_turns, 0)
        self.assertIn("cannot use Freeze", " ".join(logs))

    def test_freeze_card_cools_until_effect_ends_then_one_caster_turn(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        caster = rules.Player("Caster", 500, 1000, hand=[freeze])
        target = rules.Player("Target", 500, 1000)
        players = [caster, target]

        rules.mark_card_played(caster, freeze)
        rules.resolve_card(freeze, players, 0, 1)
        self.assertTrue(rules.card_is_cooling(caster, freeze))

        for _ in range(3):
            rules.tick_turn_cooldowns(players, 1)
        self.assertEqual(target.freeze_skip_turns, 0)
        self.assertTrue(rules.card_is_cooling(caster, freeze))

        rules.tick_turn_cooldowns(players, 0)
        self.assertFalse(rules.card_is_cooling(caster, freeze))

    def test_lava_already_on_target_prevents_freeze_and_starts_cooldown(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        marked = rules.craft_card(2, 50, 100, [])
        marked.lava_marked = True
        caster = rules.Player("Caster", 500, 1000, hand=[freeze])
        target = rules.Player("Target", 500, 1000, hand=[marked])
        players = [caster, target]

        rules.mark_card_played(caster, freeze)
        logs = rules.resolve_card(freeze, players, 0, 1)

        self.assertEqual(target.freeze_skip_turns, 0)
        self.assertFalse(marked.lava_marked)
        self.assertTrue(rules.card_is_cooling(caster, freeze))
        self.assertTrue(any("prevent Freeze" in line for line in logs))

    def test_lava_applied_during_freeze_cancels_freeze_and_clears_marks(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        lava = rules.craft_card(2, 0, 100, [], lava=True)
        marked_cards = [
            rules.craft_card(card_id, 50, 100, [])
            for card_id in range(3, 7)
        ]
        caster = rules.Player("Freeze Caster", 500, 1000, hand=[freeze])
        lava_caster = rules.Player("Lava Caster", 500, 1000)
        target = rules.Player("Target", 500, 1000, hand=marked_cards)
        players = [caster, lava_caster, target]

        rules.mark_card_played(caster, freeze)
        rules.resolve_card(freeze, players, 0, 2)
        self.assertEqual(target.freeze_skip_turns, 3)

        with patch("CrashOut_Resources.random.sample", return_value=marked_cards[:2]):
            logs = rules.resolve_card(lava, players, 1, 2)

        self.assertEqual(target.freeze_skip_turns, 0)
        self.assertFalse(any(card.lava_marked for card in marked_cards))
        self.assertTrue(rules.card_is_cooling(caster, freeze))
        self.assertTrue(any("Freeze is removed" in line for line in logs))
        rules.tick_turn_cooldowns(players, 0)
        self.assertFalse(rules.card_is_cooling(caster, freeze))

    def test_freeze_is_persisted_and_protected_as_a_unique_card(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        decoded = rules.card_from_dict(rules.card_to_dict(freeze), 1)
        self.assertTrue(decoded.freeze)
        self.assertEqual(decoded.name, "Freeze")
        self.assertEqual(
            decoded.effect,
            "Freeze — the target is frozen for 3 turns but can still play cards. "
            "Damage dealt and received, and healing, are halved while frozen. "
            "Freeze does not stack and cannot be used while you have a lava-marked "
            "card. Target lava marks also cancel Freeze and are cleared.",
        )
        self.assertTrue(rules.is_protected_card(decoded))
        self.assertEqual(rules.unique_card_total([decoded]), 1)

    def test_deck_validation_rejects_duplicate_freeze_cards(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        normal = rules.craft_card(2, 50, 100, [])
        payload = rules.build_deck_export([freeze, normal], power_points=100)
        payload["cards"].append(rules.card_to_dict(freeze))

        with self.assertRaisesRegex(ValueError, "only have one Freeze card"):
            rules.validate_deck_export(payload)

    def test_freeze_stays_with_its_owner_when_hands_are_dealt(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        normal_cards = [
            rules.craft_card(card_id, 50, 100, [])
            for card_id in range(2, 5)
        ]

        hands = rules.shuffle_and_deal_hands(
            [[freeze, normal_cards[0]], normal_cards[1:]]
        )

        self.assertEqual(sum(card.freeze for card in hands[0]), 1)
        self.assertFalse(any(card.freeze for card in hands[1]))

    def test_frozen_player_takes_their_turns_and_freeze_expires_after_three(self) -> None:
        players = [
            rules.Player("First", 500, 1000),
            rules.Player("Frozen", 500, 1000, freeze_skip_turns=3),
            rules.Player("Third", 500, 1000),
        ]
        app = object.__new__(ui.CrashOutApp)
        logs: list[str] = []
        shown_turns: list[str] = []
        app.players = players
        app.active = 0
        app._borrows = []
        app._party_duel_active = False
        app._snapshot_hp = lambda: [player.hp for player in players]
        app._record_new_deaths = lambda *_args: None
        app.append_log = logs.append
        app.show_play = shown_turns.append
        app.show_game_over = lambda *_args: self.fail("unexpected game over")
        previous_play_sfx = ui.play_sfx
        ui.play_sfx = lambda *_args, **_kwargs: None
        try:
            for _ in range(3):
                ui.CrashOutApp.advance_turn(app)
                self.assertEqual(app.active, 1)
                self.assertEqual(players[1].freeze_skip_turns, 3 - _)
                rules.tick_turn_cooldowns(players, app.active)
                ui.CrashOutApp.advance_turn(app)
                ui.CrashOutApp.advance_turn(app)
        finally:
            ui.play_sfx = previous_play_sfx

        self.assertEqual(app.active, 0)
        self.assertEqual(players[1].freeze_skip_turns, 0)
        self.assertEqual(
            shown_turns,
            ["Turn — Frozen", "Turn — Third", "Turn — First"] * 3,
        )
        self.assertFalse(any("skips their turn" in line for line in logs))

        ui.CrashOutApp.advance_turn(app)
        self.assertEqual(shown_turns[-1], "Turn — Frozen")

    def test_online_turn_start_keeps_frozen_player_active(self) -> None:
        players = [
            rules.Player("First", 500, 1000),
            rules.Player("Frozen", 500, 1000, freeze_skip_turns=3),
            rules.Player("Third", 500, 1000),
        ]
        session = MatchSession(phase="play", players=players)

        session.active = 1
        session._turn_start_ticks()
        self.assertEqual(session.active, 1)
        self.assertEqual(players[1].freeze_skip_turns, 3)
        self.assertFalse(any("skips their turn" in line for line in session.log))

        for turns_left in (2, 1, 0):
            rules.tick_turn_cooldowns(players, 1)
            self.assertEqual(players[1].freeze_skip_turns, turns_left)

    def test_online_freeze_card_can_target_an_opponent(self) -> None:
        freeze = rules.craft_card(1, 0, 100, [], freeze=True)
        session = MatchSession(
            phase="play",
            players=[
                rules.Player("Caster", 500, 1000, hand=[freeze]),
                rules.Player("Target", 500, 1000),
            ],
        )

        self.assertEqual(session._valid_target_indices(freeze), [1])

    def test_gamble_jackpot_or_whiff_damage_and_heal(self) -> None:
        gamble = rules.craft_card(1, 0, 100, [], gamble=True)
        caster = rules.Player("Caster", 500, 1000)
        target = rules.Player("Target", 500, 1000)
        players = [caster, target]

        with patch("CrashOut_Resources.random.random", return_value=0.05):
            rules.resolve_card(gamble, players, 0, 1)
            self.assertEqual(target.hp, 300)
            self.assertEqual(caster.hp, 600)

        target.hp = 500
        caster.hp = 500
        with patch("CrashOut_Resources.random.random", return_value=0.5):
            rules.resolve_card(gamble, players, 0, 1)
            self.assertEqual(target.hp, 498)
            self.assertEqual(caster.hp, 501)


if __name__ == "__main__":
    unittest.main()
