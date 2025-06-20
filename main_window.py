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
import win32com.client as win32
import textwrap

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# print(A4)

pdfmetrics.registerFont(TTFont("맑은고딕", "malgun.ttf"))
pdfmetrics.registerFont(TTFont("맑은고딕-bold", "malgunbd.ttf"))

A4_width, A4_height = A4
A4_width_in_mm = int(A4_width / mm)
A4_height_in_mm = int(A4_height / mm)

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

NORMAL_MAIL_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['규격*', '중량*', '통수*', '수취인*', '우편번호*', '기본주소*', '상세주소', '휴대폰', '문서번호', '문서제목', '비고'])
REGISTERED_MAIL_EMPTY_DATAFRAME = pd.DataFrame(
    columns=['수수료*', '환부*', '규격*', '중량', '수취인*', '우편번호*', '기본주소*', '상세주소', '휴대폰', '문서번호', '문서제목', '비고'])

DATA_EMPTY_DATAFRAME = pd.DataFrame(columns=list(COLUMNS_KR_TO_EN.keys()))


class DataFrameModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame | None, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent: QModelIndex = ...) -> int:
        if any(self._data):
            return self._data.shape[0]
        return 0

    def columnCount(self, parent: QModelIndex = ...) -> int:
        if any(self._data):
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

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled

        return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable


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
        save_to_postmoa_action = QAction('Save', self)
        file_menu.addAction(save_to_postmoa_action)

        save_to_postmoa_action.setShortcut('Ctrl+S')
        save_to_postmoa_action.setStatusTip('Convert to PostMoa')
        save_to_postmoa_action.triggered.connect(self.save_to_postmoa_dialog)

        ## clear table action 추가
        clear_table_action = QAction('Clear Table', self)
        file_menu.addAction(clear_table_action)
        clear_table_action.setStatusTip('Clear Table')
        clear_table_action.setShortcut('Ctrl+N')
        clear_table_action.triggered.connect(self.clear_table)

        self.setMenuBar(menu_bar)

        self.reset_table()

    def clear_table(self):
        self.data = DATA_EMPTY_DATAFRAME.copy(deep=True)
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

    def reset_table(self):
        self.model = DataFrameModel(self.data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()

    def append_data_to_table(self, df: pd.DataFrame):
        try:
            self.data = pd.concat([self.data, df],
                                  axis=0)
            self.data.reset_index()

        except AttributeError as err:
            print(err)

        self.reset_table()  # data가 바뀌면 table에 변화를 반영해야 함

    def save_to_postmoa_dialog(self):
        try:
            directory = QFileDialog.getExistingDirectory(self, 'Save PostMoa Directory',
                                                         directory=r'c:\Users\User\Desktop\작업용 임시 폴더',
                                                         options=QFileDialog.Option.ShowDirsOnly)

            directory = pathlib.Path(directory)
            save_to_postmoa_normal_mail_path = directory / '{datetime}_일반우편.xls'.format(
                datetime=arrow.now().format('YYYY-MM-DD HHmmss'))
            save_to_postmoa_registered_mail_path = directory / '{datetime}_등기우편.xls'.format(
                datetime=arrow.now().format('YYYY-MM-DD HHmmss'))
            save_to_save_to_windowed_envelop_pdf_path = directory / '{datetime}_창봉투_주소.pdf'.format(
                datetime=arrow.now().format('YYYY-MM-DD HHmmss'))

            self.save_to_postmoa_normal_mail_excel(save_to_postmoa_normal_mail_path)
            self.save_to_postmoa_registered_mail_excel(save_to_postmoa_registered_mail_path)
            self.save_to_windowed_envelop_pdf(save_to_save_to_windowed_envelop_pdf_path)

        except pywintypes.com_error as err:
            print(err)
            QMessageBox.critical(self, 'Error', 'table is not converted to postmoa')
            return

    def save_to_postmoa_normal_mail_excel(self, target: pathlib.Path | str):
        target = pathlib.Path(target)
        df_normal_mail = NORMAL_MAIL_EMPTY_DATAFRAME.copy(deep=True)
        # print(f'update 전 {df_normal_mail}')

        if any(self.data):
            df_normal_mail['수취인*'] = self.data['이름']
            df_normal_mail['우편번호*'] = self.data['우편번호']
            df_normal_mail['기본주소*'] = self.data['주소']
            df_normal_mail['문서제목'] = self.data['제목']
            df_normal_mail['비고'] = self.data['제출기한']

            # broadcasting을 사용할 수 있는데
            # order가 중요함
            # 규격*을 처음 적용하면 length가 0이라서
            # broadcasting이 제대로 되지 않음
            df_normal_mail['규격*'] = '규격'
            df_normal_mail['중량*'] = '25'
            df_normal_mail['통수*'] = '1'

            df_normal_mail.to_excel(target, index=False)
            self.save_to_xls(target)

    def save_to_postmoa_registered_mail_excel(self, target: pathlib.Path | str):
        target = pathlib.Path(target)
        df_registered_mail = REGISTERED_MAIL_EMPTY_DATAFRAME.copy(deep=True)

        if any(self.data):
            df_registered_mail['수취인*'] = self.data['이름']
            df_registered_mail['우편번호*'] = self.data['우편번호']
            df_registered_mail['기본주소*'] = self.data['주소']
            df_registered_mail['문서제목'] = self.data['제목']
            df_registered_mail['비고'] = self.data['제출기한']

            # broadcasting을 사용할 수 있는데
            # order가 중요함
            # 규격*을 처음 적용하면 length가 0이라서
            # broadcasting이 제대로 되지 않음
            df_registered_mail['규격*'] = '규격'
            df_registered_mail['중량'] = '25'
            df_registered_mail['수수료*'] = '보통'
            df_registered_mail['환부*'] = '환부불능'

            df_registered_mail.to_excel(target, index=False)
            self.save_to_xls(target)

    def save_to_windowed_envelop_pdf(self, target: pathlib.Path | str):
        print(f'save_to_windowed_envelop_pdf: {target}')

        target = pathlib.Path(target)
        windowed_envelop_pdf = Canvas(filename=str(target), pagesize=A4)

        for row in self.data.itertuples():
            index, name, zipcode, address, title, bike_number, due_date = row

            # print(index, name, zipcode, address, title, bike_number, due_date)
            # 주소
            self.draw_text_to_pdf(windowed_envelop_pdf, address, 85, 244, 30, 2, "맑은고딕", 10)

            # 이름
            self.draw_text_to_pdf(windowed_envelop_pdf, name, 85, 230, 30, 2, "맑은고딕-bold", 10)

            # 우편번호
            character_gap: int = 6
            for i, z in enumerate(zipcode):
                self.draw_text_to_pdf(windowed_envelop_pdf, z, 135 + (character_gap * i), 224, 30, 2, "맑은고딕", 10)

            # 절취선
            self.draw_line_to_pdf(windowed_envelop_pdf, 0, 204, A4_width_in_mm, 204)
            self.draw_line_to_pdf(windowed_envelop_pdf, 0, 110, A4_width_in_mm, 110)
            self.draw_line_to_pdf(windowed_envelop_pdf, 0, 17, A4_width_in_mm, 17)

            windowed_envelop_pdf.showPage()  # 한 페이지 완성

        windowed_envelop_pdf.save()  # 전체 pdf 닫기

    @staticmethod
    def draw_text_to_pdf(canvas: Canvas,
                         text: str,
                         horizontal_offset: int,
                         vertical_offset: int,
                         max_text_length: int,
                         row_gap: int,
                         font: str,
                         font_size: int):
        """
        
        :param canvas: 추가할 pdf canvas object
        :param text: 추가할 str
        :param horizontal_offset: text box의 left coordinate(from left to right) in mm
        :param vertical_offset: text box의 top coordinate(from bottom to top) in mm
        :param max_text_length: 한 줄에 출력할 수 있는 글자 수
        :param row_gap: 줄 사이 간격 in mm
        :param font: pdfmetrics.registerFont로 추가된 폰트의 str
        :param font_size: 폰트 크기 in pt
        :return: 
        """
        canvas.setFont(font, font_size)
        wrapped_text_rows = textwrap.wrap(text, max_text_length)

        for i, row in enumerate(wrapped_text_rows):
            row_horizontal_offset_in_pt = horizontal_offset * mm
            row_horizontal_offset_in_pt -= font_size
            row_vertical_offset_in_pt = (vertical_offset * mm) - (font_size + (row_gap * mm)) * i

            canvas.drawString(row_horizontal_offset_in_pt, row_vertical_offset_in_pt, row)

    @staticmethod
    def draw_line_to_pdf(canvas: Canvas,
                         x1: int, y1: int, x2: int, y2: int):
        """
        (x1, y1)에서 (x2, y2)까지 line 그리기
        :param canvas:
        :param x1: in mm
        :param y1: in mm
        :param x2: in mm
        :param y2: in mm
        :return:
        """
        canvas.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)

    def open_file_dialog(self):
        files, filter_used = QFileDialog.getOpenFileNames(parent=self,
                                                          caption='open file',
                                                          directory=r'c:\Users\User\Desktop\작업용 임시 폴더',
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
    def save_to_xls(xlsx: str | pathlib.Path) -> str:
        """
        df.to_excel()이 xlsx만 지원해서
        일단 xlsx로 저장하고 xls로 다시 바꾸는 method를 작성함

        :param xlsx:
        :return:
        """
        if isinstance(xlsx, str):
            xlsx = pathlib.Path(xlsx)

        excel_app = win32.gencache.EnsureDispatch('Excel.Application')
        wb = excel_app.Workbooks.Open(xlsx)

        xls = xlsx.with_suffix('.xls')
        xls = str(xls)

        # https://stackoverflow.com/questions/42182126/suppress-save-as-prompt
        excel_app.DisplayAlerts = False

        wb.SaveAs(xls, FileFormat=56)  # 56은 .xls
        wb.Close()
        # excel_app.Quit()

        excel_app.DisplayAlerts = True

        return xls

    @staticmethod
    def extract_pattern_from_pdf(pdf: pathlib.Path | str, pattern: re.Pattern) -> tuple[AnyStr, ...]:
        pdf = pathlib.Path(pdf).resolve()
        text = ''

        for page in PdfReader(pdf).pages:
            text += page.extract_text()

        try:
            ret = pattern.search(text).groups()  # 일치하는 모든 str
        except AttributeError:
            ret = ('',)

        # print(f'{ret=}')
        return ret


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
