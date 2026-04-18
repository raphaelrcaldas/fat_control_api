import sys
import time

from fcontrol_api.settings import Settings

_start = time.perf_counter()
_last = _start


def mark(label: str, *, threshold_ms: float = 0.0) -> None:
    """Loga o tempo desde o start e desde o último mark.

    A flag BOOT_PROFILE é lida a cada chamada via Settings() — permite
    habilitar o profiler sem reiniciar o processo e mantém consistência
    com o resto da config da app.

    Args:
        label: Nome da fase.
        threshold_ms: Se > 0, só imprime quando o delta exceder esse valor.
    """
    global _last  # noqa: PLW0603
    if not Settings().BOOT_PROFILE:
        return
    now = time.perf_counter()
    delta_ms = (now - _last) * 1000
    if threshold_ms and delta_ms < threshold_ms:
        _last = now
        return
    total_s = now - _start
    # stderr: não interfere com stdout (que pode ser capturado por
    # pipes/scripts) e ainda aparece normalmente nos logs do Fly.
    print(
        f'[BOOT +{total_s:6.3f}s  d+{delta_ms:7.1f}ms] {label}',
        file=sys.stderr,
        flush=True,
    )
    _last = now


def reset() -> None:
    """Reseta o relógio (útil se quiser medir só o lifespan)."""
    global _start, _last  # noqa: PLW0603
    _start = _last = time.perf_counter()
