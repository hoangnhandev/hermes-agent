#!/usr/bin/env python3
"""Deterministic Vietnamese ad-copy generator for Vinfast models.

Real, model-specific RSA copy (headlines ≤30 chars, descriptions ≤90 chars)
grounded in Vinfast EV selling points (giá/trả góp, bảo hành, sạc, lái thử,
thương hiệu) + segment angles (đô thị / gia đình / premium). Deterministic —
no LLM — so output is reproducible + policy-screenable. The agent (Violet)
may layer extra variations on top, but this gives a deploy-ready baseline with
no placeholder filler.

Policy-safe by design: avoids superlatives / "#1" (Google rejects unverified
superlatives) and restricted terms. All templates are pre-sized so substitution
never exceeds the RSA limits (defensive clamp applied as a last resort).
"""
from __future__ import annotations
from typing import Any

from _budget_calc import VINFAST_MODELS, ModelInfo


def _price_short(price_vnd: int) -> str:
    """280000000 → '280Tr'; 1300000000 → '1.3 Tỷ'."""
    if price_vnd >= 1_000_000_000:
        s = f"{price_vnd / 1_000_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{s} Tỷ"
    return f"{round(price_vnd / 1_000_000)}Tr"


def _clamp(s: str, limit: int) -> str:
    """Truncate to limit (RSA guard). Templates are pre-sized so this rarely
    fires; kept as insurance against future model-name/price growth."""
    return s if len(s) <= limit else s[:limit].rstrip()


def _ctx(m: ModelInfo) -> dict:
    return {"name": m.name, "short": m.slug.upper(), "price": _price_short(m.price_vnd),
            "slug": m.slug}


# ── Base angles (every model) ───────────────────────────────────────────────
# Each angle → 1 variation: 3 headlines + 2 descriptions. Substituted with the
# model context above. Copy is Vietnamese, policy-safe, CTA-oriented (lái thử
# is the primary conversion action).
def _base_angles(c: dict) -> list[dict]:
    return [
        {  # price / finance
            "tag": "gia",
            "headlines": ["{name} từ {price}", "Trả góp {short}", "{short} giá tốt"],
            "descriptions": [
                "Sở hữu {name} trả góp chỉ từ vài triệu/tháng.",
                "Giá {name} từ {price}. Ưu đãi trả góp, lái thử miễn phí.",
            ],
        },
        {  # warranty (Vinfast signature: 10-year)
            "tag": "bao-hanh",
            "headlines": ["{short} bảo hành 10 năm", "Bảo hành {short}", "{short} an tâm"],
            "descriptions": [
                "{name} bảo hành 10 năm — an tâm tuyệt đối.",
                "Pin Vinfast bảo hành dài hạn. Đăng ký lái thử hôm nay.",
            ],
        },
        {  # charging network
            "tag": "sac",
            "headlines": ["{short} sạc toàn quốc", "Sạc nhanh {short}", "{short} sạc_pin".replace("_", " ")],
            "descriptions": [
                "Mạng trạm sạc Vinfast phủ sóng toàn quốc.",
                "Sạc nhanh, lướt điện không lo hết pin giữa đường.",
            ],
        },
        {  # test-drive CTA (primary conversion)
            "tag": "lai-thu",
            "headlines": ["Lái thử {short} miễn phí", "Đăng ký lái thử {short}", "Trải nghiệm {short}"],
            "descriptions": [
                "Đặt lịch lái thử {name} tại đại lý gần nhất.",
                "Trải nghiệm {name} thực tế. Đăng ký lái thử ngay!",
            ],
        },
        {  # brand / national pride (no '#1' — policy-safe)
            "tag": "thuong-hieu",
            "headlines": ["{short} — xe điện Việt", "Vinfast {short}", "{short} tự hào VN"],
            "descriptions": [
                "Tự hào {name} — xe điện Việt đạt chuẩn quốc tế.",
                "{name}: thiết kế Ý, công nghệ hiện đại, tinh thần Việt.",
            ],
        },
    ]


# ── Segment angles (conditional) ────────────────────────────────────────────
def _segment_angles(m: ModelInfo, c: dict) -> list[dict]:
    out: list[dict] = []
    if m.slug in ("vf3", "vf5"):           # mini / A0 — urban
        out.append({
            "tag": "do-thi",
            "headlines": ["{short} lướt phố êm", "{short} nhỏ gọn", "Xe điện ngõ hẻm"],
            "descriptions": [
                "{name} nhỏ gọn, luồn lách ngõ hẻm, đỗ dễ.",
                "Không ồn, không khói — {name} cho phố thị.",
            ],
        })
    if m.slug in ("vf5", "vf6", "vf8"):    # family SUVs
        out.append({
            "tag": "gia-dinh",
            "headlines": ["{short} cho gia đình", "SUV {short} rộng", "{short} an toàn"],
            "descriptions": [
                "{name} rộng rãi, an toàn cho cả gia đình.",
                "Không gian rộng, tiện nghi đầy đủ — {name}.",
            ],
        })
    if m.slug in ("vf7", "vf8", "vf9"):    # premium / flagship
        out.append({
            "tag": "premium",
            "headlines": ["{short} đẳng cấp", "Premium {short}", "{short} thể thao"],
            "descriptions": [
                "{name} — thiết kế thể thao, công nghệ tiên phong.",
                "Trải nghiệm lái cao cấp cùng {name}.",
            ],
        })
    return out


def build_variations(model_slug: str, plan: dict | None = None) -> list[dict]:
    """Build real VN ad-copy variations for a Vinfast model slug.

    Returns a list of dicts: {headlines:[3], descriptions:[2], path1, path2}.
    Raises KeyError for an unknown model slug (caller falls back if needed).
    """
    m = VINFAST_MODELS[model_slug.lower().strip()]
    c = _ctx(m)
    angles = _base_angles(c) + _segment_angles(m, c)
    variations: list[dict] = []
    for a in angles:
        variations.append({
            "headlines": [_clamp(h.format(**c), 30) for h in a["headlines"]],
            "descriptions": [_clamp(d.format(**c), 90) for d in a["descriptions"]],
            "path1": m.slug,
            "path2": a["tag"],
        })
    return variations


if __name__ == "__main__":   # quick self-check: print copy + char lengths
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "vf3"
    for i, v in enumerate(build_variations(slug), 1):
        print(f"\n#{i} [{v['path2']}]")
        for h in v["headlines"]:
            print(f"  H[{len(h):>2}] {h}")
        for d in v["descriptions"]:
            print(f"  D[{len(d):>2}] {d}")
