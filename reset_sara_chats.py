"""Explicit local chat reset. Stop SARA before running with --confirm-delete.

Clears chat stores and activity log, and removes runtime stdout/stderr logs that
may contain transcripts. Does not remove memories, notes, tasks or screenshots.
"""
import argparse
import json
from pathlib import Path
import socket

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-delete',action='store_true');args=parser.parse_args()
    if not args.confirm_delete:parser.error('Pass --confirm-delete to permanently clear chat history.')
    from sara_app.config import DATA_DIR,PORT
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(('127.0.0.1',PORT))==0:raise SystemExit('Stop SARA before clearing history.')
    root=Path(DATA_DIR).resolve()
    stores=[root/'conversations.json',root/'chats.json']
    activity=root/'activity.jsonl';runtime=root/'runtime'
    logs=[*runtime.glob('*.out.log'),*runtime.glob('*.err.log')]
    for path in [*stores,activity,*logs]:
        if not path.resolve().is_relative_to(root):raise SystemExit('Refusing a path outside SARA data.')
    for path in stores:
        if path.exists():
            data=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data,list):raise SystemExit('Invalid store; inspect before reset: '+path.name)
    # All targets validated before replacing anything.
    from sara_app.storage import _write_json_atomic
    for path in stores:_write_json_atomic(path,[])
    activity.write_text('',encoding='utf-8')
    for path in logs:path.unlink()
    print(f'Cleared conversations.json, chats.json and activity.jsonl; removed {len(logs)} runtime transcript logs. No backup created.')

if __name__=='__main__':main()
