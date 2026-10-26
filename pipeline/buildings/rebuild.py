"""Written by AI on 2026-10-26 by model GPT-6.1 Sol. Rebuild owned outputs."""
import argparse,subprocess,sys
from pathlib import Path
DIRECTORY=Path(__file__).resolve().parent

def run(name,*arguments):
 subprocess.run([sys.executable,str(DIRECTORY/name),*arguments],check=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--area',choices=['core','m0','m1'],default='m1');parser.add_argument('--workers',type=int,default=8);args=parser.parse_args()
 run('transform-check.py')
 run('objects.py','--area',args.area,'--workers',str(args.workers))
 run('build.py','--area',args.area,'--workers',str(args.workers))
 if args.area=='m1':run('bag.py','--audit-scene')
 tiles={'core':['x90250_y436000'],'m0':['x90250_y436000','x91500_y435500'],'m1':['x93000_y436000','x91750_y437500']}[args.area]
 for tile in tiles:run('debug_render.py','--tile',tile)
 if args.area=='core':run('alignment.py')
 run('finalize.py')
if __name__=='__main__':main()
