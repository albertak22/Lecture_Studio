"""Canvas origin validation and school-specific presentation."""
import hashlib
from urllib.parse import urlsplit

DEFAULT_LMS = 'https://canvas.knu.ac.kr'


def normalize_lms(value):
    value = str(value or '').strip()
    if '://' not in value:
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('학교 Canvas LMS 주소를 확인해 주세요.') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or any(c.isspace() for c in value) or '\\' in value):
        raise ValueError('https://로 시작하는 학교 Canvas LMS 주소를 입력하세요.')
    # Canvas is hosted at the origin. Accept a pasted course/login link as input.
    path = parsed.path.rstrip('/')
    if path and not any(path == x or path.startswith(x + '/') for x in ('/courses','/login','/profile','/dashboard','/accounts')):
        raise ValueError('SSO 로그인 주소가 아닌 Canvas 과목 화면의 기본 주소를 입력하세요. 예: https://canvas.knu.ac.kr')
    host = parsed.hostname.encode('idna').decode('ascii').lower()
    if ':' in host:
        host = '[' + host + ']'
    return 'https://' + host + (f':{port}' if port and port != 443 else '')


def is_knu(base):
    return normalize_lms(base) == DEFAULT_LMS


def school_key(base):
    return hashlib.sha256(normalize_lms(base).encode()).hexdigest()[:12]


def school_name(base):
    return '경북대학교' if is_knu(base) else urlsplit(normalize_lms(base)).hostname


def accent(base):
    # KNU stays red; other Canvas sites get a stable non-red palette.
    if is_knu(base):
        return ('#b21e35','#95172b','#fff0f2','#e4b4bd')
    palettes = [('#245bc0','#1d4899','#edf3ff','#b6c8e8'),
                ('#6544a6','#503485','#f3effb','#ccbee6'),
                ('#006f87','#00586b','#eaf6fa','#b0d6df')]
    return palettes[int(school_key(base),16) % len(palettes)]
