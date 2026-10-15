"""KNU Lecture Studio — native Qt interface, with local Whisper processing."""

from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer, QObject, Signal, QSize, QFile
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QCheckBox,
    QPlainTextEdit,
    QTextBrowser,
    QProgressBar,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QDialogButtonBox,
    QMenu,
    QToolButton,
    QScrollArea,
    QLayout,
    QInputDialog,
)
from core import Lecture, atomic_json, video_url
from engine import Engine, DATA, ROOT
from references import reference_terms
from auth_store import CredentialStore
from onboarding import WelcomeWizard
from school import DEFAULT_LMS, normalize_lms, is_knu, school_name, accent
from recorder import MicrophoneRecorder
from results_store import rename_transcript

VERSION = "2.4"

STYLE = """
QWidget {font-family:"Malgun Gothic","Noto Sans CJK KR","Noto Sans KR","Segoe UI";font-size:13px;color:#243348;}
QMainWindow, QWidget#workspace {background:#f4f6fa;}
QWizard, QWizardPage {background:white;}
QFrame#sidebar {background:#ffffff;border-right:1px solid #e2e8f0;}
QFrame#card {background:white;border:1px solid #e1e7ef;border-radius:12px;}
QLabel#title {font-size:27px;font-weight:700;color:#17263b;}
QLabel#section {font-size:16px;font-weight:700;color:#1e3046;}
QLabel#muted {color:#748296;font-size:12px;}
QLabel#brand {font-size:17px;font-weight:700;color:#1d3046;}
QLabel#logo {background:#991b30;color:white;border-radius:10px;font-size:21px;font-weight:700;}
QLabel#tag {background:#fff0f2;color:#b21e35;border-radius:12px;padding:5px 11px;font-size:11px;font-weight:600;}
QLabel#step {background:#fff0f2;color:#a51d33;border-radius:8px;font-weight:700;}
QPushButton {background:#ffffff;border:1px solid #dbe2ea;border-radius:7px;padding:8px 13px;font-weight:500;}
QPushButton:hover {background:#f1f5f9;border-color:#bac8d6;}
QPushButton:pressed {background:#e8eef5;}
QPushButton:disabled {background:#f3f5f8;color:#a0acb9;border-color:#e6ebf1;}
QPushButton#primary {background:#b21e35;color:white;border:1px solid #b21e35;font-weight:700;}
QPushButton#primary:hover {background:#95172b;}
QPushButton#primary:disabled {background:#e4b4bd;border-color:#e4b4bd;color:white;}
QPushButton#danger {color:#b34a4a;background:#fff8f8;border-color:#efd9d9;}
QPushButton#nav {text-align:left;border:none;background:transparent;padding:12px 17px;border-radius:8px;color:#66768a;font-weight:500;}
QPushButton#nav:checked {background:#fff0f2;color:#a51d33;font-weight:700;}
QPushButton#nav:hover {background:#f1f5f8;}
QPushButton#subtle {border:none;background:transparent;color:#60758b;padding:6px 3px;}
QLineEdit, QComboBox, QPlainTextEdit, QListWidget {background:#fbfcfe;border:1px solid #dfe6ee;border-radius:7px;padding:8px;selection-background-color:#f9dce2;selection-color:#7b1729;}
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus {border-color:#c76c7c;}
QLineEdit:disabled,QComboBox:disabled {color:#94a0af;background:#f6f8fa;}
QComboBox {padding-right:22px;min-height:17px;}
QComboBox::drop-down {border:none;width:21px;}
QComboBox QAbstractItemView {background:white;border:1px solid #dfe6ee;selection-background-color:#fff0f2;selection-color:#8c1b2e;padding:5px;}
QTableWidget {border:none;background:white;alternate-background-color:#fbfcfd;gridline-color:#eef2f6;outline:0;selection-background-color:#fff4f5;selection-color:#7c2030;}
QHeaderView::section {background:#f7f9fc;color:#76869b;border:none;border-bottom:1px solid #e5ebf1;padding:12px 6px;font-size:11px;font-weight:600;}
QTableWidget::item {border:none;border-bottom:1px solid #f0f3f7;padding:8px;}
QTableWidget::item:selected {background:#fff4f5;}
QCheckBox {spacing:7px;color:#697a8d;}
QCheckBox::indicator {width:15px;height:15px;border:1px solid #bac7d2;border-radius:4px;background:white;}
QCheckBox::indicator:checked {background:#b21e35;border-color:#b21e35;image:none;}
QProgressBar {border:none;background:#eaf0f4;border-radius:4px;height:7px;min-height:7px;max-height:7px;}
QProgressBar::chunk {background:#b21e35;border-radius:4px;}
QScrollBar:vertical {background:transparent;width:8px;margin:2px;}
QScrollBar::handle:vertical {background:#cbd5df;border-radius:3px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}
QTextBrowser {background:white;border:1px solid #e1e7ef;border-radius:10px;padding:14px;}
QMenu {background:white;border:1px solid #dbe2ea;padding:5px;}
QMenu::item {padding:8px 15px;}
QMenu::item:selected {background:#fff0f2;color:#a51d33;}
QFrame#login {background:#edf6ff;border:1px solid #c9dff3;border-radius:8px;}
QLabel#percent {font-size:21px;font-weight:700;color:#b21e35;}
QToolButton {border:none;color:#687b90;background:transparent;padding:5px;}
QSplitter::handle {background:transparent;width:18px;}
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, primary=False, name=None):
    w = QPushButton(text)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        w.setObjectName("primary")
    elif name:
        w.setObjectName(name)
    if callback:
        w.clicked.connect(callback)
    return w


def card():
    w = QFrame()
    w.setObjectName("card")
    layout = QVBoxLayout(w)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return w, layout


def combo(items, current):
    w = QComboBox()
    w.addItems(items)
    w.setMinimumContentsLength(1)
    w.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    if current in items:
        w.setCurrentText(current)
    return w


def app_icon(color="#b21e35"):
    p = QPixmap(64, 64)
    p.fill(Qt.GlobalColor.transparent)
    painter = QPainter(p)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QPen(QColor("white"), 4))
    painter.drawLine(21, 19, 21, 44)
    painter.drawLine(21, 44, 43, 44)
    painter.drawLine(31, 21, 43, 21)
    painter.drawLine(31, 31, 43, 31)
    painter.end()
    return QIcon(p)


class Bridge(QObject):
    event = Signal(str, object)


class App(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle(f"KNU Lecture Studio · v{VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1400, 970)
        self.setMinimumSize(1100, 760)
        self.data_dir = Path(data_dir) if data_dir else DATA
        self.state_path = self.data_dir / "settings.json"
        try:
            self.settings = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}
        self.lectures = {}
        self.media = {}
        self.refs = {}
        self.courses = []
        self.rows = {}
        self.history = [
            p for p in self.settings.get("history", []) if isinstance(p, str)
        ]
        self.busy = False
        self.closing = False
        self.has_error = False
        self.bridge = Bridge(self)
        self.bridge.event.connect(self.on_event, Qt.ConnectionType.QueuedConnection)
        self.engine = Engine(self.bridge.event.emit)
        self.engine.data_dir = self.data_dir
        self.engine.base_url = normalize_lms(self.settings.get("base_url", DEFAULT_LMS))
        self.recorder = MicrophoneRecorder(self.bridge.event.emit)
        self.recording_active = False
        self.record_closing = False
        self.record_snapshot = None
        self.last_recording = None
        self.vault = CredentialStore(self.data_dir)
        self.remember_account = False
        self.attention_box = None
        self.mutable = []
        self.last_output = None
        self.build()
        self.apply_school_theme()
        self.refresh_history()
        self.update_selection()

    def build(self):
        root = QWidget()
        root.setObjectName("workspace")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(236)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(20, 28, 20, 23)
        sl.setSpacing(8)
        logo_row = QHBoxLayout()
        logo = label("L", "logo")
        logo.setFixedSize(42, 42)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_row.addWidget(logo)
        logo_row.addSpacing(3)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("Lecture Studio", "brand"))
        self.school_brand = label("경북대학교", "muted", True)
        titles.addWidget(self.school_brand)
        logo_row.addLayout(titles)
        sl.addLayout(logo_row)
        sl.addSpacing(32)
        sl.addWidget(label("WORKSPACE", "muted"))
        sl.addSpacing(6)
        self.nav = []
        for i, text in enumerate(["강의 전사", "완료된 파일", "설치 및 도움말", "마이크 녹음"]):
            b = button(
                text, lambda checked=False, index=i: self.switch_page(index), name="nav"
            )
            b.setCheckable(True)
            sl.addWidget(b)
            self.nav.append(b)
        sl.addStretch()
        sl.addWidget(label("LOCAL PROCESSING", "muted"))
        sl.addWidget(label("음성 인식은 내 PC에서", "section"))
        sl.addWidget(label("Whisper로 전사하고\n완성된 TXT를 저장합니다.", "muted"))
        sl.addSpacing(16)
        self.connection_badge = label("○  LMS 연결 전", "muted")
        sl.addWidget(self.connection_badge)
        self.account_button = button("학교 · 계정 설정", self.setup_account)
        self.logout_button = button("로그아웃", self.logout, name="danger")
        sl.addWidget(self.account_button)
        sl.addWidget(self.logout_button)
        self.mutable.extend([self.account_button, self.logout_button])
        sl.addWidget(label(f"VERSION {VERSION}  /  Qt", "muted"))
        shell.addWidget(side)
        self.pages = QStackedWidget()
        shell.addWidget(self.pages, 1)
        self.build_main()
        self.build_results()
        self.build_help()
        self.build_recording()
        self.switch_page(0)

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)
        if index == 1:
            self.refresh_history()

    def build_main(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 25, 28, 22)
        layout.setSpacing(17)
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(5)
        texts.addWidget(label("강의를, 텍스트로.", "title"))
        texts.addWidget(
            label("강의를 선택하고 참고자료를 더하면, 전사 준비가 끝나요.", "muted")
        )
        head.addLayout(texts)
        head.addStretch()
        head.addWidget(label("●  LOCAL WHISPER", "tag"))
        self.env_button = button("환경 검사", self.environment)
        head.addWidget(self.env_button)
        layout.addLayout(head)
        connect, cl = card()
        cl.setContentsMargins(18, 13, 18, 13)
        cl.setSpacing(9)
        row = QHBoxLayout()
        step = label("1", "step")
        step.setFixedSize(27, 27)
        step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(step)
        row.addWidget(label("LMS 연결", "section"))
        row.addStretch()
        row.addWidget(
            button("토큰 발급 안내", lambda: self.switch_page(2), name="subtle")
        )
        self.token = QLineEdit()
        self.token.setPlaceholderText("Canvas 액세스 토큰을 붙여넣으세요")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setMinimumWidth(220)
        self.token.setMaximumWidth(390)
        row.addWidget(self.token, 1)
        self.connect_button = button("연결하기", self.connect, True)
        row.addWidget(self.connect_button)
        cl.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("과목 선택", "muted"))
        self.course_box = QComboBox()
        self.course_box.setPlaceholderText("LMS 연결 후 과목을 선택하세요")
        self.course_box.setMinimumWidth(270)
        row.addWidget(self.course_box, 1)
        self.scan_button = button("영상 목록 불러오기", self.scan)
        row.addWidget(self.scan_button)
        cl.addLayout(row)
        layout.addWidget(connect)
        self.login_frame = QFrame()
        self.login_frame.setObjectName("login")
        lr = QHBoxLayout(self.login_frame)
        lr.setContentsMargins(14, 10, 14, 10)
        lr.addWidget(
            label("열린 LMS 브라우저에서 로그인한 뒤 계속하세요.", wrap=True), 1
        )
        self.login_button = button(
            "로그인 완료 · 계속", self.engine.login_ready.set, True
        )
        lr.addWidget(self.login_button)
        self.login_frame.hide()
        layout.addWidget(self.login_frame)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(16)
        split.setChildrenCollapsible(False)
        video, vl = card()
        vl.setContentsMargins(0, 16, 0, 12)
        vl.setSpacing(10)
        top = QHBoxLayout()
        top.setContentsMargins(18, 0, 18, 0)
        top.addWidget(label("강의 목록", "section"))
        self.count_label = label("0개", "muted")
        top.addWidget(self.count_label)
        top.addStretch()
        self.local_button = button("+  내 영상 추가", self.add_local)
        top.addWidget(self.local_button)
        more = QToolButton()
        more.setText("⋯")
        more.setToolTip("목록 가져오기 / 비우기")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("기존 목록 JSON 가져오기", self.import_json)
        menu.addAction("목록 비우기", self.clear)
        more.setMenu(menu)
        top.addWidget(more)
        self.more_button = more
        vl.addLayout(top)
        searchrow = QHBoxLayout()
        searchrow.setContentsMargins(18, 0, 18, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("강의 제목 또는 주차 검색")
        self.search.textChanged.connect(self.filter_rows)
        searchrow.addWidget(self.search)
        self.all_check = QCheckBox("모두 선택")
        self.all_check.toggled.connect(self.select_all)
        searchrow.addWidget(self.all_check)
        vl.addLayout(searchrow)
        self.table_stack = QStackedWidget()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "주차", "영상 제목", "자료", "상태"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for col, width in [(0, 34), (1, 72), (3, 52), (4, 105)]:
            self.table.setColumnWidth(col, width)
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Fixed
            )
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.itemChanged.connect(self.update_selection)
        self.table.itemSelectionChanged.connect(self.update_selection)
        self.table_stack.addWidget(self.table)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setSpacing(13)
        mark = label("▤")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("font-size:46px;color:#b8cbd4;")
        el.addWidget(mark)
        t = label("아직 추가된 강의가 없어요.", "section")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        t = label(
            "LMS 과목에서 영상을 불러오거나\n이미 다운로드한 영상을 추가하세요.",
            "muted",
        )
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        emptybutton = button("내 PC에서 영상 선택", self.add_local)
        el.addWidget(emptybutton, 0, Qt.AlignmentFlag.AlignCenter)
        self.mutable.append(emptybutton)
        self.table_stack.addWidget(empty)
        self.table_stack.setCurrentIndex(1)
        vl.addWidget(self.table_stack, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(18, 0, 18, 0)
        self.selection_label = label("선택한 영상 0개", "muted")
        foot.addWidget(self.selection_label)
        foot.addStretch()
        foot.addWidget(label("여러 영상 선택 가능", "muted"))
        vl.addLayout(foot)
        split.addWidget(video)
        settings, st = card()
        settings.setMinimumWidth(340)
        settings.setMaximumWidth(405)
        st.setContentsMargins(18, 16, 18, 16)
        st.setSpacing(10)
        st.addWidget(label("전사 설정", "section"))
        self.active_label = label("영상을 선택해 주세요.", "muted", True)
        st.addWidget(self.active_label)
        outer_settings = st
        form = QWidget()
        form.setObjectName("settingsForm")
        st = QVBoxLayout(form)
        st.setContentsMargins(0, 0, 4, 0)
        st.setSpacing(10)
        st.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll = QScrollArea()
        self.settings_scroll = scroll
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(form)
        scroll.setStyleSheet("QScrollArea, QWidget#settingsForm {background:white;}")
        outer_settings.addWidget(scroll, 1)
        rr = QHBoxLayout()
        rr.addWidget(label("참고자료", "muted"))
        rr.addStretch()
        self.add_ref_button = button("+ 추가", self.add_refs)
        rr.addWidget(self.add_ref_button)
        st.addLayout(rr)
        self.ref_list = QListWidget()
        self.ref_list.setFixedHeight(68)
        self.ref_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        st.addWidget(self.ref_list)
        rr = QHBoxLayout()
        self.preview_button = button(
            "추출 용어 보기", self.preview_terms, name="subtle"
        )
        rr.addWidget(self.preview_button)
        rr.addStretch()
        self.remove_ref_button = button("자료 제거", self.remove_refs, name="subtle")
        rr.addWidget(self.remove_ref_button)
        st.addLayout(rr)
        self.manual = QPlainTextEdit()
        self.manual.setPlaceholderText("추가 전문용어 (선택)\n예: CPU, Virtual Memory")
        self.manual.setFixedHeight(59)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        self.model = combo(
            ["tiny", "base", "small", "medium", "large-v3", "turbo"],
            self.settings.get("model", "medium"),
        )
        self.device = combo(
            ["auto", "cuda", "cpu"], self.settings.get("device", "auto")
        )
        self.language = combo(["ko", "en", "auto"], self.settings.get("language", "ko"))
        grid.addWidget(label("모델", "muted"), 0, 0)
        grid.addWidget(label("장치", "muted"), 0, 1)
        grid.addWidget(self.model, 1, 0)
        grid.addWidget(self.device, 1, 1)
        grid.addWidget(label("언어", "muted"), 0, 2)
        grid.addWidget(self.language, 1, 2)
        st.addLayout(grid)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("추가 용어 · 재전사 옵션  ▾")
        self.advanced_toggle.setCheckable(True)
        advanced = QWidget()
        al = QVBoxLayout(advanced)
        al.setContentsMargins(0, 0, 0, 0)
        al.addWidget(self.manual)
        self.force = QCheckBox("완료된 TXT도 다시 전사")
        al.addWidget(self.force)
        advanced.hide()
        self.advanced_toggle.toggled.connect(advanced.setVisible)
        st.addWidget(self.advanced_toggle)
        st.addWidget(advanced)
        st.addStretch(1)
        st = outer_settings
        st.addWidget(label("저장 위치", "muted"))
        out = QHBoxLayout()
        out.setSpacing(5)
        self.output = QLineEdit(
            self.settings.get("output", str(Path.home() / "Documents/KNU_Transcripts"))
        )
        self.output.setToolTip(self.output.text())
        out.addWidget(self.output, 1)
        self.browse_button = button("…", self.choose_output)
        self.browse_button.setFixedWidth(36)
        out.addWidget(self.browse_button)
        st.addLayout(out)
        self.run_button = button("선택 영상 전사", self.start_transcribe, True)
        self.run_button.setMinimumHeight(42)
        st.addWidget(self.run_button)
        self.download_button = button(
            "다운로드만", lambda: self.start_transcribe(download_only=True)
        )
        st.addWidget(self.download_button)
        split.addWidget(settings)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([760, 350])
        layout.addWidget(split, 1)
        progress, pr = card()
        pr.setContentsMargins(18, 12, 18, 12)
        pr.setSpacing(7)
        r = QHBoxLayout()
        self.stage = label("전사 준비 완료", "section")
        r.addWidget(self.stage)
        r.addStretch()
        self.percent = label("0%", "percent")
        r.addWidget(self.percent)
        self.stop_button = button("작업 중지", self.stop, name="danger")
        self.stop_button.setEnabled(False)
        r.addWidget(self.stop_button)
        pr.addLayout(r)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        pr.addWidget(self.progress)
        self.status = label(
            "영상과 참고자료를 선택한 뒤 전사를 시작하세요.", "muted", True
        )
        pr.addWidget(self.status)
        logs = QHBoxLayout()
        self.log_toggle = QToolButton()
        self.log_toggle.setText("실행 로그 보기")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self.toggle_log)
        logs.addWidget(self.log_toggle)
        logs.addStretch()
        logs.addWidget(button("저장 폴더 열기", self.open_output, name="subtle"))
        pr.addLayout(logs)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(1500)
        self.logbox.setFixedHeight(95)
        self.logbox.hide()
        pr.addWidget(self.logbox)
        layout.addWidget(progress)
        self.pages.addWidget(page)
        self.mutable.extend(
            [
                self.token,
                self.connect_button,
                self.course_box,
                self.scan_button,
                self.local_button,
                self.more_button,
                self.all_check,
                self.add_ref_button,
                self.preview_button,
                self.remove_ref_button,
                self.manual,
                self.model,
                self.device,
                self.language,
                self.output,
                self.browse_button,
                self.force,
                self.env_button,
            ]
        )

    def build_results(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(32, 30, 32, 28)
        l.setSpacing(18)
        l.addWidget(label("완료된 파일", "title"))
        l.addWidget(label("본문 TXT를 열고 이름을 바꾸거나 삭제할 수 있어요. 삭제한 TXT는 휴지통으로 이동합니다.", "muted"))
        filters = QHBoxLayout()
        self.result_filter = combo(['전체 결과','마이크 녹음'], '전체 결과')
        self.result_filter.setMinimumWidth(160)
        self.result_search = QLineEdit()
        self.result_search.setPlaceholderText('TXT 이름으로 검색')
        self.result_filter.currentTextChanged.connect(self.refresh_history)
        self.result_search.textChanged.connect(self.refresh_history)
        filters.addWidget(self.result_filter)
        filters.addWidget(self.result_search,1)
        l.addLayout(filters)
        self.results = QListWidget()
        self.results.setSpacing(4)
        self.results.itemDoubleClicked.connect(self.open_result)
        l.addWidget(self.results, 1)
        row = QHBoxLayout()
        row.addWidget(button("TXT 미리보기", self.preview_result))
        row.addWidget(button("파일 열기", self.open_result, True))
        self.rename_button = button('TXT 이름 변경', self.rename_result)
        row.addWidget(self.rename_button)
        self.mutable.append(self.rename_button)
        self.delete_result_button = button('TXT 삭제', self.delete_result, name='danger')
        row.addWidget(self.delete_result_button)
        self.mutable.append(self.delete_result_button)
        row.addWidget(button('파일 위치 열기', self.open_result_folder))
        row.addStretch()
        row.addWidget(button("녹음 저장소 열기", self.open_recording_store))
        l.addLayout(row)
        self.pages.addWidget(page)

    def build_help(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(32, 30, 32, 28)
        l.setSpacing(16)
        l.addWidget(label("설치 및 도움말", "title"))
        l.addWidget(label("설치, LMS 토큰 발급과 전사 방법을 확인하세요.", "muted"))
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        try:
            browser.setMarkdown((ROOT / "README_ko.md").read_text(encoding="utf-8"))
        except OSError:
            browser.setPlainText("README_ko.md를 확인해 주세요.")
        l.addWidget(browser, 1)
        row = QHBoxLayout()
        row.addWidget(
            button("학교 LMS 열기", lambda: QDesktopServices.openUrl(QUrl(self.engine.base_url)))
        )
        row.addWidget(button("환경 검사", self.environment))
        row.addWidget(button("그림 설치 안내", lambda: self.open_path(ROOT / "START_HERE.html")))
        row.addWidget(button("바탕화면 바로가기 만들기", self.create_shortcut))
        row.addStretch()
        l.addLayout(row)
        self.pages.addWidget(page)

    def apply_school_theme(self):
        color, dark, pale, muted = accent(self.engine.base_url)
        css = STYLE
        mapping = {'#b21e35':color, '#95172b':dark, '#991b30':dark, '#a51d33':dark,
                   '#fff0f2':pale, '#fff4f5':pale, '#f9dce2':pale, '#e4b4bd':muted,
                   '#c76c7c':color, '#7b1729':dark, '#8c1b2e':dark, '#7c2030':dark}
        import re
        css = re.sub('|'.join(map(re.escape,mapping)), lambda m:mapping[m[0]], css)
        self.setStyleSheet(css)
        self.setWindowIcon(app_icon(color))
        self.setWindowTitle(f'Lecture Studio · {school_name(self.engine.base_url)} · v{VERSION}')
        self.school_brand.setText(school_name(self.engine.base_url))
        self.school_brand.setToolTip(self.engine.base_url)

    def build_recording(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 30, 32, 28)
        layout.setSpacing(16)
        layout.addWidget(label('내 목소리와 강의를, 기록으로.', 'title'))
        layout.addWidget(label('마이크 녹음 → 종료 후 MP3 저장 → 로컬 Whisper TXT 전사', 'muted'))
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0,0,0,0)
        content_layout.setSpacing(16)
        self.rec_scroll = QScrollArea()
        self.rec_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rec_scroll.setWidgetResizable(True)
        self.rec_scroll.setWidget(content)
        layout.addWidget(self.rec_scroll,1)
        box, form = card()
        form.addWidget(label('입력 장치', 'section'))
        row = QHBoxLayout()
        self.rec_input = QComboBox()
        self.rec_input.addItem('시스템 기본 마이크', None)
        row.addWidget(self.rec_input, 1)
        self.rec_refresh = button('마이크 목록 새로고침', self.refresh_microphones)
        row.addWidget(self.rec_refresh)
        form.addLayout(row)
        self.rec_time = label('00:00:00', 'title')
        form.addWidget(self.rec_time)
        self.rec_level = QProgressBar()
        self.rec_level.setRange(0,100); self.rec_level.setValue(0); self.rec_level.setTextVisible(False)
        form.addWidget(self.rec_level)
        form.addWidget(label('입력 레벨 · 선택한 입력 장치의 소리를 녹음합니다.', 'muted'))
        self.rec_status = label('녹음 준비 완료. Windows에서 마이크 접근을 허용해 주세요.', 'muted', True)
        form.addWidget(self.rec_status)
        content_layout.addWidget(box)
        config, form = card()
        row = QHBoxLayout()
        self.rec_model = combo(['tiny','base','small','medium','large-v3','turbo'], self.model.currentText())
        self.rec_device = combo(['auto','cuda','cpu'], self.device.currentText())
        self.rec_language = combo(['ko','en','auto'], self.language.currentText())
        for title, widget in [('모델',self.rec_model),('장치',self.rec_device),('언어',self.rec_language)]:
            row.addWidget(label(title,'muted'));row.addWidget(widget,1)
        form.addLayout(row)
        self.rec_refs = QListWidget();self.rec_refs.setFixedHeight(66)
        form.addWidget(self.rec_refs)
        row = QHBoxLayout()
        self.rec_add_ref = button('PDF / PPT 참고자료 추가', self.add_record_refs)
        self.rec_clear_ref = button('자료 비우기', self.rec_refs.clear)
        row.addWidget(self.rec_add_ref);row.addWidget(self.rec_clear_ref);row.addStretch()
        form.addLayout(row)
        row = QHBoxLayout()
        self.rec_output = QLineEdit(self.settings.get("recording_output", self.output.text()))
        self.rec_browse = button('저장 폴더', self.choose_record_output)
        row.addWidget(self.rec_output,1);row.addWidget(self.rec_browse)
        form.addLayout(row)
        self.rec_auto = QCheckBox('녹음 종료 후 자동으로 TXT 전사')
        self.rec_auto.setChecked(True);form.addWidget(self.rec_auto)
        content_layout.addWidget(config)
        content_layout.addStretch()
        row = QHBoxLayout()
        self.rec_start = button('● 녹음 시작', self.start_recording, True)
        self.rec_end = button('■ 녹음 종료 · 저장', self.end_recording, name='danger')
        self.rec_end.setEnabled(False)
        self.rec_open = button('최근 MP3 열기', self.open_recording)
        self.rec_store = button('녹음 저장소 열기', self.open_recording_store)
        self.rec_open.setEnabled(False)
        row.addWidget(self.rec_start);row.addWidget(self.rec_end);row.addWidget(self.rec_open);row.addWidget(self.rec_store)
        row.addStretch();layout.addLayout(row)
        layout.addWidget(label('녹음 중 자막은 표시하지 않습니다. 종료 후 전체 녹음을 전사합니다. WAV 원본도 함께 보존합니다.', 'muted', True))
        self.pages.addWidget(page)
        self.mutable.extend([self.rec_input,self.rec_refresh,self.rec_model,self.rec_device,self.rec_language,
            self.rec_output,self.rec_browse,self.rec_add_ref,self.rec_clear_ref,self.rec_auto,self.rec_start])

    def refresh_microphones(self):
        try:
            devices = self.recorder.devices()
        except Exception as e:
            self.info('마이크 확인', f'입력 장치를 읽지 못했습니다. upgrade_ui_windows.bat 실행과 Windows 마이크 권한을 확인하세요.\n{type(e).__name__}: {e}')
            return
        self.rec_input.clear();self.rec_input.addItem('시스템 기본 마이크',None)
        for index, name in devices:
            self.rec_input.addItem(name,index)
        self.rec_status.setText(f'입력 장치 {len(devices)}개. 사용할 마이크를 선택하세요.')

    def add_record_refs(self):
        paths,_ = QFileDialog.getOpenFileNames(self,'녹음 참고자료','','강의자료 (*.pdf *.pptx *.ppt)')
        existing = {self.rec_refs.item(i).text() for i in range(self.rec_refs.count())}
        for path in paths:
            if path not in existing:
                self.rec_refs.addItem(path)

    def choose_record_output(self):
        path = QFileDialog.getExistingDirectory(self,'녹음 저장 폴더',self.rec_output.text())
        if path:
            self.rec_output.setText(path)

    def start_recording(self):
        if self.busy:
            return
        if not self.rec_output.text().strip():
            self.info('저장 폴더', '녹음 저장 폴더를 지정하세요.')
            return
        output = Path(self.rec_output.text()).expanduser().resolve()
        self.record_snapshot = {'output':output, 'model':self.rec_model.currentText(),
            'device':self.rec_device.currentText(), 'language':self.rec_language.currentText(),
            'auto':self.rec_auto.isChecked(),
            'refs':[self.rec_refs.item(i).text() for i in range(self.rec_refs.count())]}
        self.recording_active = True
        self.record_closing = False
        self.rec_time.setText('00:00:00');self.rec_level.setValue(0)
        self.rec_status.setText('마이크 연결 중…')
        self.set_busy(True);self.rec_end.setEnabled(True)
        try:
            self.recorder.start(output / '녹음결과', self.rec_input.currentData())
        except Exception as e:
            self.recording_active = False
            self.set_busy(False);self.rec_end.setEnabled(False)
            self.info('녹음 시작 실패',str(e))

    def end_recording(self):
        if self.recording_active:
            self.recorder.stop()
            self.rec_end.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.rec_status.setText('녹음을 마무리하고 MP3를 저장하고 있습니다…')

    def open_recording(self):
        if self.last_recording:
            self.open_path(Path(self.last_recording))

    def on_record_event(self, kind, value):
        if kind == 'rec_started':
            self.rec_status.setText('녹음 중 · 종료 버튼을 누르면 MP3를 저장합니다.')
            self.status.setText('마이크 녹음 중')
        elif kind == 'rec_level':
            seconds, level = value
            n = int(seconds)
            self.rec_time.setText(f'{n//3600:02}:{n//60%60:02}:{n%60:02}')
            self.rec_level.setValue(round(level))
        elif kind in ('rec_status','rec_warning'):
            self.rec_status.setText(value)
            self.log(value)
        elif kind == 'rec_error':
            self.rec_status.setText(value)
            self.log('녹음 오류: '+value)
            if not self.record_closing:
                self.info('녹음 확인',value)
        elif kind == 'rec_finished':
            self.recording_active = False
            self.rec_end.setEnabled(False)
            self.set_busy(False)
            if value:
                self.settings['recording_output'] = str(self.record_snapshot['output'])
                self.save_settings()
                self.last_recording = value
                self.rec_open.setEnabled(True)
                self.rec_status.setText('MP3 저장 완료: '+value)
                lec = Lecture('local:'+value,Path(value).stem,'마이크 녹음',local_path=value)
                self.insert_lecture(lec,{},[],'녹음 완료')
                self.refs[lec.key] = list(self.record_snapshot['refs'])
                self.table.item(self.rows[lec.key],3).setText(f"{len(self.refs[lec.key])}개")
                if self.record_snapshot['auto'] and not self.record_closing:
                    self.search.clear();self.table.clearSelection()
                    for key,row in self.rows.items():
                        self.table.item(row,0).setCheckState(Qt.CheckState.Checked if key==lec.key else Qt.CheckState.Unchecked)
                    self.model.setCurrentText(self.record_snapshot['model'])
                    self.device.setCurrentText(self.record_snapshot['device'])
                    self.language.setCurrentText(self.record_snapshot['language'])
                    self.output.setText(str(self.record_snapshot['output']))
                    self.manual.clear()
                    self.switch_page(0)
                    self.start_transcribe()
            if self.record_closing:
                QTimer.singleShot(0,self.close)

    def toggle_log(self, checked):
        self.logbox.setVisible(checked)
        self.log_toggle.setText("실행 로그 접기" if checked else "실행 로그 보기")

    def log(self, text):
        self.logbox.appendPlainText(str(text))

    def info(self, title, text):
        QMessageBox.information(self, title, text)

    def launch(self, fn, *args):
        if self.busy:
            return
        self.has_error = False
        if self.engine.start(fn, *args):
            self.set_busy(True)

    def set_busy(self, value):
        self.busy = value
        for w in self.mutable:
            w.setEnabled(not value)
        self.stop_button.setEnabled(value)
        self.table.setEnabled(not value)
        if value:
            self.stage.setText("작업 진행 중")
            self.progress.setRange(0, 0)
            self.percent.setText("진행 중")
        else:
            self.progress.setRange(0, 100)
            self.login_frame.hide()
            self.stage.setText(
                "확인이 필요해요" if self.has_error else "작업 준비 완료"
            )
            if self.percent.text() == "진행 중":
                self.percent.setText("—")
        self.update_selection()

    def on_event(self, kind, value):
        if kind.startswith("rec_"):
            self.on_record_event(kind, value)
            return
        if kind == "log":
            self.log(value)
        elif kind == "status":
            self.status.setText(value)
        elif kind == "progress":
            self.progress.setRange(0, 100)
            self.progress.setValue(round(value))
            self.percent.setText(f"{value:.0f}%")
        elif kind == "error":
            self.has_error = True
            self.log("오류: " + value)
            self.status.setText(value)
            self.log_toggle.setChecked(True)
            if not self.closing:
                QMessageBox.warning(self, "작업 오류", value)
        elif kind == "courses":
            self.courses = value
            self.course_box.clear()
            for c in value:
                self.course_box.addItem(f"{c['name']}  ·  {c['id']}", c["id"])
            if value:
                self.course_box.setCurrentIndex(0)
            self.connection_badge.setText("●  LMS 연결됨")
            self.token.clear()
            self.token.setPlaceholderText("연결됨 · 계정 설정에서 로그인 관리")
            self.status.setText(
                f"{len(value)}개 과목을 불러왔습니다. 과목을 선택해 주세요."
            )
        elif kind == "clear":
            self._clear()
        elif kind == "lecture":
            lec, headers, cookies, state = value
            self.insert_lecture(lec, headers, cookies, state)
        elif kind == "row":
            key, state = value
            if key in self.rows:
                item = self.table.item(self.rows[key], 4)
                item.setText(state)
                item.setForeground(
                    QColor(
                        "#a51d33"
                        if "완료" in state
                        else "#ae6565"
                        if "실패" in state
                        else "#73859a"
                    )
                )
        elif kind == "login":
            self.login_frame.show()
            self.status.setText(value)
            self.log(value)
        elif kind == "attention":
            self.show_attention(*value)
        elif kind == "attention_done":
            self.close_attention()
        elif kind == "login_done":
            self.close_attention()
            self.login_frame.hide()
        elif kind == "preview":
            title, text = value if isinstance(value, tuple) else ("추출 용어", value)
            self.show_text(title, text)
        elif kind == "saved":
            if value in self.history:
                self.history.remove(value)
            self.history.insert(0, value)
            self.history = self.history[:200]
            self.last_output = value
            try:
                self.save_settings()
            except OSError:
                self.log(
                    "완료 목록 설정을 저장하지 못했습니다. TXT 파일은 저장되었습니다."
                )
        elif kind == "done":
            self.close_attention()
            self.set_busy(False)
            self.refresh_history()
            if self.closing:
                QTimer.singleShot(0, self.close)

    def show_attention(self, title, message):
        self.close_attention()
        box = QMessageBox(QMessageBox.Icon.Information, title, message,
                          QMessageBox.StandardButton.Ok, self)
        box.setModal(False)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.finished.connect(lambda *_: setattr(self, 'attention_box', None))
        self.attention_box = box
        box.show()
        QApplication.alert(self, 0)

    def close_attention(self):
        if self.attention_box:
            self.attention_box.close()
            self.attention_box = None

    def startup(self):
        try:
            credentials = self.vault.load()
        except RuntimeError as e:
            self.info('계정 다시 등록', str(e))
            credentials = {}
        if credentials.get('token'):
            self.engine.credentials = credentials
            self.engine.base_url = normalize_lms(credentials.get("base_url", DEFAULT_LMS))
            self.apply_school_theme()
            self.remember_account = True
            self.token.setText(credentials['token'])
            self.connect()
        elif not self.settings.get('tutorial_complete'):
            self.setup_account()

    def setup_account(self):
        if self.busy:
            return
        current = dict(self.engine.credentials)
        current.setdefault("base_url", self.engine.base_url)
        wizard = WelcomeWizard(self, current)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        credentials = wizard.credentials()
        remember = wizard.remember.isChecked()
        if credentials.get('username') != self.engine.credentials.get('username') or credentials['base_url'] != self.engine.base_url:
            profile = self.engine.profile_path()
            try:
                if profile.exists():
                    shutil.rmtree(profile)
            except OSError:
                self.info('계정 변경 실패', '앱 전용 브라우저를 닫고 계정 설정을 다시 진행해 주세요.')
                return
        try:
            if remember:
                self.vault.save(credentials)
            else:
                self.vault.clear()
        except (OSError, RuntimeError) as e:
            self.info('계정 저장 실패', str(e))
            return
        self.remember_account = remember
        self.engine.credentials = credentials
        self.engine.base_url = credentials["base_url"]
        self.apply_school_theme()
        self.settings['tutorial_complete'] = True
        self.save_settings()
        self.token.setText(credentials['token'])
        self.connect()

    def logout(self):
        if self.busy:
            return
        # Clear in-memory credentials even when a locked browser profile cannot be deleted.
        self.engine.credentials = {}
        if self.engine.api:
            self.engine.api.token = ''
        self.engine.api = None
        self.remember_account = False
        self.token.clear()
        self.courses = []
        self.course_box.clear()
        self._clear()
        self.connection_badge.setText('○  로그아웃됨')
        try:
            self.vault.clear()
            profile = self.engine.profile_path()
            if profile.exists():
                shutil.rmtree(profile)
        except OSError:
            self.info('로그아웃 정리 필요', '브라우저 파일을 지우지 못했습니다. 앱 전용 Chromium을 닫고 로그아웃을 다시 눌러주세요.')
            return
        self.status.setText('로그아웃 완료. 이 앱의 저장 계정과 로그인 세션을 삭제했습니다.')

    def connect(self):
        if not self.token.text().strip():
            self.info("토큰 연결", "Canvas 액세스 토큰을 먼저 입력해 주세요.")
            return
        token = self.token.text().strip()
        self.engine.api = None
        self.courses = []
        self.course_box.clear()
        self._clear()
        self.connection_badge.setText('○  연결 확인 중')
        self.engine.credentials['token'] = token
        self.engine.credentials['base_url'] = self.engine.base_url
        if self.remember_account:
            try:
                self.vault.save(self.engine.credentials)
            except (OSError, RuntimeError) as e:
                self.info('계정 저장 실패', str(e))
                return
        self.launch(self.engine.connect, token)

    def scan(self):
        index = self.course_box.currentIndex()
        if self.engine.api is None or index < 0:
            self.info("과목 선택", "먼저 LMS에 연결하고 과목을 선택해 주세요.")
            return
        self.launch(self.engine.scan, dict(self.courses[index]))

    def insert_lecture(self, lec, headers, cookies, state):
        self.lectures[lec.key] = lec
        self.media[lec.key] = (headers, cookies)
        self.table.blockSignals(True)
        if lec.key not in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[lec.key] = row
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, lec.key)
            self.table.setItem(row, 0, check)
        row = self.rows[lec.key]
        for col, text in [
            (1, lec.module),
            (2, lec.title),
            (3, f"{len(self.refs.get(lec.key, []))}개"),
            (4, state),
        ]:
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.table.setItem(row, col, item)
        self.table.item(row, 2).setForeground(QColor("#24374d"))
        self.table.item(row, 4).setForeground(QColor("#6e8497"))
        self.table.blockSignals(False)
        self.table_stack.setCurrentIndex(0)
        self.count_label.setText(f"{len(self.lectures)}개")
        self.filter_rows(self.search.text())
        self.update_selection()

    def _clear(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.rows.clear()
        self.lectures.clear()
        self.media.clear()
        self.table.blockSignals(False)
        self.count_label.setText("0개")
        self.table_stack.setCurrentIndex(1)
        self.update_selection()

    def clear(self):
        if not self.busy:
            self._clear()

    def filter_rows(self, text):
        text = text.casefold().strip()
        for key, row in self.rows.items():
            lec = self.lectures[key]
            self.table.setRowHidden(
                row,
                bool(text and text not in (lec.title + " " + lec.module).casefold()),
            )

    def select_all(self, checked):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                self.table.item(row, 0).setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
        self.table.blockSignals(False)
        self.update_selection()

    def selected_keys(self):
        keys = [
            key
            for key, row in self.rows.items()
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if keys:
            return keys
        return [
            self.table.item(i.row(), 0).data(Qt.ItemDataRole.UserRole)
            for i in self.table.selectionModel().selectedRows()
        ]

    def selected(self):
        keys = self.selected_keys()
        if not keys:
            self.info("영상 선택", "먼저 영상 왼쪽 체크박스를 선택해 주세요.")
        return keys

    def update_selection(self, *_):
        keys = self.selected_keys()
        self.selection_label.setText(f"선택한 영상 {len(keys)}개")
        for w in (
            self.run_button,
            self.download_button,
            self.add_ref_button,
            self.remove_ref_button,
            self.preview_button,
        ):
            w.setEnabled(bool(keys) and not self.busy)
        self.ref_list.clear()
        if not keys:
            self.active_label.setText("영상 선택 후 자료를 추가할 수 있어요.")
            return
        self.active_label.setText(
            self.lectures[keys[0]].title
            + (f" 외 {len(keys) - 1}개" if len(keys) > 1 else "")
        )
        for path in self.refs.get(keys[0], []):
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.ref_list.addItem(item)
        if not self.ref_list.count():
            item = QListWidgetItem("자료 없이도 전사할 수 있어요.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(QColor("#95a3b2"))
            self.ref_list.addItem(item)

    def add_local(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "기존 영상·오디오 추가",
            "",
            "영상·오디오 (*.mp4 *.m4a *.mp3 *.wav *.mkv);;모든 파일 (*)",
        )
        for p in paths:
            lec = Lecture(
                "local:" + str(Path(p).resolve()), Path(p).stem, "내 PC", local_path=p
            )
            self.insert_lecture(lec, {}, [], "로컬 파일")

    def import_json(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "기존 lcms_lectures.json", "", "JSON (*.json)"
        )
        if not p:
            return
        try:
            obj = json.loads(Path(p).read_text(encoding="utf-8-sig"))
            course = str(int(obj["course_id"]))
            rows = []
            for row in obj["lectures"]:
                cid = row.get("lcms_content_id")
                if cid:
                    rows.append(
                        Lecture(
                            f"{course}:item:{row.get('canvas_item_id', cid)}",
                            str(row["title"]),
                            str(row.get("module_name", "")),
                            page_url=row.get("canvas_url", ""),
                            media_url=video_url(cid),
                            content_id=cid,
                        )
                    )
            for lec in rows:
                self.insert_lecture(lec, {}, [], "가져옴 · 확인 전")
        except (OSError, ValueError, TypeError, KeyError):
            QMessageBox.warning(
                self, "가져오기 실패", "lcms_lectures.json의 형식을 확인해 주세요."
            )

    def add_refs(self):
        keys = self.selected()
        if not keys:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "참고자료 추가", "", "강의자료 (*.pdf *.pptx *.ppt)"
        )
        for key in keys:
            refs = self.refs.setdefault(key, [])
            refs.extend(p for p in paths if p not in refs)
            self.table.item(self.rows[key], 3).setText(f"{len(refs)}개")
        self.update_selection()

    def remove_refs(self):
        keys = self.selected_keys()
        selected = [
            i.data(Qt.ItemDataRole.UserRole)
            for i in self.ref_list.selectedItems()
            if i.data(Qt.ItemDataRole.UserRole)
        ]
        for key in keys:
            self.refs[key] = (
                [p for p in self.refs.get(key, []) if p not in selected]
                if selected
                else []
            )
            self.table.item(self.rows[key], 3).setText(f"{len(self.refs[key])}개")
        self.update_selection()

    def preview_terms(self):
        keys = self.selected()
        if not keys:
            return
        paths = list(self.refs.get(keys[0], []))
        manual = self.manual.toPlainText()

        def work():
            terms = reference_terms(paths, manual)
            self.bridge.event.emit(
                "preview",
                (
                    "추출 용어",
                    f"용어 후보 {len(terms)}개 · 실제 전사는 180 토큰 이내의 용어를 사용합니다.\n\n"
                    + "\n".join(terms),
                ),
            )

        self.launch(work)

    def choose_output(self):
        p = QFileDialog.getExistingDirectory(self, "저장 폴더", self.output.text())
        if p:
            self.output.setText(p)
            self.output.setToolTip(p)

    def save_settings(self):
        atomic_json(
            self.state_path,
            {
                "recording_output": self.settings.get("recording_output", self.rec_output.text()),
                "base_url": self.engine.base_url,
                "output": self.output.text(),
                "model": self.model.currentText(),
                "device": self.device.currentText(),
                "language": self.language.currentText(),
                "history": self.history,
                "tutorial_complete": self.settings.get("tutorial_complete", False),
            },
        )

    def start_transcribe(self, checked=False, download_only=False):
        keys = self.selected()
        if not keys:
            return
        if not self.output.text().strip():
            self.info("저장 폴더", "결과 저장 폴더를 지정해 주세요.")
            return
        snapshot = [
            (self.lectures[k], list(self.refs.get(k, [])), self.media.get(k, ({}, [])))
            for k in keys
        ]
        config = {
            "model": self.model.currentText(),
            "device": self.device.currentText(),
            "language": None
            if self.language.currentText() == "auto"
            else self.language.currentText(),
            "force": self.force.isChecked(),
            "jobs": [],
        }
        try:
            self.save_settings()
        except OSError as e:
            QMessageBox.warning(self, "설정 저장 실패", str(e))
            return
        self.launch(
            self.engine.run_jobs,
            snapshot,
            Path(self.output.text()).expanduser().resolve(),
            config,
            self.manual.toPlainText(),
            download_only,
        )

    def stop(self):
        if self.recording_active:
            self.end_recording()
            return
        self.engine.stop()
        self.status.setText(
            "중지 요청 중… 완료된 파일과 다운로드 중간 파일은 보존합니다."
        )
        self.stop_button.setEnabled(False)

    def environment(self):
        self.launch(self.engine.environment)

    @staticmethod
    def is_recording_result(path):
        p = Path(path)
        return '녹음결과' in p.parts or p.name.startswith('녹음_')

    def refresh_history(self, *_):
        self.results.clear()
        query = self.result_search.text().strip().lower()
        only_recording = self.result_filter.currentText() == '마이크 녹음'
        shown = 0
        for path in self.history:
            p = Path(path)
            if query and query not in p.name.lower():
                continue
            if only_recording and not self.is_recording_result(p):
                continue
            kind = '마이크 녹음' if self.is_recording_result(p) else '강의 전사'
            suffix = '' if p.is_file() else ' · 파일 이동됨 또는 없음'
            item = QListWidgetItem(p.name + '\n' + kind + suffix + '  |  ' + str(p.parent))
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            item.setToolTip(str(p))
            item.setSizeHint(QSize(100,64))
            self.results.addItem(item)
            shown += 1
        if not shown:
            self.results.addItem(QListWidgetItem('표시할 TXT가 없습니다. 검색어나 필터를 확인하거나 전사를 완료해 주세요.'))
        self.nav[1].setText('완료된 파일' + (f'   {len(self.history)}' if self.history else ''))

    def rename_result(self):
        if self.busy:
            return
        item = self.results.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            self.info('파일 선택','이름을 변경할 TXT를 선택해 주세요.')
            return
        source = Path(item.data(Qt.ItemDataRole.UserRole))
        name, ok = QInputDialog.getText(self,'TXT 이름 변경','새 파일 이름 (.txt는 자동으로 붙습니다)',text=source.stem)
        if not ok:
            return
        try:
            target = rename_transcript(source,name)
        except (OSError,ValueError) as e:
            self.info('이름 변경 실패',str(e))
            return
        self.history = [str(target) if p==str(source) else p for p in self.history]
        if self.last_output==str(source):
            self.last_output=str(target)
        self.save_settings()
        self.refresh_history()
        for i in range(self.results.count()):
            if self.results.item(i).data(Qt.ItemDataRole.UserRole)==str(target):
                self.results.setCurrentRow(i)
                break

    def delete_result(self):
        if self.busy:
            return
        item = self.results.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            self.info('파일 선택', '삭제할 TXT를 먼저 선택해 주세요.')
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        exists = path.exists()
        message = (f'{path.name}\n\nTXT를 휴지통으로 이동하고 완료 목록에서 제거할까요?\n'
                   f'MP3·WAV와 참고자료는 보관합니다.\n\n{path}' if exists else
                   f'{path.name}\n\n파일이 이미 이동되었거나 없습니다. 완료 목록에서 제거할까요?')
        if QMessageBox.question(self, 'TXT 삭제', message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if exists:
            try:
                if path.suffix.lower() != '.txt' or not path.is_file():
                    raise ValueError('TXT 파일만 삭제할 수 있습니다.')
                result = QFile.moveToTrash(str(path.absolute()))
                success = result[0] if isinstance(result, tuple) else bool(result)
                if not success:
                    raise OSError('휴지통으로 이동하지 못했습니다. 파일을 사용하는 프로그램과 폴더 권한을 확인하세요.')
            except (OSError, ValueError) as e:
                self.info('삭제 실패', str(e))
                return
        self.history = [p for p in self.history if p != str(path)]
        if self.last_output == str(path):
            self.last_output = None
        try:
            self.save_settings()
        except OSError:
            self.info('목록 저장 확인', 'TXT는 처리했으나 완료 기록을 저장하지 못했습니다. 다음 실행에 항목이 남아 있으면 다시 목록에서 제거해 주세요.')
        self.refresh_history()
        self.status.setText('TXT를 휴지통으로 이동했습니다.' if exists else '없는 파일을 완료 목록에서 제거했습니다.')

    def open_result_folder(self):
        item = self.results.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.open_path(Path(item.data(Qt.ItemDataRole.UserRole)).parent)
        else:
            self.info('파일 선택','위치 확인할 TXT를 선택해 주세요.')

    def open_recording_store(self):
        base = Path(self.rec_output.text() or self.settings.get('recording_output', self.output.text())).expanduser()
        folder = base / '녹음결과'
        try:
            folder.mkdir(parents=True,exist_ok=True)
        except OSError as e:
            self.info('저장소 열기 실패',str(e))
            return
        self.open_path(folder)

    def open_result(self, *_):
        item = self.results.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.open_path(Path(item.data(Qt.ItemDataRole.UserRole)))

    def preview_result(self):
        item = self.results.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            return
        p = Path(item.data(Qt.ItemDataRole.UserRole))
        try:
            self.show_text(p.name, p.read_text(encoding="utf-8-sig"))
        except OSError:
            self.info("파일 없음", "원래 저장 위치에서 파일을 찾지 못했습니다.")

    def show_text(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(780, 550)
        l = QVBoxLayout(dialog)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        l.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        l.addWidget(buttons)
        dialog.exec()

    def open_path(self, path):
        if not path.exists():
            self.info("경로 없음", "아직 해당 폴더나 파일이 없습니다.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def create_shortcut(self):
        if sys.platform != 'win32':
            self.info('Windows 바로가기','Windows에서 사용할 수 있습니다. create_shortcut_windows.bat를 실행해 주세요.')
            return
        import subprocess
        try:
            p = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'create_shortcut.ps1')],
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or '바로가기를 만들지 못했습니다.')
            self.info('바로가기 생성','바탕화면에 Lecture Studio 바로가기를 만들었습니다. 프로그램 폴더를 옮기면 다시 생성해 주세요.')
        except (OSError,RuntimeError,subprocess.TimeoutExpired) as e:
            self.info('바로가기 생성 실패',str(e))

    def open_output(self):
        self.open_path(Path(self.output.text()).expanduser())

    def closeEvent(self, event):
        if self.recording_active:
            if not self.record_closing and QMessageBox.question(self, '녹음 종료',
                '녹음을 종료하고 MP3 저장을 마친 뒤 앱을 닫을까요? TXT 전사는 다음에 할 수 있습니다.') != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.record_closing = True
            self.end_recording()
            event.ignore()
            return
        if self.busy:
            if (
                not self.closing
                and QMessageBox.question(
                    self, "종료", "진행 중인 작업을 중지하고 종료할까요?"
                )
                != QMessageBox.StandardButton.Yes
            ):
                event.ignore()
                return
            self.closing = True
            self.stop()
            event.ignore()
            return
        if not self.remember_account:
            profile = self.engine.profile_path()
            if profile.exists():
                try:
                    shutil.rmtree(profile)
                except OSError:
                    pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lecture Studio")
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    w = App()
    w.show()
    QTimer.singleShot(0, w.startup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
