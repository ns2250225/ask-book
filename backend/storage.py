import json, os, sqlite3, uuid
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

DATA = Path(os.environ.get('BOOKSKILL_DATA', 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'bookskill.db'

def uid(): return uuid.uuid4().hex

def now(): return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

def init():
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS books(id TEXT PRIMARY KEY,title TEXT,author TEXT,language TEXT,fileType TEXT,fileHash TEXT,status TEXT,createdAt TEXT,progress INTEGER DEFAULT 0,stage TEXT DEFAULT '',error TEXT DEFAULT '',kind TEXT DEFAULT '其他',cover TEXT DEFAULT '',questions TEXT DEFAULT '{}',stats TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS chapters(id TEXT PRIMARY KEY,bookId TEXT REFERENCES books(id) ON DELETE CASCADE,idx INTEGER,title TEXT,content TEXT);
        CREATE TABLE IF NOT EXISTS skills(bookId TEXT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,metadata TEXT);
        CREATE TABLE IF NOT EXISTS skill_files(id TEXT PRIMARY KEY,bookId TEXT REFERENCES books(id) ON DELETE CASCADE,path TEXT,content TEXT,UNIQUE(bookId,path));
        CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY,bookId TEXT REFERENCES books(id) ON DELETE CASCADE,chapterId TEXT REFERENCES chapters(id) ON DELETE CASCADE,chapter TEXT,paragraph INTEGER,start INTEGER,end INTEGER,text TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS passage_fts USING fts5(id UNINDEXED,bookId UNINDEXED,tokens);
        CREATE VIRTUAL TABLE IF NOT EXISTS skill_fts USING fts5(id UNINDEXED,bookId UNINDEXED,tokens);
        CREATE TABLE IF NOT EXISTS checkpoints(bookId TEXT REFERENCES books(id) ON DELETE CASCADE,hash TEXT,value TEXT,PRIMARY KEY(bookId,hash));
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,bookId TEXT REFERENCES books(id) ON DELETE CASCADE,title TEXT,createdAt TEXT,updatedAt TEXT);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversationId TEXT REFERENCES conversations(id) ON DELETE CASCADE,role TEXT,content TEXT,refs TEXT DEFAULT '[]',createdAt TEXT);
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,bookId TEXT REFERENCES books(id) ON DELETE CASCADE,content TEXT,createdAt TEXT);
        ''')

def rows(sql, args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args)]

def one(sql,args=()):
    r=rows(sql,args); return r[0] if r else None

def execute(sql,args=()):
    with connect() as c: c.execute(sql,args)

def update_book(book_id, **values):
    execute('UPDATE books SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', (*values.values(),book_id))

def book(book_id):
    b=one('SELECT * FROM books WHERE id=?',(book_id,))
    if b:
        for field in ('questions','stats'): b[field]=json.loads(b[field])
        b['chapterCount']=one('SELECT count(*) AS n FROM chapters WHERE bookId=?',(book_id,))['n']
        b['metadata']=one('SELECT metadata FROM skills WHERE bookId=?',(book_id,))
        b['metadata']=json.loads(b['metadata']['metadata']) if b['metadata'] else None
    return b
