import re
from PyQt4 import Qt
from qt_helpers import VBox, HBox, Form, Grid, Parameter, Labelled, Named, NamedListModel, NamedListView, increment_str, MPLImagePlot, PyQtGraphImagePlot
from qutip import num, destroy, qeye, sigmaz, sigmam, tensor, mesolve, coherent, wigner
import numpy as np
import sys

class Hamiltonian(Qt.QAbstractTableModel):
    params = ["id", "a*ad", "a+hc", "sz", "sm+hc"]
    def __init__(self):
        super(Hamiltonian, self).__init__()
        self.coefs = {}
        for i, p1 in enumerate(self.params):
            for j, p2 in enumerate(self.params[i:]):
                self.coefs[(p1, p2)] = 0

    def rowCount(self, parent=None):
        return len(self.params)

    def columnCount(self, parent=None):
        return len(self.params)

    def headerData(self, i, orientation, role):
        if role == Qt.Qt.DisplayRole:
            return self.params[i]

    def data(self, index, role):
        if role == Qt.Qt.DisplayRole:
            i, j  = index.row(), index.column()
            if j >= i:
                pi, pj = self.params[i], self.params[j]
                return str(self.coefs[(pi, pj)])

    def setData(self, index, value, role):
        if role == Qt.Qt.EditRole:
            i, j = index.row(), index.column()
            if j >= i:
                pi, pj = self.params[i], self.params[j]
                self.coefs[(pi, pj)] = str(value.toString())
                self.dataChanged.emit(index, index)
                return True
        return False

    def flags(self, index):
        f = Qt.Qt.NoItemFlags
        i, j = index.row(), index.column()
        if j >= i:
            f |= Qt.Qt.ItemIsEnabled
            f |= Qt.Qt.ItemIsSelectable
            f |= Qt.Qt.ItemIsEditable
        return f

    def copy(self):
        new = Hamiltonian()
        new.coefs = self.coefs.copy()
        return new

    def to_matrix(self, fd):
        n = num(fd)
        a = destroy(fd)
        ic = qeye(fd)
        sz = sigmaz()
        sm = sigmam()
        iq = qeye(2)

        ms = {
            "id": tensor(iq, ic),
            "a*ad" : tensor(iq, n),
            "a+hc" : tensor(iq, a),
            "sz" : tensor(sz, ic),
            "sm+hc" : tensor(sm, ic)
        }

        H0 = 0
        H1s = []
        for (p1, p2), v in self.coefs.items():
            h = ms[p1] * ms[p2]
            try:
                term = float(v) * h
                if not term.isherm:
                    term += term.dag()
                H0 += term
            except ValueError:
                H1s.append([h, v])
        if H1s:
            return [H0] + H1s
        else:
            return H0

class HamiltonianWidget(Named):
    def __init__(self, model=None, name="Hmt1"):
        super(HamiltonianWidget, self).__init__(name=name)
        widget = Qt.QTableView()
        self.model = model if model else Hamiltonian()
        widget.setModel(self.model)
        widget.resizeColumnsToContents()
        widget.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Minimum)
        self.addWidget(widget)

    def copy(self):
        return HamiltonianWidget(model=self.model.copy(), name=increment_str(self.name))

class HamiltonianListModel(NamedListModel):
    type_name = "Hamiltonian"
    default_factory = HamiltonianWidget

class HamiltonianListView(NamedListView):
    list_model = HamiltonianListModel
    def __init__(self):
        super(HamiltonianListView, self).__init__()

        copy_action = Qt.QAction("Copy", self)
        copy_action.triggered.connect(self.copy_selected)
        self.addAction(copy_action)
        self.setContextMenuPolicy(Qt.Qt.ActionsContextMenu)

    def copy_selected(self):
        original = self.model.get_widget(self.list_widget.selectedIndexes()[0])
        new = original.copy()
        while new.name in self.model.names():
            new.name = increment_str(new.name)

        self.add_item(new)

class Sequence(Qt.QAbstractTableModel):
    def __init__(self):
        Qt.QAbstractTableModel.__init__(self)
        self.steps = []

    def rowCount(self, parent=None):
        if parent.isValid():
            return 0
        return len(self.steps)

    def columnCount(self, parent=None):
        return 2

    def headerData(self, i, orientation, role=None):
        if role == Qt.Qt.DisplayRole:
            if orientation == Qt.Qt.Horizontal:
                return ["Name", "Time Applied"][i]

    def flags(self, index):
        f = Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable
        f |= Qt.Qt.ItemIsDragEnabled

        if not index.isValid():
            f |= Qt.Qt.ItemIsDropEnabled

        if index.column() == 1:
            f |= Qt.Qt.ItemIsEditable
        return f

    def data(self, index, role):
        if role == Qt.Qt.DisplayRole:
            i, j = index.row(), index.column()
            if j == 0:
                return self.steps[i][0].name
            elif j == 1:
                return self.steps[i][1]

    def setData(self, index, value, role):
        if role == Qt.Qt.EditRole:
            i, j = index.row(), index.column()
            v, ok = value.toFloat()
            if not ok or (j != 1):
                print 'Failed to set', value
                return False
            self.steps[i][j] = v
            self.dataChanged.emit(index, index)
            return True
        return False

    def mimeTypes(self):
        return ["application/sequence-position"]

    def mimeData(self, indices):
        rows = set([i.row() for i in indices])
        if len(rows) == 1:
            res = Qt.QMimeData()
            res.setData("application/sequence-position", str(rows.pop()))
            return res

    def dropMimeData(self, mime_data, action, row, col, parent):
        if row > 0:
            src_row = int(mime_data.data("application/sequence-position"))
            item = self.steps.pop(src_row)
            if row > src_row:
                row -= 1
            self.steps.insert(row, item)
            self.modelReset.emit()
            return True
        return False

    def to_state_list(self, fock_dim, psi0, timestep):
        states = []
        for widget, time in self.steps:
            H = widget.model.to_matrix(fock_dim)
            tlist = np.arange(0, time, timestep)
            states.extend(mesolve(H, psi0, tlist, [], []).states)
            psi0 = states[-1]
        print len(states)
        return states

class SequenceView(Named):
    def __init__(self, name="Seq1"):
        super(SequenceView, self).__init__(name=name)
        self.sequence_view = Qt.QTreeView()
        self.sequence_view.setDragDropMode(Qt.QAbstractItemView.InternalMove)
        self.sequence_view.setItemsExpandable(False)
        self.sequence_view.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        self.sequence_view.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        self.sequence_view.setDragDropOverwriteMode(False)
        self.model = Sequence()
        self.sequence_view.setModel(self.model)
        self.addWidget(self.sequence_view)


class SequenceListModel(NamedListModel):
    type_name = "Sequence"
    default_factory = SequenceView

class SequenceListView(NamedListView):
    list_model = SequenceListModel

    def __init__(self):
        super(SequenceListView, self).__init__()

        self.setContextMenuPolicy(Qt.Qt.ActionsContextMenu)
        new_action = Qt.QAction("New Sequence", self)
        new_action.triggered.connect(self.new_sequence)
        self.addAction(new_action)

    def new_sequence(self):
        new = SequenceView()
        while new.name in self.model.names():
            new.name = increment_str(new.name)
        self.add_item(new)

class SequenceEditor(VBox):
    def __init__(self):
        super(SequenceEditor, self).__init__()
        self.hamiltonian_list = HamiltonianListView()
        add_step_button = Qt.QPushButton("Add Hamiltonian as Step")
        add_step_button.clicked.connect(self.add_selected)
        self.sequence_list = SequenceListView()
        self.fock_dim = Parameter("Fock Dimension", 8, 4, 30, 1, Qt.QSpinBox)
        self.timestep = Parameter("Timestep", .1, .01, 1, .01)
        self.initial_alpha = Parameter("Initial Alpha", 1, 0, 10, 1)
        self.addWidgets(self.hamiltonian_list, add_step_button, self.sequence_list)
        self.addWidgets(self.fock_dim, self.timestep, self.initial_alpha)

    def add_selected(self):
        w = self.hamiltonian_list.selected_widget()
        self.sequence_list.current_item.model.steps.append([w, 0])
        self.sequence_list.current_item.model.modelReset.emit()

class TimeImagePlotter(Named):
    def __init__(self, name, data):
        super(TimeImagePlotter, self).__init__(name=name)
        # self.wigner_plot = MPLImagePlot()
        self.wigner_plot = PyQtGraphImagePlot()
        self.data = data
        self.time_slider = Parameter("Time", 0, 0, len(data)-1, 1, lambda: Qt.QSlider(Qt.Qt.Horizontal))
        self.time_slider.valueChanged.connect(self.update_plot)
        self.addWidgets(self.wigner_plot, self.time_slider)
        self.update_plot()

    def update_plot(self):
        self.wigner_plot.plot(self.data[self.time_slider.value()])

class WignerPlotter(TimeImagePlotter):
    def __init__(self, name, state_data):
        super(WignerPlotter, self).__init__(name, [[[0]]])
        self.state_data = state_data
        self.wigner_max = Parameter('Max Alpha', 4, 2, 12, .25)
        update_button = Qt.QPushButton("Recalculate Wigners")
        update_button.clicked.connect(self.update_wigners)
        self.addWidget(HBox((self.wigner_max, update_button)))
        self.update_wigners()

    def update_wigners(self):
        max_alpha = self.wigner_max.value()
        wigner_xs = np.linspace(-max_alpha, max_alpha, 100)
        wigner_fn = lambda a: wigner(a, wigner_xs, wigner_xs)
        self.data = map(wigner_fn, self.state_data)
        self.time_slider.setRange(0, len(self.data)-1)
        self.update_plot()

class ComputationsListModel(NamedListModel):
    type_name = "Computation"

class ComputationsListView(NamedListView):
    list_model = ComputationsListModel

class SequencePlotter(Qt.QSplitter):
    def __init__(self):
        super(SequencePlotter, self).__init__(Qt.Qt.Horizontal)
        self.editor = SequenceEditor()
        self.viewer = ComputationsListView()
        compute_button = Qt.QPushButton("Compute Selected Sequence")
        compute_button.clicked.connect(self.compute_selected)
        self.addWidget(VBox((self.viewer, compute_button)))
        self.addWidget(self.editor)

    def compute_selected(self):
        item = self.editor.sequence_list.current_item

        fock_dim = self.editor.fock_dim.value()
        timestep = self.editor.timestep.value()
        initial_alpha = self.editor.initial_alpha.value()
        psi0 = coherent(fock_dim, initial_alpha)

        data = item.model.to_state_list(fock_dim, psi0, timestep)
        self.viewer.add_item(WignerPlotter(item.name, data))




app = Qt.QApplication([])
win = SequencePlotter()
win.show()
sys.exit(app.exec_())
