"""Data fetcher entegrasyon testi — INPUT_SCHEMA JSON çıktısı."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from data_fetcher import fetch_company_data


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"JSON serileştirilemez: {type(obj)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hisse finansal verisi çek ve INPUT_SCHEMA JSON yazdır."
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
    args = parser.parse_args()

    try:
        result = fetch_company_data(args.symbol, quarter_count=args.quarters)
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
