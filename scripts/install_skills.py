"""Install the public skills to an explicit, unused destination; never overwrite."""
from pathlib import Path
import argparse,shutil
def install(destination):
    source=Path(__file__).resolve().parents[1]/'skills'
    destination=Path(destination).expanduser().resolve()
    entries=sorted(p for p in source.iterdir() if (p/'SKILL.md').is_file())
    if not entries:raise ValueError('No packaged skills found')
    for p in entries:
        if (destination/p.name).exists():raise FileExistsError(f'Refusing to overwrite: {destination/p.name}')
    destination.mkdir(parents=True,exist_ok=True)
    for p in entries:shutil.copytree(p,destination/p.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','runtime.json'))
    return [str(destination/p.name) for p in entries]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--destination',required=True)
    for path in install(parser.parse_args().destination):print(path)
