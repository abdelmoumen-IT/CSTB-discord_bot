import requests
import json


def get_morning_evening_adkar():
    response = requests.get(
        "https://www.hisnmuslim.com/api/ar/27.json",
        timeout=10
    )

    response.raise_for_status()

    data = json.loads(
        response.content.decode("utf-8-sig")
    )

    return data["أذكار الصباح والمساء"]


def get_sleeping_adkar():
    response = requests.get(
        "https://www.hisnmuslim.com/api/ar/28.json",
        timeout=10
    )

    response.raise_for_status()

    data = json.loads(
        response.content.decode("utf-8-sig")
    )
    adkar = data["أذكار النوم"]
    adkar[5]["REPEAT"] = 3
    adkar.append({
        "ARABIC_TEXT":"من قال حين يأوي إلى فراشه لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير، لا حول ولا قوة إلا بالله العلي العظيم، سبحان الله والحمد لله ولا إله إلا الله والله أكبر غفرت ذنوبه ولو كانت مثل زبد البحر",
        "REPEAT": 1,
    })
    return adkar

def build_pages(adkar, limit=3500):
    pages, current = [], ""
    for item in adkar:
        text = item.get("ARABIC_TEXT", "")
        repeat = item.get("REPEAT", 1)
        block = f"{text}\n🔁 التكرار: {repeat}\n\n"
        if current and len(current) + len(block) > limit:
            pages.append(current)
            current = ""
        current += block
    if current:
        pages.append(current)
    return pages
