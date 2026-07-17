"""build_drug_classi_db."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "drug_classi.db"
MD_PATH = ROOT / "drug_classi.md"

RAW_ENTRIES: list[tuple[str, str, str, str, str, str]] = []

_NARCOTIC = [
    ("阿芬太尼", "Alfentanil"),
    ("阿法罗定", "Alphaprodine"),
    ("阿尼利定", "Anileridine"),
    ("布桂嗪", "Bucinnazine"),
    ("可待因", "Codeine"),
    ("罂粟浓缩物", "Concentrate of Poppy Straw"),
    ("地芬诺辛", "Difenoxin"),
    ("双氢可待因", "Dihydrocodeine"),
    ("二氢埃托啡", "Dihydroetorphine"),
    ("地芬诺酯", "Diphenoxylate"),
    ("羟蒂巴酚", "Drotebanol"),
    ("乙基吗啡", "Ethylmorphine"),
    ("芬太尼", "Fentanyl"),
    ("氢可酮", "Hydrocodone"),
    ("氢吗啡酮", "Hydromorphone"),
    ("左啡诺", "Levorphanol"),
    ("美沙酮", "Methadone"),
    ("吗啡", "Morphine"),
    ("奥赛利定", "Oliceridine"),
    ("阿片", "Opium"),
    ("羟考酮", "Oxycodone"),
    ("羟吗啡酮", "Oxymorphone"),
    ("哌替啶", "Pethidine"),
    ("福尔可定", "Pholcodine"),
    ("罂粟壳", "Poppy Shell"),
    ("消旋甲啡烷", "Racemethorphan"),
    ("消旋啡烷", "Racemorphan"),
    ("瑞芬太尼", "Remifentanil"),
    ("舒芬太尼", "Sufentanil"),
    ("泰吉利定", "Tegileridine"),
    ("蒂巴因", "Thebaine"),
    ("替利定", "Tilidine"),
]
for zh, en in _NARCOTIC:
    RAW_ENTRIES.append((zh, en, "麻醉药品", "药用类", "药用类麻醉药品目录（2025年版）", ""))

_PSY_I = [
    ("安非拉酮", "Amfepramone"),
    ("苯丙胺", "Amfetamine"),
    ("苄基哌嗪", "Benzylpiperazine"),
    ("丁丙诺啡", "Buprenorphine"),
    ("右苯丙胺", "Dexamfetamine"),
    ("γ-羟丁酸", "Gamma-hydroxybutyrate"),
    ("氯胺酮", "Ketamine"),
    ("左苯丙胺", "Levamfetamine"),
    ("马吲哚", "Mazindol"),
    ("甲喹酮", "Methaqualone"),
    ("哌甲酯", "Methylphenidate"),
    ("咪达唑仑原料药及注射剂", "Midazolam API and Injection"),
    ("司可巴比妥", "Secobarbital"),
    ("他喷他多", "Tapentadol"),
    ("三唑仑", "Triazolam"),
    ("齐培丙醇", "Zipeprol"),
    ("含氢可酮复方口服固体制剂（>5mg/单位）", "Hydrocodone Combination Oral Solid Dosage Forms (>5mg/unit)"),
    ("含羟考酮复方口服固体制剂（>5mg/单位）", "Oxycodone Combination Oral Solid Dosage Forms (>5mg/unit)"),
]
for zh, en in _PSY_I:
    RAW_ENTRIES.append((zh, en, "精神药品", "第一类", "药用类精神药品目录（2025年版）", ""))

_PSY_II = [
    ("阿洛巴比妥", "Allobarbital"),
    ("阿普唑仑", "Alprazolam"),
    ("异戊巴比妥", "Amobarbital"),
    ("巴比妥", "Barbital"),
    ("溴西泮", "Bromazepam"),
    ("溴替唑仑", "Brotizolam"),
    ("丁丙诺啡透皮贴剂", "Buprenorphine Transdermal Patch"),
    ("布他比妥", "Butalbital"),
    ("布托啡诺", "Butorphanol"),
    ("咖啡因", "Caffeine"),
    ("安钠咖", "Caffeine Sodium Benzoate"),
    ("卡立普多", "Carisoprodol"),
    ("去甲伪麻黄碱", "Cathine"),
    ("西博帕多", "Cebranopadol"),
    ("氯氮䓬", "Chlordiazepoxide"),
    ("氯巴占", "Clobazam"),
    ("氯硝西泮", "Clonazepam"),
    ("氯噻西泮", "Clotiazepam"),
    ("氯噁唑仑", "Cloxazolam"),
    ("地洛西泮", "Delorazepam"),
    ("右旋芬氟拉明", "Dexfenfluramine"),
    ("右美沙芬", "Dextromethorphan"),
    ("地佐辛", "Dezocine"),
    ("地西泮", "Diazepam"),
    ("地达西尼", "Dimdazenil"),
    ("依他佐辛", "Eptazocine"),
    ("麦角胺咖啡因片", "Ergotamine and Caffeine Tablet"),
    ("艾司唑仑", "Estazolam"),
    ("氯氟䓬乙酯", "Ethyl Loflazepate"),
    ("依替唑仑", "Etizolam"),
    ("依托咪酯", "Etomidate"),
    ("芬氟拉明", "Fenfluramine"),
    ("氟地西泮", "Fludiazepam"),
    ("氟硝西泮", "Flunitrazepam"),
    ("氟西泮", "Flurazepam"),
    ("格鲁米特", "Glutethimide"),
    ("卤沙唑仑", "Haloxazolam"),
    ("氯普唑仑", "Loprazolam"),
    ("劳拉西泮", "Lorazepam"),
    ("氯卡色林", "Lorcaserin"),
    ("氯甲西泮", "Lormetazepam"),
    ("美达西泮", "Medazepam"),
    ("甲丙氨酯", "Meprobamate"),
    ("甲苯巴比妥", "Methylphenobarbital"),
    ("咪达唑仑", "Midazolam"),
    ("莫达非尼", "Modafinil"),
    ("纳布啡", "Nalbuphine"),
    ("纳呋拉啡", "Nalfurafine"),
    ("尼美西泮", "Nimetazepam"),
    ("硝西泮", "Nitrazepam"),
    ("去甲西泮", "Nordazepam"),
    ("奥沙西泮", "Oxazepam"),
    ("奥沙唑仑", "Oxazolam"),
    ("喷他佐辛", "Pentazocine"),
    ("戊巴比妥", "Pentobarbital"),
    ("吡仑帕奈", "Perampanel"),
    ("苯甲曲秦", "Phendimetrazine"),
    ("苯巴比妥", "Phenobarbital"),
    ("芬特明", "Phentermine"),
    ("匹那西泮", "Pinazepam"),
    ("哌苯甲醇", "Pipradrol"),
    ("普拉西泮", "Prazepam"),
    ("瑞马唑仑", "Remimazolam"),
    ("仲丁比妥", "Secbutabarbital"),
    ("丝右哌甲酯", "Serdexmethylphenidate"),
    ("替马西泮", "Temazepam"),
    ("四氢西泮", "Tetrazepam"),
    ("曲马多", "Tramadol"),
    ("韦利西贝", "Valiloxybate"),
    ("扎来普隆", "Zaleplon"),
    ("唑吡坦", "Zolpidem"),
    ("佐匹克隆", "Zopiclone"),
    ("舒拉诺龙", "Zuranolone"),
    ("丁丙诺啡和纳洛酮复方口服固体制剂", "Buprenorphine and Naloxone Combination Oral Solid Dosage Forms"),
    ("含可待因复方口服液体制剂", "Codeine Combination Oral Liquid Dosage Forms"),
    ("含地芬诺酯复方制剂", "Diphenoxylate Combination Preparations"),
    ("含氢可酮复方口服固体制剂（≤5mg/单位）", "Hydrocodone Combination Oral Solid Dosage Forms (≤5mg/unit)"),
    ("含羟考酮复方口服固体制剂（≤5mg/单位）", "Oxycodone Combination Oral Solid Dosage Forms (≤5mg/unit)"),
]
for zh, en in _PSY_II:
    RAW_ENTRIES.append((zh, en, "精神药品", "第二类", "药用类精神药品目录（2025年版）", ""))

_TOXIC_TCM = [
    ("砒石", "Arsenolite (red/white arsenic)"),
    ("砒霜", "Arsenic Trioxide (processed)"),
    ("水银", "Mercury"),
    ("生马钱子", "Raw Strychnos nux-vomica Seed"),
    ("生川乌", "Raw Aconitum carmichaelii Tuber"),
    ("生草乌", "Raw Aconitum kusnezoffii Tuber"),
    ("生白附子", "Raw Typhonium giganteum Tuber"),
    ("生附子", "Raw Aconitum carmichaelii Daughter Root"),
    ("生半夏", "Raw Pinellia ternata Tuber"),
    ("生南星", "Raw Arisaema erubescens Tuber"),
    ("生巴豆", "Raw Croton tiglium Seed"),
    ("斑蝥", "Mylabris"),
    ("青娘虫", "Lytta caragana"),
    ("红娘虫", "Lytta vesicatoria"),
    ("生甘遂", "Raw Kansui Root"),
    ("生狼毒", "Raw Euphorbia fischeriana Root"),
    ("生藤黄", "Raw Garcinia hanburyi Resin"),
    ("生千金子", "Raw Euphorbia lathyris Seed"),
    ("生天仙子", "Raw Hyoscyamus niger Seed"),
    ("闹羊花", "Rhododendron molle Flower"),
    ("雪上一枝蒿", "Aconitum brachypodum Root"),
    ("红升丹", "Red Mercuric Oxide Preparation"),
    ("白降丹", "White Mercuric Chloride Preparation"),
    ("蟾酥", "Bufonis Venenum"),
    ("洋金花", "Datura metel Flower"),
    ("红粉", "Mercuric Oxide"),
    ("轻粉", "Calomel"),
    ("雄黄", "Realgar"),
]
for zh, en in _TOXIC_TCM:
    RAW_ENTRIES.append((zh, en, "毒性药品", "毒性中药", "医疗用毒性药品管理办法", "指原药材及饮片"))

_TOXIC_WM = [
    ("去乙酰毛花苷丙", "Deslanoside"),
    ("阿托品", "Atropine"),
    ("洋地黄毒苷", "Digitoxin"),
    ("氢溴酸后马托品", "Homatropine Hydrobromide"),
    ("三氧化二砷", "Arsenic Trioxide"),
    ("毛果芸香碱", "Pilocarpine"),
    ("升汞", "Mercuric Chloride"),
    ("水杨酸毒扁豆碱", "Physostigmine Salicylate"),
    ("亚砷酸钾", "Potassium Arsenite"),
    ("氢溴酸东莨菪碱", "Scopolamine Hydrobromide"),
    ("士的宁", "Strychnine"),
]
for zh, en in _TOXIC_WM:
    RAW_ENTRIES.append((zh, en, "毒性药品", "毒性西药", "医疗用毒性药品管理办法", "指原料药"))

_HAM_A = [
    ("10%氯化钠注射液", "10% Sodium Chloride Injection"),
    ("15%氯化钾注射液", "15% Potassium Chloride Injection"),
    ("25%硫酸镁注射液", "25% Magnesium Sulfate Injection"),
    ("50%葡萄糖注射液", "50% Glucose Injection"),
    ("甘精胰岛素注射液", "Insulin Glargine Injection"),
    ("重组人胰岛素注射液", "Recombinant Human Insulin Injection"),
    ("丙泊酚", "Propofol"),
    ("七氟烷", "Sevoflurane"),
    ("依托咪酯", "Etomidate"),
    ("胺碘酮", "Amiodarone"),
    ("利多卡因", "Lidocaine"),
    ("灭菌注射用水", "Sterile Water for Injection"),
    ("肾上腺素", "Epinephrine"),
    ("去甲肾上腺素", "Norepinephrine"),
    ("普萘洛尔", "Propranolol"),
    ("美托洛尔", "Metoprolol"),
    ("艾司洛尔", "Esmolol"),
    ("去乙酰毛花苷", "Deslanoside"),
    ("米力农", "Milrinone"),
    ("低分子量肝素", "Low Molecular Weight Heparin"),
    ("替罗非班", "Tirofiban"),
    ("阿加曲班", "Argatroban"),
    ("比伐卢定", "Bivalirudin"),
    ("阿替普酶", "Alteplase"),
    ("顺铂", "Cisplatin"),
    ("紫杉醇", "Paclitaxel"),
    ("表柔比星", "Epirubicin"),
    ("吗啡", "Morphine"),
    ("舒芬太尼", "Sufentanil"),
    ("碘海醇", "Iohexol"),
    ("碘克沙醇", "Iodixanol"),
    ("硝普钠注射液", "Sodium Nitroprusside Injection"),
    ("注射用三氧化二砷", "Arsenic Trioxide"),
    ("阿托品注射液（规格≥5mg/支）", "Atropine Injection (≥5mg/vial)"),
    ("肾上腺素（皮下注射）", "Epinephrine (Subcutaneous)"),
]
_HAM_B = [
    ("华法林", "Warfarin"),
    ("利伐沙班", "Rivaroxaban"),
    ("达比加群酯", "Dabigatran Etexilate"),
    ("小儿复方氨基酸（19AA-I）", "Pediatric Compound Amino Acid (19AA-I)"),
    ("复方氨基酸（18AA-II）", "Compound Amino Acid (18AA-II)"),
    ("卡培他滨", "Capecitabine"),
    ("巯嘌呤", "Mercaptopurine"),
    ("依托泊苷", "Etoposide"),
    ("阿那曲唑", "Anastrozole"),
    ("他莫昔芬", "Tamoxifen"),
    ("氟他胺", "Flutamide"),
    ("两性霉素B", "Amphotericin B"),
    ("两性霉素B脂质体", "Amphotericin B Liposomal"),
    ("维库溴铵", "Vecuronium Bromide"),
    ("罗库溴铵", "Rocuronium Bromide"),
    ("多索茶碱", "Doxofylline"),
    ("氨茶碱", "Aminophylline"),
    ("加压素", "Vasopressin"),
    ("特利加压素", "Terlipressin"),
    ("去氨加压素", "Desmopressin"),
    ("咪达唑仑", "Midazolam"),
    ("水合氯醛", "Chloral Hydrate"),
    ("美西律", "Mexiletine"),
    ("普罗帕酮", "Propafenone"),
    ("羟考酮", "Oxycodone"),
    ("芬太尼", "Fentanyl"),
    ("格列美脲", "Glimepiride"),
    ("瑞格列奈", "Repaglinide"),
    ("吡格列酮", "Pioglitazone"),
    ("二甲双胍", "Metformin"),
    ("利拉鲁肽", "Liraglutide"),
    ("度拉糖肽", "Dulaglutide"),
    ("吉非替尼", "Gefitinib"),
    ("奥拉帕利", "Olaparib"),
    ("索拉非尼", "Sorafenib"),
    ("万古霉素", "Vancomycin"),
    ("凝血酶散", "Thrombin Powder"),
    ("缩宫素", "Oxytocin"),
    ("异丙嗪", "Promethazine"),
]
_HAM_C = [
    ("阿卡波糖", "Acarbose"),
    ("达格列净", "Dapagliflozin"),
    ("西格列汀", "Sitagliptin"),
    ("甲氨蝶呤（口服，非肿瘤用途）", "Methotrexate (Oral, Non-oncology)"),
    ("阿片酊", "Opium Tincture"),
    ("高锰酸钾外用制剂", "Potassium Permanganate Topical Preparation"),
    ("阿维A", "Acitretin"),
    ("异维A酸", "Isotretinoin"),
    ("利巴韦林", "Ribavirin"),
    ("沙利度胺", "Thalidomide"),
    ("环孢素", "Cyclosporine"),
    ("他克莫司", "Tacrolimus"),
    ("丙戊酸钠", "Sodium Valproate"),
    ("卡马西平", "Carbamazepine"),
    ("地高辛", "Digoxin"),
    ("硝酸甘油", "Nitroglycerin"),
    ("阿仑膦酸钠", "Alendronate Sodium"),
]
for zh, en in _HAM_A:
    RAW_ENTRIES.append((zh, en, "高警示药品", "A级", "高警示药品推荐目录（2025版）", ""))
for zh, en in _HAM_B:
    RAW_ENTRIES.append((zh, en, "高警示药品", "B级", "高警示药品推荐目录（2025版）", ""))
for zh, en in _HAM_C:
    RAW_ENTRIES.append((zh, en, "高警示药品", "C级", "高警示药品推荐目录（2025版）", ""))

_ZH_ALIASES: dict[str, str] = {
    "去乙酰毛花苷": "去乙酰毛花苷丙",
    "注射用三氧化二砷": "三氧化二砷",
    "阿托品注射液（规格≥5mg/支）": "阿托品",
}

def _canonical_zh(zh: str) -> str:
    return _ZH_ALIASES.get(zh.strip(), zh.strip())

def _norm_key(zh: str, en: str) -> str:
    return en.strip().lower() or _canonical_zh(zh).lower()

def build_db() -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS drug_entries;
            DROP TABLE IF EXISTS drugs_unique;

            CREATE TABLE drug_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name_zh     TEXT NOT NULL,
                name_en     TEXT NOT NULL,
                category    TEXT NOT NULL,
                subcategory TEXT,
                source_doc  TEXT NOT NULL,
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE drugs_unique (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name_zh     TEXT NOT NULL,
                name_en     TEXT NOT NULL,
                aliases_zh  TEXT DEFAULT '[]',
                categories  TEXT NOT NULL,
                sources     TEXT NOT NULL
            );

            CREATE INDEX idx_entries_zh ON drug_entries(name_zh);
            CREATE INDEX idx_unique_zh ON drugs_unique(name_zh);
        """)

        conn.executemany(
            "INSERT INTO drug_entries (name_zh, name_en, category, subcategory, source_doc, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            RAW_ENTRIES,
        )

        merged: dict[str, dict] = {}
        for zh, en, cat, sub, src, notes in RAW_ENTRIES:
            key = _norm_key(zh, en)
            if key not in merged:
                merged[key] = {
                    "name_zh": _canonical_zh(zh),
                    "name_en": en,
                    "aliases_zh": set(),
                    "categories": set(),
                    "sources": set(),
                }
            canon = _canonical_zh(zh)
            if zh.strip() != canon:
                merged[key]["aliases_zh"].add(zh.strip())
            elif zh.strip() != merged[key]["name_zh"]:
                merged[key]["aliases_zh"].add(zh.strip())
            label = f"{cat}/{sub}" if sub else cat
            merged[key]["categories"].add(label)
            merged[key]["sources"].add(src)

        unique_rows = [
            (
                v["name_zh"],
                v["name_en"],
                json.dumps(sorted(v["aliases_zh"]), ensure_ascii=False),
                json.dumps(sorted(v["categories"]), ensure_ascii=False),
                json.dumps(sorted(v["sources"]), ensure_ascii=False),
            )
            for v in merged.values()
        ]
        conn.executemany(
            "INSERT INTO drugs_unique (name_zh, name_en, aliases_zh, categories, sources) "
            "VALUES (?, ?, ?, ?, ?)",
            unique_rows,
        )
        conn.commit()

        stats = {
            "total_entries": len(RAW_ENTRIES),
            "unique_drugs": len(unique_rows),
            "by_category": {},
        }
        for cat, _ in conn.execute(
            "SELECT category, COUNT(*) FROM drug_entries GROUP BY category ORDER BY category"
        ):
            stats["by_category"][cat] = _
        return stats
    finally:
        conn.close()

def build_md(stats: dict) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        lines = [
            "# 特殊管理药品分类目录",
            "",
            "> 自动由 `build_drug_classi_db.py` 生成，请勿手工编辑。",
            "",
            "## 数据来源",
            "",
            "| 目录 | 条目数 | 法规/文件 |",
            "|------|--------|-----------|",
            f"| 药用类麻醉药品（2025年版） | {len(_NARCOTIC)} | 国家药监局等2025年第55号公告 |",
            f"| 第一类精神药品 | {len(_PSY_I)} | 药用类精神药品目录（2025年版） |",
            f"| 第二类精神药品 | {len(_PSY_II)} | 药用类精神药品目录（2025年版） |",
            f"| 毒性中药 | {len(_TOXIC_TCM)} | 医疗用毒性药品管理办法（国务院令第23号） |",
            f"| 毒性西药 | {len(_TOXIC_WM)} | 医疗用毒性药品管理办法（国务院令第23号） |",
            f"| 高警示药品（2025版） | {len(_HAM_A)+len(_HAM_B)+len(_HAM_C)} | 药物不良反应杂志 2025;27(10):613-620 |",
            "",
            f"**分类条目合计**：{stats['total_entries']} 条（含跨类重复）",
            f"**去重后药品**：{stats['unique_drugs']} 种",
            "",
            "---",
            "",
            "## 一、去重汇总表（按中文名排序）",
            "",
            "| 中文名 | 英文名 | 别名 | 所属分类 | 来源 |",
            "|--------|--------|------|----------|------|",
        ]

        for zh, en, aliases, cats, srcs in conn.execute(
            "SELECT name_zh, name_en, aliases_zh, categories, sources "
            "FROM drugs_unique ORDER BY name_zh"
        ):
            alias_list = ", ".join(json.loads(aliases)) or "—"
            cat_list = ", ".join(json.loads(cats))
            src_list = ", ".join(json.loads(srcs))
            lines.append(f"| {zh} | {en} | {alias_list} | {cat_list} | {src_list} |")

        sections = [
            ("麻醉药品", "药用类麻醉药品目录（2025年版）", _NARCOTIC),
            ("第一类精神药品", "药用类精神药品目录（2025年版）", _PSY_I),
            ("第二类精神药品", "药用类精神药品目录（2025年版）", _PSY_II),
            ("毒性中药", "医疗用毒性药品管理办法", _TOXIC_TCM),
            ("毒性西药", "医疗用毒性药品管理办法", _TOXIC_WM),
            ("高警示药品 A级", "高警示药品推荐目录（2025版）", _HAM_A),
            ("高警示药品 B级", "高警示药品推荐目录（2025版）", _HAM_B),
            ("高警示药品 C级", "高警示药品推荐目录（2025版）", _HAM_C),
        ]

        for title, source, items in sections:
            lines += ["", "---", "", f"## {title}", "", f"来源：{source}", ""]
            lines.append("| 序号 | 中文名 | 英文名 |")
            lines.append("|------|--------|--------|")
            for i, (zh, en) in enumerate(items, 1):
                lines.append(f"| {i} | {zh} | {en} |")

        lines.append("")
        MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    finally:
        conn.close()

def main() -> None:
    stats = build_db()
    build_md(stats)
    print(f"已生成：{DB_PATH}")
    print(f"已生成：{MD_PATH}")
    print(f"分类条目：{stats['total_entries']} 条，去重后：{stats['unique_drugs']} 种")
    for cat, n in stats["by_category"].items():
        print(f"  - {cat}: {n}")

if __name__ == "__main__":
    main()
