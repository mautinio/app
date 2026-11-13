def split_evenly(total: int, parts: int) -> list[int]:
    """Целые доли, в сумме ровно `total`; остаток раздаётся первым: split_evenly(100, 3) -> [34, 33, 33]."""
    if parts <= 0:
        return []
    base, rest = divmod(total, parts)
    return [base + (1 if i < rest else 0) for i in range(parts)]
