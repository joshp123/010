"""Retain transit input bytes. Written by AI on 2026-10-26 by model GPT-6."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import requests
from .build import SOURCE


def archive(name, url, license, credit):
    path=SOURCE/name
    metadata=path.with_suffix(path.suffix+'.source.json')
    if path.exists():
        entry=json.loads(metadata.read_text())
        raw=path.read_bytes()
        assert entry['url']==url and entry['sha256']==hashlib.sha256(raw).hexdigest()
        return path
    response=requests.get(url,timeout=180)
    response.raise_for_status()
    raw=response.content
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    metadata.write_text(json.dumps({'url':url,'license':license,'credit':credit,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fetchedAt':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
    return path
