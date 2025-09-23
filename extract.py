from docx import Document
import re
import unicodedata
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

MUTATION_PATTERN = r"\b[A-Z]\d{1,3}[A-Z]{1,6}\b"
PR_POSITIONS = {10, 20, 36, 46, 63, 84, 89}

def clean_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"^[\s]*[\u2022\u25AA\u25E6\u2023\u2013\u2014\-*\u00B7]+\s*", "", text, flags=re.MULTILINE)
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r",+", ",", text)
    text = re.sub(r",\s*$", "", text)
    return text.strip()

def extract_full_text(doc):
    return "\n".join([clean_text(p.text) for p in doc.paragraphs])

def extract_hiv_subtype(text):
    match = re.search(r"Subtype\s*[:\-]\s*(\S+)", text, re.IGNORECASE)
    return {"Subtype": match.group(1) if match else "Inconnu"}

def extract_mutation_blocks(text):
    sections = re.split(r"Drug resistance interpretation:\s*(PR|RT|IN)", text, flags=re.IGNORECASE)
    mutation_table, seen_sections = [], set()

    for i in range(1, len(sections), 2):
        section = sections[i].upper().strip()
        block = sections[i + 1]
        if section in seen_sections:
            continue
        seen_sections.add(section)

        major, accessory, minor = [], [], []

        if section == "PR":
            major = re.findall(MUTATION_PATTERN, clean_block(block, r"PI Major(?: Resistance)? Mutations:"))
            accessory = re.findall(MUTATION_PATTERN, clean_block(block, r"PI Accessory(?: Resistance)? Mutations:"))
            other_raw = re.search(r"(?:PR\s+)?Other(?: Resistance)? Mutations:\s*(.*?)(?:\n[A-Z]|Comments|Mutation scoring|\Z)", text, re.DOTALL | re.IGNORECASE)
            if other_raw:
                text = clean_text(other_raw.group(1))
                if text.lower() != "none":
                    mutations = re.findall(MUTATION_PATTERN, text)
                    for mut in mutations:
                        pos_match = re.search(r"\d+", mut)
                        if pos_match:
                            pos = int(pos_match.group())
                            if pos in PR_POSITIONS:
                                accessory.append(mut)
                            else:
                                minor.append(mut)

        elif section == "RT":
            nrtis = re.findall(MUTATION_PATTERN, clean_block(block, r"NRTI(?: Resistance)? Mutations:"))
            nnrtis = re.findall(MUTATION_PATTERN, clean_block(block, r"NNRTI(?: Resistance)? Mutations:"))
            minor = re.findall(MUTATION_PATTERN, clean_block(block, r"Other Mutations:"))
            mutation_table.append({
                "Section": section,
                "Mutations_majeures": [{"NRTIs": sorted(set(nrtis))}, {"NNRTIS": sorted(set(nnrtis))}],
                "Mutations_accessoires": [],
                "Autres_mutations": sorted(set(minor))
            })
            continue

        elif section == "IN":
            major = re.findall(MUTATION_PATTERN, clean_block(block, r"IN(?:STI)? Major(?: Resistance)? Mutations:"))
            accessory = re.findall(MUTATION_PATTERN, clean_block(block, r"IN(?:STI)? Accessory(?: Resistance)? Mutations:"))
            minor = re.findall(MUTATION_PATTERN, clean_block(block, r"Other Mutations:"))

        mutation_table.append({
            "Section": section,
            "Mutations_majeures": sorted(set(major)),
            "Mutations_accessoires": sorted(set(accessory)),
            "Autres_mutations": sorted(set(minor))
        })

    return mutation_table

def clean_block(text, label):
    match = re.search(label + r"\s*(.*?)(\n[A-Z]|\Z)", text, re.DOTALL | re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""

def extract_comments(text):
    comments = {}
    for section in ["PR", "RT", "IN"]:
        match = re.search(f"{section} comments[:\s]*([\s\S]*?)(Mutation scoring|Drug resistance mutation scores|$)", text, re.IGNORECASE)
        if match:
            comments[section] = clean_text(match.group(1))
    return comments

def extract_scores(doc):
    elements = [
        ("paragraph", Paragraph(el, doc)) if isinstance(el, CT_P)
        else ("table", Table(el, doc))
        for el in doc.element.body
        if isinstance(el, (CT_P, CT_Tbl))
    ]

    scoring_tables = []
    i = 0

    while i < len(elements):
        type1, content1 = elements[i]
        if type1 == "paragraph":
            text = clean_text(content1.text)
            match = re.search(
                r"(Mutation scoring|Drug resistance mutation scores of)\s*:?\s*(PR|RT|IN|NRTI|NNRTI|INSTI)?",
                text,
                flags=re.IGNORECASE
            )
            if match:
                raw_section = match.group(2) or "RT"
                section = raw_section.upper()
                j = i + 1
                # Cherche un tableau immédiatement après
                while j < len(elements):
                    type2, content2 = elements[j]
                    if type2 == "table":
                        rows = content2.rows
                        if len(rows) < 2:
                            break

                        headers = [clean_text(cell.text) for cell in rows[0].cells]
                        scores, efficacite = {}, {}

                        # Priorité : ligne 'Total', sinon dernière ligne non vide
                        total_row = None
                        for row in rows[1:]:
                            row_vals = [clean_text(cell.text) for cell in row.cells]
                            if row_vals and row_vals[0].strip().lower() == "total":
                                total_row = row_vals
                                break

                        if not total_row:
                            for row in reversed(rows[1:]):
                                row_vals = [clean_text(cell.text) for cell in row.cells]
                                if any(row_vals[1:]):  # ignore si toutes les valeurs sauf la 1re sont vides
                                    total_row = row_vals
                                    break

                        if total_row:
                            for col, val in zip(headers[1:], total_row[1:]):
                                scores[col] = val
                                try:
                                    score = int(val)
                                    if score < 0:
                                        eff = "Hyper actif"
                                    elif score < 10:
                                        eff = "Totalement actif"
                                    elif score < 30:
                                        eff = "Bonne activité résiduelle"
                                    elif score < 60:
                                        eff = "Partiellement actif"
                                    else:
                                        eff = "Inactif"
                                except:
                                    eff = "Non interprétable"
                                efficacite[col] = eff

                            entry = {
                                "section": section if section in ["PR", "RT", "IN"] else "RT",
                                "scores": scores,
                                "efficacite": efficacite
                            }
                            if entry["section"] == "RT":
                                entry["sous_section"] = "NNRTI" if section == "NNRTI" else "NRTI"
                            scoring_tables.append(entry)
                        break  # fin de boucle j
                    j += 1
        i += 1

    return scoring_tables

def extract_info_from_text(path):
    doc = Document(path)
    full_text = extract_full_text(doc)
    return {
        "sous_type_viral": extract_hiv_subtype(full_text),
        "mutations": extract_mutation_blocks(full_text),
        "commentaires": extract_comments(full_text),
        "scores": extract_scores(doc)
    }
