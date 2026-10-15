"""One visible transcript per job, stable metadata across user renames."""
import hashlib
import json
from pathlib import Path
from core import atomic_json

MANAGEMENT = '_관리정보'


def metadata_path(default_output, key):
    out = Path(default_output)
    identity = str(key or out.name)
    return out.parent / MANAGEMENT / (hashlib.sha256(identity.encode()).hexdigest()[:24]+'.json')


def load_record(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError, ValueError):
        return {}


def resolved_output(default_output, metadata):
    name=metadata.get('output_name')
    if isinstance(name,str) and name and Path(name).name==name and '/' not in name and '\\' not in name and name.lower().endswith('.txt'):
        return Path(default_output).with_name(name)
    return Path(default_output)


def valid_txt_name(value):
    value=str(value).strip()
    if not value:
        raise ValueError('파일 이름을 입력해 주세요.')
    if not value.lower().endswith('.txt'):
        value += '.txt'
    from core import safe_name
    # Reject invalid names instead of silently saving under a different title.
    if safe_name(value)!=value or value[:-4].strip(' .')=='':
        raise ValueError('파일 이름에 사용할 수 없는 문자나 너무 긴 이름입니다. / \\ : * ? " < > | 문자는 제외해 주세요.')
    if value.lower().endswith(('.prompt.txt','.metadata.txt')):
        raise ValueError('본문과 보조 파일을 구분할 수 있도록 다른 이름을 입력하세요.')
    return value


def rename_transcript(source, requested):
    source=Path(source)
    if not source.is_file() or source.suffix.lower()!='.txt':
        raise ValueError('이름을 바꿀 TXT 파일을 찾지 못했습니다.')
    target=source.with_name(valid_txt_name(requested))
    if target==source:
        return source
    if target.exists():
        raise ValueError('같은 이름의 파일이 이미 있습니다. 다른 이름을 입력하세요.')
    updates=[]
    for path in (source.parent / MANAGEMENT).glob('*.json'):
        value=load_record(path)
        if value.get('output_name')==source.name:
            updates.append((path,value))
    # Renaming an older result also records its stable identity for future retries.
    legacy=source.with_suffix('.metadata.json')
    if not updates and legacy.is_file():
        value=load_record(legacy)
        if value:
            # Legacy jobs used filename stem as fallback identity. The worker can
            # also read the old metadata pointer below when resolving an old job.
            updates.append((legacy,value))
    source.rename(target)
    written=[]
    try:
        for path,old in updates:
            new=dict(old,output_name=target.name)
            atomic_json(path,new)
            written.append((path,old))
    except OSError:
        target.rename(source)
        for path,old in written:
            atomic_json(path,old)
        raise
    return target
