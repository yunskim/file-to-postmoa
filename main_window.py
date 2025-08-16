from PyQt6.QtGui import QIcon, QAction, QColor
from PyQt6.QtWidgets import QMainWindow, QApplication, QMessageBox, QTableView, QFileDialog, QWidget
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QDate

import pathlib
import pandas as pd
import arrow
import win32com.client as win32
import textwrap
import re
import sys

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from collections.abc import Sequence
from typing import Callable, Any
from pypdf import PdfReader

pdfmetrics.registerFont(TTFont("맑은고딕", "malgun.ttf"))
pdfmetrics.registerFont(TTFont("맑은고딕-bold", "malgunbd.ttf"))

A4_width, A4_height = A4
A4_width_in_mm = int(A4_width / mm)
A4_height_in_mm = int(A4_height / mm)

FILTERS = [
    "Excel (*.xlsx)",
    "Pdf (*.pdf)",
    "All Files (*)",
]

# 우편모아 엑셀 출력용
NORMAL_MAIL_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['규격*', '중량*', '통수*', '수취인*', '우편번호*', '기본주소*', '상세주소', '휴대폰', '문서번호', '문서제목', '비고'])
REGISTERED_MAIL_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['수수료*', '환부*', '규격*', '중량', '수취인*', '우편번호*', '기본주소*', '상세주소', '휴대폰', '문서번호', '문서제목', '비고'])
SELECTIVE_REGISTERED_MAIL_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['수수료*', '규격*', '중량', '수취인*', '우편번호*', '기본주소*', '상세주소', '휴대폰', '문서번호', '문서제목', '비고'])

# 화면에 보이는 테이블
PDF_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['이름', '우편번호', '주소', '제목', '차량번호', '비고'])


class ColumnReplacer:
    def __init__(self,
                 target_df_column: str,
                 replacer: str,
                 extra_pattern: str = '',
                 value_for_extra_pattern: str = '', ) -> None:
        self.target_df_column = target_df_column
        self.replacer = replacer
        self.extra_pattern = extra_pattern
        self.value_for_extra_pattern = value_for_extra_pattern

    def __iter__(self):
        return iter(self.__dict__.values())

    def replace(self, target_df: pd.DataFrame, data_df: pd.DataFrame) -> None:
        """
        target_df의 데이터를 data_df의 데이터를 replacer에 적용한 값으로 업데이트 한다

        :param target_df: 옮길 대상 dataframe
        :param data_df: 사용할 data가 저장된 dataframe
        :param extra_pattern: 추가로 대체될 pattern
        :param value_for_extra_pattern: 추가로 대체할  value
        """

        if self.replacer:
            replacing_data_df_columns = re.findall(r'{(\w+)}',
                                                   self.replacer)  # data_df의 column이름, replacer에서 sub할 data_df의 column names
            print(f'{replacing_data_df_columns=}')

            replaced = [self.replacer for _ in
                        range(len(data_df))]  # target_df_column 하나에 data_df의 여러 columns이 결합될 수 있음. placeholder를 생성함

            if replacing_data_df_columns:
                for replacing_data_df_column in replacing_data_df_columns:
                    print(f'{replacing_data_df_column=}')
                    for i, (_new, r) in enumerate(zip(data_df[replacing_data_df_column], replaced)):
                        if _new:
                            # data_df가 비어있지 않으면 replace
                            replaced[i] = re.sub("{" + replacing_data_df_column + "}", _new, r)
                        else:  # data_df가 비어있으면 template만 삭제
                            replaced[i] = re.sub("{" + replacing_data_df_column + "}", '', r)

                        if self.extra_pattern:
                            # 전화번호에 들어있는 -을 제거하려고 추가 처리
                            replaced[i] = re.sub(self.extra_pattern, self.value_for_extra_pattern, replaced[i])

            target_df[self.target_df_column] = replaced


# pdf_df를 우편모아 df로 변환하는 mappings
PDF_TO_POSTMOA_NORMAL_MAIL_EXCEL_COLUMNS: Sequence[ColumnReplacer] = (
    ColumnReplacer('수취인*', '{이름}'),
    ColumnReplacer('우편번호*', '{우편번호}'),
    ColumnReplacer('기본주소*', '{주소}'),
    ColumnReplacer('문서제목', '{제목}'),
    ColumnReplacer('비고', '{차량번호}, {비고}'),
    ColumnReplacer('규격*', '규격'),
    ColumnReplacer('통수*', '1'),
    ColumnReplacer('중량*', '25'),
)
PDF_TO_POSTMOA_REGISTERED_MAIL_EXCEL_COLUMNS: Sequence[ColumnReplacer] = (
    ColumnReplacer('수취인*', '{이름}'),
    ColumnReplacer('우편번호*', '{우편번호}'),
    ColumnReplacer('기본주소*', '{주소}'),
    ColumnReplacer('문서제목', '{제목}'),
    ColumnReplacer('비고', '{차량번호}, {비고}'),
    ColumnReplacer('규격*', '규격'),
    ColumnReplacer('중량', '25'),
    ColumnReplacer('수수료*', '보통'),
    ColumnReplacer('환부*', '환부불능'),
)
PDF_TO_POSTMOA_SELECTIVE_REGISTERED_MAIL_EXCEL_COLUMNS: Sequence[ColumnReplacer] = (
    ColumnReplacer('수수료*', '보통'),
    ColumnReplacer('규격*', '규격'),
    ColumnReplacer('중량', '25'),
    ColumnReplacer('수취인*', '{이름}'),
    ColumnReplacer('우편번호*', '{우편번호}'),
    ColumnReplacer('기본주소*', '{주소}'),
    ColumnReplacer('문서제목', '{제목}'),
    ColumnReplacer('비고', '{차량번호}, {비고}'),
)
# pdf_df를 windowed_envelope_df로 변환하는 mappings
PDF_TO_WINDOWED_ENVELOPE_COLUMNS: Sequence[ColumnReplacer] = (
    ColumnReplacer('문서제목', '{제목}'),
    ColumnReplacer('우편번호', '{우편번호}'),
    ColumnReplacer('기본주소', '{주소}'),
    ColumnReplacer('수취인', '{이름}'),
    ColumnReplacer('문서본문', '{차량번호}, {비고}'),
)

NAME = re.compile(r'수신\s+(.+)(?=\s+귀하\s+\(우\d+\s+.+\)\n\(경유\))', re.DOTALL)  # 이름
ZIPCODE = re.compile(r'수신\s+.+\s+귀하\s+\(우(\d+)\s+.+\)\n\(경유\)', re.DOTALL)  # zipcode
ADDRESS = re.compile(r'수신\s+.+\s+귀하\s+\(우\d+\s+(.+)\)\n\(경유\)', re.DOTALL)  # 주소
TITLE = re.compile(r'제목\s+(.+)')  # 제목
BIKE_NUMBER = re.compile(r'(?<=차량번호).+\n(\w+\n?\w\d{4})', re.DOTALL)  # 이륜차번호
DUE_DATE = re.compile(r'\n(\d+\.\d+\.\d+\.)')  # 제출기한


def extract_pattern_from_pdf(pdf: pathlib.Path | str, pattern: re.Pattern) -> str:
    pdf = pathlib.Path(pdf).resolve()

    text = ''

    for page in PdfReader(pdf).pages:
        text += page.extract_text()

    try:
        ret = pattern.search(text).group(1)  # 첫번째 pattern
    except AttributeError:
        ret = ''

    ret = ret.strip().replace('\n', '')
    return ret


def yyyymmdd_to_yyyy_mm_dd(date: str) -> str:
    return str(arrow.get(date, 'YYYYMMDD').format('YYYY-MM-DD'))


class DataFrameModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent: QModelIndex = ...) -> int:
        ret = 0
        try:
            ret = self._data.shape[0]
        except AttributeError:
            ret = 0

        return ret

    def columnCount(self, parent: QModelIndex = ...) -> int:
        ret = 0
        try:
            ret = self._data.shape[1]
        except AttributeError:
            ret = 0

        return ret

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
                ret = str(self._data.index[section] + 1)

        return ret

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled

        return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PDF to Postmoa Converter")
        self.setWindowIcon(QIcon("icon.png"))
        self.setMinimumSize(1200, 900)

        # 파일에서 주소를 추출해 보여주는 table을 central widget으로 설정함
        self.table = QTableView()

        self.setCentralWidget(self.table)

        self.data: pd.DataFrame = PDF_EMPTY_DATAFRAME.copy(deep=True)
        self.model = None

        self.set_table(self.data)

        # menu 추가
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        open_file_action = QAction('Open', self)

        ## open file action 추가
        open_file_action.setShortcut('Ctrl+O')
        open_file_action.setStatusTip('Open File')
        open_file_action.triggered.connect(self.open_file_dialog)

        file_menu.addAction(open_file_action)
        # status bar
        self.set_status_bar('Ready')

        # config
        self.config = None  # 실제 config는 open_file_dialog()에서 결정함

    def set_status_bar(self, text: str):
        self.statusBar().showMessage(text)

    def set_table(self, data: pd.DataFrame):
        """
        df를 받아서 table에 연결한다

        :param data:
        :return:
        """
        self.data = data
        self.model = DataFrameModel(data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

        self.set_status_bar('table reset')

    def clear_table(self):
        self.data = PDF_EMPTY_DATAFRAME.copy(deep=True)
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

        self.set_status_bar('table cleared')

    def reset_table(self):
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

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

    def open_file_dialog(self):
        file, filter_used = QFileDialog.getOpenFileName(parent=self,
                                                        caption='open file',
                                                        directory=r'c:\Users\User\Desktop\작업용 임시 폴더',
                                                        filter=';;'.join(FILTERS),
                                                        initialFilter=FILTERS[1])  # default는 pdf!!!

        file = pathlib.Path(file).resolve()

        match file.suffix:
            case '.pdf':
                title = extract_pattern_from_pdf(file, TITLE)
                zipcode = extract_pattern_from_pdf(file, ZIPCODE)
                name = extract_pattern_from_pdf(file, NAME)
                address = extract_pattern_from_pdf(file, ADDRESS)
                bike_number = extract_pattern_from_pdf(file, BIKE_NUMBER)
                due_date = extract_pattern_from_pdf(file, DUE_DATE)

                self.data.loc[len(self.data)] = [name, zipcode, address, title, bike_number, due_date]
                self.reset_table()

            case '.xlsx' | '.xls':
                print(f'{file=}')
            case _:
                pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
