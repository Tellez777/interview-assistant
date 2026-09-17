"""Arregla un problema de Windows con CTranslate2 (motor de faster-whisper):
las DLL de CUDA instaladas vía pip (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`)
quedan dentro de site-packages, pero el cargador de DLL de Windows no busca
ahí por defecto — a diferencia de Linux, donde el wheel usa RPATH. El
síntoma es exactamente "Library cublas64_12.dll is not found or cannot be
loaded" aunque el paquete esté instalado.

La solución es registrar esas carpetas con `os.add_dll_directory` ANTES de
importar `ctranslate2` (directa o indirectamente vía `faster_whisper`).
Se llama una sola vez por proceso, desde `app/asr/__init__.py` y desde
`scripts/check_env.py`.
"""

from __future__ import annotations

import os
from pathlib import Path

_done = False


def register_cuda_dll_dirs() -> None:
    global _done
    if _done or os.name != "nt":
        return
    _done = True

    try:
        import nvidia  # paquete "namespace" (sin __init__.py) de nvidia-cublas-cu12 / nvidia-cudnn-cu12
    except ImportError:
        return

    # Es un namespace package: no tiene __file__, solo __path__ (puede tener
    # varias entradas). Cada una es .../site-packages/nvidia.
    bin_dirs = [
        bin_dir
        for root in nvidia.__path__
        for bin_dir in Path(root).glob("*/bin")
    ]

    for bin_dir in bin_dirs:
        try:
            os.add_dll_directory(str(bin_dir))
        except OSError:
            pass

    # `os.add_dll_directory` solo lo respetan las llamadas a LoadLibraryEx
    # que pasan LOAD_LIBRARY_SEARCH_DEFAULT_DIRS. CTranslate2 (extensión
    # nativa) carga cublas/cudnn con una llamada de bajo nivel que NO pasa
    # ese flag, así que solo mirará el PATH del proceso. Sin esto, el
    # constructor del modelo funciona pero falla al primer uso real de la
    # GPU con "Library cublas64_12.dll is not found or cannot be loaded".
    extra_path = os.pathsep.join(str(d) for d in bin_dirs)
    if extra_path:
        os.environ["PATH"] = extra_path + os.pathsep + os.environ.get("PATH", "")
