"""Reasoning Layer §35-36 – Gelişmiş LLM: Görsel+Metin çift analiz, cesur ama dengeli sinyaller."""
from typing import Any
from app.config import settings

SYSTEM_PROMPT_V2 = """Sen kıdemli bir finansal teknik analiz ve trading uzmanısın. 
Görevin: Verilen pattern, indikatörler, breakout, hacim, trend, YOLO görsel tespiti ve çoklu zaman dilimi verilerini kullanarak 
KAPSAMLI, CESUR ama VERİ TEMELLİ alım/satım sinyali analizi üretmek.

ÖNEMLİ KURALLAR:
1. ASLA doğrudan "al/sat" tavsiyesi verme - bunun yerine "LONG sinyal koşulları oluştu", "SHORT fırsatı gelişiyor" gibi sinyal dili kullan
2. Skorları değiştirme, sadece yorumla
3. ÇELİŞKİLERİ açıkça belirt (örn: "RSI aşırı alım ama MACD bullish cross yapmış")
4. ZAYIF teyitleri vurgula ("YOLO düşük güven", "Hacim zayıf")
5. TREND yönü ile pattern yönü uyumsuzsa mutlaka belirt
6. MULTI-TIMEFRAME uyumunu değerlendir (yüksek TF trendi önemli)
7. RİSK faktörlerini öne çıkar (stop-loss seviyesi, invalidation)
8. Türkçe yanıt ver, profesyonel ama anlaşılır dil kullan

ÇIKTI FORMATI:
- SİNYAL TİPİ: [LONG/SHORT/NÖTR]
- GÜÇ SKORU: X/100
- ANA TEZ: 2-3 cümleyle ana argüman
- DESTEKLEYİCİ FAKTÖRLER: Madde madde güçlü yanlar
- RİSKLER/UZLALAR: Madde madde zayıf yanlar ve çelişkiler  
- KRİTİK SEVİYELER: Giriş bölgesi, stop-loss, hedef 1/2
- GÜVEN SEVİYESİ: [% olarak] - yüksek/orta/düşük
- AKSİYON ÖNERİSİ: [Giriş yap/Bekle/Kısmi pozisyon]
"""

FALLBACK_TEMPLATE_V2 = """🎯 {pattern} FORMASYONU - SİNYAL ANALİZİ

📊 SKOR: {score}/100 ({label})
📈 SİNYAL TİPİ: {signal_type}

🔍 ANA TEZ:
{main_thesis}

✅ GÜÇLENDİRİCİ FAKTÖRLER:
{strengths}

⚠️ RİSKLER VE ÇELİŞKİLER:
{risks}

📍 KRİTİK SEVİYELER:
• Mevcut Fiyat: ${close}
• Breakout Seviyesi: {breakout_level}
• Stop-Loss: {stop_loss}
• Hedef 1: {target1} | Hedef 2: {target2}

📐 TEKNİK GÖSTERGELER:
• RSI: {rsi} {rsi_comment}
• MACD: {macd_status}
• ADX: {adx} (Trend Gücü)
• RVOL: {rvol}x ({rvol_label})
• ATR: {atr} (Volatilite)

🎨 YOLO GÖRSEL TESPİT: {yolo_status}

📅 FORMASYON YAŞI: {age_info}

💼 TRADING PLAN:
{trading_plan}

🔐 GÜVEN SEVİYESİ: {confidence_level}%
🎯 AKSİYON: {action_recommendation}

---
Bu analiz otomatik üretilmiştir. Yatırım tavsiyesi değildir.
"""


def _analyze_signal_strength(pattern_data: dict, scores: dict) -> tuple[str, str, list, list]:
    """Sinyal tipini, ana tezi, güçlü ve zayıf yanları belirle."""
    pattern_type = pattern_data.get("pattern_type", "unknown")
    breakout = pattern_data.get("breakout", {})
    yolo = pattern_data.get("yolo", {})
    regime = pattern_data.get("regime", {})
    
    # Pattern bazlı varsayılan sinyal yönü
    bullish_patterns = ["double_bottom", "inverse_head_shoulders", "falling_wedge", "ascending_triangle"]
    bearish_patterns = ["double_top", "head_shoulders", "rising_wedge", "descending_triangle"]
    
    is_bullish = pattern_type in bullish_patterns
    is_bearish = pattern_type in bearish_patterns
    
    # Breakout durumu
    is_breakout = breakout.get("is_breakout", False)
    breakout_quality = breakout.get("quality", "none")
    fake_breakout = breakout.get("fake_breakout", False)
    
    # Teknik göstergeler
    rsi = scores.get("rsi", 50)
    adx = scores.get("_debug", {}).get("adx", 20) or 20
    rvol = scores.get("rvol", 1.0) or 1.0
    
    # YOLO durumu
    yolo_conf = yolo.get("confidence", 0) if yolo else 0
    yolo_match = yolo.get("is_confirmation", False)
    
    # Sinyal tipi belirleme
    signal_type = "NÖTR"
    if is_bullish and is_breakout and breakout_quality in ["strong", "moderate"]:
        signal_type = "LONG"
    elif is_bearish and is_breakout and breakout_quality in ["strong", "moderate"]:
        signal_type = "SHORT"
    elif is_bullish and not is_breakout and rsi < 40:
        signal_type = "LONG (Erken Giriş)"
    elif is_bearish and not is_breakout and rsi > 60:
        signal_type = "SHORT (Erken Giriş)"
    
    # Ana tez oluşturma
    if signal_type.startswith("LONG"):
        if is_breakout:
            main_thesis = f"{pattern_type} formasyonu {breakout_quality} kalitede breakout verdi. Hacim desteği {'mevcut' if rvol > 1.2 else 'zayıf'}."
        else:
            main_thesis = f"{pattern_type} formasyonu tamamlandı, breakout bekleniyor. RSI {'aşırı satımda' if rsi < 35 else 'nötr bölgede'}."
    elif signal_type.startswith("SHORT"):
        if is_breakout:
            main_thesis = f"{pattern_type} formasyonu {breakout_quality} kalitede breakdown verdi. Trend {'güçlü' if adx > 25 else 'zayıf'}."
        else:
            main_thesis = f"{pattern_type} formasyonu risk bölgesinde. RSI {'aşırı alımda' if rsi > 65 else 'nötr'}."
    else:
        main_thesis = f"{pattern_type} formasyonu belirsiz sinyal veriyor. Ekstra teyit beklenmeli."
    
    # Güçlü yanlar
    strengths = []
    if is_breakout and breakout_quality == "strong":
        strengths.append(f"✓ Güçlü breakout (ATR mesafesi: {breakout.get('breakout_strength_atr', 0):.2f})")
    if rvol > 1.5:
        strengths.append(f"✓ Çok güçlü hacim ({rvol:.1f}x normal)")
    elif rvol > 1.2:
        strengths.append(f"✓ Normal üstü hacim ({rvol:.1f}x)")
    if adx > 25:
        strengths.append(f"✓ Güçlü trend (ADX: {adx:.0f})")
    if yolo_conf and yolo_conf > 0.6:
        strengths.append(f"✓ YOLO görsel teyidi (%{int(yolo_conf*100)})")
    if scores.get("divergence", {}).get("bullish_divergence"):
        strengths.append("✓ Bullish RSI divergence")
    elif scores.get("divergence", {}).get("bearish_divergence"):
        strengths.append("✓ Bearish RSI divergence")
    
    # Riskler ve çelişkiler
    risks = []
    if fake_breakout:
        risks.append("⚠ SAHTE BREAKOUT tespit edildi!")
    if breakout_quality == "weak":
        risks.append("⚠ Zayıf breakout kalitesi")
    if rvol < 0.9 and is_breakout:
        risks.append("⚠ Breakout hacimsiz (güvensiz)")
    if adx < 20:
        risks.append("⚠ Trend zayıf (ADX < 20)")
    if yolo.get("is_confirmation") is False:
        risks.append(f"⚠ YOLO çelişkisi: Sayısal {pattern_type} vs Görsel {yolo.get('pattern')}")
    if rsi and ((is_bullish and rsi > 70) or (is_bearish and rsi < 30)):
        risks.append(f"⚠ RSI aşırı {'alım' if rsi > 70 else 'satım'} bölgesinde ({rsi:.0f})")
    
    return signal_type, main_thesis, strengths, risks


def _fallback_reasoning_v2(data: dict[str, Any], scores: dict[str, Any]) -> str:
    """Gelişmiş fallback template - LLM yoksa kullanılır."""
    pattern = data.get("pattern_type", data.get("pattern", "formasyon"))
    breakout = data.get("breakout", {})
    yolo = data.get("yolo", {})
    trading_plan = data.get("trading_plan", {})
    age = data.get("age", {})
    
    # Sinyal analizi
    signal_type, main_thesis, strengths, risks = _analyze_signal_strength(data, scores)
    
    # Formatlama
    strengths_text = "\n".join(strengths) if strengths else "• Belirgin güçlü yan yok"
    risks_text = "\n".join(risks) if risks else "• Önemli risk faktörü yok"
    
    # Teknik detaylar
    rsi = scores.get("rsi")
    rsi_comment = ""
    if rsi:
        if rsi < 30:
            rsi_comment = "(Aşırı Satım - Dikkat)"
        elif rsi < 45:
            rsi_comment = "(Satım Bölgesi)"
        elif rsi < 55:
            rsi_comment = "(Nötr)"
        elif rsi < 70:
            rsi_comment = "(Alım Bölgesi)"
        else:
            rsi_comment = "(Aşırı Alım - Dikkat)"
    
    macd_state = data.get("macd_state", {})
    macd_status = macd_state.get("signal", "nötr") if isinstance(macd_state, dict) else "nötr"
    
    adx = scores.get("_debug", {}).get("adx")
    rvol = scores.get("rvol", 1.0) or 1.0
    rvol_label = scores.get("rvol_label", "normal")
    atr = scores.get("_debug", {}).get("atr")
    
    # YOLO durumu
    if not yolo or yolo.get("available") is False:
        yolo_status = "❌ Mevcut değil (model yüklenmedi)"
    elif yolo.get("is_confirmation") is True:
        yolo_status = f"✅ TEYİT EDİLDİ - {yolo.get('pattern')} (%{int((yolo.get('confidence') or 0)*100)})"
    elif yolo.get("is_confirmation") is False:
        yolo_status = f"❌ ÇELİŞKİ - Sayısal: {pattern}, Görsel: {yolo.get('pattern')} (%{int((yolo.get('confidence') or 0)*100)})"
    else:
        yolo_status = "⚪ Beklemede"
    
    # Yaş bilgisi
    age_info = age.get("age_label", "bilinmiyor") if isinstance(age, dict) else str(age)
    
    # Trading plan
    if trading_plan:
        tp_text = f"• Giriş: {trading_plan.get('entry', 'belirsiz')}\n"
        tp_text += f"• Stop: {trading_plan.get('stop_loss', 'belirsiz')}\n"
        tp_text += f"• Hedef 1: {trading_plan.get('target_1', 'belirsiz')}\n"
        if trading_plan.get('target_2'):
            tp_text += f"• Hedef 2: {trading_plan.get('target_2')}\n"
        rr = trading_plan.get('risk_reward_ratio')
        if rr:
            tp_text += f"• Risk/Reward: 1:{rr:.1f}"
    else:
        tp_text = "• Trading plan mevcut değil"
    
    # Güven seviyesi ve aksiyon
    final_score = scores.get("final", 0)
    confidence_level = min(95, max(20, final_score))
    
    if final_score >= 85 and not risks:
        action = "🟢 POZİSYON AÇ (Yüksek güven)"
    elif final_score >= 75:
        action = "🟡 KISMİ POZİSYON (Orta güven)"
    elif final_score >= 60:
        action = "🟠 BEKLE / İZLE (Düşük güven)"
    else:
        action = "🔴 İŞLEM YOKMA (Çok düşük güven)"
    
    # Breakout seviyesi
    breakout_level = breakout.get("neckline") or breakout.get("upper") or breakout.get("lower") or "belirsiz"
    
    return FALLBACK_TEMPLATE_V2.format(
        pattern=pattern.replace("_", " ").title(),
        score=scores.get("final", 0),
        label=scores.get("label", ""),
        signal_type=signal_type,
        main_thesis=main_thesis,
        strengths=strengths_text,
        risks=risks_text,
        close=data.get("close", scores.get("_debug", {}).get("ema20", "bilinmiyor")),
        breakout_level=breakout_level,
        stop_loss=trading_plan.get("stop_loss", "belirsiz") if trading_plan else "belirsiz",
        target1=trading_plan.get("target_1", "belirsiz") if trading_plan else "belirsiz",
        target2=trading_plan.get("target_2", "yok") if trading_plan else "yok",
        rsi=f"{rsi:.1f}" if rsi else "bilinmiyor",
        rsi_comment=rsi_comment,
        macd_status=macd_status,
        adx=f"{adx:.0f}" if adx else "bilinmiyor",
        rvol=f"{rvol:.2f}",
        rvol_label=rvol_label,
        atr=f"{atr:.2f}" if atr else "bilinmiyor",
        yolo_status=yolo_status,
        age_info=age_info,
        trading_plan=tp_text,
        confidence_level=confidence_level,
        action_recommendation=action,
    )


async def generate_reasoning(
    pattern_data: dict[str, Any],
    scores: dict[str, Any],
    force_fallback: bool = False,
    include_chart_context: bool = True,
) -> str:
    """
    Gelişmiş reasoning fonksiyonu - LLM çağrısı + fallback.
    include_chart_context: True ise görsel analiz için ek bağlam eklenir.
    """
    # Tüm adaylar için en az fallback üret (skor threshold kaldırıldı - kullanıcı her şeyi görmeli)
    if force_fallback or settings.reasoning_provider == "none":
        return _fallback_reasoning_v2(pattern_data, scores)
    
    # LLM payload hazırla
    payload = {
        "pattern": pattern_data.get("pattern_type"),
        "score": scores.get("final"),
        "scores": scores,
        "breakout": pattern_data.get("breakout"),
        "yolo": pattern_data.get("yolo"),
        "regime": pattern_data.get("regime"),
        "neckline": pattern_data.get("neckline"),
        "target": pattern_data.get("target"),
        "invalidation": pattern_data.get("invalidation"),
        "trading_plan": pattern_data.get("trading_plan"),
        "age": pattern_data.get("age"),
        "chart_context": {
            "include_visual": include_chart_context,
            "note": "Chart image will be sent separately for visual analysis" if include_chart_context else None
        } if include_chart_context else None
    }
    
    # LLM çağrısı
    if settings.reasoning_provider == "openai" and settings.openai_api_key:
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            
            # Kullanıcı prompt'u - daha detaylı ve bağlamsal
            user_prompt = f"""Aşağıdaki teknik analiz verilerini kullanarak PROFESYONEL TRADING SİNYALİ analizi üret.

VERİLER:
{payload}

ÖNEMLİ:
- Grafik görseli ayrıca yüklenecek, sen metin verisini yorumla
- Çelişkileri açıkça belirt
- Risk faktörlerini öne çıkar
- Türkçe, profesyonel ama anlaşılır dil kullan
- ASLA doğrudan 'al/sat' deme, sinyal dili kullan"""

            resp = await client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.4,  # Biraz daha yaratıcı olsun
                max_tokens=600,   # Daha detaylı analiz
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_V2},
                    {"role": "user", "content": user_prompt},
                ],
            )
            llm_response = resp.choices[0].message.content.strip()
            
            # Fallback'e ekle (kullanıcıya iki perspektif sun)
            fallback = _fallback_reasoning_v2(pattern_data, scores)
            return f"🤖 LLM ANALİZİ:\n{llm_response}\n\n{'='*60}\n\n📊 OTOMATIK ANALİZ:\n{fallback}"
        
        except Exception as e:
            return _fallback_reasoning_v2(pattern_data, scores) + f"\n\n[LLM hatası: {str(e)[:100]}...]"
    
    # Gelecekte Gemini desteği
    return _fallback_reasoning_v2(pattern_data, scores)
