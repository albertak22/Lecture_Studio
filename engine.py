"""Background operations shared by the Qt UI. No GUI imports."""

from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import requests
from core import (
    Canvas,
    BrowserResolver,
    Cancelled,
    check_cancel,
    availability,
    media_session,
    download,
    atomic_json,
    safe_name,
    probe,
    require_duration,
)
from references import reference_terms
from school import DEFAULT_LMS, normalize_lms, is_knu, school_key

ROOT = Path(__file__).resolve().parent
DATA = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    / "KnuLectureTranscriber"
)


class Engine:
    def __init__(self, emit):
        self.emit = emit
        self.cancel = threading.Event()
        self.login_ready = threading.Event()
        self.api = None
        self.credentials = {}
        self.base_url = DEFAULT_LMS
        self.data_dir = DATA
        self.proc = None
        self.busy = False

    def start(self, fn, *args):
        if self.busy:
            return False
        self.busy = True
        self.cancel.clear()
        self.login_ready.clear()

        def worker():
            try:
                fn(*args)
            except Cancelled:
                self.emit(
                    "log", "작업 중지. 완료된 결과와 다운로드 중간 파일을 보존했습니다."
                )
                self.emit("status", "작업을 중지했습니다.")
            except Exception as e:
                reason = (
                    f"네트워크 오류 ({type(e).__name__}). 연결을 확인해 주세요."
                    if isinstance(e, requests.RequestException)
                    else str(e)
                )
                self.emit("error", reason)
            finally:
                self.busy = False
                self.emit("done", None)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def connect(self, token):
        api = Canvas(token, self.base_url)
        courses = api.courses(self.cancel)
        self.api = api
        self.emit("courses", courses)

    def scan(self, course):
        api = self.api
        self.emit("status", "Canvas에서 강의 목록을 읽고 있습니다.")
        items = api.candidates(course["id"], self.cancel, lambda s: self.emit("log", s))
        if not items:
            self.emit("status", "이 과목에 표시할 영상 후보가 없습니다.")
            return
        self.emit("clear", None)
        for lec in items:
            check_cancel(self.cancel)
            self.emit('lecture', (lec, {}, [], '선택 후 자동 확인'))
        self.emit('status', f'{len(items)}개 영상 후보를 불러왔습니다. 선택하고 전사 시작을 누르면 자동 진행합니다.')

    def profile_path(self):
        if is_knu(self.base_url):
            return self.data_dir / 'browser_profile'
        return self.data_dir / 'browser_profiles' / school_key(self.base_url)

    def resolve_selected(self, lec):
        with BrowserResolver(self.profile_path(), self.cancel,
                             self.login_ready, self.emit, self.credentials, base_url=self.base_url) as browser:
            browser.login(lec.key.split(':')[0])
            headers, cookies = browser.resolve(lec)
            if not lec.media_url:
                raise RuntimeError('실제 MP4를 찾지 못했습니다. 로그를 확인하세요. HLS/DRM 전용 영상은 지원하지 않습니다.')
            return headers, cookies

    def run_jobs(self, snapshot, output, config, manual, download_only=False):
        api = self.api
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("FFmpeg 설치가 필요합니다. 설치 안내를 확인하세요.")
        output.mkdir(parents=True, exist_ok=True)
        prepared = []
        # Validate all references before starting long downloads.
        for lec, refs, media in snapshot:
            check_cancel(self.cancel)
            terms = reference_terms(refs, manual) if not download_only else []
            hashes = (
                [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in refs]
                if not download_only
                else []
            )
            prepared.append((lec, terms, hashes, media))
        failures = 0
        for index, (lec, terms, hashes, (headers, cookies)) in enumerate(prepared, 1):
            check_cancel(self.cancel)
            self.emit("status", f"영상 준비 {index}/{len(prepared)}: {lec.title}")
            self.emit("row", (lec.key, "영상 준비 중"))
            course_folder = (
                "local" if lec.local_path else safe_name(lec.key.split(":")[0])
            )
            folder = output / course_folder if lec.local_path or is_knu(self.base_url) else output / school_key(self.base_url) / course_folder
            try:
                if lec.local_path:
                    video = Path(lec.local_path)
                    if not video.is_file() or not probe(video):
                        raise RuntimeError(
                            "로컬 파일을 읽을 수 없거나 오디오가 없습니다."
                        )
                else:
                    if lec.page_url and not lec.file_id:
                        headers, cookies = self.resolve_selected(lec)
                    headers = dict(headers)
                    headers.setdefault("Referer", self.base_url + "/")
                    url = lec.media_url
                    if not url:
                        raise RuntimeError("다운로드 주소가 없습니다.")
                    if lec.file_id and api:
                        url = api.get(f"files/{lec.file_id}").json()["url"]

                    def progress(done, total):
                        self.emit("progress", 100 * done / total if total else 0)
                        self.emit(
                            "status",
                            f"다운로드: {lec.title} · {done / 1048576:.1f} MiB"
                            + (f" / {total / 1048576:.1f} MiB" if total else ""),
                        )

                    video = download(
                        media_session(headers, cookies),
                        url,
                        folder / "videos" / (lec.stem + ".mp4"),
                        self.cancel,
                        progress,
                        lambda s: self.emit("log", s),
                        min_duration=10,
                    )
                duration = require_duration(video, 1 if lec.local_path else 10)
                self.emit("log", f"{lec.title}: 영상 길이 {duration / 60:.1f}분 확인")
                self.emit(
                    "row",
                    (
                        lec.key,
                        "다운로드 완료" if not lec.local_path else "전사 준비 완료",
                    ),
                )
                if not download_only:
                    config["jobs"].append(
                        {
                            "key": lec.key,
                            "title": lec.title,
                            "video": str(video),
                            "output": str(
                                Path(lec.local_path).parent.parent / (Path(lec.local_path).stem + '.txt')
                                if lec.local_path and Path(lec.local_path).parent.name == '오디오'
                                and Path(lec.local_path).parent.parent.parent.name == '녹음결과'
                                else folder / 'transcripts' / (lec.stem + '.txt')
                            ),
                            "terms": terms,
                            "reference_hashes": hashes,
                        }
                    )
            except Cancelled:
                raise
            except Exception as e:
                failures += 1
                import requests

                reason = (
                    type(e).__name__
                    if isinstance(e, requests.RequestException)
                    else str(e)
                )
                self.emit("log", f"{lec.title}: {reason}")
                self.emit("row", (lec.key, "실패 · 로그 확인"))
        if download_only:
            self.emit(
                "status",
                f"영상 준비 완료: {len(prepared) - failures}개 / 실패 {failures}개",
            )
            return
        if not config["jobs"]:
            raise RuntimeError("전사할 수 있는 영상이 없습니다. 로그를 확인하세요.")
        check_cancel(self.cancel)
        self.emit("progress", 0)
        with tempfile.TemporaryDirectory(prefix="knu_transcribe_") as d:
            job_path = Path(d) / "jobs.json"
            atomic_json(job_path, config)
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(ROOT / "transcribe_worker.py"),
                    str(job_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.proc = proc
            # Race: user may cancel between preflight and Popen.
            if self.cancel.is_set():
                self.kill_process()
            summary = None
            current_key = None
            key_by_output = {j["output"]: j["key"] for j in config["jobs"]}
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    if line.strip():
                        self.emit("log", line.strip()[:400])
                    continue
                typ = event.get("type")
                if typ == "progress":
                    self.emit("progress", event["percent"])
                elif typ == "status":
                    self.emit("status", event["text"])
                elif typ == "error":
                    self.emit("log", event["text"])
                    if current_key:
                        self.emit("row", (current_key, "전사 실패"))
                elif typ == "job":
                    current_key = event.get("key")
                    if current_key:
                        self.emit("row", (current_key, "전사 중"))
                elif typ == "saved":
                    self.emit(
                        "log",
                        ("완료 결과 재사용: " if event["skipped"] else "TXT 저장: ")
                        + event["path"],
                    )
                    self.emit("saved", event["path"])
                    key = key_by_output.get(event["path"], current_key)
                    if key:
                        self.emit("row", (key, "TXT 완료"))
                elif typ == "summary":
                    summary = event
            proc.wait()
            self.proc = None
            check_cancel(self.cancel)
            if summary:
                self.emit("progress", 100)
                self.emit(
                    "status",
                    f"TXT 저장 {summary['completed']}개 · 기존 결과 {summary['skipped']}개 · 실패 {summary['failed'] + failures}개",
                )
            elif proc.returncode:
                raise RuntimeError(
                    "전사 프로세스가 종료되었습니다. 환경 검사와 로그를 확인하세요."
                )

    def kill_process(self):
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    proc.terminate()
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

    def stop(self):
        self.cancel.set()
        self.login_ready.set()
        threading.Thread(target=self.kill_process, daemon=True).start()

    def environment(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "check_environment.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.emit("preview", ("환경 검사", p.stdout + "\n" + p.stderr))
