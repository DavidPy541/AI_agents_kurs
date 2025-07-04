from openai import OpenAI
import os
import base64
import json
import pandas as pd
from dotenv import load_dotenv
import subprocess
import platform
from typing import List, Dict, Any


class ReActAgent:
    """A ReAct (Reason and Act) agent that handles multiple tool calls."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.max_iterations = 10  # Prevent infinite loops
        load_dotenv()
        self.api_key = os.getenv("API_KEY")
        self.client = OpenAI(api_key=self.api_key)

    def run(self, messages: List[Dict[str, Any]]) -> str:
        """
        Run the ReAct loop to perform actions based on reasoning.
        This method will process images, compare matches, and generate results.
        """
        iteration = 0
        response = ""

        while iteration < self.max_iterations:
            iteration += 1
            response = self.process(messages)
            if response:  # Break if the process is successful
                break
        return response

    def process(self, messages: List[Dict[str, Any]]) -> str:
        """
        Core method to interact with OpenAI API and perform reasoning and actions.
        """
        # Reasoning phase: Process the request through the GPT model
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()

    def open_csv(self, filename: str):
        """Open the CSV file using system's default method."""
        if platform.system() == "Windows":
            subprocess.Popen(["start", filename], shell=True)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", filename])
        else:
            subprocess.Popen(["xdg-open", filename])

    def encode_image_to_base64(self, path: str) -> str:
        """Encodes image file to base64 string."""
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def extract_matches_from_image(self, base64_image: str, bookmaker_name: str, output_csv: str) -> List[
        Dict[str, Any]]:
        """
        Extracts the matches and odds from the base64 image using GPT-4.
        This method expects an image in base64 format and will save the results in a CSV file.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system",
                 "content": f"Jsi pomocník pro sportovní sázení. Uživatel ti posílá screenshot sázkové kanceláře {bookmaker_name} a chce získat seznam nejsázenějších zápasů a jejich kurzy."},
                {"role": "user",
                 "content": f"Najdi v tomto obrázku nejsázenější zápasy a pro každý vypiš: název zápasu a kurzy 1, 0, 2. Výsledek strukturovaně jako JSON seznam objektů se jmény: 'match', '1', '0', '2'."},
                {"role": "user",
                 "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}]}
            ],
            temperature=0.3
        )

        # Logování odpovědi pro diagnostiku
        print("Odpověď od GPT:", response.choices[0].message.content.strip())

        try:
            data_json = response.choices[0].message.content.strip()

            # Pokud je odpověď prázdná nebo nevalidní JSON
            if not data_json:
                print(f"Chyba: Odpověď od GPT je prázdná pro {bookmaker_name}")
                return []

            json_start = data_json.find('[')
            json_end = data_json.rfind(']')

            if json_start == -1 or json_end == -1:
                print(f"Chyba: Neplatný formát JSON pro {bookmaker_name}")
                return []

            json_text = data_json[json_start:json_end + 1]
            matches = json.loads(json_text)
            df = pd.DataFrame(matches)
            df.to_csv(output_csv, index=False, encoding="utf-8-sig")
            return matches
        except Exception as e:
            print(f"Chyba při zpracování odpovědi z {bookmaker_name}: {e}")
            return []

    def ask_chatgpt_if_matches_match(self, fortuna_name: str, tipsport_name: str) -> bool:
        """
        Asks GPT to compare if the two match names represent the same match.
        """
        prompt = (
            f"Porovnej, zda tyto dva názvy označují ten samý fotbalový zápas. "
            f"Názvy mohou být napsány jinak (např. různé jazyky nebo pořadí týmů). "
            f"Odpověz pouze 'Ano' nebo 'Ne'.\n"
            f"Zápas 1: {fortuna_name}\n"
            f"Zápas 2: {tipsport_name}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        answer = response.choices[0].message.content.strip().lower()
        return "ano" in answer

    def compare_matches(self, fortuna_matches: List[Dict[str, Any]], tipsport_matches: List[Dict[str, Any]]) -> List[
        Dict[str, Any]]:
        """
        Compares the matches from Fortuna and Tipsport, returns a list of matching matches.
        """
        comparison = []
        for fortuna_match in fortuna_matches:
            for tipsport_match in tipsport_matches:
                if self.ask_chatgpt_if_matches_match(fortuna_match['match'], tipsport_match['match']):
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
        return comparison

    def analyze_best_odds_difference(self, df: pd.DataFrame) -> str:
        """
        Analyzes the differences in odds and returns GPT's recommendation for the most interesting matches.
        """
        # Převeď DataFrame na CSV text pro předání GPT
        csv_text = df.to_csv(index=False)

        # Prompt pro GPT pro analýzu rozdílů v kurzech
        prompt = (
            "Níže je tabulka srovnávající kurzy pro fotbalové zápasy od dvou sázkových kanceláří: Fortuna a Tipsport. "
            "Sloupce F: 1, F: 0, F: 2 jsou kurzy z Fortuny, T: 1, T: 0, T: 2 jsou kurzy z Tipsportu. "
            "Analyzuj prosím, u kterých zápasů jsou největší rozdíly v kurzech mezi těmito dvěma sázkovkami. "
            "Zaměř se na absolutní rozdíly a vypiš 3–5 zápasů s největším rozdílem. Výsledek uveď přehledně jako seznam nebo tabulku."
        )

        # Zavolání GPT s daty a požadavkem
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Jsi sportovní analytik specializující se na porovnávání kurzů."},
                {"role": "user", "content": prompt + "\n\n" + csv_text}
            ],
            temperature=0.3
        )

        # Výstup odpovědi od GPT
        return response.choices[0].message.content.strip()


# Vytvoření instance agenta
agent = ReActAgent()

# Načítání obrázků a extrakce zápasů
fortuna_img = agent.encode_image_to_base64("fortuna_homepage.png")
tipsport_img = agent.encode_image_to_base64("tipsport_homepage.png")

fortuna_matches = agent.extract_matches_from_image(fortuna_img, "Fortuna", "fortuna_zapasy.csv")
tipsport_matches = agent.extract_matches_from_image(tipsport_img, "Tipsport", "tipsport_zapasy.csv")

# Otevření CSV souborů pro zobrazení
if fortuna_matches:
    agent.open_csv("fortuna_zapasy.csv")
if tipsport_matches:
    agent.open_csv("tipsport_zapasy.csv")

# Porovnání zápasů
comparison = agent.compare_matches(fortuna_matches, tipsport_matches)

# Uložení porovnání
df = pd.DataFrame(comparison)
output_file = "kurzy_fortuna_vs_tipsport.csv"
df.to_csv(output_file, index=False, encoding="utf-8-sig")

if not df.empty:
    agent.open_csv(output_file)
else:
    print("❗️ Nebyly nalezeny žádné shodné zápasy.")

# Získání doporučení od GPT na základě rozdílů v kurzech
recommendation = agent.analyze_best_odds_difference(df)

# Výpis doporučených zápasů
print("\n=== Doporučení od GPT ===\n")
print(recommendation)
