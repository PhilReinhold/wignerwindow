from PyQt4 import QtGui, QtCore
import numpy as np
import pyqtgraph
from qutip import sigmaz, sigmay, sigmax, propagator, qeye, num
from qt_helpers import VBox, Parameter, HorizontalSlider

radius = 300
delta = 3
xs, ys = np.mgrid[-400:400, -400:400]
rs1 = np.sqrt(xs**2 + ys**2)
gaussian = lambda mu, sig, x: np.exp(-(x-mu)**2 / (2*sig**2))

def blur_line(mu, sig, x):
    res = np.zeros_like(x)
    delta = (x - mu)**2 / sig
    res[delta < 4] =.25
    res[delta < 2] =.5
    res[delta < 1] = 1
    return res

circle = lambda r: blur_line(radius, delta, r)
c1 = circle(rs1)

join = lambda *seq: np.minimum(sum(seq), 1)

def polar_to_xyz(r, theta, phi):
    return r*np.sin(theta)*np.cos(phi), r*np.cos(theta), r*np.sin(theta)*np.sin(phi)

def dist(x1,y1, x2,y2, x3,y3): # x3,y3 is the point
    px = x2-x1
    py = y2-y1
    q = px*px + py*py
    u =  ((x3 - x1) * px + (y3 - y1) * py) / float(q)
    u[u>1] = 1
    u[u<0] = 0
    x = x1 + u * px
    y = y1 + u * py
    dx = x - x3
    dy = y - y3
    return np.sqrt(dx*dx + dy*dy)

def ray(xv, yv, width=1):
    #return gaussian(0, 1, dist(0,0, xv, yv, xs, ys))
    return blur_line(0, width, dist(0,0, xv, yv, xs, ys))

def line(xv, yv, width=1):
    return ray(xv, yv, width) + ray(-xv, -yv, width)
zline = line(0, radius)

paulis = sigmax(), sigmay(), sigmaz()

class BlochPlotter(VBox):
    def __init__(self):
        super(BlochPlotter, self).__init__()
        self.plot = pyqtgraph.ImageView()
        self.plot.setLevels(0.01, 1.0)
        self.plot.ui.histogram.hide()
        self.plot.ui.roiBtn.hide()
        self.plot.ui.normBtn.hide()
        self.azimuthal_slider = Parameter("Azimuthal", 40, 10, int(np.pi*100/2.), 1, HorizontalSlider)
        self.z_rotation_slider = Parameter("Z-Rotation", 40, -int(np.pi*100/2.), int(np.pi*100/2.), 1, HorizontalSlider)
        self.azimuthal_slider.valueChanged.connect(self.update_background)
        self.z_rotation_slider.valueChanged.connect(self.update_background)

        self.addWidgets(self.plot, self.azimuthal_slider, self.z_rotation_slider)

        self.qubit_dm = None
        self.update_background()

    def update_background(self):
        theta = self.azimuthal_slider.value() / 100.
        phi = self.z_rotation_slider.value() / 100.
        zs = ys / np.tan(theta)
        rs2 = np.sqrt(xs**2 + ys**2 + zs**2)
        c2 = circle(rs2)
        x_rad = radius
        x_line = line(x_rad*np.cos(phi), x_rad*np.sin(phi)*np.sin(theta))
        y_rad = radius
        y_line = line(-y_rad*np.sin(phi), y_rad*np.cos(phi)*np.sin(theta))
        self.background = join(c1, c2, zline, x_line, y_line)
        self.update_plot()

    def update_plot(self):
        if self.qubit_dm is None:
            im = self.background
        else:
            x, z, y = [(self.qubit_dm * s).tr().real * radius for s in paulis]
            theta = self.azimuthal_slider.value() / 100.
            phi = self.z_rotation_slider.value() / 100.
            image_x = x*np.cos(phi) - z*np.sin(phi)
            image_y = y + (x*np.sin(phi) + z*np.cos(phi))*np.sin(theta)
            im = join(self.background, ray(image_x, image_y, 5))
        self.plot.setImage(im, autoHistogramRange=False)

    def set_state(self, dm):
        self.qubit_dm = dm
        self.update_plot()


class TestBloch(BlochPlotter):
    def __init__(self):
        super(TestBloch, self).__init__()
        self.propagator = propagator(sigmaz(), .1, [])
        self.set_state(qeye(2) + sigmax())
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.propagate)
        self.timer.start()

    def propagate(self):
        self.qubit_dm *= self.propagator
        self.update_plot()

def main():
    app = QtGui.QApplication([])
    win = TestBloch()
    win.setFixedSize(500, 500)
    win.show()
    app.exec_()

if __name__ == "__main__":
    import cProfile
    cProfile.run("main()", sort="cumtime")
