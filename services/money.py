from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
ZERO = Decimal('0')
def D(value):
    if value is None or value == '': return ZERO
    result = Decimal(str(value))
    if not result.is_finite(): raise ValueError('Number must be finite')
    return result
def money(value): return D(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
def numeric(value, negative=False):
    try: result = D(value)
    except (InvalidOperation, ValueError): raise ValueError('Invalid numeric value')
    if abs(result) > Decimal('1000000000000') or (result < 0 and not negative): raise ValueError('Number out of range')
    return str(result)
