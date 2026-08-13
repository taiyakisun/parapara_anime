from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PIL import Image
from PySide6.QtCore import Qt, QMimeData, QTimer
from PySide6.QtGui import QImage, QImageReader, QIntValidator, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class AnimationFrame:
    path: str
    pixmap: QPixmap
    wait_ms: int
    display_name: str = ""


def calculate_frame_rects(
    image_width: int,
    image_height: int,
    rows: int,
    columns: int,
) -> List[tuple[int, int, int, int]]:
    """画像全体を覆うフレーム矩形を行優先の順序で返す。"""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("画像サイズは 1 ピクセル以上である必要があります。")
    if rows <= 0 or columns <= 0:
        raise ValueError("縦と横の枚数は 1 以上である必要があります。")
    if rows > image_height or columns > image_width:
        raise ValueError("縦と横の枚数は画像のピクセル数以下にしてください。")

    rects: List[tuple[int, int, int, int]] = []
    for row in range(rows):
        top = row * image_height // rows
        bottom = (row + 1) * image_height // rows
        for column in range(columns):
            left = column * image_width // columns
            right = (column + 1) * image_width // columns
            rects.append((left, top, right - left, bottom - top))
    return rects


def build_sprite_sheet(
    frames: Sequence[AnimationFrame],
    rows: int,
    columns: int,
) -> QPixmap:
    """フレームを行優先で並べたスプライトシートを生成する。"""
    if not frames:
        raise ValueError("出力するフレームがありません。")
    if rows <= 0 or columns <= 0:
        raise ValueError("縦と横の枚数は 1 以上である必要があります。")
    if rows * columns < len(frames):
        raise ValueError(
            f"出力枠が不足しています。{len(frames)} フレーム以上になるように指定してください。"
        )
    if any(frame.pixmap.isNull() for frame in frames):
        raise ValueError("読み込めないフレームが含まれています。")

    cell_width = max(frame.pixmap.width() for frame in frames)
    cell_height = max(frame.pixmap.height() for frame in frames)
    sheet_width = cell_width * columns
    sheet_height = cell_height * rows
    if sheet_width * sheet_height > 100_000_000:
        raise ValueError("出力画像が大きすぎます。縦または横の枚数を小さくしてください。")

    sheet = QPixmap(sheet_width, sheet_height)
    if sheet.isNull():
        raise ValueError("スプライトシート用の画像を作成できませんでした。")
    sheet.fill(Qt.transparent)

    painter = QPainter(sheet)
    for frame_index, frame in enumerate(frames):
        row = frame_index // columns
        column = frame_index % columns
        x = column * cell_width + (cell_width - frame.pixmap.width()) // 2
        y = row * cell_height + (cell_height - frame.pixmap.height()) // 2
        painter.drawPixmap(x, y, frame.pixmap)
    painter.end()
    return sheet


def build_numbered_frame_paths(
    output_directory: str,
    base_name: str,
    frame_count: int,
) -> List[str]:
    """個別フレーム用の5刻みの出力パスを生成する。"""
    normalized_name = base_name.strip()
    if normalized_name.lower().endswith(".png"):
        normalized_name = normalized_name[:-4].rstrip()
    if not normalized_name:
        raise ValueError("ファイル名を入力してください。")
    if any(ord(character) < 32 or character in '<>:"/\\|?*' for character in normalized_name):
        raise ValueError('ファイル名に < > : " / \\ | ? * は使用できません。')
    if normalized_name.endswith((".", " ")):
        raise ValueError("ファイル名の末尾にピリオドや空白は使用できません。")
    if frame_count <= 0:
        raise ValueError("出力するフレームがありません。")

    return [
        os.path.join(output_directory, f"{frame_number:03d}_{normalized_name}.png")
        for frame_number in range(5, frame_count * 5 + 1, 5)
    ]


def save_animation_gif(
    frames: Sequence[AnimationFrame],
    output_path: str,
    loop: bool,
) -> None:
    """一覧順、待ち時間、ループ設定を反映したGIFを保存する。"""
    if not frames:
        raise ValueError("出力するフレームがありません。")
    if any(frame.pixmap.isNull() for frame in frames):
        raise ValueError("読み込めないフレームが含まれています。")
    if any(frame.wait_ms < 0 for frame in frames):
        raise ValueError("待ち時間は 0 ミリ秒以上にしてください。")
    if any(frame.wait_ms > 655_350 for frame in frames):
        raise ValueError("GIFの待ち時間は1フレームあたり655350ミリ秒以下にしてください。")

    canvas_width = max(frame.pixmap.width() for frame in frames)
    canvas_height = max(frame.pixmap.height() for frame in frames)
    if canvas_width > 65_535 or canvas_height > 65_535:
        raise ValueError("GIFの縦横サイズは65535ピクセル以下にしてください。")
    if canvas_width * canvas_height * len(frames) > 100_000_000:
        raise ValueError("GIFが大きすぎます。画像サイズまたはフレーム数を減らしてください。")

    gif_frames: List[Image.Image] = []
    for frame in frames:
        source = frame.pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
        image = Image.frombytes(
            "RGBA",
            (source.width(), source.height()),
            source.constBits().tobytes(),
            "raw",
            "RGBA",
            source.bytesPerLine(),
            1,
        )
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        position = (
            (canvas_width - image.width) // 2,
            (canvas_height - image.height) // 2,
        )
        canvas.alpha_composite(image, position)
        gif_frames.append(canvas)

    save_options = {
        "format": "GIF",
        "save_all": True,
        "append_images": gif_frames[1:],
        "duration": [frame.wait_ms for frame in frames],
        "disposal": 2,
        "optimize": False,
    }
    if loop:
        save_options["loop"] = 0
    gif_frames[0].save(output_path, **save_options)


class FrameTableWidget(QTableWidget):
    """Table widget that accepts file drops and emits events for Delete key presses."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["File", "Wait (ms)"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if self._has_image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = self._extract_paths(event.mimeData())
        if paths:
            self.parent().add_image_files(paths)  # type: ignore[attr-defined]
            event.acceptProposedAction()
        else:
            event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Delete and self.parent():
            self.parent().remove_selected_rows()  # type: ignore[attr-defined]
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _has_image_urls(mime_data: QMimeData) -> bool:
        if not mime_data.hasUrls():
            return False
        return any(FrameTableWidget._is_supported_image(url.toLocalFile()) for url in mime_data.urls())

    @staticmethod
    def _extract_paths(mime_data: QMimeData) -> List[str]:
        if not mime_data.hasUrls():
            return []
        paths = []
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if FrameTableWidget._is_supported_image(local_path):
                paths.append(local_path)
        return paths

    @staticmethod
    def _is_supported_image(path: str) -> bool:
        if not path:
            return False
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            return False
        supported = getattr(FrameTableWidget, "_supported_formats_cache", None)
        if supported is None:
            supported = {f".{fmt.data().decode().lower()}" for fmt in QImageReader.supportedImageFormats()}
            setattr(FrameTableWidget, "_supported_formats_cache", supported)
        return ext in supported


class AnimationDialog(QDialog):
    DEFAULT_WAIT_MS = 200

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Parapara Animator")
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(820, 520)

        self.frames: List[AnimationFrame] = []
        self.current_index: int = 0
        self.is_playing: bool = False
        self.current_pixmap: Optional[QPixmap] = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance_frame)

        self._build_ui()
        self._update_button_states()
        self._refresh_display()

    # UI construction -----------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QGridLayout(self)
        control_layout = QVBoxLayout()

        self.up_button = QPushButton("上へ")
        self.down_button = QPushButton("下へ")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.step_button = QPushButton("コマ送り")
        self.loop_checkbox = QCheckBox("ループ")

        for button in (self.up_button, self.down_button, self.start_button, self.stop_button, self.step_button):
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        control_layout.addWidget(self.up_button)
        control_layout.addWidget(self.down_button)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.step_button)
        control_layout.addWidget(self.loop_checkbox)
        control_layout.addStretch(1)

        self.table = FrameTableWidget(self)
        self.table.cellChanged.connect(self._handle_cell_changed)

        table_layout = QVBoxLayout()
        table_label = QLabel("読み込んでいる画像一覧とウェイトミリ秒")
        table_layout.addWidget(table_label)

        sprite_layout = QHBoxLayout()
        sprite_layout.addWidget(QLabel("読み込み時の分割:"))
        sprite_layout.addWidget(QLabel("縦（行）"))
        self.sprite_rows_spin = QSpinBox()
        self.sprite_rows_spin.setRange(1, 1000)
        self.sprite_rows_spin.setValue(1)
        sprite_layout.addWidget(self.sprite_rows_spin)
        sprite_layout.addWidget(QLabel("× 横（列）"))
        self.sprite_columns_spin = QSpinBox()
        self.sprite_columns_spin.setRange(1, 1000)
        self.sprite_columns_spin.setValue(1)
        sprite_layout.addWidget(self.sprite_columns_spin)
        sprite_layout.addStretch(1)
        table_layout.addLayout(sprite_layout)

        table_layout.addWidget(self.table)

        bulk_layout = QHBoxLayout()
        bulk_label = QLabel("待ち時間一括設定 (ms):")
        self.bulk_wait_input = QLineEdit()
        self.bulk_wait_input.setValidator(QIntValidator(0, 3_600_000, self))
        self.bulk_wait_input.setPlaceholderText("例: 200")
        self.bulk_apply_button = QPushButton("一括設定")
        bulk_layout.addWidget(bulk_label)
        bulk_layout.addWidget(self.bulk_wait_input)
        bulk_layout.addWidget(self.bulk_apply_button)
        table_layout.addLayout(bulk_layout)

        export_layout = QHBoxLayout()
        export_layout.addWidget(QLabel("シート出力:"))
        export_layout.addWidget(QLabel("縦"))
        self.export_rows_spin = QSpinBox()
        self.export_rows_spin.setRange(1, 1000)
        self.export_rows_spin.setValue(1)
        self.export_rows_spin.setToolTip("出力する行数")
        export_layout.addWidget(self.export_rows_spin)
        export_layout.addWidget(QLabel("× 横"))
        self.export_columns_spin = QSpinBox()
        self.export_columns_spin.setRange(1, 1000)
        self.export_columns_spin.setValue(1)
        self.export_columns_spin.setToolTip("出力する列数")
        export_layout.addWidget(self.export_columns_spin)
        self.export_button = QPushButton("保存")
        self.export_button.setToolTip("現在のフレームを1枚の画像として保存")
        export_layout.addWidget(self.export_button)
        table_layout.addLayout(export_layout)

        individual_export_layout = QHBoxLayout()
        individual_export_layout.addWidget(QLabel("個別PNG出力:"))
        self.individual_export_button = QPushButton("保存")
        self.individual_export_button.setToolTip(
            "ベース名を指定し、各フレームを005から5刻みの連番で保存"
        )
        individual_export_layout.addWidget(self.individual_export_button)
        individual_export_layout.addStretch(1)
        table_layout.addLayout(individual_export_layout)

        gif_export_layout = QHBoxLayout()
        gif_export_layout.addWidget(QLabel("GIFアニメ出力:"))
        self.gif_export_button = QPushButton("保存")
        self.gif_export_button.setToolTip(
            "一覧順、待ち時間、ループ設定を反映したGIFアニメーションを保存"
        )
        gif_export_layout.addWidget(self.gif_export_button)
        gif_export_layout.addStretch(1)
        table_layout.addLayout(gif_export_layout)

        self.display_label = QLabel()
        self.display_label.setMinimumSize(320, 240)
        self.display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.display_label.setAlignment(Qt.AlignCenter)
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 800)
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix("%")
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("表示倍率:"))
        zoom_layout.addWidget(self.zoom_spin)
        zoom_layout.addWidget(QLabel("透明部分の背景:"))
        self.preview_background_combo = QComboBox()
        self.preview_background_combo.addItem("黒", "black")
        self.preview_background_combo.addItem("白", "white")
        self.preview_background_combo.setToolTip("透明部分を確認するためのプレビュー背景色")
        zoom_layout.addWidget(self.preview_background_combo)
        zoom_layout.addStretch(1)

        display_layout = QVBoxLayout()
        display_layout.addWidget(self.display_label, 1)
        display_layout.addLayout(zoom_layout)

        main_layout.addLayout(control_layout, 0, 0)
        main_layout.addLayout(table_layout, 0, 1)
        main_layout.addLayout(display_layout, 0, 2)
        main_layout.setColumnStretch(1, 1)
        main_layout.setColumnStretch(2, 2)

        self.bulk_apply_button.clicked.connect(self._apply_bulk_wait)
        self.bulk_wait_input.returnPressed.connect(self._apply_bulk_wait)
        self.export_button.clicked.connect(self.export_sprite_sheet)
        self.individual_export_button.clicked.connect(self.export_individual_frames)
        self.gif_export_button.clicked.connect(self.export_animation_gif)
        self.up_button.clicked.connect(lambda: self._move_selected_row(-1))
        self.down_button.clicked.connect(lambda: self._move_selected_row(1))
        self.start_button.clicked.connect(self.start_animation)
        self.stop_button.clicked.connect(self.stop_animation)
        self.step_button.clicked.connect(self.step_frame)
        self.zoom_spin.valueChanged.connect(self._on_zoom_changed)
        self.preview_background_combo.currentIndexChanged.connect(
            self._on_preview_background_changed
        )
        self._on_preview_background_changed()
        selection_model = self.table.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed)

    # Frame management ----------------------------------------------------
    def add_image_files(self, paths: Sequence[str]) -> None:
        added_any = False
        first_added_index = len(self.frames)
        rows = self.sprite_rows_spin.value()
        columns = self.sprite_columns_spin.value()
        for path in paths:
            if not os.path.isfile(path):
                continue
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            try:
                rects = calculate_frame_rects(pixmap.width(), pixmap.height(), rows, columns)
            except ValueError:
                continue
            for frame_index, (x, y, width, height) in enumerate(rects):
                if len(rects) == 1:
                    display_name = os.path.basename(path)
                else:
                    frame_row = frame_index // columns + 1
                    frame_column = frame_index % columns + 1
                    display_name = f"{os.path.basename(path)} [{frame_row},{frame_column}]"
                frame = AnimationFrame(
                    path=path,
                    pixmap=pixmap.copy(x, y, width, height),
                    wait_ms=self.DEFAULT_WAIT_MS,
                    display_name=display_name,
                )
                self.frames.append(frame)
                self._append_table_row(frame)
                added_any = True
        if added_any:
            added_count = len(self.frames) - first_added_index
            if first_added_index == 0:
                if rows * columns == 1:
                    suggested_rows = (added_count + 999) // 1000
                    suggested_columns = min(added_count, 1000)
                else:
                    suggested_rows = (added_count + columns - 1) // columns
                    suggested_columns = columns
                self.export_rows_spin.setValue(min(suggested_rows, 1000))
                self.export_columns_spin.setValue(min(suggested_columns, 1000))
            selected_index = first_added_index if rows * columns > 1 else len(self.frames) - 1
            self._select_row(selected_index)
            if not self.is_playing:
                self.current_index = self.table.currentRow()
                self._refresh_display()
        self._update_button_states()

    def remove_selected_rows(self) -> None:
        if self.table.selectedItems():
            selected_row = self.table.currentRow()
            if selected_row < 0:
                return
            self.stop_animation()
            self.table.blockSignals(True)
            self.table.removeRow(selected_row)
            self.table.blockSignals(False)
            del self.frames[selected_row]
            if self.frames:
                if selected_row >= len(self.frames):
                    self.current_index = len(self.frames) - 1
                else:
                    self.current_index = selected_row
            else:
                self.current_index = 0
            self._select_row(self.current_index if self.frames else -1)
            self._refresh_display()
            self._update_button_states()

    def _append_table_row(self, frame: AnimationFrame) -> None:
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)

        file_item = QTableWidgetItem(frame.display_name or os.path.basename(frame.path))
        file_item.setToolTip(frame.path)
        file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)

        wait_item = QTableWidgetItem(str(frame.wait_ms))
        wait_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.table.setItem(row, 0, file_item)
        self.table.setItem(row, 1, wait_item)
        self.table.blockSignals(False)

    def _move_selected_row(self, direction: int) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        target = row + direction
        if target < 0 or target >= len(self.frames):
            return

        self.stop_animation()
        frame = self.frames.pop(row)
        self.frames.insert(target, frame)

        self.table.blockSignals(True)
        self.table.removeRow(row)
        self.table.insertRow(target)
        self._populate_row(target, frame)
        self.table.blockSignals(False)

        self.current_index = target
        self._select_row(target)
        self._refresh_display()

    def _populate_row(self, row: int, frame: AnimationFrame) -> None:
        file_item = QTableWidgetItem(frame.display_name or os.path.basename(frame.path))
        file_item.setToolTip(frame.path)
        file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)

        wait_item = QTableWidgetItem(str(frame.wait_ms))
        wait_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.table.setItem(row, 0, file_item)
        self.table.setItem(row, 1, wait_item)

    # Animation control ---------------------------------------------------
    def start_animation(self) -> None:
        if not self.frames:
            return
        if self.current_index >= len(self.frames):
            self.current_index = 0
        self.is_playing = True
        self._update_button_states()
        self._select_row(self.current_index)
        self._display_current_frame()
        self._start_timer_for_current()

    def stop_animation(self) -> None:
        if not self.is_playing and not self.timer.isActive():
            self._update_button_states()
            return
        self.timer.stop()
        self.is_playing = False
        self._update_button_states()

    def step_frame(self) -> None:
        if self.is_playing or not self.frames:
            return
        if not self._has_next_frame():
            return
        self._advance_to_next_frame()
        self._display_current_frame()
        self._select_row(self.current_index)

    def _advance_frame(self) -> None:
        if not self.frames:
            self.stop_animation()
            return
        if not self._advance_to_next_frame():
            self.stop_animation()
            return
        self._display_current_frame()
        if self.is_playing:
            self._start_timer_for_current()

    def _advance_to_next_frame(self) -> bool:
        if not self.frames:
            return False
        if self.current_index + 1 < len(self.frames):
            self.current_index += 1
            return True
        if self.loop_checkbox.isChecked():
            self.current_index = 0
            return True
        return False

    def _has_next_frame(self) -> bool:
        if not self.frames:
            return False
        if self.current_index + 1 < len(self.frames):
            return True
        return self.loop_checkbox.isChecked()

    def _start_timer_for_current(self) -> None:
        wait = max(1, self.frames[self.current_index].wait_ms)
        self.timer.start(wait)

    def _display_current_frame(self) -> None:
        if not self.frames:
            self.current_pixmap = None
            self._refresh_display()
            return
        frame = self.frames[self.current_index]
        self.current_pixmap = frame.pixmap
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self.frames or not self.current_pixmap:
            self.display_label.setText("ここに画像をドラッグ＆ドロップしてください")
            self.display_label.setPixmap(QPixmap())
            return

        target_size = self.display_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            self.display_label.setPixmap(self.current_pixmap)
            return

        pixmap = self.current_pixmap
        fit_ratio = min(
            1.0,
            target_size.width() / pixmap.width(),
            target_size.height() / pixmap.height(),
        )
        zoom_ratio = self.zoom_spin.value() / 100.0
        scale_ratio = max(0.01, fit_ratio * zoom_ratio)
        scaled_width = max(1, int(round(pixmap.width() * scale_ratio)))
        scaled_height = max(1, int(round(pixmap.height() * scale_ratio)))
        scaled = pixmap
        if scaled_width != pixmap.width() or scaled_height != pixmap.height():
            scaled = pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        canvas = QPixmap(target_size)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        x = (target_size.width() - scaled.width()) // 2
        y = (target_size.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

        self.display_label.setText("")
        self.display_label.setPixmap(canvas)

    # Event handlers ------------------------------------------------------
    def _handle_cell_changed(self, row: int, column: int) -> None:
        if column != 1 or row < 0 or row >= len(self.frames):
            return
        item = self.table.item(row, column)
        if not item:
            return
        text = item.text().strip()
        try:
            value = int(text)
            if value < 0:
                raise ValueError
        except ValueError:
            self.table.blockSignals(True)
            item.setText(str(self.frames[row].wait_ms))
            self.table.blockSignals(False)
            return
        self.frames[row].wait_ms = value
        if row == self.current_index and self.is_playing:
            self._start_timer_for_current()

    def _on_selection_changed(self, *_args) -> None:
        if self.is_playing:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.frames):
            return
        self.current_index = row
        self._display_current_frame()

    def _on_zoom_changed(self, _value: int) -> None:
        self._refresh_display()

    def _on_preview_background_changed(self, _index: int = 0) -> None:
        if self.preview_background_combo.currentData() == "white":
            background_color = "#ffffff"
            text_color = "#333333"
        else:
            background_color = "#000000"
            text_color = "#dddddd"
        self.display_label.setStyleSheet(
            f"background-color: {background_color}; "
            "border: 1px solid #3a3a3a; "
            f"color: {text_color};"
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.frames and self.current_pixmap:
            self._refresh_display()

    # Helpers -------------------------------------------------------------
    def _select_row(self, row: int) -> None:
        self.table.blockSignals(True)
        if row < 0:
            self.table.clearSelection()
        else:
            self.table.selectRow(row)
            self.table.setCurrentCell(row, 0)
        self.table.blockSignals(False)

    def _update_button_states(self) -> None:
        has_frames = bool(self.frames)
        self.up_button.setEnabled(has_frames)
        self.down_button.setEnabled(has_frames)
        self.start_button.setEnabled(has_frames and not self.is_playing)
        self.stop_button.setEnabled(self.is_playing)
        self.step_button.setEnabled(has_frames and not self.is_playing)
        self.bulk_apply_button.setEnabled(has_frames)
        self.bulk_wait_input.setEnabled(has_frames)
        self.export_rows_spin.setEnabled(has_frames)
        self.export_columns_spin.setEnabled(has_frames)
        self.export_button.setEnabled(has_frames)
        self.individual_export_button.setEnabled(has_frames)
        self.gif_export_button.setEnabled(has_frames)

    def _refresh_wait_column(self) -> None:
        self.table.blockSignals(True)
        for row, frame in enumerate(self.frames):
            item = self.table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 1, item)
            item.setText(str(frame.wait_ms))
        self.table.blockSignals(False)

    def _apply_bulk_wait(self) -> None:
        if not self.frames:
            return
        text = self.bulk_wait_input.text().strip()
        if not text:
            return
        try:
            value = int(text)
        except ValueError:
            return
        if value < 0:
            return
        for frame in self.frames:
            frame.wait_ms = value
        self._refresh_wait_column()
        if self.is_playing:
            self._start_timer_for_current()
        self.bulk_wait_input.setText(str(value))

    def export_sprite_sheet(self) -> None:
        if not self.frames:
            return
        try:
            sheet = build_sprite_sheet(
                self.frames,
                self.export_rows_spin.value(),
                self.export_columns_spin.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "スプライトシートを出力できません", str(error))
            return

        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "スプライトシートを保存",
            "sprite_sheet.png",
            "画像 (*.png *.webp *.jpg *.jpeg)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".png"
        if not sheet.save(path):
            QMessageBox.warning(
                self,
                "スプライトシートを出力できません",
                "画像を保存できませんでした。保存先や拡張子を確認してください。",
            )

    def export_individual_frames(self) -> None:
        if not self.frames:
            return

        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "個別PNGのファイル名と保存先を指定",
            "frame.png",
            "PNG画像 (*.png)",
        )
        if not selected_path:
            return

        output_directory = os.path.dirname(selected_path) or os.getcwd()
        base_name = os.path.basename(selected_path)
        try:
            output_paths = build_numbered_frame_paths(
                output_directory,
                base_name,
                len(self.frames),
            )
        except ValueError as error:
            QMessageBox.warning(self, "個別PNGを出力できません", str(error))
            return

        existing_paths = [path for path in output_paths if os.path.exists(path)]
        if existing_paths:
            answer = QMessageBox.question(
                self,
                "既存ファイルの上書き確認",
                f"同名のファイルが {len(existing_paths)} 件あります。上書きしますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        for frame, output_path in zip(self.frames, output_paths):
            if frame.pixmap.isNull() or not frame.pixmap.save(output_path, "PNG"):
                QMessageBox.warning(
                    self,
                    "個別PNGを出力できません",
                    f"画像を保存できませんでした。\n{output_path}",
                )
                return

    def export_animation_gif(self) -> None:
        if not self.frames:
            return

        output_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "GIFアニメーションを保存",
            "animation.gif",
            "GIFアニメーション (*.gif)",
        )
        if not output_path:
            return
        if os.path.splitext(output_path)[1].lower() != ".gif":
            output_path += ".gif"

        try:
            save_animation_gif(
                self.frames,
                output_path,
                self.loop_checkbox.isChecked(),
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                "GIFアニメーションを出力できません",
                f"GIFを保存できませんでした。\n{error}",
            )


def main() -> None:
    app = QApplication(sys.argv)
    dialog = AnimationDialog()
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
