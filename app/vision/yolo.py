"""YOLO confirmation §30-32 – independent visual confirmation (non-decisive).

HF model: foduucom/stockmarket-pattern-detection-yolov8 (YOLOv8s, 6 class)
  Labels (HF README): ['Head and shoulders bottom', 'Head and shoulders top', 'M_Head', 'StockLine', 'Triangle', 'W_Bottom']
  -> mapped to canonical internal pattern types ( §33 scoring).
  Model dosya yoksa otomatik HF'den indirir (YOLO_AUTO_DOWNLOAD=true).
  Karar verici değil: yalnız 5/100 puan + is_confirmation bayrağı.
"""
from pathlib import Path
from dataclasses import dataclass
import polars as pl
from app.config import settings
from app.vision.chart import render_chart

try:
    from ultralytics import YOLO  # type: ignore
    _YOLO_AVAILABLE = True
except Exception:
    _YOLO_AVAILABLE = False


@dataclass
class YoloResult:
    pattern: str | None          # canonical id e.g. double_bottom
    confidence: float | None
    is_confirmation: bool | None  # vs numerical engine pattern_type
    raw: dict | None = None
    all_detections: list[dict] | None = None


# HF -> canonical (internal) mapping. StockLine ignorance için None.
# Hem HF exact strings hem de olası alternatifler (M_Top, M_Head) desteklenir.
YOLO_CANONICAL: dict[str, str | None] = {
    # HF exact (case sensitive)
    "Head and shoulders bottom": "inverse_head_shoulders",
    "Head and shoulders top": "head_shoulders",
    "M_Head": "double_top",
    "W_Bottom": "double_bottom",
    "Triangle": "triangle",
    "StockLine": None,  # çizgi tespiti – pattern değil, skorlamada yok sayılır
    # Alternatifler / alt tipler (eski kod uyumu + farklı eğitimler)
    "M_Top": "double_top",
    "Head and Shoulders Bottom": "inverse_head_shoulders",
    "Head and Shoulders Top": "head_shoulders",
    "HS Top": "head_shoulders",
    "HS Bottom": "inverse_head_shoulders",
    "W_Bottom ": "double_bottom",
    "TRIANGLE": "triangle",
    "ASC_TRI": "ascending_triangle",
    "DESC_TRI": "descending_triangle",
    "RISING_WEDGE": "rising_wedge",
    "FALLING_WEDGE": "falling_wedge",
    # lower-case fallback
    "head and shoulders bottom": "inverse_head_shoulders",
    "head and shoulders top": "head_shoulders",
    "m_head": "double_top",
    "w_bottom": "double_bottom",
    "triangle": "triangle",
    "stockline": None,
    "double_top": "double_top",
    "double_bottom": "double_bottom",
}

# ters mapping sadece bilgi için
CANONICAL_TO_HF_EXAMPLE = {
    "double_top": "M_Head",
    "double_bottom": "W_Bottom",
    "head_shoulders": "Head and shoulders top",
    "inverse_head_shoulders": "Head and shoulders bottom",
    "triangle": "Triangle",
}


def _canonical(label: str | None) -> str | None:
    if label is None:
        return None
    if label in YOLO_CANONICAL:
        return YOLO_CANONICAL[label]
    # try stripped
    s = label.strip()
    if s in YOLO_CANONICAL:
        return YOLO_CANONICAL[s]
    # lower
    low = label.lower().strip()
    if low in YOLO_CANONICAL:
        return YOLO_CANONICAL[low]
    return low  # fallback raw lower


def _ensure_model_download() -> Path | None:
    """HF'den modeli models/ klasörüne indir (varsa skip). None -> indirilemedi/offline."""
    target = Path(settings.yolo_model_path)
    if target.exists() and target.stat().st_size > 1_000_000:
        return target
    if not settings.yolo_auto_download:
        return None
    # Try HF download
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except Exception as e:
        # huggingface_hub yoksa ekle
        return None  # graceful
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # progress bar kapalı uzun log engellemek için
        cached = hf_hub_download(
            repo_id=settings.yolo_hf_repo,
            filename=settings.yolo_hf_filename,
            local_dir=None,  # cache
        )
        # copy cache -> target
        import shutil
        shutil.copyfile(cached, target)
        return target
    except Exception as e:
        # offline veya rate limit – cached dosyayı dene
        try:
            cached = hf_hub_download(
                repo_id=settings.yolo_hf_repo,
                filename=settings.yolo_hf_filename,
                local_files_only=True,
            )
            import shutil
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached, target)
            return target
        except Exception:
            return None


class YoloEngine:
    def __init__(self, model_path: str | None = None, conf_min: float | None = None):
        self.requested_path = model_path or settings.yolo_model_path
        self.conf_min = conf_min if conf_min is not None else settings.yolo_conf_min
        self.model = None
        self.model_path_resolved: Path | None = None
        self._load_error: str | None = None
        self._labels: list[str] | None = None  # for debugging
        self._ensure_and_load()

    def _ensure_and_load(self):
        if not _YOLO_AVAILABLE:
            self._load_error = "ultralytics not installed"
            return
        # download if missing
        ensured = _ensure_model_download()
        # pick path
        candidates = []
        if ensured and ensured.exists():
            candidates.append(ensured)
        candidates.append(Path(self.requested_path))
        # also check HF cache directly without copy (fallback)
        try:
            from huggingface_hub import hf_hub_download
            try:
                cached = Path(hf_hub_download(settings.yolo_hf_repo, settings.yolo_hf_filename, local_files_only=True))
                if cached.exists():
                    candidates.append(cached)
            except Exception:
                pass
        except Exception:
            pass
        for p in candidates:
            if p.exists() and p.stat().st_size > 1_000_000:
                try:
                    self.model = YOLO(str(p))
                    self.model_path_resolved = p
                    # expose names
                    try:
                        self._labels = list(self.model.names.values()) if hasattr(self.model, "names") else None
                    except Exception:
                        self._labels = None
                    self._load_error = None
                    return
                except Exception as e:
                    self._load_error = f"YOLO load failed {p}: {e}"
                    self.model = None
                    continue
        if self.model is None and not self._load_error:
            self._load_error = f"model file missing: {self.requested_path} (HF repo {settings.yolo_hf_repo}) – auto-download failed or offline"

    def is_ready(self) -> bool:
        return self.model is not None

    def get_model_info(self) -> dict:
        return {
            "available": self.is_ready(),
            "requested_path": self.requested_path,
            "resolved_path": str(self.model_path_resolved) if self.model_path_resolved else None,
            "hf_repo": settings.yolo_hf_repo,
            "hf_filename": settings.yolo_hf_filename,
            "conf_min": self.conf_min,
            "labels": self._labels,
            "canonical_map": {k: v for k, v in YOLO_CANONICAL.items() if v is not None},
            "error": self._load_error,
            "ultralytics_available": _YOLO_AVAILABLE,
        }

    def predict(self, df: pl.DataFrame) -> YoloResult:
        """Render chart (§31) + YOLO predict. StockLine yalnızsa None döner."""
        if self.model is None:
            return YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"error": self._load_error or "model not loaded"})

        png_bytes = render_chart(df)
        import tempfile, os
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name)
            tmp_path = tmp.name
        try:
            results = self.model.predict(tmp_path, conf=self.conf_min, verbose=False)
            if not results or len(results) == 0:
                return YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"empty": True})
            r = results[0]
            if r.boxes is None or len(r.boxes) == 0:
                return YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"boxes": 0})
            # Collect all detections (filter StockLine out for ranking, but keep for raw)
            boxes = r.boxes
            confs = boxes.conf.detach().cpu().numpy() if hasattr(boxes.conf, "detach") else boxes.conf
            # ensure numpy
            import numpy as np
            if hasattr(confs, "tolist"):
                confs = np.array(confs.tolist())
            cls_ids = boxes.cls.detach().cpu().numpy().tolist() if hasattr(boxes.cls, "detach") else boxes.cls.tolist() if hasattr(boxes.cls, "tolist") else list(boxes.cls)

            # bbox xyxy (normalized or pixel) – from r.boxes.xyxy
            try:
                xyxy = r.boxes.xyxy.detach().cpu().numpy() if hasattr(r.boxes.xyxy, "detach") else r.boxes.xyxy
                if hasattr(xyxy, "tolist"):
                    xyxy = xyxy.tolist()
            except Exception:
                xyxy = [[0,0,0,0]]*len(cls_ids)

            detections: list[dict] = []
            for idx in range(len(cls_ids)):
                cid = int(cls_ids[idx])
                label = r.names.get(cid, str(cid)) if hasattr(r, "names") else str(cid)
                canon = _canonical(label)
                conf = float(confs[idx]) if hasattr(confs, "__getitem__") else float(confs)
                bbox = xyxy[idx] if idx < len(xyxy) else [0,0,0,0]
                # ensure list of floats
                try:
                    bbox = [float(x) for x in bbox]
                except Exception:
                    bbox = [0,0,0,0]
                detections.append({"label": label, "canonical": canon, "confidence": conf, "cls_id": cid, "bbox": bbox})

            # Sort by confidence desc, prioritize non-StockLine
            non_stock = [d for d in detections if d["canonical"] is not None]
            ranked = sorted(non_stock if non_stock else detections, key=lambda x: x["confidence"], reverse=True)
            if not ranked:
                return YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"detections": detections}, all_detections=detections)
            best = ranked[0]
            if best["canonical"] is None:
                # best is StockLine only – treat as no pattern but return info
                return YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"label": best["label"], "note": "StockLine only", "detections": detections}, all_detections=detections)
            return YoloResult(pattern=best["canonical"], confidence=best["confidence"], is_confirmation=None, raw={"label": best["label"], "cls_id": best["cls_id"], "detections": detections}, all_detections=detections)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def predict_annotated(self, df: pl.DataFrame) -> tuple[bytes | None, YoloResult]:
        """Chart + YOLO plot – döner (annotated_png_bytes, YoloResult)."""
        if self.model is None:
            return None, YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"error": self._load_error})
        png_bytes = render_chart(df)
        import tempfile, os
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name)
            tmp_path = tmp.name
        try:
            results = self.model.predict(tmp_path, conf=self.conf_min, verbose=False)
            if not results or len(results)==0:
                return png_bytes, YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"empty": True})
            r = results[0]
            # annotated image via r.plot() (BGR numpy)
            try:
                plotted = r.plot()  # BGR
                import cv2  # type: ignore
                # convert BGR->RGB for PNG
                plotted_rgb = plotted[:, :, ::-1]
                pil = Image.fromarray(plotted_rgb)
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                annotated = buf.getvalue()
            except Exception:
                annotated = png_bytes
            # reuse predict for structured result (avoid double inference) – parse same r
            # Build YoloResult from r directly (duplicate logic but keep single inference)
            if r.boxes is None or len(r.boxes)==0:
                yr = YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"boxes":0})
            else:
                import numpy as np
                boxes = r.boxes
                confs = boxes.conf.detach().cpu().numpy() if hasattr(boxes.conf,"detach") else boxes.conf
                if hasattr(confs,"tolist"):
                    confs = np.array(confs.tolist())
                cls_ids = boxes.cls.detach().cpu().numpy().tolist() if hasattr(boxes.cls,"detach") else boxes.cls.tolist() if hasattr(boxes.cls,"tolist") else list(boxes.cls)
                try:
                    xyxy = boxes.xyxy.detach().cpu().numpy() if hasattr(boxes.xyxy,"detach") else boxes.xyxy
                    if hasattr(xyxy,"tolist"):
                        xyxy = xyxy.tolist()
                except Exception:
                    xyxy = [[0,0,0,0]]*len(cls_ids)
                dets=[]
                for idx in range(len(cls_ids)):
                    cid=int(cls_ids[idx]); label=r.names.get(cid,str(cid)) if hasattr(r,"names") else str(cid)
                    canon=_canonical(label); conf=float(confs[idx]) if hasattr(confs,"__getitem__") else float(confs)
                    bbox = [float(x) for x in xyxy[idx]] if idx < len(xyxy) else [0,0,0,0]
                    dets.append({"label":label,"canonical":canon,"confidence":conf,"cls_id":cid,"bbox":bbox})
                non_stock=[d for d in dets if d["canonical"] is not None]
                ranked=sorted(non_stock if non_stock else dets, key=lambda x: x["confidence"], reverse=True)
                if not ranked:
                    yr=YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"detections":dets}, all_detections=dets)
                elif ranked[0]["canonical"] is None:
                    yr=YoloResult(pattern=None, confidence=None, is_confirmation=None, raw={"label":ranked[0]["label"],"note":"StockLine only","detections":dets}, all_detections=dets)
                else:
                    best=ranked[0]
                    yr=YoloResult(pattern=best["canonical"], confidence=best["confidence"], is_confirmation=None, raw={"label":best["label"],"cls_id":best["cls_id"],"detections":dets}, all_detections=dets)
            return annotated, yr
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def confirm(self, df: pl.DataFrame, numerical_pattern_type: str | None) -> YoloResult:
        res = self.predict(df)
        if res.pattern is None or res.confidence is None:
            res.is_confirmation = None
            return res
        if numerical_pattern_type is None:
            res.is_confirmation = None
            return res
        # family-level confirmation for triangle subtypes
        if res.pattern == numerical_pattern_type:
            res.is_confirmation = True
        elif res.pattern == "triangle" and numerical_pattern_type in ("triangle", "ascending_triangle", "descending_triangle"):
            res.is_confirmation = True
        elif numerical_pattern_type == "triangle" and res.pattern in ("ascending_triangle", "descending_triangle"):
            res.is_confirmation = True
        elif "triangle" in (res.pattern or "") and "triangle" in (numerical_pattern_type or ""):
            res.is_confirmation = True
        else:
            res.is_confirmation = False
        return res

    def reload(self):
        self.model = None
        self._ensure_and_load()


# Singleton
_yolo_engine: YoloEngine | None = None


def get_yolo_engine() -> YoloEngine:
    global _yolo_engine
    if _yolo_engine is None:
        _yolo_engine = YoloEngine()
    return _yolo_engine


def reset_yolo_engine():
    global _yolo_engine
    _yolo_engine = None


def run_yolo_confirmation(df: pl.DataFrame, numerical_pattern_type: str | None) -> dict:
    engine = get_yolo_engine()
    if not engine.is_ready():
        return {"pattern": None, "confidence": None, "is_confirmation": None, "available": False, "reason": engine._load_error or "model file missing", "labels": engine._labels}
    res = engine.confirm(df, numerical_pattern_type)
    return {
        "pattern": res.pattern,
        "confidence": res.confidence,
        "is_confirmation": res.is_confirmation,
        "available": True,
        "raw": res.raw,
        "all_detections": res.all_detections,
        "model_path": str(engine.model_path_resolved) if engine.model_path_resolved else None,
        "labels": engine._labels,
    }
