"""Opencode Custom Provider (OCP) — редактор opencode.json."""

import json
import os
import re
import sys
import unicodedata
from base64 import b64decode
from copy import deepcopy
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from urllib.parse import urlsplit, urlunsplit

import requests
from PyQt6.QtCore import (
    QBuffer, QByteArray, QEvent, QIODevice, QLockFile, QObject, QPoint, QPointF, QRectF,
    QSaveFile, QSettings, QSize, Qt, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QImageReader, QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QStyledItemDelegate,
    QStyle, QVBoxLayout, QWidget,
)

APP_NAME = "Opencode Custom Provider (OCP)"
DEFAULT_PATH = Path.home() / ".config" / "opencode" / "opencode.json"
SCHEMA = "https://opencode.ai/config.json"
CONFIG_SUFFIXES = {".json", ".jsonc"}
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
TEXT = "#f7f7f7"
MONO = "monospace"
DESIGN_SIZE = QSize(1200, 750)
UI_SCALE = 1.0

LANGUAGE = "ru"

TRANSLATIONS = {
    "Файл не найден по пути по умолчанию": "File not found at the default path",
    "Не удалось открыть файл по пути по умолчанию": "Could not open the file at the default path",
    "Указать": "Browse",
    "Провайдер": "Provider",
    "Добавить провайдера": "Add provider",
    "Провайдеров пока нет": "No providers yet",
    "Добавьте первого провайдера или перетащите сюда\nфайл opencode.json": "Add your first provider or drop\nan opencode.json file here",
    "Название провайдера": "Provider name",
    "Например, OpenRouter": "For example, OpenRouter",
    "API ключ": "API key",
    "Подгрузить с сервера": "Load from server",
    "Загрузка…": "Loading…",
    "Модель": "Model",
    "Отмена": "Cancel",
    "Сохранить": "Save",
    "Закрыть": "Close",
    "Сбросить": "Discard",
    "Продолжить редактирование": "Continue editing",
    "Сбросить несохранённые изменения провайдера?": "Discard unsaved provider changes?",
    "Открыть конфиг OpenCode": "Open OpenCode configuration",
    "Конфиги OpenCode (*.json *.jsonc)": "OpenCode configurations (*.json *.jsonc)",
    "Закрыть список моделей": "Close model list",
    "Поиск по ID модели": "Search by model ID",
    "Модели на сервере": "Models on server",
    "Все": "All",
    "Выбрать все видимые модели": "Select all visible models",
    "Добавить выбранные": "Add selected",
    "Поиск не дал результатов": "No matching models",
    "На сервере пока нет моделей": "No models found on the server",
    "Новый провайдер": "New provider",
    "провайдера": "provider",
    "Эта модель уже добавлена.": "This model has already been added.",
    "Укажите название провайдера.": "Enter a provider name.",
    "В конфиге есть повторяющийся ключ JSON.": "The configuration contains a duplicate JSON key.",
    "Конфиг содержит число, недопустимое в JSON.": "The configuration contains a number that is invalid in JSON.",
    "Корневое значение конфига должно быть объектом JSON.": "The configuration root must be a JSON object.",
    "Поле «provider» должно быть объектом JSON.": "The provider field must be a JSON object.",
    "Провайдер, его «options» и «models» должны быть объектами JSON.": "The provider, options and models must be JSON objects.",
    "Файл занят. Повторите сохранение через несколько секунд.": "The file is busy. Try saving again in a few seconds.",
    "Файл изменился на диске. Откройте его снова перед сохранением.": "The file changed on disk. Reopen it before saving.",
    "Не удалось прочитать значение из ссылки {file:…}.": "Could not read the value from the {file:…} reference.",
    "Укажите Base URL в формате http:// или https://.": "Enter a Base URL beginning with http:// or https://.",
    "API ключ должен быть одной строкой.": "The API key must be a single line.",
    "ответ не содержит список ID моделей": "response does not contain a list of model IDs",
    "ответ не в формате JSON": "response is not valid JSON",
    "сервер не ответил вовремя": "server timed out",
    "ошибка проверки TLS": "TLS verification failed",
    "ошибка подключения или заголовка запроса": "connection or request header error",
    "Не удалось загрузить модели. ": "Could not load models. ",
}

def tr(text):
    if LANGUAGE != "en":
        return text
    if text in TRANSLATIONS:
        return TRANSLATIONS[text]
    patterns = (
        (r"^(\d+) модел(?:ей|и|ь)$", lambda m: m[1] + (" model" if m[1] == "1" else " models")),
        (r"^Модели · (\d+)$", lambda m: "Models · " + m[1]),
        (r"^Выбрано: (\d+)$", lambda m: "Selected: " + m[1]),
        (r"^Модели (.+)$", lambda m: "Models " + m[1]),
        (r"^GET (.+) · (\d+) найдено$", lambda m: "GET " + m[1] + " · " + m[2] + " found"),
        (r"^Удалить (.+)$", lambda m: "Remove " + m[1]),
        (r"^Редактировать (.+)$", lambda m: "Edit " + m[1]),
        (r"^Свернуть модели (.+)$", lambda m: "Collapse models " + m[1]),
        (r"^Раскрыть модели (.+)$", lambda m: "Expand models " + m[1]),
        (r"^Ошибка JSON. Строка (\d+), столбец (\d+).$", lambda m: "JSON error. Line " + m[1] + ", column " + m[2] + "."),
        (r"^Переменная окружения «(.+)» не задана.$", lambda m: "Environment variable «" + m[1] + "» is not set."),
    )
    for pattern, convert in patterns:
        match = re.match(pattern, text, re.DOTALL)
        if match:
            return convert(match)
    return text

def translate_error(text):
    if LANGUAGE != "en":
        return text
    for source, target in TRANSLATIONS.items():
        text = text.replace(source, target)
    text = text.replace("Не удалось открыть ", "Could not open ").replace(
        "Не удалось сохранить конфиг.", "Could not save the configuration.")
    return tr(text)

def localize(widget):
    for item in [widget, *widget.findChildren(QWidget)]:
        if isinstance(item, (QLabel, QPushButton)) and not getattr(item, "_no_translation", False):
            current = item.text()
            original = getattr(item, "_translation_original", None)
            rendered = getattr(item, "_translation_rendered", None)
            if current != rendered:
                original = current
            item._translation_original = original
            item._translation_rendered = tr(original)
            item.setText(item._translation_rendered)
        if isinstance(item, QLineEdit):
            current = item.placeholderText()
            if current != getattr(item, "_placeholder_rendered", None):
                item._placeholder_original = current
            item._placeholder_rendered = tr(item._placeholder_original)
            item.setPlaceholderText(item._placeholder_rendered)
        for getter, setter, attr in (
            ("accessibleName", "setAccessibleName", "_accessible"),
            ("toolTip", "setToolTip", "_tooltip"),
        ):
            current = getattr(item, getter)()
            rendered = getattr(item, attr + "_rendered", None)
            if current != rendered:
                setattr(item, attr + "_original", current)
            original = getattr(item, attr + "_original", "")
            rendered = tr(original)
            setattr(item, attr + "_rendered", rendered)
            getattr(item, setter)(rendered)

STYLE = """
QWidget { color: #f7f7f7; }
QWidget#page, QMessageBox { background: #0d0d0d; }
QFrame#card, QFrame#editor, QFrame#picker, QFrame#empty, QFrame#modelRow {
    background: #141414; border: 1px solid #292929; border-radius: 23px;
}
QFrame#editor, QFrame#picker { border-color: #fafafa; }
QFrame#picker { background: #121212; border-radius: 28px; }
QFrame#empty { background: #0d0d0d; border: 1px dashed #585858; border-radius: 28px; }
QFrame#empty[dragging="true"] { background: #171717; border-color: #ededed; }
QFrame#modelRow { background: #0d0d0d; border-radius: 15px; }
QLabel#count {
    background: transparent; border: 1px solid #3e3e3e; border-radius: 13px;
    padding: 0px 13px;
}

QPushButton {
    background: #0d0d0d; color: #e6e6e6; border: 1px solid #424242;
    border-radius: 15px; padding: 0px 22px;
}
QPushButton:hover { background: #1d1d1d; border-color: #707070; }
QPushButton:pressed { background: #2a2a2a; }
QPushButton:focus { border-color: #a4a4a4; }
QPushButton:disabled { color: #828282; border-color: #333333; }
QPushButton[primary="true"] { background: #fdfdfd; color: #0d0d0d; border-color: #fdfdfd; }
QPushButton[primary="true"]:hover { background: #e4e4e4; }
QPushButton[primary="true"]:pressed { background: #cbcbcb; }
QPushButton[primary="true"]:focus { border: 2px solid #8c8c8c; }
QPushButton[primary="true"]:disabled {
    background: #484848; color: #aaa; border-color: #484848;
}
QPushButton#iconButton, QPushButton#smallIcon, QPushButton#emptyIcon {
    padding: 0px; border-radius: 12px;
}
QPushButton#smallIcon { border-radius: 10px; }
QPushButton#emptyIcon { border-radius: 21px; }
QPushButton[leadingIcon="true"] { padding-left: 49px; padding-right: 22px; }

QLineEdit {
    background: #0d0d0d; color: #f7f7f7; border: 1px solid #373737;
    border-radius: 15px; padding: 0px 17px; selection-background-color: #e1e1e1;
    selection-color: #0d0d0d; placeholder-text-color: #777;
    lineedit-password-character: 8226;
}
QLineEdit:focus { border-color: #686868; }
QScrollArea, QListWidget { background: transparent; border: 0; }
QWidget#cards, QWidget#modelList, QWidget#qt_scrollarea_viewport { background: transparent; }
QScrollBar:vertical { background: transparent; margin: 0; width: 7px; }
QScrollBar::handle:vertical { background: #484848; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #666; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("В конфиге есть повторяющийся ключ JSON.")
        result[key] = value
    return result


def invalid_constant(_value):
    raise ValueError("Конфиг содержит число, недопустимое в JSON.")


def parse_config(raw):
    source = raw.decode("utf-8-sig")
    # Заменяем комментарии пробелами, чтобы сохранить позиции ошибок JSON.
    string_token = r'"(?:[^"\\]|\\.)*"'
    source = re.sub(string_token + r"|//[^\r\n]*|/\*[\s\S]*?\*/",
                    lambda match: match[0] if match[0][0] == '"' else
                    re.sub(r"[^\r\n]", " ", match[0]), source)

    def trailing_comma(match):
        if match[0] != ",":
            return match[0]
        index = match.start() - 1
        while index >= 0 and source[index].isspace():
            index -= 1
        return " " if index >= 0 and source[index] not in "{[,:" else ","

    source = re.sub(string_token + r"|,(?=\s*[}\]])", trailing_comma, source)
    try:
        config = json.loads(source, object_pairs_hook=json_pairs, parse_constant=invalid_constant)
    except json.JSONDecodeError as error:
        raise ValueError(f"Ошибка JSON. Строка {error.lineno}, столбец {error.colno}.") from error
    if not isinstance(config, dict):
        raise ValueError("Корневое значение конфига должно быть объектом JSON.")
    providers = config.get("provider", {})
    if not isinstance(providers, dict):
        raise ValueError("Поле «provider» должно быть объектом JSON.")
    for provider in providers.values():
        if not isinstance(provider, dict) or any(
            not isinstance(provider.get(field, {}), dict) for field in ("options", "models")
        ):
            raise ValueError("Провайдер, его «options» и «models» должны быть объектами JSON.")
    return config


def save_config(path, expected, config):
    encoded = (json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path) + ".ocp.lock")
    if not lock.tryLock(0):
        raise OSError("Файл занят. Повторите сохранение через несколько секунд.")
    try:
        try:
            current = path.read_bytes()
        except FileNotFoundError:
            current = None
        if current != expected:
            raise OSError("Файл изменился на диске. Откройте его снова перед сохранением.")
        file = QSaveFile(str(path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(encoded) != len(encoded):
            file.cancelWriting()
            raise OSError(file.errorString())
        if not file.commit():
            raise OSError(file.errorString())
        return encoded
    finally:
        lock.unlock()


def provider_id(name, providers):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "provider"
    candidate, number = stem, 2
    while candidate in providers:
        candidate = f"{stem}-{number}"
        number += 1
    return candidate


def option_text(provider, key):
    value = provider.get("options", {}).get(key, "")
    return value if isinstance(value, str) else ""


def provider_name(provider, provider_key):
    value = provider.get("name")
    return value if isinstance(value, str) and value else provider_key


def resolve_config_value(value, config_path):
    def replace(match):
        kind, token = match.groups()
        if kind == "env":
            result = os.environ.get(token)
            if result is None:
                raise ValueError(f"Переменная окружения «{token}» не задана.")
            return result
        try:
            path = Path(token).expanduser()
            return (config_path.parent / path).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError, RuntimeError, ValueError) as error:
            raise ValueError("Не удалось прочитать значение из ссылки {file:…}.") from error

    return re.sub(r"\{(env|file):([^}]+)\}", replace, value).strip()


def split_base_url(url):
    try:
        parts = urlsplit(url)
        parts.port
        valid = (parts.scheme in ("http", "https") and parts.hostname
                 and parts.username is None and not parts.fragment
                 and not any(char.isspace() for char in url))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Укажите Base URL в формате http:// или https://.")
    return parts


def model_endpoints(url):
    parts = split_base_url(url)
    base = parts.path.rstrip("/")
    last = base.rsplit("/", 1)[-1].lower()
    if last == "models":
        paths = [base]
    elif re.fullmatch(r"v\d+[a-z]*\d*", last):
        paths = [f"{base}/models"]
    else:
        paths = [f"{base}/v1/models", f"{base}/models"]
    return [parts._replace(path=path).geturl() for path in paths]


def fetch_model_ids(base_url, api_key):
    headers = {"Accept": "application/json"}
    if api_key:
        if "\r" in api_key or "\n" in api_key:
            raise ValueError("API ключ должен быть одной строкой.")
        headers["Authorization"] = f"Bearer {api_key}"

    def apply_auth(request):
        request.headers.update(headers)
        return request

    failures = []
    with requests.Session() as session:
        for url in model_endpoints(base_url):
            try:
                with session.get(url, auth=apply_auth, timeout=(5, 12),
                                 allow_redirects=False) as response:
                    if not 200 <= response.status_code < 300:
                        failures.append(f"HTTP {response.status_code}")
                        continue
                    payload = response.json()
                    if isinstance(payload, dict):
                        payload = payload.get("data", payload.get("models"))
                    if isinstance(payload, list):
                        ids = {}
                        for item in payload:
                            model_id = item.get("id") if isinstance(item, dict) else item
                            if isinstance(model_id, str) and model_id.strip():
                                ids[model_id] = None
                        if ids or not payload:
                            parts = urlsplit(response.url)
                            return list(ids), urlunsplit(parts._replace(query=""))
                    failures.append("ответ не содержит список ID моделей")
            except (requests.exceptions.JSONDecodeError, RecursionError):
                failures.append("ответ не в формате JSON")
            except requests.exceptions.Timeout:
                failures.append("сервер не ответил вовремя")
            except requests.exceptions.SSLError:
                failures.append("ошибка проверки TLS")
            except (requests.RequestException, UnicodeError):
                failures.append("ошибка подключения или заголовка запроса")
    raise ValueError("Не удалось загрузить модели. " + ", ".join(dict.fromkeys(failures)) + ".")


def request_models(result, url, key):
    try:
        result.put((fetch_model_ids(url, key), None))
    except ValueError as error:
        result.put((None, str(error)))


def px(value):
    return max(1, round(value * UI_SCALE)) if value else 0


def scale_for(size, display_ratio):
    relative = min(size.width() / DESIGN_SIZE.width(), size.height() / DESIGN_SIZE.height())
    minimum = max(0.42, 0.68 / max(1, display_ratio))
    return round(max(minimum, min(relative, 1.5)), 2)


def apply_style(scale):
    global UI_SCALE
    UI_SCALE = scale
    QApplication.instance().setStyleSheet(
        re.sub(r"(\d+)px", lambda match: f"{px(int(match[1]))}px", STYLE)
    )


def set_metrics(owner, **metrics):
    owner._ocp_metrics = {**getattr(owner, "_ocp_metrics", {}), **metrics}
    for method, values in metrics.items():
        values = values if isinstance(values, tuple) else (values,)
        getattr(owner, method)(*(px(value) for value in values))


def add_space(layout, height):
    layout.addSpacing(px(height))
    if not hasattr(layout, "_ocp_spacers"):
        layout._ocp_spacers = []
    layout._ocp_spacers.append((layout.itemAt(layout.count() - 1).spacerItem(), height))


def font(size, weight=QFont.Weight.Normal, mono=False):
    value = QFont(MONO) if mono else QFont(QApplication.font())
    value.setPixelSize(px(size))
    value.setWeight(weight)
    return value


def set_text_font(widget, size, weight=QFont.Weight.Normal, mono=False):
    widget._ocp_font = size, weight, mono
    widget.setFont(font(size, weight, mono))


def label(text, size=15, bold=False, color=TEXT, mono=False, elide=False, translate=True):
    widget = ElideLabel(text) if elide else QLabel(text)
    widget._no_translation = not translate
    widget.setTextFormat(Qt.TextFormat.PlainText)
    set_text_font(widget, size, QFont.Weight.Bold if bold else QFont.Weight.Normal, mono)
    widget.setStyleSheet(f"color: {color};")
    return widget


class ElideLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        bounds = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, bounds.width())
        painter.drawText(bounds, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)


def row(parent=None, spacing=10):
    layout = QHBoxLayout(parent)
    set_metrics(layout, setContentsMargins=(0, 0, 0, 0), setSpacing=spacing)
    return layout


def column(parent=None, margins=(0, 0, 0, 0), spacing=0):
    layout = QVBoxLayout(parent)
    set_metrics(layout, setContentsMargins=margins, setSpacing=spacing)
    return layout


def frame(name):
    widget = QFrame()
    widget.setObjectName(name)
    return widget


def paint_icon(painter, center, icon, color):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(center)
    painter.scale(UI_SCALE, UI_SCALE)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    if icon == "plus":
        line(-6, 0, 6, 0)
        line(0, -6, 0, 6)
    elif icon == "close":
        line(-5, -5, 5, 5)
        line(-5, 5, 5, -5)
    else:
        tip = -2.5 if icon == "up" else 2.5
        line(-5, -tip, 0, tip)
        line(0, tip, 5, -tip)


class Button(QPushButton):
    def __init__(self, text, *, primary=False, icon="", size=None, width=None, name=None):
        super().__init__(text)
        self.symbol = icon
        self.primary = primary
        self.setProperty("primary", primary)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        set_text_font(self, 18, QFont.Weight.Medium if primary else QFont.Weight.DemiBold)
        if size is not None:
            set_metrics(self, setFixedSize=(size, size))
            self.setObjectName({35: "smallIcon", 73: "emptyIcon"}.get(size, "iconButton"))
        else:
            set_metrics(self, setFixedHeight=50)
            if icon:
                self.setProperty("leadingIcon", True)
            if width:
                set_metrics(self, setMinimumWidth=width)
        if name:
            self.setAccessibleName(name)
            if not text:
                self.setToolTip(name)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.symbol:
            painter = QPainter(self)
            x = self.width() / 2
            if self.text():
                x = (self.width() - self.fontMetrics().horizontalAdvance(self.text())) / 2 - px(11)
                x = max(px(22), x)
            color = "#0d0d0d" if self.primary else TEXT
            if not self.isEnabled():
                color = "#999999"
            paint_icon(painter, QPointF(x, self.height() / 2), self.symbol, color)


def entry(value="", placeholder="", name=""):
    widget = QLineEdit(value)
    set_metrics(widget, setFixedHeight=50)
    set_text_font(widget, 18)
    widget.setPlaceholderText(placeholder)
    widget.setAccessibleName(name or placeholder)
    widget.setAcceptDrops(False)
    return widget


def field(text, input_widget):
    layout = column(spacing=7)
    caption = label(text, color="#aaa")
    caption.setBuddy(input_widget)
    layout.addWidget(caption)
    layout.addWidget(input_widget)
    return layout


def action_row(model_id, remove):
    widget = frame("modelRow")
    set_metrics(widget, setFixedHeight=52)
    layout = row(widget)
    set_metrics(layout, setContentsMargins=(18, 0, 10, 0))
    layout.addWidget(label(model_id, 16, color="#e3e3e3", mono=True, elide=True, translate=False), 1)
    button = Button("", icon="close", size=35, name=f"Удалить {model_id}")
    button.clicked.connect(remove)
    layout.addWidget(button)
    return widget


def model_count(count):
    if 11 <= count % 100 <= 14:
        return f"{count} моделей"
    if count % 10 == 1:
        return f"{count} модель"
    return f"{count} модели" if count % 10 in (2, 3, 4) else f"{count} моделей"


class ModelScroll(QScrollArea):
    def __init__(self, content, max_rows, gap):
        super().__init__()
        self.max_rows = max_rows
        self.gap = gap
        self.visible_rows = 0
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.setObjectName("modelList")
        content.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setWidget(content)

    def set_row_count(self, count):
        self.visible_rows = min(count, self.max_rows)
        self.resize_rows()
        self.setVisible(count > 0)

    def resize_rows(self):
        height = self.visible_rows * px(52) + max(0, self.visible_rows - 1) * px(self.gap)
        self.setFixedHeight(height)


def provider_card(name, url, models, expanded, edit, toggle, remove):
    card = frame("card")
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    layout = column(card, (20, 18, 20, 16))
    header = row()
    heading = column(spacing=5)
    heading.addWidget(label(name, 20, bold=True, elide=True, translate=False))
    if url:
        heading.addWidget(label(url, 15, color="#999", mono=True, elide=True, translate=False))
    header.addLayout(heading, 1)
    count = label(model_count(len(models)), 14, color="#bdbdbd")
    count.setObjectName("count")
    count.setAlignment(ALIGN_CENTER)
    set_metrics(count, setMinimumWidth=99, setFixedHeight=27)
    header.addWidget(count)
    add_button = Button("", icon="plus", size=46, name=f"Редактировать {name}")
    add_button.clicked.connect(edit)
    header.addWidget(add_button)
    arrow = Button("", icon="up" if expanded else "down", size=45,
                   name=f"{'Свернуть' if expanded else 'Раскрыть'} модели {name}")
    arrow.clicked.connect(toggle)
    header.addWidget(arrow)
    layout.addLayout(header)
    if expanded and models:
        add_space(layout, 16)
        model_box = QWidget()
        model_layout = column(model_box, spacing=15)
        for model_id in models:
            model_layout.addWidget(action_row(model_id, lambda _, value=model_id: remove(value)))
        model_scroll = ModelScroll(model_box, max_rows=5, gap=15)
        layout.addWidget(model_scroll)
        model_scroll.set_row_count(len(models))
    return card


class ModelRowDelegate(QStyledItemDelegate):
    def sizeHint(self, _option, _index):
        return QSize(0, px(52) + px(10))

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -px(10) - 0.5)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QColor("#626262" if focused else "#292929"))
        painter.setBrush(QColor("#181818" if hovered else "#0d0d0d"))
        painter.drawRoundedRect(rect, px(15), px(15))

        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        side = px(25)
        check_rect = QRectF(rect.left() + px(18), rect.center().y() - side / 2, side, side)
        painter.setPen(QColor("#fdfdfd" if checked else "#626262"))
        painter.setBrush(QColor("#fdfdfd" if checked else "#0d0d0d"))
        painter.drawRoundedRect(check_rect, px(7), px(7))

        text_rect = rect.adjusted(px(58), 0, -px(14), 0)
        model_font = font(16, mono=True)
        text = QFontMetrics(model_font).elidedText(
            index.data(Qt.ItemDataRole.DisplayRole), Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.setFont(model_font)
        painter.setPen(QColor("#e3e3e3"))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            hit = option.rect.adjusted(0, 0, 0, -px(10))
            if not hit.contains(event.position().toPoint()):
                return False
            state = index.data(Qt.ItemDataRole.CheckStateRole)
            next_state = (Qt.CheckState.Unchecked if state == Qt.CheckState.Checked.value
                          else Qt.CheckState.Checked)
            return model.setData(index, next_state.value, Qt.ItemDataRole.CheckStateRole)
        return super().editorEvent(event, model, option, index)


class ModelPicker(QDialog):
    def __init__(self, parent, name, model_ids, endpoint):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(f"Модели {name}")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        surface = frame("picker")
        column(self).addWidget(surface)
        body = column(surface, (28, 27, 28, 27))

        header = row()
        heading = column(spacing=5)
        heading.addWidget(label(f"Модели {name}", 23, bold=True, elide=True))
        heading.addWidget(label(f"GET {endpoint} · {len(model_ids)} найдено",
                                color="#999", mono=True, elide=True))
        header.addLayout(heading, 1)
        close = Button("", icon="close", size=45, name="Закрыть список моделей")
        close.clicked.connect(self.reject)
        header.addWidget(close)
        body.addLayout(header)
        add_space(body, 18)
        self.search = entry(placeholder="Поиск по ID модели")
        body.addWidget(self.search)
        add_space(body, 18)

        self.results = QListWidget()
        self.results.setAccessibleName("Модели на сервере")
        self.results.setItemDelegate(ModelRowDelegate(self.results))
        self.results.setUniformItemSizes(True)
        self.results.setMouseTracking(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.items = []
        for model_id in model_ids:
            item = QListWidgetItem(model_id)
            item.setToolTip(model_id)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.results.addItem(item)
            self.items.append(item)
        self.no_results = label("", color="#999")
        self.no_results.setAlignment(ALIGN_CENTER)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.results)
        self.list_stack.addWidget(self.no_results)
        body.addWidget(self.list_stack, 1)
        add_space(body, 5)

        footer = row()
        self.count = label("", color="#999")
        footer.addWidget(self.count, 1)
        self.select_all = Button("Все", width=79, name="Выбрать все видимые модели")
        self.select_all.clicked.connect(self.toggle_visible)
        footer.addWidget(self.select_all)
        self.add_selected = Button("Добавить выбранные", primary=True, width=236)
        self.add_selected.clicked.connect(self.accept)
        footer.addWidget(self.add_selected)
        body.addLayout(footer)

        self.selected = set()
        self.search.textChanged.connect(self.filter)
        self.results.itemChanged.connect(self.selection_changed)
        self.filter("")
        localize(self)
        self.search.setFocus()

    def fit_in_window(self):
        page = self.parentWidget().page
        width = min(px(824), page.width() - px(72))
        height = min(px(560), page.height() - px(46))
        self.resize(width, height)
        offset = QPoint((page.width() - self.width()) // 2,
                        max(px(12), (page.height() - self.height()) // 2 - px(24)))
        self.move(page.mapToGlobal(offset))
        self.results.doItemsLayout()

    def filter(self, text):
        query = text.strip().casefold()
        self.visible = []
        for item in self.items:
            match = query in item.text().casefold()
            item.setHidden(not match)
            if match:
                self.visible.append(item)
        self.no_results.setText(tr("Поиск не дал результатов" if self.items else "На сервере пока нет моделей"))
        self.list_stack.setCurrentWidget(self.results if self.visible else self.no_results)
        self.results.scrollToTop()
        self.update_actions()

    def selection_changed(self, item):
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(item.text())
        else:
            self.selected.discard(item.text())
        self.update_actions()

    def update_actions(self):
        self.count.setText(tr(f"Выбрано: {len(self.selected)}"))
        self.select_all.setEnabled(bool(self.visible))
        self.add_selected.setEnabled(bool(self.selected))

    def toggle_visible(self):
        remove = all(item.text() in self.selected for item in self.visible)
        state = Qt.CheckState.Unchecked if remove else Qt.CheckState.Checked
        self.results.blockSignals(True)
        try:
            for item in self.visible:
                item.setCheckState(state)
                if remove:
                    self.selected.discard(item.text())
                else:
                    self.selected.add(item.text())
        finally:
            self.results.blockSignals(False)
        self.update_actions()

    def chosen(self):
        return [item.text() for item in self.items if item.text() in self.selected]


class ProviderEditor(QFrame):
    def __init__(self, window, provider_key, provider):
        super().__init__()
        self.setObjectName("editor")
        self.window = window
        self.provider_key = provider_key
        self.original = provider
        self.models = deepcopy(provider.get("models", {}))
        self.name = entry(provider_name(provider, provider_key or ""), "Например, OpenRouter",
                          "Название провайдера")
        self.api_key = entry(option_text(provider, "apiKey"), "", "API ключ")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_url = entry(option_text(provider, "baseURL"), "https://api.example.com/v1", "Base URL")
        self.model_id = entry(placeholder="Model ID")
        self.initial_fields = self.fields()
        self.fetch_result = None

        body = column(self, (20, 17, 20, 18), 15)
        body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        names = row(spacing=15)
        names.addLayout(field("Название провайдера", self.name), 1)
        names.addLayout(field("API ключ", self.api_key), 1)
        body.addLayout(names)
        body.addLayout(field("Base URL", self.base_url))

        heading = row()
        self.model_title = label("", 20, bold=True)
        heading.addWidget(self.model_title, 1)
        self.fetch_button = Button("Подгрузить с сервера", width=239)
        self.fetch_button.clicked.connect(self.load_models)
        heading.addWidget(self.fetch_button)
        body.addLayout(heading)

        manual = row(spacing=15)
        manual.addWidget(self.model_id, 1)
        add_model = Button("Модель", primary=True, icon="plus", width=144)
        add_model.clicked.connect(self.add_manual)
        self.model_id.returnPressed.connect(self.add_manual)
        manual.addWidget(add_model)
        body.addLayout(manual)

        self.model_box = QWidget()
        self.model_grid = QGridLayout(self.model_box)
        set_metrics(self.model_grid, setContentsMargins=(0, 0, 0, 0),
                    setHorizontalSpacing=11, setVerticalSpacing=10)
        self.model_grid.setColumnStretch(0, 1)
        self.model_grid.setColumnStretch(1, 1)
        self.model_scroll = ModelScroll(self.model_box, max_rows=3, gap=10)
        body.addWidget(self.model_scroll)

        actions = row()
        actions.addStretch()
        cancel = Button("Отмена", width=114)
        cancel.clicked.connect(window.discard_editor)
        actions.addWidget(cancel)
        save = Button("Сохранить", primary=True, width=140)
        save.clicked.connect(window.save_provider)
        actions.addWidget(save)
        body.addLayout(actions)

        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.on_request_finished)
        self.refresh_models()

    def fields(self):
        return self.name.text(), self.api_key.text(), self.base_url.text()

    def is_dirty(self):
        return (self.fields() != self.initial_fields or bool(self.model_id.text().strip())
                or self.models != self.original.get("models", {}))

    def add_manual(self):
        model_id = self.model_id.text().strip()
        if not model_id:
            self.model_id.setFocus()
            return
        if model_id in self.models:
            self.window.show_error("Эта модель уже добавлена.")
            return
        self.add_models([model_id])
        self.model_id.clear()
        self.model_id.setFocus()

    def add_models(self, model_ids):
        for model_id in model_ids:
            self.models.setdefault(model_id, {"name": model_id})
        self.refresh_models()

    def remove_model(self, model_id):
        del self.models[model_id]
        self.refresh_models()

    def refresh_models(self):
        self.model_title.setText(f"Модели · {len(self.models)}")
        while self.model_grid.count():
            widget = self.model_grid.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        for index, model_id in enumerate(self.models):
            widget = action_row(model_id, lambda _, value=model_id: self.remove_model(value))
            self.model_grid.addWidget(widget, index // 2, index % 2)
        self.model_scroll.set_row_count((len(self.models) + 1) // 2)
        localize(self)

    def load_models(self):
        try:
            path = self.window.path or DEFAULT_PATH
            url = resolve_config_value(self.base_url.text(), path)
            key = resolve_config_value(self.api_key.text(), path)
            split_base_url(url)
        except ValueError as error:
            self.window.show_error(str(error))
            return

        self.fetch_result = SimpleQueue()
        self.fetch_button.setEnabled(False)
        self.fetch_button.setText("Загрузка…")
        localize(self)
        for input_widget in (self.base_url, self.api_key):
            input_widget.setReadOnly(True)
        Thread(target=request_models, args=(self.fetch_result, url, key), daemon=True).start()
        self.timer.start()

    def on_request_finished(self):
        try:
            result, error = self.fetch_result.get_nowait()
        except Empty:
            return
        self.timer.stop()
        self.fetch_result = None
        self.fetch_button.setText("Подгрузить с сервера")
        localize(self)
        self.fetch_button.setEnabled(True)
        for input_widget in (self.base_url, self.api_key):
            input_widget.setReadOnly(False)
        if error:
            self.window.show_error(error)
        else:
            self.window.pick_models(self, *result)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry()
        fit = min(1, max(1, available.width() - 40) / DESIGN_SIZE.width(),
                  max(1, available.height() - 56) / DESIGN_SIZE.height())
        initial = DESIGN_SIZE * fit
        self.setMinimumSize(min(600, initial.width()), min(420, initial.height()))
        self.resize(initial)
        self.move(available.center() - QPoint(self.width() // 2, (self.height() + 24) // 2))
        apply_style(scale_for(self.size(), screen.devicePixelRatio()))

        global LANGUAGE
        LANGUAGE = QSettings("OCP", "OCP").value("language", "ru")
        if LANGUAGE not in ("ru", "en"):
            LANGUAGE = "ru"
        self.path = None
        self.original_bytes = None
        self.config = {"$schema": SCHEMA}
        self.expanded_key = None
        self.card_model_scroll = None
        self.editor = None

        self.page = QWidget()
        self.page.setObjectName("page")
        self.page.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCentralWidget(self.page)
        body = column(self.page, (36, 35, 36, 0), 23)

        header = row()
        file_info = column(spacing=6)
        file_info.addWidget(label("opencode.json", 26, bold=True))
        self.path_label = label("Файл не найден по пути по умолчанию", 15,
                                color="#aaa", mono=True, elide=True)
        file_info.addWidget(self.path_label)
        header.addLayout(file_info, 1)
        self.language_button = Button("EN" if LANGUAGE == "ru" else "RU", width=65)
        self.language_button.setAccessibleName("Switch language" if LANGUAGE == "ru" else "Сменить язык")
        self.language_button.clicked.connect(self.switch_language)
        header.addWidget(self.language_button)
        self.choose_button = Button("Указать", primary=True, width=115)
        self.choose_button.clicked.connect(self.choose_config)
        header.addWidget(self.choose_button)
        self.add_button = Button("Провайдер", primary=True, icon="plus", width=174)
        self.add_button.clicked.connect(lambda: self.open_editor())
        header.addWidget(self.add_button)
        body.addLayout(header)

        self.content = QStackedWidget()
        self.empty = self.empty_state()
        empty_page = QWidget()
        column(empty_page, (0, 0, 0, 36)).addWidget(self.empty)
        self.content.addWidget(empty_page)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_widget = QWidget()
        list_widget.setObjectName("cards")
        self.list_layout = column(list_widget, (0, 0, 0, 36), 22)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.scroll.setWidget(list_widget)
        self.content.addWidget(self.scroll)
        body.addWidget(self.content, 1)

        self.shade = QWidget(self.page)
        self.shade.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.shade.setStyleSheet("background-color: rgba(0, 0, 0, 166);")
        self.shade.hide()

        self.scale_timer = QTimer(self, interval=40, singleShot=True)
        self.scale_timer.timeout.connect(self.update_scale)
        self.refresh()
        self.open_config(DEFAULT_PATH, startup=True)
        localize(self)

    def switch_language(self):
        global LANGUAGE
        LANGUAGE = "en" if LANGUAGE == "ru" else "ru"
        QSettings("OCP", "OCP").setValue("language", LANGUAGE)
        self.language_button.setText("RU" if LANGUAGE == "en" else "EN")
        self.language_button.setAccessibleName("Сменить язык" if LANGUAGE == "en" else "Switch language")
        localize(self)
        self.language_button.setText("RU" if LANGUAGE == "en" else "EN")
        self.language_button.setAccessibleName("Сменить язык" if LANGUAGE == "en" else "Switch language")
        self.refresh(keep_scroll=True)

    @property
    def providers(self):
        return self.config.get("provider", {})

    def empty_state(self):
        empty = frame("empty")
        layout = column(empty)
        layout.addStretch()
        mark = Button("", icon="plus", size=73, name="Добавить провайдера")
        mark.clicked.connect(lambda: self.open_editor())
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        add_space(layout, 16)
        title = label("Провайдеров пока нет", 23, bold=True)
        title.setAlignment(ALIGN_CENTER)
        layout.addWidget(title)
        add_space(layout, 17)
        text = label("Добавьте первого провайдера или перетащите сюда\nфайл opencode.json",
                     16, color="#999")
        text.setAlignment(ALIGN_CENTER)
        layout.addWidget(text)
        add_space(layout, 18)
        add = Button("Провайдер", primary=True, icon="plus", width=174)
        add.clicked.connect(lambda: self.open_editor())
        layout.addWidget(add, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return empty

    def show_error(self, message):
        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, translate_error(message), parent=self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        button = box.addButton(tr("Закрыть"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(button)
        box.exec()

    def confirm_discard(self):
        if not self.editor or not self.editor.is_dirty():
            return True
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME,
                          tr("Сбросить несохранённые изменения провайдера?"), parent=self)
        discard = box.addButton(tr("Сбросить"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(tr("Продолжить редактирование"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() == discard

    def choose_config(self):
        start = self.path or DEFAULT_PATH
        initial = str(start) if start.parent.is_dir() else str(Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self, tr("Открыть конфиг OpenCode"), initial, tr("Конфиги OpenCode (*.json *.jsonc)")
        )
        if selected:
            self.open_config(Path(selected))

    def open_config(self, path, *, startup=False):
        try:
            path = path.resolve()
            raw = path.read_bytes()
            config = parse_config(raw)
        except (OSError, ValueError, RuntimeError) as error:
            if startup and isinstance(error, FileNotFoundError):
                return
            message = f"Не удалось открыть {path.name}.\n{error}"
            if startup:
                self.path_label.setText("Не удалось открыть файл по пути по умолчанию")
                QTimer.singleShot(0, lambda: self.show_error(message))
            else:
                self.show_error(message)
            return
        if not self.confirm_discard():
            return
        self.clear_editor()
        self.path, self.original_bytes, self.config = path, raw, config
        self.path_label._no_translation = True
        self.path_label.setText(str(path))
        self.expanded_key = next(iter(self.providers), None)
        self.refresh()

    def open_editor(self, provider_key=None):
        if self.editor and self.editor.provider_key == provider_key:
            self.scroll.verticalScrollBar().setValue(0)
            self.editor.name.setFocus()
            return
        if not self.confirm_discard():
            return
        self.clear_editor()
        provider = self.providers.get(provider_key, {})
        self.editor = ProviderEditor(self, provider_key, provider)
        self.expanded_key = None
        self.refresh()
        self.scroll.verticalScrollBar().setValue(0)
        (self.editor.model_id if provider_key is not None else self.editor.name).setFocus()

    def clear_editor(self):
        if self.editor is not None:
            self.editor.timer.stop()
            self.editor.hide()
            self.list_layout.removeWidget(self.editor)
            self.editor.deleteLater()
            self.editor = None

    def discard_editor(self):
        self.clear_editor()
        self.refresh()

    def save_provider(self):
        editor = self.editor
        name, api_key, base_url = (value.strip() for value in editor.fields())
        if not name:
            self.show_error("Укажите название провайдера.")
            editor.name.setFocus()
            return
        if base_url != editor.initial_fields[2] or editor.provider_key is None:
            try:
                if base_url or editor.provider_key is None:
                    # Ссылки разрешаются при запросе, чтобы конфиг оставался переносимым.
                    if not re.search(r"\{(?:env|file):[^}]+\}", base_url):
                        split_base_url(base_url)
            except ValueError as error:
                self.show_error(str(error))
                editor.base_url.setFocus()
                return

        config = deepcopy(self.config)
        providers = config.setdefault("provider", {})
        key = editor.provider_key
        if key is None:
            key = provider_id(name, providers)
            providers[key] = {"npm": "@ai-sdk/openai-compatible", "name": name, "models": {}}
        provider = providers[key]
        if name != editor.initial_fields[0]:
            provider["name"] = name
        for option, value, initial in (
            ("apiKey", api_key, editor.initial_fields[1]),
            ("baseURL", base_url, editor.initial_fields[2]),
        ):
            if value != initial:
                if value:
                    provider.setdefault("options", {})[option] = value
                elif "options" in provider:
                    provider["options"].pop(option, None)
        models = deepcopy(editor.models)
        pending_id = editor.model_id.text().strip()
        if pending_id:
            models.setdefault(pending_id, {"name": pending_id})
        if models != provider.get("models", {}):
            provider["models"] = models

        if config != self.config and not self.persist(config):
            return
        self.expanded_key = key
        self.clear_editor()
        self.refresh()

    def persist(self, config):
        try:
            path = self.path or DEFAULT_PATH.resolve()
            encoded = save_config(path, self.original_bytes, config)
        except (OSError, ValueError, RuntimeError) as error:
            self.show_error(f"Не удалось сохранить конфиг.\n{error}")
            return False
        self.path, self.original_bytes, self.config = path, encoded, config
        self.path_label._no_translation = True
        self.path_label.setText(str(path))
        return True

    def remove_model(self, provider_key, model_id):
        config = deepcopy(self.config)
        del config["provider"][provider_key]["models"][model_id]
        if self.persist(config):
            self.refresh(keep_scroll=True)

    def toggle_card(self, provider_key):
        self.expanded_key = None if self.expanded_key == provider_key else provider_key
        self.refresh(keep_scroll=True)

    def refresh(self, *, keep_scroll=False, preview=False):
        vertical = self.scroll.verticalScrollBar()
        position = vertical.value() if keep_scroll else 0
        model_position = 0
        if keep_scroll and self.card_model_scroll is not None:
            key, model_scroll = self.card_model_scroll
            if key == self.expanded_key:
                model_position = model_scroll.verticalScrollBar().value()
        self.card_model_scroll = None
        while self.list_layout.count():
            widget = self.list_layout.takeAt(0).widget()
            widget.hide()
            if widget is not self.editor:
                widget.deleteLater()

        editing_key = self.editor.provider_key if self.editor else None
        if self.editor:
            if preview:
                editor = self.editor
                name, _, url = editor.fields()
                draft = provider_card(name.strip() or "Новый провайдер", url, editor.models, False,
                                      lambda: None, lambda: None, lambda _: None)
                self.list_layout.addWidget(draft)
            else:
                self.list_layout.addWidget(self.editor)
                self.editor.show()

        for key, provider in self.providers.items():
            if key == editing_key:
                continue
            expanded = not preview and key == self.expanded_key
            card = provider_card(
                provider_name(provider, key), option_text(provider, "baseURL"),
                provider.get("models", {}), expanded,
                lambda _, value=key: self.open_editor(value),
                lambda _, value=key: self.toggle_card(value),
                lambda model, value=key: self.remove_model(value, model),
            )
            self.list_layout.addWidget(card)
            if expanded and (model_scroll := card.findChild(ModelScroll)) is not None:
                self.card_model_scroll = key, model_scroll

        show_list = bool(self.providers) or self.editor is not None
        self.add_button.setVisible(show_list)
        self.choose_button.setProperty("primary", not show_list)
        self.choose_button.primary = not show_list
        set_text_font(self.choose_button, 18,
                      QFont.Weight.DemiBold if show_list else QFont.Weight.Medium)
        self.choose_button.style().unpolish(self.choose_button)
        self.choose_button.style().polish(self.choose_button)
        self.content.setCurrentIndex(1 if show_list else 0)
        localize(self)
        self.list_layout.activate()
        vertical.setValue(position)
        if model_position and self.card_model_scroll is not None:
            current = self.card_model_scroll
            QTimer.singleShot(0, lambda: self.restore_model_scroll(current, model_position))

    def restore_model_scroll(self, current, position):
        if self.card_model_scroll == current:
            current[1].verticalScrollBar().setValue(position)

    def pick_models(self, editor, ids, endpoint):
        if self.editor is not editor:
            return
        position = self.scroll.verticalScrollBar().value()
        self.refresh(preview=True)
        self.shade.setGeometry(self.page.rect())
        self.shade.raise_()
        self.shade.show()
        picker = ModelPicker(self, editor.name.text().strip() or "провайдера", ids, endpoint)
        picker.fit_in_window()
        accepted = picker.exec() == QDialog.DialogCode.Accepted
        self.shade.hide()
        if accepted:
            editor.add_models(picker.chosen())
        picker.deleteLater()
        self.refresh()
        self.scroll.verticalScrollBar().setValue(position)
        editor.fetch_button.setFocus()

    def drop_path(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() in CONFIG_SUFFIXES:
                return path
        return None

    def set_dragging(self, dragging):
        self.empty.setProperty("dragging", dragging)
        self.empty.style().unpolish(self.empty)
        self.empty.style().polish(self.empty)
        self.empty.update()

    def dragEnterEvent(self, event):
        if self.drop_path(event):
            event.acceptProposedAction()
            self.set_dragging(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.set_dragging(False)
        event.accept()

    def dropEvent(self, event):
        self.set_dragging(False)
        path = self.drop_path(event)
        if path:
            event.acceptProposedAction()
            self.open_config(path)
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scale_timer"):
            self.shade.setGeometry(self.page.rect())
            self.scale_timer.start()

    def event(self, event):
        handled = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, "scale_timer"):
            self.scale_timer.start()
        return handled

    def update_scale(self):
        scale = scale_for(self.page.size(), self.devicePixelRatioF())
        if scale == UI_SCALE:
            return
        self.setUpdatesEnabled(False)
        try:
            apply_style(scale)
            items = self.findChildren(QObject)
            layouts = []
            for item in reversed(items):
                if hasattr(item, "_ocp_metrics"):
                    set_metrics(item, **item._ocp_metrics)
                if hasattr(item, "_ocp_font"):
                    set_text_font(item, *item._ocp_font)
                if hasattr(item, "_ocp_spacers"):
                    for spacer, height in item._ocp_spacers:
                        spacer.changeSize(0, px(height), QSizePolicy.Policy.Minimum,
                                          QSizePolicy.Policy.Fixed)
                if isinstance(item, ModelScroll):
                    item.resize_rows()
                if isinstance(item, QLayout):
                    item.invalidate()
                    if isinstance(item.parent(), QWidget):
                        layouts.append(item)
            for layout in layouts:
                layout.activate()
            picker = QApplication.activeModalWidget()
            if isinstance(picker, ModelPicker):
                picker.fit_in_window()
        finally:
            self.setUpdatesEnabled(True)

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def app_icon():
    data = QByteArray(b64decode(ICON_ICO))
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, b"ico")
    icon = QIcon()
    for index in range(reader.imageCount()):
        if reader.jumpToImage(index):
            image = reader.read()
            if not image.isNull():
                icon.addPixmap(QPixmap.fromImage(image))
    return icon


def main():
    global MONO
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    families = set(QFontDatabase.families())
    for family in ("Inter", "Segoe UI", "Arial", "DejaVu Sans"):
        if family in families:
            app.setFont(QFont(family))
            break
    MONO = next((name for name in ("JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono")
                 if name in families), QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family())
    window = MainWindow()
    window.show()
    return app.exec()


# Многоразмерная иконка приложения для Qt и ресурса Windows EXE.
ICON_ICO = (
    b"AAABAAoAEBAAAAEAIABoBAAApgAAABQUAAABACAAuAYAAA4FAAAYGAAAAQAgAIgJAADGCwAAICAAAAEA"
    b"IACoEAAAThUAACgoAAABACAAaBoAAPYlAAAwMAAAAQAgAKglAABeQAAAQEAAAAEAIACtCAAABmYAAGBg"
    b"AAABACAAaw0AALNuAACAgAAAAQAgAHQRAAAefAAAAAAAAAEAIAAzJQAAko0AACgAAAAQAAAAIAAAAAEA"
    b"IAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASUlJByQkJGInJyeYJiYmnyYmJp8mJiafJiYmnyYm"
    b"Jp8mJiafJiYmnyYmJp8nJyeYJSUlYSoqKgYAAAAASUlJByIiIrwZGRn/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xkZGf8iIiK8KioqBiQkJGIZGRn/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/GRkZ/yUlJWEnJyeYFBQU/xQUFP8UFBT/FBQU/2Zm"
    b"Zv+ysrL/LCws/ywsLP+ysrL/ZmZm/xQUFP8UFBT/FBQU/xQUFP8nJyeYJiYmnxQUFP8UFBT/FBQU/zs7"
    b"O//09PT/enp6/xoaGv8aGhr/enp6//T09P87Ozv/FBQU/xQUFP8UFBT/JiYmnyYmJp8UFBT/FBQU/xQU"
    b"FP9oaGj/x8fH/xQUFP8UFBT/FBQU/xQUFP/IyMj/Z2dn/xQUFP8UFBT/FBQU/yYmJp8mJiafFBQU/xQU"
    b"FP8UFBT/dnZ2/7W1tf8UFBT/FBQU/xQUFP8UFBT/tbW1/3V1df8UFBT/FBQU/xQUFP8mJiafJiYmnxQU"
    b"FP8UFBT/SUlJ//r6+v9/f3//FBQU/1RUVP9UVFT/FBQU/4CAgP/6+vr/SUlJ/xQUFP8UFBT/JiYmnyYm"
    b"Jp8UFBT/FBQU/0lJSf/6+vr/f39//xQUFP9UVFT/VFRU/xQUFP+AgID/+vr6/0lJSf8UFBT/FBQU/yYm"
    b"Jp8mJiafFBQU/xQUFP8UFBT/dnZ2/7W1tf8UFBT/FBQU/xQUFP8UFBT/tbW1/3V1df8UFBT/FBQU/xQU"
    b"FP8mJiafJiYmnxQUFP8UFBT/FBQU/2hoaP/Hx8f/FBQU/xQUFP8UFBT/FBQU/8jIyP9nZ2f/FBQU/xQU"
    b"FP8UFBT/JiYmnyYmJp8UFBT/FBQU/xQUFP87Ozv/9PT0/3l5ef8aGhr/Ghoa/3l5ef/09PT/Ozs7/xQU"
    b"FP8UFBT/FBQU/yYmJp8nJyeYFBQU/xQUFP8UFBT/FBQU/2ZmZv+ysrL/LCws/ywsLP+ysrL/ZmZm/xQU"
    b"FP8UFBT/FBQU/xQUFP8nJyeYJCQkYhkZGf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8ZGRn/JCQkYkBAQAgiIiK8GRkZ/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8ZGRn/IiIivElJSQcAAAAAQEBACCQkJGInJyeYJiYmnyYmJp8mJiafJiYmnyYm"
    b"Jp8mJiafJiYmnyYmJp8nJyeYJCQkYklJSQcAAAAAgAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAEAACgAAAAUAAAAKAAAAAEAIAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAADk5ORsuLi5eKioqhiwsLIwsLCyMLCwsjCwsLIwsLCyMLCwsjCws"
    b"LIwsLCyMLCwsjCwsLIwqKiqGLi4uXjs7OxoAAAAAAAAAAAAAAAAqKio3ISEh1hgYGP8WFhb/FRUV/xUV"
    b"Ff8VFRX/FRUV/xUVFf8VFRX/FRUV/xUVFf8VFRX/FRUV/xYWFv8YGBj/IiIi1SoqKjYAAAAAQEBAHCEh"
    b"IdYUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/ISEh1js7OxotLS1gGBgY/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8YGBj/Li4uXioqKoYXFxf/FBQU/xQUFP8UFBT/FBQU/0VF"
    b"Rf/BwcH/0tLS/xcXF/8XFxf/0tLS/8HBwf9FRUX/FBQU/xQUFP8UFBT/FBQU/xYWFv8qKiqGKioqixYW"
    b"Fv8UFBT/FBQU/xQUFP8aGhr/4+Pj/9XV1f9ubm7/FBQU/xQUFP9ubm7/1dXV/+Pj4/8aGhr/FBQU/xQU"
    b"FP8UFBT/FRUV/ywsLIwqKiqLFhYW/xQUFP8UFBT/FBQU/zw8PP/6+vr/VVVV/xQUFP8UFBT/FBQU/xQU"
    b"FP9VVVX/+vr6/zs7O/8UFBT/FBQU/xQUFP8VFRX/LCwsjCoqKosWFhb/FBQU/xQUFP8UFBT/SEhI//r6"
    b"+v8/Pz//FBQU/xQUFP8UFBT/FBQU/z8/P//6+vr/SEhI/xQUFP8UFBT/FBQU/xUVFf8sLCyMKioqixYW"
    b"Fv8UFBT/FBQU/xQUFP9iYmL/+vr6/zAwMP8UFBT/FBQU/xQUFP8UFBT/MDAw//r6+v9hYWH/FBQU/xQU"
    b"FP8UFBT/FRUV/ywsLIwqKiqLFhYW/xQUFP8UFBT/Z2dn//r6+v/o6Oj/FhYW/xQUFP93d3f/d3d3/xQU"
    b"FP8WFhb/6Ojo//r6+v9nZ2f/FBQU/xQUFP8VFRX/LCwsjCoqKosWFhb/FBQU/xQUFP9nZ2f/+vr6/+jo"
    b"6P8WFhb/FBQU/3d3d/93d3f/FBQU/xYWFv/o6Oj/+vr6/2dnZ/8UFBT/FBQU/xUVFf8sLCyMKioqixYW"
    b"Fv8UFBT/FBQU/xQUFP9iYmL/+vr6/zAwMP8UFBT/FBQU/xQUFP8UFBT/MDAw//r6+v9hYWH/FBQU/xQU"
    b"FP8UFBT/FRUV/ywsLIwqKiqLFhYW/xQUFP8UFBT/FBQU/0hISP/6+vr/Pz8//xQUFP8UFBT/FBQU/xQU"
    b"FP8/Pz//+vr6/0hISP8UFBT/FBQU/xQUFP8VFRX/LCwsjCoqKosWFhb/FBQU/xQUFP8UFBT/PDw8//r6"
    b"+v9VVVX/FBQU/xQUFP8UFBT/FBQU/1VVVf/6+vr/Ozs7/xQUFP8UFBT/FBQU/xUVFf8sLCyMKioqixYW"
    b"Fv8UFBT/FBQU/xQUFP8aGhr/4+Pj/9TU1P9ubm7/FBQU/xQUFP9ubm7/1NTU/+Pj4/8aGhr/FBQU/xQU"
    b"FP8UFBT/FRUV/ywsLIwqKiqGFxcX/xQUFP8UFBT/FBQU/xQUFP9FRUX/wcHB/9LS0v8XFxf/FxcX/9LS"
    b"0v/BwcH/RUVF/xQUFP8UFBT/FBQU/xQUFP8WFhb/Kioqhi0tLWAYGBj/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xgYGP8uLi5eQkJCGyAg"
    b"INYUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/IiIi1Tk5ORsAAAAAMTExOSAgINYYGBj/FxcX/xYWFv8WFhb/FhYW/xYWFv8WFhb/FhYW/xYW"
    b"Fv8WFhb/FhYW/xYWFv8XFxf/GBgY/yIiItUqKio3AAAAAAAAAAAAAAAAQEBAHC0tLWAqKiqGKioqiyoq"
    b"KosqKiqLKioqiyoqKosqKiqLKioqiyoqKosqKiqLKioqiyoqKoYtLS1gQkJCGwAAAAAAAAAAwAAwAIAA"
    b"EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAgAAQAMAAMAAoAAAAGAAAADAAAAABACAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAR0dHJDY2NkwxMTFzMDAwdjAwMHYwMDB2MDAwdjAwMHYwMDB2MDAwdjAwMHYwMDB2MDAwdjAw"
    b"MHYwMDB2MTExczY2NkxJSUkjAAAAAAAAAAAAAAAAAAAAAAAAAAAuLi5uHx8f3xsbG/8YGBj/GBgY/xgY"
    b"GP8YGBj/GBgY/xgYGP8YGBj/GBgY/xgYGP8YGBj/GBgY/xgYGP8YGBj/GBgY/xsbG/8fHx/eMDAwawAA"
    b"AAAAAAAAAAAAAC8vL20cHBz+FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/HBwc/i8vL2wAAAAARUVFJR8fH94UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/x8fH95JSUkjNTU1TRoaGv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/HR0d/xoa"
    b"Gv8UFBT/FBQU/xoaGv8dHR3/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xsbG/82NjZMLy8vchkZ"
    b"Gf8UFBT/FBQU/xQUFP8UFBT/FBQU/ykpKf+3t7f/+Pj4/729vf8UFBT/FBQU/76+vv/4+Pj/t7e3/ykp"
    b"Kf8UFBT/FBQU/xQUFP8UFBT/FBQU/xgYGP8xMTFzMDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/FBQU/62t"
    b"rf/6+vr/sLCw/1lZWf8UFBT/FBQU/1lZWf+wsLD/+vr6/6ysrP8UFBT/FBQU/xQUFP8UFBT/FBQU/xgY"
    b"GP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/FhYW//Hx8f+9vb3/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/vr6+//Dw8P8WFhb/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQU"
    b"FP8UFBT/IyMj//r6+v+lpaX/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/paWl//r6+v8jIyP/FBQU/xQU"
    b"FP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/KCgo//r6+v+ioqL/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/oqKi//r6+v8oKCj/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgY"
    b"GP8UFBT/FBQU/xQUFP8UFBT/W1tb//r6+v+Hh4f/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/iIiI//r6"
    b"+v9bW1v/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP+MjIz/+vr6//r6"
    b"+v86Ojr/FBQU/xQUFP+jo6P/o6Oj/xQUFP8UFBT/Ozs7//r6+v/6+vr/jIyM/xQUFP8UFBT/FBQU/xgY"
    b"GP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP+MjIz/+vr6//r6+v86Ojr/FBQU/xQUFP+jo6P/o6Oj/xQU"
    b"FP8UFBT/Ozs7//r6+v/6+vr/jIyM/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQU"
    b"FP8UFBT/W1tb//r6+v+Hh4f/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/iIiI//r6+v9bW1v/FBQU/xQU"
    b"FP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/KCgo//r6+v+ioqL/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/oqKi//r6+v8oKCj/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgY"
    b"GP8UFBT/FBQU/xQUFP8UFBT/IyMj//r6+v+lpaX/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/paWl//r6"
    b"+v8jIyP/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/FhYW//Hx"
    b"8f+9vb3/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/vr6+//Hx8f8WFhb/FBQU/xQUFP8UFBT/FBQU/xgY"
    b"GP8wMDB2MDAwdRgYGP8UFBT/FBQU/xQUFP8UFBT/FBQU/62trf/6+vr/r6+v/1lZWf8UFBT/FBQU/1lZ"
    b"Wf+vr6//+vr6/6ysrP8UFBT/FBQU/xQUFP8UFBT/FBQU/xgYGP8wMDB2Ly8vchkZGf8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/yoqKv+3t7f/+Pj4/729vf8UFBT/FBQU/76+vv/4+Pj/t7e3/ykpKf8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xgYGP8xMTFzNTU1TRoaGv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/HR0d/xoa"
    b"Gv8UFBT/FBQU/xoaGv8dHR3/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xsbG/82NjZMRUVFJR8f"
    b"H94UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/x4eHt5HR0ckAAAAADAwMG8cHBz+FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/HBwc/i4u"
    b"Lm4AAAAAAAAAAAAAAAAwMDBvHx8f3hoaGv8ZGRn/GBgY/xgYGP8YGBj/GBgY/xgYGP8YGBj/GBgY/xgY"
    b"GP8YGBj/GBgY/xgYGP8YGBj/GRkZ/xoaGv8fHx/eLy8vbQAAAAAAAAAAAAAAAAAAAAAAAAAARUVFJTY2"
    b"NkwvLy9yMDAwdTAwMHUwMDB1MDAwdTAwMHUwMDB1MDAwdTAwMHUwMDB1MDAwdTAwMHUwMDB1Ly8vcjY2"
    b"NkxFRUUlAAAAAAAAAAAAAAAA4AAHAMAAAwCAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAABAMAAAwDgAAcAKAAAACAA"
    b"AABAAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQEBAGEJC"
    b"QjJAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBA"
    b"QEBAQEBAQEBAQEBAQEBCQkIyQEBAGAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQEBAIDEx"
    b"MaYpKSneISEh9x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8f"
    b"H/8fHx//Hx8f/x8fH/8fHx//Hx8f/yEhIfcpKSneMDAwpTo6Oh8AAAAAAAAAAAAAAAAAAAAAAAAAADEx"
    b"MTkoKCjZFRUV/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8VFRX/KSkp2S8vLzYAAAAAAAAAAAAA"
    b"AAA+Pj4hKSkp2RQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/KSkp2jo6"
    b"Oh8AAAAAAAAAADExMaYVFRX/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8VFRX/MDAwpgAAAAA9PT0ZKSkp3hQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8pKSneQEBAGEFBQTMhISH3FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/Kioq/19fX/9ycnL/Hh4e/xQUFP8UFBT/Hh4e/3Jycv9fX1//KSkp/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/yEhIfdCQkIyQUFBPx8fH/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/2pqav/v7+//+vr6//r6+v9ubm7/FBQU/xQUFP9vb2//+vr6//r6+v/v7+//ampq/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Hx8f/0BAQEBBQUE/Hx8f/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP82Njb/9/f3//r6+v/k5OT/sbGx/y8vL/8UFBT/FBQU/y8vL/+xsbH/5OTk//r6"
    b"+v/29vb/NjY2/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8fHx//QEBAQEFBQT8fHx//FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/4+Pj//6+vr/0tLS/x0dHf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8dHR3/0tLS//r6+v+Pj4//FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/x8fH/9AQEBAQUFBPx8f"
    b"H/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/tbW1//r6+v+RkZH/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP+RkZH/+vr6/7S0tP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Hx8f/0BA"
    b"QEBBQUE/Hx8f/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP/BwcH/+vr6/4eHh/8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/4eHh//6+vr/wcHB/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8fHx//QEBAQEFBQT8fHx//FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/8LCwv/6+vr/h4eH/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/h4eH//r6+v/CwsL/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/x8fH/9AQEBAQUFBPx8fH/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/0dHR//r6"
    b"+v9ycnL/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9zc3P/+vr6/9HR0f8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/Hx8f/0BAQEBBQUE/Hx8f/xQUFP8UFBT/FBQU/xQUFP8UFBT/Gxsb/2dn"
    b"Z//6+vr/+vr6/0hISP8UFBT/FBQU/xQUFP8mJib/JiYm/xQUFP8UFBT/FBQU/0lJSf/6+vr/+vr6/2Zm"
    b"Zv8bGxv/FBQU/xQUFP8UFBT/FBQU/xQUFP8fHx//QEBAQEFBQT8fHx//FBQU/xQUFP8UFBT/FBQU/xoa"
    b"Gv/d3d3/+vr6//r6+v/b29v/FRUV/xQUFP8UFBT/JiYm//Ly8v/y8vL/JiYm/xQUFP8UFBT/FRUV/9zc"
    b"3P/6+vr/+vr6/93d3f8aGhr/FBQU/xQUFP8UFBT/FBQU/x8fH/9AQEBAQUFBPx8fH/8UFBT/FBQU/xQU"
    b"FP8UFBT/Ghoa/93d3f/6+vr/+vr6/9vb2/8VFRX/FBQU/xQUFP8mJib/8vLy//Ly8v8mJib/FBQU/xQU"
    b"FP8VFRX/3Nzc//r6+v/6+vr/3d3d/xoaGv8UFBT/FBQU/xQUFP8UFBT/Hx8f/0BAQEBBQUE/Hx8f/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/Gxsb/2dnZ//6+vr/+vr6/0hISP8UFBT/FBQU/xQUFP8mJib/JiYm/xQU"
    b"FP8UFBT/FBQU/0lJSf/6+vr/+vr6/2dnZ/8bGxv/FBQU/xQUFP8UFBT/FBQU/xQUFP8fHx//QEBAQEFB"
    b"QT8fHx//FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/9HR0f/6+vr/cnJy/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/c3Nz//r6+v/R0dH/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/x8f"
    b"H/9AQEBAQUFBPx8fH/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/wsLC//r6+v+Hh4f/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP+Hh4f/+vr6/8LCwv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/Hx8f/0BAQEBBQUE/Hx8f/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP/BwcH/+vr6/4eH"
    b"h/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/4eHh//6+vr/wcHB/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8fHx//QEBAQEFBQT8fHx//FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/7W1"
    b"tf/6+vr/kZGR/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/kZGR//r6+v+0tLT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/x8fH/9AQEBAQUFBPx8fH/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/j4+P//r6+v/S0tL/HBwc/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/x0dHf/S0tL/+vr6/4+P"
    b"j/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Hx8f/0BAQEBBQUE/Hx8f/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP83Nzf/9/f3//r6+v/k5OT/sbGx/y8vL/8UFBT/FBQU/y8vL/+xsbH/5OTk//r6"
    b"+v/29vb/NjY2/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8fHx//QEBAQEFBQT8fHx//FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9qamr/7+/v//r6+v/6+vr/bm5u/xQUFP8UFBT/b29v//r6"
    b"+v/6+vr/7+/v/2pqav8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/x8fH/9AQEBAQUFBMyEh"
    b"IfcUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8qKir/YGBg/3Nzc/8eHh7/FBQU/xQU"
    b"FP8eHh7/c3Nz/2BgYP8qKir/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/ISEh90JC"
    b"QjI9PT0ZKSkp3hQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8pKSneQEBAGAAAAAAxMTGmFRUV/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FRUV/zExMaYAAAAAAAAAADw8PCIoKCjZFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8pKSnZQEBAIAAAAAAAAAAAAAAAADU1NTopKSnZFRUV/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8VFRX/KCgo2TExMTkAAAAAAAAAAAAAAAAAAAAAAAAAADw8PCIxMTGmKSkp3iEh"
    b"IfcfHx//Hx8f/x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8fH/8fHx//Hx8f/x8f"
    b"H/8fHx//Hx8f/x8fH/8hISH3KSkp3jExMaY+Pj4hAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAA9PT0ZQUFBM0FBQT9BQUE/QUFBP0FBQT9BQUE/QUFBP0FBQT9BQUE/QUFBP0FBQT9BQUE/QUFBP0FB"
    b"QT9BQUE/QUFBP0FBQT9BQUE/QUFBP0FBQTM9PT0ZAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAf4AAAB8AA"
    b"AAOAAAABgAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAAABgAAAAcAAAAPgAAAH+AAAHygA"
    b"AAAoAAAAUAAAAAEAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAEhISCBAQEAoQEBAKEBAQChAQEAoQEBAKEBAQChAQEAoQEBAKEBAQChAQEAoQEBAKEBA"
    b"QChAQEAoQEBAKEBAQChAQEAoQEBAKEBAQChAQEAoQEBAKEBAQChAQEAoSEhIIAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7OztONTU1rTU1NdosLCzYLCws3Sws"
    b"LN0sLCzdLCws3SwsLN0sLCzdLCws3SwsLN0sLCzdLCws3SwsLN0sLCzdLCws3SwsLN0sLCzdLCws3Sws"
    b"LN0sLCzdLCws3SwsLN0sLCzdLCws3SoqKtg1NTXaNTU1rTw8PE0AAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAElJSQcyMjKuJCQk8hkZGf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xkZGf8kJCTzMjIyrVVVVQYAAAAAAAAAAAAAAAAAAAAAAAAAADk5OQkxMTHJGhoa/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xsb"
    b"G/8xMTHJVVVVBgAAAAAAAAAAAAAAAAAAAAAzMzOuGhoa/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Gxsb/zIyMq0AAAAAAAAAAAAA"
    b"AAA9PT1QIyMj8hQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8kJCTyPDw8TQAAAAAAAAAAMzMzrxoaGv8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/GRkZ/zU1Na0AAAAAAAAAADU1NdoUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP81NTXaAAAAAEJC"
    b"Qh8sLCzYFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8WFhb/a2tr/6io"
    b"qP/Pz8//hYWF/xQUFP8UFBT/FBQU/xQUFP+FhYX/z8/P/6ioqP9ra2v/FhYW/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws2EhISCBBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8mJib/wMDA//r6+v/6+vr/+vr6//f39/8dHR3/FBQU/xQU"
    b"FP8dHR3/+Pj4//r6+v/6+vr/+vr6/8DAwP8mJib/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/nZ2d//r6+v/6+vr/+vr6//Dw8P+SkpL/FBQU/xQUFP8UFBT/FBQU/5KSkv/w8PD/+vr6//r6"
    b"+v/6+vr/nJyc/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Kysr//f39//6+vr/6enp/0VF"
    b"Rf8VFRX/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FRUV/0VFRf/q6ur/+vr6//f39/8rKyv/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/1RUVP/6+vr/+vr6/42Njf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/jo6O//r6+v/6+vr/U1NT/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP90dHT/+vr6//r6+v9wcHD/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/3Bw"
    b"cP/6+vr/+vr6/3Nzc/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/eXl5//r6+v/6+vr/ampq/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9qamr/+vr6//r6+v95eXn/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/3p6ev/6+vr/+vr6/2pqav8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/ampq//r6+v/6+vr/enp6/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP+FhYX/+vr6//r6+v9bW1v/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/1xc"
    b"XP/6+vr/+vr6/4SEhP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/sLCw//r6+v/6+vr/Pz8//xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8/Pz//+vr6//r6+v+wsLD/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP9GRkb/0dHR//r6+v/6+vr/4uLi/xkZGf8UFBT/FBQU/xQUFP8ZGRn/Z2dn/2dn"
    b"Z/8ZGRn/FBQU/xQUFP8UFBT/GRkZ/+Li4v/6+vr/+vr6/9HR0f9GRkb/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9FRUX/+vr6//r6"
    b"+v/6+vr/+vr6/3Z2dv8UFBT/FBQU/xQUFP8UFBT/Z2dn//r6+v/6+vr/Z2dn/xQUFP8UFBT/FBQU/xQU"
    b"FP93d3f/+vr6//r6+v/6+vr/+vr6/0VFRf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/RUVF//r6+v/6+vr/+vr6//r6+v92dnb/FBQU/xQU"
    b"FP8UFBT/FBQU/2dnZ//6+vr/+vr6/2dnZ/8UFBT/FBQU/xQUFP8UFBT/d3d3//r6+v/6+vr/+vr6//r6"
    b"+v9FRUX/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP9GRkb/0tLS//r6+v/6+vr/4eHh/xkZGf8UFBT/FBQU/xQUFP8ZGRn/Z2dn/2dn"
    b"Z/8ZGRn/FBQU/xQUFP8UFBT/GRkZ/+Li4v/6+vr/+vr6/9LS0v9GRkb/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP+wsLD/+vr6//r6+v8/Pz//FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/z8/"
    b"P//6+vr/+vr6/7CwsP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/hYWF//r6+v/6+vr/W1tb/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9cXFz/+vr6//r6+v+EhIT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/3p6ev/6+vr/+vr6/2pqav8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/ampq//r6+v/6+vr/enp6/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP95eXn/+vr6//r6+v9qamr/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/2pq"
    b"av/6+vr/+vr6/3l5ef8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/dHR0//r6+v/6+vr/cHBw/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP9wcHD/+vr6//r6+v9zc3P/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/1RUVP/6+vr/+vr6/42Njf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/jo6O//r6+v/6+vr/U1NT/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQUFBJywsLN4UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8rKyv/9/f3//r6+v/p6en/RUVF/xUVFf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8VFRX/RUVF/+rq"
    b"6v/6+vr/9/f3/ysrK/8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzdQEBAKEFB"
    b"QScsLCzeFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/52dnf/6+vr/+vr6//r6"
    b"+v/w8PD/kZGR/xQUFP8UFBT/FBQU/xQUFP+SkpL/8PDw//r6+v/6+vr/+vr6/5ycnP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/LCws3UBAQChBQUEnLCws3hQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8nJyf/wMDA//r6+v/6+vr/+vr6//f39/8dHR3/FBQU/xQU"
    b"FP8dHR3/+Pj4//r6+v/6+vr/+vr6/8DAwP8mJib/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/ywsLN1AQEAoQkJCHywsLNgUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xYWFv9sbGz/qamp/9DQ0P+FhYX/FBQU/xQUFP8UFBT/FBQU/4WFhf/Q0ND/qamp/2xs"
    b"bP8WFhb/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8qKirYSEhIIAAA"
    b"AAA1NTXaFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/NTU12gAAAAAAAAAAMzMzrxoaGv8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/GRkZ/zU1Na0AAAAAAAAAADw8PFEjIyPyFBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/yQkJPM7OztOAAAAAAAA"
    b"AAAAAAAAMzMzrxoaGv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xoaGv8yMjKuAAAAAAAAAAAAAAAAAAAAADk5OQkxMTHJGhoa/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xoa"
    b"Gv8yMjLISUlJBwAAAAAAAAAAAAAAAAAAAAAAAAAAOTk5CTMzM68kJCTyGhoa/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Ghoa/yMjI/IzMzOuQEBACAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAOzs7UjMzM681NTXaLCws2CwsLN4sLCzeLCws3iwsLN4sLCzeLCws3iws"
    b"LN4sLCzeLCws3iwsLN4sLCzeLCws3iwsLN4sLCzeLCws3iwsLN4sLCzeLCws3iwsLN4sLCzeLCws3iws"
    b"LN4sLCzYNTU12jMzM689PT1QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAEJCQh9BQUEnQUFBJ0FBQSdBQUEnQUFBJ0FBQSdBQUEnQUFBJ0FBQSdBQUEnQUFBJ0FB"
    b"QSdBQUEnQUFBJ0FBQSdBQUEnQUFBJ0FBQSdBQUEnQUFBJ0FBQSdBQUEnQkJCHwAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAA/wAAAP8AAAD4AAAAHwAAAOAAAAAHAAAAwAAAAAMAAADAAAAAAwAAAIAA"
    b"AAABAAAAgAAAAAEAAACAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAABAAAAgAAAAAEAAACAAAAAAQAAAMAA"
    b"AAADAAAAwAAAAAMAAADgAAAABwAAAPgAAAAfAAAA/wAAAP8AAAAoAAAAMAAAAGAAAAABACAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADw8"
    b"PE01NTWUNjY2wTY2Nsw6OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6"
    b"Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zY2"
    b"Nsw2NjbBNjY2kzw8PE0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAA5OTlDOTk53CgoKPYiIiL/Gxsb/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8bGxv/IiIi/ygoKPY4ODjcODg4QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAADY2NoUsLCzzFRUV/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8WFhb/LS0t8zU1NYEAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAANTU1gygoKPoUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/ycn"
    b"J/o1NTWBAAAAAAAAAAAAAAAAAAAAAAAAAAA5OTlDLCws8xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8tLS3zODg4QAAAAAAAAAAAAAAAAAAAAAA5OTndFRUV/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8WFhb/ODg43AAAAAAAAAAAAAAAAD09PU8oKCj2FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/KCgo9jw8PE0AAAAAAAAAADc3"
    b"N5UhISH/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/IiIi/zY2"
    b"NpMAAAAAAAAAADY2NsIbGxv/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/IiIi/0BAQP83Nzf/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Nzc3/0BA"
    b"QP8iIiL/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/Gxsb/zY2NsEAAAAAAAAAADY2NswUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/0pKSv+8vLz/9/f3//r6+v/6+vr/cHBw/xQUFP8UFBT/FBQU/xQU"
    b"FP9wcHD/+vr6//r6+v/39/f/vLy8/0pKSv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zY2NswAAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/cHBw//n5+f/6+vr/+vr6//r6+v/6+vr/tra2/xQU"
    b"FP8UFBT/FBQU/xQUFP+2trb/+vr6//r6+v/6+vr/+vr6//n5+f9wcHD/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8rKyv/8fHx//r6+v/6+vr/+vr6//r6"
    b"+v/09PT/XV1d/xQUFP8UFBT/FBQU/xQUFP9dXV3/9PT0//r6+v/6+vr/+vr6//r6+v/x8fH/Kysr/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6"
    b"Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP+ampr/+vr6//r6"
    b"+v/5+fn/h4eH/0NDQ/8gICD/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/ICAg/0NDQ/+Hh4f/+fn5//r6"
    b"+v/6+vr/mZmZ/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6"
    b"Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP/X19f/+vr6//r6+v+goKD/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/oaGh//r6+v/6+vr/1tbW/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xkZGf/29vb/+vr6//r6+v9hYWH/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/YmJi//r6+v/6+vr/9vb2/xkZGf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6+v9QUFD/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/UFBQ//r6+v/6+vr/+vr6/y8vL/8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6+v9OTk7/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Tk5O//r6+v/6+vr/+vr6/zAw"
    b"MP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6"
    b"Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6"
    b"+v9OTk7/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Tk5O//r6"
    b"+v/6+vr/+vr6/zAwMP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6"
    b"Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zk5"
    b"Of/6+vr/+vr6//r6+v9ERET/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/RERE//r6+v/6+vr/+vr6/zg4OP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/1FRUf/6+vr/+vr6//r6+v8oKCj/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/KSkp//r6+v/6+vr/+vr6/1BQUP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FRUV/6urq//6+vr/+vr6/+zs7P8VFRX/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FRUV/+zs7P/6+vr/+vr6/6urq/8VFRX/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/yEhIf+JiYn/+vr6//r6+v/6+vr/+vr6/5KSkv8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/z4+Pv/ExMT/xMTE/z4+Pv8UFBT/FBQU/xQUFP8UFBT/FBQU/5OTk//6+vr/+vr6//r6"
    b"+v/6+vr/iYmJ/yEhIf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6"
    b"Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/4aGhv/6+vr/+vr6//r6+v/6+vr/+vr6/y8v"
    b"L/8UFBT/FBQU/xQUFP8UFBT/FBQU/8XFxf/6+vr/+vr6/8TExP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAw"
    b"MP/6+vr/+vr6//r6+v/6+vr/+vr6/4aGhv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6"
    b"Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/4aGhv/6+vr/+vr6//r6"
    b"+v/6+vr/+vr6/y8vL/8UFBT/FBQU/xQUFP8UFBT/FBQU/8XFxf/6+vr/+vr6/8TExP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6+v/6+vr/+vr6/4aGhv8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/yIi"
    b"Iv+JiYn/+vr6//r6+v/6+vr/+vr6/5KSkv8UFBT/FBQU/xQUFP8UFBT/FBQU/z4+Pv/FxcX/xcXF/z4+"
    b"Pv8UFBT/FBQU/xQUFP8UFBT/FBQU/5OTk//6+vr/+vr6//r6+v/6+vr/iYmJ/yEhIf8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FRUV/6urq//6+vr/+vr6/+zs7P8VFRX/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FRUV/+zs7P/6+vr/+vr6/6urq/8VFRX/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/1FRUf/6+vr/+vr6//r6+v8oKCj/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/KSkp//r6+v/6+vr/+vr6/1BQ"
    b"UP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6"
    b"Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zk5Of/6+vr/+vr6//r6"
    b"+v9ERET/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/RERE//r6"
    b"+v/6+vr/+vr6/zg4OP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6"
    b"Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAw"
    b"MP/6+vr/+vr6//r6+v9OTk7/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/Tk5O//r6+v/6+vr/+vr6/zAwMP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6+v9OTk7/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/Tk5O//r6+v/6+vr/+vr6/zAwMP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zAwMP/6+vr/+vr6//r6+v9QUFD/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/UFBQ//r6+v/6+vr/+vr6/y8vL/8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xkZGf/29vb/+vr6//r6+v9hYWH/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/YmJi//r6+v/6+vr/9vb2/xkZ"
    b"Gf8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6"
    b"Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP/X19f/+vr6//r6"
    b"+v+goKD/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/oaGh//r6"
    b"+v/6+vr/1tbW/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6"
    b"Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP+ampr/+vr6//r6+v/5+fn/h4eH/0JCQv8gICD/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/ICAg/0JC"
    b"Qv+Hh4f/+fn5//r6+v/6+vr/mZmZ/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8rKyv/8fHx//r6+v/6+vr/+vr6//r6+v/09PT/XV1d/xQUFP8UFBT/FBQU/xQU"
    b"FP9dXV3/9PT0//r6+v/6+vr/+vr6//r6+v/x8fH/Kysr/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADo6Ot8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/cXFx//n5+f/6+vr/+vr6//r6+v/6+vr/tra2/xQU"
    b"FP8UFBT/FBQU/xQUFP+2trb/+vr6//r6+v/6+vr/+vr6//n5+f9wcHD/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zo6Ot8AAAAAAAAAADY2NswUFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/0pKSv+9vb3/9/f3//r6"
    b"+v/6+vr/cHBw/xQUFP8UFBT/FBQU/xQUFP9wcHD/+vr6//r6+v/39/f/vb29/0pKSv8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/zY2NswAAAAAAAAAADY2"
    b"NsIbGxv/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/IiIi/0FBQf83Nzf/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Nzc3/0FBQf8iIiL/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/Gxsb/zY2"
    b"NsEAAAAAAAAAADc3N5UhISH/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/IiIi/zU1NZQAAAAAAAAAAD09PVApKSn2FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/KCgo9jw8PE0AAAAAAAAAAAAAAAA5OTndFRUV/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8VFRX/OTk53AAAAAAAAAAAAAAAAAAAAAA3NzdFLS0t8xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8sLCzzOTk5QwAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAANDQ0iCgoKPkUFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/ycnJ/k2NjaFAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAADQ0NIgtLS3zFRUV/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8VFRX/LCws8zU1"
    b"NYMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA3NzdFOjo63SkpKfYhISH/Gxsb/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQU"
    b"FP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8UFBT/FBQU/xQUFP8bGxv/ISEh/ygo"
    b"KPY5OTndOTk5QwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD09"
    b"PVA3NzeVNjY2wjY2Nsw6OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6"
    b"Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zo6Ot86OjrfOjo63zY2"
    b"Nsw2NjbCNzc3lT09PU8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////"
    b"AAD+AAAAAH8AAPgAAAAAHwAA8AAAAAAPAADgAAAAAAcAAMAAAAAAAwAAwAAAAAADAACAAAAAAAEAAIAA"
    b"AAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAAB"
    b"AACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAA"
    b"AAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAAB"
    b"AACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAAAAAAAQAAgAAAAAABAACAAAAAAAEAAIAA"
    b"AAAAAQAAgAAAAAABAACAAAAAAAEAAMAAAAAAAwAAwAAAAAADAADgAAAAAAcAAPAAAAAADwAA+AAAAAAf"
    b"AAD+AAAAAH8AAP///////wAAiVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAACXBIWXMA"
    b"AA9hAAAPYQGoP6dpAAAIX0lEQVR4nO1bXUxTyxb+Zre01TbFKlyg6BYs5hISCclNDKcCEgygLwgJUTR4"
    b"0cQcY2JzeNEID1JfiNGEkBBzk3M12qMJmBAkfQAhQkSkguGBGGPuD2gtUDAStY21LW33vg8Ch93ujdiO"
    b"qFy/J2atWWuv+dgzs2bWLvB/DvIlnYuKiow8z6fxPJ8CQPOVYooWHwghMwzDvOzr63u8WqPPEtDQ0MDc"
    b"v3//qkwm+7vH43nL83x8IBBQhUKhuNjipQuZTBaIi4vzEUJcGo1Gx3HcrcHBwdOfs1uRgNzc3NNKpfLq"
    b"1NQUPB4PCQaD9CL+ipDL5di4cSPHsizj9XpPjYyM/C7VV5IAo9E45PV6d09OTsq/TphrA5ZlgyqVathm"
    b"s+WL6UUJyMvL+4/T6cxwu91ftEZ8r4iPj+eTk5P/OzQ09NdwHRMuMBqNQ06nc+d6GTwAuFwuMjs7u9No"
    b"ND4M1wkIyM3NPe31ene73e61i26N4HK5iM/n+yU3N/fkcvkSAQ0NDYxSqbz6o8/5leBwOOQqleqfy2Wy"
    b"xT+CweA/nE7n3/x+/7p59cXg9/v5Xbt2/eXVq1ddwLI3QCaTHfN4POt68ACwMMZji20G+JTheTyetz/K"
    b"Ph8LgsEgPnz44M7Pz98NLBCwkN7Gf9vQ1g6EEK1MJtsB/ElASiAQUNF8iFKpRFVVFSwWC0ZHR2G329Hf"
    b"34/s7GxJm+zsbPT398Nut2N0dBQWiwVVVVVQKpU0Q4Pf71cRQvTAn2uAhmZuX1JSApvNhqamJhQXF0Ov"
    b"10OhUCAzMxPNzc2Sds3NzcjMzIRCoYBer0dxcTGamppgs9lQXFxMKzxwHBfH87wWEEmEYsXRo0dx48YN"
    b"pKSkiOpTU1MlbaV0KSkpuHnzJo4cOUIlxuWgSoDBYEBjYyMIkd5M7ty5E5WOEILGxkYYDIaYYgwH1aTH"
    b"ZDJBoVAIZB6PB319fXA4HBgbG0N3d7ekvdlsxvDwMHJycsCyLPbt2we1Wr2kVyqVMJlMqK2tpRYzNQI2"
    b"bNiA8vJygez169eoqKiA3W5flQ+O49DV1YWuri4AQHp6Ojo6OpCUlLTUp7y8HOfPn4fP56MSN7UpkJOT"
    b"E/Hfv3z58qoHL4aXL1/iypUrAplCoUBOTk7UPsNBjYCMjIwImc1mi9mvmA+xZ0ULagRs3rw5QjY7Oxuz"
    b"XzEfYs+KFtQIkMsjlxO/3x+zX7G5HhdH7zqSeh7wo+EnAbQcyWQyQTsUCtFyDY7jVnxWLKBGgE6nE7Rn"
    b"ZmZouY7wtWnTJmq+qRGwdetWQXtycpKW6whf27Zto+abCgGpqakoLCwUyGgS4HA4BO29e/dCr9dT8R01"
    b"AYQQZGRkoK6uDu3t7RHz8uHDiBtoAbRaLaqrq1FdXQ2tVrti33Bfcrkc7e3tqKurQ0ZGxoqHr88h6rNA"
    b"Y2MjampqRHVzc3Po6emRtNVqtejt7QXLsgCAM2fOoKSkBFLX8T09PZibm0NCQsKSLC0tDSaTCSaTCRaL"
    b"BXV1dVGNI6o3wGAwSA4e+HSq83g8kvqysrKlwQMAy7IoKyuT7O/xeGA2myX1NTU1UR+Tf+YB0RhNTEzA"
    b"YrFI6s1ms+AcHw6r1SpY2BwOB6xWq2R/tVqNixcvSuotFgsmJiY+E7U4ol4D6uvrcf36dVRWVqKsrAxp"
    b"aWlLuoSEBJSWlqKjo0PU1u12o6SkZOm1t1qtkvMfAEpLS7FlyxaBzG63w2q1or29HePj49EOI3oCeJ7H"
    b"+Pg4Ll26hFu3bmF4eFiwExQUFEgSAHwi4fbt26t6VkFBgaAdDAZRWVkJp9MZXfDLQGUNmJ6exoMHDwQy"
    b"msnK8gUTAAYGBqgMHqC4CE5NTQnaNAkI90UzyaJGwLt37wRtqWvxaBDu6/3799R8UyMg/PRH9cTGCMOk"
    b"edL8mQd86wC+NagRIFZap1HUVKkia7aBQCBmv4ugRsDbt28jZMnJyTH7FfMh9qxoQY0AsWzMaDTG7FfM"
    b"RyyZXzioETA2Nob5+XmB7Ny5c0hPT4/aZ3p6Os6ePSuQzc/PY2xsLGqf4aBWG/R6vejs7MShQ4eWZElJ"
    b"Sejt7RUUR+/duxdxybkIhmGwf/9+yeIoAHR2dlKrCwKUq8MtLS04ePCgYPFTq9WCs/61a9dw4cIFUXuz"
    b"2YyTJ0+K6oBPhZaWlhZ6AYPyNjgxMYH6+nrwPC/Z5/Dhw1HpeJ5HfX191MdeKVDPA1pbW3HixAnJa/Hp"
    b"6WlJWymd0+nE8ePH0draSiXG5VicAh9kMlkAAJWiW29vLwYGBlBRUYEDBw4gKysLiYmJePHixYofN9TW"
    b"1qK5uRk7duzAmzdv8Pz5c3R3d+Pu3btU6oyLYBgmQAhxAwsEEEJm4uLifKBEAPBpvra1taGtrW3VNk+f"
    b"PkVRURGtECShVCp9PM87gYUpwDDMS0KI66s/+fuBOxQKvQAWCOjr63us0Wh0YiXu9Qa5XA61Wq0dHBx8"
    b"AixbBDmOu6VWq8U36HUEjUbDh0KhPxbbgpJKYWEh/+zZs7WPao1ACEFWVhY3MDCwdFkh2Aa9Xu8plmXX"
    b"7RfTLMsGvV7vr8tlAgJGRkZ+V6lUw/Hx8dKZzA8KnU7HKxSKoSdPnlxfLhetKu7Zs+ffs7OzO10u17r4"
    b"/YBOp+MTExP/ZbPZssJ1K/1s7qHP5/vF4XD8sFsDIQQsywYVCsXQ48ePC8X6SN5cTk5O3ti+ffuMXq8v"
    b"8/v9fCgUIlKnuO8NcrkcWq2WNxgMfCgUOjUyMvKbVN9VveJ5eXlXGYY59vHjRxfP8/F+v1/Fcdx39dNZ"
    b"hmECSqXSB8CtVqu1HMf98ejRozOfs/uiOZ6fn79bJpPtIIToF7+3/15ACHHzPO8MhUIvFpOcn1gF/gd5"
    b"6BPjUd0XQgAAAABJRU5ErkJggolQTkcNChoKAAAADUlIRFIAAABgAAAAYAgGAAAA4ph3OAAAAAlwSFlz"
    b"AAAPYQAAD2EBqD+naQAADR1JREFUeJztnV9MVFcex7/n3pkLAwwjg8wAdlswiMZW2sTEIkuYIWyq7tJY"
    b"QXlgm5hUQnnR3U2NfVC3WsMmJm2zWx4qBEy6aUlapK1/sqFNydwxSNXUbKuNAWoKTRXk30AdBmSYuWcf"
    b"yszyZ+7lXpk5ozCfJ7jn3HN+93zvnPs7/4EYMVYzZLkJFBUVZfM8XwzgKUmS1hFCMgEYl2/aY4mbUtrP"
    b"cdw9SZJ+oZSKly9f7l1Ogo8kQFFR0QZCyKsAygkhzwIApRSSJPm8Xi8nSRK3HKMeVziOkwRBkDiO0xHy"
    b"W9FRSn8ghLQC+EgUxTta09QkQElJidXn8/0dQA2lFB6Ph7jdbjIxMYGZmRlQSrXm/0RCCIFer0dSUhKM"
    b"RiNNTEyks4KciYuLO/nVV18NqU5LbTybzfZXALUAhKGhId7lcsHv9z+C+SsPnudhNpthsVj8ALwAjjqd"
    b"zn8CWPKNXFIAu90eTyltIoRUulwuDA0NwefzhcHslYdOp4PFYoHZbAaAjwFUiaL4UOkeRQFKSkqsMzMz"
    b"/wHwwr1797hff/01fNauYEwmE9atWycB+E6v1/+xvb19UC6urADbt2836PX6DkppXl9fn25qaioixq5U"
    b"DAYDsrKyfISQmxzH/V7ulyDnrRBBEBoBvBAr/EdjamoKfX19OgAvAGiEzMvOh7pos9n+Rgg5fPfuXTIx"
    b"MRFBM1c2Pp8PXq+XmEymvKysrPG+vr6rC+MsUmXW1ewdGxsz9Pf3s7F0hZOZmYmUlJTJuLi47IUu6qIq"
    b"aNbPFwYHZb8bMTQyNDQEAHFer/fvC8Pm/QJmW7hdQ0ND3PDwMCv7VgUWiyXQTtg0t8U87xfAcdyfKaUY"
    b"HR1lbuBKZ3R0FJIkEQCvzr0+TwBK6V6Px0MkSWJq3GrA7/fD4/EQSmn53OtBAYqKirIJIc+63e5l95DG"
    b"CI3b7SaEkOeKioqyA9eCAhBC7AAQczsjR6BsA2UNzBGA47jfUUoxMzPD3rJVwpwe46cC13SBPyRJWidJ"
    b"ko9Sqgt1MysEQcDzzz+PzMxMWK1W+Hw+dHR0oKenR1M6ubm5KCwshE6nw+DgIPr7+/H999/D6/VGyPKl"
    b"mR0z8fM8vy5wLVjYhJBMr9cblYEUQghsNhsqKyths9lgNM4fUJMkCadOnUJ9fb2q9F5//XUcP34cHDf/"
    b"cdxuN5xOJ5qbm+F0OqMyfuH1eonBYAgKMNdCYzRGsjZv3oyWlhY0NzejtLR0UeEDAMdxOH78OHJzc5dM"
    b"Lzc3N2ThA4DRaERpaSmam5vR0tKCzZs3h+UZtDBbxsGHjOrQ4a5du3Dp0iUUFBQsGZfjOBQWFi4Zr7Cw"
    b"MGThL6SgoACXLl3Czp07VdkaKaImwM6dO9HY2Ij4+HjV96jx0LR4cfHx8WhqasKOHTtU3xNuoiKAxWLB"
    b"O++8g8DAthrGx8fhcDiWjOdwOKBl4IgQgnfffRdpaWmq7wknURHgyJEjgWE7VQwMDKCqqgpq+qeGh4dx"
    b"4MABDAwMqE7fbDbjzTffVB0/nDB3OVNSUlBeXq4Y54svvoAoihgeHsbAwADu3LmjaRy6s7MTL774InJy"
    b"cpCRkYG0tDTY7Xa88sorsveUlZWhtrYWY2NjqvMJB8wFKCsrQ1xcXMiwiYkJHDp0CG1tbcvOx+fzoaur"
    b"C11dXQCATz/9FBcuXEBdXR0SExMXxY+Pj8eePXtw9uzZZeetBeZVkJInc+zYsbAUvhxtbW04evSobLga"
    b"LyvcMBWA4zhs27YtZNj9+/fR2toacRtaW1shN9i0bds2VS5sOGGam9lsRkpKSsiw7u5uJhO9/H4/uru7"
    b"Q4aZzWZNzkE4YC6AHPfv32dmh1Jeci9IpGAqgNLDsRyDXrUC8HzIWTAAwLQbXCkvnY6tY7gip5E/ScQE"
    b"iDIxAaJMTIAow1QAQRBkw1gu9lDKS8nGSPDYtAMePHjAzA6lvFa0G5qamiobxnLxh1JeSjZGAqYCbNiw"
    b"QTbsp59+YmZHb6/8ylI1487hhJkASuMAlFLZ/plI0NXVJTsjory8HGvWrGFmCxMBeJ7HW2+9BYPBEDL8"
    b"1q1bmJycZGEKAGBychK3bt0KGWYwGHDixAlmvaIRa3cnJSVh+/btqKqqwsaNG2GxWGTjnj9/XlPaHMdh"
    b"3759sNlsAACn04mWlhZomVR84cIF5OXlhQyrqKiA3W5Hd3c3Ghsb8c0330RsymZwVNxut4sej8emVD+q"
    b"paCgAA0NDaq6dqenp5Gfn6+6M47jOHz44YcoKSmZd729vR379+9XLYLVasW1a9dUuZ0ulwvV1dXo7OxU"
    b"lbYS2dnZSExMdIqiaAciUAUlJyejvr5edb96Q0ODpp7Qffv2LSp8ACgpKcHevXtVpzM4OIiGhgZVcc1m"
    b"M86cOYPk5GTV6asl7AJs3bpVtSs3MDCAuro6TekHqp1Q2O12TWm9//77qmdPrF27Flu3btWUvhpiXRFR"
    b"JuwC3LhxAyMjI6riZmRk4ODBg5rSdzqdsmGiKGpK69ChQ8jIyFAVd2RkBDdu3NCUvhrCLsCDBw9QU1MD"
    b"l8ulKn51dTWsVqvq9FtaWtDe3r7o+tdff41z586pTsdqtaK6ulpVXJfLhZqamoh0l0TEDe3s7ER+fj7y"
    b"8/ODbqhcIcfFxaGsrAwffPCBqrQlScL+/fuxd+/eYJ0viiLOnTunyQ0tLy9X9IAGBwfR1dWFpqYmXL16"
    b"9clyQxfCcRzee+89VFRUhAy/efMm81nKbW1tsu2ATz75BG+88YYmQdUScTc0FJIk4cSJE5Dbc2LLli1I"
    b"SEhgYQoAICEhAVu2bAkZNjU1hZMnT0ak8EPBzAsaHx+XnXhFCMHGjRtZmYJNmzbJzsxubW3F+Pg4M1uY"
    b"uqE//vijbNj69euZ2ZGdnS0bpnUt2nJhKoDSCnyTycTMDqW8WO8SwFQAJdc0Es38R8mL9fR0pgIoLRFV"
    b"mrQVbpTyYr2MNdYVEWViAkSZmABRJiZAlGEqgNKEKL1ez8wOpbxYb0rLVAAlF09Lj+hySU9Plw1b0W6o"
    b"UjtAqVDCzaoWQO4BN23axKQtwPO8bL+Ty+VSPY4RLpgKIEkSrl+/HjLMarUuuYA7HJSXl8tWd9evX2fW"
    b"CxqAuRfU0dEhG1ZbWxvRcYFdu3ahtrZWNlzJtkjBfKX8Z599hmPHjoVcLZ+YmIizZ8/i/PnzcDgcGBkZ"
    b"QX9/v+atCoDf1nrl5OQgMzMTa9euRXFxMXbv3i0b/+HDh/j88881P89yYS7A2NgYWltbUVlZKRtn9+7d"
    b"8wprYGAABw8eVD0xqqCgAHV1daoH3IHfXgzWH2AgSg2x06dPa/rYZWRkoLGxUdWWMmlpaWhqatJU+KOj"
    b"ozh9+rTq+OEkKgIMDw/j8OHDmvZsW7NmDYqLi5eMV1xcrGlsgVKKw4cPq9oKJxJErSuira0NBw4cwMOH"
    b"iid8zCMpKSkscQJMTU3htddew5dffqn6nnAT1b6gtrY2lJaW4sqVK0vGlSRJlZfS0dGhypW8cuUKXn75"
    b"5agWPjBfADfHccw3jb59+zYqKipQWVmJixcvwu12L4oT2LZSzXhtT08PTp06FVIEt9uNixcvorKyEhUV"
    b"Fbh9+3ZYnkELs2UcfMigF0Qp7RcEQUIUfhWUUoiiCFEUIQgC8vLyghu3+v1+zRu31tfXw+FwoLCwEDzP"
    b"BzduvXnzZlQ3bgUAQRAogHuB/4MCcBx3D4COEBLVA9m8Xi++/fbbZafT09PDfIbDUhBCwHEcTykNChB8"
    b"2yVJ+iVwQlyMyKDX6wPzke4GrgUFoJSKgDYvIoY2AmUbKGtgjgCXL1/upZT+YDQaV8eBkFHAaDRSSukP"
    b"c09gnffBJYS0JiYmUpZTRFYLPM9j9tDPefMzF3o8HxFCmO+bthpITU0Fx3EUwEdzr88TYPZ0nzMWi8Uf"
    b"+xWED51Oh7S0ND+AMwvPHF7k8+t0urcBeFmO0a50ZtdITwuC8PbCsEWveW9vrycrK2syISFhx/T0NKan"
    b"p1nYuGIxmUxIT08HIeRIe4i1VSHrmZ9//vnaM888s8FoND47MTFBYucHPxoGgwFPP/20RAhpFkUx5O7g"
    b"ct0OlBByAMB3WVlZPrk9HmLIEzjOFsB/AVRB5nRt2S9tX1+fLycn57wkSX9ISUmxer1eEquO1GEymQJv"
    b"/nd6vf5PDodDdoMiRVent7fXk52d/W9CyHqTyZSn0+kwNTXFfObAk4JOp0N6enqgzv+YELJHqfABFWfK"
    b"B+LZ7fa/UEr/AUAYHh7mR0dHme7z9jjD8zxSU1MDruY0IeSoKIr/gky1MxdNxxa+9NJLltkjWWskSSIe"
    b"j4e43W4yMTEx95CyFU+g0zIpKQnJyck0ISGBzjayzgiC8PbCM4MV03oUA+x2ew6AVyml5YSQ54D/H1Lm"
    b"9XpJNI7DYgHHcZIgCJTjOD6wypJSemu2e+HjhY0sNSz74M7ZQ0DtAJ4ihKwDsA5zzslaYbgB3Jvtz79L"
    b"CHGIotgXZZtixHiC+R/ezQO4JMo++wAAAABJRU5ErkJggolQTkcNChoKAAAADUlIRFIAAACAAAAAgAgG"
    b"AAAAwz5hywAAAAlwSFlzAAAPYQAAD2EBqD+naQAAESZJREFUeJztnWtQVEebx/995gYD4zBEEDZKwEsU"
    b"NSRqqTVlqIwaEz9MiTExcYn54hrRtdStWMQkr/mm1BI0byRBoXKp0gj7RjeJUFQqxhAnpRWCJgpEJQQv"
    b"iBfwEnC4yTCX3g8w7oDMzLkwZxo5v4/nPN39nOn/9Dnd/XQ3oKCgoKAwSiGhyDQ9PT1RpVItopTOI4Sk"
    b"ApgMIAZANABNKMp8hHAC6ARwD8BFSmkdIeSU2+3+6cSJE83DXdiwCaC/0l8HsBrA08OVr8IAagAcdLvd"
    b"xcMlBskCsFgsYyml7xNCNqD/3+3xeNDd3Y3Ozk44HA709vbC5XLB4/GAUirZ6UcZQgg4joNarYZWq4VO"
    b"p0N0dDT0ej04jvOaOQHsBbDDZrPdlVSe2IRmszlSp9NtoZS+RwgxeDwearfbSWdnJzo6OuDxeKT4pTAI"
    b"juMQHR0Ng8EAo9FIOY4jlNIOQkiOw+HYU1lZeV9MvqIE8Nxzz6UTQv4HwOOUUrS2tuLOnTtwuVxislMQ"
    b"iFqtRlxcHGJjY0EIAYAbAFbZbLaTQvMSLACLxfIfAAoBqNvb29HS0oLe3l6h2SgMA1qtFgkJCRgzZgwA"
    b"uACst9lsnwvJg7cALBaLGkAegP/yeDy0ubmZtLW1CXJYITSYTCYkJiZSjuMIIeSflNK3bTYbr+aYlwAs"
    b"FouaUvo1IWSZy+WiTU1NpLu7W5rXCsOKXq9HUlISVavVhFJaRgh5mY8IuGAG/eQRQpb19PTg0qVLSuUz"
    b"SHd3Ny5dukR6enpACFlGCPmATzpVMIP+d36Oy+WiV65cIU6nU7KzCqHB4/Ggs7PT20swp6SkXGtsbDwb"
    b"KE3AV0D/1/5PHo9H1djYqPzzRwh6vR7JycmU4zg3gIWBegd+XwFmszmyv6unbm5uVip/BNHd3Y3m5mYC"
    b"QA3gX2azOdKfrV8B6HS6LQAeb29vh/K1P/Joa2tDe3s7ADyu0+k2+7Mb8hXQP7x7GYChoaFB6eePULRa"
    b"LaZMmQIAHYSQiUMNG/trAbYTQgytra1K5Y9gent70dbWBkKIAcA/hrJ5qAXon9W76vF41H/99RdRhndH"
    b"Nmq1Gk8++STlOM4FIMlms7X43n+oBeif0tXY7Xal8h8BXC4X7HY7Qd9M7euD7w/1ClgNAB0dHSF2TUEu"
    b"fOryjcH3BghgyZIl/wbgae+AgsKjQWdnp3d6/un09PRE33sDBOB0OhcCff1IZT7/0cHj8aCrqwsAoFKp"
    b"FvneGyAASuk8AMq//xHEKwAAc32vDxBAfwAnHA6HPF4pyIa3Timlqb7XB38ETgag9P0fQbx1SgiZ4ntd"
    b"PcguBsCICe1SqVSYPXs2nn/+eUyfPh3jxo1DfHw8jEYj6uvrUV5ejsLCQtHPo9FokJWVBavViqlTp8Ju"
    b"t+P27du4desWLly4gB9//BFnzpyB2+0e5icbfry/AaXU6Ht9wECQxWLpBaA5f/4809G7EyZMwJYtW7B0"
    b"6VLExsYGtK2qqsLKlSsFi0Cj0eDQoUOYP39+QLvW1lZ8//332LNnD65duyaoDDkhhGDGjBkA4LTZbFrv"
    b"9cGvAA0AZis/Li4OO3bswMmTJ5GZmRm08gFg/vz5yMrKElxWVlZW0MoHgNjYWGRmZuLkyZPYsWMH4uLi"
    b"BJclBz51OmBhDt+IoLAza9YsVFRUYM2aNdBohC0uslqtgssTmkaj0WDNmjWoqKjAM888I7i8cDEiBLB0"
    b"6VJ8/fXXGDt2rKj0kydPFpxm0qRJosoaO3YsvvnmG7z44oui0ssN8wKYPXs2Pv30U0RERIjO4+LFi4LT"
    b"XLp0SXR5ERER+OyzzzBr1izRecgF0wLQ6/X4+OOPoVIFDV0MSHl5uSxpfFGpVPjkk0+g1+sl5RNqmBbA"
    b"tm3bkJKSIimPqqoqFBUVCU5XWFiIqqoqSWWnpKRg27ZtkvIINcwKICYmBm+88dDkFS+cTidqamqwc+dO"
    b"UV1AoK/f/Oqrr2Lnzp2oqamB2Gjo1atXIyYmRlRaORg8EMQMq1at4v3er6iowFdffYXa2lq0tbWhq6tr"
    b"WCaznE4nCgoKUFBQAI7jEBUVBZPJhLS0NKxatQqLFi0KmkdkZCRee+01Ua2QHAweCKIAcO7cufB40w8h"
    b"BL/88gueeOKJgHaUUmRnZ6OkpEQmzwaSmZmJvLw87wJNvzQ2NmLBggVhH1+ZOXMmAMBmsz1wmMlXwIQJ"
    b"E4JWPgDs3r07bJUPACUlJfjwww+D2iUnJ2P8+PEyeCQcJgXAZwSuqakJ+fn5MngTmD179qCpqSmoHZ9n"
    b"CgdMCmDevHlBbUpKSpiYtHK5XLxaIUUAAuiPZQ/IqVOnZPCEH6dPnw5qI2Y0Ug6YFMBjjz0W1Oby5csy"
    b"eMIPPqOGfJ4pHDApAJPJFNSGpbA1n3Arv/CZuQwHI1YAPT09MnjCj/v3g+/PxOeZwgGTAgjWrwbAVNQy"
    b"H1/4PFM4YFIACvKhCGCUowhglKMIYJSjCGCUowhglMOcAPhE/LK4comPT2o1e+EXzAmATxBI/+ZHTMFn"
    b"PwUpga2hgjkB9G98HBAWBcDHJz7PJjfMCYBPEOjff/8tgyfC4OOT1ADXUMCcAGbPnh3U5sKFCzJ4Igw+"
    b"Ps2ZM0cGT4TBlAA4jsPy5cuD2o1UAWRkZPge+8IETHmzcuVKTJs2LahdbW2tDN4Ig49PqampWLlypQze"
    b"8IcZASxfvhx5eXlB7Zqbm/HHH3/I4JEwamtr0dLSEtQuLy8PGRkZMnjEj7AIgBCCadOmYd26daivr8fN"
    b"mzexd+9eXv3ksrIyyVPBZrMZBw4cQHV1Naqrq3HgwAGYzWZJeXo8HpSVlQW1U6vV2LdvH27evIn6+nqs"
    b"W7cO06ZNC9t0sezrAgwGA/Ly8rBs2TJR6V944QVJ/m3evBnvvPPOQ9cppcjNzZUUaTxz5kz88MMPotKW"
    b"lZUhOzs7pPszMrEuQErlf/vtt5Iq32w2+12rRwjBtm3bJLUE586dw5EjR0SlXbZsGT74gNchH8OKrAKY"
    b"MWOG6Mp3OBzIycmRVP6GDRsCNrWEEKxfv15SGTk5OaJ3WcvIyMD06dMllS8UWQXAp4/vj40bN+LGjRuS"
    b"yk9LSxsWm0Bcv34dGzduFJ1e7rECZnoBCuFBVgGcOXNGdNqCggLJ6+v49NWljjGMHz8eBQUFotP//vvv"
    b"ksoXiqwCOH/+PK+u0lDodDq8++67ksrft29fwBW6lFLs27dPUhnvvfcedDqdqLSlpaWyj3LK/grIzs4W"
    b"LYKXXnrpQVdGDJWVlcjNzR1SBN5u4K+//io6/5kzZ/Iayh6K0tJSvP3226LLFovsEQodHR3YsGEDPvro"
    b"I6Snp2Pr1q2CpklffvllSV3B/Px8nD59GuvXr3/wwVdbW4vCwkJUVlaKzhcAXnnlFUH27e3t2L17N06c"
    b"OIH6+vqw7B/AzAYRy5cvR35+ftDRwObmZsydO5ephSFA30TWb7/9hoSEhIB2LpcLmzZtQmlpqUye/T9M"
    b"DAT548iRI8jOzg5ql5iYiKeeekoGj4SRlpYWtPKBvldgOCrfH8wIAAAOHz6MP//8M6id1L56KODjU11d"
    b"HQ4fPiyDN/xhSgAej4fXUKrco2V84ONTaWkpe6+ucDswGD5jBSNVAHL38fnAnACuXLkS1IbFzRb4+MTn"
    b"2eSGOQGM1OjakRrNzJwA+Gz8wKIADAZDUBuWNrXwwpwA+GzJqtVqg9rIDR+fWNjVbDDMCUBBXhQBjHIU"
    b"AYxyFAGMchQBjHIUAYxymBQAn3lxltbY8fEl3GcF+IOdX9GHtra2oDYsbbYQGRkZ1IbPM4WDESuA6Oho"
    b"GTzhR1RUVFCb1tZWGTwRDpMC4LPZwsSJE2XwhB98DplkcVMLgFEBNDQ0BLXhc6iEXMydOzeojZjDK+WA"
    b"SQHwOQwiMzOTiV231Go1MjMzg9pJPYMwVDApAD4/VlJSEjZv3iyDN4HZsmULkpKSgtopAhDAtWvXcPXq"
    b"1aB2W7du5fXvCxWZmZl46623gto1Njbi+vXrMngkHCYFQCnF/v37g9oRQrBr1y4cPHgQVqsVSUlJMBgM"
    b"IRkj4DgOBoMBSUlJsFqtKC4uxq5du3ht7LB//35mxwGYWRcwmJiYGJw5c0ZUf9/pdKKurg7l5eUoLCwU"
    b"PQ+v0WiQlZUFq9WK1NRUXruYDub+/fuYM2cO7t27J8qH4WSodQHh/4ryw7179/Dll1/izTffFJxWo9Eg"
    b"LS0NaWlpWLx4sajzgzUaDQ4dOiT5uLeDBw8yUfn+YPIV4CU3N1dyIOX8+fORlZUlOF1WVpbkyr98+TJy"
    b"c3Ml5RFqmBZAd3c3Nm3aBLfbLSkfq9UqSxpf3G43Nm3ahO7ubkn5hBqmBQD0rRNYu3atpIBKMYc28hnd"
    b"80dPTw/Wrl2Ls2fPis5DLpgXAAAcPXoUK1aswN27d0WlFzMKx+cwyKG4c+cOVqxYgaNHj4pKLzcjQgAA"
    b"UF1djUWLFuGLL77gFTnsS3l5ueDyhKZxOp34/PPPsXjxYlRXVwsuL1wMFoATYPeMu7t372L79u149tln"
    b"UVJSwmuGraqqCkVFRYLLKiws5DV619raiuLiYixYsADvv/++6FYq1PjU6YB/z+BxgFYAprq6OskfXnKg"
    b"Uqkwa9YsLFmyBKmpqRg3bhzi4+NhNBpRX1+P8vJyFBUVSRoHWLduHaxWK6ZOnQq73Y7bt2/j1q1bqKur"
    b"w7Fjx3D27NkR81ulpqaCUtr6888/P1jHNlgAlwGkNDQ0iN7rToFNdDqd91T2Kzab7cFc+uBXwEWAzZU3"
    b"CtLw1imldMBc+wABUErrAIje5UqBXbx1Sgip870+QACEkFMAW+FWCsODT9jaad/rAwSg0WiOA4Ber2cq"
    b"6lZBGiqV6sGf2u12/+R7b0AtHzt27CaAGo7jlFbgESIqKsrbDaw5ceJEs++9of7mBwF+690VRgY+dfnl"
    b"4HsPCcDtdhcDcBqNRspCzJ2CNNRqNYxGI0XfAFDx4PsPCaC/idjLcRyJi4uTwUWFUBIfHw+O4wiAApvN"
    b"9tChRv6+9HZQSjtiY2OVMYERjE6ng8lkAqW0XaVS7RjKZkgB2Gy2u4SQHEIIr90vFdhk3LhxIISAEJJT"
    b"UVEx5MoUv309h8OxB8CNMWPGwGQyhcxJhdBgMpm8m2ndcDgcfk/C8iuAysrK+5TSfwfgSkxMpHq9PgRu"
    b"KoQCvV6PxMRECsAFYFVlZeV9f7aqQBldvXq1KTk5+SYhJMNgMFC73U5Y2+pUYSBarRbJyclUpVIRQsib"
    b"Npst4M7UAQUAAI2NjWeTk5NjOI4zR0dHo6Ojg7n9bhX60Gq1SEpKglarJYSQfx4/fvy/g6XhO96bTSkt"
    b"i4iIwKRJk5TXAYPo9XpMnDiRRkREgFJaRinldfxI0BYAABobGz0pKSn/SwgxcBxnNhqN1OVyERZ3vhyN"
    b"xMTEYMKECVSlUhFK6Yfx8fFrv/vuO15RKoJjvxYuXLiGUloEQN3e3o6Wlhb09vYKdlpBOlqtFgkJCd6v"
    b"fRchJOv48eNfCMlDVPCfxWJ5FsC/ADxOKUVbWxtu377N5FaojyJqtRrx8fEwmUzeSZ4bAFbZbLaTQvMS"
    b"Hf1pNpsjdTrdZkrpPwghBo/HQ+12O+no6EBnZ6fyoTjMeGdoDQYDjEYj5TiOUEo7CCE7HQ5HfqCuXiAk"
    b"h/9aLJaxALYD+E8AGqDv5I+uri50dXXB4XCgt7cXLpcLHo+H2VWyrEAIAcdxUKvV0Gq10Ol0iIqKQlRU"
    b"lG+MhhNAAYCdNptNUhjysMV/WyyWBACvA3gDwNPDla/CAGrQN6VbPNTEjhhCsgAgPT09UaVSLQIwl1Ka"
    b"SgiZQik1EkIM6G8lFPzi7G/a7ZTShv4YvtNut/unwcEcCgoKCgoKEvg/2P8yn5U1aCkAAAAASUVORK5C"
    b"YIKJUE5HDQoaCgAAAA1JSERSAAABAAAAAQAIBgAAAFxyqGYAAAAJcEhZcwAAD2EAAA9hAag/p2kAACAA"
    b"SURBVHic7d19dFTVvTfw757JTN5mkkACDC/xCQmQoBJUKAlPQohEkEhQQeJtfQMUtXJ777WAq61Sa621"
    b"rmpc3nZdvAgVULFUFBBCQSgxCaEQlPJaDQghNUQSIJKXmUkykzn7+QOSZzJMMi/Zc87kzO+zVv6Yk5nf"
    b"3uvMnO+cOWeffQBCCCGEEEIIIYQQQgghhKgTU7oD/srKyjLqdLpUAGnX/1IBDAcQA8DIOY9hjBkB6BTs"
    b"Jhn47JzzVsZYC4BWAC0ALgI4DaAKQJXdbj994MCBViU76a8BEwB5eXnxkiTlSpI0gzE2A9c2ekKCRRXn"
    b"vESj0ZRoNJrSffv2NSrdIW8EdQDMmDFjpCRJj3DOH2SM3Y4g7y8h13HO+VHG2EcajeaDkpKSOqU71Jug"
    b"26CmTp0aqdfr7wewCMBdjDGNwl0ixG+cc4kxtpdzvsFms207ePBgm9J9chY0AZCfnx9jtVr/nTG2DECC"
    b"p+dLkoSOjg50dHTAZrOho6MDdrsdkiTd8EeIvzQazQ1/Op0O4eHh0Ov1CA8PR3h4ODQar76nrgAoioyM"
    b"XLVr166WAHfdK4oHQHZ29qCwsLD/BPBfAAb19jxJkmCxWGC1WmGxWNDW1gbOuXwdJaQXjDFERkYiOjoa"
    b"UVFRiI6O9hQIVwH8d2dn5x8qKiquytRNtxQLgMLCQu3ly5efAfAKgFh3z+Gco7W1FU1NTTCbzfRtTgYE"
    b"jUYDg8GAuLg4GI1GMNbrZtYMYOWQIUPe3rx5s0PGLnZTJADuvPPODM752wBud/f/9vZ2NDY2oqWlBQ6H"
    b"IuuFECG0Wi1iYmIQHx+PiIgIt8/hnP9Dq9U+U1JScljm7skbALm5uQYAbwB4yl3bVqsVly5dgtlslrNb"
    b"hMjCYDBg6NChiIqKcvdvDmA1gOdKS0tl2wBkC4C8vLx0h8PxEa4N2OnBarWivr4eVqtVru4QopioqCiY"
    b"TKbeguC0JEmF5eXlJ+Xoi1aGNtj06dOf5JxvAWBy/kdnZycuXryI+vp62O12GbpCiPLsdjuamppgt9vd"
    b"HTBMYIwtTkpKaqipqTka6L4EdA8gPz8/vK2tbS2AR1z/19jYiEuXLtFvfBLStFothg4divj4+Bv+xxh7"
    b"PyIi4sldu3Z1BKr9gAVAVlaWMSwsbNv1YbvdHA4Hamtr6Xc+IU4MBgMSExOh1d6wU77PbrfPC9S1BgEJ"
    b"gFmzZg3t6OjYxRi7w3m5xWLBhQsXaHefEDd0Oh0SExPdHRs4otfr79mzZ88l0W0KD4AZM2b8H0mS/gZg"
    b"jPPyK1euoKGhgQbvENIHxhiGDRuGhIQbBsN+o9FoZpaUlPxLaHsii82aNWuozWY7AJeNv76+HleuXBHZ"
    b"FCGqlpCQAJPJ5Lr4G71eny1yT0DYWYD8/PyY9vb2vYyxW7qWcc5RV1eH77//XlQzhIQEq9UKm83mOpIw"
    b"3uFwzBg5cuSfa2trbSLaERIA+fn54VardQdj7P92LeOc49tvv0VLS1Bc80DIgNPe3o729nbExsY6h8AI"
    b"rVY7Zfz48X85e/Zsv0+hibjUlrW1ta11PdpfV1eH1tYBOUkKIUGjtbUVdXU3TCeQ197evgYCfsL3ew8g"
    b"Nzd3CYCVzsvq6+tpt58QQdrb2yFJEgwGg/PiiUlJSbX9HSzUrwDIy8tLvz7CL6xr2ZUrV3DpkvCzFYSE"
    b"NKvVCo1G43qKcNZNN920/V//+pffG5zfPwGysrKMnZ2dmwF0X+JksVjQ0NDgb0lCSB8aGhpcr5eJ0Gg0"
    b"m69fZOcXvwNAp9O9zhgb1/XY4XDgwoULdJ6fkADhnKO2ttZ1+HwqgNf9renXQYTr1/MfdH59TU0NDe8l"
    b"RAYGgwFJSUnOi7hGo8n0Zz4Bn/cACgsLtdcn8+je+BsbG2njJ0QmZrMZjY09Zh1nDofj7cLCQp+P6fkc"
    b"ANen8eqeycfhcNBBP0Jk5nolLWPsjsuXL//Y1zo+/QS4PoHneTjN4VdXV4erVxWd15CQkBQXF4dRo0Y5"
    b"L2ru7Owc7ctEoz7tAVyfvbd747darWhqavKlBCFEkObmZtezArE6ne4/fKnhdQDk5+fHAHjWeVl9fT0d"
    b"9SdEIZzzG067c86fvb6tesXrALBarf8OIM7pMc3hR4jCuu6V4WRQW1vbUm9f71UATJ06NfL6HXu60YE/"
    b"QoLD5cuXXRctnzp1aqQ3r/UqAK7fq697hoL29nY67UdIkGhtbUV7e7vzooTw8PD7vHmtVwHAGFvo/Njl"
    b"HCQhRGFutsmF7p7nymMAzJgxYyTnfGbXY845XeNPSJBpaWnpces8zvmsmTNnjvD0Oo8BIEnSI8636G5t"
    b"baWpvAkJMg6Ho8fPcsaYprOz84bp+F15DADO+YPOj+m8PyHByXXblCTp3zy9ps8AyMvLi2eMdQ/7lSSJ"
    b"Dv4REqRaW1t7/AxgjN1+9913D+7rNX0GgCRJuXAaLmyxWOgW3YQEKc6565gAZrPZcvt6jacA6DHPHw38"
    b"ISS4WSyWHo855zN6eSoADwHgOtGna3FCSHBxs43m9fX8XgMgKyvLCCCt67EkSWhra+tX5wghgdXW1ub6"
    b"Mz3t+rbsVq8BoNPpUp0fd3R00IU/hAQ5zjk6OnreTFiv14/r5el9/gRIc37gWpQQEpxstp43DeKcp/Xy"
    b"VO8DwLUoISQ4ufmy9isAbvgJQAgJfqICYLjzA7vd3o8uEULk4mZbveE2w13CevsHgB6zitAAoMDS6XRI"
    b"T09HWloakpOTkZKSgsTERBiNRkRHR8NgMMBms6G+vh6VlZXYsWMHysvLFT8wyxhDTk4O5s6di4yMDJhM"
    b"Juj1epjNZlgsFrS2tqK2thbnzp1DdXU1qqqqcOLECfpCCSDXa3U4573OENRXAPQ4dUABIF5ycjIKCgow"
    b"depUTJkyBZGRfc/hoNPpkJKSgpSUFDz00EOorKzE8uXLUV1dLVOPe0pOTkZRUREyMjJu+N+gQYMwaNAg"
    b"AMD48eN7/M9qteKLL77AwYMHUVxcrFj/1cp1W2WM9XoasNdZgadPn97IGOseR1xVVYXOzk4hHQxlgwcP"
    b"xoIFCzB//nykp6f3u15zczMWLVqEyspKAb3zXkZGBtavX4/Y2FjPT/bg+PHj2Lp1Kz7++GO6qawAWq3W"
    b"NXQbS0tLE9w9t9cAyM3NtQHQdT3+6quvaC+gH0aOHImnn34aDz/8sMdvel81Nzdjzpw5sn2TJicnY+fO"
    b"nUI2fmdtbW3YuHEjVq9e7e6W2MRLjDHccsst3Y8557aysrJwd8/t6yCgzvkBbfz+iYuLwyuvvIKDBw9i"
    b"yZIlwjd+AIiNjUVRUREY6/ft4j1ijKGoqEj4xg8AkZGRWLJkCQ4ePIhXXnkFcXFxnl9EbuB6XIgxpu/t"
    b"uX7fHJT0TaPR4Ec/+hEqKirw+OOPIyysr8Mt/ZeRkYGcnJyAtgEAOTk5bn/zixQWFobHH38c+/fvxw9/"
    b"+ENoNPQxDRRaswEQFxeHdevWoaioCIMH93k5tlAFBQUBb2Pu3LkBb6NLfHw83nzzTaxbt472BgKEAkCw"
    b"CRMmYM+ePZg5c6bnJwuWmZkZ8DYC/e3vzsyZM7Fnzx5MmDBB9rbVjgJAoMzMTGzZssX1fm2yMZl6He8x"
    b"oNpwZ9SoUdiyZYsiAaRmFACCZGdnY+PGjYiOjla6K6oVHR2NDz/8EFlZWUp3RTUoAAQYN24c1q9fH5Aj"
    b"/L6or69XRRt9iYyMxIYNGzBuXK9XuBIfUAD0k9FoxJ/+9CdERUUp3RUcOnQo4G3IPeDInaioKKxduxYG"
    b"g0Hprgx4FAD99NprryElJUXpbgAAiouLA97Gjh07At6GN8aMGYPXXntN6W4MeBQA/TB9+nTMmzdP6W4A"
    b"uPbtX15eHvB2ysvLg2IvAADmz58vy9gHNaMA8JNer8err76qdDcAXLshxIoVK2S5MpBzjuXLl6O5uTng"
    b"bXnj1VdfhV7f60A34gEFgJ8ee+wxjB49WuluoKmpCYsXL5b1irrq6mosWrQoKEIgOTkZjz76qNLdGLAo"
    b"APyg1+uxdOlSpbuByspKFBQUKLJLXllZiTlz5gTFz4GlS5fSXoCfAjtAXaUefPBBRQbEWCwW1NfX49Ch"
    b"QyguLlZ8QpDq6uru3+EFBQXIzMyEyWSSfSzE8OHDUVhYiI0bN8rarhpQAPiIMYYlS5YEpDbnHEeOHMHh"
    b"w4dx5MgR1NTUdM+sYzabg3JiVs45ysrKUFZW1r1Mr9fDYDB0z2SUlJSESZMmYcqUKZg0aVJArlpcsmQJ"
    b"PvzwQ8VnSBpoKAB8lJ6eHpBBKHv37sXvfvc7VFVVCa8tN5vNhu+//757co+vv/4au3btAgCkpaXhF7/4"
    b"hfBrJVJTUzFhwgScOHFCaF21o2MAPiosLBRar7OzE8888wwWLlyoio3fk6qqKixcuBBLly4VPsPUgw8+"
    b"6PlJpAcKAB9oNBrcd999wup1dHRg8eLF+PTTT4XVHCi2bduGxYsXC51u/t5776W5A3xEa8sHEyZMQHx8"
    b"vLB6K1aswL59+4TVG2j27duH5557Tli9hIQE3HrrrcLqhQIKAB/ceeedwmpt3rwZn3zyibB6A9XHH3+M"
    b"jz/+WFg9ke9RKKAA8MH06dOF1GlsbMQLL7wgpJYaPP/888JmA87NzRVSJ1RQAHhJq9UKmcYbADZu3Aiz"
    b"2SyklhqYzWZh5/DT09Oh1WqF1AoFFABeSklJEXK9vyRJ+OCDDwT0SF3ef/99IefwIyMjkZycLKBHoYEC"
    b"wEui5qM7duwYLly4IKSWmly4cAFHjx4VUkvUnloooADw0pgxY4TUOXXqlJA6avTPf/5TSJ1gmZ9hIKAA"
    b"8NLIkSOF1Pnqq6+E1FEjUetG1HsVCigAvDRixAghdUJhtJ+/vv76ayF1RL1XoYACwEuiPlRXr14VUkeN"
    b"mpqahNShAPAeBYCXRE36abFYhNRRI1HrJhgmaB0oKAC8JGrKb6vVKqSOGolaN0pPzz6QUAB4iQIg8GgP"
    b"QH4UAF4SdXffYJzUI1iIWjeBvhOzmlAAEBLCKAAICWEUAISEMAoAQkIYBQAhIYwCgJAQRgFASAijACAk"
    b"hFEAEBLCKAAICWEUAISEMAoAQkIYBQAhIYwCgJAQRgHgBZ1OJ6SOw+EQUkfNJEkSUkfUe6Z2FABeEDUZ"
    b"CM0F4JmodRQRESGkjtpRAHhBVACIvBW2WolaRzQtmHcoALwQHh4upE57e7uQOmomah2Jes/UjgLAC9HR"
    b"0ULqXL58WUgdNRO1jkS9Z2pHAeCFxMREIXUuXbokpI6aiVpHot4ztaMA8IKou83SHoBnotYR3SHYOxQA"
    b"Xhg9erSQOt98842QOmomah2Jes/UjgLAC6JuNy3q7rdqJmodTZw4UUgdtaMA8GDEiBHCPkwUAJ6JDIDh"
    b"w4cLqaVmFAAezJ49W0idhoYGNDY2CqmlZleuXBF2IDA/P19IHTWjAOiDXq/H448/LqQWfft7T9S6Wrx4"
    b"MQ0J9oACoA+LFi0SdjSZAsB7otZVSkoKFi1aJKSWWlEA9CIxMRHLli0TVu/IkSPCaqndl19+KazW8uXL"
    b"MWrUKGH11IYCwI3o6Ghs2LABMTExQup1dHRg//79QmqFgoqKCmEXBcXExGDDhg00MrAXFAAuUlNTsW3b"
    b"NqSlpQmrWVFRgba2NmH11M5qtaKiokJYvfHjx2Pbtm1ITU0VVlMtQvo+ymFhYRg2bBgSExNx88034667"
    b"7kJWVpbwA0c7d+4UWs9fer0es2fPRn5+PtLT0zFs2DAA185QnDhxArt27cLu3buD4rLl4uJizJgxQ1i9"
    b"W265BXv27MGBAwfwt7/9DV999RVqa2vR0NCAzs5OYe0MNKy3f+Tm5nLnx6dOnQp8bwKMMYacnBw88MAD"
    b"mDhxIkaPHh3we8lbrVZMnDgRFosloO14MmfOHLz44osex8jX1tbi5ZdfVjy0DAYDjh07hqioqIC209nZ"
    b"ifPnz+PYsWP45JNPsH//fnDOPb8wyN166609HpeWlrrd1kPmJ8CYMWOwdetW/PnPf8aCBQswduzYgG/8"
    b"ALB9+3ZFN36tVouXXnoJa9as8eoCmcTERKxZswYvvfQStFqtDD10z2w2Y8eOHQFvJywsDGPHjkVhYSE2"
    b"bdqELVu2YMyYMQFvN1iERABkZmaiuLgYU6ZMkb3td955R/Y2nf3yl7/EU0895fPrnnrqKaxcuTIAPfLe"
    b"6tWrZW8zIyMDxcXFyMzMlL1tJag+AJKSkoQe0ffFzp07UVVVJXu7XebMmePXxt/l6aefxpw5cwT2yDdV"
    b"VVX461//Knu7MTExWL9+PZKSkmRvW26qDgDGGN566y0YjUbZ25YkCUVFRbK320Wv1+NXv/pVv+u8+OKL"
    b"0Ov1AnrknzfeeEPYRKG+iImJwVtvvQXGej1MpgqqDoCcnBxFdvsBYM2aNYp++8+ePVvIAJjExERh10P4"
    b"o6qqCmvXrlWk7SlTpmDatGmKtC0XVQfAvffeq0i7dXV1eOONNxRpu4vIC2GUDAAAeP311/Hdd98p0rZS"
    b"nyG5qDoAMjIyZG/TZrPhqaeeUvy0n6g5DETX8ofFYsGTTz6pyPgEJT5DclJ1AJhMJtnbXLZsGY4ePSp7"
    b"u666BvkEWy1/HT16FMuXL5e9XSU+Q3JSdQAQQvqm6gCor6+Xvc0333wTt99+u+ztumpoaAjKWv664447"
    b"FDmrosRnSE6qDoDKykrZ29Tr9VizZo3iV5+dOHEiKGv5Izo6Gu+8844ipyOV+AzJSdUBsH37dkXaHTFi"
    b"BFasWKFI21127dolrNbu3buF1fLHc889hxEjRijStlKfIbmoOgDKy8tx+PBhRdp+8sknhV5S7Kvdu3ej"
    b"tra233Vqa2sVDYC0tDQsWbJEkbYrKytVP4+DqgOAc45nn30Wra2tsret0WgUOWrdxWaz4eWXX+53nV//"
    b"+teKXh68YsUKaDTyf0xbWlrw05/+VBVXBvZF1QEAADU1NXjsscfQ0tIie9tz5sxRdC9g586d/boYafXq"
    b"1YqMxe+SlpaGe+65R/Z2W1pasHDhQtTU1MjettxUHwDAtV25goICRQ7o9OdiHBF+85vf+HVV3erVq/HK"
    b"K68EoEfee/rpp2VvU8nPihJCbkKQadOmYf78+bjtttuQnJxME4K4CMUJQaqrq3H8+PGQnBAkpKYE45yj"
    b"vLwc5eXlAK5NluE6JVh2drbQKcGioqIwd+5cbNq0SVhNf+zcuRN79+7F7NmzMXv2bLdTgu3evTtopgQr"
    b"KCgQvvHb7XZUVFTcMCWYw+EQ2s5AElJ7AN5ITU3FH//4xxsStD/27duHRx99VFi9UPDBBx8InRPw1KlT"
    b"+MlPfoIzZ84IqxnMaEowP50+fRrz5s0TeinvtGnTAr4rqyZRUVHIzs4WVu/rr7/GvHnzQmbj9wUFgBsW"
    b"i0XomQO9Xi/0A6122dnZwkb9dR3RV/oYTLCiAOjFhQsX8OabbwqrN2nSJGG11G7y5MnCahUVFeHChQvC"
    b"6qkNBUAf1q9fj3PnzgmpdcsttwipEwpEratz585h/fr1QmqpFQVAH2w2G9atWyekFgWA90Stq3Xr1sFu"
    b"twuppVYUAB6IGgc/bNgwxMfHC6mlZgkJCRg6dKiQWiIviFIrCgAPvvvuOxw/flxILdoL8EzUOjp+/Dgu"
    b"XrwopJaaUQB4QdT18BQAnokMAOIZBYAXzp8/L6TO2LFjhdRRM1HrSNR7pnYUAF6orq4WUmfIkCFC6qiZ"
    b"qHUk6j1TOwoAL4iYWAOAsINbaiZqHYl6z9SOAsALokaR0R6AZ6LWEY388w4FgBc6OjqE1ImIiBBSR81E"
    b"rSNR75naUQB4oa2tTUid8PBwIXXUTNQ6EvWeqR0FgBdEfZiUvMvuQCFqHbW3twupo3YUAF4QNZxUq9UK"
    b"qaNmoiYApSHA3qEAICSEUQAQEsIoAAgJYRQAhIQwCgBCQhgFACEhjAKAkBBGAUBICKMAICSEUQAQEsIo"
    b"AAgJYRQAhIQwCgBCQhgFACEhjALAS52dnULq0JwAvRO1bkS9V6GAAsBLoiYFoduE9y46OlpIHavVKqRO"
    b"KKAA8BIFQOCJWjc0HZj3KAC8JOpbRdS3nBrRHoD8KAC89N133wmpM2jQICF11CguLk5IHVHvVSigAPCS"
    b"qA9VWlqakDpqNH78eCF1KAC8RwHgpbq6OiF1br75ZiF11EjUuhH1XoUCCgAvnT17VkidW2+9VUgdNRJ1"
    b"Z+Bz584JqRMKKAC8dPLkSSF1brvtNowaNUpILTUZNWoUbr/9diG1RN3OPRRQAHjp3LlzQk4vaTQaPPLI"
    b"IwJ6pC6PPvooGGP9rmO1WunOwD6gAPCSw+EQ9s3y8MMPw2AwCKmlBgaDAQ8//LCQWidPnoTD4RBSKxRQ"
    b"APigrKxMSJ34+Hj89re/FVJLDV599VUMHjxYSK3S0lIhdUIFBYAPPv/8c2G1CgsL8cADDwirN1AtWLAA"
    b"CxYsEFZP5HsUCigAfHDy5Ek0NjYKq/fGG28gLy9PWL2B5q677sLrr78urN6VK1dw6tQpYfVCAQWADyRJ"
    b"wqeffiqsXnh4ONatW4f7779fWM2B4v7778e7774r9Jbp27dvhyRJwuqFAgoAH23evFlovbCwMKxatQob"
    b"NmwIiVGCaWlpeO+997Bq1SqEhYUJrf3RRx8JrRcKxL4DIeDEiRM4c+YMxo0bJ7TuzJkzcdddd+HIkSP4"
    b"4osv8OWXX6KmpgZmsxkWiwVmsxk2m01om4Gi1+thMBgQHR0Ng8GApKQkTJ48GT/4wQ8wadIkIaf7XJ0+"
    b"fVrYWI1QQgHgI8451q5di9///vfCazPGMHnyZEyePNnt/y0WC+rr61FZWYkdO3agvLwcnHPh/fAFYww5"
    b"OTmYO3cuMjIyYDKZFLnice3atYqvi4Go1yjOzc3tsTbp4Mr/p9frcejQIZhMJkX7UVlZieXLlys28CU5"
    b"ORlFRUXIyMhQpP0uFy9exNSpUwfMHpIcXIecl5aWut3W6RiAH2w2G1atWqV0N5CRkYGdO3cqsgEq2bar"
    b"VatW0cbvJwoAP7333ntBMeQ0NjYW69evR3JysmxtJicnY/369YiNjZWtzd5UV1fj/fffV7obAxYFgJ9s"
    b"NhteeOEFpbsB4FoIFBUVBeTgmivGGIqKioJi4weA559/nr79+4ECoB/KysqwdetWpbsB4NoueU5OTsDb"
    b"ycnJCYrdfgDYsmULysvLle7GgEYB0E8/+9nPgub684KCgoC3MXfu3IC34Y2zZ8/i5z//udLdGPAoAPrJ"
    b"bDbjiSeeCIqJKDMzMwPeRjB8+1utVjzxxBMwm81Kd2XAowAQ4MyZM1i4cKHi01HLcVpS6VOfbW1teOyx"
    b"x/DNN98o2g+1oAAQ5MCBA3jooYdgsViU7opqWSwWPPTQQ/j73/+udFdUgwJAoMrKSsyfPx8XLlxQpP36"
    b"+npVtOFObW0t5s+fj8rKSkXaVysKAMFOnjyJWbNmYe/evbK3fejQoYC3ocQGuHfvXtx999001j8AKAAC"
    b"oKmpCYsXL8ayZcvw/fffy9ZucXFxwNvYsWNHwNvo0tjYiGXLlmHx4sVoamqSrd1QQgEQIJIkYdOmTcjO"
    b"zsa7774b8DvWHjp0SJZz4uXl5QHfC+js7MS7776LadOmYdOmTXSNfwD1FQD2Hk/UUFb4o6mpCStXrkRm"
    b"ZibWrFkTkDMFTU1NWLFihSxXw3HOsXz5cjQ3Nwuv3dbWhjVr1iAzMxMrV66kb30/uY4I5Zz3OlSy17Gj"
    b"06dPb2SMdc/UWFVVRfddF2Dw4MF44IEHMH/+fEycOLHf9bp+bsj92zwjI0PY9QDHjh3D1q1b8cknn8j6"
    b"k0mttFqt623WGktLSxPcPbevy4HPA0jqenzmzBkacy1YcnIyCgoKkJmZiYyMDERGRvr0+oF6ObDVasXh"
    b"w4dx6NAhFBcXB8VFVWqi0+mQmprqvOh8aWmp26vF+gqAEwAmdD0+e/Ys2tvbhXWS9KTT6ZCeno7U1FQk"
    b"JycjJSUFN910E4xGI6KiomAwGGC321FfX9+94QTThCBdQWYymaDT6WA2m2G1WtHa2opvv/0W586dQ3V1"
    b"NU6fPo0TJ07Abrd7Lk78Eh4ejrFjx3Y/5pyfKCsrc7u72deMQC3OD+gYQGDZ7XYcOXIER44cUborPuGc"
    b"o6ysTNg9E0j/abXaHo8ZYy29PLXPg4AXnR/odLr+9YoQIgs322qvo7f6CoDTzg9ETt9MCAkcN9tqVW/P"
    b"7SsAerxIr9f3o0uEELkEJABoD4CQgcH1y5ox5nsA2O32G34CyDHlFCHEf4yxG76sbTbbmd6e32sAHDhw"
    b"oBVOewEajcbn89SEEHlFRka6nrGrur4tu9XnuT3OeYnzYyVu+EAI8Z6bbXRfX8/vMwA0Gk2PAIiKivKv"
    b"V4QQWbgGAGOspJenAvAcAKUAuoeaRUdH04AgQoIUY8z1S5rr9frSvl7T59a8b9++Rs750e4nazQwGAz9"
    b"6SMhJECMRmOPL2jO+dHPPvusz6urPH6dM8Z63HM5Li7O7w4SQgLHddvUaDR/8fQajwGg0Wg+4Jx3z8hg"
    b"NBpvGGtMCFGWVqvtsXfOOZfCwsI+8PQ6jwFQUlJSxxjrnuCOMYaYmBi/O0oIES8mJqbH7j9jbM/evXu/"
    b"8/Q6r47occ43OD+Oj4/3uYOEkMBxs01ucPc8V14FgM1m2wbgStfjiIgIOhhISJAwGo2IiIhwXnSlo6Pj"
    b"U29e61UAHDx4sI1z/qbzsqFDh3rfQ0JIwAwZMsR1UdHBgwe9mnzS65P6UVFR/wPgqtNjGhhEiMKio6Nd"
    b"t8Ordrv9f7x9vdcBsGvXrhYA/+28zGQy0QVChCiEMYZhw4a5Lnurr7H/rnwa1tfZ2fkHAN3zQUdFRdG4"
    b"AEIUEhsb6/rt38w5/4MvNXwKgIqKiqsAVjovM5lMNC6AEJlptVoMHz7cdfELpaWlPt1MweeB/UOGDHkb"
    b"QPfwYK1WSwcECZHZ0KFDe3zxcs7/MWTIkP/1tY5fP+DvvPPOXqCZJQAABNlJREFUDM75QefX19TUwGw2"
    b"+1OOEOIDg8GApKQk50Vco9FklpSUHPa1ll/77jU1NXVJSUnDAUzuWmY0GtHc3Ez3cSMkgHQ6HUaPHu16"
    b"Ve7qzz///B1/6vXn2t4VcJo5WKvVYtSoUXRWgJAAYYwhMTHR9ZjbaQDP+VvT7wAoLS01a7XaBwF03y4o"
    b"Ojr6htMShBAxhg0b5nrUv12SpMLS0lK/f3v36/D9+fPnG5KSkhoA3Nu1LCoqCpIkwWq19qc0IcRJQkKC"
    b"u4PtPy4rK9vdn7r9Pn9XU1NzdPTo0ckAuu89ZjAYYLPZ6F6ChAgQFxeHESNG9FjGGHu/tLT0V/2tLWJ+"
    b"Lx4REfGk6wSiI0eOhNFoFFCekNBlNBoxcuRI18X7IiIinoTTdH3+EnbELisry6jT6T4HMKlrGeccdXV1"
    b"aGryaWwCIQTXvvlHjhzpemD9iN1uv9OX4b59EXrIftasWUNtNlsFgLHOy+vr63HlypVeXkUIcZWQkACT"
    b"yeS6+BuHw5G1f//+y6LaETqG99y5c5bk5OTtnPM5ALpnKDAYDNBoNLBYLCKbI0R1GGMwmUzuDvh9o9Fo"
    b"ZpaVlXmc5cen9kQW63J9T+CvcPo5AABWqxW1tbWw2+2BaJaQAU2n0yExMdHdZfZH9Hr9PXv27Lkkus2A"
    b"jdq5fkxgK4A85+UOhwO1tbU0bJgQJwaDwd0gHwDYZ7fb54n6ze8qYJfx1dbW2saPH/+Xzs7OJADpXcs1"
    b"Gg3i4uKg1WrR1tYGzvt9IJOQAUur1cJkMmHEiBE33HSHMfZ+ZGTkD0tKSgI2qEaOcbssNzf3CQB/BNBj"
    b"4jKHw4GLFy+iubmZgoCEFMYYYmNjMXz4cHff+u0AflJaWvouBJzq67MfgSzuLC8vL93hcHwEINX1f1ar"
    b"FQ0NDXSQkISEriHzvUypVyVJ0oPl5eUn5eiLrFfu5ObmGgC8DuBpd21brVZcunSJjg8QVTIajRgyZEhv"
    b"Gz4HsBrAc/0Z2+8rRS7dmzFjxhSHw/E2Y+wOd/9vb29HY2MjWlpa4HA45O4eIcJotVrExMQgPj7ederu"
    b"bpzzf2i12mf8uZ6/vxS7drewsFB7+fLlHwP4LYBYd8+RJAlmsxlNTU1obW2l4wRkQGCMwWg0Ii4urnsM"
    b"TC+aAbwwZMiQ/928ebMi33SKX7yfnZ09SKfT/Qfn/FkAg3p7XtcVhhaLBRaLhc4gkKDBGENkZCSio6O7"
    b"p+nuY6MHgKuMsbc453/wdQ4/0RQPgC75+fkxbW1tSwEsB5Dg6fmSJKGjowM2mw0dHR3o6OiA3W6Hw+GA"
    b"JEndfxQSpD8YY9BoNN1/Wq0WOp0O4eHhCA8Ph16vR3h4uKcNvstlAEWRkZFvX59mX3FBEwBdpk6dGhke"
    b"Hn4fgEWc85mMMRFXLBKiCM65xBjbA2BDR0fHp97esUcuQRcAzmbOnDmis7PzEUmS/o0xdjuCvL+EXMc5"
    b"50c1Gs1fwsLCPvDmLr1KGTAbVF5eXrwkSdM55zNwbXhxmtJ9IsRJFYB9jLESvV5f+tlnn32vdIe8MWAC"
    b"wFVWVpZRr9eP45yn4VoYpAEwcc5jGGNGADGccyNjTK9sT8lAxjm3McZaAbRwzlsZYy0A6nFtg69ijFXZ"
    b"bLYzgRqrTwghhBBCCCGEEEIIIYQQ4p//B3D5onOocv2IAAAAAElFTkSuQmCC"
)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-icon":
        Path(sys.argv[2]).write_bytes(b64decode(ICON_ICO))
    else:
        sys.exit(main())
