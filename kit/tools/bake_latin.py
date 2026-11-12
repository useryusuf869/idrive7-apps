#!/usr/bin/env python3
"""Rebuild the German glyph atlas (umlauts, sharp s) from the Ubuntu font (Pillow required).

python3 kit/tools/bake_latin.py [path/to/Ubuntu.ttf]
The generated atlas is committed; normal builds need no Pillow or font download.

The atlas holds the label charset plus every character the German catalog uses, at the
same size, width and weight as the Russian atlas. A glyph the given font file lacks
(arrows and marks in a Latin-only subset) is copied from the committed Russian atlas,
which was baked from the full Ubuntu font.
"""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zlib

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def crop(atlas, image, code):
    x, y, w, h, ox, oy, adv = atlas['glyphs'][code]
    return (image.crop((x, y, x + w, y + h)) if w and h else None), ox, oy, adv


def decode(atlas):
    return Image.frombytes('L', (atlas['atlasW'], atlas['atlasH']), zlib.decompress(base64.b64decode(atlas['alpha'])))


def main():
    font = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf')
    if not font.is_file():
        raise SystemExit('Ubuntu font not found; pass the path to Ubuntu.ttf')
    spec = importlib.util.spec_from_file_location('bake_fonts', HERE / 'bake_fonts.py')
    baker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baker)
    baker.FONTDIR = str(font.parent)
    words = json.loads((ROOT / 'kit/runtime/locales/de.json').read_text(encoding='utf-8'))
    chars = ''.join(sorted(set(baker.TEXT + 'ÄÖÜäöüßéèàØ' + ''.join(words.values()))))
    from fontTools.ttLib import TTFont
    cmap = TTFont(str(font)).getBestCmap()
    own = ''.join(c for c in chars if ord(c) in cmap)
    variable = (85, 500) if '[' in font.name or 'wdth' in font.name else None
    baked = baker.bake(font.name, variable, 48, own)
    baked['glyphs'] = {str(k): v for k, v in baked['glyphs'].items()}
    baked_image = decode(baked)
    base = json.loads((ROOT / 'kit/localization/fonts/cyrillic-ru.json').read_text(encoding='utf-8'))['sizes'][0]
    base_image = decode(base)
    glyphs, borrowed = [], []
    for c in chars:
        code = str(ord(c))
        if code in baked['glyphs']:
            glyphs.append((code,) + crop(baked, baked_image, code))
        elif code in base['glyphs']:
            glyphs.append((code,) + crop(base, base_image, code))
            borrowed.append(c)
        else:
            raise SystemExit('No glyph for %r in the font or the Russian atlas' % c)
    width, x, y, row, place = 1024, 0, 0, 0, {}
    for code, image, ox, oy, adv in glyphs:
        if image is None:
            place[code] = (0, 0)
            continue
        if x + image.width > width:
            x, y, row = 0, y + row + 1, 0
        place[code] = (x, y)
        x += image.width + 1
        row = max(row, image.height)
    height = y + row + 1
    if height > 2048:
        raise SystemExit('Latin atlas exceeds its reserved GPU budget')
    sheet = Image.new('L', (width, height), 0)
    table = {}
    for code, image, ox, oy, adv in glyphs:
        px, py = place[code]
        if image is not None:
            sheet.paste(image, (px, py))
        table[code] = [px, py, image.width if image else 0, image.height if image else 0, ox, oy, adv]
    atlas = {'size': 48, 'ascent': base['ascent'], 'descent': base['descent'], 'atlasW': width, 'atlasH': height,
             'alpha': base64.b64encode(zlib.compress(sheet.tobytes(), 9)).decode('ascii'), 'glyphs': table}
    cache_key = hashlib.sha256(json.dumps(atlas, separators=(',', ':')).encode()).hexdigest()[:16]
    data = {'family': 'latin', 'source': 'Ubuntu (Ubuntu Font Licence 1.0)', 'cacheKey': cache_key, 'sizes': [atlas]}
    out = ROOT / 'kit/localization/fonts/latin-de.json'
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('latin:', len(chars), 'glyphs (%d from the Russian atlas: %s),' % (len(borrowed), ''.join(borrowed)),
          width, 'x', height, 'pixels,', out.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
