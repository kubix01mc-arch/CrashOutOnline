"""Board rules for the local Party race mode."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

BOARD_WIDTH = 30
BOARD_HEIGHT = 6
RANK_POINTS = (5, 3, 2, 0)
STARTING_ROWS = (0, 2, 3, 5)

TETROMINOES: dict[str, tuple[tuple[int, int], ...]] = {
    "I": ((0, 0), (1, 0), (2, 0), (3, 0)),
    "O": ((0, 0), (1, 0), (0, 1), (1, 1)),
    "T": ((0, 0), (1, 0), (2, 0), (1, 1)),
    "S": ((1, 0), (2, 0), (0, 1), (1, 1)),
    "Z": ((0, 0), (1, 0), (1, 1), (2, 1)),
    "J": ((0, 0), (0, 1), (1, 1), (2, 1)),
    "L": ((2, 0), (0, 1), (1, 1), (2, 1)),
}

Cell = tuple[int, int]


def starting_tiles(player_count: int) -> dict[Cell, int]:
    """Place racers in column one at rows 1, 3, 4, and 6, in that order."""
    if not 2 <= player_count <= len(STARTING_ROWS):
        raise ValueError("Party mode requires two to four players.")
    return {(0, STARTING_ROWS[index]): index for index in range(player_count)}


def _normalize_shape(cells: Iterable[Cell]) -> tuple[Cell, ...]:
    cells = tuple(cells)
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    return tuple(sorted((x - min_x, y - min_y) for x, y in cells))


def rotations(piece: str) -> tuple[tuple[Cell, ...], ...]:
    """Return unique clockwise orientations, normalized to the top-left."""
    shape = _normalize_shape(TETROMINOES[piece])
    result: list[tuple[Cell, ...]] = []
    for _ in range(4):
        if shape not in result:
            result.append(shape)
        shape = _normalize_shape((y, -x) for x, y in shape)
    return tuple(result)


def legal_columns(
    occupied: set[Cell],
    shape: tuple[Cell, ...],
    *,
    owners: Mapping[Cell, int] | None = None,
    player_idx: int | None = None,
) -> list[int]:
    """Find every column where the piece can land connected to the racer."""
    width = max(x for x, _ in shape) + 1
    result: list[int] = []
    for column in range(BOARD_WIDTH - width + 1):
        try:
            drop_piece(
                occupied,
                shape,
                column,
                owners=owners,
                player_idx=player_idx,
            )
        except ValueError:
            continue
        result.append(column)
    return result


def legal_positions(
    shape: tuple[Cell, ...],
    *,
    owners: Mapping[Cell, int],
    player_idx: int,
) -> list[tuple[int, int]]:
    """Return board positions where a piece fits and touches its player's tiles."""
    width = max(x for x, _ in shape) + 1
    height = max(y for _, y in shape) + 1
    return [
        (column, row)
        for row in range(BOARD_HEIGHT - height + 1)
        for column in range(BOARD_WIDTH - width + 1)
        if _connects_to_player(
            {
                (column + x, row + y)
                for x, y in shape
            },
            owners,
            player_idx,
        )
    ]


def place_piece(
    shape: tuple[Cell, ...],
    column: int,
    row: int,
    *,
    owners: Mapping[Cell, int],
    player_idx: int,
) -> set[Cell]:
    """Place a piece directly at a chosen row and column, allowing takeover."""
    width = max(x for x, _ in shape) + 1
    height = max(y for _, y in shape) + 1
    if (
        column < 0
        or row < 0
        or column + width > BOARD_WIDTH
        or row + height > BOARD_HEIGHT
    ):
        raise ValueError("Piece does not fit on the board.")
    cells = {(column + x, row + y) for x, y in shape}
    if not _connects_to_player(cells, owners, player_idx):
        raise ValueError("Piece must connect to one of this player's tiles.")
    return cells


def _connects_to_player(
    cells: set[Cell], owners: Mapping[Cell, int], player_idx: int
) -> bool:
    return any(
        owners.get((x, y)) == player_idx
        or owners.get(neighbor) == player_idx
        for x, y in cells
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
    )


def drop_piece(
    occupied: set[Cell],
    shape: tuple[Cell, ...],
    column: int,
    *,
    owners: Mapping[Cell, int] | None = None,
    player_idx: int | None = None,
) -> set[Cell]:
    """Drop a piece until it connects, taking ownership of tiles it overlaps."""
    if (owners is None) != (player_idx is None):
        raise ValueError("Both owners and player_idx are required for connected drops.")
    width = max(x for x, _ in shape) + 1
    height = max(y for _, y in shape) + 1
    if column < 0 or column + width > BOARD_WIDTH or height > BOARD_HEIGHT:
        raise ValueError("Piece does not fit on the board.")

    def connects_to_player(cells: set[Cell]) -> bool:
        if owners is None or player_idx is None:
            return False
        return any(
            owners.get((x, y)) == player_idx
            or owners.get(neighbor) == player_idx
            for x, y in cells
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        )

    offset_y = 0
    while True:
        cells = {(column + x, offset_y + y) for x, y in shape}
        if any(cell in occupied for cell in cells):
            if owners is None:
                return cells
            if connects_to_player(cells):
                return cells
            raise ValueError("Piece cannot connect to one of this player's tiles.")
        if connects_to_player(cells):
            return cells
        next_cells = {(column + x, offset_y + y + 1) for x, y in shape}
        if any(y >= BOARD_HEIGHT for _, y in next_cells):
            if owners is not None:
                raise ValueError("Piece cannot connect to one of this player's tiles.")
            return cells
        if any(cell in occupied for cell in next_cells):
            if owners is None:
                return cells
            if connects_to_player(next_cells):
                return next_cells
            raise ValueError("Piece cannot connect to one of this player's tiles.")
        offset_y += 1


def apply_placement(
    owners: dict[Cell, int], cells: Iterable[Cell], player_idx: int
) -> None:
    """Assign placed cells to the new player, replacing any previous owner."""
    for cell in cells:
        owners[cell] = player_idx



def conflict_groups(
    placements: Mapping[int, set[Cell]],
) -> dict[frozenset[int], set[Cell]]:
    """Group contested cells by the exact set of players that overlapped there."""
    contenders: dict[Cell, set[int]] = defaultdict(set)
    for player_idx, cells in placements.items():
        for cell in cells:
            contenders[cell].add(player_idx)

    groups: dict[frozenset[int], set[Cell]] = defaultdict(set)
    for cell, players in contenders.items():
        if len(players) > 1:
            groups[frozenset(players)].add(cell)
    return dict(groups)


def clear_completed_rows(
    owners: Mapping[Cell, int],
) -> dict[Cell, int]:
    """Clear complete rows and let the blocks above fall into the gaps."""
    full_rows = {
        y
        for y in range(BOARD_HEIGHT)
        if all((x, y) in owners for x in range(BOARD_WIDTH))
    }
    shifted: dict[Cell, int] = {}
    for (x, y), owner in owners.items():
        if y not in full_rows:
            new_y = y + sum(row > y for row in full_rows)
            shifted[(x, new_y)] = owner
    return shifted


def rank_points(
    rank_keys: list[tuple[int, ...]], *, higher_is_better: bool = True
) -> list[int]:
    """Award 5/3/2/0 points, keeping tied players at the same rank."""
    order = sorted(
        range(len(rank_keys)),
        key=lambda index: rank_keys[index],
        reverse=higher_is_better,
    )
    points = [0] * len(rank_keys)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and rank_keys[order[end]] == rank_keys[order[start]]:
            end += 1
        rank_points = RANK_POINTS[min(start, len(RANK_POINTS) - 1)]
        for position in range(start, end):
            points[order[position]] = rank_points
        start = end
    return points
