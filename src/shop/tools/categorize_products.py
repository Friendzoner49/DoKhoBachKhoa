"""One-time backfill of `products.category` for the catalog that existed
before the website got category grouping (18/10/2026) -- the column was
in the schema from the start but nothing ever wrote to it.

Like import_xlsx, this is meant to run once and then stay out of the
way: going forward, categories are set/changed from the app's product
dialog (an editable combo listing categories already in use). Re-running
this is harmless for any code still in CODE_TO_CATEGORY below, but it
will never touch a product added after this script was written -- those
need a category set by hand in the app.

Usage:
    uv run python -m shop.tools.categorize_products
"""
from shop.core.products import list_products, set_category
from shop.db.migrate import connect

CATEGORY_LABELS = {
    "gao-mi": "Gạo, bún, miến, mì, phở",
    "bot": "Bột & nguyên liệu làm bánh",
    "giavi": "Gia vị, nước mắm, nước chấm",
    "rauqua": "Rau, củ, nấm & thực phẩm tươi",
    "dauhat": "Đậu, hạt, vừng, lạc",
    "cafe": "Cà phê, trà, đồ uống",
    "banhkeo": "Bánh kẹo & đồ ăn vặt",
    "giadung": "Đồ gia dụng & khác",
}

CODE_TO_CATEGORY = {
    # Gạo, bún, miến, mì, phở
    "GAO001": "gao-mi", "GAO002": "gao-mi", "GAO003": "gao-mi", "GAO004": "gao-mi", "GAO005": "gao-mi",
    "BUN01": "gao-mi", "BUN02": "gao-mi", "BUN03": "gao-mi", "PHO001": "gao-mi",
    "MIEN01": "gao-mi", "MIEN02": "gao-mi", "MIEN03": "gao-mi", "MIEN04": "gao-mi",
    "MYF001": "gao-mi", "MYF002": "gao-mi",
    "MT0001": "gao-mi", "MT0002": "gao-mi", "MT0003": "gao-mi", "MT0004": "gao-mi",
    "MT0005": "gao-mi", "MT0006": "gao-mi", "MT0007": "gao-mi", "MT0008": "gao-mi", "MT0009": "gao-mi",
    # Bột & nguyên liệu làm bánh
    "BOBC01": "bot", "BOBX01": "bot", "BOCG01": "bot", "BOCX01": "bot", "BONA01": "bot",
    "BONC01": "bot", "BONE01": "bot", "BOQU01": "bot", "BORC01": "bot", "BOSS01": "bot",
    # Gia vị, nước mắm, nước chấm
    "BOCA01": "giavi", "BONV01": "giavi",
    "DAUHA1": "giavi", "DAUHA2": "giavi", "DAUME1": "giavi",
    "DIHU01": "giavi", "HOI001": "giavi", "QUET01": "giavi", "THQUA1": "giavi",
    "TIBOT1": "giavi", "TIHAT1": "giavi",
    "MAM001": "giavi", "MAM002": "giavi", "MAM003": "giavi", "MAM004": "giavi",
    "MAM005": "giavi", "MAM006": "giavi", "MAM007": "giavi",
    "NTUG01": "giavi", "NTUG02": "giavi",
    "TUOT01": "giavi", "TUOT02": "giavi", "TUOT03": "giavi", "TUOT04": "giavi",
    "TUBAN1": "giavi", "XIDAU1": "giavi", "XIDAU2": "giavi", "XIDAU3": "giavi",
    "SATE01": "giavi", "LGM001": "giavi", "NMAU01": "giavi", "MECHU1": "giavi",
    "OT0001": "giavi", "OT0002": "giavi", "OT0003": "giavi",
    "HANKO1": "giavi", "HANKR0": "giavi", "HANKR1": "giavi",
    "MYCHI1": "giavi", "MYCHI2": "giavi",
    "GIAVI1": "giavi", "GIAVI2": "giavi", "GLAUB1": "giavi", "GLAUH1": "giavi",
    "CODUA1": "giavi", "CODUA2": "giavi", "SDUA01": "giavi",
    "VIVP01": "giavi", "VIVP02": "giavi",
    # Rau, củ, nấm & thực phẩm tươi
    "CABS01": "rauqua", "MANG01": "rauqua", "NAMH01": "rauqua", "NAMT01": "rauqua",
    "MONHI1": "rauqua", "RIENG1": "rauqua", "SAT001": "rauqua", "TACHU1": "rauqua",
    "GAC001": "rauqua", "KEGA01": "rauqua", "CP0001": "rauqua", "CPT001": "rauqua", "CHNV01": "rauqua",
    # Đậu, hạt, vừng, lạc
    "DAUDE1": "dauhat", "DAUXA1": "dauhat", "DAUXA2": "dauhat", "DAUN01": "dauhat",
    "VUDEN1": "dauhat", "VUTRA1": "dauhat", "KEO005": "dauhat", "KEO006": "dauhat",
    # Cà phê, trà, đồ uống
    "CAFE01": "cafe", "CAFE02": "cafe", "CAFE03": "cafe", "CAFE04": "cafe", "CAFE05": "cafe",
    "CAFE06": "cafe", "CAFE07": "cafe", "CAFE08": "cafe", "CAFE09": "cafe", "CAFE10": "cafe", "CAFE11": "cafe",
    "CHETN1": "cafe", "CHETN2": "cafe", "VINUT1": "cafe", "BOCC01": "cafe", "PHIN01": "cafe",
    # Bánh kẹo & đồ ăn vặt
    "BADAM1": "banhkeo", "BADAT1": "banhkeo", "BADAV1": "banhkeo", "BDX001": "banhkeo", "BDXCLS": "banhkeo",
    "BGAO01": "banhkeo", "BGAO02": "banhkeo", "BGAO03": "banhkeo", "BGAO04": "banhkeo",
    "BLAI01": "banhkeo", "BTRA01": "banhkeo",
    "KEO001": "banhkeo", "KEO002": "banhkeo", "KEO003": "banhkeo", "KEO004": "banhkeo",
    "HQUA01": "banhkeo", "MITSAY": "banhkeo",
    "THLH01": "banhkeo", "THNC01": "banhkeo", "THSC01": "banhkeo",
    "PHTOM1": "banhkeo", "PHTOM2": "banhkeo", "CHAO1": "banhkeo", "TOMYA1": "banhkeo",
    # Đồ gia dụng & khác
    "NOICOM": "giadung", "THULA1": "giadung",
}


def main():
    conn = connect()
    products = {p["code"]: p for p in list_products(conn, active_only=False)}

    updated, already_set, unknown = 0, 0, []
    for code, slug in CODE_TO_CATEGORY.items():
        if code not in products:
            continue
        label = CATEGORY_LABELS[slug]
        if products[code]["category"] == label:
            already_set += 1
            continue
        set_category(conn, code, label)
        updated += 1

    for code in products:
        if code not in CODE_TO_CATEGORY:
            unknown.append(code)

    print(f"Updated {updated} products, {already_set} already had the right category.")
    if unknown:
        print(f"{len(unknown)} product(s) have no mapping (left as-is): {', '.join(unknown)}")


if __name__ == "__main__":
    main()
