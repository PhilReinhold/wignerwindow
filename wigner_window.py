import sys
from PyQt4 import Qt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from qutip import coherent_dm, propagator, num, destroy, mat2vec, vec2mat, Qobj, wigner
import numpy as np
from IPython.core.debugger import Tracer

class WignerWindow(Qt.QMainWindow):
    """docstring for WignerWindow"""
    def __init__(self):
        super(WignerWindow, self).__init__()
        self.main_widget = Qt.QWidget()
        self.main_widget.setLayout(Qt.QVBoxLayout())
        self.plots_box = Qt.QWidget()
        self.params_box = Qt.QWidget()
        self.controls_box = Qt.QWidget()
        boxes = (self.plots_box, self.params_box, self.controls_box)
        for b in boxes:
            self.main_widget.layout().addWidget(b)
        self.setCentralWidget(self.main_widget)
        self.wigner_figure = Figure()
        self.wigner_axes = self.wigner_figure.add_subplot(111)
        self.wigner_axes.hold(False)
        self.wigner_canvas = FigureCanvas(self.wigner_figure)
        self.plots_box.setLayout(Qt.QHBoxLayout())
        self.plots_box.layout().addWidget(self.wigner_canvas)
        self.frequency_param = Qt.QDoubleSpinBox()
        self.kerr_param = Qt.QDoubleSpinBox()
        self.decay_param = Qt.QDoubleSpinBox()
        self.timestep_param = Qt.QDoubleSpinBox()
        self.initial_state_param = Qt.QDoubleSpinBox()
        self.fock_dim_param = Qt.QSpinBox()
        params = [
            self.frequency_param, self.kerr_param, self.decay_param,
            self.timestep_param, self.initial_state_param, self.fock_dim_param
        ]
        param_labels = ["Frequency",  "Kerr",       "Decay",      "Timestep",      "Initial Alpha", "Fock Dimension"]
        param_ranges = [(.1, 3, .01), (0, .3, .01), (0, .3, .01), (.01, 1, .01),  (0, 3, .1),      (3, 20, 1)]
        param_defaults = [ .3,         0,            0,            .05,            1,               8]
        self.params_box.setLayout(Qt.QFormLayout())
        for p, pl, (pmin, pmax, pstep), pd in zip(params, param_labels, param_ranges, param_defaults):
            p.setRange(pmin, pmax)
            p.setSingleStep(pstep)
            p.setValue(pd)
            self.params_box.layout().addRow(pl, p)
        for p in (self.frequency_param, self.kerr_param, self.decay_param, self.timestep_param, self.fock_dim_param):
            p.valueChanged.connect(self.update_propagator)
        for p in (self.initial_state_param, self.fock_dim_param):
            p.valueChanged.connect(self.initialize)
        self.reset_button = Qt.QPushButton('Reset')
        self.start_button = Qt.QPushButton('Start')
        self.stop_button = Qt.QPushButton('Stop')
        controls = (self.reset_button, self.start_button, self.stop_button)
        control_fns = (self.initialize, self.start, self.stop)
        self.controls_box.setLayout(Qt.QHBoxLayout())
        for c, f in zip(controls, control_fns):
            self.controls_box.layout().addWidget(c)
            c.clicked.connect(f)
        self.stop_button.hide()

        self.wigner_xs = np.linspace(-6, 6, 100)

        self.initialize()
        self.update_propagator()


    def plot(self):
        dm = Qobj(vec2mat(self.dm_vec))
        wigner_array = wigner(dm, self.wigner_xs, self.wigner_xs)
        self.wigner_axes.imshow(wigner_array)
        self.wigner_canvas.draw()

    def update_propagator(self):
        w0 = self.frequency_param.value()
        K = self.kerr_param.value()
        kappa = self.decay_param.value()
        dt = self.timestep_param.value()
        fd = self.fock_dim_param.value()
        n = num(fd)
        a = destroy(fd)
        H = w0*n + K*n*n
        self.prop = propagator(H, dt, [kappa*a]).data

    def initialize(self):
        alpha = self.initial_state_param.value()
        fd = self.fock_dim_param.value()
        self.dm_vec = mat2vec(coherent_dm(fd, alpha).full())
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
