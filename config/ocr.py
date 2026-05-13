# -*- coding: utf-8 -*-
"""
config/ocr.py - Tesseract OCR 配置
"""

import os
import re
import sys
import shutil

# ===================== Tesseract OCR 路径自动检测 =====================
def _detect_tesseract_path() -> str:
    env_path = os.getenv("TESSERACT_PATH", "").strip()
    if env_path:
        return env_path

    if sys.platform == "win32":
        for base in [r"C:\Program Files", r"C:\Program Files (x86)", r"D:\tools", r"D:\software"]:
            for ver in ["", "_ocr", r"Tesseract-OCR", r"Tesseract", "tesseract"]:
                candidate = os.path.join(base, ver, "tesseract.exe")
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate)
        return r"D:\software\tesseract"
    else:
        found = shutil.which("tesseract")
        if found:
            return os.path.dirname(found)
        for base in ["/usr/bin", "/usr/local/bin", "/opt"]:
            for ver in ["", "_ocr", "tesseract"]:
                candidate = os.path.join(base, ver, "tesseract")
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate)
        return ""


TESSERACT_PATH = _detect_tesseract_path()

# ===================== OCR =====================
OCR_PSM_MODES = [6, 7]
NET_VALUE_DECIMAL = 4
