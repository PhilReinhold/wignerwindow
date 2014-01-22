# Qt Helpers
from PyQt4 import Qt
import re

from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from pyqtgraph import ImageView
import numpy as np
from pyqtgraph.graphicsItems.InfiniteLine import InfiniteLine


def increment_str(s):
    if re.match(".*[0-9]$", s):
        return re.sub("[0-9]+", lambda s: str(int(s.group())+1), s)
    else:
        return s + "1"

# Layout Helpers
class LayoutWidget(Qt.QFrame):
    _layout_cls = None
    def __init__(self, children=None, *args, **kwargs):
        super(LayoutWidget, self).__init__(*args, **kwargs)
        self.setLayout(self._layout_cls())
        if children is not None:
            self.addWidgets(*children)

    def addWidget(self, *args, **kwargs):
        self.layout().addWidget(*args, **kwargs)

    def insertWidget(self, *args, **kwargs):
        self.layout().insertWidget(*args, **kwargs)

    def addWidgets(self, *ws):
        for w in ws:
            self.addWidget(w)

    def minimize(self):
        self.setSizePolicy(Qt.QSizePolicy.Maximum, Qt.QSizePolicy.Maximum)
        self.setContentsMargins(0,0,0,0)

class VBox(LayoutWidget):
    _layout_cls = Qt.QVBoxLayout

class HBox(LayoutWidget):
    _layout_cls = Qt.QHBoxLayout

class Form(LayoutWidget):
    _layout_cls = Qt.QFormLayout

class Grid(LayoutWidget):
    _layout_cls = Qt.QGridLayout

class Labelled(HBox):
    def __init__(self, widget, name):
        HBox.__init__(self, (Qt.QLabel(name), widget))
        self.layout().setContentsMargins(0,0,0,0)

class Parameter(Labelled):
    def __init__(self, name, initial, min, max, step, widget_class=Qt.QDoubleSpinBox):
        widget = widget_class()
        widget.setValue(initial)
        widget.setRange(min, max)
        widget.setSingleStep(step)
        self._pwidget = widget
        super(Parameter, self).__init__(widget, name)

    def __getattr__(self, item):
        return getattr(self._pwidget, item)

class Named(Qt.QGroupBox, VBox):
    def __init__(self, type="", name=None):
        super(Named, self).__init__()
        if not name:
            name = type + "1"
        self.name = name

    @property
    def name(self):
        return str(self.title())

    @name.setter
    def name(self, value):
        self.setTitle(value)


class NamedListModel(Qt.QAbstractListModel):
    type_name = ""
    default_factory = None

    def __init__(self, widgets=None):
        super(NamedListModel, self).__init__()
        if widgets is None:
            if self.default_factory is None:
                self.widget_list = []
            else:
                self.widget_list = [self.default_factory()]
        else:
            self.widget_list = widgets

    def rowCount(self, parent=None):
        return len(self.widget_list)

    def data(self, idx, role=None):
        if role == Qt.Qt.DisplayRole:
            return self.get_widget(idx).name

    def setData(self, idx, value, role):
        if role == Qt.Qt.EditRole:
            self.widget_list[idx.row()].name = value.toString()
            return True
        else:
            return False

    def names(self):
        return [m.name for m in self.widget_list]

    def get_widget(self, idx):
        return self.widget_list[idx.row()]

    def add_item(self, item):
        self.widget_list.append(item)
        i = self.index(len(self.widget_list) - 1)
        self.dataChanged.emit(i, i)

    def flags(self, index):
        return Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable | Qt.Qt.ItemIsEditable

    def __getitem__(self, item):
        return self.widget_list[item]

class NamedListView(Qt.QGroupBox, VBox):
    list_model_class = NamedListModel
    def __init__(self, plural_name=None):
        super(NamedListView, self).__init__()
        if plural_name is None:
            plural_name = self.list_model_class.type_name + "s"
        self.setTitle(plural_name)
        self.model = self.list_model_class()

        self.list_widget = Qt.QListView()
        self.list_widget.setModel(self.model)
        self.list_widget.selectionModel().selectionChanged.connect(self.change_item)
        self.list_widget.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Maximum)

        if self.list_model_class.default_factory is not None:
            self.setContextMenuPolicy(Qt.Qt.ActionsContextMenu)
            new_item_action = Qt.QAction("New Item", self)
            self.addAction(new_item_action)
            new_item_action.triggered.connect(lambda: self.add_item(self.list_model_class.default_factory()))

        self.current_item = None
        self.addWidgets(self.list_widget)
        self.addWidgets(*self.model.widget_list)
        if self.model.widget_list:
            self.list_widget.setCurrentIndex(self.model.index(0,0))


    def add_item(self, item):
        while item.name in self.model.names():
            item.name = increment_str(item.name)

        self.addWidget(item)
        self.model.add_item(item)
        self.list_widget.resize(self.list_widget.sizeHint())


        if self.current_item is None:
            item.show()
            self.current_item = item
            self.list_widget.setCurrentIndex(self.model.index(0,0))

        else:
            item.hide()

    def selected_widget(self):
        return self.model.get_widget(self.list_widget.selectedIndexes()[0])

    def change_item(self, selected, deselected):
        idx = selected.indexes()[0]
        if self.current_item is not None:
            self.current_item.hide()
        self.current_item = self.model[idx.row()]
        self.current_item.show()

class ButtonPair(HBox):
    def __init__(self, text1, text2):
        super(ButtonPair, self).__init__()
        self._button1 = Qt.QPushButton(text1)
        self._button2 = Qt.QPushButton(text2)
        self._button2.hide()
        self.clicked1 = self._button1.clicked
        self.clicked2 = self._button2.clicked
        self.clicked1.connect(self._button1.hide)
        self.clicked1.connect(self._button2.show)
        self.clicked2.connect(self._button1.show)
        self.clicked2.connect(self._button2.hide)
        self.addWidgets(self._button1, self._button2)



class MPLImagePlot(FigureCanvasQTAgg):
    def __init__(self):
        self._figure = Figure()
        self._axes = self._figure.add_subplot(111)
        super(MPLImagePlot, self).__init__(self._figure)

    def plot(self, arr):
        self._axes.imshow(arr)
        self.draw()

class PyQtGraphImagePlot(ImageView):
    def __init__(self, *args, **kwargs):
        super(PyQtGraphImagePlot, self).__init__(*args, **kwargs)
        self.ui.histogram.hide()
        self.ui.roiBtn.hide()
        self.ui.normBtn.hide()
        self.line1 = InfiniteLine(pos=0, angle=0, movable=False)
        self.line2 = InfiniteLine(pos=0, angle=90, movable=False)
        self.addItem(self.line1)
        self.addItem(self.line2)

    def plot(self, arr):
        self.setImage(np.array(arr))
        self.line1.setPos(arr.shape[0]/2.)
        self.line2.setPos(arr.shape[1]/2.)

class HorizontalSlider(Qt.QSlider):
    def __init__(self, *args, **kwargs):
        super(HorizontalSlider, self).__init__(Qt.Qt.Horizontal, *args, **kwargs)

