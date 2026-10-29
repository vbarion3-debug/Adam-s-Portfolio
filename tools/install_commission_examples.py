"""One-time migration of local v0.13.1 Commission; preserve shell, nav fixes and X link."""
import re
from prepare_work import ROOT, write_text
from prepare_commission import START, END, load_items, render, check_alignment


def main():
    page = ROOT / 'commission.html'
    style = ROOT / 'css/commission.css'
    model = ROOT / 'tools/commission-items.json'
    original = page.read_text(encoding='utf-8')
    css = style.read_text(encoding='utf-8')
    # Never reset a model already present in the local project.
    chosen = model if model.exists() else ROOT / 'tools/commission-items.example.json'
    items = load_items(chosen)
    updated = original
    if START in updated or END in updated:
        check_alignment(updated, items)
    else:
        pattern = r'<section class="commission-prices"[^>]*>.*?</section>'
        prices = re.findall(pattern, updated, re.S)
        if len(prices) != 1: raise ValueError('Expected one Prices section; no changes made.')
        copies = re.findall(r'<div class="commission-price-copy">(.*?)</div>', prices[0], re.S)
        if len(copies) != 3: raise ValueError('Expected three v0.13.1 price copies; no changes made.')
        header = prices[0].split('<ul class="commission-price-list">')[0]
        simple = header + '<ul class="commission-price-list">\n' + '\n'.join('<li>'+copy+'</li>' for copy in copies) + '\n</ul>\n</section>'
        section = '\n    <section class="commission-examples" aria-labelledby="examples-title">\n<h2 id="examples-title">Examples</h2>\n' + render(items) + '\n</section>'
        updated = re.sub(pattern, lambda _: simple + section, updated, count=1, flags=re.S)
    if 'commission-art-' in updated or 'data-slot=' in updated:
        raise ValueError('Legacy slot markup remains; no changes made.')
    # Remove only the exact legacy CSS block; preserve appended local changes.
    if 'commission-art-' in css:
        legacy = (ROOT / 'tools/commission-legacy.css').read_text(encoding='utf-8')
        if legacy not in css: raise ValueError('Legacy Commission CSS differs; merge/remove slot rules manually before installing.')
        css = css.replace(legacy, '')
    if '.commission-examples {' not in css:
        css += '\n.commission-examples { margin-top: 2rem; }\n'
    if not re.search(r'<dialog\b[^>]*class="lightbox"', updated):
        donor = (ROOT / 'animation.html').read_text(encoding='utf-8')
        dialogs = re.findall(r'<dialog\b[^>]*class="lightbox".*?</dialog>', donor, re.S)
        if len(dialogs) != 1: raise ValueError('Expected the existing shared dialog in animation.html.')
        updated = updated.replace('</body>', dialogs[0]+'\n</body>',1)
    if 'src="js/main.js"' not in updated:
        updated = updated.replace('</body>', '<script src="js/main.js" defer></script>\n</body>',1)
    check_alignment(updated, items)
    # Build/validate everything above before writing any user files.
    if not model.exists(): write_text(model, chosen.read_text(encoding='utf-8'))
    for path, before, after in [(page, original, updated), (style, style.read_text(encoding='utf-8'), css)]:
        if before != after:
            backup = path.with_name(path.name+'.before-examples-v0.14.bak')
            if not backup.exists(): write_text(backup, before)
            write_text(path, after)
    print('Commission migrated. Local model preserved; nav/X/shell untouched. Examples uses the existing dialog/main.js.')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError) as error: raise SystemExit(str(error))
