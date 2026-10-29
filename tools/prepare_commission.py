"""Static Commission examples. Reuse prepare_work's encoder, keep all HTML outside markers."""
import argparse
import csv
import html
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageOps
from prepare_work import ROOT, thumbnail, save_webp, webp_mode, alpha_statistics, write_text

START = '<!-- COMMISSION GALLERY START -->'
END = '<!-- COMMISSION GALLERY END -->'
PATTERN = re.escape(START) + r'.*?' + re.escape(END)


def load_items(path):
    items = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(items, list):
        raise ValueError('Model must be a JSON list.')
    ids = set()
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ('id', 'name', 'thumb', 'full')):
            raise ValueError('Each item needs id, name, thumb, full strings.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', item['id']) or item['id'] in ids:
            raise ValueError('IDs must be unique simple filename stems.')
        ids.add(item['id'])
        if not isinstance(item.get('sample'), bool) or (item['sample'] and 'Test sample' not in item['name']):
            raise ValueError('sample must be boolean; mocks need Test sample in their name.')
        if 'tier' in item and (not isinstance(item['tier'], str) or not item['tier']):
            raise ValueError('Optional tier must be a nonempty string.')
        for kind in ('thumb', 'full'):
            relative = Path(item[kind])
            folder = (ROOT / 'assets/work/commission' / kind).resolve()
            if relative.is_absolute() or not (ROOT / relative).resolve().is_relative_to(folder) or relative.suffix.lower() != '.webp':
                raise ValueError(f'{kind} must be a relative WebP path inside assets/work/commission/{kind}.')
    return items


def render(items):
    esc = lambda v: html.escape(str(v), quote=True)
    lines = [START]
    if any(x['sample'] for x in items):
        lines.append('<p class="gallery-note">Items labeled “Test sample” are technical samples, not Adam’s artwork.</p>')
    lines.append('<ul class="gallery commission-gallery" aria-label="Commission examples">')
    for n, item in enumerate(items):
        tier = f' data-tier="{esc(item["tier"])}"' if item.get('tier') else ''
        lazy = ' loading="lazy"' if n >= 7 else ''
        lines.append(f'<li><a href="{esc(item["full"])}" data-gallery data-id="{esc(item["id"])}" data-kind="image" data-name="{esc(item["name"])}"{tier}><img src="{esc(item["thumb"])}" alt="{esc(item["name"])}" width="280" height="280"{lazy} decoding="async"></a></li>')
    return '\n'.join(lines + ['</ul>', END])


class GalleryLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == 'a' and 'data-gallery' in data:
            self.entries.append(data)
        elif tag == 'img' and self.entries:
            self.entries[-1]['thumb'] = data.get('src')


def check_alignment(page, items):
    if page.count(START) != 1 or page.count(END) != 1 or len(re.findall(PATTERN, page, re.S)) != 1:
        raise ValueError('Expected one Commission marker pair.')
    parser = GalleryLinks()
    parser.feed(re.search(PATTERN, page, re.S).group())
    # Order is allowed to change through JSON. Membership/path/name/tier must agree.
    actual = {x.get('data-id'): x for x in parser.entries}
    if len(actual) != len(items) or len(parser.entries) != len(items):
        raise ValueError('HTML/JSON item IDs differ; reconcile them before conversion.')
    for item in items:
        entry = actual.get(item['id'], {})
        if any(entry.get(k, '') != value for k, value in [('thumb', item['thumb']), ('href', item['full']), ('data-name', item['name']), ('data-tier', item.get('tier', ''))]):
            raise ValueError('HTML/JSON name, full path or tier differs; reconcile first.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir', type=Path, default=ROOT / 'tools/commission-sources')
    ap.add_argument('--quality', type=int, choices=range(82, 91), default=88, metavar='82..90')
    ap.add_argument('--alpha-lossless', action='store_true')
    args = ap.parse_args()
    try:
        model = ROOT / 'tools/commission-items.json'
        items = load_items(model)
        page = ROOT / 'commission.html'
        original = page.read_text(encoding='utf-8')
        check_alignment(original, items)
        prepared = []
        for item in items:
            # All sources live in the user-selected directory, which may be external.
            source = args.input_dir / (item['id'] + '.png')
            with Image.open(source) as image:
                rgba = ImageOps.exif_transpose(image).convert('RGBA')
            thumb, alpha = thumbnail(rgba)
            full = rgba.copy() if alpha else rgba.convert('RGB')
            full.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            prepared.append((item, thumb, full, alpha))
    except (OSError, ValueError, KeyError) as error:
        ap.exit(1, f'{error}; no output changed.\n')
    rows = []
    for item, thumb, full, alpha in prepared:
        for kind, image, budget in [('thumb', thumb, 30000), ('full', full, 900000)]:
            target = ROOT / item[kind]
            before = target.stat().st_size if target.exists() else ''
            save_webp(image, target, alpha, args.quality, args.alpha_lossless)
            size = target.stat().st_size
            rows.append(dict(id=item['id'], kind=kind, mode=webp_mode(alpha, args.quality, args.alpha_lossless), before_bytes=before, after_bytes=size, target_bytes=budget, result='PASS' if size <= budget else 'OVER', **alpha_statistics(image)))
            print(f'{item["id"]} {kind}: {size} B; {rows[-1]["result"]}')
    updated = re.sub(PATTERN, lambda _: render(items), original, count=1, flags=re.S)
    if updated != original:
        write_text(page.with_name('commission.before-v0.14.html.bak'), original)
        write_text(page, updated)
    else:
        # Keep a before-run backup even when the generated markup is unchanged.
        backup = page.with_name('commission.before-v0.14.html.bak')
        if not backup.exists(): write_text(backup, original)
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=['id','kind','mode','before_bytes','after_bytes','target_bytes','result','alpha_min','alpha_nonopaque_pct'], lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    write_text(ROOT / 'tools/commission-size-report-v0.14.csv', output.getvalue())
    print('Commission markers updated in JSON order. JSON and all other HTML are unchanged. Review at 100%.')


if __name__ == '__main__': main()
