import os
import re
from PyQt4 import Qt
from bloch_plot import BlochPlotter
from qt_helpers import VBox, HBox, Parameter, Named, NamedListModel, NamedListView, increment_str, PyQtGraphImagePlot, ButtonPair, HorizontalSplitter, Labelled, Form
from qutip import num, destroy, qeye, sigmaz, sigmam, tensor, mesolve, coherent_dm, wigner, basis, ket2dm
import numpy as np
import sys
import json
from multiprocessing import Process
from multiprocessing.queues import Queue

hamiltonian_filename = "/Users/phil/.wigner/hamiltonians"
sequence_filename = "/Users/phil/.wigner/sequences"

class Hamiltonian(Qt.QAbstractTableModel):
    params = ["id", "a*ad", "a+hc", "sz", "sm+hc"]
    images = ["id.png", "aad.png", "ahc.png", "sz.png", "smhc.png"]
    def __init__(self, json_str=None):
        super(Hamiltonian, self).__init__()
        if json_str is None:
            self.coefs = {}
            for i, p1 in enumerate(self.params):
                for j, p2 in enumerate(self.params[i:]):
                    self.coefs[(p1, p2)] = 0
        else:
            obj = json.loads(json_str)
            self.coefs = { tuple(k.split(',')): v for k, v in obj.items()}

        self.image_pixmaps = [Qt.QPixmap('latex/' + i) for i in self.images]
        self.image_pixmaps = [i.scaledToHeight(10, Qt.Qt.SmoothTransformation) for i in self.image_pixmaps]

    def __repr__(self):
        obj = { ','.join(k):v for k, v in self.coefs.items() }
        return json.dumps(obj)

    def rowCount(self, parent=None):
        return len(self.params)

    def columnCount(self, parent=None):
        return len(self.params)

    def headerData(self, i, orientation, role):
        if role == Qt.Qt.DecorationRole:
            return self.image_pixmaps[i]

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
                if not h.isherm:
                    replacement = lambda m: '(-' + m.group() + ')'
                    conj_v = re.sub('[1-9]+j', replacement, v)
                    H1s.append([h.dag(), conj_v])
        if H1s:
            return [H0] + H1s
        else:
            return H0

class HamiltonianWidget(Named):
    def __init__(self, model=None, name="Hmt1"):
        super(HamiltonianWidget, self).__init__(name=name)
        widget = Qt.QTableView()
        self.model = model if model else Hamiltonian()
        self.model.dataChanged.connect(widget.resizeColumnsToContents)
        widget.setModel(self.model)
        widget.resizeColumnsToContents()
        row_heights = sum(widget.rowHeight(i) for i in range(widget.model().rowCount()))
        total_height = row_heights + widget.horizontalHeader().height()
        widget.setMinimumHeight(total_height + 15)
        column_widths = sum(widget.columnWidth(i) for i in range(widget.model().columnCount()))
        total_width = column_widths + widget.verticalHeader().width()
        widget.setMinimumWidth(total_width + 15)
        self.addWidget(widget)

    def copy(self):
        return HamiltonianWidget(model=self.model.copy(), name=increment_str(self.name))

class HamiltonianListModel(NamedListModel):
    type_name = "Hamiltonian"
    default_factory = HamiltonianWidget
    def __init__(self, filename=hamiltonian_filename):
        try:
            make_widget = lambda n, s: HamiltonianWidget(name=n, model=Hamiltonian(json_str=s))
            widgets = [make_widget(*i) for i in json.load(open(filename)).items()]
            if not widgets:
                widgets = None
            for w in widgets:
                w.hide()
            super(HamiltonianListModel, self).__init__(widgets=widgets)
        except Exception as e:
            print "Couldn't load hamiltonians", e
            super(HamiltonianListModel, self).__init__()

    def save_state(self):
        obj = {h.name: str(h.model) for h in self.widget_list}
        json.dump(obj, open(hamiltonian_filename, 'w'))


class HamiltonianListView(NamedListView):
    list_model_class = HamiltonianListModel
    def __init__(self):
        super(HamiltonianListView, self).__init__()

        copy_action = Qt.QAction("Copy", self)
        copy_action.triggered.connect(self.copy_selected)
        self.addAction(copy_action)

        save_action = Qt.QAction("Save", self)
        save_action.triggered.connect(self.model.save_state)
        self.addAction(save_action)

        self.setContextMenuPolicy(Qt.Qt.ActionsContextMenu)

    def copy_selected(self):
        original = self.model.get_widget(self.list_widget.selectedIndexes()[0])
        new = original.copy()
        self.add_item(new)


class Sequence(Qt.QAbstractTableModel):
    def __init__(self, json_str=None):
        Qt.QAbstractTableModel.__init__(self)
        self.steps = []
        self.base = []

    def __repr__(self):
        return json.dumps([{'hmt':h, 'time':t} for (h, t) in self.steps])

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

    def get_steps(self, fock_dim, timestep):
        res = []
        base_H = sum(w.model.to_matrix(fock_dim) for w in self.base)
        for widget, time in self.steps:
            H = base_H + widget.model.to_matrix(fock_dim)
            tlist = np.arange(0, time, timestep)
            res.append((H, tlist))
        return res

    def to_state_list(self, fock_dim, psi0, timestep):
        return to_state_list(self.get_steps(), fock_dim, psi0, timestep)


def to_state_list(steps, fock_dim, psi0, timestep):
    states = []
    for H, tlist in steps:
        states.extend(mesolve(H, psi0, tlist, [], []).states)
        psi0 = states[-1]
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

        self.base_view = Qt.QListView()
        self.base_model = NamedListModel()
        self.base_view.setModel(self.base_model)
        self.model.base = self.base_model.widget_list

        delete_base_action = Qt.QAction("Delete", self.base_view)
        delete_base = lambda: self.base_model.remove_index(self.base_view.selectedIndexes()[0])
        delete_base_action.triggered.connect(delete_base)
        self.base_view.addAction(delete_base_action)
        self.base_view.setContextMenuPolicy(Qt.Qt.ActionsContextMenu)

        self.addWidgets(Qt.QLabel("Base Hamiltonian"), self.base_view)
        self.addWidgets(Qt.QLabel("Sequence Steps"), self.sequence_view)



class SequenceListModel(NamedListModel):
    type_name = "Sequence"
    default_factory = SequenceView
    def __init__(self):
        super(SequenceListModel, self).__init__(no_default=True)

class SequenceListView(NamedListView):
    list_model_class = SequenceListModel

class SequenceEditor(VBox):
    def __init__(self):
        super(SequenceEditor, self).__init__()
        self.hamiltonian_list = HamiltonianListView()
        add_step_button = Qt.QPushButton("Add as Step")
        add_step_button.clicked.connect(self.add_selected)
        add_base_button = Qt.QPushButton("Add to Base")
        add_base_button.clicked.connect(self.add_selected_as_base)
        self.sequence_list = SequenceListView()
        self.sequence_list.model.dataChanged.connect(self.sequence_list.hide_if_empty)
        self.sequence_list.hide_if_empty()
        self.fock_dim = Parameter("Fock Dimension", 8, 4, 30, 1, Qt.QSpinBox)
        self.timestep = Parameter("Timestep", .1, .01, 1, .01)
        self.initial_alpha = Parameter("Initial Alpha", 1, 0, 10, 1)
        splitter = Qt.QSplitter()
        comp_params_box = VBox((self.fock_dim, self.timestep, self.initial_alpha))

        for w in (add_step_button, add_base_button):
            self.hamiltonian_list.insertWidget(1, w)

        splitter.addWidget(self.hamiltonian_list)
        splitter.addWidget(self.sequence_list)
        self.addWidgets(splitter, comp_params_box)

    def add_selected(self):
        w = self.hamiltonian_list.selected_widget()
        if self.sequence_list.current_item is None:
            self.sequence_list.add_item(SequenceView())
        self.sequence_list.current_item.model.steps.append([w, 10])
        self.sequence_list.current_item.model.modelReset.emit()

    def add_selected_as_base(self):
        w = self.hamiltonian_list.selected_widget()
        if self.sequence_list.current_item is None:
            self.sequence_list.add_item(SequenceView())
        self.sequence_list.current_item.base_model.add_item(w)
        self.sequence_list.current_item.base_model.modelReset.emit()


class WignerPlotter(Named):
    calculating_wigners = Qt.pyqtSignal()
    wigners_complete = Qt.pyqtSignal()
    def __init__(self, name, state_data):
        super(WignerPlotter, self).__init__(name=name)
        self.wigner_plot_0 = PyQtGraphImagePlot()
        ket_0_pm, ket_1_pm = Qt.QPixmap(), Qt.QPixmap()
        ket_0, ket_1 = Qt.QLabel(), Qt.QLabel()
        ket_0_pm.load("latex/ket0.png")
        ket_1_pm.load("latex/ket1.png")
        ket_0_pm = ket_0_pm.scaledToWidth(25)
        ket_1_pm = ket_1_pm.scaledToWidth(25)
        ket_0.setPixmap(ket_0_pm)
        ket_1.setPixmap(ket_1_pm)
        ket_0.setAlignment(Qt.Qt.AlignHCenter | Qt.Qt.AlignVCenter)
        ket_1.setAlignment(Qt.Qt.AlignHCenter | Qt.Qt.AlignVCenter)
        ket_0.setFixedWidth(25)
        ket_1.setFixedWidth(25)


        self.wigner_plot_1 = PyQtGraphImagePlot()
        self.bloch_plot = BlochPlotter()
        self.state_data = state_data
        self.wigner_max = Parameter('Max Alpha', 4, 2, 12, .25)
        update_button = Qt.QPushButton("Recalculate Wigners")
        update_button.clicked.connect(self.update_wigners)

        wigners_box = HBox((self.wigner_max, update_button))

        play_button = ButtonPair("Play", "Stop")
        play_button.clicked1.connect(self.play_sequence)
        play_button.clicked2.connect(self.stop_sequence)
        self.play_speed = Parameter("Speed", 25, 1, 1000, 1, Qt.QSpinBox)
        self.time_slider = Parameter("Time", 0, 0, len(state_data)-1, 1, lambda: Qt.QSlider(Qt.Qt.Horizontal))
        self.time_slider.valueChanged.connect(self.update_plot)
        time_box = HBox((play_button, self.play_speed))

        params_box = VBox(
            (wigners_box, time_box, self.time_slider,
             self.bloch_plot.azimuthal_slider,  self.bloch_plot.z_rotation_slider)
        )
        top_box = HBox((HBox((ket_0, self.wigner_plot_0)), HBox((self.wigner_plot_1, ket_1))))
        bottom_box = HBox((self.bloch_plot, params_box))
        self.bloch_plot.setMinimumWidth(self.width()/2)
        bottom_box.addWidget(self.bloch_plot, 10)
        bottom_box.addWidget(params_box, 1)


        self.addWidget(VBox((top_box, bottom_box)))

        self.update_wigners()

    def update_wigners(self):
        fd = self.state_data[0].dims[0][1]
        self.qubit_dms = [dm.ptrace(0) for dm in self.state_data]
        # todo: apply basis operation to qubit dms
        proj_0, proj_1 = [tensor(ket2dm(basis(2, i)), qeye(fd)) for i in (1, 0)]
        residuals_0 = [(proj_0 * dm * proj_0).ptrace(1) for dm in self.state_data]
        residuals_1 = [(proj_1 * dm * proj_1).ptrace(1) for dm in self.state_data]
        max_alpha = self.wigner_max.value()

        def process_wigners(r1, r2, max_alpha):
            wigner_xs = np.linspace(-max_alpha, max_alpha, 100)
            wigner_fn = lambda a: wigner(a, wigner_xs, wigner_xs)
            return (map(wigner_fn, r1), map(wigner_fn, r2))

        def processing_complete(res):
            self.data_0, self.data_1 = res
            self.update_plot()
            self.wigners_complete.emit()
            win.statusBar().showMessage("Wigners Finished", 2000)

        args = residuals_0, residuals_1, max_alpha
        run_in_process(process_wigners, processing_complete, args)
        self.calculating_wigners.emit()
        win.statusBar().showMessage("Calculating Wigners")


    def update_plot(self):
        v = self.time_slider.value()
        self.wigner_plot_0.plot(self.data_0[v])
        self.wigner_plot_1.plot(self.data_1[v])
        self.bloch_plot.set_state(self.qubit_dms[v])

    def play_sequence(self):
        self.time_slider.setValue(0)
        self.play_timer = Qt.QTimer()
        self.play_timer.setInterval(1000 / self.play_speed.value())
        self.play_timer.timeout.connect(self.increment_plot)
        self.play_timer.start()

    def stop_sequence(self):
        self.play_timer.stop()

    def increment_plot(self):
        v = (self.time_slider.value() + 1) % len(self.state_data)
        self.time_slider.setValue(v)

class ComputationsListModel(NamedListModel):
    type_name = "Computation"

class ComputationsListView(NamedListView):
    list_model_class = ComputationsListModel

class SequencePlotter(Qt.QSplitter):
    thread_is_running = Qt.pyqtSignal()
    thread_is_stopped = Qt.pyqtSignal()
    def __init__(self):
        super(SequencePlotter, self).__init__(Qt.Qt.Horizontal)
        self.editor = SequenceEditor()
        self.viewer = ComputationsListView()
        compute_button = Qt.QPushButton("Compute Selected Sequence")
        compute_button.clicked.connect(self.compute_selected)
        compute_hamiltonian_button = Qt.QPushButton("Compute Hamiltonian")
        compute_hamiltonian_button.clicked.connect(self.compute_hamiltonian)
        self.compute_hamiltonian_time = Parameter("Time", 10, 1, 1000, 1, Qt.QSpinBox)
        compute_hamiltonian_box = HBox((compute_hamiltonian_button, self.compute_hamiltonian_time))
        self.editor.hamiltonian_list.insertWidget(1, compute_hamiltonian_box)
        self.editor.sequence_list.addWidget(compute_button)

        #self.addWidget(VBox((self.viewer, compute_button, compute_hamiltonian_box)))
        self.addWidget(self.viewer)
        self.addWidget(self.editor)

        self.viewer.model.dataChanged.connect(self.viewer.hide_if_empty)
        self.viewer.hide_if_empty()

    def compute_selected(self):
        item = self.editor.sequence_list.current_item
        self.compute_item(item.name, item.model)

    def compute_item(self, name, model):
        name += "_1"
        fock_dim = self.editor.fock_dim.value()
        timestep = self.editor.timestep.value()
        initial_alpha = self.editor.initial_alpha.value()
        steps = model.get_steps(fock_dim, timestep)
        res0 = coherent_dm(fock_dim, initial_alpha)
        qubit0 = ket2dm((basis(2, 0) + basis(2, 1)) / np.sqrt(2))
        psi0 = tensor(qubit0, res0)
        def add_to_viewer(r):
            item = WignerPlotter(name, r)
            item.wigners_complete.connect(lambda: self.viewer.add_item(item))
            win.statusBar().showMessage("Computing Wigners")
        args = (steps, fock_dim, psi0, timestep)
        run_in_process(to_state_list, add_to_viewer, args)
        #self.thread_is_running.emit()
        win.statusBar().showMessage("Computing States")

    def compute_hamiltonian(self):
        w = self.editor.hamiltonian_list.selected_widget()
        t = self.compute_hamiltonian_time.value()
        seq = Sequence()
        seq.steps.append([w, t])
        self.compute_item(w.name, seq)

class Window(Qt.QMainWindow):
    def __init__(self):
        super(Window, self).__init__()
        main = SequencePlotter()
        self.setCentralWidget(main)
        status_bar = Qt.QStatusBar()
        self.setStatusBar(status_bar)

class Worker(Qt.QObject):
    finished = Qt.pyqtSignal(name="finished")
    def __init__(self, *args):
        super(Worker, self).__init__()
        self.args = args

    def start(self):
        self.output = self.process(*self.args)
        self.finished.emit()

def run_in_thread(worker):
    thread = Qt.QThread()
    worker.moveToThread(thread)
    app.connect(thread, Qt.SIGNAL('started()'), worker.start)
    app.connect(worker, Qt.SIGNAL('finished()'), thread.quit)
    app.connect(worker, Qt.SIGNAL('finished()'), thread.deleteLater)
    return worker, thread

def run_in_process(fn, result_fn, args):
    q = Queue()
    def queued_fn(_q, *_args):
        _q.put(fn(*_args))
    p = Process(target=queued_fn, args=(q,) + args)
    p.start()
    checker = Qt.QTimer()
    checker.setInterval(50)
    def check():
        if q.empty():
            pass
        else:
            result_fn(q.get_nowait())
            checker.stop()
    checker.timeout.connect(check)
    checker.start()

if __name__ == "__main__":
    if not os.path.exists("/Users/phil/.wigner"):
        os.makedirs("/Users/phil/.wigner")

    app = Qt.QApplication([])
    win = Window()
    win.show()
    sys.exit(app.exec_())
