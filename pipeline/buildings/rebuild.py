"""Written by AI on 2026-10-25 by model GPT-6.1 Sol. Rebuild owned outputs."""
import subprocess,sys
from pathlib import Path
DIRECTORY=Path(__file__).resolve().parent

def run(name,*arguments):
 subprocess.run([sys.executable,str(DIRECTORY/name),*arguments],check=True)

def main():
 run('transform-check.py')
 for area in ['core','m0']:
  run('objects.py','--area',area)
  run('build.py','--area',area)
  if area=='core':
   run('debug_render.py','--tile','x90250_y436000')
   run('alignment.py')
  else:run('debug_render.py','--tile','x91500_y435500')
 run('finalize.py')
if __name__=='__main__':main()
