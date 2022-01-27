"""
Contains embedded image and icon resources for SQLitely. Auto-generated.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     26.01.2022
@modified    27.01.2022
------------------------------------------------------------------------------
"""
try:
    import wx
    from wx.lib.embeddedimage import PyEmbeddedImage
except ImportError:
    class PyEmbeddedImage(object):
        """Data stand-in for wx.lib.embeddedimage.PyEmbeddedImage."""
        def __init__(self, data):
            self.data = data


"""Returns the application icon bundle, for several sizes and colour depths."""
def get_appicons():
    icons = wx.IconBundle()
    [icons.AddIcon(i.Icon) for i in [
        Icon16x16_32bit, Icon32x32_32bit, Icon48x48_32bit
    ]]
    return icons


"""NightFall application 16x16 icon, 32-bit colour."""
Icon16x16_32bit = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKnRFWHRDcmVhdGlvbiBUaW1l"
    "AFQgMzAgb2t0IDIwMTIgMjI6NDQ6MDUgKzAyMDC0W8ohAAAAB3RJTUUH3AoeFDEedCN/hAAA"
    "AAlwSFlzAAALEgAACxIB0t1+/AAAAARnQU1BAACxjwv8YQUAAALsSURBVHjaXVM9bxxVFD3v"
    "c96Ox17WKxNZSoSEGwQNEqnSJIpcOlJER4Nc0EKHXCIXFK4i0dFZokqH5C1o+Q1AJERooFj5"
    "g4x3dufjfXMHKYjwitGM5p1zzzn3Xob/ndtvnx7EEI9trI6YEvsBDLycL2W1sxhcPH/nk69/"
    "/+999volfwV+XT06c336QldTfbWsAbGFclaBGQMz30MulIuef3P3V3PCTk/TvwQjeHjr8PtN"
    "559kprCqO1jHUW7vICsGGzkmuyURTUhNQaji4t7L2dORRI4EtXpwJgnMrMWrVzUu6wZ6opFz"
    "hDQlJIHi4JDoP+8NeGGe/Ha3PSPol+zy848OUtG8SKnS3ntc1S0a2yKwCnu7U2zvTJGYhENP"
    "hUkBl8hCELFxXsv3ZYer47RSetNeo+4cXczgokSpEkRMGNYNfBYIHJAuQ2rxD0HwQRvOj+VQ"
    "56OuJ2CM6HoBjwETs4Ynd06RdHAQDkllTKIBS4KYyLkFBmOPZHPb79tMzEIjpQRGsW5ISeIC"
    "ve/AdCSrnMJU2Aw95nlGnw5cEXVS+7KzHG1oIEiWS5HaIhCZQDN4/CUnqKKgYhbdmlEWAd5f"
    "Y1ZRJ7wlO9uQNujl2uKODWNM5J8XCAQoSGkcAm69ANcSKY5VJ1jbACUSTJEoi24p21YuVmnn"
    "w47kDpRwohglmyBLSppmwJOtvuMEZiiZhQ+UU2KQlBGL3YLfyHTuXXA2V1hZquAdGrLSUuWN"
    "o2AjoyA7RL+h4QqgcYZiGYL1jvnqXCz+bOrDt6dTm8SDyDqqrxATJzsDRB5nlWEgMiktdkuD"
    "O5XBtiEFrHr2+LtfnvNxEpufLk/WKVz0ntqWPKgAyeOkJGPlAxzrEalTgtKvtIPO6eLhuz+f"
    "jFgxPn6kdTi8aZ/fzIotn9P9lLVwxJJogLji2CIV81JgbrgrpH728L0/PmOnSG9s4+vz6Qf3"
    "DrZ8d6yUPDKZ7e+WHHulWJa6WxRydv7xDy/fWOe/Adzse81dEqnqAAAAAElFTkSuQmCC"
)


"""NightFall application 32x32 icon, 32-bit colour."""
Icon32x32_32bit = PyEmbeddedImage(
    "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"
    "AABJRU5ErkJggg=="
)


"""NightFall application 48x48 icon, 32-bit colour."""
Icon48x48_32bit = PyEmbeddedImage(
    "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"
    "6ZnD1+t//y929v2ppwf70AAAAABJRU5ErkJggg=="
)


"""Small image for brightness slider end in theme editor."""
Brightness_High = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACi0lEQVQ4y32TzW9MYRTGf+e9"
    "d8a0YwZth8YESRuqDTbqK5GwsaNsxMpS4g+wFAmJiMQfYC+x9FFLS9RXpRGiVJUqZpgxmJn2"
    "zr33/bC406ZEPMnJ+5xznnPOexZH+Avjd6QL6AN6gGw7PA9UgZnhI662XC+L5OmopIHtwDZg"
    "M9ALrGynm0AZeAu8BF7sGnHRUoPHtyQtwj5gbzqzdve6vuODXWt3bUilMp04R6yDhdrXx3Nf"
    "39+YjFqVJ8Aj53i455iLfAAHO5xjX0eu/+DA8Nn9vv6edeEHTJiMV7Cy0N0/uKbn/MY3E5ez"
    "QWNW2muNy9gN6QKOpjOFkaG9Fw+p6GPWWc2/IOJhvNXzk08v3Y3C2ihw27eWfmDLuk0jg671"
    "MRvrBv+DsjrbUzww+Gn65mug37eGAlBc1T1QjIOZJWFsIwLdJDTzGBNiiVFYfOWR7uwtWkMR"
    "KPjGkgPyCpPV1qBdTCP8Tss0AYuIRYnFw6HEgoQ4alljyQM531oEUNZGLOg69aiKczFK3FKx"
    "kLxKXMJpYC0KEN8YmkCzPv8lqEflTsGgVCJWy36gxC75NgqDxTplDFVjKH0rTZRSnuArnZjE"
    "+Cpe5mu8Nv9ZqZSMoWQMVWUt08YyVZl98U6MCzxl8CURJgUxvsQJF40Ow6D8qfbOWKasZdq7"
    "PsrCicOS0lp3NH9UM2t68oV0yqY8ZfAksWQlQxxFweTzz8+Chfiec9w/cspN+QDGMBFFLh8E"
    "Tb859koXN3X19a7PFTIdKiM4oiBulT83KnOzv2bClh4DHqTTMvHHMV27wopYMwzsBIaADUC+"
    "na4Dc8Ar4FnKZ/zkGcI/Gizi6gUKzrG1fY25drgBlEV4ffocleX63z0oTbaa3lsYAAAAAElF"
    "TkSuQmCC"
)


"""Small image for brightness slider start in theme editor."""
Brightness_Low = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGXRFWHRTb2Z0d2FyZQBBZG9i"
    "ZSBJbWFnZVJlYWR5ccllPAAAAgVJREFUeNrEk01oE0EYht/Zn3R3k1KbovUvbaCHhAi2IOLB"
    "S6GVIoh40Jt4KHgRD1496t2T4r3gRbC3empaPFRBe2lALdqmJE1LooSk7uZnm83s+E3dQGN6"
    "66EDz7Kz+86737zfDhNC4DhDwTGH1rl5fE2FwgD2z9QkjEPv24RLNKle36fLq8+82yAYKjFI"
    "jBEpIho8rxDfiSxRJXhPBXI7FMcgmV8fS01M3bz/6MbQ+fioTGivVMgvzL1c3FpfW6Lpx8DQ"
    "78qAFltUWiKeHJ+59fDprBvqT/62HXOzsGOaw7HkvSfPZ0cSl2ekRmp7QuQCJjExeefB9FYu"
    "H7bLZdQrFbi2jczqF2xs/Ahfmbo9LTVSe5RBiDin9kVijHMIz8OfShmMu3CcXxCsCcXSY1Ij"
    "tT0ZcF82AHq9VmOWYcBtNdBsOTgbPYPUcAJNtw7LNBjpdBw0638DcdCq6m4+W1TDVlwJCYQj"
    "JrQ+Bo2+d/pUFMVcrki6atDW7i20fdbwOFv7tPw+oxvCDRkK9aqFgaF+RAYs+MJzF968zUiN"
    "1PYY7LdR2+f4WtjeTqfn51cazl5pZPSCp6rw8pvZ0utnL1Z+rmfTUiO1nXWscxbuXtKoCugy"
    "JJpeJSaJi4Fuh/hArKoMRU2B9+5b+8g/0SODXfJ0pJjopN0iHMZgkwE/vICd+Gn8K8AAsW7k"
    "DEehxxcAAAAASUVORK5CYII="
)


"""Tray icon when theme is not applied."""
IconTray_Off = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKnRFWHRDcmVhdGlvbiBUaW1l"
    "AFQgMzAgb2t0IDIwMTIgMjI6NDQ6MDUgKzAyMDC0W8ohAAAAB3RJTUUH3AoeFDIuedcc6wAA"
    "AAlwSFlzAAALEgAACxIB0t1+/AAAAARnQU1BAACxjwv8YQUAAAIWSURBVHjaXZM9qxpBGIXH"
    "dV2/DWIRLGy0SxUklb2dF2JjbZE6lpbWVhfyC2wsbmVAf4Cd/yCNBOxEUCKIX3v9yHkG55Kb"
    "gdl39p33PefMmd2I+W9Mp9PK5XJp3263RjQaLd7vd5NIJJbxeHzy+vo6qNVqv/+tj7jFaDTy"
    "VNQ/n8/fk8lksNlsjABMJpMxvu+bbDbLeyjgH/v9vluv129vADSr8OfpdHqKRCJmt9sZsZlU"
    "KmVBrtfrG1AQBMbzvPHxePwKiAeANvphGD5Julmv12a1Whmx2ClQGiygmmxOEaK+VTAcDisq"
    "+KV1AMB2u7WFKMnn85aZgYpYLGbBmFqHip98DNMMDoeDYeqMVjZyMdDlGBCQB4Ae1bV9SWrI"
    "OLtJhElm2iYYHTtN5BzBA6zhy7AiBSA7JncE18igCT+4DfYA137Rl3mWGQBQ3UA6DfoGLBB7"
    "HAkz8YXIjeDBUoUfKaAQJpQACLg7NxFWR/a4zqUvuRMlP7MBA8PJdsfiSAAj3RFRqzjxlBhI"
    "TkgCEGQjD3a3BoTIPvkHAV/lIDqbzf5Uq9UPQqtRCBARFvuhiJVmFGBgLpezvuj9udPpvFio"
    "+XzeVdGYQifPsaLCXR9gXLHiuFQqde3t8FgsFvdCofAiY9IC+CIAm3dmMnE+nU6HMvK5XC5/"
    "azabt3d/oxutVqui0FZhQ2ct0qi5FPhEc9Dr9d79zn8BzRuXAnOgpKsAAAAASUVORK5CYII="
)


"""Tray icon when theme is temporarily suspended."""
IconTray_Off_Paused = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACqElEQVQ4y12Tu0psSRSGv6pd"
    "u7q1a3uhGxoREwWDA2YTmXekwpgYGwyGBjKDobHMwMA8wUkMJuoBfQCfokHkgIHSiAra7b7U"
    "rsueZLo5Z1ayVlDr+2vdBP+z29vbLe/9cYxxP0mStaZpaLfb41ardeOc+7q7u/vt+/diFgyH"
    "Q9lqtS6ttacLCwv67e2NJEkwxqCUIssykiSpY4x/5Xl+PhgM4hwwHA6lMeafqqoOhBBMp1Oc"
    "cywuLpIkCSGEOUhrjZTyuizLnweDQZQASqnLuq4PvPe8vr7y/PxMnufkeU5VVUgpcc5RliV5"
    "nlOW5YEQ4hJAXF1dbUkpR4D23vP+/k5ZlgghWF1dxRgDQAiBNE2RUiKlJE3TWkr5RXnvj733"
    "uigKiqKg1+uxt7dHURTc3d2RZRk7Ozs8Pj4yGo1QSiGlxHuvkyQ5lnme708mE6qqwlqLlJL1"
    "9XX6/f5MiX6/T5ZlWGup6xrn3CzeV9PpdC2EgFKKGCMATdMQY+Tz85N2uz0v4ePjgyzLEEKQ"
    "pikhhDVV1zXWWpRSeO/nkBgjeZ6ztLRE0zRYa3l5ecE5hzEG5xxaa5T3flxVVd97TwiBsizn"
    "S+K9x1o7Bwoh5mL/jXMsy7K8sdZSFAVVVc3994nWWpxzCCGYCTVNQwjhRpydnW0VRTEKIWhr"
    "LcYYtre3EULw9PTE8vIy3W6XyWTCeDxGKUWv10NrXUspvwiAk5OT3733v856IISYT2DWG601"
    "KysrdDqd2Yb+cXp6+psEuL+/P3fOXTvn5t+LMeKco6oqYoxzcKvVQghxvbGxcQ6QADw8PDTd"
    "bvdvrXUnhPBT0zTJrH6lFEopjDF0Op06TdM/Nzc3fzk8PIw/XOPMjo6OtoDjNE33pZRrxhiM"
    "MWOt9Y3W+uvFxcUP5/wvIpuHTwi8H/EAAAAASUVORK5CYII="
)


"""Tray icon when theme is not applied and schedule is enabled."""
IconTray_Off_Scheduled = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKnRFWHRDcmVhdGlvbiBUaW1l"
    "AFQgMzAgb2t0IDIwMTIgMjI6NDQ6MDUgKzAyMDC0W8ohAAAAB3RJTUUH3AofEiwFvRvBowAA"
    "AAlwSFlzAAALEgAACxIB0t1+/AAAAARnQU1BAACxjwv8YQUAAAILSURBVHjaXVO9ijJBEJwd"
    "1/UX08PY7EA432Phi80EAyMvETQwUDEyMNlc0Ef4YPEFxEAxPjAwNhJEFHXV9arm7EOvYZjp"
    "3q7q6m611B9bLBa5MAxLOG4kEsne73flOM4ax7/dbsN8Pr96zrfkgUQ9nU57l8vlMxaLOdvt"
    "VmmtVTKZVLZtq1QqRT9AngeShmVZ4S8BwbPZ7H8QBC79w+GgrterSiQShgRqzDsajRoymF8o"
    "FP6RRNObTCas7EKiYuXNZqOOx6M55/NZIdEQSoy58/m8ZxSMx+McqnxBhUOC3W6nTqeTqZzJ"
    "ZEwLNKpgdcZJCDUB3u82QCVUcchMIBMxPJPIATLOm8YW+I0EwDnIKdlIcCmTEnmTABM3N6Qa"
    "MN8yC5LwTbUgc+39fp99OCaBACqRvhmn8WY8nU6bb4/8rI3JKx4GSCRG6awUj8dNnGQ03o+V"
    "/mwFH9eQ/sYPz0o4MLYgMd6MsU36bBO2thHwcT6ogkCRSyNAZtFsNn/VDQYDadfXqDwEOGCA"
    "7OxT2qIv4G63a8D9fl+Vy2U+A5yhrtfrK4A9qc4hEsQZPKuSVdZqNVHnFYvFlX5IbiDZJ1A2"
    "wUMCKhICz/PUaDQy/nK5bLz8mVqtlsZPuIfET7A7XBUnzWFxFtICrd1uRzqdTvhCIFatVnMA"
    "l7AiFwRZrgy7X8P3sdJhpVJ5+Tt/A7XSjiMMbcfNAAAAAElFTkSuQmCC"
)


"""Tray icon when theme is applied."""
IconTray_On = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKnRFWHRDcmVhdGlvbiBUaW1l"
    "AFQgMzAgb2t0IDIwMTIgMjI6NDQ6MDUgKzAyMDC0W8ohAAAAB3RJTUUH3AoeFDEedCN/hAAA"
    "AAlwSFlzAAALEgAACxIB0t1+/AAAAARnQU1BAACxjwv8YQUAAALsSURBVHjaXVM9bxxVFD3v"
    "c96Ox17WKxNZSoSEGwQNEqnSJIpcOlJER4Nc0EKHXCIXFK4i0dFZokqH5C1o+Q1AJERooFj5"
    "g4x3dufjfXMHKYjwitGM5p1zzzn3Xob/ndtvnx7EEI9trI6YEvsBDLycL2W1sxhcPH/nk69/"
    "/+999volfwV+XT06c336QldTfbWsAbGFclaBGQMz30MulIuef3P3V3PCTk/TvwQjeHjr8PtN"
    "559kprCqO1jHUW7vICsGGzkmuyURTUhNQaji4t7L2dORRI4EtXpwJgnMrMWrVzUu6wZ6opFz"
    "hDQlJIHi4JDoP+8NeGGe/Ha3PSPol+zy848OUtG8SKnS3ntc1S0a2yKwCnu7U2zvTJGYhENP"
    "hUkBl8hCELFxXsv3ZYer47RSetNeo+4cXczgokSpEkRMGNYNfBYIHJAuQ2rxD0HwQRvOj+VQ"
    "56OuJ2CM6HoBjwETs4Ynd06RdHAQDkllTKIBS4KYyLkFBmOPZHPb79tMzEIjpQRGsW5ISeIC"
    "ve/AdCSrnMJU2Aw95nlGnw5cEXVS+7KzHG1oIEiWS5HaIhCZQDN4/CUnqKKgYhbdmlEWAd5f"
    "Y1ZRJ7wlO9uQNujl2uKODWNM5J8XCAQoSGkcAm69ANcSKY5VJ1jbACUSTJEoi24p21YuVmnn"
    "w47kDpRwohglmyBLSppmwJOtvuMEZiiZhQ+UU2KQlBGL3YLfyHTuXXA2V1hZquAdGrLSUuWN"
    "o2AjoyA7RL+h4QqgcYZiGYL1jvnqXCz+bOrDt6dTm8SDyDqqrxATJzsDRB5nlWEgMiktdkuD"
    "O5XBtiEFrHr2+LtfnvNxEpufLk/WKVz0ntqWPKgAyeOkJGPlAxzrEalTgtKvtIPO6eLhuz+f"
    "jFgxPn6kdTi8aZ/fzIotn9P9lLVwxJJogLji2CIV81JgbrgrpH728L0/PmOnSG9s4+vz6Qf3"
    "DrZ8d6yUPDKZ7e+WHHulWJa6WxRydv7xDy/fWOe/Adzse81dEqnqAAAAAElFTkSuQmCC"
)


"""Tray icon when theme is applied and schedule is enabled."""
IconTray_On_Scheduled = PyEmbeddedImage(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKnRFWHRDcmVhdGlvbiBUaW1l"
    "AFQgMzAgb2t0IDIwMTIgMjI6NDQ6MDUgKzAyMDC0W8ohAAAAB3RJTUUH3AofEi0Nqtt40AAA"
    "AAlwSFlzAAALEgAACxIB0t1+/AAAAARnQU1BAACxjwv8YQUAAALpSURBVHjaXVM7aBxXFD3v"
    "M29mdlarP0bGScByZTeGVDa4sRNIsWDhIqQK6gKBuAgYVYmjUoUbFQa7EqRLFcMWBuNWlTs7"
    "SaNNE5JFKxTt7uzO5319Z4mdKG8Y7nvwzrn3nHsfw//W6MnWprNuu3adrlB8QwcGnq0MZNbp"
    "VSw6+Ojed/3/3mfvNuEh+En79p6u3P0466jhYIQgW8iW2kCSIF1bR1CR9k7uX/xN7bDdXf+e"
    "oAGXi588K0rT9UxhMpqhqgVaCx0CAdpxpMvZnEi0EnjEvQ/7S3cbEtkQnKmbe7IyXWiN0ekZ"
    "jkc5VEJIWMg4g2zFsFWNUNcUK/A46fYvzfbowgN2/M3Hmz7Ofw0+U9pYDCn7pJrC8TbWVxbR"
    "XliCZwIaDTAFEwKBfpkkmkfyqqww3LbjSE1nJzgrDXTw4KQ9ZR7CetT5GAYCljNIHSCUAIjA"
    "GqsSIbdlOUK3KDVq61BUHCYYpEkO6yPoOoarOZpOOBmQuhgxqQ5SgBFZHU+7cjwuN7SnbELB"
    "+0CuBkypEs8FSl0AypHVHCGKMK1KrJIkJmrwyIG7aEOWlcDM5FS2gPF0Ocg5eFJa/C052tSs"
    "mr5iwsgLC2NPsJwlYEZDqgWSZeQgr9mFaqZRopFH+sgyJRg5bnFmObiScM5QkhR5ZRAJh0Rx"
    "SlQO5KyUvZHtXC9tgZKRvoaZpcgicpqabJ1HUXB8e/jn++n7+fPLsFSpCNMeH/LowGija59h"
    "XCeYGIMxSZkZgamm6BiB/8CjG0tz8ONPL2Lrp9/ROBRY+4B/dXjU1yHZN05AsIqYY+oIw6nL"
    "UVJnvHNzIO3m8esXf81jgvb+nae/9HlzmLwe7OTB9ypDE+cNGHWDJgkTKn9k/yGg+fjxs1W8"
    "/OLS/Hzr8pudc4/pIcAHV1b2Arf3FVIFaakigVgxtLnH96+G/z7BH5hgu/DnCN6tL699sLlg"
    "im2hZDcJfGM15VhriUFLzXqxXD649/zo3HN+CzVkcYMJjL9TAAAAAElFTkSuQmCC"
)
