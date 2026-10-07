import unittest

from cascade_windows.geometry import (
    ANCHOR_BOTTOM_LEFT,
    ANCHOR_TOP_LEFT,
    plan_layout,
    split_into_rounds,
    usable_area,
)
from cascade_windows.model import Rect
from cascade_windows.settings import Settings

WORKAREA = Rect(0, 0, 1920, 1080)


class UsableAreaTest(unittest.TestCase):
    def test_default_margin_is_twenty_pixels_on_every_side(self):
        self.assertEqual(usable_area(WORKAREA, Settings()), Rect(20, 20, 1880, 1040))

    def test_margins_are_independent(self):
        settings = Settings(margin_top=10, margin_right=30, margin_bottom=50, margin_left=70)
        self.assertEqual(usable_area(WORKAREA, settings), Rect(70, 10, 1820, 1020))

    def test_area_never_collapses_to_nothing(self):
        settings = Settings(margin_left=5000, margin_right=5000)
        self.assertGreaterEqual(usable_area(WORKAREA, settings).width, 1)


class AnchoredTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.area = usable_area(WORKAREA, self.settings)

    def test_all_windows_share_the_bottom_left_corner(self):
        placements = plan_layout(4, self.area, self.settings)
        self.assertEqual(len(placements), 4)
        for placement in placements:
            self.assertEqual(placement.anchor, ANCHOR_BOTTOM_LEFT)
            self.assertEqual(placement.rect.x, self.area.x)
            self.assertEqual(placement.rect.bottom, self.area.bottom)

    def test_back_window_touches_top_margin_and_front_window_touches_right_margin(self):
        placements = plan_layout(4, self.area, self.settings)
        self.assertEqual(placements[0].rect.y, self.area.y)
        self.assertEqual(placements[-1].rect.right, self.area.right)

    def test_each_window_is_one_step_lower_and_one_step_further_right(self):
        placements = plan_layout(4, self.area, self.settings)
        for back, front in zip(placements, placements[1:]):
            self.assertEqual(front.rect.y - back.rect.y, self.settings.step_y)
            self.assertEqual(front.rect.right - back.rect.right, self.settings.step_x)

    def test_exact_numbers_for_three_windows(self):
        placements = plan_layout(3, self.area, self.settings)
        self.assertEqual(placements[0].rect, Rect(20, 20, 1820, 1040))
        self.assertEqual(placements[1].rect, Rect(20, 50, 1850, 1010))
        self.assertEqual(placements[2].rect, Rect(20, 80, 1880, 980))

    def test_steps_are_independent(self):
        settings = Settings(step_x=10, step_y=40)
        placements = plan_layout(3, usable_area(WORKAREA, settings), settings)
        self.assertEqual(placements[1].rect.y - placements[0].rect.y, 40)
        self.assertEqual(placements[1].rect.right - placements[0].rect.right, 10)

    def test_single_window_fills_the_usable_area(self):
        placements = plan_layout(1, self.area, self.settings)
        self.assertEqual(placements[0].rect, self.area)

    def test_no_windows_gives_no_placements(self):
        self.assertEqual(plan_layout(0, self.area, self.settings), [])


class WrapTest(unittest.TestCase):
    def test_fitting_windows_use_one_round(self):
        settings = Settings()
        area = usable_area(WORKAREA, settings)
        self.assertEqual(split_into_rounds(10, area, settings), [10])

    def test_too_many_windows_wrap_into_more_rounds(self):
        settings = Settings(step_y=100)
        area = usable_area(WORKAREA, settings)
        rounds = split_into_rounds(30, area, settings)
        self.assertGreater(len(rounds), 1)
        self.assertEqual(sum(rounds), 30)

    def test_wrapped_windows_never_get_smaller_than_the_minimum_size(self):
        settings = Settings(step_y=100)
        area = usable_area(WORKAREA, settings)
        for placement in plan_layout(30, area, settings):
            self.assertGreaterEqual(placement.rect.width, settings.min_width)
            self.assertGreaterEqual(placement.rect.height, settings.min_height)

    def test_every_round_starts_a_little_further_in(self):
        settings = Settings(step_y=100, wrap_offset=12)
        area = usable_area(WORKAREA, settings)
        rounds = split_into_rounds(30, area, settings)
        placements = plan_layout(30, area, settings)
        first_of_second_round = placements[rounds[0]]
        self.assertEqual(first_of_second_round.rect.x, area.x + 12)
        self.assertEqual(first_of_second_round.rect.y, area.y + 12)

    def test_disabling_wrap_compresses_the_steps_instead(self):
        settings = Settings(step_y=100, wrap_enabled=False)
        area = usable_area(WORKAREA, settings)
        placements = plan_layout(30, area, settings)
        self.assertEqual(len(placements), 30)
        self.assertEqual(placements[0].rect.y, area.y)
        self.assertEqual(placements[-1].rect.right, area.right)
        for placement in placements:
            self.assertGreaterEqual(placement.rect.height, settings.min_height)


class FitPercentFixedTest(unittest.TestCase):
    def test_fit_gives_all_windows_the_same_largest_size(self):
        settings = Settings(size_mode="fit")
        area = usable_area(WORKAREA, settings)
        placements = plan_layout(3, area, settings)
        sizes = {(p.rect.width, p.rect.height) for p in placements}
        self.assertEqual(sizes, {(1880 - 60, 1040 - 60)})
        self.assertEqual(placements[0].rect.x, area.x)
        self.assertEqual(placements[0].rect.y, area.y)
        self.assertEqual(placements[-1].rect.right, area.right)
        self.assertEqual(placements[-1].rect.bottom, area.bottom)
        self.assertEqual(placements[0].anchor, ANCHOR_TOP_LEFT)

    def test_percent_uses_the_given_share_of_the_area(self):
        settings = Settings(size_mode="percent", percent_width=50, percent_height=50)
        area = usable_area(WORKAREA, settings)
        placements = plan_layout(2, area, settings)
        self.assertEqual((placements[0].rect.width, placements[0].rect.height), (940, 520))
        self.assertEqual(placements[1].rect.x - placements[0].rect.x, 30)

    def test_fixed_size_is_limited_to_the_area(self):
        settings = Settings(size_mode="fixed", fixed_width=5000, fixed_height=400)
        area = usable_area(WORKAREA, settings)
        placement = plan_layout(1, area, settings)[0]
        self.assertEqual((placement.rect.width, placement.rect.height), (area.width, 400))

    def test_fixed_windows_wrap_when_the_cascade_leaves_the_area(self):
        settings = Settings(size_mode="fixed", fixed_width=900, fixed_height=900)
        area = usable_area(WORKAREA, settings)
        placements = plan_layout(10, area, settings)
        for placement in placements:
            self.assertLessEqual(placement.rect.bottom, area.bottom)
            self.assertLessEqual(placement.rect.right, area.right)


if __name__ == "__main__":
    unittest.main()
