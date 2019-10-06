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
    # from fontTools.misc.py23 import *
    from fontTools.ttLib import TTFont
    from fontTools.feaLib.builder import addOpenTypeFeatures, Builder
except ImportError:
    sys.stderr.write('The required FontForge and fonttools modules could not be loaded.\n\n')
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
    parser.add_argument('--no-underline',
                        help='don\'t add underlines',
                        default=True, action='store_false', dest='add_underlines')
    parser.add_argument('--add-commas',
                        help='add commas',
                        default=False, action='store_true')
    parser.add_argument('--shift-amount', help='amount to shift digits to group them together, try 100', type=int, default=0)
    parser.add_argument('--squish', help='horizontal scale to apply to the digits to maybe make them more readable when shifted', type=float, default=1.0)
    parser.add_argument('--squish-all',
                        help='squish all numbers, including decimals and ones less than 4 digits, use with --squish flag',
                        default=False, action='store_true')
    parser.add_argument('--spaceless-commas',
                        help='manipulate commas to not change the spacing, for monospace fonts, use with --add-commas',
                        default=False, action='store_true')
    return parser


FONT_NAME_RE = re.compile(r'^([^-]*)(?:(-.*))?$')
NUM_DIGIT_COPIES = 7

def gen_feature(digit_names, underscore_name, dot_name):
    feature = """
languagesystem DFLT dflt;
languagesystem latn dflt;
languagesystem cyrl dflt;
languagesystem grek dflt;
languagesystem kana dflt;
@digits=[{digit_names}];
{nds}

feature calt {{
    ignore sub {dot_name} @digits';
    sub @digits @digits' by @digits;

    sub @digits' @digits @digits @digits by @nd0;
    sub @nd0 @digits' by @nd0;

    reversesub @nd0' @nd0 by @nd1;
    reversesub @nd0' @nd1 by @nd2;
    reversesub @nd0' @nd2 by @nd3;
    reversesub @nd0' @nd3 by @nd4;
    reversesub @nd0' @nd4 by @nd5;
    reversesub @nd0' @nd5 by @nd6;
    reversesub @nd0' @nd6 by @nd1;
}} calt;
"""[1:]

    nds = [' '.join(['nd{}.{}'.format(i,j) for j in range(10)]) for i in range(NUM_DIGIT_COPIES)]
    nds = ['@nd{}=[{}];'.format(i,nds[i]) for i in range(NUM_DIGIT_COPIES)]
    nds = "\n".join(nds)
    feature = feature.format(digit_names=' '.join(digit_names),
        nds=nds, underscore_name=underscore_name, dot_name=dot_name)
    with open('mods.fea', 'w') as f:
        f.write(feature)

def shift_layer(layer, shift):
    layer = layer.dup()
    mat = psMat.translate(shift, 0)
    layer.transform(mat)
    return layer

def squish_layer(layer, squish):
    layer = layer.dup()
    mat = psMat.scale(squish, 1.0)
    layer.transform(mat)
    return layer

def add_comma_to(glyph, comma_glyph, spaceless):
    comma_layer = comma_glyph.layers[1].dup()
    x_shift = glyph.width
    y_shift = 0
    if spaceless:
        mat = psMat.scale(0.8, 0.8)
        comma_layer.transform(mat)
        x_shift -= comma_glyph.width / 2
        # y_shift = -200
    mat = psMat.translate(x_shift, y_shift)
    comma_layer.transform(mat)
    glyph.layers[1] += comma_layer
    if not spaceless:
        glyph.width += comma_glyph.width


def patch_one_font(font, rename_font, add_underlines, shift_amount, squish, squish_all, add_commas, spaceless_commas):
    font.encoding = 'ISO10646'

    mod_name = 'N'
    if add_commas:
        if spaceless_commas:
            mod_name += 'onoCommas'
        else:
            mod_name += 'ommas'
    if add_underlines:
        mod_name += 'umderline'
    if shift_amount != 0:
        mod_name += 'Shift{}'.format(shift_amount)
    if squish != 1.0:
        squish_s = '{}'.format(squish)
        mod_name += 'Squish{}'.format(squish_s.replace('.','p'))
        if squish_all:
            mod_name += 'All'

    # Rename font
    if rename_font:
        font.familyname += ' with '+mod_name
        font.fullname += ' with '+mod_name
        fontname, style = FONT_NAME_RE.match(font.fontname).groups()
        font.fontname = fontname + 'With' + mod_name
        if style is not None:
            font.fontname += style
        font.appendSFNTName(
            'English (US)', 'Preferred Family', font.familyname)
        font.appendSFNTName(
            'English (US)', 'Compatible Full', font.fullname)

    digit_names = [font[code].glyphname for code in range(ord('0'),ord('9')+1)]
    test_names = [font[code].glyphname for code in range(ord('A'),ord('J')+1)]
    underscore_name = font[ord('_')].glyphname
    dot_name = font[ord('.')].glyphname
    print(digit_names)

    underscore_layer = font[underscore_name].layers[1]

    # 0xE900 starts an area spanning until 0xF000 that as far as I can tell nothing
    # popular uses. I checked the Apple glyph browser and Nerd Font.
    # Uses an array because of python closure capture semantics
    encoding_alloc = [0xE900]
    def make_copy(loc, to_name, add_underscore, add_comma, shift, squish):
        encoding = encoding_alloc[0]
        font.selection.select(loc)
        font.copy()
        font.selection.select(encoding)
        font.paste()
        glyph = font[encoding]
        glyph.glyphname = to_name
        if squish != 1.0:
            glyph.layers[1] = squish_layer(glyph.layers[1], squish)
        if shift != 0:
            glyph.layers[1] = shift_layer(glyph.layers[1], shift)
        if add_underscore:
            glyph.layers[1] += underscore_layer
        if add_comma:
            add_comma_to(glyph, font[ord(',')], spaceless_commas)
        encoding_alloc[0] += 1

    for copy_i in range(0,NUM_DIGIT_COPIES):
        for digit_i in range(0,10):
            shift = 0
            if copy_i % 3 == 0:
                shift = -shift_amount
            elif copy_i % 3 == 2:
                shift = shift_amount
            add_underscore = add_underlines and (copy_i >= 3 and copy_i < 6)
            add_comma = add_commas and (copy_i == 3 or copy_i == 6)
            make_copy(digit_names[digit_i], 'nd{}.{}'.format(copy_i,digit_i), add_underscore, add_comma, shift, squish)

    if squish_all and squish != 1.0:
        for digit in digit_names:
            glyph = font[digit]
            glyph.layers[1] = squish_layer(glyph.layers[1], squish)

    gen_feature(digit_names, underscore_name, dot_name)

    font.generate('out/tmp.ttf')
    ft_font = TTFont('out/tmp.ttf')
    addOpenTypeFeatures(ft_font, 'mods.fea', tables=['GSUB'])
    ft_font.save('out/{0}.ttf'.format(font.fullname))


def patch_fonts(target_files, *args):
    for target_file in target_files:
        target_font = fontforge.open(target_file.name)
        try:
            patch_one_font(target_font, *args)
        finally:
            target_font.close()
    return 0


def main(argv):
    args = get_argparser().parse_args(argv)
    return patch_fonts(args.target_fonts, args.rename_font, args.add_underlines, args.shift_amount, args.squish, args.squish_all, args.add_commas, args.spaceless_commas)


raise SystemExit(main(sys.argv[1:]))
