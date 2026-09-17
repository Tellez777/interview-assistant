"""Enumeración de dispositivos de audio: micrófono y loopback WASAPI.

El loopback es lo que permite capturar lo que dice el entrevistador (el
audio que sale por los parlantes vía Zoom/Meet/Teams), no solo lo que
entra por el micrófono. Sin esto el sistema solo "escucharía" al usuario.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyaudiowpatch as pyaudio


@dataclass
class DeviceInfo:
    index: int
    name: str
    sample_rate: int
    channels: int
    is_loopback: bool


def list_input_devices() -> list[DeviceInfo]:
    """Micrófonos y demás dispositivos de entrada estándar (no loopback)."""
    devices: list[DeviceInfo] = []
    with pyaudio.PyAudio() as p:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0 and not info.get("isLoopbackDevice", False):
                devices.append(
                    DeviceInfo(
                        index=info["index"],
                        name=info["name"],
                        sample_rate=int(info["defaultSampleRate"]),
                        channels=int(info["maxInputChannels"]),
                        is_loopback=False,
                    )
                )
    return devices


def list_loopback_devices() -> list[DeviceInfo]:
    """Dispositivos WASAPI loopback: 'lo que suena' por cada salida."""
    devices: list[DeviceInfo] = []
    with pyaudio.PyAudio() as p:
        for info in p.get_loopback_device_info_generator():
            devices.append(
                DeviceInfo(
                    index=info["index"],
                    name=info["name"],
                    sample_rate=int(info["defaultSampleRate"]),
                    channels=int(info["maxInputChannels"]),
                    is_loopback=True,
                )
            )
    return devices


def get_default_loopback() -> DeviceInfo:
    """El loopback del dispositivo de salida por defecto (parlantes/audífonos)."""
    with pyaudio.PyAudio() as p:
        info = p.get_default_wasapi_loopback()
        return DeviceInfo(
            index=info["index"],
            name=info["name"],
            sample_rate=int(info["defaultSampleRate"]),
            channels=int(info["maxInputChannels"]),
            is_loopback=True,
        )


def get_default_input() -> DeviceInfo:
    """El micrófono por defecto del sistema."""
    with pyaudio.PyAudio() as p:
        info = p.get_default_input_device_info()
        return DeviceInfo(
            index=info["index"],
            name=info["name"],
            sample_rate=int(info["defaultSampleRate"]),
            channels=int(info["maxInputChannels"]),
            is_loopback=False,
        )
