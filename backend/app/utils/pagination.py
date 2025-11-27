from math import ceil

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def validate_pagination(page: int | None, page_size: int | None) -> tuple[int, int]:
    page = 1 if page is None else max(1, int(page))
    page_size = DEFAULT_PAGE_SIZE if page_size is None else clamp(int(page_size), 1, MAX_PAGE_SIZE)
    return page, page_size


def page_meta(page: int, page_size: int, total_items: int) -> dict:
    if total_items:
        total_pages = max(1, ceil(total_items / page_size))
    else:
        total_pages = 1

    return {
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
