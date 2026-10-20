#!/usr/bin/env python3
"""Shared Crash Out game rules for the desktop and browser games."""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_STARTING_HP = 500
DEFAULT_POWER_POINTS = 100
PLAYER_COUNT_MIN = 1
PLAYER_COUNT_MAX = 100
DECK_SIZE = 10  # default max cards (includes Mercy as last card)
MAX_UNIQUE_CARDS_IN_DECK = 6
DECK_SIZE_MIN = 3
DECK_SIZE_MAX = 20
# Duplicate archetypes (Bruiser, etc.) only when deck_size > this (i.e. 12+).
# Steal / Heavy Hit / Shield / Poison stay unique regardless.
ARCHETYPE_UNIQUE_LIMIT = 11
FIFTH_CARD_HEAL = 50
STEAL_PP_COST = 25
HEAVY_HIT_MULTIPLIER = 1.5
COOLDOWN_CLEAR_TURNS = 2
HEAVY_HIT_COOLDOWN_TURNS = 2
# Damage% buckets for card names: every 10% PP (0%, 10%, …, 100%).
ARCHETYPE_BUCKETS = 10
BORROW_TURNS = 2  # return after thief ends this many turns (steal turn + 1 more)
POISON_DURATION_TURNS = 3
POISON_DOT_FRACTION = 0.10
VAMPIRE_DURATION_TURNS = 5
REAPER_DURATION_TURNS = 15
FREEZE_DURATION_TURNS = 3
GAMBLE_JACKPOT_CHANCE = 0.10
GAMBLE_JACKPOT_DAMAGE = 200
GAMBLE_JACKPOT_HEAL = 100
GAMBLE_WHIFF_DAMAGE = 2
GAMBLE_WHIFF_HEAL = 1
BOT_NAME = "bot"
HP_MIN, HP_MAX = 1, 1000000
PP_MIN, PP_MAX = 1, 999
TURN_DELAY_MS = 500
TURN_DELAY_SEC = 0.5

ARCHETYPE_NAMES: dict[int, str] = {
    0: "Sanctuary",
    1: "Haven",
    2: "Caretaker",
    3: "Medic",
    4: "Hybrid",
    5: "Allrounder",
    6: "Skirmisher",
    7: "Bruiser",
    8: "Brawler",
    9: "Destroyer",
    10: "Wrecker",
}

UNIQUE_CARD_FIELDS = (
    "steals",
    "heavy_hit",
    "shields",
    "poisons",
    "lava",
    "reaper",
    "vampire",
    "cure",
    "freeze",
    "gamble",
)


@dataclass
class ActiveReaper:
    source_idx: int
    target_idx: int
    turns_left: int = 5


@dataclass
class ActiveVampireMark:
    source_idx: int
    turns_left: int = VAMPIRE_DURATION_TURNS


@dataclass
class FreezeSource:
    source_idx: int
    card_id: int


@dataclass
class Card:
    id: int
    name: str
    damage: int
    heal: int
    heal_any: bool = False
    steals: bool = False
    heavy_hit: bool = False
    shields: bool = False
    poisons: bool = False
    exordia: bool = False
    lava: bool = False
    reaper: bool = False
    vampire: bool = False
    cure: bool = False
    freeze: bool = False
    gamble: bool = False
    exordia_uses: int = 0
    exordia_charged: bool = False
    lava_marked: bool = False
    borrowed_from: int | None = None
    cooldown_remaining: int = 0

    @property
    def effect(self) -> str:
        if self.heal_any:
            return f"Heal the selected player for {self.heal} HP."
        dmg, heal = effective_card_stats(self)
        base = f"{dmg} dmg to target / {heal} heal to you"
        if self.steals:
            return base + " / steal 1 opponent card for 1 turn"
        if self.heavy_hit:
            return (
                base
                + f" / {HEAVY_HIT_COOLDOWN_TURNS}-turn cooldown"
                + f" / clears target cooldowns for {COOLDOWN_CLEAR_TURNS} turns"
            )
        if self.shields:
            return (
                "Shield — block the next damage against you. "
                "This card grants no damage or healing and costs half PP."
            )
        if self.poisons:
            tick = poison_tick_damage(dmg)
            return (
                base
                + f" / Poison ({tick} dmg/turn for {POISON_DURATION_TURNS} turns)"
            )
        if self.lava:
            return "Floor is Lava — marks half of the targets cards, if you use a lava marked card, it deals 25% of your health back to you."
        if self.reaper:
            return f"Reaper — if you stay above the target's HP for {REAPER_DURATION_TURNS} consecutive turns, execute them at the end of the final turn."
        if self.cure:
            return "Cure — clears your poison, lava marks, Reaper effects, and Vampire marks from yourself."
        if self.freeze:
            return (
                f"Freeze — the target is frozen for {FREEZE_DURATION_TURNS} turns "
                "but can still play cards. Damage dealt and received, and healing, "
                "are halved while frozen. Freeze does not stack and cannot be used "
                "while you have a lava-marked card. Target lava marks also cancel "
                "Freeze and are cleared."
            )
        if self.gamble:
            return (
                f"Gamble — {int(GAMBLE_JACKPOT_CHANCE * 100)}% chance: "
                f"{GAMBLE_JACKPOT_DAMAGE} dmg / {GAMBLE_JACKPOT_HEAL} heal. "
                f"{int((1 - GAMBLE_JACKPOT_CHANCE) * 100)}% chance: "
                f"{GAMBLE_WHIFF_DAMAGE} dmg / {GAMBLE_WHIFF_HEAL} heal."
            )
        if self.vampire:
            return base + f" / Vampire mark ({VAMPIRE_DURATION_TURNS} turns; user heals half of target damage)"
        return base

    def label(self) -> str:
        if self.heal_any:
            base = f"{self.name} — heal {self.heal} HP (any target)"
        else:
            primary, extra = self.face_stats()
            primary_line = primary.replace("\n", " ")
            extra_note = ""
            if self.steals:
                extra_note = " + steal"
            elif self.heavy_hit:
                extra_note = " + Heavy Hit"
            elif self.shields:
                extra_note = " + Shield"
            elif self.poisons:
                extra_note = " + Poison"
            elif self.lava:
                extra_note = " + Floor is Lava"
            elif self.reaper:
                extra_note = " + Reaper"
            elif self.vampire:
                extra_note = " + Vampire"
            elif self.cure:
                extra_note = " + Cure"
            elif self.freeze:
                extra_note = " + Freeze"
            elif self.gamble:
                extra_note = " + Gamble"
            if not extra:
                base = f"{self.name} — {primary_line}{extra_note}"
            else:
                base = f"{self.name} — {primary_line} / {extra}"
        if self.is_borrowed:
            return base + " (borrowed)"
        return base

    @property
    def is_borrowed(self) -> bool:
        return self.borrowed_from is not None

    def face_stats(self) -> tuple[str, str]:
        """
        Primary stat (large) and extra detail (small) for card faces.
        Extra is heal when heal <= damage, otherwise damage.
        """
        if self.heal_any:
            return f"HEAL\n{self.heal}", "any target"
        if self.lava:
            return "LAVA", "mark half / 25% HP"
        if self.reaper:
            return "REAPER", f"{REAPER_DURATION_TURNS} turns above HP"
        if self.cure:
            return "CURE", "clear poison / lava / Reaper / Vampire"
        if self.shields:
            return "SHIELD", "block next hit"
        if self.freeze:
            return "FREEZE", f"{FREEZE_DURATION_TURNS} turns; half damage"
        if self.gamble:
            return "GAMBLE", "10% 200/100 · 90% 2/1"
        dmg, heal = effective_card_stats(self)
        if heal <= dmg:
            primary = f"{dmg}\nDMG"
            extra = f"+{heal} heal you" if heal > 0 else ""
        else:
            primary = f"{heal}\nHEAL"
            extra = f"+{dmg} dmg to target" if dmg > 0 else ""
        if self.steals:
            steal_line = "steal 1 card"
            extra = f"{extra} / {steal_line}" if extra else steal_line
        elif self.heavy_hit:
            heavy_line = f"{HEAVY_HIT_COOLDOWN_TURNS}t cd / clear cd {COOLDOWN_CLEAR_TURNS}t"
            extra = f"{extra} / {heavy_line}" if extra else heavy_line
        elif self.shields:
            shield_line = "block next hit"
            extra = f"{extra} / {shield_line}" if extra else shield_line
        elif self.poisons:
            tick = poison_tick_damage(dmg)
            poison_line = f"poison {tick}x{POISON_DURATION_TURNS}"
            extra = f"{extra} / {poison_line}" if extra else poison_line
        if self.vampire:
            extra = f"{extra} / vampire mark {VAMPIRE_DURATION_TURNS}t" if extra else f"vampire mark {VAMPIRE_DURATION_TURNS}t"
        return primary, extra


@dataclass
class ActiveBorrow:
    card: Card
    owner_idx: int
    thief_idx: int
    turns_left: int = BORROW_TURNS


@dataclass
class ActivePoison:
    damage_per_tick: int
    turns_left: int


@dataclass
class Player:
    name: str
    hp: int
    max_hp: int
    hand: list[Card] = field(default_factory=list)
    last_card_id: int | None = None
    cooldown_clear_turns: int = 0
    shield_charges: int = 0
    poisons: list[ActivePoison] = field(default_factory=list)
    reaper_marks: list[ActiveReaper] = field(default_factory=list)
    vampire_marks: list[ActiveVampireMark] = field(default_factory=list)
    freeze_skip_turns: int = 0
    freeze_sources: list[FreezeSource] = field(default_factory=list)
    freeze_card_cooling_ids: set[int] = field(default_factory=set)
    freeze_cooldown_turns: dict[int, int] = field(default_factory=dict)
    cheats_enabled: bool = False

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def is_bot(self) -> bool:
        return self.name == BOT_NAME

    @property
    def poisoned(self) -> bool:
        return any(p.turns_left > 0 for p in self.poisons)

    def playable_cards(self) -> list[Card]:
        return [c for c in self.hand if not card_is_cooling(self, c)]


def cooldown_turns_for(card: Card) -> int:
    return HEAVY_HIT_COOLDOWN_TURNS if card.heavy_hit else 1


def mark_card_played(player: Player, card: Card) -> None:
    """Start this card's cooldown. Tick at end of turn consumes 1 immediately."""
    player.last_card_id = card.id
    if card.freeze:
        return
    if player.cheats_enabled:
        for held in player.hand:
            held.cooldown_remaining = 0
        return
    turns = cooldown_turns_for(card)
    for held in player.hand:
        if held.id == card.id:
            held.cooldown_remaining = turns + 1
            break


def _cooldown_remaining(player: Player, card: Card) -> int:
    for held in player.hand:
        if held.id == card.id:
            return held.cooldown_remaining
    return 0


def card_is_cooling(player: Player, card: Card) -> bool:
    if card.freeze and any(held.lava_marked for held in player.hand):
        return True
    if player.cheats_enabled:
        return False
    if card.freeze and (
        card.id in player.freeze_card_cooling_ids
        or player.freeze_cooldown_turns.get(card.id, 0) > 0
    ):
        return True
    remaining = _cooldown_remaining(player, card)
    if remaining <= 0:
        return False
    # Cooldown-clear relief bypasses the 1-turn lock, but not Heavy Hit's own 2-turn lock.
    if player.cooldown_clear_turns > 0 and not card.heavy_hit:
        return False
    return True


def unique_card_count(cards: list[Card]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field, label in {
        "steals": "Steal",
        "heavy_hit": "Heavy Hit",
        "shields": "Shield",
        "poisons": "Poison",
        "lava": "Floor is Lava",
        "reaper": "Reaper",
        "vampire": "Vampire",
        "cure": "Cure",
        "freeze": "Freeze",
        "gamble": "Gamble",
    }.items():
        counts[label] = sum(getattr(card, field) for card in cards)
    return counts


def unique_card_total(cards: list[Card]) -> int:
    return sum(unique_card_count(cards).values())


@dataclass
class MatchSettings:
    player_count: int
    starting_hp: int
    power_points: int
    deck_size: int = DECK_SIZE

    @property
    def vs_bot(self) -> bool:
        return self.player_count == 1

    @property
    def max_hp(self) -> int:
        return self.starting_hp * 2

    @property
    def allow_duplicate_archetypes(self) -> bool:
        return allows_duplicate_archetypes(self.deck_size)


def allows_duplicate_archetypes(deck_size: int) -> bool:
    """Duplicate Sanctuary/Bruiser/etc. only when deck has 12+ cards."""
    return deck_size > ARCHETYPE_UNIQUE_LIMIT


def clamp_deck_size(deck_size: int) -> int:
    return max(DECK_SIZE_MIN, min(DECK_SIZE_MAX, deck_size))


def name_for_split(damage: int, heal: int, power_points: int) -> str:
    if damage == heal:
        return "Allrounder"
    if power_points <= 0:
        return "Allrounder"
    ratio = damage / power_points
    bucket = int(round(ratio * ARCHETYPE_BUCKETS))
    bucket = max(0, min(ARCHETYPE_BUCKETS, bucket))
    return ARCHETYPE_NAMES[bucket]


def damage_for_bucket(bucket: int, power_points: int) -> int:
    if bucket <= 0:
        return 0
    if bucket >= ARCHETYPE_BUCKETS:
        return power_points
    return int(round(power_points * bucket / ARCHETYPE_BUCKETS))


def uniquify_name(base: str, existing: list[Card]) -> str:
    used = {c.name for c in existing}
    if base not in used:
        return base
    n = 2
    while f"{base} {n}" in used:
        n += 1
    return f"{base} {n}"


def card_archetype(card: Card) -> str:
    """Archetype / Mercy / Heavy Hit / Shield / Poison / special card name used for uniqueness."""
    if card.heal_any:
        return "Mercy"
    if card.heavy_hit:
        return "Heavy Hit"
    if card.shields:
        return "Shield"
    if card.poisons:
        return "Poison"
    if card.lava:
        return "Floor is Lava"
    if card.reaper:
        return "Reaper"
    if card.vampire:
        return "Vampire"
    if card.cure:
        return "Cure"
    if card.freeze:
        return "Freeze"
    if card.gamble:
        return "Gamble"
    return name_for_split(card.damage, card.heal, card.damage + card.heal)


def archetype_taken(archetype: str, existing: list[Card]) -> bool:
    return any(card_archetype(c) == archetype for c in existing)


def stat_budget(
    power_points: int,
    steals: bool = False,
    *,
    shields: bool = False,
) -> int:
    if steals:
        return power_points - STEAL_PP_COST
    if shields:
        return 0
    return power_points


def shield_pp_cost(power_points: int) -> int:
    """Shield spends half the card's power points."""
    return max(0, int(power_points) // 2)


def can_craft_steal(power_points: int) -> bool:
    return power_points >= STEAL_PP_COST


def can_craft_shield(power_points: int) -> bool:
    """A Shield card requires positive PP and spends half on its effect."""
    return shield_pp_cost(power_points) < power_points


def deck_has_steal(existing: list[Card]) -> bool:
    return any(c.steals for c in existing)


def can_add_steal_card(existing: list[Card], power_points: int) -> bool:
    return can_craft_steal(power_points) and not deck_has_steal(existing)


def deck_has_heavy_hit(existing: list[Card]) -> bool:
    return any(c.heavy_hit for c in existing)


def can_add_heavy_hit_card(existing: list[Card]) -> bool:
    return not deck_has_heavy_hit(existing)


def deck_has_shield(existing: list[Card]) -> bool:
    return any(c.shields for c in existing)


def can_add_shield_card(existing: list[Card], power_points: int | None = None) -> bool:
    if deck_has_shield(existing):
        return False
    if power_points is not None and not can_craft_shield(power_points):
        return False
    return True


def deck_has_poison(existing: list[Card]) -> bool:
    return any(c.poisons for c in existing)


def deck_has_reaper(existing: list[Card]) -> bool:
    return any(c.reaper for c in existing)


def can_add_reaper_card(existing: list[Card]) -> bool:
    return not deck_has_reaper(existing)


def deck_has_cure(existing: list[Card]) -> bool:
    return any(c.cure for c in existing)


def can_add_cure_card(existing: list[Card]) -> bool:
    return not deck_has_cure(existing)


def can_add_poison_card(existing: list[Card]) -> bool:
    return not deck_has_poison(existing)


def deck_has_vampire(existing: list[Card]) -> bool:
    return any(c.vampire for c in existing)


def can_add_vampire_card(existing: list[Card]) -> bool:
    return not deck_has_vampire(existing)


def poison_tick_damage(card_damage: int) -> int:
    """10% of card damage per poison tick (at least 1 if the hit had damage)."""
    if card_damage <= 0:
        return 0
    return max(1, int(round(card_damage * POISON_DOT_FRACTION)))


def effective_card_stats(card: Card) -> tuple[int, int]:
    if card.shields:
        return card.damage, 0
    if card.heavy_hit:
        return (
            int(round(card.damage * HEAVY_HIT_MULTIPLIER)),
            int(round(card.heal * HEAVY_HIT_MULTIPLIER)),
        )
    return card.damage, card.heal


def tick_reaper_marks(players: list[Player]) -> list[str]:
    logs: list[str] = []
    for player in players:
        remaining: list[ActiveReaper] = []
        for mark in player.reaper_marks:
            source = players[mark.source_idx] if 0 <= mark.source_idx < len(players) else None
            if source is None or not source.alive or not player.alive:
                continue
            if source.hp <= player.hp:
                logs.append(f"{player.name}'s Reaper mark breaks because their HP is no longer lower.")
                continue
            if mark.turns_left <= 1:
                logs.append(f"{source.name}'s Reaper executes {player.name}.")
                player.hp = 0
                continue
            mark.turns_left -= 1
            remaining.append(mark)
            logs.append(f"Reaper holds on {player.name}: {mark.turns_left} turn(s) remain.")
        player.reaper_marks = remaining
    return logs


def apply_vampire_mark(target: Player, source_idx: int) -> list[str]:
    if not target.alive:
        return []
    for mark in target.vampire_marks:
        if mark.source_idx == source_idx:
            mark.turns_left = VAMPIRE_DURATION_TURNS
            break
    else:
        target.vampire_marks.append(ActiveVampireMark(source_idx))
    return [
        f"{target.name} is Vampire-marked for {VAMPIRE_DURATION_TURNS} turns; "
        "the card's user heals half of damage the target takes during that time."
    ]


def tick_vampire_marks(player: Player) -> list[str]:
    if not player.vampire_marks:
        return []
    logs: list[str] = []
    remaining: list[ActiveVampireMark] = []
    for mark in player.vampire_marks:
        mark.turns_left -= 1
        if mark.turns_left > 0:
            remaining.append(mark)
            logs.append(
                f"Vampire mark on {player.name}: {mark.turns_left} turn(s) remain."
            )
        else:
            logs.append(f"Vampire mark on {player.name} wore off.")
    player.vampire_marks = remaining
    return logs


def craft_card(
    card_id: int,
    damage: int,
    power_points: int,
    existing: list[Card],
    *,
    steals: bool = False,
    heavy_hit: bool = False,
    shields: bool = False,
    poisons: bool = False,
    exordia: bool = False,
    lava: bool = False,
    reaper: bool = False,
    vampire: bool = False,
    cure: bool = False,
    freeze: bool = False,
    gamble: bool = False,
    deck_size: int = DECK_SIZE,
) -> Card:
    """
    Build a craftable card.
    Special cards are treated as unique one-per-deck effects. Standard archetypes stay unique
    unless deck_size is above ARCHETYPE_UNIQUE_LIMIT.
    """
    if exordia:
        raise ValueError("Exodia cards have been removed from Crash Out.")
    uniques = sum(
        1
        for flag in (
            steals,
            heavy_hit,
            shields,
            poisons,
            lava,
            reaper,
            vampire,
            cure,
            freeze,
            gamble,
        )
        if flag
    )
    if uniques > 1:
        raise ValueError(
            "A card can only have one special effect: Steal, Heavy Hit, Shield, Poison, "
            "Floor is Lava, Reaper, Vampire, Cure, Freeze, or Gamble."
        )
    if steals and not can_craft_steal(power_points):
        raise ValueError(f"Steal costs {STEAL_PP_COST} PP — not enough budget.")
    if steals and deck_has_steal(existing):
        raise ValueError("Your deck already has a steal card. Only one per deck.")
    if heavy_hit and deck_has_heavy_hit(existing):
        raise ValueError("Your deck already has a Heavy Hit card. Only one per deck.")
    if shields and deck_has_shield(existing):
        raise ValueError("Your deck already has a Shield card. Only one per deck.")
    if shields and not can_craft_shield(power_points):
        raise ValueError("Shield requires positive PP.")
    if poisons and deck_has_poison(existing):
        raise ValueError("Your deck already has a Poison card. Only one per deck.")
    if lava and any(c.lava for c in existing):
        raise ValueError("Your deck already has a Floor is Lava card. Only one per deck.")
    if reaper and any(c.reaper for c in existing):
        raise ValueError("Your deck already has a Reaper card. Only one per deck.")
    if vampire and deck_has_vampire(existing):
        raise ValueError("Your deck already has a Vampire card. Only one per deck.")
    if cure and any(c.cure for c in existing):
        raise ValueError("Your deck already has a Cure card. Only one per deck.")
    if freeze and any(c.freeze for c in existing):
        raise ValueError("Your deck already has a Freeze card. Only one per deck.")
    if gamble and any(c.gamble for c in existing):
        raise ValueError("Your deck already has a Gamble card. Only one per deck.")
    if deck_size == DECK_SIZE and any(
        (
            steals,
            heavy_hit,
            shields,
            poisons,
            lava,
            reaper,
            vampire,
            cure,
            freeze,
            gamble,
        )
    ) and unique_card_total(existing) >= MAX_UNIQUE_CARDS_IN_DECK:
        raise ValueError(
            f"A {DECK_SIZE}-card deck can have at most "
            f"{MAX_UNIQUE_CARDS_IN_DECK} unique cards."
        )

    if shields or lava or reaper or cure or freeze or gamble:
        damage = 0
        heal = 0
    else:
        budget = stat_budget(power_points, steals, shields=shields)
        damage = max(0, min(budget, damage))
        heal = budget - damage
        if poisons and heal > 0:
            raise ValueError("Poison can only be put on a damage-only card (0 heal).")

    if heavy_hit:
        base = "Heavy Hit"
    elif shields:
        base = "Shield"
    elif poisons:
        base = "Poison"
    elif lava:
        base = "Floor is Lava"
    elif reaper:
        base = "Reaper"
    elif vampire:
        base = "Vampire"
    elif cure:
        base = "Cure"
    elif freeze:
        base = "Freeze"
    elif gamble:
        base = "Gamble"
    else:
        budget = stat_budget(power_points, steals, shields=shields)
        base = name_for_split(damage, heal, budget)
    allow_dupes = allows_duplicate_archetypes(deck_size)
    if archetype_taken(base, existing) and not allow_dupes:
        raise ValueError(
            f"Your deck already has a {base} card. "
            "Pick a different damage/heal split."
        )
    name = uniquify_name(base, existing) if allow_dupes else base
    return Card(
        id=card_id,
        name=name,
        damage=damage,
        heal=heal,
        heal_any=False,
        steals=steals,
        heavy_hit=heavy_hit,
        shields=shields,
        poisons=poisons,
        exordia=exordia,
        lava=lava,
        reaper=reaper,
        vampire=vampire,
        cure=cure,
        freeze=freeze,
        gamble=gamble,
    )


def make_mercy_card(card_id: int = DECK_SIZE, existing: list[Card] | None = None) -> Card:
    name = "Mercy"
    if existing is not None:
        name = uniquify_name("Mercy", existing)
    return Card(
        id=card_id,
        name=name,
        damage=0,
        heal=FIFTH_CARD_HEAL,
        heal_any=True,
    )


DECK_FILE_FORMAT = "crash_out_deck"
DECK_FILE_VERSION = 1
DECKS_DIR_NAME = "decks"


def card_to_dict(card: Card) -> dict[str, Any]:
    return {
        "name": card.name,
        "damage": int(card.damage),
        "heal": int(card.heal),
        "heal_any": bool(card.heal_any),
        "steals": bool(card.steals),
        "heavy_hit": bool(card.heavy_hit),
        "shields": bool(card.shields),
        "poisons": bool(card.poisons),
        "exordia": bool(card.exordia),
        "lava": bool(card.lava),
        "reaper": bool(card.reaper),
        "vampire": bool(card.vampire),
        "cure": bool(card.cure),
        "freeze": bool(card.freeze),
        "gamble": bool(card.gamble),
        "exordia_uses": int(card.exordia_uses),
        "exordia_charged": bool(card.exordia_charged),
        "lava_marked": bool(card.lava_marked),
    }


def card_from_dict(data: dict[str, Any], card_id: int) -> Card:
    if data.get("cloak") or data.get("joker"):
        raise ValueError("Cloak and Joker cards are no longer supported.")
    shields = bool(data.get("shields", False))
    return Card(
        id=card_id,
        name=str(data.get("name") or f"Card{card_id}"),
        damage=max(0, int(data.get("damage", 0))),
        heal=0 if shields else max(0, int(data.get("heal", 0))),
        heal_any=bool(data.get("heal_any", False)),
        steals=bool(data.get("steals", False)),
        heavy_hit=bool(data.get("heavy_hit", False)),
        shields=shields,
        poisons=bool(data.get("poisons", False)),
        exordia=bool(data.get("exordia", False)),
        lava=bool(data.get("lava", False)),
        reaper=bool(data.get("reaper", False)),
        vampire=bool(data.get("vampire", False)),
        cure=bool(data.get("cure", False)),
        freeze=bool(data.get("freeze", False)),
        gamble=bool(data.get("gamble", False)),
        exordia_uses=max(0, int(data.get("exordia_uses", 0))),
        exordia_charged=bool(data.get("exordia_charged", False)),
        lava_marked=bool(data.get("lava_marked", False)),
    )


def build_deck_export(
    cards: list[Card],
    *,
    power_points: int,
    deck_size: int | None = None,
    name: str = "",
) -> dict[str, Any]:
    """
    Build a portable deck JSON object.
    If Mercy is missing, append one so the file is a complete playable deck.
    """
    exported = [copy.deepcopy(c) for c in cards]
    size = deck_size or max(len(exported) + (0 if any(c.heal_any for c in exported) else 1), DECK_SIZE_MIN)
    size = clamp_deck_size(size)
    if not any(c.heal_any for c in exported):
        exported.append(make_mercy_card(size, exported))
    # Normalize ids 1..n
    for i, card in enumerate(exported, start=1):
        card.id = i
        card.borrowed_from = None
        card.cooldown_remaining = 0
    return {
        "format": DECK_FILE_FORMAT,
        "version": DECK_FILE_VERSION,
        "name": name or "Saved Deck",
        "power_points": int(power_points),
        "deck_size": len(exported),
        "cards": [card_to_dict(c) for c in exported],
    }


def validate_deck_export(data: dict[str, Any]) -> tuple[list[Card], int, str]:
    """
    Parse and validate a deck file.
    Returns (cards, power_points, deck_name). Raises ValueError on bad data.
    """
    if not isinstance(data, dict):
        raise ValueError("Deck file must be a JSON object.")
    if data.get("format") != DECK_FILE_FORMAT:
        raise ValueError("Not a Crash Out deck file.")
    cards_raw = data.get("cards")
    if not isinstance(cards_raw, list) or not cards_raw:
        raise ValueError("Deck file has no cards.")
    power_points = int(data.get("power_points", DEFAULT_POWER_POINTS))
    if not (PP_MIN <= power_points <= PP_MAX):
        raise ValueError(f"Invalid power points in deck file ({power_points}).")
    deck_name = str(data.get("name") or "Saved Deck")

    cards: list[Card] = []
    for i, raw in enumerate(cards_raw, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Card {i} is invalid.")
        if bool(raw.get("exordia", False)):
            raise ValueError("Exodia cards have been removed from Crash Out.")
        card = card_from_dict(raw, i)
        unique_flags = sum(bool(getattr(card, field)) for field in UNIQUE_CARD_FIELDS)
        if unique_flags > 1:
            raise ValueError(
                f"Card '{card.name}' can only have one special effect: "
                "Steal, Heavy Hit, Shield, Poison, Floor is Lava, "
                "Reaper, Vampire, Cure, Freeze, or Gamble."
            )
        if card.heal_any:
            if (
                card.steals
                or card.heavy_hit
                or card.shields
                or card.poisons
                or card.lava
                or card.reaper
                or card.vampire
                or card.cure
                or card.freeze
                or card.gamble
            ):
                raise ValueError(
                    f"Mercy card '{card.name}' cannot have special effects."
                )
        else:
            if not (
                card.lava
                or card.reaper
                or card.cure
                or card.freeze
                or card.gamble
                or card.shields
            ):
                budget = stat_budget(power_points, card.steals, shields=card.shields)
                if card.damage + card.heal != budget:
                    raise ValueError(
                        f"Card '{card.name}' stats ({card.damage}+{card.heal}) "
                        f"do not match {power_points} PP budget ({budget})."
                    )
            if card.shields and (card.damage > 0 or card.heal > 0):
                raise ValueError(
                    f"Shield card '{card.name}' cannot deal damage or heal."
                )
            if card.poisons and card.heal > 0:
                raise ValueError(
                    f"Poison card '{card.name}' must be damage-only (0 heal)."
                )
        cards.append(card)

    if len(cards) < DECK_SIZE_MIN or len(cards) > DECK_SIZE_MAX:
        raise ValueError(
            f"Deck size must be {DECK_SIZE_MIN}-{DECK_SIZE_MAX} (got {len(cards)})."
        )
    mercies = [c for c in cards if c.heal_any]
    if len(mercies) != 1:
        raise ValueError("Deck must include exactly one Mercy card.")
    unique_labels = {
        "steals": "steal",
        "heavy_hit": "Heavy Hit",
        "shields": "Shield",
        "poisons": "Poison",
        "lava": "Floor is Lava",
        "reaper": "Reaper",
        "vampire": "Vampire",
        "cure": "Cure",
        "freeze": "Freeze",
        "gamble": "Gamble",
    }
    for field, label in unique_labels.items():
        if sum(bool(getattr(card, field)) for card in cards) > 1:
            raise ValueError(f"Deck can only have one {label} card.")
    if any(count > 1 for count in unique_card_count(cards).values()):
        raise ValueError("Deck can only have one of each unique card.")
    if len(cards) == DECK_SIZE and unique_card_total(cards) > MAX_UNIQUE_CARDS_IN_DECK:
        raise ValueError(
            f"A {DECK_SIZE}-card deck can have at most "
            f"{MAX_UNIQUE_CARDS_IN_DECK} unique cards."
        )
    return cards, power_points, deck_name


def save_deck_file(path: Path | str, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_deck_file(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Deck file must be a JSON object.")
    return data


def default_decks_dir(project_root: Path | None = None) -> Path:
    root = project_root or Path(__file__).resolve().parent
    return root / DECKS_DIR_NAME


def make_bot_deck(power_points: int, deck_size: int = DECK_SIZE) -> list[Card]:
    deck_size = clamp_deck_size(deck_size)
    # Preferred craftable pattern across 10% buckets; cycles when deck is larger.
    buckets = [2, 7, 10, 0, 5, 3, 8, 1, 9, 4]
    craftable = max(0, deck_size - 1)
    deck: list[Card] = []
    for i in range(craftable):
        bucket = buckets[i % len(buckets)]
        damage = damage_for_bucket(bucket, power_points)
        heal = power_points - damage
        base = name_for_split(damage, heal, power_points)
        name = uniquify_name(base, deck)
        deck.append(
            Card(id=i + 1, name=name, damage=damage, heal=heal, heal_any=False)
        )
    deck.append(make_mercy_card(deck_size, deck))
    return deck


def normalize_hand_ids(hand: list[Card]) -> list[Card]:
    """Assign ids 1..n for cooldown tracking on a dealt hand."""
    normalized: list[Card] = []
    for i, card in enumerate(hand, start=1):
        dealt = copy.deepcopy(card)
        dealt.id = i
        dealt.borrowed_from = None
        normalized.append(dealt)
    return normalized


def is_protected_card(card: Card) -> bool:
    """Mercy and unique-attribute cards stay with the player who crafted them."""
    return (
        card.heal_any
        or card.steals
        or card.heavy_hit
        or card.shields
        or card.poisons
        or card.lava
        or card.reaper
        or card.vampire
        or card.cure
        or card.freeze
        or card.gamble
    )


def shuffle_and_deal_hands(player_decks: list[list[Card]]) -> list[list[Card]]:
    """Shuffle craftable cards only; Mercy and unique-effect cards stay with their owner."""
    if not player_decks:
        return []
    protected_hands: list[list[Card]] = []
    shuffle_pool: list[Card] = []

    for deck in player_decks:
        protected = [copy.deepcopy(c) for c in deck if is_protected_card(c)]
        shuffleable = [copy.deepcopy(c) for c in deck if not is_protected_card(c)]
        protected_hands.append(protected)
        shuffle_pool.extend(shuffleable)

    quotas = [len(deck) - len(protected) for deck, protected in zip(player_decks, protected_hands)]
    if sum(quotas) != len(shuffle_pool):
        raise ValueError(
            f"Shuffle pool size {len(shuffle_pool)} does not match deal quotas {quotas}."
        )

    random.shuffle(shuffle_pool)
    hands: list[list[Card]] = []
    offset = 0
    for protected, quota in zip(protected_hands, quotas):
        drawn = shuffle_pool[offset : offset + quota]
        offset += quota
        hands.append(normalize_hand_ids(protected + drawn))
    return hands


def make_players(count: int, deck: list[Card], starting_hp: int) -> list[Player]:
    max_hp = starting_hp * 2
    return [
        Player(
            name=f"player-{i}",
            hp=starting_hp,
            max_hp=max_hp,
            hand=copy.deepcopy(deck),
        )
        for i in range(1, count + 1)
    ]


def make_players_from_mixed_decks(
    player_decks: list[list[Card]],
    starting_hp: int,
) -> list[Player]:
    """Combine crafted decks, shuffle, and deal hands for hotseat multiplayer."""
    hands = shuffle_and_deal_hands(player_decks)
    max_hp = starting_hp * 2
    return [
        Player(
            name=f"player-{i + 1}",
            hp=starting_hp,
            max_hp=max_hp,
            hand=hands[i],
        )
        for i in range(len(hands))
    ]


def make_solo_players(
    human_deck: list[Card],
    bot_deck: list[Card],
    starting_hp: int,
) -> list[Player]:
    max_hp = starting_hp * 2
    return [
        Player(
            name="player-1",
            hp=starting_hp,
            max_hp=max_hp,
            hand=copy.deepcopy(human_deck),
        ),
        Player(
            name=BOT_NAME,
            hp=starting_hp,
            max_hp=max_hp,
            hand=copy.deepcopy(bot_deck),
        ),
    ]


def apply_damage(
    target: Player,
    damage: int,
    *,
    players: list[Player] | None = None,
    bypass_shield: bool = False,
    source_frozen: bool = False,
) -> list[str]:
    if damage <= 0:
        return []
    if target.freeze_skip_turns > 0 or source_frozen:
        damage = (damage + 1) // 2
    if target.cheats_enabled:
        return [f"{target.name}'s DEBUG immunity blocks {damage} damage."]
    if (
        not bypass_shield
        and target.shield_charges > 0
        and target.freeze_skip_turns <= 0
    ):
        target.shield_charges -= 1
        try:
            from crash_out_sfx import SFX_SHIELD_BLOCK, play_sfx

            play_sfx(SFX_SHIELD_BLOCK)
        except Exception:
            pass
        return [
            f"{target.name}'s Shield blocks {damage} damage!"
            + (" (Shield spent.)" if target.shield_charges <= 0 else "")
        ]
    hp_before = target.hp
    target.hp = max(0, target.hp - damage)
    damage_taken = hp_before - target.hp
    logs = []
    if damage_taken > 0 and players is not None:
        healed_sources: set[int] = set()
        for mark in target.vampire_marks:
            source_idx = mark.source_idx
            if (
                mark.turns_left <= 0
                or source_idx in healed_sources
                or not 0 <= source_idx < len(players)
            ):
                continue
            source = players[source_idx]
            if not source.alive:
                continue
            healed_sources.add(source_idx)
            heal_amount = damage_taken // 2
            if heal_amount > 0:
                logs.extend(apply_heal(source, heal_amount))
                logs.append(
                    f"Vampire heals {source.name} for half of {damage_taken} damage."
                )
    if target.hp == 0:
        try:
            from crash_out_sfx import SFX_CRASH_OUT, play_sfx

            play_sfx(SFX_CRASH_OUT)
        except Exception:
            pass
        return logs + [f"{target.name} takes {damage} damage and is OUT!"]
    try:
        from crash_out_sfx import SFX_DAMAGE, play_sfx

        play_sfx(SFX_DAMAGE)
    except Exception:
        pass
    return logs + [
        f"{target.name} takes {damage} damage ({target.hp}/{target.max_hp} HP left)"
    ]


def apply_heal(
    target: Player,
    amount: int,
    *,
    source_frozen: bool = False,
) -> list[str]:
    if target.freeze_skip_turns > 0 or source_frozen:
        amount = (amount + 1) // 2
    before = target.hp
    target.hp = min(target.max_hp, target.hp + amount)
    gained = target.hp - before
    if gained > 0:
        try:
            from crash_out_sfx import SFX_HEAL, play_sfx

            play_sfx(SFX_HEAL, delay_ms=90)
        except Exception:
            pass
    if gained < amount:
        return [
            f"{target.name} heals {gained} HP "
            f"(capped at max {target.max_hp}; now {target.hp}/{target.max_hp})"
        ]
    return [f"{target.name} heals {gained} HP ({target.hp}/{target.max_hp} HP now)"]


def resolve_card(
    card: Card,
    players: list[Player],
    active: int,
    target_idx: int,
    borrows: list[ActiveBorrow] | None = None,
) -> list[str]:
    """
    Normal cards:
      - Target other: damage them, then heal the caster.
      - Target self: heal the caster only (no self-damage).
    Mercy: heal only the selected target.
    """
    logs: list[str] = []
    caster = players[active]
    target = players[target_idx]
    source_frozen = caster.freeze_skip_turns > 0

    if card.freeze and any(held.lava_marked for held in caster.hand):
        logs.append(
            f"{caster.name} cannot use Freeze while they have a lava-marked card."
        )
        return logs

    if card.lava_marked:
        penalty = max(1, int(round(caster.hp * 0.25)))
        card.lava_marked = False
        logs.extend(
            apply_damage(
                caster,
                penalty,
                players=players,
                source_frozen=source_frozen,
            )
        )
        logs.append(
            f"{card.name} was marked by Floor is Lava — {caster.name} takes {penalty} damage ({penalty} = 25% of current HP)."
        )

    if card.cure:
        if card.lava_marked:
            card.lava_marked = False
            logs.append(f"{card.name} clears its own lava mark.")
        caster.poisons.clear()
        for held in caster.hand:
            if held.lava_marked:
                held.lava_marked = False
        caster.reaper_marks.clear()
        caster.vampire_marks.clear()
        logs.append(
            f"{caster.name}'s Cure removes their poison, lava marks, "
            "Reaper marks, and Vampire marks."
        )
        return logs

    if card.freeze:
        if any(held.lava_marked for held in target.hand):
            logs.extend(
                cancel_freeze_for_lava(
                    target,
                    players,
                    current_turn_idx=active,
                )
            )
            caster.freeze_cooldown_turns[card.id] = 2
            logs.append(
                f"{target.name}'s lava marks prevent Freeze; the freeze is canceled."
            )
            return logs
        already_frozen = target.freeze_skip_turns > 0
        if not already_frozen:
            target.freeze_skip_turns = FREEZE_DURATION_TURNS
        if not any(
            source.source_idx == active and source.card_id == card.id
            for source in target.freeze_sources
        ):
            target.freeze_sources.append(FreezeSource(active, card.id))
        caster.freeze_card_cooling_ids.add(card.id)
        if already_frozen:
            logs.append(f"{target.name} is already frozen; Freeze does not stack.")
        else:
            logs.append(
                f"{target.name} is frozen for {FREEZE_DURATION_TURNS} turns."
            )
        return logs

    if card.gamble:
        if random.random() < GAMBLE_JACKPOT_CHANCE:
            damage, heal = GAMBLE_JACKPOT_DAMAGE, GAMBLE_JACKPOT_HEAL
            outcome = "hits the jackpot"
        else:
            damage, heal = GAMBLE_WHIFF_DAMAGE, GAMBLE_WHIFF_HEAL
            outcome = "whiffs"
        if target_idx != active:
            logs.extend(
                apply_damage(
                    target,
                    damage,
                    players=players,
                    source_frozen=source_frozen,
                )
            )
        logs.extend(apply_heal(caster, heal, source_frozen=source_frozen))
        logs.append(
            f"{caster.name}'s Gamble {outcome}: {damage} damage / {heal} heal."
        )
        return logs

    if card.reaper:
        if caster.hp <= target.hp:
            logs.append(f"{caster.name}'s Reaper fails because their HP is not higher than {target.name}'s.")
            return logs
        target.reaper_marks.append(
            ActiveReaper(
                source_idx=active,
                target_idx=target_idx,
                turns_left=REAPER_DURATION_TURNS,
            )
        )
        logs.append(
            f"{target.name} is marked by Reaper: {caster.name} must stay above "
            f"them in HP for {REAPER_DURATION_TURNS} turns."
        )
        return logs

    if card.lava:
        marked_cards = []
        if target.hand:
            need = max(1, (len(target.hand) + 1) // 2)
            chosen = random.sample(target.hand, k=min(len(target.hand), need))
            for held in chosen:
                held.lava_marked = True
                marked_cards.append(held.name)
        if marked_cards:
            logs.append(f"{target.name}'s cards are lava-marked: {', '.join(marked_cards)}.")
            if target.freeze_skip_turns > 0:
                logs.extend(
                    cancel_freeze_for_lava(
                        target,
                        players,
                        current_turn_idx=active,
                    )
                )
        else:
            logs.append(f"{target.name} has no cards to lava-mark.")
        return logs

    damage, heal = effective_card_stats(card)

    if card.heal_any:
        logs.extend(apply_heal(target, card.heal, source_frozen=source_frozen))
        return logs

    if target_idx == active:
        if heal > 0:
            logs.extend(apply_heal(caster, heal, source_frozen=source_frozen))
        else:
            logs.append(f"{card.name} has 0 heal — nothing happens on self.")
        if damage > 0:
            logs.append(f"(Its {damage} damage is ignored on self.)")
        if card.heavy_hit:
            keep_id = card.id if target_idx == active else None
            logs.extend(apply_heavy_hit_cooldown_effect(target, keep_card_id=keep_id))
            logs.append(
                f"{card.name} is on cooldown for {HEAVY_HIT_COOLDOWN_TURNS} turns."
            )
        if card.shields:
            logs.extend(apply_shield(caster))
        return logs

    if damage > 0:
        logs.extend(
            apply_damage(
                target,
                damage,
                players=players,
                source_frozen=source_frozen,
            )
        )
    else:
        logs.append(f"{card.name} has 0 damage — no damage to {target.name}.")
    if card.vampire:
        logs.extend(apply_vampire_mark(target, active))
    if heal > 0:
        logs.extend(apply_heal(caster, heal, source_frozen=source_frozen))
    elif damage > 0:
        logs.append("(This card has 0 heal — caster gains nothing.)")
    if card.heavy_hit:
        keep_id = card.id if target_idx == active else None
        logs.extend(apply_heavy_hit_cooldown_effect(target, keep_card_id=keep_id))
        logs.append(
            f"{card.name} is on cooldown for {HEAVY_HIT_COOLDOWN_TURNS} turns."
        )
    if card.shields:
        logs.extend(apply_shield(caster))
    if card.poisons and target.alive:
        poison_damage = poison_tick_damage(damage)
        if source_frozen:
            poison_damage = (poison_damage + 1) // 2
        logs.extend(apply_poison(target, poison_damage))
    return logs


def apply_shield(caster: Player) -> list[str]:
    if caster.freeze_skip_turns > 0:
        return [f"{caster.name}'s Freeze prevents their Shield from working."]
    caster.shield_charges = 1
    try:
        from crash_out_sfx import SFX_SHIELD, play_sfx

        play_sfx(SFX_SHIELD)
    except Exception:
        pass
    return [f"{caster.name} gains Shield — the next damage against them is blocked."]


def apply_poison(
    target: Player,
    damage_per_tick: int,
    *,
    turns: int = POISON_DURATION_TURNS,
) -> list[str]:
    if damage_per_tick <= 0 or turns <= 0:
        return []
    target.poisons.append(
        ActivePoison(damage_per_tick=damage_per_tick, turns_left=turns)
    )
    try:
        from crash_out_sfx import SFX_POISON, play_sfx

        play_sfx(SFX_POISON)
    except Exception:
        pass
    return [
        f"{target.name} is poisoned — {damage_per_tick} damage at the start of "
        f"their turn for {turns} turns (ignores Shield)."
    ]


def tick_poisons_on_turn_start(
    player: Player,
    players: list[Player] | None = None,
) -> list[str]:
    """Apply poison DoT at the start of this player's turn (bypasses Shield)."""
    if not player.poisons:
        return []
    logs: list[str] = []
    remaining: list[ActivePoison] = []
    for effect in player.poisons:
        if effect.turns_left <= 0 or not player.alive:
            continue
        logs.append(f"Poison ticks on {player.name}...")
        logs.extend(
            apply_damage(
                player,
                effect.damage_per_tick,
                players=players,
                bypass_shield=True,
            )
        )
        effect.turns_left -= 1
        if effect.turns_left > 0 and player.alive:
            remaining.append(effect)
            logs.append(f"({effect.turns_left} poison turn(s) left.)")
        elif player.alive:
            logs.append(f"Poison on {player.name} wore off.")
    player.poisons = remaining
    return logs


def apply_heavy_hit_cooldown_effect(
    target: Player,
    *,
    keep_card_id: int | None = None,
) -> list[str]:
    target.last_card_id = None
    target.cooldown_clear_turns = COOLDOWN_CLEAR_TURNS
    for held in target.hand:
        if keep_card_id is not None and held.id == keep_card_id:
            continue
        held.cooldown_remaining = 0
    try:
        from crash_out_sfx import SFX_HEAVY_HIT, play_sfx

        play_sfx(SFX_HEAVY_HIT)
    except Exception:
        pass
    return [
        f"{target.name}'s cooldowns are cleared for {COOLDOWN_CLEAR_TURNS} turns "
        "(Heavy Hit)."
    ]


def tick_turn_cooldowns(players: list[Player], ending_idx: int) -> list[str]:
    logs: list[str] = []
    player = players[ending_idx]
    logs.extend(tick_vampire_marks(player))
    if player.cooldown_clear_turns > 0:
        player.cooldown_clear_turns -= 1
        if player.cooldown_clear_turns <= 0:
            player.cooldown_clear_turns = 0
            logs.append(f"{player.name}'s Heavy Hit cooldown relief ended.")
            try:
                from crash_out_sfx import SFX_RELIEF_END, play_sfx

                play_sfx(SFX_RELIEF_END)
            except Exception:
                pass
    for held in player.hand:
        if held.cooldown_remaining <= 0:
            continue
        held.cooldown_remaining -= 1
        if held.cooldown_remaining <= 0 and held.heavy_hit:
            logs.append(f"{player.name}'s Heavy Hit is ready.")
            try:
                from crash_out_sfx import SFX_HH_READY, play_sfx

                play_sfx(SFX_HH_READY)
            except Exception:
                pass
    for card_id, turns_left in list(player.freeze_cooldown_turns.items()):
        if turns_left <= 1:
            del player.freeze_cooldown_turns[card_id]
            logs.append(f"{player.name}'s Freeze is ready.")
        else:
            player.freeze_cooldown_turns[card_id] = turns_left - 1
    logs.extend(tick_freeze_on_turn_end(players, ending_idx))
    return logs


def cancel_freeze_for_lava(
    target: Player,
    players: list[Player],
    *,
    current_turn_idx: int,
) -> list[str]:
    """Clear lava marks and any Freeze status on a player with lava-marked cards."""
    for held in target.hand:
        held.lava_marked = False
    if target.freeze_skip_turns <= 0 and not target.freeze_sources:
        return []

    target.freeze_skip_turns = 0
    for source in target.freeze_sources:
        if not 0 <= source.source_idx < len(players):
            continue
        caster = players[source.source_idx]
        caster.freeze_card_cooling_ids.discard(source.card_id)
        caster.freeze_cooldown_turns[source.card_id] = (
            2 if source.source_idx == current_turn_idx else 1
        )
    target.freeze_sources.clear()
    return [f"{target.name}'s Freeze is removed by Floor is Lava."]


def tick_freeze_on_turn_end(
    players: list[Player],
    target_idx: int,
) -> list[str]:
    """Consume a frozen turn after the affected player finishes their turn."""
    target = players[target_idx]
    if target.freeze_skip_turns <= 0:
        return []
    target.freeze_skip_turns -= 1
    if target.freeze_skip_turns > 0:
        return []

    for source in target.freeze_sources:
        if not 0 <= source.source_idx < len(players):
            continue
        caster = players[source.source_idx]
        caster.freeze_card_cooling_ids.discard(source.card_id)
        caster.freeze_cooldown_turns[source.card_id] = 1
    target.freeze_sources.clear()
    return [f"{target.name} is no longer frozen."]


def steal_applies(
    card: Card,
    players: list[Player],
    active: int,
    target_idx: int,
) -> bool:
    if not card.steals or target_idx == active:
        return False
    if players[active].is_bot or players[target_idx].is_bot:
        return False
    return True


def random_steal_index(hand: list[Card]) -> int:
    if not hand:
        return 0
    return random.randrange(len(hand))


def resolve_steal(
    card: Card,
    players: list[Player],
    active: int,
    target_idx: int,
    borrows: list[ActiveBorrow],
) -> list[str]:
    if not steal_applies(card, players, active, target_idx):
        return []
    victim = players[target_idx]
    if not victim.hand:
        try:
            from crash_out_sfx import SFX_STEAL_FAIL, play_sfx

            play_sfx(SFX_STEAL_FAIL)
        except Exception:
            pass
        return [f"{victim.name} has no cards to steal."]
    steal_idx = random_steal_index(victim.hand)
    return apply_steal(players, active, target_idx, steal_idx, borrows)


def apply_steal(
    players: list[Player],
    thief_idx: int,
    victim_idx: int,
    hand_index: int,
    borrows: list[ActiveBorrow],
) -> list[str]:
    logs: list[str] = []
    thief = players[thief_idx]
    victim = players[victim_idx]
    if not victim.hand:
        try:
            from crash_out_sfx import SFX_STEAL_FAIL, play_sfx

            play_sfx(SFX_STEAL_FAIL)
        except Exception:
            pass
        logs.append(f"{victim.name} has no cards to steal.")
        return logs
    hand_index = max(0, min(len(victim.hand) - 1, hand_index))
    stolen = victim.hand.pop(hand_index)
    stolen.borrowed_from = victim_idx
    thief.hand.append(stolen)
    borrows.append(
        ActiveBorrow(
            card=stolen,
            owner_idx=victim_idx,
            thief_idx=thief_idx,
        )
    )
    try:
        from crash_out_sfx import SFX_STEAL, play_sfx

        play_sfx(SFX_STEAL)
    except Exception:
        pass
    logs.append(
        f"{thief.name} steals {stolen.name} from {victim.name} "
        f"(returns after {BORROW_TURNS - 1} more of {thief.name}'s turns)"
    )
    return logs


def return_expired_borrows(
    players: list[Player],
    ending_player_idx: int,
    borrows: list[ActiveBorrow],
) -> tuple[list[ActiveBorrow], list[str]]:
    logs: list[str] = []
    still_active: list[ActiveBorrow] = []
    returned = False
    for borrow in borrows:
        if borrow.thief_idx != ending_player_idx:
            still_active.append(borrow)
            continue
        borrow.turns_left -= 1
        if borrow.turns_left <= 0:
            thief = players[borrow.thief_idx]
            owner = players[borrow.owner_idx]
            if borrow.card in thief.hand:
                thief.hand.remove(borrow.card)
            borrow.card.borrowed_from = None
            owner.hand.append(borrow.card)
            logs.append(f"{borrow.card.name} returns to {owner.name}'s hand.")
            returned = True
        else:
            still_active.append(borrow)
    if returned:
        try:
            from crash_out_sfx import SFX_BORROW_RETURN, play_sfx

            play_sfx(SFX_BORROW_RETURN)
        except Exception:
            pass
    return still_active, logs


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


def first_living_opponent(players: list[Player], active: int) -> int | None:
    for i, p in enumerate(players):
        if i != active and p.alive:
            return i
    return None


def bot_choose_play(
    players: list[Player],
    active: int,
    starting_hp: int,
) -> tuple[Card, int, str] | None:
    bot = players[active]
    playable = bot.playable_cards()
    if not playable:
        return None

    foe = first_living_opponent(players, active)
    if foe is None:
        return playable[0], active, "no opponents left"

    foe_hp = players[foe].hp
    half = max(1, starting_hp // 2)
    wants_heal = bot.hp <= half

    lethal = [c for c in playable if not c.heal_any and c.damage >= foe_hp]
    if lethal:
        card = max(lethal, key=lambda c: c.damage)
        return (
            card,
            foe,
            f"bot at {bot.hp} HP — finishing blow ({card.damage} >= {foe_hp})",
        )

    healers = [c for c in playable if c.heal > 0 or c.heal_any]
    attackers = [c for c in playable if not c.heal_any and c.damage > 0]

    if wants_heal and healers:
        card = max(healers, key=lambda c: c.heal)
        return card, active, f"bot at {bot.hp} HP (<= {half}) — healing"

    if attackers:
        card = max(attackers, key=lambda c: c.damage)
        reason = (
            f"bot at {bot.hp} HP (> {half}) — attacking"
            if not wants_heal
            else f"bot at {bot.hp} HP — no heal card ready, attacking"
        )
        return card, foe, reason

    card = max(playable, key=lambda c: c.heal)
    return card, active, f"bot at {bot.hp} HP — healing with {card.name}"


def describe_target(
    card: Card,
    players: list[Player],
    active: int,
    target_idx: int,
) -> str:
    who = players[target_idx].name
    if card.heal_any:
        if target_idx == active:
            return who + " (heal self)"
        return who + " (heal them only)"
    if target_idx == active:
        if card.shields:
            return who + " (gain Shield; no damage or healing)"
        return who + " (self — heal yourself)"
    if card.steals:
        return who + " (damage them + heal you + steal 1 card)"
    if card.heavy_hit:
        if target_idx == active:
            return who + " (self — +50% heal, 2-turn cooldown, clears your cooldowns 2 turns)"
        return who + " (damage them + heal you +50%, 2-turn cooldown, clears their cooldowns 2 turns)"
    if card.shields:
        return who + " (no damage or healing + gain Shield)"
    if card.poisons:
        return who + " (damage them + Poison DoT)"
    return who + " (damage them + heal you)"
