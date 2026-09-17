"""Traducción EN→ES con `argostranslate` (CTranslate2 por debajo, en CPU).

No corre en GPU a propósito: la GPU la ocupa el ASR (ver `app/asr/`), y
esto es rápido de sobra en CPU (~50 ms medido en esta laptop una vez
cargado el paquete de idioma — ver plan, sección M4).

El paquete de idioma se descarga una sola vez (`ensure_package_installed`)
y queda cacheado en el home del usuario por argostranslate; no hace falta
volver a descargarlo en cada arranque del servidor.
"""

from __future__ import annotations

import argostranslate.package
import argostranslate.translate

FROM_CODE = "en"
TO_CODE = "es"

# Dirección inversa: la usa Live Mode en español (app.live.pipeline) para
# traducir la pregunta del entrevistador a inglés antes de buscar en el
# banco de respuestas, que está indexado en inglés.
FROM_CODE_ES = "es"
TO_CODE_ES = "en"

_ready_pairs: set[tuple[str, str]] = set()


def _ensure_pair_installed(from_code: str, to_code: str) -> None:
    """Descarga e instala el paquete `from_code`→`to_code` si todavía no
    está. Idempotente: seguro de llamar en cada arranque del servidor."""
    if (from_code, to_code) in _ready_pairs:
        return

    installed = argostranslate.package.get_installed_packages()
    if any(p.from_code == from_code and p.to_code == to_code for p in installed):
        _ready_pairs.add((from_code, to_code))
        return

    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    package = next(p for p in available if p.from_code == from_code and p.to_code == to_code)
    argostranslate.package.install_from_path(package.download())
    _ready_pairs.add((from_code, to_code))


def ensure_package_installed() -> None:
    """Compatibilidad hacia atrás: instala solo el paquete en→es."""
    _ensure_pair_installed(FROM_CODE, TO_CODE)


def translate_en_to_es(text: str) -> str:
    _ensure_pair_installed(FROM_CODE, TO_CODE)
    return argostranslate.translate.translate(text, FROM_CODE, TO_CODE)


def translate_es_to_en(text: str) -> str:
    _ensure_pair_installed(FROM_CODE_ES, TO_CODE_ES)
    return argostranslate.translate.translate(text, FROM_CODE_ES, TO_CODE_ES)
