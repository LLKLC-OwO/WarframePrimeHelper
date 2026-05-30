"""部件名识别与弓类兜底。"""

from warframe_prime_helper.constants import PART_MAP, PART_MATCH_PRIORITY, SUFFIX_CN_NAME
from warframe_prime_helper.text import normalize_text


class PartMatcher:
    def __init__(self, part_map: dict[str, str] | None = None):
        source = part_map or PART_MAP
        self.part_map_entries = [
            (normalize_text(k), v, k) for k, v in source.items()
        ]

    def _pick_part_match(self, matches: list[tuple[str, str, str]]) -> tuple[str, str, str]:
        non_blueprint = [m for m in matches if m[1] != "blueprint"]
        pool = non_blueprint or matches
        return max(pool, key=lambda m: (PART_MATCH_PRIORITY.get(m[1], 5), len(m[0])))

    def resolve_part_suffix(self, leftover_text: str) -> tuple[str, str]:
        matches = []
        for cn_norm, en, cn_display in self.part_map_entries:
            if cn_norm and cn_norm in leftover_text:
                matches.append((cn_norm, en, cn_display))

        if not matches:
            return "set", ""

        chosen = self._pick_part_match(matches)
        return chosen[1], chosen[2]

    def try_bow_part_fallback(
        self,
        base_url: str,
        real_name: str,
        clean_ocr: str,
        fetch_price,
    ) -> tuple[str | None, str | None, str | None, bool | None]:
        bow_hint = ("弓" in real_name) or ("弓" in clean_ocr)
        if not bow_hint:
            return None, None, None, None

        suffix_candidates = [
            "grip",
            "string",
            "limb",
            "upper_limb",
            "lower_limb",
            "blueprint",
        ]
        for suffix in suffix_candidates:
            test_url = f"{base_url}_{suffix}"
            test_price, test_is_fast = fetch_price(test_url)
            if test_price:
                cn_name = SUFFIX_CN_NAME.get(suffix, suffix)
                return suffix, cn_name, test_price, test_is_fast
        return None, None, None, None
