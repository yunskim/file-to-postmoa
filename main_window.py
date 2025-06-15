import sys
from typing import Any
import re
import io

import pywintypes
from PyQt6.QtGui import QIcon, QAction, QColor
from PyQt6.QtWidgets import QMainWindow, QApplication, QTableView, QFileDialog, QMessageBox
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

import pathlib
import pandas as pd
from typing import AnyStr
from pypdf import PdfReader
import arrow
import xlwings as xw

FILTERS = [
    "Hwp (*.hwp *.hwpx *.odt )",
    "Excel (*.xlsx)",
    "Pdf (*.pdf)",
    "All Files (*)",
]

NAME_ZIPCODE_ADDRESS = re.compile(r'수신\s+(.+)\s+귀하\s+\(우(\d+)\s+(.+)\)\n\(경유\)', re.DOTALL)  # 이름, zipcode, 주소
TITLE = re.compile(r'제목\s+(.+)')
BIKE_NUMBER = re.compile(r'\n(.+)\n(\w)(\d{4})\n')
DUE_DATE = re.compile(r'\n(\d+\.\d+\.\d+\.)')

COLUMNS_EN_TO_KR = dict(
    name='이름',
    zipcode='우편번호',
    address='주소',
    title='제목',
    bike_number='차량번호',
    due_date='제출기한',
)

COLUMNS_KR_TO_EN = {v: k for k, v in COLUMNS_EN_TO_KR.items()}

NORMAL_MAIL_EMPTY_DATAFRAME = pd.DataFrame(columns=['<UNK>', '<UNK>', '<UNK>'])
REGISTERED_MAIL_EMPTY_DATAFRAME = pd.DataFrame(columns=['<UNK>', '<UNK>', '<UNK>'])
DATA_EMPTY_DATAFRAME = pd.DataFrame(columns=list(COLUMNS_KR_TO_EN.keys()))


class DataFrameModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame | None, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent: QModelIndex = ...) -> int:
        if self._data:
            return self._data.shape[0]
        return 0

    def columnCount(self, parent: QModelIndex = ...) -> int:
        if self._data:
            return self._data.shape[1]
        return 0

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

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        ret = None
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                ret = str(self._data.columns[section])
            if orientation == Qt.Orientation.Vertical:
                ret = str(self._data.index[section])

        return ret


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pdf to Postmoa Converter")
        self.setWindowIcon(QIcon("icon.png"))
        self.setMinimumSize(1200, 900)

        # 파일에서 주소를 추출해 보여주는 table을 central widget으로 설정함
        self.table = QTableView()

        self.setCentralWidget(self.table)

        self.model: DataFrameModel | None = None
        self.data: pd.DataFrame | None = DATA_EMPTY_DATAFRAME

        # empty DataFrame
        # self.data = pd.DataFrame([[1, 2, 3], [4, 5, 6]], index=['1', '2'], columns=['A', 'B', 'C'])
        # self.model = DataFrameModel(self.data)
        # self.table.setModel(self.model)

        # menu 추가
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        open_file_action = QAction('Open', self)

        ## open file action 추가
        open_file_action.setShortcut('Ctrl+O')
        open_file_action.setStatusTip('Open File')
        open_file_action.triggered.connect(self.open_file_dialog)

        file_menu.addAction(open_file_action)

        ## conver to postmoa action 추가
        convert_to_postmoa_action = QAction('Save PostMoa', self)
        file_menu.addAction(convert_to_postmoa_action)

        convert_to_postmoa_action.setShortcut('Ctrl+C')
        convert_to_postmoa_action.setStatusTip('Convert to PostMoa')
        convert_to_postmoa_action.triggered.connect(self.convert_to_postmoa_dialog)

        ## clear table action 추가
        clear_table_action = QAction('Clear Table', self)
        file_menu.addAction(clear_table_action)
        clear_table_action.setStatusTip('Clear Table')
        clear_table_action.setShortcut('Ctrl+N')
        clear_table_action.triggered.connect(self.clear_table)

        self.setMenuBar(menu_bar)

    def clear_table(self):
        self.data = None
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

    def reset_table(self):
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

    def append_data_to_table(self, df: pd.DataFrame):
        try:
            self.data = self.data.append(df)

        except AttributeError as err:
            print(err)

        self.reset_table()  # data가 바뀌면 table에 변화를 반영해야 함

    def convert_to_postmoa_dialog(self):
        try:
            directory = QFileDialog.getExistingDirectory(self, 'Save PostMoa Directory',
                                                         directory=r'c:\Users\User\Desktop\작업용 임시 폴더',
                                                         options=QFileDialog.Option.ShowDirsOnly)

            directory = pathlib.Path(directory)
            save_to_postmoa_normal_mail_path = directory / '{datetime}_normal_mail.xls'.format(
                datetime=arrow.now().format('YYYY-MM-DD HHmmss'))
            save_to_postmoa_registered_mail_path = directory / '{datetime}_registered_mail.xls'.format(
                datetime=arrow.now().format('YYYY-MM-DD HHmmss'))

            self.save_to_postmoa_normal_mail(save_to_postmoa_normal_mail_path)
            self.save_to_postmoa_registered_mail(save_to_postmoa_registered_mail_path)

        except pywintypes.com_error as err:
            print(err)
            QMessageBox.critical(self, 'Error', 'table is not converted to postmoa')
            return

    def save_to_postmoa_normal_mail(self, target: pathlib.Path | str):
        target = pathlib.Path(target)
        df_normal_mail = NORMAL_MAIL_EMPTY_DATAFRAME.copy(deep=True)

        if any(self.data):
            print(f'{self.data}')
            df_normal_mail['이름'] = self.data['이름']
            df_normal_mail['주소'] = self.data['주소']
            df_normal_mail['우편번호'] = self.data['우편번호']

        print(f'{df_normal_mail}')

    def save_to_postmoa_registered_mail(self, target: pathlib.Path | str):
        target = pathlib.Path(target)
        df_registered_mail = REGISTERED_MAIL_EMPTY_DATAFRAME.copy(deep=True)

        if any(self.data):
            df_registered_mail['이름'] = self.data['이름']
            df_registered_mail['주소'] = self.data['주소']
            df_registered_mail['우편번호'] = self.data['우편번호']

        print(f'{self.data}')
        print(f'{df_registered_mail}')

    def open_file_dialog(self):
        files, filter_used = QFileDialog.getOpenFileNames(parent=self,
                                                          caption='open file',
                                                          directory=None,
                                                          filter=';;'.join(FILTERS),
                                                          initialFilter=FILTERS[2])  # default는 pdf!!!

        df = pd.DataFrame(columns=list(COLUMNS_KR_TO_EN.keys()))

        files = [pathlib.Path(file) for file in files]
        for file in files:
            if file.suffix in ('.pdf',):
                try:
                    name, zipcode, address = self.extract_pattern_from_pdf(file, NAME_ZIPCODE_ADDRESS)
                    title = self.extract_pattern_from_pdf(file, TITLE)
                    title = ''.join(title)
                    bike_number = self.extract_pattern_from_pdf(file, BIKE_NUMBER)
                    bike_number = ''.join(bike_number)
                    due_date = self.extract_pattern_from_pdf(file, DUE_DATE)
                    due_date = ''.join(due_date)
                    df.loc[len(df)] = [name, zipcode, address, title, bike_number, due_date]
                except AttributeError as err:
                    print(err)

        self.append_data_to_table(df)  # 새로은 pdf를 읽어 기존 테이블에 추가

    def closeEvent(self, event):
        # Alternative to "QMessageBox.Yes" for PyQt6
        # https://stackoverflow.com/questions/65735260/alternative-to-qmessagebox-yes-for-pyqt6
        reply = QMessageBox.question(
            self,
            'Close Confirmation',
            'Are you sure you want to close the window?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def extract_pattern_from_pdf(pdf: pathlib.Path | str, pattern: re.Pattern) -> tuple[AnyStr, ...]:
        pdf = pathlib.Path(pdf).resolve()
        text = ''

        for page in PdfReader(pdf).pages:
            text += page.extract_text()

        ret = pattern.search(text).groups()  # 일치하는 모든 str
        return ret


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
