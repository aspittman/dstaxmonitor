from pathlib import Path
import os
ROOT = Path(__file__).resolve().parent
class Config:
    DATA_DIR = ROOT / 'data'
    UPLOAD_DIR = ROOT / 'uploads'
    EXPORT_DIR = ROOT / 'exports'
    DATABASE = DATA_DIR / 'dstaxmonitor.sqlite3'
    RULE_DIR = ROOT / 'tax_rules'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    DEBUG = False
