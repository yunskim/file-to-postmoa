import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QApplication


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hwp, Hwpx, Odt, Xls, Xlsx to Postmoa Converter")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(300, 300, 600, 400)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
