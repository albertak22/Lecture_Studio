"""Local PDF/PPTX/PPT text and terminology extraction."""

from __future__ import annotations
import collections
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

STOP = set(
    "the and or to of with for in on at as by from is are what why how when where which who can will do does be been this that these those an a it we you your our its not page chapter section overview introduction course professor textbook references reference figure table example examples question questions".split()
)
PHRASES = [
    "Operating System",
    "Resource Management",
    "CPU Utilization",
    "Efficiency",
    "Fairness",
    "Batch Processing",
    "Serial Processing",
    "Multiprogramming",
    "Multitasking",
    "Time Sharing",
    "Job Control Language",
    "Scheduler",
    "Scheduling",
    "Throughput",
    "Latency",
    "Virtualization",
    "Concurrency",
    "Persistence",
    "Process",
    "Thread",
    "Context Switching",
    "Deadlock",
    "Semaphore",
    "Mutex",
    "Virtual Memory",
    "Paging",
    "Memory Management",
    "Interrupt",
    "System Call",
    "Kernel",
    "Microkernel",
    "Monolithic Kernel",
    "Device Driver",
    "File System",
    "Computer Architecture",
    "Clock Cycle",
    "Instruction",
    "CPU",
    "GPU",
    "IPC",
    "Cache",
    "Pipeline",
    "Packet Switching",
    "Circuit Switching",
    "Bandwidth",
    "Modulation",
    "Encoding",
    "Nyquist",
    "Shannon",
    "Signal to Noise Ratio",
    "SNR",
    "Sliding Window",
    "Go Back N",
    "Selective Repeat",
    "ARQ",
    "Network Layer",
    "Data Link Layer",
    "Dynamic Programming",
    "Greedy Algorithm",
    "Branch and Bound",
    "Backtracking",
    "Binary Search Tree",
    "Hash Table",
    "Graph",
    "Heap",
    "Queue",
    "Stack",
]


def soffice_path():
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for base in (
        os.environ.get("PROGRAMFILES", "C:/Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"),
    ):
        path = Path(base) / "LibreOffice/program/soffice.exe"
        if path.exists():
            return str(path)
    return None


def read_reference(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"참고자료가 없습니다: {path.name}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz

        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise ValueError(f"암호로 보호된 PDF입니다: {path.name}")
            text = "\n".join(page.get_text("text", sort=True) for page in doc)
    elif suffix == ".pptx":
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        with zipfile.ZipFile(path) as z:
            names = sorted(
                (
                    n
                    for n in z.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
                ),
                key=lambda n: int(re.search(r"(\d+)\.xml", n)[1]),
            )
            text = "\n".join(
                "\n".join(
                    "".join(t.text or "" for t in p.findall(".//a:t", ns))
                    for p in ET.fromstring(z.read(n)).findall(".//a:p", ns)
                )
                for n in names
            )
    elif suffix == ".ppt":
        exe = soffice_path()
        if not exe:
            raise ValueError(
                "구형 .ppt는 LibreOffice 설치가 필요합니다. 또는 PowerPoint에서 .pptx/PDF로 저장해 추가하세요."
            )
        with tempfile.TemporaryDirectory(prefix="knu_ppt_") as d:
            root = Path(d)
            p = subprocess.run(
                [
                    exe,
                    "-env:UserInstallation=" + (root / "profile").as_uri(),
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    d,
                    str(path.resolve()),
                ],
                capture_output=True,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            pdf = root / (path.stem + ".pdf")
            if p.returncode or not pdf.exists():
                raise ValueError(
                    "PPT 변환에 실패했습니다. PowerPoint에서 PDF로 저장해 추가하세요."
                )
            text = read_reference(pdf)
    else:
        raise ValueError("PDF, PPTX, PPT 파일만 지원합니다.")
    if not text.strip():
        raise ValueError(
            f"{path.name}: 추출할 텍스트가 없습니다. 이미지/스캔 자료는 OCR 후 PDF를 사용하거나 추가 용어를 직접 입력하세요."
        )
    return text


def extract_terms(text):
    flat = re.sub(r"\s+", " ", text)
    priority = [
        p
        for p in PHRASES
        if re.search(r"(?<![A-Za-z])" + re.escape(p) + r"(?![A-Za-z])", flat, re.I)
    ]
    counts = collections.Counter()
    for line in text.splitlines():
        line = line.strip()
        # Title phrases as well as lowercase terms; no fixed-vocabulary restriction.
        for word in re.findall(
            r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9/-]{2,}(?![A-Za-z])", line
        ):
            if word.casefold() not in STOP:
                counts[word] += 1 + int(word.isupper())
        if len(line) <= 110:
            for phrase in re.findall(
                r"\b[A-Z][A-Za-z/-]+(?:[ \t]+[A-Z][A-Za-z/-]+){1,3}\b", line
            ):
                if not any(w.casefold() in STOP for w in phrase.split()):
                    counts[phrase] += 3
    seen = {x.casefold() for x in priority}
    for term in sorted(counts, key=lambda x: (-counts[x], -len(x), x.casefold())):
        if term.casefold() not in seen:
            priority.append(term)
            seen.add(term.casefold())
    return priority


def reference_terms(paths, manual=""):
    terms, seen = [], set()
    # User-entered terms get first priority.
    sources = [[t.strip() for t in re.split(r"[,;\n]", manual) if t.strip()]]
    sources.extend(extract_terms(read_reference(p)) for p in paths)
    for source in sources:
        for t in source:
            if t.casefold() not in seen:
                terms.append(t)
                seen.add(t.casefold())
    return terms


def make_prompt(terms, encode, budget=180):
    selected = []
    for term in terms:
        candidate = "Lecture terminology: " + ", ".join(selected + [term]) + "."
        if len(encode(candidate)) <= budget:
            selected.append(term)
    return (
        "Lecture terminology: " + ", ".join(selected) + "." if selected else ""
    ), selected
