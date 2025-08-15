# -*- coding: utf-8 -*-
"""
Black Notepad (PySide6, Windows Notepad-like + Modern UI)
- File: New/Open/Save/Save As, unsaved-changes prompt
- Edit: Undo/Redo, Cut/Copy/Paste, Select All
- Find/Replace dialog (case / whole word)
- Format: Word Wrap toggle, Font chooser, Insert Date/Time (F5)
- View: Status Bar toggle, Theme (Light/Dark), Custom BG/FG color
- Status: Line / Column / Wrap state
- Icon: load black_notepad.ico (exe 포함 & 런타임 사용)
- Frameless: 기본 타이틀바 제거 + 메뉴바 오른쪽에 최소/최대/닫기 버튼
- Jump List: Windows 작업표시줄 우클릭 → 최근 항목 자동 노출

Python 3.10+ / Windows 10/11
"""
import os
import sys
import time
import ctypes
from typing import Optional

# ---- AppID & 리소스 경로 (PyInstaller onefile 대응) ----
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.blacknotepad.app")

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))  # PyInstaller onefile 임시폴더
    return os.path.join(base, rel)

def add_to_recent(path: str):
    """Windows Jump List '최근 항목'에 등록."""
    try:
        SHAddToRecentDocs = ctypes.windll.shell32.SHAddToRecentDocs
        SHARD_PATHW = 0x00000003  # wide-char 경로
        SHAddToRecentDocs(SHARD_PATHW, ctypes.c_wchar_p(path))
    except Exception:
        pass


from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QFontDialog,
    QColorDialog, QDialog, QLineEdit, QCheckBox, QPushButton, QLabel,
    QGridLayout, QStatusBar
)

APP_NAME = "Black Notepad"


# -------- Find / Replace Dialog --------
class FindReplaceDialog(QDialog):
    def __init__(self, parent=None, replace: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Replace" if replace else "Find")
        self.setModal(True)
        self.resize(420, 120)

        self.replace_mode = replace
        self.edit_find = QLineEdit(self)
        self.edit_replace = QLineEdit(self)
        self.chk_case = QCheckBox("Match case", self)
        self.chk_word = QCheckBox("Whole word", self)

        btn_find = QPushButton("Find Next", self)
        btn_find.clicked.connect(self.accept)
        self.btn_replace = QPushButton("Replace", self)
        self.btn_replace.clicked.connect(self._replace_clicked)
        self.btn_replace_all = QPushButton("Replace All", self)
        self.btn_replace_all.clicked.connect(self._replace_all_clicked)
        btn_close = QPushButton("Close", self)
        btn_close.clicked.connect(self.reject)

        lay = QGridLayout(self)
        lay.addWidget(QLabel("Find:"), 0, 0)
        lay.addWidget(self.edit_find, 0, 1, 1, 3)
        if replace:
            lay.addWidget(QLabel("Replace:"), 1, 0)
            lay.addWidget(self.edit_replace, 1, 1, 1, 3)
        lay.addWidget(self.chk_case, 2, 1)
        lay.addWidget(self.chk_word, 2, 2)
        lay.addWidget(btn_find, 0, 4)
        if replace:
            lay.addWidget(self.btn_replace, 1, 4)
            lay.addWidget(self.btn_replace_all, 2, 4)
        lay.addWidget(btn_close, 3, 4)

        if not replace:
            self.btn_replace.hide()
            self.btn_replace_all.hide()

        self._replace_cb = None
        self._replace_all_cb = None

    def options(self):
        opts = QtGui.QTextDocument.FindFlags()
        if self.chk_case.isChecked():
            opts |= QtGui.QTextDocument.FindCaseSensitively
        if self.chk_word.isChecked():
            opts |= QtGui.QTextDocument.FindWholeWords
        return opts

    def on_replace(self, cb): self._replace_cb = cb
    def on_replace_all(self, cb): self._replace_all_cb = cb
    def _replace_clicked(self):
        if self._replace_cb:
            self._replace_cb(self.edit_find.text(), self.edit_replace.text(), self.options())
    def _replace_all_clicked(self):
        if self._replace_all_cb:
            self._replace_all_cb(self.edit_find.text(), self.edit_replace.text(), self.options())


# -------- Main Window --------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 프레임리스 (타이틀바 제거)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowTitle(APP_NAME)
        self.resize(980, 640)

        # 아이콘 (창/작업표시줄)
        ico_path = resource_path("black_notepad.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        # 중앙 에디터
        self.edit = QtWidgets.QTextEdit(self)
        self.setCentralWidget(self.edit)
        self.edit.setAcceptRichText(False)  # Notepad처럼 플레인 텍스트
        self._set_default_font()

        # 상태바
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self._install_credit_link()

        # 상태
        self.current_path: Optional[str] = None
        self.is_dark = True
        self.custom_bg = "#0f0f0f"
        self.custom_fg = "#e6e6e6"
        self._apply_theme(dark=True)

        # 메뉴/액션
        self._build_menu()
        self._apply_wrap(True)
        self._install_menu_corner_controls()

        # 시그널
        self.edit.document().modificationChanged.connect(self._update_title)
        self.edit.cursorPositionChanged.connect(self._update_status)
        self.edit.textChanged.connect(self._update_status)

        self._update_title()
        self._update_status()

    # ---- 우측 창 제어 버튼(프레임리스용) ----
    def _install_menu_corner_controls(self):
        mb = self.menuBar()
        box = QtWidgets.QWidget(self)
        lay = QtWidgets.QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(0)

        self.btn_min = QtWidgets.QToolButton(box)
        self.btn_max = QtWidgets.QToolButton(box)
        self.btn_close = QtWidgets.QToolButton(box)

        style = self.style()
        self.btn_min.setIcon(style.standardIcon(QtWidgets.QStyle.SP_TitleBarMinButton))
        self._update_max_icon()
        self.btn_close.setIcon(style.standardIcon(QtWidgets.QStyle.SP_TitleBarCloseButton))

        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setAutoRaise(True)
            b.setFixedSize(36, 24)

        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max_restore)
        self.btn_close.clicked.connect(self.close)

        box.setStyleSheet("""
        QToolButton { border: none; }
        QToolButton:hover { background: #2a2a2a; }
        QToolButton:pressed { background: #3a3a3a; }
        QToolButton#close:hover { background: #c42b1c; }
        """)
        self.btn_close.setObjectName("close")

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)
        mb.setCornerWidget(box, Qt.TopRightCorner)

        # 메뉴바 드래그로 창 이동/더블클릭 최대화
        mb.installEventFilter(self)
        self._drag_pos = None

    def _update_max_icon(self):
        style = self.style()
        if self.isMaximized():
            self.btn_max.setIcon(style.standardIcon(QtWidgets.QStyle.SP_TitleBarNormalButton))
        else:
            self.btn_max.setIcon(style.standardIcon(QtWidgets.QStyle.SP_TitleBarMaxButton))

    def _toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._update_max_icon()

    def eventFilter(self, obj, event):
        if obj is self.menuBar():
            if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return False
            elif event.type() == QtCore.QEvent.MouseMove and event.buttons() & Qt.LeftButton and self._drag_pos is not None:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                self._drag_pos = None
                return False
            elif event.type() == QtCore.QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self._toggle_max_restore()
                return True
        return super().eventFilter(obj, event)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QtCore.QEvent.WindowStateChange and hasattr(self, "btn_max"):
            self._update_max_icon()

    # ---- UI helpers ----
    def _set_default_font(self):
        self.edit.setFont(QtGui.QFont("Consolas", 12))

    def _build_menu(self):
        mb = self.menuBar()
        # File
        m_file = mb.addMenu("&File")
        act_new = QAction("New\tCtrl+N", self, triggered=self.file_new);  act_new.setShortcut("Ctrl+N")
        act_open = QAction("Open...\tCtrl+O", self, triggered=self.file_open); act_open.setShortcut("Ctrl+O")
        act_save = QAction("Save\tCtrl+S", self, triggered=self.file_save); act_save.setShortcut("Ctrl+S")
        act_saveas = QAction("Save As...\tShift+Ctrl+S", self, triggered=self.file_save_as); act_saveas.setShortcut("Ctrl+Shift+S")
        m_file.addActions([act_new, act_open]); m_file.addSeparator()
        m_file.addActions([act_save, act_saveas]); m_file.addSeparator()
        m_file.addAction(QAction("Exit", self, triggered=self.close))

        # Edit
        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(QAction("Undo\tCtrl+Z", self, shortcut="Ctrl+Z", triggered=self.edit.undo))
        m_edit.addAction(QAction("Redo\tCtrl+Y", self, shortcut="Ctrl+Y", triggered=self.edit.redo))
        m_edit.addSeparator()
        m_edit.addAction(QAction("Cut\tCtrl+X", self, shortcut="Ctrl+X", triggered=self.edit.cut))
        m_edit.addAction(QAction("Copy\tCtrl+C", self, shortcut="Ctrl+C", triggered=self.edit.copy))
        m_edit.addAction(QAction("Paste\tCtrl+V", self, shortcut="Ctrl+V", triggered=self.edit.paste))
        m_edit.addSeparator()
        m_edit.addAction(QAction("Select All\tCtrl+A", self, shortcut="Ctrl+A", triggered=self.edit.selectAll))
        m_edit.addSeparator()
        m_edit.addAction(QAction("Find...\tCtrl+F", self, shortcut="Ctrl+F", triggered=self.find_dialog))
        m_edit.addAction(QAction("Replace...\tCtrl+H", self, shortcut="Ctrl+H", triggered=self.replace_dialog))

        # Format
        m_format = mb.addMenu("F&ormat")
        self.act_wrap = QAction("Word Wrap\tCtrl+W", self, checkable=True, checked=True, triggered=self.toggle_wrap)
        m_format.addAction(self.act_wrap)
        m_format.addSeparator()
        m_format.addAction(QAction("Font...", self, triggered=self.choose_font))
        m_format.addAction(QAction("Insert Date/Time (F5)", self, shortcut="F5", triggered=self.insert_datetime))

        # View
        m_view = mb.addMenu("&View")
        m_theme = m_view.addMenu("Theme / Colors")
        m_theme.addAction(QAction("Light", self, triggered=lambda: self._apply_theme(dark=False)))
        m_theme.addAction(QAction("Dark (Black)", self, triggered=lambda: self._apply_theme(dark=True)))
        m_theme.addSeparator()
        m_theme.addAction(QAction("Custom Background...", self, triggered=self.pick_bg))
        m_theme.addAction(QAction("Custom Foreground...", self, triggered=self.pick_fg))
        self.act_statusbar = QAction("Status Bar", self, checkable=True, checked=True, triggered=self.toggle_statusbar)
        m_view.addAction(self.act_statusbar)

        # Help
        m_help = mb.addMenu("&Help")
        m_help.addAction(QAction("About", self, triggered=lambda:
            QMessageBox.information(self, APP_NAME, f"{APP_NAME}\nPySide6 Notepad with Dark/Light themes.")))

    # ---- File ops ----
    def _maybe_save(self) -> bool:
        if self.edit.document().isModified():
            name = os.path.basename(self.current_path) if self.current_path else "Untitled"
            ret = QMessageBox.question(self, "Save changes?", f"Save changes to '{name}'?",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ret == QMessageBox.Cancel:
                return False
            if ret == QMessageBox.Yes:
                return self.file_save()
        return True

    def file_new(self):
        if not self._maybe_save():
            return
        self.edit.clear()
        self.current_path = None
        self.edit.document().setModified(False)
        self._update_title()

    def _read_text_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="cp949", errors="replace") as f:
                return f.read()

    def file_open(self):
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "Text Files (*.txt *.py *.md *.log *.json *.csv);;All Files (*.*)")
        if not path:
            return
        text = self._read_text_file(path)
        self.edit.setPlainText(text)
        self.current_path = path
        self.edit.document().setModified(False)
        self._update_title()
        add_to_recent(path)  # Jump List 최근 항목 등록

    def file_save(self) -> bool:
        if self.current_path is None:
            return self.file_save_as()
        return self._write_to_path(self.current_path)

    def file_save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save As", self.current_path or "Untitled.txt", "Text Files (*.txt);;All Files (*.*)")
        if not path:
            return False
        self.current_path = path
        ok = self._write_to_path(path)
        if ok:
            self._update_title()
        return ok

    def _write_to_path(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.edit.toPlainText())
            self.edit.document().setModified(False)
            add_to_recent(path)  # Jump List 최근 항목 등록
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
            return False

    # ---- Edit / Find / Replace ----
    def _find_once(self, pattern: str, opts: QtGui.QTextDocument.FindFlags) -> bool:
        if not pattern:
            return False
        found = self.edit.find(pattern, opts)
        if not found:
            cursor = self.edit.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.edit.setTextCursor(cursor)
            found = self.edit.find(pattern, opts)
        if not found:
            QMessageBox.information(self, "Find", "No matches found.")
        return found

    def find_dialog(self):
        dlg = FindReplaceDialog(self, replace=False)
        sel = self.edit.textCursor().selectedText()
        if sel:
            dlg.edit_find.setText(sel)
        if dlg.exec() == QDialog.Accepted:
            self._find_once(dlg.edit_find.text(), dlg.options())

    def replace_dialog(self):
        dlg = FindReplaceDialog(self, replace=True)
        sel = self.edit.textCursor().selectedText()
        if sel:
            dlg.edit_find.setText(sel)

        def do_replace(find_text, repl_text, opts):
            cur = self.edit.textCursor()
            if not cur.hasSelection():
                if not self._find_once(find_text, opts):
                    return
                cur = self.edit.textCursor()
            if cur.selectedText():
                cur.insertText(repl_text)
            self._find_once(find_text, opts)

        def do_replace_all(find_text, repl_text, opts):
            if not find_text:
                return
            cur = self.edit.textCursor()
            cur.movePosition(QTextCursor.Start)
            self.edit.setTextCursor(cur)
            count = 0
            while self.edit.find(find_text, opts):
                c = self.edit.textCursor()
                if c.hasSelection():
                    c.insertText(repl_text)
                    count += 1
            QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s).")

        dlg.on_replace(do_replace)
        dlg.on_replace_all(do_replace_all)
        dlg.exec()

    # ---- Format ----
    def toggle_wrap(self, checked: bool):
        self._apply_wrap(checked)
        self._update_status()

    def _apply_wrap(self, on: bool):
        if hasattr(self, "act_wrap") and self.act_wrap is not None:
            self.act_wrap.setChecked(on)
        self.edit.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere if on else QtGui.QTextOption.NoWrap
        )

    def choose_font(self):
        ok, font = QFontDialog.getFont(self.edit.font(), self, "Choose Font")
        if ok:
            self.edit.setFont(font)

    def insert_datetime(self):
        self.edit.insertPlainText(time.strftime("%H:%M %Y-%m-%d"))

    # ---- View / Theme ----
    def _apply_theme(self, dark: bool):
        self.is_dark = dark
        if dark:
            bg, fg = self.custom_bg or "#0f0f0f", self.custom_fg or "#e6e6e6"
            sel = "#3b6cff"
            self._apply_editor_colors(bg, fg, sel)
            self._apply_app_palette(dark=True)
        else:
            bg, fg = "#ffffff", "#000000"
            sel = "#2a62ff"
            self._apply_editor_colors(bg, fg, sel)
            self._apply_app_palette(dark=False)
        self._style_credit_link()

    def _apply_editor_colors(self, bg_hex: str, fg_hex: str, sel_hex: str):
        self.edit.setStyleSheet(
            f"""
            QTextEdit {{
                background: {bg_hex};
                color: {fg_hex};
                selection-background-color: {sel_hex};
            }}
            """
        )

    def _apply_app_palette(self, dark: bool):
        QtWidgets.QApplication.setStyle("Fusion")
        if dark:
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window,        QtGui.QColor("#1a1a1a"))
            pal.setColor(QtGui.QPalette.Base,          QtGui.QColor("#121212"))
            pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#1e1e1e"))
            pal.setColor(QtGui.QPalette.Text,          QtCore.Qt.white)
            pal.setColor(QtGui.QPalette.Button,        QtGui.QColor("#1a1a1a"))
            pal.setColor(QtGui.QPalette.ButtonText,    QtCore.Qt.white)
            pal.setColor(QtGui.QPalette.WindowText,    QtCore.Qt.white)
            pal.setColor(QtGui.QPalette.ToolTipBase,   QtGui.QColor("#2a2a2a"))
            pal.setColor(QtGui.QPalette.ToolTipText,   QtCore.Qt.white)
            pal.setColor(QtGui.QPalette.Highlight,     QtGui.QColor("#3b6cff"))
            pal.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)
        else:
            pal = QtWidgets.QApplication.style().standardPalette()
        QtWidgets.QApplication.instance().setPalette(pal)

    def pick_bg(self):
        col = QColorDialog.getColor(QtGui.QColor(self.custom_bg), self, "Pick Background")
        if col.isValid():
            self.custom_bg = col.name()
            self._apply_theme(self.is_dark)

    def pick_fg(self):
        col = QColorDialog.getColor(QtGui.QColor(self.custom_fg), self, "Pick Foreground")
        if col.isValid():
            self.custom_fg = col.name()
            self._apply_theme(self.is_dark)

    def toggle_statusbar(self, checked: bool):
        self.status.setVisible(checked)

    # ---- Title & Status ----
    def _update_title(self, *_):
        name = os.path.basename(self.current_path) if self.current_path else "Untitled"
        dirty = "*" if self.edit.document().isModified() else ""
        self.setWindowTitle(f"{name}{dirty} - {APP_NAME}")

    def _update_status(self, *_):
        cur = self.edit.textCursor()
        line = cur.blockNumber() + 1
        col = cur.positionInBlock() + 1
        wrap = "ON" if hasattr(self, "act_wrap") and self.act_wrap.isChecked() else "OFF"
        self.status.showMessage(f"Ln {line} , Col {col}    |    Wrap {wrap}")

    # ---- Close ----
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._maybe_save():
            event.accept()
        else:
            event.ignore()
    def _install_credit_link(self):
        
        """상태바 오른쪽에 @made by Weed 링크 달기"""
        self.credit = QLabel(self)
        self.credit.setText('<a href="https://happyweed.tistory.com/">@made by Weed</a>')
        self.credit.setTextFormat(Qt.RichText)
        self.credit.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.credit.setOpenExternalLinks(True)
        self.credit.setCursor(Qt.PointingHandCursor)
        self._style_credit_link()  # 테마에 맞는 색 적용
        # 상태바의 오른쪽(항상 보이도록) 배치
        self.status.addPermanentWidget(self.credit)

    def _style_credit_link(self):
        """다크/라이트 테마에 맞게 링크 색상/호버 스타일 적용"""
        # 본문 텍스트는 은은하게, 링크는 부드러운 포인트 컬러
        if getattr(self, "is_dark", True):
            base = "#a9a9a9"     # 본문(설명)용 옅은 회색
            link = "#8AB4F8"     # 다크 테마용 부드러운 블루
        else:
            base = "#333333"
            link = "#1A73E8"     # 라이트 테마용 블루

        # QLabel의 리치텍스트에 CSS 적용 (a 태그 스타일)
        self.credit.setStyleSheet(f"""
            QLabel {{ color: {base}; }}
            a {{ color: {link}; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        """)


# -------- main --------
def main():
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 작업표시줄/Alt+Tab 기본 앱 아이콘
    ico_path = resource_path("black_notepad.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

#made by Weed
#https://happyweed.tistory.com/40