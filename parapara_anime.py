from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, QMimeData, QTimer
from PySide6.QtGui import QImageReader, QIntValidator, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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

        self.display_label = QLabel()
        self.display_label.setMinimumSize(320, 240)
        self.display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.display_label.setAlignment(Qt.AlignCenter)
        self.display_label.setStyleSheet(
            "background-color: #202020; border: 1px solid #3a3a3a; color: #aaaaaa;"
        )
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 800)
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix("%")
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("表示倍率:"))
        zoom_layout.addWidget(self.zoom_spin)
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
        self.up_button.clicked.connect(lambda: self._move_selected_row(-1))
        self.down_button.clicked.connect(lambda: self._move_selected_row(1))
        self.start_button.clicked.connect(self.start_animation)
        self.stop_button.clicked.connect(self.stop_animation)
        self.step_button.clicked.connect(self.step_frame)
        self.zoom_spin.valueChanged.connect(self._on_zoom_changed)
        selection_model = self.table.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed)

    # Frame management ----------------------------------------------------
    def add_image_files(self, paths: Sequence[str]) -> None:
        added_any = False
        for path in paths:
            if not os.path.isfile(path):
                continue
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            frame = AnimationFrame(path=path, pixmap=pixmap, wait_ms=self.DEFAULT_WAIT_MS)
            self.frames.append(frame)
            self._append_table_row(frame)
            added_any = True
        if added_any:
            self._select_row(len(self.frames) - 1)
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

        file_item = QTableWidgetItem(os.path.basename(frame.path))
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
        file_item = QTableWidgetItem(os.path.basename(frame.path))
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


def main() -> None:
    app = QApplication(sys.argv)
    dialog = AnimationDialog()
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
