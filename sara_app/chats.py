"""Local named conversations with atomic writes and independent history."""
from threading import RLock
from uuid import uuid4
from .config import DATA_DIR
from .storage import _read_json_list, _write_json_atomic, now

LOCK = RLock()
FILE = DATA_DIR / 'chats.json'

def _find(rows, identity):
    row = next((row for row in rows if row.get('id') == identity), None)
    if row is None: raise ValueError('Chat was deleted or does not exist. Choose another chat.')
    return row

def list_chats():
    with LOCK:
        return [{key: row.get(key) for key in ('id','title','created','updated')} for row in reversed(_read_json_list(FILE))]

def create(title='New chat'):
    if not isinstance(title,str) or not 1 <= len(title.strip()) <= 100: raise ValueError('Chat title must contain 1–100 characters.')
    with LOCK:
        rows=_read_json_list(FILE)
        if len(rows)>=100: raise ValueError('100 chats are saved. Export and remove an old chat first.')
        row={'id':uuid4().hex,'title':title.strip(),'created':now(),'updated':now(),'messages':[]}
        rows.append(row);_write_json_atomic(FILE,rows)
        return {key:value for key,value in row.items() if key!='messages'}

def messages(identity):
    with LOCK: return list(_find(_read_json_list(FILE),identity).get('messages',[]))

def rename(identity,title):
    if not isinstance(title,str) or not 1 <= len(title.strip()) <= 100: raise ValueError('Chat title must contain 1–100 characters.')
    with LOCK:
        rows=_read_json_list(FILE);row=_find(rows,identity);row['title']=title.strip();row['updated']=now();_write_json_atomic(FILE,rows)

def delete(identity):
    with LOCK:
        rows=_read_json_list(FILE);_find(rows,identity);_write_json_atomic(FILE,[row for row in rows if row['id']!=identity])

def append(identity,turn):
    with LOCK:
        rows=_read_json_list(FILE)
        # Deleting a chat during generation must not resurrect it.
        try: row=_find(rows,identity)
        except ValueError: return False
        if row['title']=='New chat' and turn.get('question') and not turn.get('initiated_by'):
            row['title']=str(turn['question'])[:70]
        row['messages']=(row.get('messages',[])+[turn])[-200:];row['updated']=now()
        rows.remove(row);rows.append(row);_write_json_atomic(FILE,rows);return True
