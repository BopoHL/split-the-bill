from decimal import Decimal, ROUND_HALF_UP

def to_tiins(amount: float) -> int:
    """Convert human-readable currency units to tiins (integer) safely using Decimal"""
    # Convert to string first to avoid float precision artifacts
    d = Decimal(str(amount))
    return int((d * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def from_tiins(tiins: int) -> float:
    """Convert tiins (integer) to human-readable currency units (float)"""
    # We return float for the API, but do the division via Decimal for precision
    return float(Decimal(tiins) / Decimal('100'))
