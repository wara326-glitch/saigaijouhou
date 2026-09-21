from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json, re

JST = timezone(timedelta(hours=9))
UA = {'User-Agent':'FukushimaDisasterDashboard/1.0'}
FEEDS = {
    'extra':'https://www.data.jma.go.jp/developer/xml/feed/extra.xml',
    'eqvol':'https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'
}

def get(url):
    with urlopen(Request(url, headers=UA), timeout=20) as r:
        return r.read()

def local(tag): return tag.split('}')[-1]

def text_all(root):
    return ' '.join((e.text or '').strip() for e in root.iter() if (e.text or '').strip())

def feed_entries(url):
    root=ET.fromstring(get(url)); out=[]
    for e in root.iter():
        if local(e.tag)!='entry': continue
        d={}
        for c in e:
            n=local(c.tag)
            if n in ('title','updated','id') and c.text: d[n]=c.text.strip()
            if n=='link' and c.attrib.get('href'): d['link']=c.attrib['href']
        if d.get('link'): out.append(d)
    return out

def sev_from_name(name):
    if '特別警報' in name: return 4
    if '危険警報' in name: return 3
    if '警報' in name: return 3
    if '注意報' in name: return 1
    return 0

def parse_warning():
    best={'level':0,'label':'平常','items':[],'headline':'','published':None,'source':'気象庁防災情報XML'}
    entries=feed_entries(FEEDS['extra'])
    candidates=[e for e in entries if any(k in e.get('title','') for k in ['警報','注意報','気象警報'])]
    for ent in candidates[:120]:
        try: root=ET.fromstring(get(ent['link']))
        except Exception: continue
        whole=text_all(root)
        if '福島県' not in whole and '福島地方気象台' not in whole: continue
        items=[]
        # Collect active warning-like names. Statuses containing 解除 are excluded.
        for node in root.iter():
            if local(node.tag) not in ('Warning','Item'): continue
            t=text_all(node)
            if '解除' in t: continue
            if not any(k in t for k in ['注意報','警報']): continue
            names=[]
            for x in node.iter():
                if local(x.tag) in ('Name','Kind') and x.text:
                    s=x.text.strip()
                    if ('注意報' in s or '警報' in s) and s not in names: names.append(s)
            items.extend(names)
        # fallback: extract warning names from full text
        if not items:
            for m in re.findall(r'[^、。\s]{0,10}(?:特別警報|危険警報|警報|注意報)', whole):
                if '解除' not in m and m not in items: items.append(m)
        items=list(dict.fromkeys(items))[:12]
        level=max([sev_from_name(x) for x in items] or [0])
        headline=''
        for x in root.iter():
            if local(x.tag) in ('Headline','HeadlineText') and x.text:
                headline=x.text.strip(); break
        best={'level':level,'label':('特別警報' if level>=4 else '警報' if level>=3 else '注意報' if level>=1 else '平常'),
              'items':items,'headline':headline,'published':ent.get('updated'),'source':'気象庁防災情報XML'}
        return best
    return best

def intensity_num(s):
    table={'1':1,'2':2,'3':3,'4':4,'5-':5,'5弱':5,'5+':5.5,'5強':5.5,'6-':6,'6弱':6,'6+':6.5,'6強':6.5,'7':7}
    return table.get(str(s).strip(),0)

def parse_eq():
    entries=feed_entries(FEEDS['eqvol'])
    for ent in entries[:100]:
        if not any(k in ent.get('title','') for k in ['震源・震度','震度速報','地震情報']): continue
        try: root=ET.fromstring(get(ent['link']))
        except Exception: continue
        whole=text_all(root)
        if '福島県' not in whole: continue
        max_i=0; vals=[]
        for x in root.iter():
            if local(x.tag) in ('MaxInt','Int') and x.text:
                n=intensity_num(x.text); max_i=max(max_i,n)
                if n: vals.append(x.text.strip())
        mag=None; hypo=''
        for x in root.iter():
            if local(x.tag)=='Magnitude' and x.text and mag is None: mag=x.text.strip()
            if local(x.tag)=='Name' and x.text and not hypo and any(k in x.text for k in ['県','沖','地方','海道','湾','海']): hypo=x.text.strip()
        level=3 if max_i>=5 else 2 if max_i>=4 else 1 if max_i>=3 else 0
        return {'level':level,'label':f'最大震度 {max(vals,key=intensity_num) if vals else "不明"}',
                'magnitude':mag,'hypocenter':hypo,'published':ent.get('updated'),'title':ent.get('title',''),'source':'気象庁防災情報XML'}
    return {'level':0,'label':'直近の対象情報なし','magnitude':None,'hypocenter':'','published':None,'source':'気象庁防災情報XML'}

def main():
    now=datetime.now(JST).isoformat(timespec='seconds')
    out={'updated':now,'weather':parse_warning(),'earthquake':parse_eq()}
    Path('data').mkdir(exist_ok=True)
    Path('data/jma.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
