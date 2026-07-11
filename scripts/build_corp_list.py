# -*- coding: utf-8 -*-
"""
corpCode_cache.json(전체 11만+건)에서 상장사만 추려 corp_list.json(웹 검색용, 경량)을 생성한다.
corpCode_cache.json이 없으면 financial_analyzer.load_corp_codes()로 먼저 받아온다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import financial_analyzer as fa

corp_list = fa.load_corp_codes()
listed = [c for c in corp_list if c["stock_code"]]
listed.sort(key=lambda c: c["corp_name"])

compact = [[c["corp_name"], c["corp_code"], c["stock_code"]] for c in listed]

out_path = ROOT / "corp_list.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

print(f"[완료] 상장사 {len(compact)}건 -> {out_path.name} ({out_path.stat().st_size/1024:.1f} KB)")
