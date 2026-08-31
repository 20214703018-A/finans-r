"""Advanced Pattern Extensions - Fibonacci, Harmonic Patterns, Elliott Wave helpers."""
import polars as pl
import numpy as np
from scipy.signal import find_peaks
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FibonacciLevel:
    level: float
    price: float
    description: str


@dataclass 
class HarmonicPattern:
    pattern_type: str  # Gartley, Butterfly, Bat, Crab, Shark
    point_x: int
    point_a: int
    point_b: int
    point_c: int
    point_d: int
    confidence: float
    ratios: dict


def calculate_fibonacci_retracement(start_price: float, end_price: float, is_uptrend: bool = True) -> List[FibonacciLevel]:
    """Fibonacci retracement seviyeleri hesapla."""
    diff = abs(end_price - start_price)
    
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]
    descriptions = [
        "Başlangıç", "23.6% Retracement", "38.2% Retracement", "50% Retracement",
        "61.8% Retracement (Golden Ratio)", "78.6% Retracement", 
        "100% (Tam Hareket)", "127.2% Extension", "161.8% Extension (Golden)"
    ]
    
    fib_levels = []
    for level, desc in zip(levels, descriptions):
        if is_uptrend:
            price = end_price - (diff * level)
        else:
            price = end_price + (diff * level)
        
        fib_levels.append(FibonacciLevel(
            level=level,
            price=round(price, 4),
            description=desc
        ))
    
    return fib_levels


def calculate_fibonacci_extensions(start_price: float, swing_high: float, swing_low: float, is_up: bool = True) -> List[float]:
    """Fibonacci extension hedefleri hesapla."""
    diff = abs(swing_high - swing_low)
    extensions = [0.618, 1.0, 1.272, 1.414, 1.618, 2.0, 2.618]
    
    ext_prices = []
    for ext in extensions:
        if is_up:
            price = swing_high + (diff * ext)
        else:
            price = swing_low - (diff * ext)
        ext_prices.append(round(price, 4))
    
    return ext_prices


def detect_fibonacci_clusters(df: pl.DataFrame, lookback: int = 100) -> Dict:
    """Birden fazla Fibonacci seviyesinin örtüştüğü bölgeleri tespit et (confluence zones)."""
    if df.height < lookback:
        return {"clusters": [], "strongest_zone": None}
    
    close = df["close"].to_numpy()[-lookback:]
    high = df["high"].to_numpy()[-lookback:]
    low = df["low"].to_numpy()[-lookback:]
    
    # Swing noktalarını bul
    highs_idx, _ = find_peaks(high, distance=5, prominence=np.std(high)*0.3)
    lows_idx, _ = find_peaks(-low, distance=5, prominence=np.std(low)*0.3)
    
    if len(highs_idx) < 2 or len(lows_idx) < 2:
        return {"clusters": [], "strongest_zone": None}
    
    # Son swing high ve low
    last_high_idx = highs_idx[-1]
    last_low_idx = lows_idx[-1]
    
    # Hangisi daha yeni?
    if last_high_idx > last_low_idx:
        # Uptrend → retracement hesapla
        start_price = low[last_low_idx]
        end_price = high[last_high_idx]
        fib_levels = calculate_fibonacci_retracement(start_price, end_price, is_uptrend=True)
    else:
        # Downtrend
        start_price = high[last_high_idx]
        end_price = low[last_low_idx]
        fib_levels = calculate_fibonacci_retracement(start_price, end_price, is_uptrend=False)
    
    # Mevcut fiyatın yakınındaki seviyeler
    current_price = close[-1]
    nearby_levels = []
    for fib in fib_levels:
        dist_pct = abs(fib.price - current_price) / current_price * 100
        if dist_pct < 2.0:  # %2 içindeki seviyeler
            nearby_levels.append({
                "level": fib.level,
                "price": fib.price,
                "distance_pct": round(dist_pct, 2),
                "description": fib.description
            })
    
    return {
        "clusters": nearby_levels,
        "strongest_zone": nearby_levels[0] if nearby_levels else None,
        "trend_direction": "up" if last_high_idx > last_low_idx else "down",
        "swing_high": float(high[last_high_idx]),
        "swing_low": float(low[last_low_idx])
    }


def detect_harmonic_patterns(df: pl.DataFrame, lookback: int = 200) -> List[HarmonicPattern]:
    """
    Harmonik pattern tespiti (Gartley, Butterfly, Bat, Crab, Shark).
    XABCD formasyonu ile Fibonacci oranlarını kontrol eder.
    """
    if df.height < 50:
        return []
    
    close = df["close"].to_numpy()[-lookback:]
    high = df["high"].to_numpy()[-lookback:]
    low = df["low"].to_numpy()[-lookback:]
    
    # Tüm swing noktalarını bul
    peaks_idx, _ = find_peaks(high, distance=10, prominence=np.std(high)*0.2)
    troughs_idx, _ = find_peaks(-low, distance=10, prominence=np.std(low)*0.2)
    
    patterns = []
    
    # 5 noktalı XABCD formasyonları ara
    # Bullish: X(high) -> A(low) -> B(high) -> C(low) -> D(high, lower than X)
    # Bearish: X(low) -> A(high) -> B(low) -> C(high) -> D(low, higher than X)
    
    for i in range(len(peaks_idx) - 4):
        # Potansiyel bearish harmonic pattern (X tepe)
        x_idx = peaks_idx[i]
        
        # Sonraki dip (A)
        subsequent_troughs = troughs_idx[(troughs_idx > x_idx)]
        if len(subsequent_troughs) == 0:
            continue
        a_idx = subsequent_troughs[0]
        
        # Sonraki tepe (B)
        subsequent_peaks = peaks_idx[(peaks_idx > a_idx)]
        if len(subsequent_peaks) == 0:
            continue
        b_idx = subsequent_peaks[0]
        
        # Sonraki dip (C)
        subsequent_troughs2 = troughs_idx[(troughs_idx > b_idx)]
        if len(subsequent_troughs2) == 0:
            continue
        c_idx = subsequent_troughs2[0]
        
        # Sonraki tepe (D)
        subsequent_peaks2 = peaks_idx[(peaks_idx > c_idx)]
        if len(subsequent_peaks2) == 0:
            continue
        d_idx = subsequent_peaks2[0]
        
        # Fiyatlar
        px = high[x_idx]
        pa = low[a_idx]
        pb = high[b_idx]
        pc = low[c_idx]
        pd = high[d_idx]
        
        # Fibonacci oranları
        xa = px - pa
        ab = pb - pa
        bc = pb - pc
        cd = pd - pc
        xd = pd - px
        
        # Oran hesapla
        ratios = {
            "ab_retracement": ab / xa if xa != 0 else 0,
            "bc_retracement": bc / ab if ab != 0 else 0,
            "cd_extension": cd / bc if bc != 0 else 0,
            "xd_retracement": xd / xa if xa != 0 else 0,
        }
        
        # Pattern tiplerini kontrol et (Gartley, Bat, Butterfly, Crab)
        pattern_type = None
        confidence = 0.0
        
        # Gartley: AB=0.618XA, BC=0.382-0.886AB, CD=1.27-1.618BC, XD=0.786XA
        if (0.55 <= ratios["ab_retracement"] <= 0.68 and
            0.35 <= ratios["bc_retracement"] <= 0.92 and
            1.20 <= ratios["cd_extension"] <= 1.68 and
            0.72 <= ratios["xd_retracement"] <= 0.85):
            pattern_type = "bullish_gartley"
            confidence = min(1.0, sum([
                abs(0.618 - ratios["ab_retracement"]) < 0.08,
                0.35 <= ratios["bc_retracement"] <= 0.92,
                abs(1.414 - ratios["cd_extension"]) < 0.2,
                abs(0.786 - ratios["xd_retracement"]) < 0.08
            ]) / 4)
        
        # Bat: AB=0.382-0.5XA, BC=0.382-0.886AB, CD=1.618-2.618BC, XD=0.886XA
        elif (0.35 <= ratios["ab_retracement"] <= 0.52 and
              0.35 <= ratios["bc_retracement"] <= 0.92 and
              1.55 <= ratios["cd_extension"] <= 2.7 and
              0.82 <= ratios["xd_retracement"] <= 0.95):
            pattern_type = "bullish_bat"
            confidence = min(1.0, sum([
                abs(0.42 - ratios["ab_retracement"]) < 0.1,
                0.35 <= ratios["bc_retracement"] <= 0.92,
                abs(2.0 - ratios["cd_extension"]) < 0.4,
                abs(0.886 - ratios["xd_retracement"]) < 0.08
            ]) / 4)
        
        # Butterfly: AB=0.786XA, BC=0.382-0.886AB, CD=1.618-2.618BC, XD=1.27XA
        elif (0.72 <= ratios["ab_retracement"] <= 0.85 and
              0.35 <= ratios["bc_retracement"] <= 0.92 and
              1.55 <= ratios["cd_extension"] <= 2.7 and
              1.20 <= ratios["xd_retracement"] <= 1.35):
            pattern_type = "bullish_butterfly"
            confidence = min(1.0, sum([
                abs(0.786 - ratios["ab_retracement"]) < 0.08,
                0.35 <= ratios["bc_retracement"] <= 0.92,
                abs(2.0 - ratios["cd_extension"]) < 0.4,
                abs(1.27 - ratios["xd_retracement"]) < 0.08
            ]) / 4)
        
        if pattern_type and confidence >= 0.5:
            patterns.append(HarmonicPattern(
                pattern_type=pattern_type,
                point_x=int(x_idx),
                point_a=int(a_idx),
                point_b=int(b_idx),
                point_c=int(c_idx),
                point_d=int(d_idx),
                confidence=round(confidence, 2),
                ratios={k: round(v, 3) for k, v in ratios.items()}
            ))
    
    return patterns[:5]  # En fazla 5 pattern döndür


def add_fibonacci_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """DataFrame'e Fibonacci seviyelerini ekle."""
    close = df["close"].to_numpy()
    n = len(close)
    
    # Basit pivot-based Fibonacci seviyesi (son swing'den)
    fib_support = np.full(n, np.nan)
    fib_resistance = np.full(n, np.nan)
    
    if n >= 50:
        # Son 50 bardaki swing'leri bul
        high_s = df["high"].to_numpy()[-50:]
        low_s = df["low"].to_numpy()[-50:]
        
        peaks, _ = find_peaks(high_s, distance=5)
        troughs, _ = find_peaks(-low_s, distance=5)
        
        if len(peaks) > 0 and len(troughs) > 0:
            last_peak = high_s[peaks[-1]]
            last_trough = low_s[troughs[-1]]
            
            diff = last_peak - last_trough
            
            # 0.382, 0.5, 0.618 seviyeleri
            fib_382 = last_peak - (diff * 0.382) if last_peak > last_trough else last_trough + (diff * 0.382)
            fib_500 = last_peak - (diff * 0.5) if last_peak > last_trough else last_trough + (diff * 0.5)
            fib_618 = last_peak - (diff * 0.618) if last_peak > last_trough else last_trough + (diff * 0.618)
            
            # Son bara ekle
            fib_support[-1] = fib_618
            fib_resistance[-1] = fib_382
    
    return df.with_columns([
        pl.Series("fib_support", fib_support),
        pl.Series("fib_resistance", fib_resistance),
    ])
