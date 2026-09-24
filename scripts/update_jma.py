from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

JST=timezone(timedelta(hours=9)); UA={'User-Agent':'JapanDisasterDashboard/11.0'}
PREFS={'北海道':'01','青森県':'02','岩手県':'03','宮城県':'04','秋田県':'05','山形県':'06','福島県':'07','茨城県':'08','栃木県':'09','群馬県':'10','埼玉県':'11','千葉県':'12','東京都':'13','神奈川県':'14','新潟県':'15','富山県':'16','石川県':'17','福井県':'18','山梨県':'19','長野県':'20','岐阜県':'21','静岡県':'22','愛知県':'23','三重県':'24','滋賀県':'25','京都府':'26','大阪府':'27','兵庫県':'28','奈良県':'29','和歌山県':'30','鳥取県':'31','島根県':'32','岡山県':'33','広島県':'34','山口県':'35','徳島県':'36','香川県':'37','愛媛県':'38','高知県':'39','福岡県':'40','佐賀県':'41','長崎県':'42','熊本県':'43','大分県':'44','宮崎県':'45','鹿児島県':'46','沖縄県':'47'}
REGIONS={'県北':['07201','07210','07213','07214','07301','07303','07308','07322'],'県中':['07203','07207','07211','07342','07344','07501','07502','07503','07504','07505','07521','07522'],'県南':['07205','07461','07464','07465','07466','07481','07482','07483','07484'],'会津':['07202','07208','07402','07405','07407','07408','07421','07422','07423','07444','07445','07446','07447'],'南会津':['07362','07364','07367','07368'],'相双':['07209','07212','07541','07542','07543','07544','07545','07546','07547','07548','07561','07564'],'いわき':['07204']}
FEEDS={'extra':'https://www.data.jma.go.jp/developer/xml/feed/extra.xml','eqvol':'https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'}

def get(url):
 with urlopen(Request(url,headers=UA),timeout=25) as r:return r.read()
def get_json(url):return json.loads(get(url).decode('utf-8'))
def local(t):return t.split('}')[-1]
def text_all(root):return ' '.join((x.text or '').strip() for x in root.iter() if (x.text or '').strip())
def dt(s):
 try:return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(JST)
 except:return None
def fresh(ent,hours):
 t=dt(ent.get('updated',''));return bool(t and datetime.now(JST)-t <= timedelta(hours=hours))

def sev_name(n):
 s=str(n).replace(' ','')
 if any(x in s for x in ['レベル5','特別警報','大津波警報','氾濫発生情報']):return 4
 if any(x in s for x in ['レベル4','危険警報','危険情報','土砂災害警戒情報','津波警報']):return 3
 if any(x in s for x in ['レベル3','大雨警報','土砂災害警報','高潮警報','氾濫警報','氾濫警戒情報']):return 2
 if any(x in s for x in ['レベル2','注意報','氾濫注意情報']):return 1
 if '警報' in s and '注意報' not in s:return 2
 return 0
def label(lv):return '災害切迫' if lv>=4 else '危険' if lv>=3 else '警戒' if lv>=2 else '注意' if lv>=1 else '発表なし'
def is_active_status(s):
 s=str(s or '')
 return not any(x in s for x in ['解除','発表警報・注意報はなし','なし'])

def muni5(code):
 c=str(code or '')
 # JMA warning JSON uses 7-digit secondary-area codes; first 5 digits identify municipality.
 return c[:5] if len(c)>=5 and c[:2].isdigit() else c

def active_kinds(area):
 out=[]
 for w in area.get('warnings',[]):
  if not is_active_status(w.get('status','')):continue
  n=(w.get('name') or w.get('kind') or '').strip()
  if n and any(x in n for x in ('警報','注意報','危険情報')):out.append(n)
 return list(dict.fromkeys(out))
def choose_municipal_areas(data,code):
 candidates=[]
 for at in data.get('areaTypes',[]):
  areas=at.get('areas',[]);score=sum(1 for a in areas if str(a.get('code','')).startswith(code) and len(str(a.get('code','')))>=5)
  if score:candidates.append((score,areas))
 return max(candidates,key=lambda x:x[0])[1] if candidates else []
def parse_warning(code):
 # JMA legacy JSON disappeared for some prefectures after the 2026 R06 transition.
 # Treat 404 as "legacy unavailable" and let the R06 XML feed become authoritative.
 try:data=get_json(f'https://www.jma.go.jp/bosai/warning/data/warning/{code}0000.json')
 except Exception as e:return {'level':None,'items':[],'error':str(e)},{}
 areas=choose_municipal_areas(data,code);municipal={}
 for a in areas:
  raw=str(a.get('code',''))
  c=muni5(raw)
  if not(c.startswith(code) and len(c)==5):continue
  kinds=active_kinds(a)
  old=municipal.get(c,{'name':'','items':[],'level':0})
  merged=list(dict.fromkeys(old.get('items',[])+kinds))
  municipal[c]={'name':a.get('name','') or old.get('name',''),'items':merged,'level':max([sev_name(x) for x in merged] or [0])}
 items=list(dict.fromkeys(x for d in municipal.values() for x in d['items']));lv=max([d['level'] for d in municipal.values()] or [0])
 return {'level':lv,'items':items,'municipality_count':sum(1 for d in municipal.values() if d['level']>0)},municipal

def feed_entries(url):
 root=ET.fromstring(get(url));out=[]
 for e in root.iter():
  if local(e.tag)!='entry':continue
  d={}
  for c in e:
   n=local(c.tag)
   if n in ('title','updated','id') and c.text:d[n]=c.text.strip()
   if n=='link' and c.attrib.get('href'):d['link']=c.attrib['href']
  if d.get('link'):out.append(d)
 return out

def xml_area_records(root):
 """Return [(code,name,[(kind,status)])] from JMA warning XML, tolerant of schema wrappers."""
 rec=[]
 for item in root.iter():
  if local(item.tag) not in ('Item','Warning'):continue
  area=None
  for ch in item.iter():
   if local(ch.tag)=='Area':area=ch;break
  if area is None:continue
  code=name=''
  for x in area.iter():
   if local(x.tag)=='Code' and x.text and not code:code=x.text.strip()
   elif local(x.tag)=='Name' and x.text and not name:name=x.text.strip()
  if not code:continue
  kinds=[]
  for k in item.iter():
   if local(k.tag)!='Kind':continue
   kn=st=''
   for x in k.iter():
    if local(x.tag)=='Name' and x.text and not kn:kn=x.text.strip()
    elif local(x.tag)=='Status' and x.text and not st:st=x.text.strip()
   if kn:kinds.append((kn,st))
  if kinds:rec.append((code,name,kinds))
 return rec

def parse_r06_all():
 """Build current warning/advisory state for all prefectures from JMA R06 XML.
 New 2026 products can contain split secondary areas; prefecture is determined
 from municipality/area codes when possible and text is used as a fallback."""
 try: entries=feed_entries(FEEDS['extra'])
 except Exception as e: return {},str(e),[]
 keys=('気象警報・注意報','大雨','土砂災害','高潮','暴風','暴風雪','大雪','波浪','雷','濃霧','乾燥','なだれ','着雪','着氷','融雪','低温','霜')
 candidates=[e for e in entries if any(k in e.get('title','') for k in keys) and fresh(e,48)]
 state={p:{'items':[],'level':0,'areas':set()} for p in PREFS}
 used=[];seen=set()
 for ent in candidates:
  try:
   root=ET.fromstring(get(ent['link'])); txt=text_all(root)
  except: continue
  prod=ent.get('title','')
  # Do not collapse every prefecture's bulletin solely by title.
  sig=(prod,ent.get('updated',''),ent.get('link',''))
  if sig in seen: continue
  seen.add(sig)
  rec=xml_area_records(root)
  touched=set()
  for code,name,kinds in rec:
   code=str(code)
   p=None
   if len(code)>=2:
    pc=code[:2]
    p=next((pn for pn,prefcode in PREFS.items() if prefcode==pc),None)
   if not p:
    p=next((pn for pn in PREFS if pn in txt),None)
   if not p: continue
   active=[kn for kn,st in kinds if is_active_status(st) and any(x in kn for x in ('警報','注意報','危険情報'))]
   if active:
    state[p]['items'].extend(active); state[p]['areas'].add(name or code); touched.add(p)
  if touched: used.append({'title':prod,'updated':ent.get('updated',''),'prefectures':sorted(touched)})
 for p,d in state.items():
  d['items']=list(dict.fromkeys(d['items']))
  d['areas']=sorted(d['areas'])
  d['level']=max([sev_name(x) for x in d['items']] or [0])
 return state,None,used

def parse_fukushima_r06():
 """Build Fukushima municipality status from the latest current R06 warning XML products.
    This intentionally does NOT use the stale legacy warning JSON for Fukushima."""
 try:entries=feed_entries(FEEDS['extra'])
 except Exception as e:return {},str(e),None
 # New 2026 warning family: VPWW55-61. Feed titles contain R06 and/or the hazard name.
 keys=('気象警報・注意報（Ｒ０６）','気象警報・注意報(R06)','大雨','土砂災害','高潮','暴風','暴風雪','大雪','波浪','雷','濃霧','乾燥','なだれ','着雪','着氷','融雪','低温','霜')
 candidates=[e for e in entries if any(k in e.get('title','') for k in keys) and fresh(e,48)]
 municipal={c:{'name':'','items':[],'level':0} for codes in REGIONS.values() for c in codes}
 used=[];seen_product=set()
 for ent in candidates:
  try:
   root=ET.fromstring(get(ent['link']));txt=text_all(root)
  except:continue
  if '福島県' not in txt:continue
  # One latest bulletin per title/product. Newer feed entries occur first.
  prod=ent.get('title','')
  if prod in seen_product:continue
  seen_product.add(prod);used.append({'title':prod,'updated':ent.get('updated','')})
  for code,name,kinds in xml_area_records(root):
   if code not in municipal:continue
   if name:municipal[code]['name']=name
   active=[]
   for kn,st in kinds:
    if is_active_status(st) and any(x in kn for x in ('警報','注意報','危険情報')):active.append(kn)
   # The latest product is authoritative for that hazard. Add active kinds only.
   municipal[code]['items'].extend(active)
  if len(seen_product)>=12:break
 if not used:return {},'福島県の新体系XMLを取得できませんでした',None
 for d in municipal.values():
  d['items']=list(dict.fromkeys(d['items']));d['level']=max([sev_name(x) for x in d['items']] or [0])
 return municipal,None,used

def apply(prefs,pnames,lv,kind,detail,published):
 for p in pnames:
  if p not in prefs:continue
  old=prefs[p]['hazards'].get(kind)
  if not old or old.get('level') is None or lv>=old.get('level',0):prefs[p]['hazards'][kind]={'level':lv,'detail':detail,'published':published}
  if lv>prefs[p]['level']:prefs[p]['level']=lv;prefs[p]['dominant']=kind;prefs[p]['detail']=detail

def parse_xml_hazards(prefs):
 for feed,limit in ((FEEDS['eqvol'],120),(FEEDS['extra'],240)):
  try:entries=feed_entries(feed)[:limit]
  except:continue
  for ent in entries:
   title=ent.get('title','');keys=['震源・震度','震度速報','津波警報','津波情報','指定河川洪水予報','氾濫']
   if not any(k in title for k in keys):continue
   if ('震度' in title and not fresh(ent,6)) or ('震度' not in title and not fresh(ent,24)):continue
   try:root=ET.fromstring(get(ent['link']));txt=text_all(root)
   except:continue
   pnames=[p for p in PREFS if p in txt]
   if not pnames:continue
   if '津波' in title:
    if '解除' in txt and not any(k in txt for k in ['継続','切替','発表']):continue
    hit=next((x for x in ['大津波警報','津波警報','津波注意報'] if x in txt),None)
    if hit:apply(prefs,pnames,sev_name(hit),'津波',hit,ent.get('updated'))
   elif '洪水' in title or '氾濫' in title:
    hits=[x for x in ['レベル5 氾濫特別警報','氾濫特別警報','氾濫発生情報','レベル4 氾濫危険警報','氾濫危険情報','レベル3 氾濫警報','氾濫警戒情報','レベル2 氾濫注意報','氾濫注意情報'] if x in txt]
    if hits:
     hit=max(hits,key=sev_name);apply(prefs,pnames,sev_name(hit),'河川氾濫',hit,ent.get('updated'))
   elif '震度' in title:
    vals=[x.text.strip() for x in root.iter() if local(x.tag) in ('MaxInt','Int') and x.text];score={'1':1,'2':2,'3':3,'4':4,'5-':5,'5弱':5,'5+':5.5,'5強':5.5,'6-':6,'6弱':6,'6+':6.5,'6強':6.5,'7':7}
    if vals:
     m=max(vals,key=lambda x:score.get(x,0));v=score.get(m,0);lv=4 if v>=6 else 3 if v>=5 else 2 if v>=4 else 1 if v>=3 else 0
     if lv:apply(prefs,pnames,lv,'地震','震度'+m,ent.get('updated'))

def main():
 prefs={p:{'level':0,'label':'発表なし','dominant':'平常','detail':'','hazards':{}} for p in PREFS};fmun={}
 # Prefer the current 2026 R06 XML feed nationally; legacy JSON is only a fallback.
 r06,r06err,r06used=parse_r06_all()
 for p,c in PREFS.items():
  rd=r06.get(p,{}) if not r06err else {}
  if rd:
   w={'level':rd.get('level',0),'items':rd.get('items',[]),'area_count':len(rd.get('areas',[])),'source':'JMA R06 XML'}
  else:
   w,_=parse_warning(c)
  prefs[p]['hazards']['気象']=w
  if w.get('level') is None:
   prefs[p]['data_error']=True
  elif w.get('level',0)>0:
   prefs[p]['level']=w['level'];prefs[p]['dominant']='気象';prefs[p]['detail']='・'.join(w.get('items',[])[:8])
 # Fukushima now follows the SAME path as other prefectures.
 # Start from the public prefecture warning JSON and normalize 7-digit area codes.
 fw,flegacy=parse_warning('07')
 fmun=flegacy
 fused=[]
 fp=prefs['福島県']
 if fw.get('level') is not None:
  fp.pop('data_error',None)
  fp['hazards']['気象']=fw
  fp['level']=fw.get('level',0);fp['dominant']='気象' if fp['level'] else '平常';fp['detail']='・'.join(fw.get('items',[])[:12])
 # Overlay newer R06 XML municipality detail when available; failure no longer makes Fukushima alone unavailable.
 rx,rerr,fused=parse_fukushima_r06()
 if rx and any(d.get('items') for d in rx.values()):
  for c,d in rx.items():
   if c in fmun and d.get('items'):
    merged=list(dict.fromkeys(fmun[c].get('items',[])+d.get('items',[])))
    fmun[c]['items']=merged;fmun[c]['level']=max([sev_name(x) for x in merged] or [0])
  allitems=list(dict.fromkeys(x for d in fmun.values() for x in d.get('items',[])));flv=max([d.get('level',0) for d in fmun.values()] or [0])
  fp['hazards']['気象']={'level':flv,'items':allitems,'municipality_count':sum(1 for d in fmun.values() if d.get('level',0)>0),'source':'JMA warning JSON + R06 XML'}
  fp['level']=flv;fp['dominant']='気象' if flv else '平常';fp['detail']='・'.join(allitems[:12])
 parse_xml_hazards(prefs)
 for p in prefs:
  prefs[p]['hazards']['避難情報']={'level':None,'detail':'自動取得未接続'};prefs[p]['label']='取得不能' if prefs[p].get('data_error') else label(prefs[p]['level'])
 regions={}
 for rn,codes in REGIONS.items():
  hits=[];affected=[];lv=0
  for c in codes:
   d=fmun.get(c)
   if d:
    lv=max(lv,d.get('level',0));hits+=d.get('items',[])
    if d.get('level',0)>0:affected.append(d.get('name') or c)
  regions[rn]={'level':lv,'label':label(lv),'items':list(dict.fromkeys(hits)),'affected':list(dict.fromkeys(affected))}
 now=datetime.now(JST).isoformat(timespec='seconds');Path('data').mkdir(exist_ok=True)
 Path('data/jma.json').write_text(json.dumps({'updated':now,'prefectures':prefs,'regions':regions,'municipalities':fmun,'fukushima_source_products':fused,'sources':['JMA R06 current warning XML (nationwide)','JMA disaster XML feeds'],'r06_source_products':r06used,'note':'Fukushima 59 municipalities and 7 regions are derived from current JMA 2026 R06 XML warning products; acquisition failure is never shown as safe.'},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
