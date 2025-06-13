import sys
from typing import Any
import re

from PyQt6.QtGui import QIcon, QAction, QColor
from PyQt6.QtWidgets import QMainWindow, QApplication, QTableView, QFileDialog
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

import pathlib
import pandas as pd
from pypdf import PdfReader

FILTERS = [
    "Hwp (*.hwp *.hwpx *.odt )",
    "Excel (*.xlsx)",
    "Pdf (*.pdf)",
    "All Files (*)",
]

ADDRESS = re.compile(r'수신\s+(.+)\s+귀하\s+\(우(\d+)\s+(.+)\)\n\(경유\)', re.DOTALL)  # 이름, zipcode, 주소


class DataFrameModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame | None, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return self._data.shape[0]

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return self._data.shape[1]

    def data(self, index: QModelIndex, role: int = ...) -> Any:
        ret = None
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            ret = self._data.iat[index.row(), index.column()]
            ret = str(ret)

        if role == Qt.ItemDataRole.DecorationRole:
            value = self._data.iat[index.row(), index.column()]
            if not value or value == 'None':
                ret = QColor('red')

        return ret

    def setData(self, index: QModelIndex, value: Any, role: int = ...) -> bool:
        # https: // www.pythonguis.com / faq / qtableview - cell - edit /
        if role == Qt.ItemDataRole.EditRole:
            self._data.iat[index.row(), index.column()] = value
            return True

        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hwp, Hwpx, Odt, Xls, Xlsx to Postmoa Converter")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(300, 300, 600, 400)

        # 파일에서 주소를 추출해 보여주는 table을 central widget으로 설정함
        self.table = QTableView()
        self.setCentralWidget(self.table)

        # empty DataFrame
        self.data = pd.DataFrame([[1, 2, 3], [4, 5, 6]], index=['1', '2'], columns=['A', 'B', 'C'])
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)

        # menu 추가
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        file_open_action = QAction('Open File', self)
        file_menu.addAction(file_open_action)

        file_open_action.setShortcut('Ctrl+O')
        file_open_action.setStatusTip('Open File')
        file_open_action.triggered.connect(self.open_file_dialog)

        self.setMenuBar(menu_bar)

    def reset_table(self, data: pd.DataFrame):
        self.data = data
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)

    def open_file_dialog(self):
        files, filter_used = QFileDialog.getOpenFileNames(parent=self,
                                                          caption='open file',
                                                          directory=None,
                                                          filter=';;'.join(FILTERS),
                                                          initialFilter=FILTERS[2])  # default는 pdf!!!

        files = [pathlib.Path(file) for file in files]
        for file in files:
            if file.suffix in ('.pdf',):
                print(self.extract_text_from_pdf(file))

        self.reset_table(self.data)

    @staticmethod
    def extract_text_from_pdf(pdf: pathlib.Path | str) -> tuple[str, str, str] | None:
        pdf = pathlib.Path(pdf).resolve()
        text = ''

        for page in PdfReader(pdf).pages:
            text += page.extract_text()

        name, zipcode, address = ADDRESS.search(text).groups()  # 일치하는 모든 str
        return name, zipcode, address


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
