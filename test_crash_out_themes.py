import unittest

from crash_out_themes import CARD_STYLES, find_theme_by_name, theme_names


class ThemePresetTests(unittest.TestCase):
    def test_new_presets_are_selectable_and_have_unique_names(self) -> None:
        names = theme_names()
        self.assertEqual(len(names), len(set(names)))
        for name in (
            "Desert Mirage",
            "Moonlit Library",
            "Coral Reef",
            "Bubblegum Arcade",
        ):
            with self.subTest(name=name):
                theme = find_theme_by_name(name)
                self.assertIsNotNone(theme)
                assert theme is not None
                self.assertIn(theme.card_style, CARD_STYLES)
                self.assertEqual(theme.name, name)


if __name__ == "__main__":
    unittest.main()
