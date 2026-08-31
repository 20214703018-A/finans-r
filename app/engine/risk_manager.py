"""
Risk Management & Position Sizing Engine
Calculates Stop Loss, Take Profit, Position Size based on signal strength and volatility.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    LOW = "Düşük Risk"
    MEDIUM = "Orta Risk"
    HIGH = "Yüksek Risk"
    VERY_HIGH = "Çok Yüksek Risk"

@dataclass
class TradePlan:
    entry_price: float
    stop_loss: float
    take_profit_1: float  # %50 pozisyon kapat
    take_profit_2: float  # %25 pozisyon kapat
    take_profit_3: float  # Koşucu (Trailing)
    position_size_pct: float  # Portföyün yüzde kaçı
    risk_reward_ratio: float
    expected_hold_time: str  # "Scalp", "Day", "Swing", "Position"
    risk_level: RiskLevel
    confidence_score: float
    notes: str

class RiskManager:
    def __init__(self, default_risk_per_trade: float = 0.02):
        """
        default_risk_per_trade: Her işlemde maksimum portföy riski (%2 varsayılan)
        """
        self.default_risk = default_risk_per_trade

    def calculate_trade_plan(
        self, 
        df: pd.DataFrame, 
        signal_type: str, 
        signal_score: float,
        current_price: float
    ) -> TradePlan:
        """
        Ana fonksiyon: Tüm parametreleri hesaplar
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        # 1. Volatilite bazlı stop mesafesi
        atr = last.get('atr', 0)
        if atr == 0:
            atr = (last['high'] - last['low']) * 1.5  # Fallback
        
        bb_upper = last.get('bb_upper', current_price * 1.02)
        bb_lower = last.get('bb_lower', current_price * 0.98)
        
        # 2. Trend yönü
        is_long = 'BUY' in signal_type or signal_type == 'NEUTRAL'
        if 'SELL' in signal_type:
            is_long = False
            
        # 3. Stop Loss Hesaplama (Dinamik)
        stop_loss = self._calculate_stop_loss(
            is_long=is_long,
            price=current_price,
            atr=atr,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            ema_20=last.get('ema_20', current_price),
            ema_50=last.get('ema_50', current_price),
            swing_high=df['high'].tail(20).max(),
            swing_low=df['low'].tail(20).min()
        )
        
        # 4. Take Profit Seviyeleri (Risk bazlı)
        risk_distance = abs(current_price - stop_loss)
        tp1, tp2, tp3 = self._calculate_take_profits(
            is_long=is_long,
            entry=current_price,
            risk_distance=risk_distance,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            atr=atr
        )
        
        # 5. Pozisyon Büyüklüğü (Signal strength + Risk level)
        position_pct, risk_level = self._calculate_position_size(
            signal_score=signal_score,
            stop_distance_pct=abs(current_price - stop_loss) / current_price,
            volatility=atr / current_price,
            rvol=last.get('rvol', 1.0)
        )
        
        # 6. Risk/Reward Oranı
        reward_distance = (tp1 - current_price) if is_long else (current_price - tp1)
        rr_ratio = reward_distance / risk_distance if risk_distance > 0 else 0
        
        # 7. Beklenen Tutma Süresi
        hold_time = self._estimate_hold_time(signal_type, atr/current_price)
        
        # 8. Notlar
        notes = self._generate_notes(
            is_long=is_long,
            rr_ratio=rr_ratio,
            risk_level=risk_level,
            atr_pct=atr/current_price*100
        )
        
        return TradePlan(
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            position_size_pct=position_pct,
            risk_reward_ratio=rr_ratio,
            expected_hold_time=hold_time,
            risk_level=risk_level,
            confidence_score=signal_score,
            notes=notes
        )

    def _calculate_stop_loss(
        self, 
        is_long: bool, 
        price: float, 
        atr: float,
        bb_upper: float,
        bb_lower: float,
        ema_20: float,
        ema_50: float,
        swing_high: float,
        swing_low: float
    ) -> float:
        """
        Akıllı Stop Loss:
        - Long: Swing Low, EMA50, veya ATR*2 altındakilerden en mantıklısı
        - Short: Swing High, EMA50, veya ATR*2 üstündekilerden en mantıklısı
        """
        if is_long:
            # Uzun pozisyon için stop aşağıda olmalı
            stop_atr = price - (atr * 2.5)  # ATR bazlı
            stop_ema = min(ema_20, ema_50) * 0.995  # EMA altına buffer
            stop_swing = swing_low * 0.995  # Swing low altına buffer
            
            # En güvenli stop (en aşağıdaki ama çok da uzak olmayan)
            candidates = [s for s in [stop_atr, stop_ema, stop_swing] if s < price]
            if not candidates:
                return price * 0.95  # Fallback %5 stop
            
            # Çok yakın stoplardan kaçın (noise'da patlamasın)
            min_safe_distance = price * 0.02  # En az %2 aşağıda
            safe_candidates = [c for c in candidates if (price - c) / price > 0.02]
            
            if safe_candidates:
                return max(safe_candidates)  # En yukarıdaki güvenli stop
            else:
                return min(candidates)  # Hiç güvenli yoksa en kötüsü
                
        else:
            # Kısa pozisyon için stop yukarıda olmalı
            stop_atr = price + (atr * 2.5)
            stop_ema = max(ema_20, ema_50) * 1.005
            stop_swing = swing_high * 1.005
            
            candidates = [s for s in [stop_atr, stop_ema, stop_swing] if s > price]
            if not candidates:
                return price * 1.05
            
            min_safe_distance = price * 0.02
            safe_candidates = [c for c in candidates if (c - price) / price > 0.02]
            
            if safe_candidates:
                return min(safe_candidates)
            else:
                return max(candidates)

    def _calculate_take_profits(
        self,
        is_long: bool,
        entry: float,
        risk_distance: float,
        bb_upper: float,
        bb_lower: float,
        atr: float
    ) -> Tuple[float, float, float]:
        """
        3 kademeli kar al:
        TP1: 1.5x Risk (Pozisyonun %50'sini kapat)
        TP2: 2.5x Risk (Pozisyonun %25'ini kapat)
        TP3: 4x Risk veya Bant dışı (Koşucu)
        """
        if is_long:
            tp1 = entry + (risk_distance * 1.5)
            tp2 = entry + (risk_distance * 2.5)
            tp3 = entry + (risk_distance * 4.0)
            
            # Bollinger üst bandını hedef olarak kullan (eğer daha yakınsa)
            if bb_upper > entry and bb_upper < tp2:
                tp2 = bb_upper * 0.995  # Bandın biraz altı
            if bb_upper > tp1 and bb_upper < tp3:
                tp3 = bb_upper * 1.005  # Bandın biraz üstü (breakout)
                
        else:
            tp1 = entry - (risk_distance * 1.5)
            tp2 = entry - (risk_distance * 2.5)
            tp3 = entry - (risk_distance * 4.0)
            
            if bb_lower < entry and bb_lower > tp2:
                tp2 = bb_lower * 1.005
            if bb_lower < tp1 and bb_lower > tp3:
                tp3 = bb_lower * 0.995
        
        return round(tp1, 2), round(tp2, 2), round(tp3, 2)

    def _calculate_position_size(
        self,
        signal_score: float,
        stop_distance_pct: float,
        volatility: float,
        rvol: float
    ) -> Tuple[float, RiskLevel]:
        """
        Kelly Criterion benzeri yaklaşım:
        - Güçlü sinyal + Dar stop = Büyük pozisyon
        - Zayıf sinyal + Geniş stop = Küçük pozisyon
        - Yüksek volatilite = Pozisyon küçült
        """
        # Baz pozisyon (%2 risk)
        base_size = self.default_risk
        
        # Sinyal gücü çarpanı (0.5x - 2.0x)
        signal_multiplier = 0.5 + (abs(signal_score) / 100)
        
        # Stop mesafesi çarpanı (Dar stop = büyük pozisyon)
        if stop_distance_pct < 0.02:
            stop_multiplier = 2.0
        elif stop_distance_pct < 0.05:
            stop_multiplier = 1.5
        elif stop_distance_pct < 0.10:
            stop_multiplier = 1.0
        else:
            stop_multiplier = 0.5  # Çok geniş stop, pozisyon küçült
        
        # Volatilite çarpanı
        if volatility > 0.05:
            vol_multiplier = 0.5  # Yüksek volatilite, yarıya düşür
        elif volatility > 0.02:
            vol_multiplier = 0.8
        else:
            vol_multiplier = 1.2
        
        # Hacim çarpanı (Düşük hacim = risk)
        volume_multiplier = 1.0 if rvol > 0.8 else 0.7
        
        final_pct = base_size * signal_multiplier * stop_multiplier * vol_multiplier * volume_multiplier
        
        # Limitler
        final_pct = min(max(final_pct, 0.01), 0.10)  # %1 ile %10 arası
        
        # Risk seviyesi
        if final_pct > 0.07:
            risk_level = RiskLevel.VERY_HIGH
        elif final_pct > 0.05:
            risk_level = RiskLevel.HIGH
        elif final_pct > 0.03:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
            
        return round(final_pct * 100, 2), risk_level

    def _estimate_hold_time(self, signal_type: str, atr_pct: float) -> str:
        """
        Stratejiye göre beklenen tutma süresi
        """
        if atr_pct > 0.05:
            return "Scalp (Saatler)"  # Çok volatil, hızlı çık
        elif 'BREAKOUT' in signal_type or atr_pct > 0.03:
            return "Day Trade (Gün içi)"
        elif 'TREND' in signal_type or atr_pct < 0.02:
            return "Swing (3-10 Gün)"
        else:
            return "Position (1-4 Hafta)"

    def _generate_notes(
        self,
        is_long: bool,
        rr_ratio: float,
        risk_level: RiskLevel,
        atr_pct: float
    ) -> str:
        notes = []
        
        if rr_ratio < 1.5:
            notes.append("⚠️ Düşük R/R - İşlem değmeyebilir")
        elif rr_ratio > 3.0:
            notes.append("✅ Mükemmel R/R Oranı")
            
        if atr_pct > 0.05:
            notes.append("🔥 Yüksek Volatilite - Stop geniş tutulmalı")
        elif atr_pct < 0.01:
            notes.append("💤 Düşük Volatilite - Sıkışma var, patlama bekle")
            
        if risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
            notes.append("⚡ Yüksek Risk - Pozisyon boyutunu küçült!")
            
        direction = "LONG" if is_long else "SHORT"
        return f"{direction} | " + " | ".join(notes) if notes else f"{direction} | Standart işlem"
