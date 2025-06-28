import openai
import os
import base64
import json
import pandas as pd
from dotenv import load_dotenv
import subprocess
import platform

# Testovací CSV na úvod
# with open("test.csv", "w", encoding="utf-8") as f:
#     f.write("test csv\n")

# Funkce pro otevření CSV souboru
def open_csv(filename):
    if platform.system() == "Windows":
        subprocess.Popen(["start", filename], shell=True)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", filename])
    else:
        subprocess.Popen(["xdg-open", filename])


# Načtení API klíče
load_dotenv()
api_key = os.getenv("API_KEY")
client = openai.OpenAI(api_key=api_key)

def encode_image_to_base64(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def extract_matches_from_image(base64_image, bookmaker_name, output_csv):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": f"Jsi pomocník pro sportovní sázení. Uživatel ti posílá screenshot sázkové kanceláře {bookmaker_name} a chce získat seznam nejsázenějších zápasů a jejich kurzy."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Najdi v tomto obrázku nejsázenější zápasy a pro každý vypiš: název zápasu a kurzy 1, 0, 2. Výsledek strukturovaně jako JSON seznam objektů se jmény: 'match', '1', '0', '2'."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        temperature=0.3
    )

    try:
        data_json = response.choices[0].message.content.strip()
        json_start = data_json.find('[')
        json_end = data_json.rfind(']')
        json_text = data_json[json_start:json_end+1]
        matches = json.loads(json_text)
        df = pd.DataFrame(matches)
        df.to_csv(output_csv, index=False, encoding="utf-8-sig")
        return matches
    except Exception as e:
        print(f"Chyba při zpracování odpovědi z {bookmaker_name}: {e}")
        return []

def ask_chatgpt_if_matches_match(fortuna_name, tipsport_name):
    prompt = (
        f"Porovnej, zda tyto dva názvy označují ten samý fotbalový zápas. "
        f"Názvy mohou být napsány jinak (např. různé jazyky nebo pořadí týmů). "
        f"Odpověz pouze 'Ano' nebo 'Ne'.\n"
        f"Zápas 1: {fortuna_name}\n"
        f"Zápas 2: {tipsport_name}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    answer = response.choices[0].message.content.strip().lower()
    return "ano" in answer

# Kód načte a zpracuje obrázky
fortuna_img = encode_image_to_base64("fortuna_homepage.png")
tipsport_img = encode_image_to_base64("tipsport_homepage.png")

fortuna_matches = extract_matches_from_image(fortuna_img, "Fortuna", "fortuna_zapasy.csv")
tipsport_matches = extract_matches_from_image(tipsport_img, "Tipsport", "tipsport_zapasy.csv")

# Otevři CSV se seznamy zápasů
if fortuna_matches:
    open_csv("fortuna_zapasy.csv")
if tipsport_matches:
    open_csv("tipsport_zapasy.csv")

# Porovnání zápasů
comparison = []
for fortuna_match in fortuna_matches:
    for tipsport_match in tipsport_matches:
        if ask_chatgpt_if_matches_match(fortuna_match['match'], tipsport_match['match']):
            comparison.append({
                "Zápas (Fortuna)": fortuna_match['match'],
                "F: 1": fortuna_match['1'],
                "F: 0": fortuna_match['0'],
                "F: 2": fortuna_match['2'],
                "T: 1": tipsport_match['1'],
                "T: 0": tipsport_match['0'],
                "T: 2": tipsport_match['2']
            })
            break

# Uložení a otevření porovnání
df = pd.DataFrame(comparison)
output_file = "kurzy_fortuna_vs_tipsport.csv"
df.to_csv(output_file, index=False, encoding="utf-8-sig")

if not df.empty:
    open_csv(output_file)
else:
    print("❗️ Nebyly nalezeny žádné shodné zápasy.")


# Načti CSV soubor s výsledky porovnání
output_file = "kurzy_fortuna_vs_tipsport.csv"
df = pd.read_csv(output_file, encoding="utf-8-sig")

# Převeď DataFrame na CSV text pro předání GPT
csv_text = df.to_csv(index=False)

# Prompt pro GPT
prompt = (
    "Níže je tabulka srovnávající kurzy pro fotbalové zápasy od dvou sázkových kanceláří: Fortuna a Tipsport. "
    "Sloupce F: 1, F: 0, F: 2 jsou kurzy z Fortuny, T: 1, T: 0, T: 2 jsou kurzy z Tipsportu. "
    "Analyzuj prosím, u kterých zápasů jsou největší rozdíly v kurzech mezi těmito dvěma sázkovkami. "
    "Zaměř se na absolutní rozdíly a vypiš 3–5 zápasů s největším rozdílem. Výsledek uveď přehledně jako seznam nebo tabulku."
)

# Zavolání GPT s daty a požadavkem
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Jsi sportovní analytik specializující se na porovnávání kurzů."},
        {"role": "user", "content": prompt + "\n\n" + csv_text}
    ],
    temperature=0.3
)

# Výpis odpovědi
print("\n=== Výstup od GPT ===\n")
print(response.choices[0].message.content)
