
import ctypes
import ctypes.util
import dataclasses
import logging

from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _FontRaw:
    namelang: List[str]
    family: List[str]
    familylang: List[str]
    style: List[str]
    stylelang: List[str]
    fullname: List[str]
    fullnamelang: List[str]
    file: List[str]
    index: List[int]


@dataclasses.dataclass
class FontInfo:
    family: str
    familylang: str
    style: str
    stylelang: str
    fullname: str
    file: str


class FontManager:
    def __init__(self):
        self.fontconfig = ctypes.util.find_library("fontconfig")
        self.font_raw: List[_FontRaw] = []
        # { family: { style: List[FontInfo] } }
        self.fonts: Dict[str, Dict[str, List[FontInfo]]] = {}
        self.families: List[str] = []
        self.styles: Dict[str, List[str]] = {}

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
        _FcStyle = b"style"  # String  Font style. Overrides weight and slant
        _FcStyleLang = b"stylelang"  # String  Language corresponding to each style name
        _FcFullname = b"fullname"  # String  Font face full name where different from family and family + style
        _FcFullnameLang = b"fullnamelang"  # String  Language corresponding to each fullname
        _FcFile = b"file"  # String  The filename holding the font relative to the config's sysroot
        _FcIndex = b"index"  # Int     The index of the font within the file

        # functions
        fc.FcInit.restype = _FcBool
        fc.FcFontList.restype = _FcFontSetP
        fc.FcFontList.argtypes = [ctypes.c_void_p, _FcPatternP, _FcObjectSetP]
        fc.FcFontSetDestroy.argtypes = [_FcFontSetP]
        fc.FcPatternAddString.restype = _FcBool
        fc.FcPatternAddString.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_char_p]
        fc.FcPatternCreate.restype = _FcPatternP
        fc.FcPatternDestroy.argtypes = [_FcPatternP]
        fc.FcPatternGetString.restype = _FcResult
        fc.FcPatternGetString.argtypes = [_FcPatternP, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        fc.FcObjectSetBuild.restype = _FcObjectSetP
        fc.FcObjectSetDestroy.argtypes = [_FcObjectSetP]

        if fc.FcInit() != _FcTrue:
            raise RuntimeError(f"Font subsystem not init for {self.fontconfig} FcInit failed")

        # build an object set from a null-terminated list of property names
        objset = fc.FcObjectSetBuild(_FcNamelang, _FcFamily, _FcFamilyLang, _FcStyle, _FcStyleLang,
                                     _FcFullname, _FcFullnameLang, _FcFile, _FcIndex, None)
        # build patterns with no properties
        pat = fc.FcPatternCreate()
        # list fonts
        cfontsets = fc.FcFontList(None, pat, objset)
        if not cfontsets:
            raise RuntimeError("Font subsystem not init for FcFontList empty pattern return NULL pointer")

        # list of FcPattern
        fontsets = ctypes.cast(cfontsets, ctypes.POINTER(_FcFontSet)).contents

        def _fc_pattern_list_strings(_pattern: _FcPatternP, _property: bytes) -> List[str]:
            out_list: List[str] = []
            idx: int = 0

            while True:
                _s = ctypes.c_char_p()
                _result = fc.FcPatternGetString(p, _property, idx, ctypes.byref(_s))
                if _result != _FcResultMatch:
                    break
                out_list.append(_s.value.decode("utf-8", errors="replace"))
                idx += 1

            return out_list

        def _fc_pattern_get_int(_pattern: _FcPatternP, _property: bytes) -> List[int]:
            out_list: List[int] = []
            idx: int = 0

            while True:
                _i = ctypes.c_char_p()
                _result = fc.FcPatternGetString(p, _property, idx, ctypes.byref(_i))
                if _result != _FcResultMatch:
                    break
                out_list.append(_i.value)
                idx += 1

            return out_list

        self.font_raw: List[_FontRaw] = []
        for i in range(fontsets.nfont):
            p = fontsets.fonts[i]
            self.font_raw.append(_FontRaw(
                namelang=_fc_pattern_list_strings(p, _FcNamelang),
                family=_fc_pattern_list_strings(p, _FcFamily),
                familylang=_fc_pattern_list_strings(p, _FcFamilyLang),
                style=_fc_pattern_list_strings(p, _FcStyle),
                stylelang=_fc_pattern_list_strings(p, _FcStyleLang),
                fullname=_fc_pattern_list_strings(p, _FcFullname),
                fullnamelang=_fc_pattern_list_strings(p, _FcFullnameLang),
                file=_fc_pattern_list_strings(p, _FcFile),
                index=_fc_pattern_get_int(p, _FcIndex),
            ))

        # destroy
        fc.FcPatternDestroy(pat)
        fc.FcFontSetDestroy(cfontsets)
        # parse font raw families
        for fr in self.font_raw:
            for i in range(len(fr.family)):
                fm = fr.family[i]
                if fm not in self.fonts.keys():
                    self.fonts[fm] = {}
                    self.styles[fm] = []
                    self.families.append(fm)
        self.families.sort()

        # get style from family
        for fm in self.families:
            # list fonts
            pat = fc.FcPatternCreate()
            r = fc.FcPatternAddString(pat, _FcFamily, fm.encode("utf-8"))
            if r != _FcTrue:
                raise RuntimeError(f"Font subsystem not init for FcPatternAddString return {r} for family {fm}")
            cfontsets = fc.FcFontList(None, pat, objset)
            if not cfontsets:
                raise RuntimeError(f"Font subsystem not init for FcFontList family {fm} return NULL pointer")
            # list of FcPattern
            fontsets = ctypes.cast(cfontsets, ctypes.POINTER(_FcFontSet)).contents
            for i in range(fontsets.nfont):
                p = fontsets.fonts[i]
                r = _FontRaw(
                    namelang=_fc_pattern_list_strings(p, _FcNamelang),
                    family=_fc_pattern_list_strings(p, _FcFamily),
                    familylang=_fc_pattern_list_strings(p, _FcFamilyLang),
                    style=_fc_pattern_list_strings(p, _FcStyle),
                    stylelang=_fc_pattern_list_strings(p, _FcStyleLang),
                    fullname=_fc_pattern_list_strings(p, _FcFullname),
                    fullnamelang=_fc_pattern_list_strings(p, _FcFullnameLang),
                    file=_fc_pattern_list_strings(p, _FcFile),
                    index=_fc_pattern_get_int(p, _FcIndex),
                )
                for fs in range(len(r.style)):
                    if fs not in self.fonts[fm].keys():
                        self.fonts[fm][r.style[fs]] = []
                        self.styles[fm].append(r.style[fs])
                    self.fonts[fm][r.style[fs]].append(FontInfo(
                        family=r.family[0],
                        familylang=r.familylang[0],
                        style=r.style[fs],
                        stylelang=r.stylelang[fs],
                        file=r.file[0] if r.file else "",
                        fullname=r.fullname[0] if r.fullname else "",
                    ))
            fc.FcPatternDestroy(pat)
            fc.FcFontSetDestroy(cfontsets)

        fc.FcObjectSetDestroy(objset)
        # finalize fontconfig library
        fc.FcFini()

if __name__ == "__main__":
    font = FontManager()
    font.init()

    for f in font.families:
        print(f)

    print(font.styles["Noto Sans Arabic"])
    print(font.fonts["Noto Sans Arabic"]["Regular"])
