"""Reasoning Layer §35-36 – LLM explains result, never changes score."""
from typing import Any
from app.config import settings

SYSTEM_PROMPT = (
    "Sen finansal teknik analiz açıklama katmanısın. Görevin: verilen pattern, skorlar, "
    "breakout, hacim, trend, YOLO çıktısını kullanıcıya sade ve çelişkilere dikkat çekerek özetlemek. "
    "Asla al/sat tavsiyesi verme, asla skoru değiştirme. Türkçe yanıt ver. "
    "Önemli: 'bilmiyorum' demekten çekinme, zayıf teyitleri belirt."
)

FALLBACK_TEMPLATE = """{pattern} paterni {score}/100 skorla {label} olarak değerlendirildi.
Geometri: {geometry}/30, Breakout: {breakout}/20, Hacim: {volume}/15, Trend: {trend}/15, Momentum: {momentum}/10, YOLO: {yolo}/5, S/R: {sr}/5.
{breakout_text}
Hacim {rvol_label} (RVOL {rvol:.2f}), RSI {rsi}.
Neckline {neckline}, hedef {target}, geçersizlik {invalidation}.
Regime: {regime}.
{yolo_text}
{divergence_text}
Bu açıklama skorun nedenini özetler; skorun kendisi değişmez.
"""


def _fallback_reasoning(data: dict[str, Any], scores: dict[str, Any]) -> str:
    pattern = data.get("pattern_type", data.get("pattern", "pattern"))
    breakout = data.get("breakout", {})
    b_quality = breakout.get("quality", "none")
    is_breakout = breakout.get("is_breakout", False)
    fake = breakout.get("fake_breakout", False)
    if fake:
        breakout_text = "Breakout sahte (failed) olarak işaretlendi – fiyat tekrar formasyon içine döndü."
    elif is_breakout:
        breakout_text = f"Breakout teyit edildi (kalite: {b_quality}, ATR mesafesi {breakout.get('breakout_strength_atr', 0):.2f})."
    elif b_quality == "none":
        breakout_text = "Henüz breakout yok; fiyat sınır içinde."
    else:
        breakout_text = f"Breakout beklemede (kalite: {b_quality})."

    yolo = data.get("yolo", {})
    if yolo.get("available") is False:
        yolo_text = "YOLO teyidi mevcut değil (model yüklenmedi)."
    elif yolo.get("is_confirmation") is True:
        yolo_text = f"YOLO görsel teyit verdi: {yolo.get('pattern')} %{int(yolo.get('confidence',0)*100)}."
    elif yolo.get("is_confirmation") is False:
        yolo_text = f"YOLO çelişki: sayısal {pattern} ama görsel {yolo.get('pattern')} (%{int((yolo.get('confidence') or 0)*100)})."
    else:
        yolo_text = "YOLO teyidi yok."

    div = scores.get("divergence", {})
    if div.get("bullish_divergence"):
        divergence_text = "RSI bullish divergence var – momentum dönüşü destekliyor."
    elif div.get("bearish_divergence"):
        divergence_text = "RSI bearish divergence var."
    else:
        divergence_text = ""

    return FALLBACK_TEMPLATE.format(
        pattern=pattern,
        score=scores.get("final", 0),
        label=scores.get("label", ""),
        geometry=scores.get("geometry", 0),
        breakout=scores.get("breakout", 0),
        volume=scores.get("volume", 0),
        trend=scores.get("trend", 0),
        momentum=scores.get("momentum", 0),
        yolo=scores.get("yolo", 0),
        sr=scores.get("support_resistance", 0),
        breakout_text=breakout_text,
        rvol_label=scores.get("rvol_label", "normal"),
        rvol=scores.get("rvol") or 0,
        rsi=scores.get("rsi") or "-",
        neckline=data.get("neckline", "-"),
        target=data.get("target", "-"),
        invalidation=data.get("invalidation", "-"),
        regime=data.get("regime", {}).get("regime", "-") if isinstance(data.get("regime"), dict) else data.get("regime", "-"),
        yolo_text=yolo_text,
        divergence_text=divergence_text,
    )


async def generate_reasoning(
    pattern_data: dict[str, Any],
    scores: dict[str, Any],
    force_fallback: bool = False,
) -> str:
    """
    Calls LLM if pattern_score >= threshold and provider configured; else fallback template.
    Never mutates score.
    """
    # Only strong candidates get LLM
    if scores.get("final", 0) < settings.reasoning_score_threshold:
        return _fallback_reasoning(pattern_data, scores)
    if force_fallback or settings.reasoning_provider == "none":
        return _fallback_reasoning(pattern_data, scores)

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
    }

    if settings.reasoning_provider == "openai" and settings.openai_api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.3,
                max_tokens=400,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Aşağıdaki analiz çıktısını kullanıcının anlayacağı sade Türkçe ile açıkla. "
                            f"Skoru değiştirme. Çelişkileri belirt. JSON girdi:\n{payload}"
                        ),
                    },
                ],
            )
            return resp.choices[0].message.content.strip()  # type: ignore
        except Exception as e:
            return _fallback_reasoning(pattern_data, scores) + f"\n\n[LLM hatası, fallback kullanıldı: {e}]"

    # Future: gemini branch
    return _fallback_reasoning(pattern_data, scores)
