"""Update/check the four shared nav links without replacing local pages or galleries."""
import argparse
import re
from pathlib import Path
from prepare_work import write_text

ROOT = Path(__file__).resolve().parents[1]
PAGES = {'index.html': '01', 'animation.html': '01', 'commission.html': '02', 'about.html': '03', 'contact.html': '04'}
LINKS = [('index.html', 'Work', '01'), ('commission.html', 'Commission', '02'), ('about.html', 'About', '03'), ('contact.html', 'Contact', '04')]
PATTERN = r'<ul class="nav-list">.*?</ul>'


def nav(page):
    entries = []
    for href, label, number in LINKS:
        current = ''
        if label == 'Work' and page in ('index.html', 'animation.html'):
            current = ' aria-current="true"'
        elif href == page:
            current = ' aria-current="page"'
        entries.append(f'        <li><a href="{href}"{current}><span class="nav-arrow" aria-hidden="true">↳</span> {label} <span class="nav-number">{number}</span></a></li>')
    return '<ul class="nav-list">\n' + '\n'.join(entries) + '\n      </ul>'


def updated(page, text):
    if len(re.findall(PATTERN, text, flags=re.S)) != 1:
        raise ValueError(f'{page}: expected exactly one ul.nav-list; no pages changed.')
    result = re.sub(PATTERN, lambda _: nav(page), text, count=1, flags=re.S)
    number = PAGES[page]
    result = re.sub(r'(<p class="panel-label">)Index / \d+(</p>)', lambda m: m[1] + 'Index / ' + number + m[2], result)
    result = re.sub(r'(<div class="side-note"[^>]*>\s*<span>)PAGE / \d+', lambda m: m[1] + 'PAGE / ' + number, result)
    return result


def verify(texts):
    normalized = []
    for page, text in texts.items():
        match = re.findall(PATTERN, text, flags=re.S)
        if len(match) != 1 or match[0] != nav(page):
            raise ValueError(f'{page}: navigation differs from the expected shared list.')
        normalized.append(re.sub(r' aria-current="(?:page|true)"', '', match[0]))
        if len(re.findall(r'\baria-current="page"', text)) != 1:
            raise ValueError(f'{page}: expected exactly one aria-current=page.')
        if re.search(r'<div class="side-note"[^>]*>\s*<span>PAGE / (?!' + PAGES[page] + r'\b)\d+', text):
            raise ValueError(f'{page}: side-note number is outdated.')
    if len(set(normalized)) != 1:
        raise ValueError('Navigation lists are inconsistent.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only check of all five local pages.')
    args = parser.parse_args()
    try:
        texts = {page: (ROOT / page).read_text(encoding='utf-8') for page in PAGES}
        results = texts if args.check else {page: updated(page, text) for page, text in texts.items()}
        verify(results)  # Validate every page before any write.
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    if not args.check:
        for page, text in results.items():
            if text != texts[page]:
                path = ROOT / page
                write_text(path.with_name(path.name + '.before-v0.13.bak'), texts[page])
                write_text(path, text)
                print(f'Updated {page}')
    print('PASS: five shared nav lists identical except aria-current; one current page each; PAGE numbers correct.')


if __name__ == '__main__':
    main()
