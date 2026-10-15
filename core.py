"""KNU lecture discovery and resumable downloads. No transcription cloud APIs."""

from __future__ import annotations
import hashlib
import html
import itertools
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import requests
from school import DEFAULT_LMS, normalize_lms, is_knu

BASE = "https://canvas.knu.ac.kr"
CDN = "https://kyungpook-cms-global.edge.naverncp.com/contents9/kyungpook1"
REFERER = "https://lcms.knu.ac.kr/"


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled("사용자가 작업을 중지했습니다.")


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def safe_name(text):
    name = (
        re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(text)).strip(" .")[:90] or "lecture"
    )
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *("COM" + str(i) for i in range(1, 10)),
        *("LPT" + str(i) for i in range(1, 10)),
    }:
        name = "_" + name
    return name


def origin(url):
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)


def content_id_from_url(url):
    p = urlsplit(url)
    if p.hostname == "lcms.knu.ac.kr":
        m = re.fullmatch(r"/em/([A-Za-z0-9_-]{8,64})/?", p.path)
        if m:
            return m.group(1)
    return None


def video_url(content_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", content_id):
        raise ValueError("LCMS 콘텐츠 ID 형식이 잘못되었습니다.")
    return f"{CDN}/{content_id}/contents/media_files/screen.mp4"


@dataclass
class Lecture:
    key: str
    title: str
    module: str = ""
    page_url: str = ""
    media_url: str = ""
    content_id: str = ""
    local_path: str = ""
    file_id: int = 0

    @property
    def stem(self):
        return (
            safe_name(self.title)
            + "__"
            + hashlib.sha256(self.key.encode()).hexdigest()[:8]
        )


class Canvas:
    """Token is only attached to the exact Canvas API origin, never CDN requests."""

    def __init__(self, token, base_url=BASE):
        if not token.strip():
            raise ValueError("Canvas 액세스 토큰을 입력하세요.")
        self.base_url = normalize_lms(base_url)
        self.token = token.strip()
        self.session = requests.Session()

    def get(self, url, params=None):
        if not url.startswith("https://"):
            url = self.base_url + "/api/v1/" + url.lstrip("/")
        if origin(url) != origin(self.base_url) or not urlsplit(url).path.startswith("/api/v1/"):
            raise ValueError("Canvas API 외부로 토큰을 전송할 수 없습니다.")
        r = self.session.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=(15, 45),
            allow_redirects=False,
        )
        if r.status_code == 401:
            raise RuntimeError(
                "토큰이 만료되었거나 올바르지 않습니다. 새 토큰을 발급받으세요."
            )
        if r.status_code == 403:
            raise RuntimeError(
                "이 과목/자료에 접근할 권한이 없습니다. LMS 수강 권한을 확인하세요."
            )
        if 300 <= r.status_code < 400:
            raise RuntimeError(
                "Canvas API가 다른 주소로 이동했습니다. LMS 주소를 확인하세요."
            )
        if r.status_code >= 400:
            raise RuntimeError(f"Canvas API 응답 오류: HTTP {r.status_code}")
        return r

    def pages(self, path, cancel):
        result, seen = [], set()
        url = self.base_url + "/api/v1/" + path
        while url:
            check_cancel(cancel)
            if url in seen:
                raise RuntimeError("Canvas 페이지 순환 오류")
            seen.add(url)
            r = self.get(url, {"per_page": 100} if len(seen) == 1 else None)
            try:
                data = r.json()
            except ValueError:
                raise RuntimeError("Canvas API 응답이 아닙니다. 학교 Canvas 주소와 API 사용 가능 여부를 확인하세요.") from None
            if not isinstance(data, list):
                raise RuntimeError("Canvas 목록 응답 형식이 올바르지 않습니다.")
            result.extend(data)
            url = r.links.get("next", {}).get("url")
        return result

    def courses(self, cancel):
        return [
            c for c in self.pages("courses", cancel) if c.get("name") and c.get("id")
        ]

    def candidates(self, course_id, cancel, log):
        items = []
        known_files = set()
        modules = self.pages(f"courses/{int(course_id)}/modules", cancel)
        for module in modules:
            log("강의 목록 확인: " + module.get("name", ""))
            for item in self.pages(
                f"courses/{int(course_id)}/modules/{module['id']}/items", cancel
            ):
                typ = item.get("type")
                url = item.get("external_url") or ""
                if typ in ("ExternalTool", "ExternalUrl", "Page"):
                    items.append(
                        Lecture(
                            f"{course_id}:item:{item['id']}",
                            item.get("title", "영상"),
                            module.get("name", ""),
                            f"{self.base_url}/courses/{course_id}/modules/items/{item['id']}",
                            media_url=url
                            if urlsplit(url).path.lower().endswith(".mp4")
                            else "",
                            content_id=content_id_from_url(url) or "",
                        )
                    )
                elif typ == "File" and str(item.get("title", "")).lower().endswith(
                    ".mp4"
                ):
                    f = self.get(
                        f"courses/{course_id}/files/{item['content_id']}"
                    ).json()
                    known_files.add(f["id"])
                    items.append(
                        Lecture(
                            f"{course_id}:file:{f['id']}",
                            f.get("display_name", "영상"),
                            module.get("name", ""),
                            media_url=f["url"],
                            file_id=f["id"],
                        )
                    )
        try:
            files = self.pages(f"courses/{course_id}/files", cancel)
        except RuntimeError as e:
            log("파일함을 조회하지 못했습니다. 모듈 목록은 계속 사용합니다. " + str(e))
            files = []
        for f in files:
            if f["id"] not in known_files and (
                f.get("content-type") == "video/mp4"
                or f.get("display_name", "").lower().endswith(".mp4")
            ):
                items.append(
                    Lecture(
                        f"{course_id}:file:{f['id']}",
                        f.get("display_name", "영상"),
                        "파일함",
                        media_url=f["url"],
                        file_id=f["id"],
                    )
                )
        return items


def select_content_media(urls, content_id):
    """Never select a shared intro/placeholder merely because it arrived first."""
    if not content_id:
        return ""
    candidates = [
        u
        for u in urls
        if content_id in urlsplit(u).path.split("/")
        and urlsplit(u).path.lower().endswith(".mp4")
    ]
    return next(
        (u for u in candidates if urlsplit(u).path.endswith("/screen.mp4")),
        candidates[0] if candidates else video_url(content_id),
    )


def extract_media_urls(text, base_url):
    """Parse player JSON/config/HTML; retain signatures and relative path layout."""
    normal = html.unescape(
        re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), text).replace(
            "\\/", "/"
        )
    )
    urls = []

    def add(value):
        if not isinstance(value, str):
            return
        url = urljoin(base_url, html.unescape(value.strip()))
        if (
            urlsplit(url).scheme in ("http", "https")
            and urlsplit(url).path.lower().endswith(".mp4")
            and url not in urls
        ):
            urls.append(url)

    def traverse(value):
        if isinstance(value, str):
            add(value)
        elif isinstance(value, list):
            for v in value:
                traverse(v)
        elif isinstance(value, dict):
            for v in value.values():
                traverse(v)

    try:
        traverse(json.loads(text))
    except ValueError:
        pass
    for match in re.finditer(
        r"[\"']([^\"'<>\s]+\.mp4(?:\?[^\"'<>\s]*)?)[\"']", normal, re.I
    ):
        add(match[1])
    return urls[:100]


def rank_media_candidates(records, content_id):
    """Duration evidence beats ID/path guesses; unknown CDN object IDs are supported."""

    def score(r):
        duration = r.get("duration")
        known_long = duration is not None and duration >= 10
        matched = bool(content_id and content_id in urlsplit(r["url"]).path.split("/"))
        sources = r.get("sources", set())
        return (
            int(known_long),
            int("dom" in sources),
            int(matched),
            int("metadata" in sources),
            int(urlsplit(r["url"]).path.endswith("/screen.mp4")),
            int("network" in sources),
        )

    eligible = []
    for r in records:
        if r.get("status") is not None and r["status"] >= 400:
            continue
        duration = r.get("duration")
        if duration is not None and duration < 10:
            continue
        name = Path(urlsplit(r["url"]).path).name.lower()
        if duration is None and re.fullmatch(
            r"(?:intro|wait|waiting|loading|blank|dummy|preview|preroll|sample)(?:[_-]\d+)?\.mp4",
            name,
        ):
            continue
        # An unmatched bare network request can be a shared player asset.
        matched = bool(content_id and content_id in urlsplit(r["url"]).path.split("/"))
        if r.get("sources", set()) == {"network"} and not matched:
            continue
        eligible.append(r)
    return sorted(eligible, key=score, reverse=True)


class BrowserResolver:
    def __init__(self, profile, cancel, login_ready, emit, credentials=None, headless=True, base_url=BASE):
        self.profile, self.cancel, self.login_ready, self.emit = (
            Path(profile),
            cancel,
            login_ready,
            emit,
        )
        self.pw = self.context = None
        self.credentials = credentials or {}
        self.headless = headless
        self.base_url = normalize_lms(base_url)
        self.manual_login = self.credentials.get("manual_login", True)
        self.interactive_session = False
        self.course_id = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        try:
            self._launch()
        except Exception:
            self.pw.stop()
            raise RuntimeError(
                "브라우저를 열 수 없습니다. python -m playwright install chromium 을 실행하고 이전 앱 브라우저를 닫으세요."
            )
        return self

    def __exit__(self, *args):
        try:
            if self.context:
                self.context.close()
        finally:
            if self.pw:
                self.pw.stop()

    def _launch(self, state=None):
        self.context = self.pw.chromium.launch_persistent_context(
            str(self.profile), headless=self.headless, accept_downloads=False,
            viewport={"width": 1100, "height": 800},
        )
        if state:
            self.context.add_cookies(state.get("cookies", []))

    def switch_visibility(self, headless):
        if self.headless == headless:
            return
        state = self.context.storage_state()
        self.context.close()
        self.context = None
        self.headless = headless
        self._launch(state)

    @staticmethod
    def trusted_login_url(url):
        p = urlsplit(url)
        return p.scheme == 'https' and bool(p.hostname) and (
            p.hostname == 'knu.ac.kr' or p.hostname.endswith('.knu.ac.kr'))

    def course_page_state(self, page):
        """Inspect browser evidence; never infer login from an HTTP 200 alone."""
        try:
            parsed = urlsplit(page.url)
            if origin(page.url) != origin(self.base_url):
                return None
            if not self.course_id or not re.match(
                rf"^/courses/{re.escape(str(self.course_id))}(?:/|$)", parsed.path):
                return None
            return page.evaluate("""() => {
                const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
                const password = Array.from(document.querySelectorAll('input[type=password]')).some(visible);
                const body = (document.body?.innerText || '').trim();
                const env = window.ENV || {};
                const user = !!(env.current_user_id || env.current_user?.id);
                const nav = !!document.querySelector('#section-tabs, #course_home_content, .context_module, #context_modules');
                const account = !!document.querySelector('#global_nav_profile_link, a[href="/profile"], a[href="/logout"]');
                const denied = /^(access denied|unauthorized|page not found|접근 권한이 없습니다|권한이 없습니다)/i.test(body);
                return {password, user, nav, account, denied, text_length:body.length};
            }""")
        except Exception:
            return None

    def authenticated(self):
        for page in self.context.pages:
            state = self.course_page_state(page)
            if state and not state.get('password') and not state.get('denied') and (
                state.get('user') or (state.get('nav') and state.get('account'))):
                return True
        return False

    def manual_course_confirmed(self):
        # The explicit Continue click allows actual media access to be attempted
        # on a customized Canvas page without the standard DOM markers.
        for page in self.context.pages:
            state = self.course_page_state(page)
            if (state and not state.get('password') and not state.get('denied')
                    and state.get('text_length', 0) > 40):
                return True
        return False

    def trusted_for_credentials(self, url):
        if is_knu(self.base_url):
            return self.trusted_login_url(url)
        return urlsplit(url).scheme == 'https' and origin(url) == origin(self.base_url)

    def auto_login(self, page):
        """Submit once, only a recognizable form on a school HTTPS origin."""
        if self.manual_login:
            return False
        username, password = self.credentials.get('username'), self.credentials.get('password')
        if not username or not password:
            return False
        entered = False
        for frame in page.frames:
            if not self.trusted_for_credentials(frame.url):
                continue
            try:
                passwords = frame.locator('input[type="password"]:visible')
                if passwords.count() != 1:
                    continue
                pwd = passwords.first
                action = pwd.evaluate('(e) => e.form ? e.form.action : ""')
                if not self.trusted_for_credentials(action):
                    continue
                form = pwd.locator('xpath=ancestor::form')
                users = form.locator('input[autocomplete="username"]:visible, input[name="user_id"]:visible, input[name="username"]:visible, input[name="userid"]:visible, input[name="userId"]:visible, input[name="id"]:visible, input[name="pseudonym_session[unique_id]"]:visible')
                if users.count() != 1:
                    users = form.locator('input[type="text"]:visible, input[type="email"]:visible')
                if users.count() != 1:
                    continue
                users.first.fill(username, timeout=2000)
                pwd.fill(password, timeout=2000)
                entered = True
                submit = form.locator('button[type="submit"]:visible, input[type="submit"]:visible')
                if submit.count():
                    submit.first.click(timeout=2500)
                else:
                    pwd.press('Enter', timeout=2500)
                return True
            except Exception:
                if entered:
                    return True
                continue
        return False

    def login(self, course_id):
        self.course_id = str(course_id)
        if not self.course_id.isdigit():
            raise ValueError('Canvas 과목 ID가 올바르지 않습니다.')
        target = f"{self.base_url}/courses/{self.course_id}"
        if self.authenticated():
            return
        page = self.context.pages[0] if self.context.pages else self.context.new_page()
        try:
            page.goto(target, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass
        attempted = False
        for _ in range(8):
            check_cancel(self.cancel)
            if self.authenticated():
                self.emit('log', '과목 화면에서 로그인 상태를 확인했습니다.')
                return
            if not attempted and not self.manual_login:
                attempted = self.auto_login(page)
            page.wait_for_timeout(500)
        self.switch_visibility(False)
        page = self.context.pages[0] if self.context.pages else self.context.new_page()
        try:
            page.goto(target, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass
        self.login_ready.clear()
        self.emit('login', '열린 학교 브라우저에서 로그인하세요. 과목 화면 확인 후 [로그인 완료 · 계속]을 누르면 영상 탐색을 시도합니다.')
        self.emit('attention', ('학교 로그인', '학교 브라우저에서 로그인한 뒤 과목 화면까지 이동해 주세요. [로그인 완료 · 계속]을 누르세요.'))
        try:
            while True:
                check_cancel(self.cancel)
                live = [p for p in self.context.pages if not p.is_closed()]
                if not live:
                    raise RuntimeError('로그인 창이 닫혔습니다. 다시 시작해 주세요.')
                if self.authenticated():
                    self.emit('log', '과목 화면의 로그인 정보를 확인해 자동으로 계속합니다.')
                    break
                if self.login_ready.is_set():
                    self.login_ready.clear()
                    if self.manual_course_confirmed():
                        self.emit('log', '사용자가 과목 화면을 확인했습니다. 실제 영상 접근을 시도합니다.')
                        break
                    self.emit('attention', ('과목 화면 확인', '학교 로그인 화면에 머물러 있거나 과목 화면을 확인하지 못했습니다. 로그인 후 원래 과목 탭으로 이동하고 다시 계속을 눌러주세요.'))
                live[0].wait_for_timeout(250)
        finally:
            self.emit('login_done', '')
        # Keep the exact successful browser alive; do not discard sessionStorage
        # or tab-scoped SSO state by immediately restarting Chromium.
        self.interactive_session = True

    def resolve(self, lecture, timeout=25):
        if self.interactive_session:
            return self._resolve(lecture, timeout=180, manual=True)
        self.switch_visibility(True)
        result = self._resolve(lecture, timeout=timeout)
        if lecture.media_url:
            return result
        check_cancel(self.cancel)
        self.switch_visibility(False)
        try:
            return self._resolve(lecture, timeout=180, manual=True)
        finally:
            self.emit('attention_done', None)
            self.switch_visibility(True)

    def _resolve(self, lecture, timeout=40, manual=False):
        """Discover this page's real sources, independent of semester/CDN layout."""
        check_cancel(self.cancel)
        old_pages = set(self.context.pages)
        page = self.context.new_page()
        candidates = {}
        requests_by_url = {}
        metadata_count = 0
        hls_seen = False
        cid = lecture.content_id
        checked = {}
        played = set()
        result = None
        chosen_at = None
        first_candidate = None
        seen_lcms = False

        def owned(req):
            try:
                return req.frame.page not in old_pages
            except Exception:
                return False

        def add(url, source, referer="", duration=None, status=None):
            nonlocal first_candidate
            if urlsplit(url).scheme not in ("https", "http"):
                return
            record = candidates.setdefault(
                url,
                {
                    "url": url,
                    "sources": set(),
                    "referer": referer,
                    "duration": None,
                    "status": None,
                },
            )
            record["sources"].add(source)
            if referer:
                record["referer"] = referer
            if duration is not None:
                record["duration"] = duration
            if status is not None:
                record["status"] = status
            first_candidate = first_candidate or time.monotonic()

        def on_request(req):
            nonlocal hls_seen
            if not owned(req):
                return
            path = urlsplit(req.url).path.lower()
            if path.endswith(".m3u8"):
                hls_seen = True
            if path.endswith(".mp4"):
                requests_by_url[req.url] = req
                add(req.url, "network", req.frame.url)

        def on_response(response):
            if not owned(response.request):
                return
            if urlsplit(response.url).path.lower().endswith(
                ".mp4"
            ) or response.headers.get("content-type", "").split(";")[0].lower() in (
                "video/mp4",
                "application/mp4",
            ):
                requests_by_url[response.url] = response.request
                add(
                    response.url,
                    "network",
                    response.request.frame.url,
                    status=response.status,
                )

        def on_finished(req):
            nonlocal metadata_count
            if (
                not owned(req)
                or req.resource_type not in ("xhr", "fetch", "document", "script")
                or urlsplit(req.url).path.lower().endswith((".mp4", ".m3u8"))
            ):
                return
            try:
                response = req.response()
                if not response or response.status >= 400:
                    return
                headers = response.headers
                ctype = headers.get("content-type", "").lower()
                if not any(
                    x in ctype
                    for x in ("json", "xml", "html", "javascript", "text/plain")
                ):
                    return
                if int(headers.get("content-length", "0") or 0) > 2_000_000:
                    return
                body = response.body()
                if len(body) > 2_000_000:
                    return
                for url in extract_media_urls(
                    body.decode("utf-8", errors="replace"), response.url
                ):
                    add(url, "metadata", req.frame.url)
                    metadata_count += 1
            except Exception:
                pass

        self.context.on("request", on_request)
        self.context.on("response", on_response)
        self.context.on("requestfinished", on_finished)
        try:
            try:
                page.goto(lecture.page_url, wait_until="commit", timeout=45000)
            except Exception:
                pass
            if manual:
                page.bring_to_front()
                self.emit("attention", ("재생 버튼을 눌러주세요", f"{lecture.title}\n자동 탐색이 완료되지 않아 브라우저를 열었습니다. 재생 버튼을 눌러주세요. 영상 주소가 확인되면 자동으로 다운로드와 전사를 계속합니다. (최대 3분 대기, 앱에서 중지 가능)"))
            start = time.monotonic()
            end = start + timeout
            notice_sent = False
            fallback_tested = False
            while time.monotonic() < end:
                check_cancel(self.cancel)
                new_pages = [
                    p
                    for p in self.context.pages
                    if p not in old_pages and not p.is_closed()
                ]
                for p in new_pages:
                    for frame in p.frames:
                        candidate_id = content_id_from_url(frame.url)
                        if candidate_id:
                            cid = candidate_id
                            seen_lcms = True
                        try:
                            sources = frame.evaluate("""() => Array.from(document.querySelectorAll('video')).map(v => ({
                                url: v.currentSrc || v.src,
                                sources: Array.from(v.querySelectorAll('source')).map(s=>s.src),
                                duration: Number.isFinite(v.duration) ? v.duration : null,
                                paused: v.paused
                            }))""")
                            for source in sources:
                                if source.get("url"):
                                    add(
                                        source["url"],
                                        "dom",
                                        frame.url,
                                        duration=source.get("duration"),
                                    )
                                for url in source.get("sources", []):
                                    add(url, "dom", frame.url)
                                key = (frame.url, source.get("url"))
                                if source.get("paused") and key not in played:
                                    played.add(key)
                                    # Load actual media, including players that transition after a waiting clip.
                                    frame.evaluate("""() => {for(const v of document.querySelectorAll('video')) {
                                        v.muted=true; const p=v.play(); if(p) p.catch(()=>{});
                                    }}""")
                            if time.monotonic() - start > 2:
                                for selector in (
                                    ".vjs-big-play-button",
                                    'button[aria-label="재생"]',
                                    'button[aria-label="Play"]',
                                    'button[title="재생"]',
                                    'button[title="Play"]',
                                    ".jw-icon-display",
                                    '.plyr__control[data-plyr="play"]',
                                ):
                                    key = (frame.url, selector)
                                    if key not in played:
                                        control = frame.locator(selector).first
                                        if control.count() and control.is_visible():
                                            played.add(key)
                                            control.click(timeout=1000)
                        except Exception:
                            pass
                # Test the OS-compatible fallback once, but do not end discovery if it fails.
                if is_knu(self.base_url) and cid and not fallback_tested and time.monotonic() - start > 5:
                    fallback_tested = True
                    add(video_url(cid), "fallback", REFERER)
                ranked = rank_media_candidates(list(candidates.values()), cid)
                # Give the intro->lecture switch and metadata responses time to settle.
                if first_candidate and time.monotonic() - first_candidate >= 2:
                    cookies = self.context.cookies()
                    previous_url = result[0]["url"] if result else None
                    result = None
                    for record in ranked:
                        url = record["url"]
                        last = checked.get(url)
                        if last is not None and not last[0]:
                            continue
                        headers = self.candidate_headers(
                            record, requests_by_url.get(url)
                        )
                        if last is None:
                            self.emit(
                                "status", f"{lecture.title}: 영상 후보 접근 확인 중"
                            )
                            last = availability(media_session(headers, cookies), url)
                            checked[url] = last
                        if last[0]:
                            result = (record, headers, cookies)
                            chosen_at = (
                                (chosen_at or time.monotonic())
                                if url == previous_url
                                else time.monotonic()
                            )
                            break
                    if result and time.monotonic() - chosen_at > 1:
                        break
                if time.monotonic() - start > 8 and not notice_sent and result is None:
                    notice_sent = True
                    self.emit(
                        "status",
                        f"{lecture.title}: " + ("열린 브라우저에서 재생 버튼을 눌러주세요." if manual else "숨김 브라우저에서 영상 주소를 자동 탐색하고 있습니다."),
                    )
                if not new_pages:
                    break
                new_pages[0].wait_for_timeout(300)
            lecture.content_id = cid or ""
            # Re-rank after the settle window so a now-loaded long video supersedes the intro.
            if result:
                ranked = rank_media_candidates(list(candidates.values()), cid)
                for record in ranked:
                    url = record["url"]
                    headers = self.candidate_headers(record, requests_by_url.get(url))
                    cookies = self.context.cookies()
                    ok, reason = checked.get(url) or availability(
                        media_session(headers, cookies), url
                    )
                    if ok:
                        result = (record, headers, cookies)
                        break
                if result[0] not in ranked:
                    result = None
            if result:
                record, headers, cookies = result
                lecture.media_url = record["url"]
                self.emit(
                    "log",
                    f"{lecture.title}: 실제 영상 주소 확인 ({urlsplit(lecture.media_url).hostname}; 탐색 후보 {len(candidates)}개)",
                )
                return headers, cookies
            lecture.media_url = ""
            reasons = sorted(set(reason for ok, reason in checked.values() if not ok))
            detail = " / ".join(reasons[:3]) or (
                "HLS 재생만 확인됨" if hls_seen else "실제 MP4 주소를 발견하지 못함"
            )
            self.emit(
                "log",
                f"{lecture.title}: 탐색 실패 — LCMS ID {'확인' if cid else '미확인'}, MP4 후보 {len(candidates)}개, 설정에서 추출 {metadata_count}개, {detail}",
            )
            return {}, []
        finally:
            self.context.remove_listener("request", on_request)
            self.context.remove_listener("response", on_response)
            self.context.remove_listener("requestfinished", on_finished)
            for p in list(self.context.pages):
                if p not in old_pages:
                    try:
                        p.close()
                    except Exception:
                        pass

    def candidate_headers(self, record, request):
        headers = {
            "Referer": record.get("referer") or (REFERER if is_knu(self.base_url) else self.base_url + "/"),
            "User-Agent": self.context.pages[0].evaluate("navigator.userAgent"),
        }
        if request is not None:
            try:
                captured = request.all_headers()
                for key in ("referer", "user-agent", "origin", "authorization"):
                    if captured.get(key):
                        headers[key] = captured[key]
            except Exception:
                pass
        return headers


def media_session(headers=None, cookies=None):
    s = requests.Session()
    s.headers.update(
        {"User-Agent": "Mozilla/5.0", "Referer": REFERER, "Accept-Encoding": "identity"}
    )
    if headers:
        s.headers.update(headers)
    for c in cookies or []:
        s.cookies.set(
            c["name"],
            c["value"],
            domain=c["domain"],
            path=c.get("path", "/"),
            secure=c.get("secure", False),
        )
    return s


def media_duration(path):
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg/ffprobe를 설치하고 프로그램을 다시 시작하세요.")
    p = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if p.returncode:
        return 0.0
    try:
        obj = json.loads(p.stdout)
        duration = float(obj.get("format", {}).get("duration", 0))
        return (
            duration
            if any(s.get("codec_type") == "audio" for s in obj.get("streams", []))
            and duration > 0
            else 0.0
        )
    except (ValueError, TypeError):
        return 0.0


def probe(path):
    return media_duration(path) > 0


def require_duration(path, minimum):
    duration = media_duration(path)
    if duration < minimum:
        raise RuntimeError(
            f"영상 길이가 {duration:.1f}초로 너무 짧습니다. 대기 영상일 수 있어 전사를 중단했습니다. MP4 목록을 다시 불러오세요."
        )
    return duration


def availability(session, url):
    if not url:
        return False, "영상 주소 미확인"
    try:
        with session.get(
            url, headers={"Range": "bytes=0-4095"}, timeout=(10, 20), stream=True
        ) as r:
            if r.status_code not in (200, 206):
                return False, f"HTTP {r.status_code}"
            ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
            if ctype in (
                "video/mp4",
                "application/mp4",
                "video/x-m4v",
                "application/octet-stream",
                "binary/octet-stream",
            ):
                return True, "MP4 응답 확인"
            if ctype in ("text/html", "application/json"):
                return False, "로그인 화면 또는 JSON 응답"
            first = next(r.iter_content(512), b"")
            if b"ftyp" in first[:32]:
                return True, "MP4 헤더 확인"
            return False, f"영상 형식 미확인 ({ctype or 'Content-Type 없음'})"
    except requests.RequestException as e:
        return False, f"네트워크 오류 ({type(e).__name__})"


def available(session, url):
    return availability(session, url)[0]


def download(session, url, target, cancel, progress, log, min_duration=0):
    """Require full byte count + ffprobe before promoting .part to final MP4."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        duration = media_duration(target)
        if duration > 0 and duration < min_duration:
            backup = target.with_name(
                target.stem + f".short-{time.time_ns()}" + target.suffix
            )
            target.rename(backup)
            log(
                f"기존 {duration:.1f}초 파일을 별도 보관하고 다시 다운로드합니다: {backup.name}"
            )
        elif duration > 0:
            log("완료된 영상 재사용: " + target.name)
            return target
        else:
            raise RuntimeError(
                "기존 영상이 손상되었습니다. 다른 저장 폴더를 선택하거나 해당 파일을 옮기세요."
            )
    part = target.with_suffix(target.suffix + ".part")
    meta = part.with_suffix(part.suffix + ".json")
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    old = {}
    if meta.exists():
        try:
            old = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if part.exists() and old.get("url_hash") != url_hash:
        part.unlink()  # Our own incomplete file; incompatible source.
        old = {}
    for attempt in range(4):
        check_cancel(cancel)
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        if offset and old.get("validator"):
            headers["If-Range"] = old["validator"]
        try:
            with session.get(url, headers=headers, stream=True, timeout=(15, 45)) as r:
                if r.status_code in (401, 403, 404):
                    raise RuntimeError(
                        f"영상 HTTP {r.status_code}: 로그인 세션 또는 영상 주소가 만료됐을 수 있습니다. 목록을 다시 불러오세요."
                    )
                if r.status_code == 416:
                    m = re.fullmatch(
                        r"bytes \*/(\d+)", r.headers.get("Content-Range", "")
                    )
                    if m and offset == int(m[1]) and probe(part):
                        require_duration(part, min_duration)
                        part.replace(target)
                        meta.unlink(missing_ok=True)
                        return target
                    raise RuntimeError(
                        "이어받기 크기가 맞지 않습니다. .part 파일을 옮기고 다시 시도하세요."
                    )
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
                chunks = r.iter_content(1024 * 512)
                if ctype not in (
                    "video/mp4",
                    "application/mp4",
                    "video/x-m4v",
                    "application/octet-stream",
                    "binary/octet-stream",
                ):
                    first = next(chunks, b"")
                    signature = first[:32]
                    if offset and r.status_code == 206:
                        with part.open("rb") as existing:
                            signature = existing.read(32)
                    if b"ftyp" not in signature or ctype in (
                        "text/html",
                        "application/json",
                        "text/xml",
                    ):
                        raise RuntimeError(
                            "영상 대신 로그인 화면 또는 다른 형식이 반환되었습니다."
                        )
                    chunks = itertools.chain([first], chunks)
                total = None
                if r.status_code == 206:
                    m = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+)", r.headers.get("Content-Range", "")
                    )
                    if (
                        not m
                        or int(m[1]) != offset
                        or int(m[2]) < offset
                        or int(m[2]) >= int(m[3])
                    ):
                        raise RuntimeError("서버의 이어받기 범위가 올바르지 않습니다.")
                    total = int(m[3])
                else:
                    offset = 0  # Range ignored / If-Range validator changed.
                    if r.headers.get("Content-Length"):
                        total = int(r.headers["Content-Length"])
                old = {
                    "url_hash": url_hash,
                    "validator": r.headers.get("ETag")
                    or r.headers.get("Last-Modified"),
                    "total": total,
                }
                atomic_json(meta, old)
                count = offset
                last = 0.0
                with part.open("ab" if offset else "wb") as f:
                    for chunk in chunks:
                        check_cancel(cancel)
                        if chunk:
                            f.write(chunk)
                            count += len(chunk)
                            if time.monotonic() - last > 0.25:
                                progress(count, total)
                                last = time.monotonic()
                progress(count, total)
                if total is not None and count != total:
                    if count > total:
                        raise RuntimeError(
                            "영상 크기가 서버 크기보다 큽니다. .part 파일을 확인하세요."
                        )
                    log("분할 응답을 이어서 받습니다.")
                    continue
            if not probe(part):
                raise RuntimeError(
                    "다운로드한 파일에서 정상 오디오를 확인하지 못했습니다. .part 파일은 보존했습니다."
                )
            require_duration(part, min_duration)
            part.replace(target)
            meta.unlink(missing_ok=True)
            return target
        except requests.RequestException:
            log(f"연결 중단: 재시도 {attempt + 1}/4 (받은 부분 보존)")
            if cancel.wait(min(2**attempt, 8)):
                raise Cancelled()
    raise RuntimeError("다운로드가 완료되지 않았습니다. 다시 실행하면 이어받습니다.")
