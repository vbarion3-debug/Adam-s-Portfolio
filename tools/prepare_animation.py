"""Render the static Animation gallery and local still thumbnails. No YouTube calls.
Default model: tools/animation-items.json. Create it from the example first.
"""
import argparse
import csv
import html
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from PIL import Image, ImageOps
from prepare_work import ROOT, THUMB_BUDGET, alpha_statistics, gallery_note, save_webp, thumbnail, webp_mode, write_text


def parse_youtube_url(value):
    """Extract an ID from a small host/path allowlist; never forward URL params."""
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('youtube_url must be a nonempty URL without whitespace/control characters.')
    url = value if '://' in value else 'https://' + value
    try:
        parsed = urlsplit(url)
        host = parsed.netloc.lower()
        if parsed.scheme not in ('http', 'https') or host not in ('youtu.be', 'youtube.com', 'www.youtube.com'):
            raise ValueError('youtube_url host must be youtu.be, youtube.com or www.youtube.com, without credentials/port.')
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError(f'Invalid youtube_url: {error}') from error
    if not set(query).issubset({'v', 'si', 't', 'start', 'feature'}) or any(len(values) != 1 for values in query.values()):
        raise ValueError('youtube_url contains unsupported or duplicate query parameters.')
    if host == 'youtu.be':
        if 'v' in query:
            raise ValueError('Short URLs must identify the video in the path only.')
        candidate = re.fullmatch(r'/([A-Za-z0-9_-]{11})/?', parsed.path)
        video_id = candidate.group(1) if candidate else ''
    elif parsed.path == '/watch':
        video_id = query.get('v', [''])[0]
    else:
        if 'v' in query:
            raise ValueError('Embed URLs must identify the video in the path only.')
        candidate = re.fullmatch(r'/embed/([A-Za-z0-9_-]{11})/?', parsed.path)
        video_id = candidate.group(1) if candidate else ''
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id) is None:
        raise ValueError('youtube_url must contain an exact 11-character YouTube ID in /watch?v=, /embed/ or the youtu.be path.')
    return video_id


def normalize_youtube_id(item):
    from_url = parse_youtube_url(item['youtube_url']) if 'youtube_url' in item else None
    given = item.get('youtube_id')
    if given is not None and (not isinstance(given, str) or not given):
        raise ValueError('youtube_id must be a nonempty string.')
    if from_url is not None and given is not None and from_url != given:
        raise ValueError('youtube_id and youtube_url identify different videos.')
    video_id = given if given is not None else from_url
    if video_id is None:
        raise ValueError('Each item needs youtube_id or youtube_url.')
    valid = re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id) is not None
    mock = item.get('sample') is True and re.fullmatch(r'MOCK_NOT_A_VIDEO_\d{2}', video_id) is not None
    if not valid and not mock:
        raise ValueError('Real IDs need exactly 11 allowed characters; mock IDs must be MOCK_NOT_A_VIDEO_XX with sample=true.')
    if item.get('sample') and ('Test sample' not in item['name'] or not mock):
        raise ValueError('Technical samples require a Test sample name and a deliberately invalid MOCK_NOT_A_VIDEO_XX ID.')
    return video_id


def render(items):
    lines = ['    <ul class="gallery" aria-label="Animation gallery">']
    esc = lambda v: html.escape(str(v), quote=True)
    for n, item in enumerate(items):
        lazy = ' loading="lazy"' if n >= 7 else ''
        youtube_id = item['youtube_id']
        # ID whitelist below guarantees this query needs no URL escaping.
        href = f'https://www.youtube.com/watch?v={youtube_id}'
        lines.append(f'      <li><a href="{esc(href)}" data-gallery data-id="{esc(item["id"])}" data-kind="youtube" data-youtube-id="{esc(youtube_id)}" data-name="{esc(item["name"])}"><img src="{esc(item["thumb"])}" alt="{esc(item["name"])}" width="280" height="280"{lazy} decoding="async"></a></li>')
    return '\n'.join(lines + ['    </ul>'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', type=Path, default=ROOT / 'tools/animation-items.json')
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'tools/animation-sources')
    parser.add_argument('--quality', type=int, choices=range(82, 91), default=88, metavar='82..90')
    parser.add_argument('--alpha-lossless', action='store_true', help='Restore lossless RGBA encoding for transparent posters.')
    args = parser.parse_args()
    if not args.items.is_file():
        parser.error('Model missing. Copy animation-items.example.json to animation-items.json first; existing data is never reset automatically.')
    items = json.loads(args.items.read_text(encoding='utf-8'))
    if not isinstance(items, list):
        parser.error('Model must be a JSON list.')
    known = set()
    prepared = []
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ('id', 'name', 'thumb')):
            parser.error('Each item needs nonempty id, name and thumb strings, plus youtube_id or youtube_url.')
        if item['id'] in known or item.get('kind') != 'youtube':
            parser.error('IDs must be unique; kind must be youtube.')
        known.add(item['id'])
        try:
            normalized_id = normalize_youtube_id(item)
        except ValueError as error:
            parser.error(str(error))
        item = dict(item, youtube_id=normalized_id)
        if Path(item['thumb']).is_absolute() or not (ROOT / item['thumb']).resolve().is_relative_to((ROOT / 'assets/work/animation/thumb').resolve()) or Path(item['thumb']).suffix.lower() != '.webp':
            parser.error('thumb must be a relative .webp path inside assets/work/animation/thumb.')
        # source is a local poster filename, never a remote thumbnail URL.
        filename = item.get('source', item['id'] + '.png')
        if not isinstance(filename, str) or Path(filename).name != filename or '\\' in filename:
            parser.error('source must be a simple local filename inside --input-dir.')
        path = args.input_dir / filename
        if not path.is_file():
            parser.error(f'Missing poster: {path}; no output changed.')
        with Image.open(path) as image:
            thumb, alpha = thumbnail(ImageOps.exif_transpose(image))
        prepared.append((item, thumb, alpha))
    items = [item for item, _, _ in prepared]
    page = ROOT / 'animation.html'
    source_html = page.read_text(encoding='utf-8')
    pattern = r'<!-- GALLERY START -->.*?<!-- GALLERY END -->'
    if len(re.findall(pattern, source_html, flags=re.S)) != 1:
        parser.error('animation.html needs exactly one gallery marker pair; no output changed.')
    rows = []
    for item, thumb, alpha in prepared:
        target = ROOT / item['thumb']
        before = target.stat().st_size if target.exists() else ''
        save_webp(thumb, target, alpha, args.quality, args.alpha_lossless)
        size = target.stat().st_size
        rows.append(dict(id=item['id'], mode=webp_mode(alpha, args.quality, args.alpha_lossless), before_bytes=before, after_bytes=size, target_bytes=THUMB_BUDGET, result='PASS' if size <= THUMB_BUDGET else 'OVER', **alpha_statistics(thumb)))
        print(f'{item["id"]}: {rows[-1]["mode"]}; thumb={size} B; {rows[-1]["result"]}')
    updated = re.sub(pattern, lambda _: '<!-- GALLERY START -->\n' + render(items) + '\n    <!-- GALLERY END -->', source_html, flags=re.S)
    updated = gallery_note(updated, any(x.get('sample') for x in items))
    write_text(page.with_name('animation.before-v0.12.html.bak'), source_html)
    write_text(page, updated)
    report = io.StringIO(newline='')
    writer = csv.DictWriter(report, fieldnames=['id', 'mode', 'before_bytes', 'after_bytes', 'target_bytes', 'result', 'alpha_min', 'alpha_nonopaque_pct'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    write_text(ROOT / 'tools/animation-size-report-v0.12.csv', report.getvalue())
    print(f'{len(items)} Animation entries rendered. Illustration/JSON are untouched. Model order is the gallery order; real playback still needs testing.')


if __name__ == '__main__':
    main()
