import os, sqlite3, time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'billiard_club.db')
PORT = int(os.environ.get('PORT', '8000'))


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY, typ TEXT NOT NULL, no INTEGER NOT NULL,
        price REAL NOT NULL DEFAULT 30000, active INTEGER NOT NULL DEFAULT 0,
        started REAL DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT, typ TEXT, tab_no INTEGER,
        name TEXT, price REAL, qty INTEGER, created REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, typ TEXT, tab_no INTEGER,
        started REAL, ended REAL, seconds INTEGER, total REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, cat TEXT,
        size TEXT DEFAULT '', price REAL, active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT)''')
    defaults = {'club':'BILYARD CLUB','login':'','admin':''}
    for k,v in defaults.items():
        c.execute('INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)', (k,v))
    for i in range(1, 6):
        c.execute('INSERT OR IGNORE INTO tables(id,typ,no,price) VALUES(?,?,?,?)', (i,'BILLIARD',i,30000))
    for i in range(1, 4):
        c.execute('INSERT OR IGNORE INTO tables(id,typ,no,price) VALUES(?,?,?,?)', (100+i,'TENNIS',i,20000))
    products = [
      ('Suv','Ichimlik','0.5L',3000),('Suv','Ichimlik','1L',5000),('Suv','Ichimlik','1.5L',7000),('Suv','Ichimlik','2L',9000),
      ('Coca-Cola','Ichimlik','0.5L',7000),('Coca-Cola','Ichimlik','1L',11000),('Coca-Cola','Ichimlik','1.5L',15000),('Coca-Cola','Ichimlik','2L',19000),
      ('Fanta','Ichimlik','0.5L',7000),('Fanta','Ichimlik','1L',11000),('Fanta','Ichimlik','1.5L',15000),('Fanta','Ichimlik','2L',19000),
      ('Sprite','Ichimlik','0.5L',7000),('Sprite','Ichimlik','1L',11000),('Sprite','Ichimlik','1.5L',15000),('Sprite','Ichimlik','2L',19000),
      ('Pepsi','Ichimlik','0.5L',7000),('Pepsi','Ichimlik','1L',11000),('Pepsi','Ichimlik','1.5L',15000),('Pepsi','Ichimlik','2L',19000),
      ('Chips','Gazak','',10000),('Suxarik','Gazak','',8000),('Shokolad','Gazak','',10000),("Yong'oq",'Gazak','',15000),('Pullik tayoqcha','Tayoqcha','',5000)
    ]
    if c.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        c.executemany('INSERT INTO products(name,cat,size,price) VALUES(?,?,?,?)', products)
    c.commit(); return c


def money(x): return f"{x:,.0f}".replace(',', ' ') + " so'm"

def esc(s):
    return (str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;'))


def page(title, body, refresh=False):
    meta = '<meta http-equiv="refresh" content="5">' if refresh else ''
    return f'''<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{esc(title)}</title>
    <style>
    :root{{--bg:#081018;--card:#142531;--gold:#e5b83b;--blue:#1c7fb5;--green:#1c9b57;--red:#a83232;--white:#f7f7f7}}
    *{{box-sizing:border-box}} body{{margin:0;font-family:Segoe UI,Arial,sans-serif;background:linear-gradient(135deg,#050b10,#0b1820);color:var(--white)}}
    header{{position:sticky;top:0;z-index:5;background:#03070a;padding:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;box-shadow:0 2px 15px #0008}}
    header .brand{{font-size:22px;font-weight:800;color:var(--gold);margin-right:auto}} a,button{{border:0;border-radius:10px;padding:11px 15px;font-weight:800;text-decoration:none;color:white;background:#173044;cursor:pointer}} a:hover,button:hover{{filter:brightness(1.14)}}
    .wrap{{max-width:1400px;margin:0 auto;padding:22px}} h1,h2{{color:var(--gold)}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}}
    .section{{background:#071017aa;border:1px solid #24404f;border-radius:18px;padding:18px;margin-bottom:18px}} .card{{background:var(--card);border-radius:16px;padding:16px;border:1px solid #294551}}
    .card.busy{{border-color:#7b3333;background:#3d1e24}} .big{{font-size:31px;font-weight:900;font-variant-numeric:tabular-nums}} .gold{{color:var(--gold)}} .status{{font-weight:800;margin:4px 0 10px}} .muted{{opacity:.8}}
    .btnrow{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}} .green{{background:var(--green)}} .red{{background:var(--red)}} .blue{{background:var(--blue)}}
    .pill{{display:inline-block;padding:5px 9px;background:#0d3342;border-radius:999px;margin:3px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #28404b;text-align:left}} input{{background:#0b171f;color:white;border:1px solid #355461;border-radius:8px;padding:9px}}
    .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}} .stat{{background:#142531;padding:17px;border-radius:14px}} .stat b{{font-size:22px;color:var(--gold)}}
    </style></head><body><header><div class="brand">🎱 BILYARD CLUB</div>
    <a href="/">🏠 Bosh sahifa</a><a href="/menu">🥤 Menyu</a><a href="/reports">📊 Hisobot</a><a href="/settings">⚙ Sozlamalar</a></header><div class="wrap">{body}</div></body></html>'''


def home():
    c=db(); rows=c.execute('SELECT * FROM tables ORDER BY typ,no').fetchall(); c.close()
    groups={'TENNIS':[],'BILLIARD':[]}
    for r in rows: groups[r['typ']].append(r)
    def card(r):
        elapsed = max(0,int(time.time()-r['started'])) if r['active'] and r['started'] else 0
        mm,ss=divmod(elapsed,60); hh,mm=divmod(mm,60)
        total=elapsed*r['price']/3600
        return f'''<div class="card {'busy' if r['active'] else ''}"><div class="gold"><b>{esc(r['typ'])} {r['no']}</b></div>
        <div class="status">{'🔴 BAND' if r['active'] else '🟢 BO‘SH'}</div><div class="big">{hh:02d}:{mm:02d}:{ss:02d}</div>
        <div class="muted">{money(total)} • {money(r['price'])}/soat</div>
        <div class="btnrow"><a class="blue" href="/table?id={r['id']}">Kirish</a>
        <a class="{'red' if r['active'] else 'green'}" href="/toggle?id={r['id']}">{'⏹ Tugatish' if r['active'] else '▶ Band qilish'}</a>
        </div></div>'''
    body=f'<h1>{esc(setting("club") or "BILYARD CLUB")}</h1>'
    body += f'<div class="section"><h2>🎱 5 TA BILLIARD</h2><div class="grid">{"".join(card(r) for r in groups["BILLIARD"])}</div></div>'
    body += f'<div class="section"><h2>🏓 3 TA TENNIS</h2><div class="grid">{"".join(card(r) for r in groups["TENNIS"])}</div></div>'
    return page('BILYARD CLUB',body,True)


def setting(k):
    c=db(); r=c.execute('SELECT v FROM settings WHERE k=?',(k,)).fetchone(); c.close(); return r['v'] if r else ''

def table_view(tid, msg=''):
    c=db(); r=c.execute('SELECT * FROM tables WHERE id=?',(tid,)).fetchone(); c.close()
    if not r:return page('Xato','<div class="section">Stol topilmadi.</div>')
    elapsed=max(0,int(time.time()-r['started'])) if r['active'] and r['started'] else 0
    mm,ss=divmod(elapsed,60); hh,mm=divmod(mm,60)
    body=f'<div class="section"><h1>{esc(r["typ"])} {r["no"]}</h1>'
    if msg: body+=f'<div class="pill">{esc(msg)}</div>'
    body+=f'<p>{"🔴 BAND" if r["active"] else "🟢 BO‘SH"}</p><div class="big">{hh:02d}:{mm:02d}:{ss:02d}</div>'
    body+=f'<p>Stol narxi: <b class="gold">{money(r["price"])}/soat</b></p><div class="btnrow">'
    body+=f'<a class="{"red" if r["active"] else "green"}" href="/toggle?id={r["id"]}">{"⏹ Tugatish" if r["active"] else "▶ Band qilish"}</a><a class="blue" href="/menu?typ={r["typ"]}&no={r["no"]}">🥤 Mahsulot qo‘shish</a><a href="/">← Orqaga</a></div></div>'
    return page(f'{r["typ"]} {r["no"]}',body,True)


def menu(typ='', no=''):
    c=db(); ps=c.execute('SELECT * FROM products WHERE active=1 ORDER BY cat,name,size').fetchall(); c.close()
    cards=''
    for p in ps:
        q=''
        if typ and no: q=f'<a class="blue" href="/sale?typ={esc(typ)}&no={no}&pid={p["id"]}">➕ Olish</a>'
        cards += f'<div class="card"><b class="gold">{esc(p["name"])} {esc(p["size"] or "")}</b><div class="muted">{esc(p["cat"])}</div><h3>{money(p["price"])}</h3>{q}</div>'
    title='🥤 MENYU' + (f' — {esc(typ)} {esc(no)}' if typ and no else '')
    return page(title,f'<h1>{title}</h1><div class="grid">{cards}</div><p><a href="/">← Bosh sahifa</a></p>')


def reports():
    now=time.time(); today=datetime.now(); start=today.replace(hour=0,minute=0,second=0,microsecond=0).timestamp(); week=(today-timedelta(days=today.weekday())).replace(hour=0,minute=0,second=0,microsecond=0).timestamp(); month=today.replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
    c=db()
    def calc(s):
        a=c.execute('SELECT COALESCE(SUM(total),0) x,COUNT(*) n FROM sessions WHERE ended>=?',(s,)).fetchone()
        b=c.execute('SELECT COALESCE(SUM(price*qty),0) x,COUNT(*) n FROM sales WHERE created>=?',(s,)).fetchone()
        return a['x']+b['x'], a['n'], b['x'], b['n']
    d,w,m=calc(start),calc(week),calc(month); c.close()
    def block(name,v): return f'<div class="stat"><div>{name}</div><b>{money(v[0])}</b><div class="muted">{v[1]} o‘yin • {v[3]} savdo</div></div>'
    body='<h1>📊 HISOBOT</h1><div class="stats">'+block('BUGUN',d)+block('HAFTA',w)+block('OYLIK',m)+'</div>'
    body+='<div class="section"><h2>Jami</h2><p>Bugungi savdo: <b class="gold">'+money(d[0])+'</b></p><p>Haftalik savdo: <b class="gold">'+money(w[0])+'</b></p><p>Oylik savdo: <b class="gold">'+money(m[0])+'</b></p></div>'
    return page('Hisobot',body)


def settings_page(msg=''):
    c=db(); trs=c.execute('SELECT * FROM tables ORDER BY typ,no').fetchall(); ps=c.execute('SELECT * FROM products WHERE active=1 ORDER BY cat,name,size').fetchall(); c.close()
    rows=''.join(f'<tr><td>{r["typ"]} {r["no"]}</td><td><form method="post" action="/save_price"><input type="hidden" name="id" value="{r["id"]}"><input name="price" value="{r["price"]}" size="10"><button class="blue">Saqlash</button></form></td></tr>' for r in trs)
    prows=''.join(f'<tr><td>{esc(p["name"])} {esc(p["size"] or "")}</td><td>{money(p["price"])}</td></tr>' for p in ps)
    body='<h1>⚙ SOZLAMALAR</h1>'+(f'<div class="pill">{esc(msg)}</div>' if msg else '')
    body+=f'''<div class="section"><h2>Stol narxlari</h2><table><tr><th>Stol</th><th>Narx / soat</th></tr>{rows}</table></div>
    <div class="section"><h2>Klub nomi</h2><form method="post" action="/save_club"><input name="club" value="{esc(setting('club'))}" size="30"><button class="blue">Saqlash</button></form></div>
    <div class="section"><h2>Mahsulotlar</h2><table><tr><th>Nomi</th><th>Narxi</th></tr>{prows}</table></div>'''
    return page('Sozlamalar',body)


class H(BaseHTTPRequestHandler):
    def send(self,html,status=200):
        data=html.encode('utf-8'); self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def form(self):
        n=int(self.headers.get('Content-Length','0') or 0); return {k:v[0] for k,v in parse_qs(self.rfile.read(n).decode()).items()}
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query)
        try:
            if u.path=='/': self.send(home())
            elif u.path=='/table': self.send(table_view(int(q.get('id',['0'])[0])))
            elif u.path=='/toggle':
                tid=int(q.get('id',['0'])[0]); c=db(); r=c.execute('SELECT * FROM tables WHERE id=?',(tid,)).fetchone()
                if r:
                    if r['active']:
                        end=time.time(); secs=max(0,int(end-r['started'])); total=secs*r['price']/3600
                        c.execute('INSERT INTO sessions(typ,tab_no,started,ended,seconds,total) VALUES(?,?,?,?,?,?)',(r['typ'],r['no'],r['started'],end,secs,total)); c.execute('UPDATE tables SET active=0,started=NULL WHERE id=?',(tid,)); c.commit(); c.close(); self.send(home())
                    else:
                        c.execute('UPDATE tables SET active=1,started=? WHERE id=?',(time.time(),tid)); c.commit(); c.close(); self.send(home())
                else:self.send('Not found',404)
            elif u.path=='/menu': self.send(menu(q.get('typ',[''])[0],q.get('no',[''])[0]))
            elif u.path=='/sale':
                typ=q.get('typ',[''])[0]; no=int(q.get('no',['0'])[0]); pid=int(q.get('pid',['0'])[0]); c=db(); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone();
                if p: c.execute('INSERT INTO sales(typ,tab_no,name,price,qty,created) VALUES(?,?,?,?,?,?)',(typ,no,p['name'],p['price'],1,time.time())); c.commit()
                c.close(); self.send(menu(typ,str(no)))
            elif u.path=='/reports': self.send(reports())
            elif u.path=='/settings': self.send(settings_page())
            else:self.send('404',404)
        except Exception as e:self.send(page('Xato',f'<div class="section"><h2>Xato</h2><pre>{esc(e)}</pre></div>'),500)
    def do_POST(self):
        if self.path=='/save_price':
            f=self.form(); c=db(); c.execute('UPDATE tables SET price=? WHERE id=?',(float(f['price']),int(f['id']))); c.commit(); c.close(); self.send(settings_page('Narx saqlandi.'))
        elif self.path=='/save_club':
            f=self.form(); c=db(); c.execute('INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)',('club',f.get('club','BILYARD CLUB'))); c.commit(); c.close(); self.send(settings_page('Klub nomi saqlandi.'))
        else:self.send('Not found',404)
    def log_message(self,*args): pass

if __name__=='__main__':
    db().close(); print(f'BILYARD CLUB server: http://0.0.0.0:{PORT}')
    ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
