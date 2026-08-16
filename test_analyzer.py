"""Analiz motoru entegrasyon testi — Hisse Etki Skoru JSON çıktısı."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from analyzer import analyze_company
from data_fetcher import fetch_company_data


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"JSON serileştirilemez: {type(obj)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hisse verisi çek, analiz et, Hisse Etki Skoru JSON yazdır."
    )
    parser.add_argument(
        "--symbol",
        default="AAPL",
        help='Hisse sembolü (örn. "THYAO.IS", "AAPL")',
    )
    parser.add_argument(
        "--quarters",
        type=int,
        default=4,
        help="Çekilecek çeyrek sayısı (1-4)",
    )
    parser.add_argument(
        "--kap-metni",
        default=None,
        help="Opsiyonel KAP duyuru metni",
    )
    parser.add_argument(
        "--local-fallback",
        action="store_true",
        help="Claude API yerine deterministik yerel derleme kullan",
    )
    args = parser.parse_args()

    try:
        input_data = fetch_company_data(args.symbol, quarter_count=args.quarters)
        result = analyze_company(
            input_data,
            kap_metni=args.kap_metni,
            use_local_fallback=args.local_fallback,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        print(
            json.dumps(
                {"error": f"Beklenmeyen hata: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    payload = result.model_dump(mode="python")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    sys.exit(main())
