"""Written by AI on 2026-10-26 by model GPT-6 Astra. Rebuild isolated overview from retained sources."""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(name, *arguments):
    subprocess.run([sys.executable, str(HERE / name), *arguments], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reextract', action='store_true', help='Redo building extraction from retained raw bytes.')
    arguments = parser.parse_args()
    run('index.py')
    building_arguments = ['--reextract'] if arguments.reextract else []
    jobs = [subprocess.Popen([sys.executable, str(HERE / 'buildings.py'), '--workers', '4', *building_arguments]),
            subprocess.Popen([sys.executable, str(HERE / 'imagery.py'), '--workers', '4'])]
    codes = [job.wait() for job in jobs]
    if any(codes):
        raise SystemExit(f'Building/imagery stages failed: {codes}; retained source caches allow resume.')
    # Classes include the delivered building/tank/bridge footprints.
    run('surfaces.py')
    run('imagery_coverage.py')
    run('finalize.py')
    run('mosaic.py')


if __name__ == '__main__':
    main()
