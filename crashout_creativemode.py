#!/usr/bin/env python3
"""Crash Out — Creative Mode (no cooldowns, every card deals 999)."""

from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass, field

STARTING_HP = 100
PLAYER_COUNT_MIN = 2
PLAYER_COUNT_MAX = 100

# Creative Mode: every card deals 999 damage, no cooldowns.
STANDARD_DECK = [
    {"id": 1, "name": "Tap", "kind": "damage", "amount": 999},
    {"id": 2, "name": "Hit", "kind": "damage", "amount": 999},
    {"id": 3, "name": "Smash", "kind": "damage", "amount": 999},
    {"id": 4, "name": "Crush", "kind": "damage", "amount": 999},
    {"id": 5, "name": "Mend", "kind": "damage", "amount": 999},
]


@dataclass
class Card:
    id: int
    name: str
    kind: str  # "damage" or "heal"
    amount: int

    @property
    def effect(self) -> str:
        if self.kind == "heal":
            return f"Heal one player (including yourself) for {self.amount} HP."
        return f"Deal {self.amount} damage to one player (including yourself)."


@dataclass
class Player:
    name: str
    hp: int = STARTING_HP
    hand: list[Card] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.hp > 0


def make_standard_deck() -> list[Card]:
    return [Card(**c) for c in STANDARD_DECK]


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg: str = "Press Enter to continue...") -> None:
    input(msg)


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{msg}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("  Please enter something.")


def prompt_int(msg: str, lo: int, hi: int) -> int:
    while True:
        raw = input(f"{msg} ({lo}-{hi}): ").strip()
        try:
            n = int(raw)
            if lo <= n <= hi:
                return n
        except ValueError:
            pass
        print(f"  Enter a number between {lo} and {hi}.")


def prompt_choice(msg: str, options: list[str]) -> int:
    print(msg)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}) {opt}")
    return prompt_int("Choice", 1, len(options)) - 1


def banner(title: str) -> None:
    line = "=" * 52
    print(f"\n{line}\n  CRASH OUT CREATIVE — {title}\n{line}\n")


def print_card(card: Card, index: int | None = None) -> None:
    prefix = f"  [{index}] " if index is not None else "  "
    if card.kind == "heal":
        print(f"{prefix}{card.name} — heal {card.amount} HP")
    else:
        print(f"{prefix}{card.name} — {card.amount} damage")


def print_status(players: list[Player], active: int | None = None) -> None:
    print("Players:")
    for i, p in enumerate(players):
        mark = " <--" if i == active else ""
        status = f"{p.hp} HP" if p.alive else "OUT"
        print(f"  {i + 1}. {p.name}: {status}{mark}")
    print()


def make_players(count: int) -> list[Player]:
    """Fixed seats: player-1 .. player-N, same deck each."""
    return [
        Player(
            name=f"player-{i}",
            hand=copy.deepcopy(make_standard_deck()),
        )
        for i in range(1, count + 1)
    ]


def choose_player_count() -> int:
    clear()
    banner("Match Size")
    print("How many players for this match?\n")
    return prompt_choice(
        "Pick a match size:",
        [f"{count} players" for count in range(2, PLAYER_COUNT_MAX + 1)],
    ) + PLAYER_COUNT_MIN


def show_shared_deck() -> None:
    clear()
    banner("Shared Deck")
    print("Every player keeps these cards all game.")
    print("No cooldowns — play any card every turn.\n")
    for i, card in enumerate(make_standard_deck(), start=1):
        print_card(card, i)
    print()
    pause()


def pass_device(next_player: Player) -> None:
    clear()
    banner("Pass the Device")
    print(f"  Hand the terminal to {next_player.name}.")
    print("  Don't peek at other players' hands!\n")
    pause(f"{next_player.name}, press Enter to start your turn...")


def choose_target(players: list[Player], active: int) -> int | None:
    # You can target any living player, including yourself.
    legal = [i for i, p in enumerate(players) if p.alive]
    if not legal:
        return None
    options = []
    for i in legal:
        label = f"{players[i].name} ({players[i].hp} HP)"
        if i == active:
            label += " (you)"
        options.append(label)
    pick = prompt_choice("Choose a target (you can pick yourself):", options)
    return legal[pick]


def apply_damage(target: Player, damage: int) -> None:
    target.hp = max(0, target.hp - damage)
    if target.hp == 0:
        print(f"  -> {target.name} takes {damage} damage and is OUT!")
    else:
        print(f"  -> {target.name} takes {damage} damage ({target.hp} HP left)")


def apply_heal(target: Player, amount: int) -> None:
    target.hp += amount
    print(f"  -> {target.name} heals {amount} HP ({target.hp} HP now)")


def check_winner(players: list[Player]) -> Player | None:
    alive = [p for p in players if p.alive]
    if len(alive) == 1:
        return alive[0]
    return None


def next_alive_index(players: list[Player], current: int) -> int | None:
    n = len(players)
    for step in range(1, n + 1):
        i = (current + step) % n
        if players[i].alive:
            return i
    return None


def play_turn(players: list[Player], active: int) -> None:
    player = players[active]
    clear()
    banner(f"Turn — {player.name}")
    print_status(players, active)

    if not player.hand:
        print(f"{player.name} has no cards — turn skipped.")
        pause()
        return

    print("Your cards (no cooldown — reuse anytime):\n")
    for i, card in enumerate(player.hand, start=1):
        print_card(card, i)
    print()

    pick = prompt_int("Play which card #", 1, len(player.hand)) - 1
    card = player.hand[pick]

    if card.kind == "heal":
        print(f"\n>>> {player.name} plays '{card.name}' (heal {card.amount})!\n")
    else:
        print(f"\n>>> {player.name} plays '{card.name}' ({card.amount} damage)!\n")

    target_idx = choose_target(players, active)
    if target_idx is None:
        print("No valid targets.")
    else:
        who = players[target_idx].name
        if target_idx == active:
            who += " (self)"
        print(f"Targeted: {who}")
        print("\n--- Resolve ---")
        if card.kind == "heal":
            apply_heal(players[target_idx], card.amount)
        else:
            apply_damage(players[target_idx], card.amount)

    print()
    print_status(players)
    pause("End turn — press Enter...")


def game_loop(players: list[Player]) -> None:
    active = 0
    while True:
        if not players[active].alive:
            nxt = next_alive_index(players, active)
            if nxt is None:
                break
            active = nxt
            continue

        pass_device(players[active])
        play_turn(players, active)

        winner = check_winner(players)
        if winner is not None:
            clear()
            banner("Game Over")
            print_status(players)
            print(f"  *** {winner.name} wins! ***\n")
            pause()
            return

        nxt = next_alive_index(players, active)
        if nxt is None:
            clear()
            banner("Game Over")
            print("No one left standing.\n")
            pause()
            return
        active = nxt


def main() -> None:
    try:
        clear()
        banner("Welcome")
        print("Creative Mode — pick a 2, 3, or 4 player match.")
        print(f"Each player starts at {STARTING_HP} HP (no max cap).")
        print("Every card deals 999 damage. No cooldowns.")
        print("You can target any living player, including yourself.\n")
        pause()

        count = choose_player_count()
        show_shared_deck()
        players = make_players(count)
        clear()
        banner("Players")
        print_status(players)
        print(f"{count}-player match. Everyone starts at {STARTING_HP} HP.\n")
        pause("Press Enter to begin...")
        game_loop(players)

        clear()
        banner("Thanks for playing")
        again = prompt("Play again? (y/n)", "n").lower()
        if again.startswith("y"):
            main()
    except KeyboardInterrupt:
        print("\n\nAborted. See you next crash-out.")
        sys.exit(0)


if __name__ == "__main__":
    main()
