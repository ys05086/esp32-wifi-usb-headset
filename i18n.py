"""Small, dependency-free UI catalog. Audio and protocol data are never translated."""
import json
import locale
from pathlib import Path
import sys

from translations import EN

LANGUAGES = {'ko': '한국어', 'en': 'English'}
_language = 'ko'


def preferred_language(settings):
    if settings.get('language') in LANGUAGES:
        return settings['language']
    try:
        name = locale.getlocale()[0] or ''
    except (ValueError, OSError):
        name = ''
    return 'ko' if name.lower().startswith(('ko', 'korean')) else 'en'


def saved_language():
    folder = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent
    try:
        settings = json.loads((folder / 'settings.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        settings = {}
    return preferred_language(settings if isinstance(settings, dict) else {})


def set_language(language):
    global _language
    _language = language if language in LANGUAGES else 'ko'


def get_language():
    return _language


class Message(str):
    """Keep the source and values so a status can be redrawn after a language change."""
    def __new__(cls, source, values):
        template = EN.get(source, source) if _language == 'en' else source
        values = {k: tr(v) if isinstance(v, Message) else v for k, v in values.items()}
        instance = super().__new__(cls, template.format(**values) if values else template)
        instance.source, instance.values = source, values
        return instance


def tr(source, **values):
    if isinstance(source, Message):
        return Message(source.source, source.values)
    return Message(source, values)


class WidgetText:
    """Remember static captions only; never touch device names, entries or audio state."""
    def __init__(self, root):
        reverse = {value: key for key, value in EN.items()}
        self.widgets = []

        def visit(widget):
            options = widget.keys()
            if 'text' in options and not ('textvariable' in options and widget.cget('textvariable')):
                text = str(widget.cget('text'))
                self.widgets.append((widget, reverse.get(text, text)))
            for child in widget.winfo_children():
                visit(child)
        visit(root)

    def refresh(self):
        for widget, source in self.widgets:
            if widget.winfo_exists():
                widget.configure(text=tr(source))
