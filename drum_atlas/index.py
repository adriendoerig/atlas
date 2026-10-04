import hashlib
import json
import os
from pathlib import Path
import numpy as np
from .analysis import analyze, ANALYSIS_VERSION, ClapEmbedder
from .store import connect

EXTENSIONS={'.wav','.wave','.aif','.aiff','.flac','.ogg','.mp3'}
def scan(db_path,roots,*,clap=True,one_shot=.35,drum=.5,cache_dir=None,progress=print):
    roots=[Path(p).expanduser().resolve() for p in roots]
    if not roots or any(not p.is_dir() for p in roots):
        raise ValueError('Provide existing root directories; no index changes were made.')
    db=connect(db_path)
    found=set()
    # Fail enumeration before deactivating anything if a directory is unreadable.
    def onerror(e): raise e
    for root in roots:
        for folder, dirs, files in os.walk(root,followlinks=False,onerror=onerror):
            dirs.sort()
            for name in sorted(files):
                p=Path(folder,name)
                if p.suffix.lower() in EXTENSIONS and not p.is_symlink(): found.add(str(p.resolve()))
    stats={'found':len(found),'analyzed':0,'cached':0,'embedded':0,'errors':0}
    engine=None
    for i,path in enumerate(sorted(found)):
        progress(f'[{i+1}/{len(found)}] {Path(path).name}',flush=True)
        st=Path(path).stat()
        old=db.execute('SELECT * FROM samples WHERE path=?',(path,)).fetchone()
        fresh=old and old['mtime_ns']==st.st_mtime_ns and old['size']==st.st_size and old['analysis_version']==ANALYSIS_VERSION and not old['error']
        if not fresh:
            try:
                a=analyze(path)
                db.execute('''INSERT INTO samples(path,mtime_ns,size,analysis_version,duration,sample_rate,channels,
                    one_shot,drum_heuristic,features,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET mtime_ns=excluded.mtime_ns,size=excluded.size,
                    analysis_version=excluded.analysis_version,duration=excluded.duration,sample_rate=excluded.sample_rate,
                    channels=excluded.channels,one_shot=excluded.one_shot,drum_heuristic=excluded.drum_heuristic,
                    features=excluded.features,detail=excluded.detail,clap=NULL,clap_version=NULL,drum_clap=NULL,
                    clap_detail=NULL,error=NULL,active=1''',
                    (path,st.st_mtime_ns,st.st_size,ANALYSIS_VERSION,a['duration'],a['sample_rate'],a['channels'],
                     a['one_shot'],a['drum_heuristic'],json.dumps(a['features']),json.dumps(a['detail'])))
                stats['analyzed']+=1
            except Exception as e:
                db.execute('''INSERT INTO samples(path,mtime_ns,size,error) VALUES(?,?,?,?)
                  ON CONFLICT(path) DO UPDATE SET error=excluded.error,clap=NULL,features=NULL,active=1''',
                  (path,st.st_mtime_ns,st.st_size,str(e)))
                stats['errors']+=1
                db.commit()
                continue
        else:
            stats['cached']+=1
            db.execute('UPDATE samples SET active=1 WHERE path=?',(path,))
        db.commit()
        row=db.execute('SELECT * FROM samples WHERE path=?',(path,)).fetchone()
        if clap and row['one_shot']>=one_shot and (row['clap'] is None or row['clap_version']!=ClapEmbedder.VERSION):
            # Model failures are fatal and explicit: never silently substitute baseline for CLAP.
            if engine is None:
                progress('Loading CLAP (first run downloads model weights)...',flush=True)
                engine=ClapEmbedder(cache_dir)
            v,score,detail=engine.embed(path)
            db.execute('UPDATE samples SET clap=?,clap_version=?,drum_clap=?,clap_detail=? WHERE id=?',
                       (v.astype('<f4').tobytes(),ClapEmbedder.VERSION,score,json.dumps(detail),row['id']))
            stats['embedded']+=1
            db.commit()
    for row in db.execute('SELECT id,path FROM samples WHERE active=1').fetchall():
        p=Path(row['path'])
        if any(p.is_relative_to(root) for root in roots) and str(p) not in found:
            db.execute('UPDATE samples SET active=0 WHERE id=?',(row['id'],))
    db.commit()
    build_spaces(db,clap=clap,one_shot=one_shot,drum=drum)
    stats['accepted']=db.execute("SELECT count(*) FROM points WHERE space='timbral'").fetchone()[0]
    db.close()
    return stats

def build_spaces(db,*,clap,one_shot,drum):
    rows=db.execute('SELECT * FROM samples WHERE active=1 AND error IS NULL AND features IS NOT NULL ORDER BY id').fetchall()
    selected=[r for r in rows if r['one_shot']>=one_shot and
              (r['drum_clap'] if clap and r['clap_version']==ClapEmbedder.VERSION and r['drum_clap'] is not None
               else (-1 if clap else r['drum_heuristic']))>=drum]
    modes=['timbral','clap'] if clap else ['timbral']
    if not clap:
        db.execute("DELETE FROM points WHERE space='clap'")
        db.execute("DELETE FROM spaces WHERE name='clap'")
    for mode in modes:
        sig=hashlib.sha256(json.dumps([mode,one_shot,drum,clap,'projection-1',
           [(r['id'],r['mtime_ns'],r['size'],r['analysis_version'],r['clap_version']) for r in selected]]).encode()).hexdigest()
        old=db.execute('SELECT signature FROM spaces WHERE name=?',(mode,)).fetchone()
        if old and old[0]==sig: continue
        matrix=np.array([json.loads(r['features']) if mode=='timbral' else np.frombuffer(r['clap'],dtype='<f4') for r in selected],dtype=np.float32)
        metric='euclidean' if mode=='timbral' else 'cosine'
        detail={'one_shot_threshold':one_shot,'drum_threshold':drum,'drum_method':'CLAP prompts' if clap else 'rough envelope heuristic',
                'dimensions':32 if mode=='timbral' else 512,'projection':'UMAP' if len(selected)>=4 else 'small-set layout'}
        if len(matrix):
            if mode=='timbral':
                mean=matrix.mean(axis=0); scale=matrix.std(axis=0); scale[scale<1e-6]=1
                matrix=(matrix-mean)/scale
                detail.update(mean=mean.tolist(),scale=scale.tolist())
            if len(matrix)>=4:
                import umap
                coords=umap.UMAP(n_neighbors=min(15,len(matrix)-1),metric=metric,init='random',
                                 random_state=42,min_dist=.12,n_jobs=1).fit_transform(matrix)
            else:
                coords=np.column_stack([np.arange(len(matrix)),np.zeros(len(matrix))])
        else: coords=[]
        with db:
            db.execute('DELETE FROM points WHERE space=?',(mode,))
            for r,v,xy in zip(selected,matrix,coords):
                db.execute('INSERT INTO points VALUES(?,?,?,?,?)',(mode,r['id'],float(xy[0]),float(xy[1]),v.astype('<f4').tobytes()))
            db.execute('INSERT OR REPLACE INTO spaces VALUES(?,?,?,?)',(mode,sig,metric,json.dumps(detail)))
    db.commit()

def neighbors(db,space,sample_id,k=8):
    rows=db.execute('SELECT sample_id,vector FROM points WHERE space=? ORDER BY sample_id',(space,)).fetchall()
    ids=[r['sample_id'] for r in rows]
    if sample_id not in ids: raise KeyError(sample_id)
    x=np.array([np.frombuffer(r['vector'],dtype='<f4') for r in rows])
    q=x[ids.index(sample_id)]
    if space=='clap': distances=1-(x@q)/(np.linalg.norm(x,axis=1)*np.linalg.norm(q)+1e-12)
    else: distances=np.linalg.norm(x-q,axis=1)
    return [{'id':ids[i],'distance':float(max(0,distances[i]))} for i in np.argsort(distances) if ids[i]!=sample_id][:k]
