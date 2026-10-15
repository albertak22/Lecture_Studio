"""School selection, optional password login, and guided setup."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWizard, QWizardPage, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton, QMessageBox
from school import DEFAULT_LMS, normalize_lms, school_name


class SchoolPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.owner = wizard

    def validatePage(self):
        try:
            base = normalize_lms(self.owner.lms.text())
        except ValueError as e:
            QMessageBox.warning(self, 'LMS 주소 확인', str(e))
            return False
        if base != self.owner.previous_base:
            self.owner.username.clear(); self.owner.password.clear(); self.owner.token.clear()
            self.owner.previous_base = base
        self.owner.lms.setText(base)
        return True


class WelcomeWizard(QWizard):
    def __init__(self, parent=None, credentials=None):
        super().__init__(parent)
        self.setWindowTitle('Lecture Studio · 학교와 계정 설정')
        self.resize(720, 590)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        for button,text in [(QWizard.WizardButton.NextButton,'다음 →'),(QWizard.WizardButton.BackButton,'← 이전'),
                            (QWizard.WizardButton.FinishButton,'저장하고 연결'),(QWizard.WizardButton.CancelButton,'나중에 · 로컬 사용')]:
            self.setButtonText(button,text)
        credentials = credentials or {}
        self.previous_base = credentials.get('base_url', DEFAULT_LMS)
        self.page_with('01  환영합니다', '강의 다운로드와 마이크 녹음을 TXT로',
            'LMS 강의를 선택하거나 내 PC의 영상을 추가해 전사합니다. 마이크 녹음은 종료 후 MP3 저장과 TXT 전사를 자동으로 진행합니다.\n\n'
            '학교 연결 없이 녹음·로컬 전사만 사용하려면 [나중에 · 로컬 사용]을 누르세요.\n\n새 PC는 START_HERE.html의 설치 안내를 먼저 확인하세요.')
        page = SchoolPage(self)
        page.setTitle('02  학교 Canvas LMS 주소')
        page.setSubTitle('로그인 후 과목이 보이는 Canvas 주소를 입력하세요.')
        layout = QVBoxLayout(page)
        hint = QLabel('경북대학교: https://canvas.knu.ac.kr\n다른 학교: https://학교주소.instructure.com 또는 학교 자체 Canvas 주소\n\nSSO 로그인 주소(appfn 등)는 입력하지 마세요. Canvas API 연결 성공 여부는 마지막 단계에서 확인합니다.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.lms = QLineEdit(self.previous_base)
        self.lms.setPlaceholderText('https://학교의-Canvas-주소')
        layout.addWidget(self.lms)
        self.school_hint = QLabel()
        self.school_hint.setWordWrap(True);layout.addWidget(self.school_hint)
        self.lms.textChanged.connect(self.show_school)
        self.addPage(page);self.show_school()
        page, layout = self.page_with('03  로그인 방법', '수동 로그인을 기본으로 사용합니다',
            '학교 브라우저에서 직접 로그인해도 세션을 재사용합니다. 자동 입력을 원하면 아래 체크를 해제하고 아이디·비밀번호를 입력하세요. 다른 학교의 외부 SSO는 직접 로그인합니다.')
        self.manual_login = QCheckBox('수동 로그인 사용 (기존 로그인 세션은 재사용)')
        self.manual_login.setChecked(credentials.get('manual_login', True))
        layout.addWidget(self.manual_login)
        self.username = QLineEdit(credentials.get('username',''));self.username.setPlaceholderText('학교 아이디 (자동 입력 사용 시)')
        self.password = QLineEdit(credentials.get('password',''));self.password.setPlaceholderText('비밀번호 (자동 입력 사용 시)')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.username);layout.addWidget(self.password)
        self.manual_login.toggled.connect(self.toggle_manual)
        self.toggle_manual(self.manual_login.isChecked())
        self.remember = QCheckBox('이 Windows 사용자 계정에서 로그인 유지 (암호화 저장)')
        self.remember.setChecked(True);layout.addWidget(self.remember)
        page, layout = self.page_with('04  Canvas 토큰 발급', 'LMS → 계정 → 설정 → 새 액세스 토큰',
            '학교 화면에서 발급한 토큰을 붙여넣으세요. 학교 정책에 따라 토큰 발급이나 API 사용이 제한될 수 있습니다. 해당 경우 녹음·로컬 파일 전사를 사용할 수 있습니다.')
        btn = QPushButton('입력한 학교 LMS의 계정 설정 열기');btn.clicked.connect(self.open_settings);layout.addWidget(btn)
        self.token = QLineEdit(credentials.get('token',''));self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('이 학교에서 발급받은 Canvas 액세스 토큰');layout.addWidget(self.token)
        page.registerField('token*',self.token)
        self.page_with('05  과목·영상·자료 선택', '과목 선택 → 영상 목록 → 참고자료 → 전사 시작',
            'Canvas 파일함의 MP4와 모듈의 외부 도구·링크·페이지를 후보로 불러옵니다. 외부 영상 서비스는 학교마다 달라 모두 지원되지는 않습니다.\n\n'
            'PDF/PPT 자료를 연결하고 전사 시작을 누르면 숨김 브라우저에서 주소를 찾습니다. 필요할 때 로그인이나 재생 요청 창을 띄웁니다.\n\n'
            '경북대는 빨간색, 다른 학교는 주소에 따라 파랑·보라·청록 중 하나를 적용합니다. 공식 학교 색상을 조회하는 기능은 아닙니다.')
        self.page_with('06  마이크 녹음', '마이크 선택 → 녹음 시작 → 종료하고 전사',
            '왼쪽 마이크 녹음 탭에서 입력 장치를 고르고 녹음하세요. 시간과 입력 레벨이 표시됩니다. 종료하면 MP3와 복구용 WAV를 저장하고 TXT 전사를 시작합니다.\n\n'
            '녹음 중 자막을 출력하는 기능은 아닙니다. PC 내부 소리는 마이크로 자동 수집하지 않으며, 시스템에 제공되는 입력 장치가 있어야 합니다.\n\n'
            '계정 변경은 학교·계정 설정, 저장 정보 삭제는 로그아웃을 사용하세요.')

    def show_school(self):
        try:
            base=normalize_lms(self.lms.text())
            self.school_hint.setText('선택 학교: '+school_name(base)+'\nCanvas 여부는 토큰 연결 시 확인합니다.')
        except ValueError:
            self.school_hint.setText('학교 Canvas의 HTTPS 주소를 입력하세요.')

    def toggle_manual(self, enabled):
        self.username.setEnabled(not enabled);self.password.setEnabled(not enabled)

    def open_settings(self):
        try:
            QDesktopServices.openUrl(QUrl(normalize_lms(self.lms.text())+'/profile/settings'))
        except ValueError as e:
            QMessageBox.warning(self,'LMS 주소',str(e))

    def page_with(self,title,subtitle,text):
        page=QWizardPage();page.setTitle(title);page.setSubTitle(subtitle)
        layout=QVBoxLayout(page);desc=QLabel(text);desc.setWordWrap(True);layout.addWidget(desc);layout.addSpacing(18)
        self.addPage(page);return page,layout

    def credentials(self):
        manual=self.manual_login.isChecked()
        return {'base_url':normalize_lms(self.lms.text()), 'manual_login':manual,
                'username':'' if manual else self.username.text().strip(),
                'password':'' if manual else self.password.text(), 'token':self.token.text().strip()}
