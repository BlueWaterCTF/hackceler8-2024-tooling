import os
import glob

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import QMetaObject

DEFAULT_SPEED = 1.5


class SpeedSpinBox(QtWidgets.QSlider):
    SPEED_DIAL = (.1, .2, .5, 1, 1.5, 2, 4, 10)

    def __init__(self, parent=None):
        super().__init__(QtCore.Qt.Orientation.Horizontal, parent)

        self.setRange(0, len(self.SPEED_DIAL) - 1)
        self.setValue(self.SPEED_DIAL.index(DEFAULT_SPEED))
        self.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBothSides)

    def step(self, delta):
        self.setValue(self.value() + delta)


class PlayTextWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        self.counter = QtWidgets.QLabel('Tick: 0', self)
        layout.addWidget(self.counter)

        layout.addStretch()

        # sim mode
        self.sim_mode = QtWidgets.QCheckBox('Sim Mode', self)
        layout.addWidget(self.sim_mode)

    def set_tick(self, subed, index=None, unsubed=None):
        if index is None:
            self.counter.setText(f'Tick: {subed}')
        else:
            self.sim_mode.setDisabled(index > 0)
            self.counter.setText(f'Tick: {subed + index}/{subed + unsubed} ({index}/{unsubed})')


class PlayWidget(QtWidgets.QWidget):
    state: str = None

    stopReplay = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        self.speed_txt = QtWidgets.QDoubleSpinBox(self)
        layout.addWidget(self.speed_txt)

        self.speed_txt.setPrefix('Speed ')
        self.speed_txt.setSuffix('x')
        self.speed_txt.setRange(0.1, 100)
        self.speed_txt.setDecimals(1)
        self.speed_txt.setValue(DEFAULT_SPEED)
        self.speed_txt.setStepType(QtWidgets.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)

        self.speed = SpeedSpinBox(self)
        layout.addWidget(self.speed)
        self.speed.valueChanged.connect(self.set_speed)

        # play button
        self.play_button = QtWidgets.QPushButton(self)
        layout.addWidget(self.play_button)

        self.set_state('pause')
        self.play_button.setIconSize(QtCore.QSize(16, 16))
        self.play_button.setFixedSize(QtCore.QSize(32, 32))
        self.play_button.clicked.connect(self.switch)

    def set_speed(self, speed):
        target = SpeedSpinBox.SPEED_DIAL[speed]
        self.speed_txt.setValue(target)

    def switch(self):
        match self.state:
            case 'play':
                self.set_state('pause')
            case 'pause':
                self.set_state('play')
            case 'replay':
                self.stopReplay.emit()
            case _:
                assert False

    def set_state(self, state):
        if self.state == state:
            return
        match state:
            case 'play':
                self.state = 'play'
                self.play_button.setIcon(QtGui.QIcon.fromTheme('media-playback-pause'))
                self.play_button.setDisabled(False)
            case 'pause':
                self.state = 'pause'
                self.play_button.setIcon(QtGui.QIcon.fromTheme('media-playback-start'))
                self.play_button.setDisabled(False)
            case 'step':
                self.state = 'step'
                self.play_button.setIcon(QtGui.QIcon.fromTheme('media-playback-pause'))
                self.play_button.setDisabled(True)
            case 'replay':
                self.state = 'replay'
                self.play_button.setIcon(QtGui.QIcon.fromTheme('media-playback-stop'))
                self.play_button.setDisabled(False)
            case _:
                assert False


class SaveWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        self.input = QtWidgets.QLineEdit(self)
        layout.addWidget(self.input)

        self.save_button = QtWidgets.QPushButton('Save', self)
        layout.addWidget(self.save_button)


class ReplayButtonsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # total ticks
        self.total = QtWidgets.QLabel(self)
        layout.addWidget(self.total)

        # replay show
        self.btn1 = QtWidgets.QPushButton('Replay (Realtime)', self)
        layout.addWidget(self.btn1)

        # replay no show
        self.btn2 = QtWidgets.QPushButton('Replay (Direct)', self)
        layout.addWidget(self.btn2)

    def set_total(self, total):
        if total < 0:
            self.total.clear()
        else:
            self.total.setText(f'Total ticks: {total}')


class ReplayWidget(QtWidgets.QWidget):
    watch_dir: str
    current_file: str

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # list
        self.list = QtWidgets.QListWidget(self)
        layout.addWidget(self.list)

        self.list.currentTextChanged.connect(self.selected_file)

        # buttons
        self.btns = ReplayButtonsWidget(self)
        layout.addWidget(self.btns)

        self.watcher = QtCore.QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.refresh)

    def selected_file(self, fname):
        if not fname:
            self.btns.set_total(-1)
            return
        counter = 0
        with open(os.path.join(self.watch_dir, fname + '.jsonl'), 'rb') as f:
            for _ in f:
                counter += 1
        self.btns.set_total(counter)

    def set_args(self, current, dir):
        self.current_file = current
        self.watch_dir = dir
        self.watcher.addPath(dir)
        self.refresh()

    def __sort_key(self, fname: str):
        return not fname.startswith('autosave'), os.path.getmtime(os.path.join(self.watch_dir, fname + '.jsonl'))

    def refresh(self):
        files = glob.iglob('**/*.jsonl', root_dir=self.watch_dir, recursive=True)
        fls = []
        for file in files:
            if not file.endswith('.jsonl') or file == self.current_file:
                continue
            fls.append(file[:-len('.jsonl')])
        fls.sort(key=self.__sort_key, reverse=True)

        self.list.clear()
        self.list.addItems(fls)


class ToolboxWidget(QtWidgets.QWidget):
    def __init__(self):
        self.__shown = False

        super().__init__()
        self.unfocus_func = None

        # layout
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # counter area
        self.counter = PlayTextWidget(self)
        layout.addWidget(self.counter)

        # play button area
        self.play = PlayWidget(self)
        layout.addWidget(self.play)

        # replay area
        self.replay = ReplayWidget(self)
        layout.addWidget(self.replay)

        # save area
        self.save = SaveWidget(self)
        layout.addWidget(self.save)

        WT = QtCore.Qt.WindowType
        self.setWindowFlags(
            WT.NoDropShadowWindowHint |
            WT.CustomizeWindowHint |
            WT.WindowTitleHint |
            WT.WindowStaysOnTopHint |
            WT.MSWindowsFixedSizeDialogHint
        )
        self.setWindowTitle('\U0001f4a6 Blue Water Hacking Toolbox')

    @QtCore.Slot()
    def showInit(self):
        self.show()
        self.move(100, 100)

    def leaveEvent(self, event):
        if self.unfocus_func is not None:
            self.unfocus_func()
        super().leaveEvent(event)

    def show_async(self):
        if not self.__shown:
            QMetaObject.invokeMethod(self, 'showInit')
            self.__shown = True
