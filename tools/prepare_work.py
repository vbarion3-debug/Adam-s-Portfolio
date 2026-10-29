"""Local derivative converter. Requires Pillow. Never copies PNG masters.
Default: preserve current gallery entries/metadata; update the three local artworks.
"""
import argparse
import csv
import html
import io
import json
import re
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
THUMB_BUDGET = 30000
FULL_BUDGET = 900000


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8', newline='')
    temporary.replace(path)


def gallery_note(page, has_samples):
    """Replace a note or insert it before the gallery marker if it was removed."""
    note = '<p class="gallery-note">Items labeled “Test sample” are technical samples, not Adam’s artwork.</p>' if has_samples else '<p class="gallery-note" hidden></p>'
    pattern = r'<p\b(?=[^>]*\bclass=["\'][^"\']*\bgallery-note\b)[^>]*>.*?</p>'
    if re.search(pattern, page, flags=re.S):
        return re.sub(pattern, lambda _: note, page, count=1, flags=re.S)
    return page.replace('<!-- GALLERY START -->', note + '\n    <!-- GALLERY START -->', 1)


def thumbnail(image):
    """Shared still-poster pipeline: detect actual transparency; crop to 280px."""
    rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A').getextrema()[0] < 255
    pixels = rgba if alpha else rgba.convert('RGB')
    return ImageOps.fit(pixels, (280, 280), method=Image.Resampling.LANCZOS), alpha


def render(items):
    lines = ['    <ul class="gallery" aria-label="Illustration gallery">']
    esc = lambda v: html.escape(str(v), quote=True)
    for n, item in enumerate(items):
        lazy = ' loading="lazy"' if n >= 7 else ''
        size = item.get('thumb_width', 320)
        height = item.get('thumb_height', size)
        optional = ''.join(f' data-{key}="{esc(item[key])}"' for key in ('poster', 'description') if item.get(key))
        lines.append(f'      <li><a href="{esc(item["full"])}" data-gallery data-id="{esc(item["id"])}" data-kind="{esc(item.get("kind", "image"))}" data-name="{esc(item["name"])}"{optional}><img src="{esc(item["thumb"])}" alt="{esc(item["name"])}" width="{size}" height="{height}"{lazy} decoding="async"></a></li>')
    return '\n'.join(lines + ['    </ul>'])


def alpha_statistics(image):
    """Measure actual derivative pixels, before encoding; percent uses 0..100."""
    channel = image.getchannel('A') if image.mode == 'RGBA' else image.convert('RGBA').getchannel('A')
    histogram = channel.histogram()
    total = image.width * image.height
    return dict(alpha_min=channel.getextrema()[0],
                alpha_nonopaque_pct=round(100 * sum(histogram[:255]) / total, 6))


def webp_mode(alpha, quality, alpha_lossless=False):
    if alpha:
        return 'lossless-alpha' if alpha_lossless else f'lossy-alpha-q{quality}'
    return f'lossy-q{quality}'


def save_webp(image, path, alpha, quality, alpha_lossless=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    lossless = alpha and alpha_lossless
    image.save(temporary, format='WEBP', lossless=lossless,
               quality=100 if lossless else quality, alpha_quality=100,
               method=6, exact=lossless)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--keep-samples', action='store_true', help='Add missing fixtures up to 13; existing entries always stay.')
    parser.add_argument('--quality', type=int, choices=range(82, 91), default=88, metavar='82..90')
    parser.add_argument('--alpha-lossless', action='store_true', help='Use the old lossless RGBA mode instead of lossy RGB with lossless alpha.')
    args = parser.parse_args()
    sources = [args.input_dir / f'project-{i:02}.png' for i in range(1, 4)]
    for source in sources:
        if not source.is_file():
            parser.error(f'Missing {source}; no output changed.')
    page = ROOT / 'index.html'
    source_html = page.read_text(encoding='utf-8')
    pattern = r'<!-- GALLERY START -->.*?<!-- GALLERY END -->'
    if len(re.findall(pattern, source_html, flags=re.S)) != 1:
        parser.error('Expected exactly one gallery marker pair; no output changed.')
    current = ROOT / 'tools/current-items.json'
    if not current.is_file():
        parser.error('current-items.json is missing. Restore the local gallery model before running; no output changed.')
    items = json.loads(current.read_text(encoding='utf-8'))
    if not isinstance(items, list) or len({x['id'] for x in items}) != len(items):
        parser.error('Expected a list with unique IDs; no output changed.')
    # Abort rather than silently deleting an HTML-only gallery addition.
    markup = re.search(pattern, source_html, flags=re.S).group()
    html_ids = set(re.findall(r'data-id=[\"\x27]([^\"\x27]+)', markup))
    model_ids = {x['id'] for x in items}
    link_count = len(re.findall(r'<a\b[^>]*\bdata-gallery\b', markup))
    if html_ids != model_ids or link_count != len(items):
        parser.error('HTML and current-items.json differ. Reconcile the local model first; no output changed.')
    sample_file = ROOT / 'tools/sample-items.json'
    samples = json.loads(sample_file.read_text(encoding='utf-8')) if args.keep_samples else []
    # Decode all masters before writing any derivatives.
    images = []
    for source in sources:
        with Image.open(source) as original:
            images.append(ImageOps.exif_transpose(original).convert('RGBA'))
    rows = []
    for i, (source, rgba) in enumerate(zip(sources, images), 1):
        alpha = rgba.getchannel('A').getextrema()[0] < 255
        image = rgba if alpha else rgba.convert('RGB')
        full = image.copy()
        full.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        thumb, _ = thumbnail(image)
        stem = f'illustration-{i:03}'
        existing = next((x for x in items if x['id'] == stem), None)
        # Retain existing local paths as well as titles/descriptions and order.
        t = existing['thumb'] if existing else f'assets/work/illustration/thumb/{stem}.webp'
        f = existing['full'] if existing else f'assets/work/illustration/full/{stem}.webp'
        for relative in (t, f):
            if Path(relative).is_absolute() or not (ROOT / relative).resolve().is_relative_to(ROOT.resolve()) or Path(relative).suffix.lower() != '.webp':
                parser.error('Output paths must be .webp inside the project.')
        before = [(ROOT / p).stat().st_size if (ROOT / p).exists() else None for p in (t, f)]
        save_webp(thumb, ROOT / t, alpha, args.quality, args.alpha_lossless)
        save_webp(full, ROOT / f, alpha, args.quality, args.alpha_lossless)
        sizes = [(ROOT / p).stat().st_size for p in (t, f)]
        update = dict(id=stem, category='illustration', thumb=t, full=f, width=full.width, height=full.height,
                      thumb_width=280, thumb_height=280, sample=False)
        if existing is not None:
            existing.update(update)
        else:
            items.append(dict(name=f'Illustration {i:03}', **update))
        mode = webp_mode(alpha, args.quality, args.alpha_lossless)
        for kind, old, new, budget, derivative in zip(('thumb', 'full'), before, sizes, (THUMB_BUDGET, FULL_BUDGET), (thumb, full)):
            rows.append(dict(source=source.name, kind=kind, mode=mode, before_bytes='' if old is None else old,
                             after_bytes=new, target_bytes=budget, result='PASS' if new <= budget else 'OVER', visual_100_percent='NOT VERIFIED', **alpha_statistics(derivative)))
        print(f'{source.name}: {mode}; thumb={sizes[0]} B; full={sizes[1]} B')
        if sizes[0] > THUMB_BUDGET or sizes[1] > FULL_BUDGET:
            print('OVER budget. Selected RGB quality/dimensions are unchanged; alpha_quality=100. Review at 100% before changing settings or revising SPEC.')
    if args.keep_samples:
        known = {x['id'] for x in items}
        for sample in samples[:13]:
            if sample['id'] not in known:
                items.append(sample)
                known.add(sample['id'])
    updated = re.sub(pattern, lambda _: '<!-- GALLERY START -->\n' + render(items) + '\n    <!-- GALLERY END -->', source_html, flags=re.S)
    updated = gallery_note(updated, any(x.get('sample') for x in items))
    write_text(page.with_name('index.before-v0.12.html.bak'), source_html)
    write_text(current.with_name('current-items.before-v0.12.json.bak'), current.read_text(encoding='utf-8'))
    write_text(page, updated)
    write_text(current, json.dumps(items, indent=2, ensure_ascii=False) + '\n')
    csv_text = io.StringIO(newline='')
    writer = csv.DictWriter(csv_text, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    write_text(ROOT / 'tools/size-report-v0.12.csv', csv_text.getvalue())
    print('Report: tools/size-report-v0.12.csv (bytes; decimal KB). Compare with masters at 100% before release.')
    print('Existing gallery entries/metadata preserved; masters never copied. Back up WebP files before rerunning.')


if __name__ == '__main__':
    main()
