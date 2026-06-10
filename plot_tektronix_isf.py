from pathlib import Path
import re
import numpy as np
import matplotlib.pyplot as plt


def read_tektronix_isf(path: Path):
    data = path.read_bytes()

    match = re.search(br":CURV\s*#(\d)(\d+)", data[:4096])
    if not match:
        raise ValueError("Bloco :CURV # não encontrado no arquivo ISF.")

    n_digits = int(match.group(1))
    n_bytes = int(match.group(2)[:n_digits])
    data_start = match.end()
    header = data[:data_start].decode("ascii", errors="ignore")

    def get_float(key: str, default=None):
        pattern = rf"(?:^|;|:)\s*{re.escape(key)}\s+([-+]?\d+(?:\.\d*)?(?:E[-+]?\d+)?)"
        found = re.search(pattern, header, re.IGNORECASE)
        return float(found.group(1)) if found else default

    byte_count = int(get_float("BYT_N", 1))
    bit_count = int(get_float("BIT_N", 8))

    if byte_count == 1 and bit_count == 8:
        raw = np.frombuffer(data[data_start:data_start + n_bytes], dtype=np.int8)
    elif byte_count == 2 and bit_count == 16:
        raw = np.frombuffer(data[data_start:data_start + n_bytes], dtype=">i2")
    else:
        raise ValueError(f"Formato não tratado: BYT_N={byte_count}, BIT_N={bit_count}")

    x_increment = get_float("XIN")
    x_zero = get_float("XZE", 0.0)
    point_offset = get_float("PT_O", 0.0)

    y_multiplier = get_float("YMU")
    y_offset = get_float("YOF", 0.0)
    y_zero = get_float("YZE", 0.0)

    time_s = x_zero + (np.arange(raw.size) - point_offset) * x_increment
    voltage_v = (raw.astype(float) - y_offset) * y_multiplier + y_zero

    return time_s, voltage_v, header


if __name__ == "__main__":
    isf_path = Path("T0039CH1.ISF")
    out_png = Path("T0039CH1_plot_reconstruido.png")

    time_s, voltage_v, header = read_tektronix_isf(isf_path)

    print(f"Pontos: {len(voltage_v)}")
    print(f"Tensão máxima: {voltage_v.max():.1f} V")
    print(f"Tensão mínima: {voltage_v.min():.1f} V")

    plt.figure(figsize=(12, 5))
    plt.plot(time_s * 1e6, voltage_v, linewidth=0.9)
    plt.xlabel("Tempo (µs)")
    plt.ylabel("Tensão CH1 (V)")
    plt.title("Reconstrução do sinal Tektronix")
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.show()
