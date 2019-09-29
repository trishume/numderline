# Based on https://github.com/powerline/fontpatcher/blob/develop/scripts/powerline-fontpatcher
# Used under the MIT license

import argparse
import sys
import re
import os.path

from itertools import chain

try:
    import fontforge
    import psMat
except ImportError:
    sys.stderr.write('The required FontForge modules could not be loaded.\n\n')
    sys.stderr.write('You need FontForge with Python bindings for this script to work.\n')
    sys.exit(1)


def get_argparser(ArgumentParser=argparse.ArgumentParser):
    parser = ArgumentParser(
        description=('Font patcher for Numderline. '
                     'Requires FontForge with Python bindings. '
                     'Stores the patched font as a new, renamed font file by default.')
    )
    parser.add_argument('target_fonts', help='font files to patch', metavar='font',
                        nargs='+', type=argparse.FileType('rb'))
    parser.add_argument('--no-rename',
                        help='don\'t add " with Numderline" to the font name',
                        default=True, action='store_false', dest='rename_font')
    return parser


FONT_NAME_RE = re.compile(r'^([^-]*)(?:(-.*))?$')
NUM_DIGIT_COPIES = 6

def gen_feature(digit_names):
    feature = """
languagesystem DFLT dflt;
languagesystem latn dflt;
languagesystem cyrl dflt;
languagesystem grek dflt;
languagesystem kana dflt;
@digits=[{digit_names}];
{nds}
{allnds}
{allnds_nxt}

feature calt {{
  sub @digits by @nd0;
}} calt;
"""[1:]

    nds = [' '.join(['nd{}.{}'.format(i,j) for j in range(10)]) for i in range(NUM_DIGIT_COPIES)]
    nds = ['@nd{}=[{}];'.format(i,nds[i]) for i in range(NUM_DIGIT_COPIES)]
    nds = "\n".join(nds)

    allnds = ['nd{}.{}'.format(i,j) for i in range(NUM_DIGIT_COPIES) for j in range(10)]
    allnds = "@allnds=[{}];".format(' '.join(allnds))

    allnds_nxt = ['nd{}.{}'.format((i+1)%NUM_DIGIT_COPIES,j) for i in range(NUM_DIGIT_COPIES) for j in range(10)]
    allnds_nxt = "@allnds_nxt=[{}];".format(' '.join(allnds_nxt))

    feature = feature.format(digit_names=' '.join(digit_names), nds=nds, allnds=allnds, allnds_nxt=allnds_nxt)
    with open('mods.fea', 'w') as f:
        f.write(feature)


def patch_one_font(font, rename_font=True):
    font_em_original = font.em
    font.em = 2048
    font.encoding = 'ISO10646'

    # Rename font
    if rename_font:
        font.familyname += ' with Numderline'
        font.fullname += ' with Numderline'
        fontname, style = FONT_NAME_RE.match(font.fontname).groups()
        font.fontname = fontname + 'WithNumderline'
        if style is not None:
            font.fontname += style
        font.appendSFNTName(
            'English (US)', 'Preferred Family', font.familyname)
        font.appendSFNTName(
            'English (US)', 'Compatible Full', font.fullname)

    target_bb = [0, 0, 0, 0]
    font_width = 0

    # Find the biggest char width and height in the Latin-1 extended range and
    # the box drawing range This isn't ideal, but it works fairly well - some
    # fonts may need tuning after patching.
    for cp in chain(range(0x00, 0x17f), range(0x2500, 0x2600)):
        try:
            bbox = font[cp].boundingBox()
        except TypeError:
            continue
        if not font_width:
            font_width = font[cp].width
        if bbox[0] < target_bb[0]:
            target_bb[0] = bbox[0]
        if bbox[1] < target_bb[1]:
            target_bb[1] = bbox[1]
        if bbox[2] > target_bb[2]:
            target_bb[2] = bbox[2]
        if bbox[3] > target_bb[3]:
            target_bb[3] = bbox[3]

    font.em = font_em_original

    digit_names = [font[code].glyphname for code in range(ord('0'),ord('9')+1)]
    test_names = [font[code].glyphname for code in range(ord('A'),ord('J')+1)]
    print(digit_names)

    # 0xE900 starts an area spanning until 0xF000 that as far as I can tell nothing
    # popular uses. I checked the Apple glyph browser and Nerd Font.
    # Uses an array because of python closure capture semantics
    encoding_alloc = [0xE900]
    def make_copy(loc, to_name):
        encoding = encoding_alloc[0]
        font.selection.select(loc)
        font.copy()
        font.selection.select(encoding)
        font.paste()
        font[encoding].glyphname = to_name
        encoding_alloc[0] += 1

    for copy_i in range(0,NUM_DIGIT_COPIES):
        for digit_i in range(0,10):
            make_copy(test_names[copy_i], 'nd{}.{}'.format(copy_i,digit_i))

    gen_feature(digit_names)
    font.mergeFeature('mods.fea')

    # Generate patched font
    # extension = os.path.splitext(font.path)[1]
    # if extension.lower() not in ['.ttf', '.otf']:
    #     # Default to OpenType if input is not TrueType/OpenType
    #     extension = '.otf'
    extension = '.otf'
    font.generate('out/{0}{1}'.format(font.fullname, extension))


def patch_fonts(target_files, rename_font=True):
    for target_file in target_files:
        target_font = fontforge.open(target_file.name)
        try:
            patch_one_font(target_font, rename_font)
        finally:
            target_font.close()
    return 0


def main(argv):
    args = get_argparser().parse_args(argv)
    return patch_fonts(args.target_fonts, args.rename_font)


raise SystemExit(main(sys.argv[1:]))
