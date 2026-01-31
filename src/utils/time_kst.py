# utils/time_kst.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

@dataclass
class KSTNow:
    epoch: int
    kst_text: str
    dt: datetime

def now_kst() -> KSTNow:
    dt = datetime.now(KST).replace(microsecond=0)
    return KSTNow(
        epoch=int(dt.timestamp()),
        kst_text=dt.strftime("%Y/%m/%d %H:%M:%S"),
        dt=dt,
    )
