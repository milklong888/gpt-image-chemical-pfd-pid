"""Check portable text/source packaging and local Markdown file links before release."""
from pathlib import Path
import json,re,sys
from urllib.parse import unquote,urlsplit
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','__pycache__','.pytest_cache','.venv','data','outputs','node_modules'}
FORBIDDEN={'.dwg','.bak','.shx','.dll','.exe','.zip','.pdf','.bkp','.apw','.sldprt','.sldasm','.exb'}
PATTERNS={
    'private_home_path':re.compile(r'[A-Za-z]:[/\\]Users[/\\](?!Public\b|example\b)[^/\\\s]+',re.I),
    'wechat_private_path':re.compile('wx'+'id_[a-z0-9_]{8,}',re.I),
    'github_token':re.compile('gh'+'[opusr]_[A-Za-z0-9]{30,}'),
    'private_key':re.compile('-----BEGIN '+r'(?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
def scan():
    errors=[];count=0
    for p in ROOT.rglob('*'):
        rel=p.relative_to(ROOT)
        if not p.is_file() or any(part in SKIP for part in rel.parts):continue
        count+=1
        if p.suffix.lower() in FORBIDDEN:errors.append([rel.as_posix(),'excluded_binary_or_source_format'])
        if p.stat().st_size>2*1024*1024:errors.append([rel.as_posix(),'oversized_payload'])
        try:text=p.read_text('utf-8-sig')
        except UnicodeDecodeError:
            errors.append([rel.as_posix(),'unreviewed_binary']);continue
        for name,pattern in PATTERNS.items():
            if pattern.search(text):errors.append([rel.as_posix(),name])
        if p.suffix=='.md':
            for match in re.finditer(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)',text):
                target=match[1].strip().strip('<>')
                if urlsplit(target).scheme or target.startswith('#') or '<' in target:continue
                path=unquote(target.split('#')[0])
                if path and not (p.parent/path).exists():errors.append([rel.as_posix(),'broken_link',target])
    for p in ROOT.glob('skills/*/SKILL.md'):
        import yaml
        text=p.read_text('utf8');front=re.match(r'^---\n(.*?)\n---',text,re.S)
        data=yaml.safe_load(front[1]) if front else {}
        if data.get('name')!=p.parent.name or not data.get('description'):errors.append([str(p.relative_to(ROOT)),'skill_frontmatter'])
    return {'pass':not errors,'files_checked':count,'errors':errors,'scope':'Text/package/link check; not a complete copyright or security audit.'}
if __name__=='__main__':
    result=scan();print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['pass'] else 1)
