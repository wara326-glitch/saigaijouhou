from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
JST=timezone(timedelta(hours=9)); UA={'User-Agent':'JapanDisasterDashboard/4.0'}
FEEDS={'extra':'https://www.data.jma.go.jp/developer/xml/feed/extra.xml','eqvol':'https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'}
PREFS=['北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県','茨城県','栃木県','群馬県','埼玉県','千葉県','東京都','神奈川県','新潟県','富山県','石川県','福井県','山梨県','長野県','岐阜県','静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県','奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県','徳島県','香川県','愛媛県','高知県','福岡県','佐賀県','長崎県','熊本県','大分県','宮崎県','鹿児島県','沖縄県']
REGIONS={'県北':['福島市','二本松市','伊達市','本宮市','桑折町','国見町','川俣町','大玉村'],'県中':['郡山市','須賀川市','田村市','鏡石町','天栄村','石川町','玉川村','平田村','浅川町','古殿町','三春町','小野町'],'県南':['白河市','西郷村','泉崎村','中島村','矢吹町','棚倉町','矢祭町','塙町','鮫川村'],'会津':['会津若松市','喜多方市','北塩原村','西会津町','磐梯町','猪苗代町','会津坂下町','湯川村','柳津町','三島町','金山町','昭和村','会津美里町'],'南会津':['下郷町','檜枝岐村','只見町','南会津町'],'相双':['相馬市','南相馬市','広野町','楢葉町','富岡町','川内村','大熊町','双葉町','浪江町','葛尾村','新地町','飯舘村'],'いわき':['いわき市']}
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
 if '特別警報' in s:return 4
 if '危険警報' in s:return 3
 if '警報' in s:return 3
 if '注意報' in s:return 1
 return 0
def label(lv):return '特別警報' if lv>=4 else '警報' if lv>=3 else '注意報' if lv>=1 else '平常'
def warning_rows(root):
 rows=[]
 for node in root.iter():
  if local(node.tag) not in ('Item','Warning'):continue
  txt=text_all(node)
  if '解除' in txt:continue
  names=[];areas=[]
  for x in node.iter():
   if not x.text:continue
   s=x.text.strip();n=local(x.tag)
   if n in ('Name','Kind') and ('警報' in s or '注意報' in s):names.append(s)
   if n=='Name':areas.append(s)
  names=list(dict.fromkeys(names));areas=list(dict.fromkeys(areas))
  if names:rows.append((names,areas,txt))
 return rows
def parse_all_warnings():
 result={p:{'level':0,'label':'平常','items':[]} for p in PREFS}; frows=[]; latest=None
 for ent in feed_entries(FEEDS['extra'])[:220]:
  if not any(k in ent.get('title','') for k in ['警報','注意報']):continue
  try:root=ET.fromstring(get(ent['link']))
  except:continue
  whole=text_all(root); matched=[p for p in PREFS if p in whole]
  if not matched:continue
  rows=warning_rows(root)
  for p in matched:
   hits=[]
   for names,areas,txt in rows:
    if p in txt or any(p in a for a in areas):hits+=names
   if not hits:
    for names,areas,txt in rows:hits+=names
   hits=list(dict.fromkeys(hits));lv=max([sev(x) for x in hits] or [0])
   if lv>=result[p]['level']:result[p]={'level':lv,'label':label(lv),'items':hits[:10],'published':ent.get('updated')}
   if p=='福島県' and not frows:frows=rows;latest=ent
 # Fukushima municipalities may not repeat prefecture name in each Item; derive seven areas from latest Fukushima bulletin.
 regions={}
 for rn,cities in REGIONS.items():
  hits=[]
  for names,areas,txt in frows:
   if any(c in txt or c in areas for c in cities):hits+=names
  hits=list(dict.fromkeys(hits));lv=max([sev(x) for x in hits] or [0]);regions[rn]={'level':lv,'label':label(lv),'items':hits[:8]}
 return result,regions
def main():
 prefs,regions=parse_all_warnings();now=datetime.now(JST).isoformat(timespec='seconds')
 out={'updated':now,'prefectures':prefs,'regions':regions}
 Path('data').mkdir(exist_ok=True);Path('data/jma.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
