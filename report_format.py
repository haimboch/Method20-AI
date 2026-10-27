"""Display-only number formatting. Never round values used in trading rules."""
import math
import re
from numbers import Real

_NUM=re.compile(r'(?<![A-Za-z0-9_])([+-]?\d+\.\d{3,})(?![0-9.])')

def fmt2(value):
    if value is None:
        return "לא זמין"
    try:
        number=float(value)
        if not math.isfinite(number):
            return "לא זמין"
        return f"{number:.2f}"
    except (ValueError,TypeError):
        return "לא זמין"

def fmt_signed(value):
    if value is None:
        return "לא זמין"
    try:
        number=float(value)
        return f"{number:+.2f}" if math.isfinite(number) else "לא זמין"
    except (ValueError,TypeError):
        return "לא זמין"

def format_numbers_in_text(value):
    """Format decimal numeric values embedded in explanatory strings.

    Avoids changing integer counts, dates and non-decimal IDs.
    """
    if isinstance(value,Real) and not isinstance(value,bool):
        return fmt2(value)
    if value is None:
        return "לא זמין"
    text=str(value)
    return _NUM.sub(lambda m:fmt2(m.group(1)),text)
