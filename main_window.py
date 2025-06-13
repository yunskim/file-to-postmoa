import sys

from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QMainWindow, QApplication, QTableView, QFileDialog

FILTERS = [
    "Excel Files (*.xlsx)",
    "All Files (*)",
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hwp, Hwpx, Odt, Xls, Xlsx to Postmoa Converter")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(300, 300, 600, 400)

        # 파일에서 주소를 추출해 보여주는 table을 central widget으로 설정함
        self.table_view = QTableView(self)
        self.setCentralWidget(self.table_view)

        # menu 추가
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        file_open_action = QAction('Open File', self)
        file_menu.addAction(file_open_action)

        file_open_action.setShortcut('Ctrl+O')
        file_open_action.setStatusTip('Open File')
        file_open_action.triggered.connect(self.open_file_dialog)

        self.setMenuBar(menu_bar)

    def open_file_dialog(self):
        files = QFileDialog.getOpenFileNames(parent=self,
                                             caption='open file',
                                             directory=None,
                                             filter=';;'.join(FILTERS),
                                             initialFilter=FILTERS[0])


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
