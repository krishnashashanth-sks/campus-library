"""Multi-symbology barcode and QR decoder for QuickScanDialog.

Combines pure-NumPy/OpenCV Code 128 (edge-to-edge ink-spread-invariant
decoding + mod-103 checksum verification) and Code 39 decoders with
OpenCV's QRCodeDetector and BarcodeDetector (EAN-8/13, UPC-A/E), plus
gradient-based barcode region localization for rotated or off-center labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import barcode.charsets.code128 as _c128
import cv2
import numpy as np


@dataclass(frozen=True)
class BarcodeScanResult:
    """Represents a verified barcode or QR detection in an image frame."""

    code: str
    symbology: str
    points: Optional[np.ndarray] = None  # Shape (N, 2) float32/int32 in frame coords


def _bitstring_to_runs(bits: str) -> tuple[int, ...]:
    runs: list[int] = []
    cur = bits[0]
    count = 0
    for ch in bits:
        if ch == cur:
            count += 1
        else:
            runs.append(count)
            cur = ch
            count = 1
    runs.append(count)
    return tuple(runs)


# Precompute exact Code 128 symbol tables from python-barcode's authoritative spec.
_CODE128_RUNS: tuple[tuple[int, ...], ...] = tuple(
    _bitstring_to_runs(bits) for bits in _c128.CODES
)
# Edge-to-edge distances (b1+s1, s1+b2, b2+s2, s2+b3) uniquely identify all 106 symbols.
_CODE128_EDGE_MAP: dict[tuple[int, int, int, int], int] = {}
_CODE128_EDGE_ARRAY = np.zeros((106, 4), dtype=np.float32)
_CODE128_RUN_ARRAY = np.zeros((106, 6), dtype=np.float32)

for _sym_idx, _r in enumerate(_CODE128_RUNS):
    _edges = (_r[0] + _r[1], _r[1] + _r[2], _r[2] + _r[3], _r[3] + _r[4])
    _CODE128_EDGE_MAP[_edges] = _sym_idx
    _CODE128_EDGE_ARRAY[_sym_idx] = _edges
    _CODE128_RUN_ARRAY[_sym_idx] = _r

# Stop pattern = 11000111010 + trailing bar 11 -> (2, 3, 3, 1, 1, 1, 2)
_CODE128_STOP_RUNS = (2, 3, 3, 1, 1, 1, 2)
_CODE128_STOP_EDGES = (5, 6, 4, 2, 2, 3)

# Reverse character tables for Code 128 Sets A and B (values 0..95)
_CODE128_SET_A_CHARS: dict[int, str] = {}
for _v, _ch in enumerate(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_"
):
    _CODE128_SET_A_CHARS[_v] = _ch
for _v in range(64, 96):
    _CODE128_SET_A_CHARS[_v] = chr(_v - 64)

_CODE128_SET_B_CHARS: dict[int, str] = {
    _v: chr(_v + 32) for _v in range(95)
}
_CODE128_SET_B_CHARS[95] = "\x7f"

# Code 39 table: 9-bit wide/narrow patterns (B S B S B S B S B), '1' = wide, '0' = narrow
_CODE39_PATTERNS: dict[str, str] = {
    "000110100": "0",
    "100100001": "1",
    "001100001": "2",
    "101100000": "3",
    "000110001": "4",
    "100110000": "5",
    "001110000": "6",
    "000100101": "7",
    "100100100": "8",
    "001100100": "9",
    "100001001": "A",
    "001001001": "B",
    "101001000": "C",
    "000011001": "D",
    "100011000": "E",
    "001011000": "F",
    "000001101": "G",
    "100001100": "H",
    "001001100": "I",
    "000011100": "J",
    "100000011": "K",
    "001000011": "L",
    "101000010": "M",
    "000010011": "N",
    "100010010": "O",
    "001010010": "P",
    "000000111": "Q",
    "100000110": "R",
    "001000110": "S",
    "000010110": "T",
    "110000001": "U",
    "011000001": "V",
    "111000000": "W",
    "010010001": "X",
    "110010000": "Y",
    "011010000": "Z",
    "010000101": "-",
    "110000100": ".",
    "011000100": " ",
    "010101000": "$",
    "010100010": "/",
    "010001010": "+",
    "000101010": "%",
    "010010100": "*",
}


def _extract_runs_from_binary(binary_line: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert a 1D boolean/uint8 line (True/1 = dark bar, False/0 = white space) into runs.

    Returns:
        (is_dark, run_lengths, run_starts)
    """
    arr = np.asarray(binary_line, dtype=np.uint8)
    if arr.size < 20:
        empty = np.empty(0, dtype=np.int32)
        return np.empty(0, dtype=bool), empty, empty
    changes = np.flatnonzero(arr[1:] != arr[:-1]) + 1
    starts = np.concatenate(([0], changes))
    ends = np.concatenate((changes, [arr.size]))
    lengths = ends - starts
    is_dark = arr[starts].astype(bool)
    return is_dark, lengths.astype(np.int32), starts.astype(np.int32)


_START_EDGES = frozenset({
    (3, 2, 5, 5),  # 103 Start A: (2,1,1,4,1,2)
    (3, 2, 3, 3),  # 104 Start B: (2,1,1,2,1,4)
    (3, 2, 3, 5),  # 105 Start C: (2,1,1,2,3,2)
})


def _match_code128_start(runs6: np.ndarray) -> Optional[int]:
    """Fast O(1) check for Code 128 Start A/B/C without full table scan."""
    r0, r1, r2, r3, r4, r5 = (
        int(runs6[0]), int(runs6[1]), int(runs6[2]),
        int(runs6[3]), int(runs6[4]), int(runs6[5]),
    )
    total = r0 + r1 + r2 + r3 + r4 + r5
    if total < 11:
        return None
    inv = 11.0 / total
    # All Start codes begin with bar=2, space=1, bar=1 -> e1=3, e2=2
    e1 = (r0 + r1) * inv
    if abs(e1 - 3.0) > 0.65:
        return None
    e2 = (r1 + r2) * inv
    if abs(e2 - 2.0) > 0.65:
        return None
    e3 = (r2 + r3) * inv
    e4 = (r3 + r4) * inv
    q = (3, 2, int(round(e3)), int(round(e4)))
    if q not in _START_EDGES:
        return None
    if abs(e3 - q[2]) + abs(e4 - q[3]) > 0.9:
        return None
    sym = _CODE128_EDGE_MAP.get(q)
    return sym if sym in (103, 104, 105) else None


def _match_code128_symbol(runs6: np.ndarray, allow_fuzzy: bool = True) -> tuple[Optional[int], float]:
    """Match a 6-run (bar,space,bar,space,bar,space) segment to a Code 128 symbol (0..105)."""
    total = float(int(runs6[0]) + int(runs6[1]) + int(runs6[2]) + int(runs6[3]) + int(runs6[4]) + int(runs6[5]))
    if total < 8.0:
        return None, 999.0

    inv = 11.0 / total
    e1 = (int(runs6[0]) + int(runs6[1])) * inv
    e2 = (int(runs6[1]) + int(runs6[2])) * inv
    e3 = (int(runs6[2]) + int(runs6[3])) * inv
    e4 = (int(runs6[3]) + int(runs6[4])) * inv

    q = (int(round(e1)), int(round(e2)), int(round(e3)), int(round(e4)))
    sym = _CODE128_EDGE_MAP.get(q)
    if sym is not None:
        err = (
            abs(e1 - q[0])
            + abs(e2 - q[1])
            + abs(e3 - q[2])
            + abs(e4 - q[3])
        )
        if err <= 1.55:
            return sym, float(err)

    if not allow_fuzzy:
        return None, 999.0

    # Fallback nearest-neighbor in edge space for slightly skewed/blurred scans
    vec = np.array([e1, e2, e3, e4], dtype=np.float32)
    dists = np.abs(_CODE128_EDGE_ARRAY - vec).sum(axis=1)
    best_idx = int(np.argmin(dists))
    best_dist = float(dists[best_idx])
    if best_dist <= 1.85:
        norm_runs = runs6.astype(np.float32) * inv
        run_err = float(np.abs(_CODE128_RUN_ARRAY[best_idx] - norm_runs).max())
        if run_err <= 1.35:
            return best_idx, best_dist
    return None, 999.0


def _is_code128_stop(runs7: np.ndarray) -> bool:
    """Check whether a 7-run (B S B S B S B) segment matches Code 128 Stop (13 modules)."""
    total = float(runs7.sum())
    if total < 10.0:
        return False
    scale = 13.0 / total
    # Edge-to-edge check on first 6 pairs: expected (5, 6, 4, 2, 2, 3)
    e = np.array([
        runs7[0] + runs7[1],
        runs7[1] + runs7[2],
        runs7[2] + runs7[3],
        runs7[3] + runs7[4],
        runs7[4] + runs7[5],
        runs7[5] + runs7[6],
    ], dtype=np.float32) * scale
    expected = np.array(_CODE128_STOP_EDGES, dtype=np.float32)
    if float(np.abs(e - expected).sum()) > 2.2:
        return False
    norm = runs7.astype(np.float32) * scale
    if float(np.abs(norm - np.array(_CODE128_STOP_RUNS, dtype=np.float32)).max()) > 1.35:
        return False
    return True


def _decode_code128_values(start_code: int, values: list[int]) -> Optional[str]:
    """Translate Code 128 symbol integers (excluding start, checksum, stop) to ASCII text."""
    if not values:
        return None

    if start_code == 103:
        charset = "A"
    elif start_code == 104:
        charset = "B"
    elif start_code == 105:
        charset = "C"
    else:
        return None

    out: list[str] = []
    shift_once = False
    for val in values:
        if val < 0 or val > 102:
            return None

        active = charset
        if shift_once:
            active = "B" if charset == "A" else ("A" if charset == "B" else charset)
            shift_once = False

        if active == "C":
            if val <= 99:
                out.append(f"{val:02d}")
            elif val == 100:
                charset = "B"
            elif val == 101:
                charset = "A"
            elif val == 102:
                continue  # FNC1
            else:
                return None
        elif active == "B":
            if val <= 95:
                out.append(_CODE128_SET_B_CHARS[val])
            elif val == 98:
                shift_once = True
            elif val == 99:
                charset = "C"
            elif val == 101:
                charset = "A"
            elif val in (96, 97, 100, 102):
                continue  # FNC codes
        elif active == "A":
            if val <= 95:
                out.append(_CODE128_SET_A_CHARS[val])
            elif val == 98:
                shift_once = True
            elif val == 99:
                charset = "C"
            elif val == 100:
                charset = "B"
            elif val in (96, 97, 101, 102):
                continue

    text = "".join(out).strip()
    if not text:
        return None
    # Reject control-only garbage
    if not all(32 <= ord(ch) <= 126 for ch in text):
        return None
    return text


def _decode_code128_from_runs(
    is_dark: np.ndarray,
    lengths: np.ndarray,
    starts: np.ndarray,
) -> Optional[tuple[str, int, int]]:
    """Attempt to decode Code 128 from run-length arrays.

    Returns (decoded_text, start_pixel, end_pixel) or None.
    """
    n = lengths.size
    if n < 25:  # Start(6) + Data(6) + Check(6) + Stop(7) = 25 runs minimum
        return None

    # Find candidate dark-bar starts matching Start A/B/C
    for i in range(0, n - 24):
        if not is_dark[i]:
            continue
        start_runs = lengths[i : i + 6]
        start_sym = _match_code128_start(start_runs)
        if start_sym is None:
            continue

        # Optional quiet-zone check if preceding space exists
        if i > 0 and not is_dark[i - 1]:
            mod_est = float(start_runs.sum()) / 11.0
            if lengths[i - 1] < max(1.5, mod_est * 2.5):
                # Allow slight cropping only if at very edge of line
                if i > 1:
                    continue

        symbols: list[int] = []
        pos = i + 6
        found_stop = False
        while pos + 6 <= n:
            if pos + 7 <= n and len(symbols) >= 2 and _is_code128_stop(lengths[pos : pos + 7]):
                found_stop = True
                end_px = int(starts[pos + 6] + lengths[pos + 6])
                break
            sym, _ = _match_code128_symbol(lengths[pos : pos + 6])
            if sym is None or sym >= 103:
                break
            symbols.append(sym)
            pos += 6

        if not found_stop or len(symbols) < 2:
            continue

        payload_syms = symbols[:-1]
        check_sym = symbols[-1]
        calc = start_sym
        for idx, val in enumerate(payload_syms, start=1):
            calc += idx * val
        if (calc % 103) != check_sym:
            continue

        text = _decode_code128_values(start_sym, payload_syms)
        if text:
            return text, int(starts[i]), end_px

    return None


def _decode_code39_from_runs(
    is_dark: np.ndarray,
    lengths: np.ndarray,
    starts: np.ndarray,
) -> Optional[tuple[str, int, int]]:
    """Decode Code 39 (*...*) from run-length arrays."""
    n = lengths.size
    if n < 29:  # '*' + >=1 char + '*' = 3*9 + 2 gaps = 29 runs
        return None

    def _classify_9(seg: np.ndarray) -> Optional[str]:
        s = sorted(int(v) for v in seg)
        narrow_max = s[5]
        wide_min = s[6]
        if narrow_max <= 0 or wide_min * 10 < narrow_max * 16:
            return None
        thresh = (narrow_max + wide_min) * 0.5
        bits = "".join("1" if int(v) >= thresh else "0" for v in seg)
        return _CODE39_PATTERNS.get(bits)

    for i in range(0, n - 28):
        if not is_dark[i]:
            continue
        seg0 = lengths[i : i + 9]
        # '*' pattern is '010010100' -> wide bars/spaces at indices 1, 4, 6
        if seg0[1] <= seg0[0] or seg0[4] <= seg0[0] or seg0[6] <= seg0[0]:
            continue
        if _classify_9(seg0) != "*":
            continue

        chars: list[str] = []
        pos = i + 9
        closed = False
        end_px = 0
        while pos + 10 <= n:
            # Inter-character gap must be a narrow white space
            gap = lengths[pos]
            char_seg = lengths[pos + 1 : pos + 10]
            ch = _classify_9(char_seg)
            if ch is None:
                break
            if gap > float(np.min(char_seg)) * 4.5:
                break
            if ch == "*":
                closed = True
                end_px = int(starts[pos + 9] + lengths[pos + 9])
                break
            chars.append(ch)
            pos += 10

        if closed and len(chars) >= 2:
            text = "".join(chars).strip()
            if text:
                return text, int(starts[i]), end_px

    return None


def _binarize_scanline_variants(gray_band: np.ndarray) -> list[np.ndarray]:
    """Generate robust binarized 1D profiles (1=dark, 0=light) for a horizontal band."""
    if gray_band.ndim == 2 and gray_band.shape[0] > 1:
        profile = np.median(gray_band, axis=0).astype(np.uint8)
    else:
        profile = gray_band.reshape(-1).astype(np.uint8)

    if profile.size < 32:
        return []

    # Fast bailout on blank/flat/very low-contrast scanlines
    if int(profile.max()) - int(profile.min()) < 26:
        return []

    variants: list[np.ndarray] = []

    # 1) Otsu threshold on 1D profile
    col = profile.reshape(1, -1)
    _, otsu = cv2.threshold(col, 0, 1, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    variants.append(otsu.ravel())

    # 2) Upsampled 2x cubic + Otsu (helps low-res webcam narrow 1-module bars)
    up = cv2.resize(col, (profile.size * 2, 1), interpolation=cv2.INTER_CUBIC)
    _, otsu_up = cv2.threshold(up, 0, 1, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    variants.append(otsu_up.ravel())

    # 3) Local sliding-window adaptive threshold (handles shadows / uneven lighting)
    win = max(31, (profile.size // 8) | 1)
    local_mean = cv2.boxFilter(
        up.astype(np.float32), -1, (win * 2, 1), borderType=cv2.BORDER_REPLICATE
    ).ravel()
    adaptive = (up.ravel().astype(np.float32) < (local_mean - 4.0)).astype(np.uint8)
    variants.append(adaptive)

    return variants


def _scan_band_for_1d(gray_band: np.ndarray, include_code39: bool = True) -> Optional[tuple[str, str, int, int, float]]:
    """Try decoding Code 128 (or Code 39) on a horizontal grayscale band.

    Returns (code, symbology, x1, x2, scale_x) where x1, x2 are in original band pixels.
    """
    variants = _binarize_scanline_variants(gray_band)
    for idx, binary in enumerate(variants):
        scale_x = 0.5 if idx >= 1 else 1.0
        for reverse in (False, True):
            line = binary[::-1] if reverse else binary
            is_dark, lengths, starts = _extract_runs_from_binary(line)
            hit = _decode_code128_from_runs(is_dark, lengths, starts)
            if hit is not None:
                text, s_px, e_px = hit
                if reverse:
                    total_w = line.size
                    s_px, e_px = total_w - e_px, total_w - s_px
                return (
                    text,
                    "CODE128",
                    int(s_px * scale_x),
                    int(e_px * scale_x),
                    scale_x,
                )
            if include_code39:
                hit39 = _decode_code39_from_runs(is_dark, lengths, starts)
                if hit39 is not None:
                    text, s_px, e_px = hit39
                    if reverse:
                        total_w = line.size
                        s_px, e_px = total_w - e_px, total_w - s_px
                    return (
                        text,
                        "CODE39",
                        int(s_px * scale_x),
                        int(e_px * scale_x),
                        scale_x,
                    )
    return None


def _find_barcode_candidate_boxes(gray: np.ndarray) -> list[tuple[np.ndarray, tuple[float, float], tuple[float, float], float]]:
    """Locate likely 1D barcode regions using gradient asymmetry + morphology."""
    h, w = gray.shape[:2]
    if h < 40 or w < 40:
        return []

    # Work on a downscaled copy for speed on HD webcams
    max_dim = 640.0
    scale = min(1.0, max_dim / max(h, w))
    small = (
        cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else gray
    )

    grad_x = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)

    candidates = []
    for mode, diff in (("H", cv2.subtract(np.abs(grad_x), np.abs(grad_y))), ("V", cv2.subtract(np.abs(grad_y), np.abs(grad_x)))):
        blurred = cv2.GaussianBlur(cv2.convertScaleAbs(diff), (9, 9), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7) if mode == "H" else (7, 21))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        closed = cv2.erode(closed, None, iterations=2)
        closed = cv2.dilate(closed, None, iterations=3)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:3]
        for c in contours:
            area = cv2.contourArea(c)
            if area < (small.shape[0] * small.shape[1]) * 0.012:
                continue
            rect = cv2.minAreaRect(c)
            (cx, cy), (rw, rh), angle = rect
            if rw < 15 or rh < 15:
                continue
            box = cv2.boxPoints(rect) / scale
            candidates.append((box, (cx / scale, cy / scale), (rw / scale, rh / scale), angle))

    return candidates


def _crop_and_deskew(gray: np.ndarray, center: tuple[float, float], size: tuple[float, float], angle: float) -> Optional[np.ndarray]:
    """Rotate and crop a candidate barcode region so bars become vertical."""
    rw, rh = size
    if rw < rh:
        rw, rh = rh, rw
        angle += 90.0

    pad_w = rw * 1.22
    pad_h = rh * 1.25
    h, w = gray.shape[:2]

    # Cap crop size to avoid excessive rotation work
    rot = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(gray, rot, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    cx, cy = center
    x1 = max(0, int(cx - pad_w * 0.5))
    y1 = max(0, int(cy - pad_h * 0.5))
    x2 = min(w, int(cx + pad_w * 0.5))
    y2 = min(h, int(cy + pad_h * 0.5))
    if x2 - x1 < 30 or y2 - y1 < 12:
        return None
    return rotated[y1:y2, x1:x2]


class BarcodeDecoder:
    """Thread-safe multi-symbology barcode & QR decoder."""

    def __init__(self) -> None:
        self._qr_detector = cv2.QRCodeDetector() if hasattr(cv2, "QRCodeDetector") else None
        self._cv_barcode_detector = (
            cv2.barcode.BarcodeDetector() if hasattr(cv2, "barcode") else None
        )

    @staticmethod
    def _normalize_payload(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        # Strip common library QR prefixes if used (e.g., BOOK:10001)
        upper = text.upper()
        for prefix in ("BOOK:", "BOOK_ID:", "BOOKID:", "ID:"):
            if upper.startswith(prefix):
                candidate = text[len(prefix):].strip()
                if candidate:
                    return candidate
        return text

    def _try_opencv_qr(self, gray: np.ndarray) -> Optional[BarcodeScanResult]:
        if self._qr_detector is None:
            return None
        try:
            text, pts, _ = self._qr_detector.detectAndDecode(gray)
            norm = self._normalize_payload(text)
            if norm:
                poly = pts[0].astype(np.int32) if pts is not None and len(pts) > 0 else None
                return BarcodeScanResult(norm, "QR", poly)
        except Exception:
            pass
        return None

    def _try_opencv_ean_upc(self, gray: np.ndarray) -> Optional[BarcodeScanResult]:
        if self._cv_barcode_detector is None:
            return None
        try:
            if hasattr(self._cv_barcode_detector, "detectAndDecodeWithType"):
                ok, infos, types, pts = self._cv_barcode_detector.detectAndDecodeWithType(gray)
                if ok and infos:
                    for idx, info in enumerate(infos):
                        norm = self._normalize_payload(info)
                        if norm:
                            sym = str(types[idx]) if types and idx < len(types) else "EAN/UPC"
                            poly = (
                                pts[idx].astype(np.int32)
                                if pts is not None and idx < len(pts)
                                else None
                            )
                            return BarcodeScanResult(norm, sym.upper(), poly)
            else:
                res = self._cv_barcode_detector.detectAndDecode(gray)
                if res and len(res) >= 1 and res[0]:
                    val = res[0]
                    if isinstance(val, (list, tuple)):
                        for item in val:
                            norm = self._normalize_payload(item)
                            if norm:
                                return BarcodeScanResult(norm, "EAN/UPC", None)
                    else:
                        norm = self._normalize_payload(val)
                        if norm:
                            return BarcodeScanResult(norm, "EAN/UPC", None)
        except Exception:
            pass
        return None

    def decode(self, frame: np.ndarray, thorough: bool = False) -> Optional[BarcodeScanResult]:
        """Decode a barcode or QR code from a BGR or grayscale image frame."""
        if frame is None or frame.size == 0:
            return None

        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        h, w = gray.shape[:2]
        if h < 16 or w < 16:
            return None

        # 1) Fast 1D scanline sweep across horizontal bands (centered & full width)
        band_h = max(3, min(9, h // 40))
        y_fractions = (
            (0.50, 0.40, 0.60, 0.30, 0.70, 0.20, 0.80)
            if not thorough
            else (0.50, 0.42, 0.58, 0.33, 0.67, 0.24, 0.76, 0.15, 0.85)
        )
        for yf in y_fractions:
            yc = int(h * yf)
            y0 = max(0, yc - band_h // 2)
            y1 = min(h, y0 + band_h)
            hit = _scan_band_for_1d(gray[y0:y1, :], include_code39=True)
            if hit is not None:
                code, sym, x1, x2, _ = hit
                box = np.array(
                    [[x1, max(0, yc - 22)], [x2, max(0, yc - 22)], [x2, min(h - 1, yc + 22)], [x1, min(h - 1, yc + 22)]],
                    dtype=np.int32,
                )
                return BarcodeScanResult(self._normalize_payload(code), sym, box)

        # 2) Vertical scanline sweep for 90-degree rotated barcodes
        for xf in (0.50, 0.35, 0.65):
            xc = int(w * xf)
            x0 = max(0, xc - band_h // 2)
            x1 = min(w, x0 + band_h)
            band_rot = gray[:, x0:x1].T
            hit = _scan_band_for_1d(band_rot, include_code39=True)
            if hit is not None:
                code, sym, y1, y2, _ = hit
                box = np.array(
                    [[max(0, xc - 22), y1], [min(w - 1, xc + 22), y1], [min(w - 1, xc + 22), y2], [max(0, xc - 22), y2]],
                    dtype=np.int32,
                )
                return BarcodeScanResult(self._normalize_payload(code), sym, box)

        # 3) QR Code detection (very fast on grayscale)
        qr_hit = self._try_opencv_qr(gray)
        if qr_hit is not None:
            return qr_hit

        # 4) Gradient-based ROI localization & deskewing for tilted/small 1D barcodes
        boxes = _find_barcode_candidate_boxes(gray)
        for poly, center, size, angle in boxes:
            crop = _crop_and_deskew(gray, center, size, angle)
            if crop is None:
                continue
            ch, cw = crop.shape[:2]
            # Enhance local contrast inside ROI
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            crop_eq = clahe.apply(crop)
            for src_crop in (crop, crop_eq):
                for yf in (0.50, 0.35, 0.65, 0.25, 0.75):
                    yc = int(ch * yf)
                    y0 = max(0, yc - 2)
                    y1 = min(ch, yc + 3)
                    hit = _scan_band_for_1d(src_crop[y0:y1, :], include_code39=True)
                    if hit is not None:
                        code, sym, _, _, _ = hit
                        return BarcodeScanResult(
                            self._normalize_payload(code),
                            sym,
                            poly.astype(np.int32),
                        )

        # 5) OpenCV EAN/UPC detector (with contrast-enhanced fallback if thorough)
        ean_hit = self._try_opencv_ean_upc(gray)
        if ean_hit is not None:
            return ean_hit

        if thorough:
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            for fn in (self._try_opencv_qr, self._try_opencv_ean_upc):
                hit = fn(enhanced)
                if hit is not None:
                    return hit

        return None


def decode_image_file(file_path: str) -> Optional[BarcodeScanResult]:
    """Load an image file from disk and decode any barcode or QR code in it."""
    img = cv2.imread(str(file_path))
    if img is None:
        return None
    decoder = BarcodeDecoder()
    # Try raw, padded (in case tight-cropped PNG lacks quiet zone), and sharpened
    res = decoder.decode(img, thorough=True)
    if res is not None:
        return res
    padded = cv2.copyMakeBorder(img, 36, 36, 36, 36, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return decoder.decode(padded, thorough=True)
