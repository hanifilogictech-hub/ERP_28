import math
from datetime import date, timedelta


def month_range(today: date, offset: int):
    total_month = (today.year * 12 + today.month - 1) - offset
    year = total_month // 12
    month = total_month % 12 + 1
    start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def _fmt_tick(value: float):
    if value >= 100000:
        return f"{value / 100000:.1f}L"
    if value >= 1000:
        return f"{value / 1000:.0f}K"
    return str(int(round(value)))


def build_chart(labels, values, steps=6):
    max_val = max(values) if values else 0
    if max_val <= 0:
        y_max = float(steps)
    else:
        step_value = max(1, math.ceil(max_val / steps))
        y_max = step_value * steps

    points = []
    for label, value in zip(labels, values):
        points.append(
            {
                "label": label,
                "value": value,
                "height": round((value / y_max) * 100, 2),
            }
        )

    y_ticks = []
    for i in range(steps, -1, -1):
        y_ticks.append(_fmt_tick((y_max / steps) * i))

    return {"points": points, "y_ticks": y_ticks}

