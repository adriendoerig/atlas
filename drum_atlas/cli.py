from .paths import database_path, cache_dir
import argparse
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='Drum Atlas: scan local sample folders and audition similarity maps')
    p.add_argument('--db',default=str(database_path()),help='Persistent SQLite index')
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('scan',help='Recursively scan one or more roots')
    s.add_argument('roots',nargs='+')
    s.add_argument('--baseline-only',action='store_true',help='Skip CLAP; use rough heuristic percussion score')
    s.add_argument('--one-shot',type=float,default=.35)
    s.add_argument('--drum',type=float,default=.5)
    s.add_argument('--model-cache',default=str(cache_dir() / 'models'))
    s=sub.add_parser('serve',help='Open the local audition browser')
    s.add_argument('--port',type=int,default=8765)
    s=sub.add_parser('demo',help='Create a small synthetic test library')
    s.add_argument('folder')
    args=p.parse_args()
    if args.command=='scan':
        if not 0<=args.one_shot<=1 or not 0<=args.drum<=1: p.error('Thresholds must be between 0 and 1')
        from .index import scan
        print(json.dumps(scan(args.db,args.roots,clap=not args.baseline_only,one_shot=args.one_shot,
                              drum=args.drum,cache_dir=args.model_cache),indent=2))
    elif args.command=='serve':
        import uvicorn
        from .server import create_app
        print(f'Open http://127.0.0.1:{args.port}')
        uvicorn.run(create_app(args.db),host='127.0.0.1',port=args.port)
    elif args.command=='demo':
        from .demo import generate
        generate(Path(args.folder))
if __name__=='__main__': main()
