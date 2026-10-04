import re, json, math
from backend import storage as db

def tokenize(text):
    words=re.findall(r'[a-zA-Z0-9_]+|[\u4e00-\u9fff]+',text.lower())
    out=[]
    for w in words:
        if re.fullmatch(r'[\u4e00-\u9fff]+',w):
            out.extend(w); out.extend(w[i:i+2] for i in range(len(w)-1))
        else: out.append(w)
    return out

def index_book(book_id):
    with db.connect() as c:
        c.execute('DELETE FROM passage_fts WHERE bookId=?',(book_id,)); c.execute('DELETE FROM passages WHERE bookId=?',(book_id,))
        for ch in c.execute('SELECT * FROM chapters WHERE bookId=? ORDER BY idx',(book_id,)).fetchall():
            n=0
            for match in re.finditer(r'[^\n]+',ch['content']):
                for offset in range(0,len(match.group()),900):
                    raw=match.group()[offset:offset+900]
                    text=raw.strip()
                    if not text: continue
                    n+=1; pid=db.uid(); start=match.start()+offset+len(raw)-len(raw.lstrip())
                    c.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?,?)',(pid,book_id,ch['id'],ch['title'],n,start,start+len(text),text))
                    c.execute('INSERT INTO passage_fts VALUES(?,?,?)',(pid,book_id,' '.join(tokenize(ch['title']+' '+text))))

def index_skills(book_id):
    with db.connect() as c:
        c.execute('DELETE FROM skill_fts WHERE bookId=?',(book_id,))
        for f in c.execute("SELECT * FROM skill_files WHERE bookId=? AND path NOT LIKE 'references/%' AND path != 'metadata.json'",(book_id,)).fetchall():
            c.execute('INSERT INTO skill_fts VALUES(?,?,?)',(f['id'],book_id,' '.join(tokenize(f['content']))))

def search(book_id, query, kind='book', limit=6):
    terms=list(dict.fromkeys(tokenize(query)))[:50]
    if not terms: return []
    expression=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
    fts='passage_fts' if kind=='book' else 'skill_fts'; table='passages' if kind=='book' else 'skill_files'
    restricted=" AND t.path NOT LIKE 'references/%' AND t.path != 'metadata.json'" if kind=='skill' else ''
    return db.rows(f'SELECT t.*, bm25({fts}) AS score FROM {fts} JOIN {table} t ON t.id={fts}.id WHERE {fts} MATCH ? AND {fts}.bookId=? {restricted} ORDER BY score LIMIT ?', (expression,book_id,limit))
