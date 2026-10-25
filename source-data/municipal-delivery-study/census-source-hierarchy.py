# Written by AI on 2026-10-25 by model GPT-6 Astra.
import urllib.request,json,gzip,concurrent.futures,collections,pathlib,time,posixpath
base='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/'
out=pathlib.Path(__file__).resolve().parent
def get(uri):
 b=urllib.request.urlopen(base+uri,timeout=45).read();return json.loads(gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b)
def contents(node):
 c=node.get('content',{});u=c.get('uri',c.get('url'))
 if u:yield u
 for child in node.get('children',[]):yield from contents(child)
root=get('tileset.json'); refs=list(contents(root['root']));print('root',len(refs),flush=True)
def inspect(ref):
 data=get(ref);uris=[posixpath.normpath(posixpath.join(posixpath.dirname(ref),u)) for u in contents(data['root'])]; counts=collections.Counter(u.split('/')[0] for u in uris);return {'uri':ref,'counts':dict(counts),'contents':uris}
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for row in pool.map(inspect,refs):rows.append(row);print(row['uri'],row['counts'],flush=True)
(out/'hierarchy-census.json').write_text(json.dumps({'source':base,'observedAt':'2026-10-25','subtrees':rows},indent=2))
print('TOTAL',dict(sum((collections.Counter(r['counts']) for r in rows),collections.Counter())))
