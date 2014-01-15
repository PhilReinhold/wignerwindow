import sys
from PyQt4 import Qt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from qutip import coherent_dm, propagator, num, destroy, mat2vec, vec2mat, Qobj, wigner
from qutip import qeye, sigmaz, sigmam, tensor, basis, ket2dm, ptrace
import numpy as np
from IPython.core.debugger import Tracer

class WignerWindow(Qt.QMainWindow):
    """docstring for WignerWindow"""
    def __init__(self):
        super(WignerWindow, self).__init__()
        main_widget = Qt.QWidget()
        main_widget.setLayout(Qt.QHBoxLayout())
        params_controls_box = Qt.QWidget()
        plots_box = Qt.QWidget()
        params_box = Qt.QWidget()
        controls_box = Qt.QWidget()
        params_controls_box.setLayout(Qt.QVBoxLayout())
        params_controls_box.layout().addWidget(params_box)
        params_controls_box.layout().addWidget(controls_box)
        main_widget.layout().addWidget(plots_box)
        main_widget.layout().addWidget(params_controls_box)
        self.setCentralWidget(main_widget)
        plots_box.setLayout(Qt.QHBoxLayout())
        self.plot_boxes, self.bar_set = [], []
        self.wigner_figures, self.wigner_axes, self.wigner_canvases = [], [], []
        for _ in range(2):
            self.wigner_figures.append(Figure())
            self.wigner_axes.append(self.wigner_figures[-1].add_subplot(111))
            self.wigner_axes[-1].hold(False)
            self.wigner_canvases.append(FigureCanvas(self.wigner_figures[-1]))
            self.bar_set.append([Qt.QProgressBar() for _ in range(3)])
            self.plot_boxes.append(Qt.QWidget())
            self.plot_boxes[-1].setLayout(Qt.QVBoxLayout())
            self.plot_boxes[-1].layout().addWidget(self.wigner_canvases[-1])
            for b in self.bar_set[-1]:
                b.setRange(0, 100)
                self.plot_boxes[-1].layout().addWidget(b)
        self.plot_widgets = zip(self.wigner_axes, self.wigner_canvases, self.bar_set)
        for b in self.plot_boxes:
            plots_box.layout().addWidget(b)
        self.frequency_param = Qt.QDoubleSpinBox()
        self.q_frequency_param = Qt.QDoubleSpinBox()
        self.chi_param = Qt.QDoubleSpinBox()
        self.kerr_param = Qt.QDoubleSpinBox()
        self.decay_param = Qt.QDoubleSpinBox()
        self.timestep_param = Qt.QDoubleSpinBox()
        self.initial_state_param = Qt.QDoubleSpinBox()
        self.fock_dim_param = Qt.QSpinBox()
        self.params = {
            "Cavity Frequency": (Qt.QDoubleSpinBox(), (0, 3, .01, 0)),
            "Qubit Frequency": (Qt.QDoubleSpinBox(), (0, .3, .01, 0)),
            "Chi": (Qt.QDoubleSpinBox(), (0, 3, .01, 0)),
            "Kerr": (Qt.QDoubleSpinBox(), (0, .3, .01, 0)),
            "Cavity Decay": (Qt.QDoubleSpinBox(), (0, .3, .01, 0)),
            "Qubit Decay": (Qt.QDoubleSpinBox(), (0, .3, .01, 0)),
            "Timestep": (Qt.QDoubleSpinBox(), (0.01, .3, .01, .2)),
            "Initial Alpha": (Qt.QDoubleSpinBox(), (0, 2, .1, 1)),
            "Initial Qubit Angle": (Qt.QDoubleSpinBox(), (0, 1, 0.01, .5)),
            "Fock Dimension": (Qt.QSpinBox(), (4, 20, 1, 5)),
            "Max Alpha": (Qt.QDoubleSpinBox(), (1, 10, .5, 4)),
            "Alpha Points": (Qt.QSpinBox(), (25, 1000, 5, 100)),
        }

        params_box.setLayout(Qt.QFormLayout())
        for pl, (p, (pmin, pmax, pstep, pd)) in self.params.items():
            p.setRange(pmin, pmax)
            p.setSingleStep(pstep)
            p.setValue(pd)
            params_box.layout().addRow(pl, p)

        self.reset_button = Qt.QPushButton('Reset')
        self.prop_button = Qt.QPushButton('Change Propagator')
        self.start_button = Qt.QPushButton('Start')
        self.stop_button = Qt.QPushButton('Stop')
        controls = (self.reset_button, self.prop_button, self.start_button, self.stop_button)
        control_fns = (self.initialize, self.update_propagator, self.start, self.stop)
        controls_box.setLayout(Qt.QVBoxLayout())
        for c, f in zip(controls, control_fns):
            controls_box.layout().addWidget(c)
            c.clicked.connect(f)
        self.stop_button.hide()


        self.initialize()
        self.update_propagator()

    def get(self, label):
        return self.params[label][0].value()

    def plot(self):
        fd = self.get("Fock Dimension")
        ma = self.get("Max Alpha")
        na = self.get("Alpha Points")
        wigner_xs = np.linspace(-ma, ma, na)
        dm = Qobj(vec2mat(self.dm_vec), dims=[[2, fd], [2, fd]])
        projectors = [tensor(ket2dm(basis(2,i)), qeye(fd)) for i in reversed(range(2))]
        dms = [p * dm * p for p in projectors]
        (pop0, coherence), (_, pop1) = ptrace(dm, 0).full()
        pops = [pop0, pop1]
        coherence /= np.sqrt(pop0 * pop1)
        resids = [ptrace(d, 1) for d in dms]
        wigner_arrays = [wigner(d, wigner_xs, wigner_xs) for d in resids]
        for (axis, canvas, bars), pop, arr in zip(self.plot_widgets, pops, wigner_arrays):
            axis.imshow(arr)
            canvas.draw()
            bars[0].setValue(np.abs(pop) * 100)
            bars[1].setValue(np.abs(coherence) * 100)
            tau = 2*np.pi
            bars[2].setValue((np.angle(coherence) % tau) * 100 / tau)

    def update_propagator(self):
        w0 = self.get('Cavity Frequency')
        wq = self.get('Qubit Frequency')
        chi = self.get("Chi")
        K = self.get('Kerr')
        kappa = self.get("Cavity Decay")
        gamma = self.get("Qubit Decay")
        dt = self.get("Timestep")
        fd = self.get("Fock Dimension")

        n = tensor(qeye(2), num(fd))
        a = tensor(qeye(2), destroy(fd))
        sz = tensor(sigmaz(), qeye(fd))
        sm = tensor(sigmam(), qeye(fd))
        H = w0*n + K*n*n + (wq/2.)*sz + chi*n*sz
        self.prop = propagator(H, dt, [kappa*a, gamma*sm]).data

    def initialize(self):
        alpha = self.get("Initial Alpha")
        angle = self.get("Initial Qubit Angle")
        qubit_state = ket2dm(np.sqrt(angle) * basis(2, 0) + np.sqrt(1 - angle) * basis(2, 1))
        fd = self.get("Fock Dimension")
        cavity_state = coherent_dm(fd, alpha)
        self.dm_vec = mat2vec(tensor(qubit_state, cavity_state).full())
        self.update_propagator()
        self.plot()

    def update_state(self):
        self.dm_vec = self.prop * self.dm_vec
        self.plot()

    def start(self):
        self.start_button.hide()
        self.stop_button.show()
        self.update_timer = Qt.QTimer()
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self.update_state)
        self.update_timer.start()

    def stop(self):
        self.start_button.show()
        self.stop_button.hide()
        self.update_timer.stop()

def main():
    app = Qt.QApplication([])
    win = WignerWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
