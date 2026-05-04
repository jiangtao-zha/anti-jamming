"""
抗干扰算法统一接口包。

所有抗干扰算法通过 adapters.py 提供统一的调用接口:
    processed_signal, processed_template = antijam_func(radar_par, **kwargs)
"""

from anti_jamming.adapters import (
    ANTIJAM_ADAPTERS,
    get_antijam_func,
    list_antijam_types,
    wln_adapter,
    fdc_adapter,
    adapt_filter_adapter,
    wave_agile_adapter,
    frequency_agile_adapter,
    frft_adapter,
    qpzh_adapter,
    fastslow_adapter,
)
