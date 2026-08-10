import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from parapara_anime import (
    AnimationDialog,
    AnimationFrame,
    build_sprite_sheet,
    calculate_frame_rects,
)


class CalculateFrameRectsTests(unittest.TestCase):
    def test_one_by_five_is_five_horizontal_frames(self) -> None:
        self.assertEqual(
            calculate_frame_rects(10, 6, 1, 5),
            [
                (0, 0, 2, 6),
                (2, 0, 2, 6),
                (4, 0, 2, 6),
                (6, 0, 2, 6),
                (8, 0, 2, 6),
            ],
        )

    def test_two_by_five_is_ten_row_major_frames(self) -> None:
        rects = calculate_frame_rects(10, 6, 2, 5)

        self.assertEqual(len(rects), 10)
        self.assertEqual(rects[:5], [(column * 2, 0, 2, 3) for column in range(5)])
        self.assertEqual(rects[5:], [(column * 2, 3, 2, 3) for column in range(5)])

    def test_uneven_dimensions_keep_all_pixels(self) -> None:
        self.assertEqual(
            calculate_frame_rects(5, 5, 2, 2),
            [(0, 0, 2, 2), (2, 0, 3, 2), (0, 2, 2, 3), (2, 2, 3, 3)],
        )


class AddSpriteSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.image_path = os.path.join(self.temp_dir.name, "sheet.png")
        image = QImage(10, 6, QImage.Format_ARGB32)
        image.fill(QColor("red"))
        self.assertTrue(image.save(self.image_path))
        self.dialog = AnimationDialog()

    def tearDown(self) -> None:
        self.dialog.close()
        self.temp_dir.cleanup()

    def test_default_one_by_one_keeps_image_as_one_frame(self) -> None:
        self.dialog.add_image_files([self.image_path])

        self.assertEqual(len(self.dialog.frames), 1)
        self.assertEqual(self.dialog.frames[0].pixmap.size().toTuple(), (10, 6))
        self.assertEqual(self.dialog.frames[0].display_name, "sheet.png")

    def test_two_by_five_adds_ten_frames_in_row_major_order(self) -> None:
        self.dialog.sprite_rows_spin.setValue(2)
        self.dialog.sprite_columns_spin.setValue(5)

        self.dialog.add_image_files([self.image_path])

        self.assertEqual(len(self.dialog.frames), 10)
        self.assertTrue(
            all(frame.pixmap.size().toTuple() == (2, 3) for frame in self.dialog.frames)
        )
        self.assertEqual(self.dialog.frames[0].display_name, "sheet.png [1,1]")
        self.assertEqual(self.dialog.frames[4].display_name, "sheet.png [1,5]")
        self.assertEqual(self.dialog.frames[5].display_name, "sheet.png [2,1]")
        self.assertEqual(self.dialog.current_index, 0)
        self.assertEqual(self.dialog.export_rows_spin.value(), 2)
        self.assertEqual(self.dialog.export_columns_spin.value(), 5)

    def test_build_sprite_sheet_uses_row_major_order_and_transparent_remainder(self) -> None:
        frames = []
        for color_name in ("red", "green", "blue"):
            image = QImage(2, 2, QImage.Format_ARGB32)
            image.fill(QColor(color_name))
            frames.append(
                AnimationFrame(
                    path=color_name,
                    pixmap=QPixmap.fromImage(image),
                    wait_ms=200,
                )
            )

        sheet = build_sprite_sheet(frames, 2, 2).toImage()

        self.assertEqual(sheet.size().toTuple(), (4, 4))
        self.assertEqual(sheet.pixelColor(0, 0), QColor("red"))
        self.assertEqual(sheet.pixelColor(2, 0), QColor("green"))
        self.assertEqual(sheet.pixelColor(0, 2), QColor("blue"))
        self.assertEqual(sheet.pixelColor(2, 2).alpha(), 0)

    def test_build_sprite_sheet_rejects_too_few_cells(self) -> None:
        self.dialog.add_image_files([self.image_path])
        frames = self.dialog.frames * 2

        with self.assertRaisesRegex(ValueError, "出力枠が不足"):
            build_sprite_sheet(frames, 1, 1)

    def test_build_sprite_sheet_centers_smaller_frames(self) -> None:
        large_image = QImage(4, 4, QImage.Format_ARGB32)
        large_image.fill(QColor("red"))
        small_image = QImage(2, 2, QImage.Format_ARGB32)
        small_image.fill(QColor("blue"))
        frames = [
            AnimationFrame("large", QPixmap.fromImage(large_image), 200),
            AnimationFrame("small", QPixmap.fromImage(small_image), 200),
        ]

        sheet = build_sprite_sheet(frames, 1, 2).toImage()

        self.assertEqual(sheet.size().toTuple(), (8, 4))
        self.assertEqual(sheet.pixelColor(4, 0).alpha(), 0)
        self.assertEqual(sheet.pixelColor(5, 1), QColor("blue"))

    def test_export_sprite_sheet_saves_the_selected_image(self) -> None:
        self.dialog.add_image_files([self.image_path])
        output_without_extension = os.path.join(self.temp_dir.name, "exported_sheet")

        with patch(
            "parapara_anime.QFileDialog.getSaveFileName",
            return_value=(output_without_extension, ""),
        ):
            self.dialog.export_sprite_sheet()

        output_path = f"{output_without_extension}.png"
        self.assertTrue(os.path.isfile(output_path))
        self.assertEqual(QImage(output_path).size().toTuple(), (10, 6))


if __name__ == "__main__":
    unittest.main()
