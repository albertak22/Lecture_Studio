"""Separate process: GPU memory is released and cancellation is reliable."""

from __future__ import annotations
import hashlib
import importlib
import inspect
import json
import sys
import time
from pathlib import Path
from core import atomic_json
from references import make_prompt


from results_store import metadata_path, load_record, resolved_output


def emit(kind, **data):
    print(json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)


def run(config, model_loader=None, tokenizer_factory=None):
    # Optional injection is for offline integration tests, never selected in the GUI.
    if model_loader is None:
        import torch
        import whisper
        from whisper.tokenizer import get_tokenizer

        device = config["device"]
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA를 사용할 수 없습니다. 환경 검사 후 PyTorch GPU 설치를 확인하거나 CPU를 선택하세요."
                )
            # A real kernel operation catches unsupported GPU architectures early.
            try:
                (torch.ones(1, device="cuda") + 1).cpu()
            except Exception as e:
                raise RuntimeError(
                    "GPU/PyTorch 호환 오류입니다. RTX 5070용 CUDA 빌드 및 NVIDIA 드라이버를 확인하세요."
                ) from e
        model_loader = lambda name: whisper.load_model(name, device=device)
        tokenizer_factory = get_tokenizer
        # Report progress without changing Whisper's decoding algorithm.
        module = importlib.import_module("whisper.transcribe")
        original = module.tqdm.tqdm

        class Progress(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.last_sent = 0

            def update(self, n=1):
                result = super().update(n)
                if time.monotonic() - self.last_sent > 0.5 and self.total:
                    emit("progress", percent=min(100, 100 * self.n / self.total))
                    self.last_sent = time.monotonic()
                return result

        module.tqdm.tqdm = Progress
    else:
        device = config["device"]
    tokenizer = tokenizer_factory(
        multilingual=True, language=config.get("language") or "ko", task="transcribe"
    )
    model = None
    completed = skipped = failed = 0
    for job in config["jobs"]:
        emit("job", title=job["title"], key=job.get("key"))
        try:
            video = Path(job["video"])
            out = Path(job["output"])
            out.parent.mkdir(parents=True, exist_ok=True)
            prompt, selected = make_prompt(job["terms"], tokenizer.encode)
            st = video.stat()
            source = {
                "video": str(video.resolve()),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "model": config["model"],
                "device": device,
                "language": config.get("language"),
                "prompt": prompt,
                "reference_hashes": job.get("reference_hashes", []),
                "pipeline": 1,
            }
            fingerprint = hashlib.sha256(
                json.dumps(source, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            meta = metadata_path(out, job.get('key'))
            previous = load_record(meta)
            if not previous:
                previous = load_record(out.with_suffix('.metadata.json'))
            out = resolved_output(out, previous)
            if not config.get("force") and out.exists() and previous:
                try:
                    if (
                        previous.get("fingerprint")
                        == fingerprint
                    ):
                        atomic_json(meta, dict(previous, output_name=out.name))
                        emit("saved", path=str(out), skipped=True)
                        skipped += 1
                        continue
                except (ValueError, OSError):
                    pass
            if model is None:
                emit(
                    "status",
                    text=f"Whisper {config['model']} 모델 로딩 ({device}). 첫 실행은 모델 다운로드로 시간이 걸립니다.",
                )
                model = model_loader(config["model"])
            emit(
                "status", text=f"전사 중: {job['title']} / 참고 용어 {len(selected)}개"
            )
            kwargs = dict(
                language=config.get("language") or None,
                task="transcribe",
                initial_prompt=prompt or None,
                fp16=device == "cuda",
                verbose=False,
            )
            if "carry_initial_prompt" in inspect.signature(model.transcribe).parameters:
                kwargs["carry_initial_prompt"] = True
            result = model.transcribe(str(video), **kwargs)
            text = (
                "\n".join(
                    s["text"].strip()
                    for s in result.get("segments", [])
                    if s.get("text", "").strip()
                )
                or result.get("text", "").strip()
            )
            if not text:
                raise RuntimeError(
                    "인식된 음성이 없습니다. 오디오와 언어 설정을 확인하세요."
                )
            temp = out.with_suffix(".txt.tmp")
            temp.write_text(text + "\n", encoding="utf-8-sig")
            temp.replace(out)
            atomic_json(
                meta,
                {
                    "output_name": out.name,
                    "fingerprint": fingerprint,
                    "source": source,
                    "terms": selected,
                    "completed": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            emit("saved", path=str(out), skipped=False)
            completed += 1
        except Exception as e:
            failed += 1
            emit("error", text=f"{job['title']}: {type(e).__name__}: {e}")
    emit("summary", completed=completed, skipped=skipped, failed=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        with open(sys.argv[1], encoding="utf-8") as f:
            config = json.load(f)
        raise SystemExit(run(config))
    except Exception as e:
        emit("error", text=f"{type(e).__name__}: {e}")
        raise SystemExit(1)
