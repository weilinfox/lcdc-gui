
import ctypes
import ctypes.util
import dataclasses
import logging

from typing import Dict, List, Tuple, Union

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _FontRaw:
    family: List[str]
    familylang: List[str]
    style: List[str]
    stylelang: List[str]
    fullname: List[str]
    fullnamelang: List[str]
    postscriptname: List[str]
    slant: List[int]
    weight: List[int]
    width: List[int]
    file: List[str]
    index: List[int]


@dataclasses.dataclass
class FontInfo:
    family: List[str]
    familylang: List[str]
    style: List[str]
    stylelang: List[str]
    fullname: List[str]
    fullnamelang: List[str]
    postscriptname: List[str]
    slant: int
    weight: int
    width: int
    file: str


class FontManager:
    def __init__(self):
        self.fontconfig = ctypes.util.find_library("fontconfig")
        self.font_raw: List[_FontRaw] = []
        # { family: { style: List[FontInfo] } }
        self.fonts: Dict[str, Dict[Tuple[int, int, int], List[FontInfo]]] = {}
        self.families: List[str] = []
        self.family_styles: Dict[str, List[Tuple[int, int, int]]] = {}

        self.name_fonts: Dict[str, Dict[Tuple[int, int, int], List[FontInfo]]] = {}
        self.fullnames: List[str] = []
        self.fullname_styles: Dict[str, List[Tuple[int, int, int]]] = {}

    def init(self):
        if self.fontconfig is None:
            raise AssertionError("Font subsystem not init for fontconfig.so not found")

        fc = ctypes.CDLL(self.fontconfig)

        # types
        _FcBool = ctypes.c_int
        _FcFalse: int = 0
        _FcTrue: int = 1

        _FcChar32 = ctypes.c_uint
        _FcChar16 = ctypes.c_ushort
        _FcChar8 = ctypes.c_ubyte

        _FcPatternP = ctypes.c_void_p
        _FcObjectSetP = ctypes.c_void_p
        _FcFontSetP = ctypes.c_void_p

        _FcResult = ctypes.c_int
        _FcResultMatch = 0
        _FcResultNoMatch = 1
        _FcResultTypeMismatch = 2
        _FcResultNoId = 3
        _FcResultOutOfMemory = 4

        class _FcFontSet(ctypes.Structure):
            """
            a list of FcPatterns
            """
            _fields_ = [
                ("nfont", ctypes.c_int),  # 'nfont' holds the number of patterns in the 'fonts' array
                ("sfont", ctypes.c_int),  # 'sfont' is used to indicate the size of that array
                ("fonts", ctypes.POINTER(_FcPatternP)),  # FcPattern **fonts
            ]

        # font properties
        _FcNamelang = b"namelang"  # String  Language name to be used for the default value of familylang, stylelang and fullnamelang
        _FcFamily = b"family"  # String  Font family names
        _FcFamilyLang = b"familylang"  # String  Language corresponding to each family name
        _FcSlant = b"slant"  # Int     Italic, oblique or roman
        _FcWeight = b"weight"  # Int     Light, medium, demibold, bold or black
        _FcWidth = b"width"  # Int     Condensed, normal or expanded
        _FcStyle = b"style"  # String  Font style. Overrides weight and slant
        _FcStyleLang = b"stylelang"  # String  Language corresponding to each style name
        _FcFullname = b"fullname"  # String  Font face full name where different from family and family + style
        _FcFullnameLang = b"fullnamelang"  # String  Language corresponding to each fullname
        _FcPostscriptname = b"postscriptname"  # String  Font family name in PostScript
        _FcFile = b"file"  # String  The filename holding the font relative to the config's sysroot
        _FcIndex = b"index"  # Int     The index of the font within the file
        _FcVariable = b"variable"  # Bool    Whether font is Variable Font
        _FcDecorative = b"decorative"  # Bool    Whether the style is a decorative variant

        # functions
        fc.FcInit.restype = _FcBool
        fc.FcFontList.restype = _FcFontSetP
        fc.FcFontList.argtypes = [ctypes.c_void_p, _FcPatternP, _FcObjectSetP]
        fc.FcFontSetDestroy.argtypes = [_FcFontSetP]
        fc.FcPatternAddString.restype = _FcBool
        fc.FcPatternAddString.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_char_p]
        fc.FcPatternCreate.restype = _FcPatternP
        fc.FcPatternDestroy.argtypes = [_FcPatternP]
        fc.FcPatternGetBool.restype = _FcResult
        fc.FcPatternGetBool.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_FcBool)]
        fc.FcPatternGetInteger.restype = _FcResult
        fc.FcPatternGetInteger.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        fc.FcPatternGetString.restype = _FcResult
        fc.FcPatternGetString.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        fc.FcObjectSetBuild.restype = _FcObjectSetP
        fc.FcObjectSetDestroy.argtypes = [_FcObjectSetP]

        if fc.FcInit() != _FcTrue:
            raise RuntimeError(f"Font subsystem not init for {self.fontconfig} FcInit failed")

        # build an object set from a null-terminated list of property names
        objset = fc.FcObjectSetBuild(_FcNamelang, _FcFamily, _FcFamilyLang, _FcStyle, _FcStyleLang, _FcSlant,
                                     _FcWeight, _FcWidth, _FcFullname, _FcFullnameLang, _FcPostscriptname, _FcFile, _FcIndex, None)
        # build patterns with no properties
        pat = fc.FcPatternCreate()
        # list fonts
        cfontsets = fc.FcFontList(None, pat, objset)
        if not cfontsets:
            raise RuntimeError("Font subsystem not init for FcFontList empty pattern return NULL pointer")

        # list of FcPattern
        fontsets = ctypes.cast(cfontsets, ctypes.POINTER(_FcFontSet)).contents

        def _fc_pattern_list_strings(_pattern: _FcPatternP, _property: bytes) -> Union[List[str], None]:
            out_list: List[str] = []
            idx: int = 0

            while True:
                _s = ctypes.c_char_p()
                _result = fc.FcPatternGetString(p, _property, idx, ctypes.byref(_s))
                if _result == _FcResultMatch:
                    pass
                elif _result == _FcResultNoId:
                    break
                elif _result in [_FcResultNoMatch, _FcResultTypeMismatch]:
                    return None
                elif _result == _FcResultOutOfMemory:
                    raise RuntimeError(f"Font subsystem not init for {_property} FcPatternGetString return FcResultOutOfMemory")
                out_list.append(_s.value.decode("utf-8", errors="replace"))
                idx += 1

            return out_list

        def _fc_pattern_get_int(_pattern: _FcPatternP, _property: bytes) -> Union[List[int], None]:
            out_list: List[int] = []
            idx: int = 0

            while True:
                _i = ctypes.c_int()
                _result = fc.FcPatternGetInteger(p, _property, idx, ctypes.byref(_i))
                if _result == _FcResultMatch:
                    pass
                elif _result == _FcResultNoId:
                    break
                elif _result in [_FcResultNoMatch, _FcResultTypeMismatch]:
                    return None
                elif _result == _FcResultOutOfMemory:
                    raise RuntimeError(f"Font subsystem not init for {_property} FcPatternGetInteger return FcResultOutOfMemory")
                out_list.append(_i.value)
                idx += 1

            return out_list

        def _fc_pattern_get_bool(_pattern: _FcPatternP, _property: bytes) -> Union[List[bool], None]:
            out_list: List[bool] = []
            idx: int = 0

            while True:
                _i = _FcBool()
                _result = fc.FcPatternGetBool(p, _property, idx, ctypes.byref(_i))
                if _result == _FcResultMatch:
                    pass
                elif _result == _FcResultNoId:
                    break
                elif _result in [_FcResultNoMatch, _FcResultTypeMismatch]:
                    return None
                elif _result == _FcResultOutOfMemory:
                    raise RuntimeError(f"Font subsystem not init for {_property} FcPatternGetBool return FcResultOutOfMemory")
                out_list.append(_i.value == _FcTrue)
                idx += 1

            return out_list

        self.font_raw: List[_FontRaw] = []
        for i in range(fontsets.nfont):
            p = fontsets.fonts[i]
            r = _FontRaw(
                family=_fc_pattern_list_strings(p, _FcFamily),
                familylang=_fc_pattern_list_strings(p, _FcFamilyLang),
                style=_fc_pattern_list_strings(p, _FcStyle),
                stylelang=_fc_pattern_list_strings(p, _FcStyleLang),
                fullname=_fc_pattern_list_strings(p, _FcFullname),
                fullnamelang=_fc_pattern_list_strings(p, _FcFullnameLang),
                postscriptname=_fc_pattern_list_strings(p, _FcPostscriptname),
                slant=_fc_pattern_get_int(p, _FcSlant),
                weight=_fc_pattern_get_int(p, _FcWeight),
                width=_fc_pattern_get_int(p, _FcWidth),
                file=_fc_pattern_list_strings(p, _FcFile),
                index=_fc_pattern_get_int(p, _FcIndex),
            )
            if r.weight is None or r.slant is None or r.width is None:
                continue
            self.font_raw.append(r)

        # destroy
        fc.FcPatternDestroy(pat)
        fc.FcFontSetDestroy(cfontsets)
        # parse font raw families
        for fr in self.font_raw:
            fm = fr.family[0]
            fn = fr.fullname[0]
            fs = (fr.slant[0], fr.weight[0], fr.width[0])
            fi = FontInfo(
                family=fr.family,
                familylang=fr.familylang,
                style=fr.style,
                stylelang=fr.stylelang,
                fullname=fr.fullname,
                fullnamelang=fr.fullnamelang,
                postscriptname=fr.postscriptname,
                slant=fr.slant[0],
                weight=fr.weight[0],
                width=fr.width[0],
                file=fr.file[0],
            )

            if fm not in self.fonts.keys():
                self.fonts[fm] = {}
                self.family_styles[fm] = []
                self.families.append(fm)
            if fs not in self.fonts[fm].keys():
                self.fonts[fm][fs] = []
                self.family_styles[fm].append(fs)
            self.fonts[fm][fs].append(fi)

            if fn not in self.name_fonts.keys():
                self.name_fonts[fn] = {}
                self.fullname_styles[fn] = []
                self.fullnames.append(fn)
            if fs not in self.name_fonts[fn].keys():
                self.name_fonts[fn][fs] = []
                self.fullname_styles[fn].append(fs)
            self.name_fonts[fn][fs].append(fi)

        self.fullnames.sort()

        fc.FcObjectSetDestroy(objset)
        # finalize fontconfig library
        fc.FcFini()

if __name__ == "__main__":
    font = FontManager()
    font.init()

    for f in font.fullnames:
        logger.warning(f)

    for fm in font.fonts.keys():
        for fs in font.fonts[fm].keys():
            if len(font.fonts[fm][fs]) > 1:
                logger.warning(f"===== {fm}, {fs} =====")
                for f in font.fonts[fm][fs]:
                    logger.warning(f"\t{f}")
                logger.warning(f"===== end =====")

    logger.warning("")
    logger.warning(f"===== start =====")
    for fn in font.name_fonts.keys():
        for fs in font.name_fonts[fn].keys():
            if len(font.name_fonts[fn][fs]) > 1:
                logger.warning(f"===== {fn}, {fs} =====")
                for f in font.name_fonts[fn][fs]:
                    logger.warning(f"\t{f}")
                logger.warning(f"===== end =====")
