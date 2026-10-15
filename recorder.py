"""Bounded-memory microphone capture, recoverable WAV, then MP3 export."""
from array import array
from datetime import datetime
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import uuid
import wave


class MicrophoneRecorder:
    def __init__(self, emit):
        self.emit = emit
        self.stop_event = threading.Event()
        self.thread = None

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    @staticmethod
    def devices():
        import sounddevice as sd
        apis = sd.query_hostapis()
        return [(i, f"{d['name']} · {apis[d['hostapi']]['name']}")
                for i,d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]

    def start(self, folder, device=None):
        if self.active:
            raise RuntimeError('녹음이 이미 진행 중입니다.')
        if not shutil.which('ffmpeg'):
            raise RuntimeError('MP3 저장에 FFmpeg가 필요합니다. 설치 안내를 확인하세요.')
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(Path(folder),device), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self, folder, device):
        result = None
        wav_path = None
        part = None
        try:
            import sounddevice as sd
            info = sd.query_devices(device, 'input')
            rate = int(info['default_samplerate'])
            sd.check_input_settings(device=device, channels=1, dtype='int16', samplerate=rate)
            folder.mkdir(parents=True, exist_ok=True)
            name = '녹음_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
            bundle = folder / name
            folder = bundle / '오디오'
            folder.mkdir(parents=True, exist_ok=True)
            wav_path = folder / (name + '.wav')
            mp3 = folder / (name + '.mp3')
            part = folder / (name + '.mp3.part')
            chunks = queue.Queue(maxsize=128)
            overflow = threading.Event()
            device_warning = threading.Event()
            frames_written = 0
            peak = 0
            last_report = 0.0

            def callback(data, frames, timing, status):
                if status:
                    device_warning.set()
                try:
                    chunks.put_nowait(bytes(data))
                except queue.Full:
                    overflow.set()
                    self.stop_event.set()

            # Write PCM to disk continuously; no entire recording is held in RAM.
            with open(wav_path, 'wb') as raw:
                with wave.open(raw, 'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
                    with sd.RawInputStream(device=device, channels=1, dtype='int16',
                                           samplerate=rate, blocksize=2048, callback=callback) as stream:
                        self.emit('rec_started', str(wav_path))
                        while not self.stop_event.is_set():
                            try:
                                data = chunks.get(timeout=.2)
                            except queue.Empty:
                                if not stream.active:
                                    raise RuntimeError('마이크 연결이 중단되었습니다.')
                                continue
                            wav.writeframes(data)
                            frames_written += len(data)//2
                            peak = max((abs(v) for v in array('h',data)), default=0)
                            now = time.monotonic()
                            if now-last_report >= .2:
                                raw.flush()
                                self.emit('rec_level', (frames_written/rate, min(100,100*peak/32768)))
                                last_report = now
                    # Stream is closed before draining, so no callback can append afterwards.
                    while not chunks.empty():
                        data = chunks.get_nowait()
                        wav.writeframes(data)
                        frames_written += len(data)//2
            if overflow.is_set():
                raise RuntimeError('디스크 처리 지연으로 녹음이 중지되었습니다. 남은 WAV를 확인하세요.')
            if frames_written < rate:
                raise RuntimeError('녹음이 1초보다 짧습니다. WAV는 보존했습니다. 1초 이상 다시 녹음하세요.')
            if device_warning.is_set():
                self.emit('rec_warning', '마이크 입력 지연이 감지되었습니다. 저장된 녹음에 끊김이 있는지 확인하세요.')
            self.emit('rec_status', '녹음을 종료하고 MP3를 저장하고 있습니다…')
            with tempfile_log(folder) as log:
                proc = subprocess.run(
                    ['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(wav_path),
                     '-vn','-codec:a','libmp3lame','-b:a','128k','-f','mp3',str(part)],
                    stdout=subprocess.DEVNULL, stderr=log,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if proc.returncode or not part.exists() or part.stat().st_size == 0:
                    raise RuntimeError('MP3 변환에 실패했습니다. WAV 원본을 내 영상 추가로 열어 전사할 수 있습니다.')
            part.replace(mp3)
            result = str(mp3)
            # Keep the WAV as a recovery source, including after successful conversion.
            self.emit('rec_status', 'MP3 저장 완료. WAV 원본도 함께 보존했습니다.')
        except Exception as exc:
            detail = f'\n복구용 WAV: {wav_path}' if wav_path and wav_path.exists() else ''
            self.emit('rec_error', f'{type(exc).__name__}: {exc}{detail}')
        finally:
            if part:
                part.unlink(missing_ok=True)
            self.emit('rec_finished', result)


def tempfile_log(folder):
    import tempfile
    return tempfile.TemporaryFile(mode='w+b', dir=folder)
