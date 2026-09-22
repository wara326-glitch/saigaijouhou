from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

JST = timezone(timedelta(hours=9))
UA = {'User-Agent': 'JapanDisasterDashboard/12.0'}
FEED = 'https://www.data.jma.go.jp/developer/xml/feed/extra.xml'
REGIONS = {
 '県北':['07201','07210','07213','07214','07301','07303','07308','07322'],
 '県中':['07203','07207','07211','07342','07344','07501','07502','07503','07504','07505','07521','07522'],
 '県南':['07205','07461','07464','07465','07466','07481','07482','07483','07484'],
 '会津':['07202','07208','07402','07405','07407','07408','07421','07422','07423','07444','07445','07446','07447'],
 '南会津':['07362','07364','07367','07368'],
 '相双':['07209','07212','07541','07542','07543','07544','07545','07546','07547','07548','07561','07564'],
 'いわき':['07204']
}
MUNICIPAL = {c for v in REGIONS.values() for c in v}

def get(url):
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        return r.read()

def local(tag): return tag.split('}')[-1]
def text(el, name):
    for x in el.iter():
        if local(x.tag) == name and x.text:
            return x.text.strip()
    return ''
def active(status):
    s = status or ''
    return not any(x in s for x in ('解除','なし','発表警報・注意報はなし'))
def severity(name):
    s = (name or '').replace(' ','')
    if '特別警報' in s: return 4
    if '危険警報' in s: return 3
    if '警報' in s and '注意報' not in s: return 2
    if '注意報' in s: return 1
    return 0
def label(v): return '災害切迫' if v>=4 else '危険' if v>=3 else '警戒' if v>=2 else '注意' if v>=1 else '発表なし'
def base_code(code):
    c = ''.join(x for x in str(code) if x.isdigit())
    return c[:5] if len(c) >= 5 else c

def entries():
    root = ET.fromstring(get(FEED)); out=[]
    for e in root.iter():
        if local(e.tag) != 'entry': continue
        d={'title':'','updated':'','link':''}
        for x in e:
            n=local(x.tag)
            if n in ('title','updated') and x.text: d[n]=x.text.strip()
            if n=='link' and x.attrib.get('href'): d['link']=x.attrib['href']
        if d['link']: out.append(d)
    return out

def records(root):
    out=[]; seen=set()
    # R06 products use Item containers. Keep Warning as a compatibility fallback.
    for item in root.iter():
        if local(item.tag) not in ('Item','Warning'): continue
        area = next((x for x in item.iter() if local(x.tag)=='Area'), None)
        if area is None: continue
        code = text(area,'Code'); name=text(area,'Name')
        bc=base_code(code)
        if bc not in MUNICIPAL: continue
        kinds=[]
        for k in item.iter():
            if local(k.tag)!='Kind': continue
            kn=text(k,'Name'); st=text(k,'Status')
            if kn and active(st) and any(x in kn for x in ('警報','注意報')):
                kinds.append(kn)
        key=(bc,tuple(kinds))
        if kinds and key not in seen:
            seen.add(key); out.append((bc,name,kinds))
    return out

def main():
    es=entries()
    # VPWW55-61 are the post-2026-05-28 products used by the JMA warning page.
    candidates=[e for e in es if '気象警報・注意報（Ｒ０６）' in e['title'] or '気象警報・注意報(R06)' in e['title']]
    muni={c:{'name':'','items':[],'level':0} for c in MUNICIPAL}
    used=[]; product_seen=set()
    for e in candidates:
        try: root=ET.fromstring(get(e['link']))
        except Exception: continue
        alltxt=' '.join((x.text or '') for x in root.iter())
        if '福島県' not in alltxt: continue
        product=e['title']
        if product in product_seen: continue
        product_seen.add(product); used.append({'title':product,'updated':e['updated']})
        for c,n,ks in records(root):
            if n: muni[c]['name']=n
            muni[c]['items'].extend(ks)
        if len(product_seen)>=7: break
    if not used:
        raise RuntimeError('Current Fukushima R06 warning products were not found in JMA extra feed')
    for d in muni.values():
        d['items']=list(dict.fromkeys(d['items']))
        d['level']=max([severity(x) for x in d['items']] or [0])
    path=Path('data/jma.json'); data=json.loads(path.read_text(encoding='utf-8'))
    items=list(dict.fromkeys(x for d in muni.values() for x in d['items']))
    lv=max([d['level'] for d in muni.values()] or [0])
    fp=data.setdefault('prefectures',{}).setdefault('福島県',{})
    fp.pop('data_error',None)
    fp['level']=max(lv, max([v.get('level',0) or 0 for k,v in fp.get('hazards',{}).items() if k!='気象'] or [0]))
    fp['label']=label(fp['level'])
    fp['dominant']='気象' if lv>=max([v.get('level',0) or 0 for k,v in fp.get('hazards',{}).items() if k!='気象'] or [0]) and lv else fp.get('dominant','平常')
    fp['detail']='・'.join(items[:12]) if items else '現在、発表中の気象警報・注意報はありません。'
    fp.setdefault('hazards',{})['気象']={'level':lv,'items':items,'municipality_count':sum(d['level']>0 for d in muni.values()),'source':'JMA R06 VPWW55-61','products':used}
    regions={}
    for rn,codes in REGIONS.items():
        ri=[]; affected=[]; rlv=0
        for c in codes:
            d=muni[c]; rlv=max(rlv,d['level']); ri.extend(d['items'])
            if d['level']>0: affected.append(d['name'] or c)
        regions[rn]={'level':rlv,'label':label(rlv),'items':list(dict.fromkeys(ri)),'affected':affected}
    data['regions']=regions
    data['fukushima_municipalities']=muni
    data['warning_source']='JMA warning page / R06 VPWW55-61'
    data['warning_updated']=datetime.now(JST).isoformat(timespec='seconds')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Fukushima warning overlay:', len(used), 'products, level', lv, items)

if __name__=='__main__': main()
