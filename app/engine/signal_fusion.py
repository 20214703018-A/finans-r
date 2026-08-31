"""
Advanced Signal Fusion Engine
Combines multiple indicators (Sensors) into a unified trading decision.
Uses Voting, Weighted Scoring, and Conflict Detection.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class SignalType(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WEAK_BUY = "WEAK_BUY"
    NEUTRAL = "NEUTRAL"
    WEAK_SELL = "WEAK_SELL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

class StrategyMode(Enum):
    TREND_FOLLOWING = "Trend Takibi (Güvenli)"
    MEAN_REVERSION = "Ortalamaya Dönüş (Cesur)"
    BREAKOUT = "Kırılım (Agresif)"
    CONTRARIAN = "Tersine İşlem (Very Cesur)"

@dataclass
class SensorVote:
    name: str
    vote: int  # -10 (Strong Sell) to +10 (Strong Buy)
    weight: float
    reason: str
    confidence: float  # 0.0 to 1.0

@dataclass
class FusionResult:
    signal: SignalType
    total_score: float
    mode: StrategyMode
    buy_votes: int
    sell_votes: int
    neutral_votes: int
    conflicts: List[str]
    key_drivers: List[str]
    recommended_action: str

class SignalFusionEngine:
    def __init__(self):
        # Ağırlıklar strateji moduna göre dinamik değişebilir
        self.weights = {
            'trend': 1.5,      # ADX, EMA Slope
            'momentum': 1.2,   # RSI, Stoch, CCI
            'volatility': 1.0, # Bollinger, Keltner
            'volume': 1.3,     # RVOL, OBV
            'pattern': 1.4     # Formasyonlar
        }

    def analyze(self, df: pd.DataFrame, current_price: float) -> FusionResult:
        if len(df) < 50:
            return FusionResult(
                signal=SignalType.NEUTRAL,
                total_score=0,
                mode=StrategyMode.TREND_FOLLOWING,
                buy_votes=0, sell_votes=0, neutral_votes=0,
                conflicts=["Yetersiz Veri"],
                key_drivers=[],
                recommended_action="Veri bekleniyor..."
            )

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        votes: List[SensorVote] = []
        conflicts = []
        key_drivers = []

        # 1. TREND SENSÖRLERİ
        votes.extend(self._analyze_trend_sensors(last, prev))
        
        # 2. MOMENTUM SENSÖRLERİ
        votes.extend(self._analyze_momentum_sensors(last, prev))
        
        # 3. VOLATİLİTE SENSÖRLERİ
        votes.extend(self._analyze_volatility_sensors(last, prev))
        
        # 4. HACİM SENSÖRLERİ
        votes.extend(self._analyze_volume_sensors(last, prev))
        
        # 5. PATTERN SENSÖRLERİ (Eğer varsa)
        if 'pattern_score' in df.columns:
            votes.append(self._analyze_pattern_sensor(last))

        # OYLAMA VE HESAPLAMA
        total_weighted_score = sum(v.vote * v.weight for v in votes)
        max_possible_score = sum(10 * v.weight for v in votes)
        normalized_score = (total_weighted_score / max_possible_score) * 100 if max_possible_score > 0 else 0

        # Çatışma Tespiti
        buy_votes = [v for v in votes if v.vote > 2]
        sell_votes = [v for v in votes if v.vote < -2]
        
        if len(buy_votes) > 0 and len(sell_votes) > 0:
            # Önemli çatışma: Trend aşağı, Momentum yukarı gibi
            conflicts.append(f"Trend ({len([v for v in buy_votes if 'Trend' in v.name])}) ve Momentum ({len([v for v in sell_votes if 'Momentum' in v.name])}) çelişiyor.")

        # Strateji Modu Belirleme
        adx = last.get('adx', 0)
        is_trending = adx > 25
        is_squeeze = last.get('bb_kc_squeeze', False)
        rsi = last.get('rsi', 50)
        
        mode = StrategyMode.TREND_FOLLOWING
        if is_squeeze and abs(normalized_score) > 60:
            mode = StrategyMode.BREAKOUT
            key_drivers.append("Volatilite Sıkışması Patlaması Bekleniyor!")
        elif not is_trending and (rsi < 30 or rsi > 70):
            mode = StrategyMode.MEAN_REVERSION
            key_drivers.append("Aşırı Uzaklaşma Tespit Edildi (Cesur Dönüş)")
        elif is_trending and abs(normalized_score) > 80:
             mode = StrategyMode.CONTRARIAN # Çok aşırıysa tersini düşün (Riskli ama kazandırabilir)
             if normalized_score > 80: key_drivers.append("Aşırı Alım Bölgesi - Dikkatli Ol")
             else: key_drivers.append("Aşırı Satım Bölgesi - Fırsat Olabilir")

        # Sinyal Sınıflandırma
        signal = self._classify_signal(normalized_score, mode)
        
        # Öneri Oluşturma
        action_text = self._generate_action_text(signal, mode, key_drivers)

        return FusionResult(
            signal=signal,
            total_score=normalized_score,
            mode=mode,
            buy_votes=len(buy_votes),
            sell_votes=len(sell_votes),
            neutral_votes=len(votes) - len(buy_votes) - len(sell_votes),
            conflicts=conflicts,
            key_drivers=key_drivers,
            recommended_action=action_text
        )

    def _analyze_trend_sensors(self, last, prev) -> List[SensorVote]:
        votes = []
        # EMA Alignment
        if last['ema_20'] > last['ema_50'] > last['ema_200']:
            votes.append(SensorVote("EMA Trend", 8, self.weights['trend'], "Golden Alignment", 0.9))
        elif last['ema_20'] < last['ema_50'] < last['ema_200']:
            votes.append(SensorVote("EMA Trend", -8, self.weights['trend'], "Death Alignment", 0.9))
        else:
            votes.append(SensorVote("EMA Trend", 0, self.weights['trend'], "Karışık Trend", 0.5))
            
        # ADX Strength
        adx = last.get('adx', 0)
        if adx > 30:
            direction = 1 if last['close'] > last['ema_20'] else -1
            votes.append(SensorVote("ADX Gücü", direction * 7, self.weights['trend'], f"Güçlü Trend (ADX:{adx:.1f})", 0.8))
        
        # Slope
        slope = last.get('ema_slope_20', 0)
        if slope > 0.002:
            votes.append(SensorVote("Eğim", 6, self.weights['trend'], "Yükselen Eğim", 0.7))
        elif slope < -0.002:
            votes.append(SensorVote("Eğim", -6, self.weights['trend'], "Düşen Eğim", 0.7))
            
        return votes

    def _analyze_momentum_sensors(self, last, prev) -> List[SensorVote]:
        votes = []
        rsi = last.get('rsi', 50)
        stoch_k = last.get('stoch_k', 50)
        cci = last.get('cci', 0)
        willr = last.get('willr', -50)
        
        # RSI Logic
        if rsi < 30: votes.append(SensorVote("RSI", 8, self.weights['momentum'], "Aşırı Satım", 0.85))
        elif rsi > 70: votes.append(SensorVote("RSI", -8, self.weights['momentum'], "Aşırı Alım", 0.85))
        elif 45 < rsi < 55: votes.append(SensorVote("RSI", 0, self.weights['momentum'], "Nötr Bölge", 0.4))
        else: votes.append(SensorVote("RSI", 2 if rsi > 50 else -2, self.weights['momentum'], "Normal", 0.5))

        # Stochastic
        if stoch_k < 20 and last.get('stoch_d', 0) < 20:
            votes.append(SensorVote("Stochastic", 7, self.weights['momentum'], "Derin Satım", 0.8))
        elif stoch_k > 80:
            votes.append(SensorVote("Stochastic", -7, self.weights['momentum'], "Derin Alım", 0.8))
            
        # CCI
        if cci < -100: votes.append(SensorVote("CCI", 6, self.weights['momentum'], "Negatif Sapma", 0.7))
        elif cci > 100: votes.append(SensorVote("CCI", -6, self.weights['momentum'], "Pozitif Sapma", 0.7))

        # Divergence (Eğer hesaplandıysa)
        if last.get('divergence_signal', 0) != 0:
            div_val = last['divergence_signal']
            votes.append(SensorVote("Uyumsuzluk", div_val * 9, self.weights['momentum'] * 1.5, "Güçlü Dönüş Sinyali", 0.95))

        return votes

    def _analyze_volatility_sensors(self, last, prev) -> List[SensorVote]:
        votes = []
        bb_pct = last.get('bb_pct', 0.5)
        squeeze = last.get('bb_kc_squeeze', False)
        
        # Bollinger %B
        if bb_pct < 0.1:
            votes.append(SensorVote("Bollinger", 7, self.weights['volatility'], "Alt Bant Dışı (Cesur Al)", 0.8))
        elif bb_pct > 0.9:
            votes.append(SensorVote("Bollinger", -7, self.weights['volatility'], "Üst Bant Dışı (Cesur Sat)", 0.8))
            
        # Squeeze
        if squeeze:
            votes.append(SensorVote("Squeeze", 0, self.weights['volatility'], "Patlama Öncesi Sessizlik", 0.6))
            # Squeeze tek başına yön vermez, momentumla birlikte değerlendirilir
            
        return votes

    def _analyze_volume_sensors(self, last, prev) -> List[SensorVote]:
        votes = []
        rvol = last.get('rvol', 1.0)
        
        if rvol > 2.0:
            # Yüksek hacim yönü güçlendirir
            direction = 1 if last['close'] > last['open'] else -1
            votes.append(SensorVote("Hacim", direction * 8, self.weights['volume'], f"Anormal Hacim ({rvol:.1f}x)", 0.9))
        elif rvol < 0.5:
            votes.append(SensorVote("Hacim", 0, self.weights['volume'], "Hacimsiz (Güvensiz)", 0.3))
            
        return votes

    def _analyze_pattern_sensor(self, last) -> SensorVote:
        score = last.get('pattern_score', 0)
        # Pattern score 0-100 arası
        if score > 75:
            return SensorVote("Formasyon", 9, self.weights['pattern'], "Güçlü Formasyon", 0.9)
        elif score < 25:
            return SensorVote("Formasyon", -9, self.weights['pattern'], "Negatif Formasyon", 0.9)
        return SensorVote("Formasyon", 0, self.weights['pattern'], "Belirsiz", 0.5)

    def _classify_signal(self, score: float, mode: StrategyMode) -> SignalType:
        # Eşikler moda göre değişir
        if mode == StrategyMode.CONTRARIAN:
            # Daha agresif eşikler
            if score > 70: return SignalType.STRONG_BUY
            if score > 40: return SignalType.BUY
            if score > 10: return SignalType.WEAK_BUY
            if score < -70: return SignalType.STRONG_SELL
            if score < -40: return SignalType.SELL
            if score < -10: return SignalType.WEAK_SELL
        else:
            # Standart
            if score > 60: return SignalType.STRONG_BUY
            if score > 30: return SignalType.BUY
            if score > 5: return SignalType.WEAK_BUY
            if score < -60: return SignalType.STRONG_SELL
            if score < -30: return SignalType.SELL
            if score < -5: return SignalType.WEAK_SELL
            
        return SignalType.NEUTRAL

    def _generate_action_text(self, signal: SignalType, mode: StrategyMode, drivers: List[str]) -> str:
        base_msg = {
            SignalType.STRONG_BUY: "GÜÇLÜ AL",
            SignalType.BUY: "AL",
            SignalType.WEAK_BUY: "Zayıf Al / İzle",
            SignalType.NEUTRAL: "BEKLE",
            SignalType.WEAK_SELL: "Zayıf Sat / İzle",
            SignalType.SELL: "SAT",
            SignalType.STRONG_SELL: "GÜÇLÜ SAT"
        }
        mode_msg = f"[{mode.value}]"
        driver_msg = " | ".join(drivers) if drivers else ""
        return f"{base_msg[signal]} {mode_msg} {driver_msg}"
