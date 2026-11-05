"""Small zh -> en glossary for campus topics.

The knowledge base is mostly English while students often ask in Chinese.
Keyword search cannot bridge that on its own, so we append English terms for
Chinese words found in the question. This is a stop-gap until embeddings are
added; the LLM-based query rewrite in rag.py covers what this list misses.
"""

GLOSSARY = {
    # dining
    "吃饭": "dining restaurant canteen food", "餐厅": "restaurant dining", "饭堂": "canteen restaurant dining",
    "食堂": "canteen restaurant dining", "吃": "dining restaurant food", "咖啡": "coffee cafe",
    "营业时间": "opening hours", "营业": "opening hours", "外卖": "takeaway", "超市": "supermarket retail outlet",
    "便利店": "convenience store retail outlet",
    # sports
    "操场": "sports field track football pitch outdoor sports facilities", "跑道": "running track",
    "体育馆": "sports hall sports centre arena", "体育": "sports facilities", "健身": "fitness gym",
    "游泳": "swimming pool", "泳池": "swimming pool", "羽毛球": "badminton", "篮球": "basketball",
    "网球": "tennis", "足球": "football soccer", "球场": "court pitch", "运动": "sports facilities",
    "开放时间": "opening hours", "关门": "closing time opening hours close", "几点关": "closing time opening hours close",
    "几点开": "opening time opening hours",
    # hall
    "宿舍": "hall residence accommodation", "申请": "application apply", "舍堂": "hall residential",
    "室友": "roommate", "住宿": "accommodation hall residence", "入住": "check-in move in",
    # printing / IT
    "打印": "printing print", "额度": "quota budget carbon count", "复印": "copy photocopy", "扫描": "scan",
    "打印机": "printer multi-function printer MFP", "收费": "charge fee price",
    "无线网": "wifi wi-fi", "网络": "wifi network internet", "校园网": "wifi eduroam campus network",
    "密码": "password", "邮箱": "email account", "账号": "account", "账户": "account",
    # general
    "地图": "campus map", "新生": "new student freshman undergraduate", "本科": "undergraduate",
    "研究生": "postgraduate", "巴士": "bus transport", "校巴": "campus bus shuttle", "图书馆": "library",
    "活动": "event activities", "迎新": "orientation", "学生证": "student card ID",
    "医疗": "medical health clinic", "诊所": "clinic medical health", "付款": "payment pay", "缴费": "payment fee",
}


def expand(text):
    """English terms for the Chinese words in `text` (empty string if none)."""
    out = []
    for zh, en in GLOSSARY.items():
        if zh in text:
            out.append(en)
    return " ".join(out)
