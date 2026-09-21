from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
JST=timezone(timedelta(hours=9)); UA={'User-Agent':'JapanDisasterDashboard/5.0'}
PREFS={'北海道':'01','青森県':'02','岩手県':'03','宮城県':'04','秋田県':'05','山形県':'06','福島県':'07','茨城県':'08','栃木県':'09','群馬県':'10','埼玉県':'11','千葉県':'12','東京都':'13','神奈川県':'14','新潟県':'15','富山県':'16','石川県':'17','福井県':'18','山梨県':'19','長野県':'20','岐阜県':'21','静岡県':'22','愛知県':'23','三重県':'24','滋賀県':'25','京都府':'26','大阪府':'27','兵庫県':'28','奈良県':'29','和歌山県':'30','鳥取県':'31','島根県':'32','岡山県':'33','広島県':'34','山口県':'35','徳島県':'36','香川県':'37','愛媛県':'38','高知県':'39','福岡県':'40','佐賀県':'41','長崎県':'42','熊本県':'43','大分県':'44','宮崎県':'45','鹿児島県':'46','沖縄県':'47'}
REGIONS={'県北':['07201','07210','07213','07214','07301','07303','07308','07322'],'県中':['07203','07207','07211','07342','07344','07501','07502','07503','07504','07505','07521','07522'],'県南':['07205','07461','07464','07465','07466','07481','07482','07483','07484'],'会津':['07202','07208','07402','07405','07407','07408','07421','07422','07423','07444','07445','07446','07447'],'南会津':['07362','07364','07367','07368'],'相双':['07209','07212','07541','07542','07543','07544','07545','07546','07547','07548','07561','07564'],'いわき':['07204']}
# JMA warning JSON: current municipality-level warnings. Codes beginning 07 are Fukushima municipalities.
def get_json(url):
 with urlopen(Request(url,headers=UA),timeout=20) as r:return json.loads(r.read().decode('utf-8'))
def sev_name(name):
 if '特別警報' in name:return 4
 if '危険警報' in name or ('警報' in name and '注意報' not in name):return 3
 if '注意報' in name:return 1
 return 0
def label(lv):return '特別警報' if lv>=4 else '警報' if lv>=3 else '注意報' if lv>=1 else '平常'
def active_kinds(area):
 out=[]
 for w in area.get('warnings',[]):
  status=str(w.get('status',''))
  if status in ('解除','発表警報・注意報はなし','解除済み'):continue
  name=w.get('name') or w.get('kind') or ''
  if name and ('警報' in name or '注意報' in name):out.append(name)
 return list(dict.fromkeys(out))
def parse_pref(pref,code):
 try:data=get_json(f'https://www.jma.go.jp/bosai/warning/data/warning/{code}0000.json')
 except:return {'level':0,'label':'取得確認','items':[]},{}
 # Latest JMA structure has areaTypes; select municipality/local-government layer when available.
 areas=[]
 for at in data.get('areaTypes',[]):
  candidate=at.get('areas',[])
  if candidate and any(str(a.get('code','')).startswith(code) and len(str(a.get('code','')))==5 for a in candidate):areas=candidate
 if not areas:
  for at in data.get('areaTypes',[]):areas.extend(at.get('areas',[]))
 municipal={}
 for a in areas:
  c=str(a.get('code','')); kinds=active_kinds(a)
  if c and kinds:municipal[c]={'name':a.get('name',''),'items':kinds,'level':max([sev_name(x) for x in kinds] or [0])}
 items=[]
 for x in municipal.values():items+=x['items']
 items=list(dict.fromkeys(items));lv=max([x['level'] for x in municipal.values()] or [0])
 return {'level':lv,'label':label(lv),'items':items[:12]},municipal
def main():
 prefs={};fmun={}
 for p,c in PREFS.items():
  prefs[p],mun=parse_pref(p,c)
  if p=='福島県':fmun=mun
 regions={}
 for rn,codes in REGIONS.items():
  hits=[];affected=[];lv=0
  for c in codes:
   d=fmun.get(c)
   if not d:continue
   lv=max(lv,d['level']);hits+=d['items'];affected.append(d['name'])
  hits=list(dict.fromkeys(hits));affected=list(dict.fromkeys(affected))
  regions[rn]={'level':lv,'label':label(lv),'items':hits[:8],'affected':affected}
 now=datetime.now(JST).isoformat(timespec='seconds')
 out={'updated':now,'prefectures':prefs,'regions':regions,'source':'JMA warning JSON municipality data'}
 Path('data').mkdir(exist_ok=True);Path('data/jma.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
