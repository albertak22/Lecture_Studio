"""Read-only environment check; does not install or upgrade packages."""

import importlib
import importlib.metadata
import shutil
import sys
from pathlib import Path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("Python:", sys.version.split()[0])
    print("실행 경로:", sys.executable)
    missing = []
    for module, package in [
        ("PySide6.QtWidgets", "PySide6"),
        ("requests", "requests"),
        ("fitz", "PyMuPDF"),
        ("playwright", "playwright"),
        ("whisper", "openai-whisper"),
        ("sounddevice", "sounddevice"),
    ]:
        try:
            importlib.import_module(module)
            print("OK:", module, importlib.metadata.version(package) if package else "")
        except Exception as e:
            missing.append(module)
            print("확인 필요:", module, type(e).__name__)
    for name in ("ffmpeg", "ffprobe"):
        exe = shutil.which(name)
        print(name + ":", exe or "설치/PATH 설정 필요")
        if not exe:
            missing.append(name)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = Path(p.chromium.executable_path)
            print(
                "Chromium:",
                "설치됨"
                if exe.exists()
                else "python -m playwright install chromium 필요",
            )
            if not exe.exists():
                missing.append("Chromium")
    except Exception:
        pass
    try:
        import torch

        print("PyTorch:", torch.__version__, "/ CUDA 빌드:", torch.version.cuda)
        if torch.cuda.is_available():
            print("GPU:", torch.cuda.get_device_name(0))
            result = (torch.ones(1, device="cuda") + 1).cpu().item()
            print("실제 GPU 연산:", "OK" if result == 2 else "확인 필요")
        else:
            print(
                "CUDA 사용 불가: CPU 전사는 가능. GPU를 쓰려면 CUDA 빌드/드라이버 확인."
            )
    except Exception as e:
        print("PyTorch/GPU 확인 필요:", type(e).__name__, str(e)[:300])
        missing.append("torch/GPU")
    from references import soffice_path

    print(
        "LibreOffice (.ppt 전용):", soffice_path() or "미설치 — PDF/PPTX에는 필요 없음"
    )
    print(
        "\n필수 항목 확인 필요: " + ", ".join(missing)
        if missing
        else "\n기본 실행 환경 확인 완료"
    )
    return bool(missing)


if __name__ == "__main__":
    raise SystemExit(main())
