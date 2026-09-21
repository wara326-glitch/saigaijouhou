from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json, re
JST=timezone(timedelta(hours=9)); UA={'User-Agent':'FukushimaDisasterDashboard/2.0'}
FEEDS={'extra':'https://www.data.jma.go.jp/developer/xml/feed/extra.xml','eqvol':'https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'}
def get(url):
 with urlopen(Request(url,headers=UA),timeout=20) as r:return r.read()
def local(t):return t.split('}')[-1]
def text_all(root):return ' '.join((e.text or '').strip() for e in root.iter() if (e.text or '').strip())
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
def sev(s):
 if '特別警報' in s or '緊急安全確保' in s or '大津波警報' in s or '氾濫発生' in s:return 4
 if '警報' in s or '避難指示' in s or '氾濫危険' in s:return 3
 if '警戒' in s or '氾濫警戒' in s:return 2
 if '注意報' in s or '高齢者等避難' in s or '氾濫注意' in s:return 1
 return 0
def find_latest(feed,keywords,need_fukushima=True):
 for ent in feed_entries(feed)[:180]:
  if not any(k in ent.get('title','') for k in keywords):continue
  try:root=ET.fromstring(get(ent['link']))
  except:continue
  whole=text_all(root)
  if need_fukushima and '福島' not in whole:continue
  return ent,root,whole
 return None,None,''
def parse_warning():
 ent,root,whole=find_latest(FEEDS['extra'],['警報','注意報','気象警報'])
 if not root:return {'level':0,'label':'平常','items':[]}
 items=[]
 for x in root.iter():
  if local(x.tag) in ('Name','Kind') and x.text and ('警報' in x.text or '注意報' in x.text):items.append(x.text.strip())
 items=list(dict.fromkeys(items))[:12];level=max([sev(x) for x in items] or [0])
 return {'level':level,'label':'特別警報' if level>=4 else '警報' if level>=3 else '注意報' if level else '平常','items':items,'published':ent.get('updated')}
def intensity_num(s):
 return {'1':1,'2':2,'3':3,'4':4,'5-':5,'5弱':5,'5+':5.5,'5強':5.5,'6-':6,'6弱':6,'6+':6.5,'6強':6.5,'7':7}.get(str(s).strip(),0)
def parse_eq():
 ent,root,whole=find_latest(FEEDS['eqvol'],['震源・震度','震度速報','地震情報'])
 if not root:return {'level':0,'label':'直近の対象情報なし'}
 vals=[];mag=None;hypo=''
 for x in root.iter():
  if local(x.tag) in ('MaxInt','Int') and x.text and intensity_num(x.text):vals.append(x.text.strip())
  if local(x.tag)=='Magnitude' and x.text and mag is None:mag=x.text.strip()
  if local(x.tag)=='Name' and x.text and not hypo and any(k in x.text for k in ['県','沖','地方','海道','湾','海']):hypo=x.text.strip()
 mi=max([intensity_num(v) for v in vals] or [0]);level=3 if mi>=5 else 2 if mi>=4 else 1 if mi>=3 else 0
 return {'level':level,'label':'最大震度 '+(max(vals,key=intensity_num) if vals else '不明'),'magnitude':mag,'hypocenter':hypo,'published':ent.get('updated')}
def parse_generic(feed,keywords,labels):
 ent,root,whole=find_latest(feed,keywords)
 if not root:return {'level':0,'label':'発表なし','detail':'現在、福島県対象の情報は確認されていません'}
 hits=[x for x in labels if x in whole];level=max([sev(x) for x in hits] or [1]);detail='・'.join(hits[:8]) or ent.get('title','情報あり')
 return {'level':level,'label':hits[0] if hits else '情報あり','detail':detail,'published':ent.get('updated')}
def main():
 now=datetime.now(JST).isoformat(timespec='seconds')
 out={'updated':now,'weather':parse_warning(),'earthquake':parse_eq(),
 'tsunami':parse_generic(FEEDS['eqvol'],['津波警報','津波情報'],['大津波警報','津波警報','津波注意報','津波予報']),
 'landslide':parse_generic(FEEDS['extra'],['土砂災害','大雨'],['土砂災害警戒情報','土砂災害警報','土砂災害注意報','大雨特別警報','大雨警報']),
 'flood':parse_generic(FEEDS['extra'],['指定河川洪水','氾濫'],['氾濫発生情報','氾濫危険情報','氾濫警戒情報','氾濫注意情報']),
 'evacuation':{'level':0,'label':'県ポータル連携','detail':'避難指示・開設避難所は福島県防災ポータルで確認','url':'https://www.bousai.pref.fukushima.lg.jp/'},
 'road':{'level':0,'label':'公式情報','detail':'県道・国道・高速道路の通行規制','url':'https://www.pref.fukushima.lg.jp/sec/41035c/dourokisei.html'},
 'power':{'level':0,'label':'停電情報','detail':'東北電力ネットワークの福島県停電情報','url':'https://nw.tohoku-epco.co.jp/teideninfo/'},
 'nuclear':{'level':0,'label':'リアルタイム監視','detail':'県内モニタリングポスト・空間線量率','url':'https://fukushima-radioactivity.jp/pc/monitoringPostList'}}
 Path('data').mkdir(exist_ok=True);Path('data/jma.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
