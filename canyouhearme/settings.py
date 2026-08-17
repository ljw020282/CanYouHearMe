"""Settings: phrases, shortcuts, cache, voice, devices, API key."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from canyouhearme.defaults import VOICES
from canyouhearme.playback import list_output_devices


class SettingsDialog(QDialog):
    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CanYouHearMe 设置")
        self.setMinimumWidth(560)
        self._data = dict(data)

        self.key_edit = QLineEdit(self._data.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("百炼 API Key，只存在本机 config.json")
        self.base_edit = QLineEdit(self._data.get("dashscope_base", ""))
        self.root_edit = QLineEdit(self._data.get("data_root", ""))
        self.voice_box = QComboBox()
        for vid, label in VOICES:
            self.voice_box.addItem(f"{label}  ({vid})", vid)
        idx = self.voice_box.findData(self._data.get("voice"))
        if idx >= 0:
            self.voice_box.setCurrentIndex(idx)

        devices = list_output_devices()
        self.cable_box = QComboBox()
        self.monitor_box = QComboBox()
        self.cable_box.addItem("自动识别 CABLE Input", None)
        self.monitor_box.addItem("系统默认输出", None)
        for dev in devices:
            self.cable_box.addItem(f"{dev['id']}: {dev['name']}", dev["id"])
            self.monitor_box.addItem(f"{dev['id']}: {dev['name']}", dev["id"])
        self._select_device(self.cable_box, self._data.get("cable_device"))
        self._select_device(self.monitor_box, self._data.get("monitor_device"))
        self.monitor_on = QCheckBox("本地监听（耳机/音箱，不进 YY）")
        self.monitor_on.setChecked(bool(self._data.get("monitor_enabled", True)))
        self.pin_on = QCheckBox("启动时钉住悬浮条")
        self.pin_on.setChecked(bool(self._data.get("pin_overlay", True)))
        self.hide_after = QCheckBox("取消钉住后，说完自动隐藏")
        self.hide_after.setChecked(bool(self._data.get("hide_after_speak", True)))

        self.imm_spin = QSpinBox()
        self.imm_spin.setRange(1, 40)
        self.imm_spin.setValue(int(self._data.get("immediate_cache_max_chars", 6)))
        self.hit_spin = QSpinBox()
        self.hit_spin.setRange(1, 20)
        self.hit_spin.setValue(int(self._data.get("background_cache_hits", 3)))
        self.scan_spin = QSpinBox()
        self.scan_spin.setRange(15, 600)
        self.scan_spin.setValue(int(self._data.get("scan_interval_sec", 60)))

        self.phrase_edits = []
        phrase_box = QGroupBox("十条常用语")
        phrase_form = QVBoxLayout(phrase_box)
        phrases = list(self._data.get("phrases") or [])
        while len(phrases) < 10:
            phrases.append("")
        for i in range(10):
            edit = QLineEdit(phrases[i])
            self.phrase_edits.append(edit)
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{i + 1}."))
            row.addWidget(edit)
            phrase_form.addLayout(row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["缩写", "展开成"])
        self.table.horizontalHeader().setStretchLastSection(True)
        shortcuts = self._data.get("shortcuts") or {}
        for key, value in shortcuts.items():
            self._add_shortcut_row(key, value)
        add_btn = QPushButton("加一行缩写")
        add_btn.clicked.connect(lambda: self._add_shortcut_row("", ""))

        form = QFormLayout()
        form.addRow("API Key", self.key_edit)
        form.addRow("百炼地址", self.base_edit)
        form.addRow("数据目录", self.root_edit)
        form.addRow("音色", self.voice_box)
        form.addRow("进 YY 的设备", self.cable_box)
        form.addRow("本地监听设备", self.monitor_box)
        form.addRow(self.monitor_on)
        form.addRow(self.pin_on)
        form.addRow(self.hide_after)
        form.addRow("短句立刻缓存（字数少于）", self.imm_spin)
        form.addRow("长句缓存所需成功次数", self.hit_spin)
        form.addRow("扫库间隔（秒）", self.scan_spin)

        short_box = QGroupBox("缩写")
        short_lay = QVBoxLayout(short_box)
        short_lay.addWidget(self.table)
        short_lay.addWidget(add_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(phrase_box)
        root.addWidget(short_box)
        root.addWidget(buttons)

    def _add_shortcut_row(self, key: str, value: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))

    def _select_device(self, box: QComboBox, device_id) -> None:
        if device_id is None:
            box.setCurrentIndex(0)
            return
        idx = box.findData(device_id)
        if idx >= 0:
            box.setCurrentIndex(idx)

    def result_data(self) -> dict:
        phrases = [e.text().strip() for e in self.phrase_edits if e.text().strip()]
        shortcuts = {}
        for row in range(self.table.rowCount()):
            k_item = self.table.item(row, 0)
            v_item = self.table.item(row, 1)
            key = (k_item.text() if k_item else "").strip()
            value = (v_item.text() if v_item else "").strip()
            if key and value:
                shortcuts[key] = value
        return {
            "api_key": self.key_edit.text().strip(),
            "dashscope_base": self.base_edit.text().strip(),
            "data_root": self.root_edit.text().strip(),
            "voice": self.voice_box.currentData(),
            "cable_device": self.cable_box.currentData(),
            "monitor_device": self.monitor_box.currentData(),
            "monitor_enabled": self.monitor_on.isChecked(),
            "pin_overlay": self.pin_on.isChecked(),
            "hide_after_speak": self.hide_after.isChecked(),
            "immediate_cache_max_chars": self.imm_spin.value(),
            "background_cache_hits": self.hit_spin.value(),
            "scan_interval_sec": self.scan_spin.value(),
            "phrases": phrases,
            "shortcuts": shortcuts,
        }
