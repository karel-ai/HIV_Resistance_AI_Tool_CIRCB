import json
from pathlib import Path
from datetime import date
from extract import extract_info_from_text
from extract2 import extract_note_and_interpretation

# 📁 Racine où se trouvent tous les dossiers patients (à adapter)
DOSSIER_RACINE = Path(r".\Dossier_patient")
DOSSIER_OUTPUT = Path(r".\data_json")
DOSSIER_OUTPUT.mkdir(parents=True, exist_ok=True)

# 🔍 Recherche récursive de tous les fichiers .docx
fichiers = list(DOSSIER_RACINE.rglob("*.docx"))

# Regroupe les fichiers par patient à partir de leur nom (ex: P001_note.docx et P001_mut.docx)
patients = {}
for f in fichiers:
    name = f.stem.lower()
    if "TR" in name:
        code = name.replace("_note", "").upper()
        patients.setdefault(code, {})["note"] = f
    elif "Stanford" in name or "mutation" in name:
        code = name.replace("_mut", "").replace("_mutation", "").upper()
        patients.setdefault(code, {})["mut"] = f

# 🔁 Traitement de chaque patient ayant une paire complète
for code, fichiers in patients.items():
    note_path = fichiers.get("note")
    mut_path = fichiers.get("mut")
    if not (note_path and mut_path):
        print(f"⛔ Fichiers incomplets pour {code}")
        continue

    try:
        data_note = extract_note_and_interpretation(str(note_path))
        data_mut = extract_info_from_text(str(mut_path))

        json_data = {
            "code_patient": code,
            "sexe": data_note.get("sexe", "Autre"),
            "date_naissance": data_note.get("date_naissance", "2000-01-01"),
            "charges_virales": data_note.get("charges_virales", []),
            "taux_cd4": data_note.get("taux_cd4", []),
            "historique_therapeutique": data_note.get("historique_therapeutique", []),
            "co_infections": [],
            "observance": "inconnu",
            "extraction_texte": data_mut,
            "results": {
                "note": data_note.get("note", ""),
                "interpretation": data_note.get("interpretation", ""),
                "resultats": data_note.get("resultats", "")
            }
        }

        # Création de input/output
        input_parts = [
            f"Code du patient: {code}",
            f"Sexe: {json_data['sexe']}",
            f"Date naissance: {json_data['date_naissance']}",
            "Observance: inconnu"
        ]

        for t in json_data["historique_therapeutique"]:
            input_parts.append(f"Traitement: {t['arv']} | Début: {t['debut']} | Fin: {t['fin']} | Raison: {t.get('raison_changement', '')}")
        for cv in json_data["charges_virales"]:
            input_parts.append(f"CV: {cv['valeur']} copies/ml le {cv['date']}")
        for cd4 in json_data["taux_cd4"]:
            input_parts.append(f"Taux_CD4: {cd4['valeur']} cellules/ml le {cd4['date']}")
        for bloc in data_mut.get("mutations", []):
            section = bloc.get("Section", "inconnue")
            mutation_texts = []
            if section == "RT" and isinstance(bloc.get("Mutations_majeures", [])[0], dict):
                nrtis = bloc["Mutations_majeures"][0].get("NRTIs", [])
                nnrtis = bloc["Mutations_majeures"][1].get("NNRTIS", [])
                if nrtis: mutation_texts.append(f"NRTIs: {', '.join(nrtis)}")
                if nnrtis: mutation_texts.append(f"NNRTIs: {', '.join(nnrtis)}")
            else:
                for k in ["Mutations_majeures", "Mutations_accessoires", "Autres_mutations"]:
                    if bloc.get(k): mutation_texts.append(f"{k.replace('_', ' ').capitalize()}: {', '.join(bloc[k])}")
            if mutation_texts:
                input_parts.append(f"Mutation {section}: {' | '.join(mutation_texts)}")

        for bloc in data_mut.get("scores", []):
            section = bloc.get("section", "inconnue")
            sous_section = bloc.get("sous_section", None)
            scores = bloc.get("scores", {})
            efficience = bloc.get("efficience", {})
            section_label = f"{section} - {sous_section}" if sous_section else section
            if scores:
                input_parts.append(f"Scores {section_label}:")
                for arv, val in scores.items():
                    input_parts.append(f"  - {arv}: score={val}, efficience={efficience.get(arv, '')}")

        json_data["input"] = "\n".join(input_parts)
        json_data["output"] = {
            "Résultats": json_data["results"]["resultats"],
            "Note": json_data["results"]["note"],
            "Interprétation_clinique": json_data["results"]["interpretation"]
        }

        output_path = DOSSIER_OUTPUT / f"{code}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Patient {code} traité et enregistré")

    except Exception as e:
        print(f"❌ Erreur avec {code} : {e}")
