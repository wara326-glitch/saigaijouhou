from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
JST=timezone(timedelta(hours=9)); UA={'User-Agent':'JapanDisasterDashboard/7.0'}
PREFS={'北海道':'01','青森県':'02','岩手県':'03','宮城県':'04','秋田県':'05','山形県':'06','福島県':'07','茨城県':'08','栃木県':'09','群馬県':'10','埼玉県':'11','千葉県':'12','東京都':'13','神奈川県':'14','新潟県':'15','富山県':'16','石川県':'17','福井県':'18','山梨県':'19','長野県':'20','岐阜県':'21','静岡県':'22','愛知県':'23','三重県':'24','滋賀県':'25','京都府':'26','大阪府':'27','兵庫県':'28','奈良県':'29','和歌山県':'30','鳥取県':'31','島根県':'32','岡山県':'33','広島県':'34','山口県':'35','徳島県':'36','香川県':'37','愛媛県':'38','高知県':'39','福岡県':'40','佐賀県':'41','長崎県':'42','熊本県':'43','大分県':'44','宮崎県':'45','鹿児島県':'46','沖縄県':'47'}
REGIONS={'県北':['07201','07210','07213','07214','07301','07303','07308','07322'],'県中':['07203','07207','07211','07342','07344','07501','07502','07503','07504','07505','07521','07522'],'県南':['07205','07461','07464','07465','07466','07481','07482','07483','07484'],'会津':['07202','07208','07402','07405','07407','07408','07421','07422','07423','07444','07445','07446','07447'],'南会津':['07362','07364','07367','07368'],'相双':['07209','07212','07541','07542','07543','07544','07545','07546','07547','07548','07561','07564'],'いわき':['07204']}
FEEDS={'extra':'https://www.data.jma.go.jp/developer/xml/feed/extra.xml','eqvol':'https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'}
def get(url):
 with urlopen(Request(url,headers=UA),timeout=20) as r:return r.read()
def get_json(url):return json.loads(get(url).decode('utf-8'))
def local(t):return t.split('}')[-1]
def text_all(root):return ' '.join((x.text or '').strip() for x in root.iter() if (x.text or '').strip())
def dt(s):
 try:return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(JST)
 except:return None
def fresh(ent,hours):
 t=dt(ent.get('updated',''));return bool(t and datetime.now(JST)-t <= timedelta(hours=hours))
def sev_name(n):
 if '特別警報' in n or '大津波警報' in n or '氾濫発生' in n:return 4
 if '津波警報' in n or '氾濫危険' in n:return 3
 if '土砂災害警戒情報' in n or '氾濫警戒' in n:return 2
 if '警報' in n and '注意報' not in n:return 3
 if '注意報' in n or '氾濫注意' in n:return 1
 return 0
def label(lv):return '緊急' if lv>=4 else '警報' if lv>=3 else '警戒' if lv>=2 else '注意' if lv>=1 else '平常'
def active_kinds(area):
 out=[]
 for w in area.get('warnings',[]):
  status=str(w.get('status',''))
  if status in ('解除','発表警報・注意報はなし','解除済み'):continue
  n=w.get('name') or w.get('kind') or ''
  if n and ('警報' in n or '注意報' in n):out.append(n)
 return list(dict.fromkeys(out))
def parse_warning(code):
 try:data=get_json(f'https://www.jma.go.jp/bosai/warning/data/warning/{code}0000.json')
 except:return {'level':0,'items':[]},{}
 areas=[]
 for at in data.get('areaTypes',[]):
  c=at.get('areas',[])
  if c and any(str(a.get('code','')).startswith(code) and len(str(a.get('code','')))==5 for a in c):areas=c
 municipal={}
 for a in areas:
  c=str(a.get('code','')); kinds=active_kinds(a)
  if c and kinds:municipal[c]={'name':a.get('name',''),'items':kinds,'level':max([sev_name(x) for x in kinds] or [0])}
 items=list(dict.fromkeys(sum((x['items'] for x in municipal.values()),[])));lv=max([x['level'] for x in municipal.values()] or [0])
 return {'level':lv,'items':items[:12]},municipal
def feed_entries(url):
 root=ET.fromstring(get(url));out=[]
 for e in root.iter():
  if local(e.tag)!='entry':continue
  d={}
  for c in e:
   n=local(c.tag)
   if n in ('title','updated') and c.text:d[n]=c.text.strip()
   if n=='link' and c.attrib.get('href'):d['link']=c.attrib['href']
  if d.get('link'):out.append(d)
 return out
def apply(prefs,pnames,lv,kind,detail,published):
 for p in pnames:
  if p not in prefs:continue
  old=prefs[p]['hazards'].get(kind)
  if not old or lv>=old.get('level',0):prefs[p]['hazards'][kind]={'level':lv,'detail':detail,'published':published}
  if lv>prefs[p]['level']:prefs[p]['level']=lv;prefs[p]['dominant']=kind;prefs[p]['detail']=detail
def parse_xml_hazards(prefs):
 for feed,limit in ((FEEDS['eqvol'],100),(FEEDS['extra'],180)):
  try:entries=feed_entries(feed)[:limit]
  except:continue
  for ent in entries:
   title=ent.get('title','')
   if not any(k in title for k in ['震源・震度','震度速報','津波警報','津波情報','土砂災害警戒情報','指定河川洪水予報','氾濫']):continue
   # Do not treat old feed history as an active alert. Earthquakes are situational for 6h; active warning bulletins max 24h.
   if ('震度' in title and not fresh(ent,6)) or ('震度' not in title and not fresh(ent,24)):continue
   try:root=ET.fromstring(get(ent['link']));txt=text_all(root)
   except:continue
   pnames=[p for p in PREFS if p in txt]
   if not pnames:continue
   if '津波' in title:
    if '津波警報・注意報を解除' in txt or '解除しました' in txt:continue
    if '大津波警報' in txt:lv,detail=4,'大津波警報'
    elif '津波警報' in txt:lv,detail=3,'津波警報'
    elif '津波注意報' in txt:lv,detail=1,'津波注意報'
    else:continue
    apply(prefs,pnames,lv,'津波',detail,ent.get('updated'))
   elif '土砂災害警戒情報' in title:
    if '全警戒解除' in txt or ('解除' in txt and '警戒対象地域' not in txt):continue
    apply(prefs,pnames,2,'土砂','土砂災害警戒情報',ent.get('updated'))
   elif '洪水' in title or '氾濫' in title:
    hits=[x for x in ['氾濫発生情報','氾濫危険情報','氾濫警戒情報','氾濫注意情報'] if x in txt]
    if hits:apply(prefs,pnames,max(sev_name(x) for x in hits),'河川',hits[0],ent.get('updated'))
   elif '震度' in title:
    vals=[]
    for x in root.iter():
     if local(x.tag) in ('MaxInt','Int') and x.text:vals.append(x.text.strip())
    score={'1':1,'2':2,'3':3,'4':4,'5-':5,'5弱':5,'5+':5.5,'5強':5.5,'6-':6,'6弱':6,'6+':6.5,'6強':6.5,'7':7}
    if vals:
     m=max(vals,key=lambda x:score.get(x,0));v=score.get(m,0);lv=4 if v>=6 else 3 if v>=5 else 2 if v>=4 else 1 if v>=3 else 0
     if lv:apply(prefs,pnames,lv,'地震','震度'+m,ent.get('updated'))
def main():
 prefs={p:{'level':0,'label':'平常','dominant':'平常','detail':'','hazards':{}} for p in PREFS};fmun={}
 for p,c in PREFS.items():
  w,mun=parse_warning(c);prefs[p]['hazards']['気象']=w
  if w['level']>0:prefs[p]['level']=w['level'];prefs[p]['dominant']='気象';prefs[p]['detail']='・'.join(w['items'][:3])
  if p=='福島県':fmun=mun
 parse_xml_hazards(prefs)
 for p in prefs:prefs[p]['hazards']['避難情報']={'level':None,'detail':'自動取得未接続'};prefs[p]['label']=label(prefs[p]['level'])
 regions={}
 for rn,codes in REGIONS.items():
  hits=[];affected=[];lv=0
  for c in codes:
   d=fmun.get(c)
   if d:lv=max(lv,d['level']);hits+=d['items'];affected.append(d['name'])
  regions[rn]={'level':lv,'label':label(lv),'items':list(dict.fromkeys(hits))[:8],'affected':list(dict.fromkeys(affected))}
 now=datetime.now(JST).isoformat(timespec='seconds')
 Path('data').mkdir(exist_ok=True);Path('data/jma.json').write_text(json.dumps({'updated':now,'prefectures':prefs,'regions':regions,'sources':['JMA current warning JSON','JMA disaster XML feeds'],'note':'Current JMA warnings are read from current warning JSON. XML feed history is freshness-limited so old bulletins do not remain falsely active. Earthquake display is a recent-event status, not an ongoing warning.'},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
