import unittest

from crash_out_window import format_elapsed_time

from crash_out_party import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    TETROMINOES,
    apply_placement,
    clear_completed_rows,
    conflict_groups,
    drop_piece,
    legal_columns,
    legal_positions,
    place_piece,
    rank_points,
    rotations,
    starting_tiles,
)


class PartyBoardTests(unittest.TestCase):
    def test_rotations_are_unique_and_keep_four_cells(self) -> None:
        for piece in TETROMINOES:
            orientations = rotations(piece)
            self.assertEqual(len(orientations), len(set(orientations)))
            self.assertTrue(all(len(shape) == 4 for shape in orientations))

    def test_piece_drops_to_floor_and_stops_above_existing_tile(self) -> None:
        shape = rotations("O")[0]
        cells = drop_piece(set(), shape, 4)
        self.assertEqual(cells, {(4, 4), (5, 4), (4, 5), (5, 5)})
        raised = drop_piece(cells, shape, 4)
        self.assertEqual(raised, {(4, 2), (5, 2), (4, 3), (5, 3)})

    def test_legal_columns_cover_entire_board_without_frontier_limit(self) -> None:
        columns = legal_columns(set(), rotations("I")[0])
        self.assertEqual(columns, list(range(BOARD_WIDTH - 3)))

    def test_legal_columns_allow_placement_behind_progress(self) -> None:
        owners = {(10, 5): 0}
        columns = legal_columns(
            set(owners),
            rotations("O")[0],
            owners=owners,
            player_idx=0,
        )
        self.assertIn(8, columns)

    def test_legal_positions_offer_rows_and_direct_placement(self) -> None:
        owners = {(0, 0): 0}
        shape = rotations("O")[0]
        positions = legal_positions(
            shape,
            owners=owners,
            player_idx=0,
        )
        self.assertIn((0, 0), positions)
        self.assertIn((0, 1), positions)
        cells = place_piece(
            shape,
            0,
            1,
            owners=owners,
            player_idx=0,
        )
        self.assertEqual(cells, {(0, 1), (1, 1), (0, 2), (1, 2)})

    def test_starting_tiles_use_requested_rows_in_player_order(self) -> None:
        self.assertEqual(
            starting_tiles(4),
            {(0, 0): 0, (0, 2): 1, (0, 3): 2, (0, 5): 3},
        )
        self.assertEqual(
            starting_tiles(2),
            {(0, 0): 0, (0, 2): 1},
        )

    def test_new_piece_stops_at_its_owners_tiles(self) -> None:
        shape = rotations("O")[0]
        for player_idx, row in enumerate((0, 2, 3, 5)):
            with self.subTest(row=row):
                owners = {(0, row): player_idx}
                columns = legal_columns(
                    set(owners),
                    shape,
                    owners=owners,
                    player_idx=player_idx,
                )
                self.assertIn(1, columns)
                for column in columns:
                    cells = drop_piece(
                        set(owners),
                        shape,
                        column,
                        owners=owners,
                        player_idx=player_idx,
                    )
                    self.assertTrue(
                        any(
                            owners.get(neighbor) == player_idx
                            for x, y in cells
                            for neighbor in (
                                (x - 1, y),
                                (x + 1, y),
                                (x, y - 1),
                                (x, y + 1),
                            )
                        )
                    )

    def test_piece_can_land_over_and_take_over_another_players_tile(self) -> None:
        owners = {(4, 4): 1, (4, 5): 0}
        shape = rotations("O")[0]
        cells = drop_piece(
            set(owners),
            shape,
            4,
            owners=owners,
            player_idx=0,
        )

        self.assertIn((4, 4), cells)
        self.assertEqual(min(y for _, y in cells), 3)
        apply_placement(owners, cells, 0)
        self.assertEqual(owners[(4, 4)], 0)
        self.assertEqual(owners[(4, 5)], 0)

    def test_piece_without_a_connected_landing_is_illegal(self) -> None:
        owners = {(0, 0): 0}
        with self.assertRaises(ValueError):
            drop_piece(
                set(owners),
                rotations("O")[0],
                3,
                owners=owners,
                player_idx=0,
            )

    def test_overlapping_cells_are_grouped_for_one_duel(self) -> None:
        groups = conflict_groups(
            {
                0: {(1, 1), (2, 1), (3, 1)},
                1: {(2, 1), (3, 1)},
                2: {(3, 1)},
            }
        )
        self.assertEqual(
            groups,
            {
                frozenset({0, 1, 2}): {(3, 1)},
                frozenset({0, 1}): {(2, 1)},
            },
        )

    def test_complete_rows_clear_and_above_rows_fall(self) -> None:
        owners = {(x, BOARD_HEIGHT - 1): x % 2 for x in range(BOARD_WIDTH)}
        owners[(0, BOARD_HEIGHT - 2)] = 3
        result = clear_completed_rows(owners)
        self.assertEqual(result[(0, BOARD_HEIGHT - 1)], 3)
        self.assertEqual(len(result), 1)

    def test_rank_points_preserve_ties(self) -> None:
        self.assertEqual(rank_points([(4,), (2,), (2,), (1,)]), [5, 3, 3, 0])
        self.assertEqual(
            rank_points([(4,), (2,), (2,), (1,)], higher_is_better=False),
            [0, 3, 3, 5],
        )

    def test_elapsed_time_formats_minutes_and_hours(self) -> None:
        self.assertEqual(format_elapsed_time(0), "00:00")
        self.assertEqual(format_elapsed_time(59), "00:59")
        self.assertEqual(format_elapsed_time(125), "02:05")
        self.assertEqual(format_elapsed_time(3661), "01:01:01")


if __name__ == "__main__":
    unittest.main()
