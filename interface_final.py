# ================================================
# Streamlit : Génération de rapports TR (VIH/ARV)
# ================================================

import streamlit as st
import pandas as pd
import json, re, os, gc
from pathlib import Path
from datetime import date, datetime
try:
    from extract import extract_info_from_text  # Extraction des mutations et scores
    from extract2 import extract_note_and_interpretation
    from generation_tr import generate_model_response
    from generate_with_ollama import generate_model_ollama_response
except ImportError:
    st.warning("⚠️ Certains modules d'extraction ne sont pas disponibles")

# ---------------------------
# Config Streamlit
# ---------------------------
st.set_page_config(page_title="Génération de rapport de test de resistance", layout="wide")
st.title("🧠 Génération de rapport TR")

# ---------------------------
# Intervalle de date
# ---------------------------
MIN_DATE = date(1930, 1, 1)
MAX_DATE = date(2066, 12, 31)

# ---------------------------
# Initialisation des variables
# ---------------------------
note = ""
interpretation = ""
resultats = ""
sexe = "Autre"
date_naissance = date(2000, 1, 1)
charges_virales = []
t_cd4 = []
historique = []

# ---------------------------
# Informations patient
# ---------------------------
code_patient = st.text_input("🆔 Code patient (ex: P001)")
Nom_patient = st.text_input("📄 Nom du patient")

# ---------------------------
# Upload rapport clinique
# ---------------------------
st.subheader("📄 Rapport clinique (note & interprétation) (.docx)")
uploaded_note = st.file_uploader("Importer le rapport clinique (.docx)", type=["docx"], key="upload_note")

if uploaded_note:
    try:
        with open("temp_note.docx", "wb") as f:
            f.write(uploaded_note.getbuffer())
        
        # Vérifier si le module d'extraction est disponible
        try:
            from extract2 import extract_note_and_interpretation
            note_interp = extract_note_and_interpretation("temp_note.docx")
            
            note = note_interp.get("note", "")
            interpretation = note_interp.get("interpretation", "")
            resultats = note_interp.get("resultats", "")
            sexe_extrait = note_interp.get("sexe", None)
            date_naissance_extrait = note_interp.get("date_naissance", None)
            charges_virales = note_interp.get("charges_virales", [])
            t_cd4 = note_interp.get("taux_cd4", [])
            historique = note_interp.get("historique_therapeutique", [])
            
            if sexe_extrait:
                sexe = "Masculin" if sexe_extrait.lower() == "masculin" else ("Féminin" if sexe_extrait.lower() == "féminin" else "Autre")
            if date_naissance_extrait:
                try:
                    date_naissance = datetime.strptime(date_naissance_extrait, "%d/%m/%Y").date()
                except:
                    try:
                        date_naissance = date.fromisoformat(date_naissance_extrait)
                    except:
                        pass
            
            st.success("✅ Extraction note & interprétation réussie")
            
        except ImportError:
            st.error("❌ Module extract2 non disponible pour l'extraction")
            
    except Exception as e:
        st.error(f"❌ Erreur lors du traitement du fichier: {e}")
    finally:
        # Nettoyage du fichier temporaire
        if os.path.exists("temp_note.docx"):
            os.remove("temp_note.docx")

# ---------------------
# Fonction pour afficher charges virales
# ---------------------
def afficher_charges_virales(charges_virales):
    charges_mod = []
    nb_initial = len(charges_virales)
    n_cv = st.number_input("Nombre de charges virales", min_value=0, max_value=30, step=1, value=nb_initial, key="n_cv")
    
    for i in range(n_cv):
        col1, col2 = st.columns(2)
        with col1:
            valeur = charges_virales[i]["valeur"] if i < nb_initial and charges_virales else ""
            valeur = st.text_input(f"Charge virale {i+1}", value=valeur, key=f"charge_{i}")
        with col2:
            if i < nb_initial and charges_virales:
                raw_date = charges_virales[i]["date"]
                try:
                    # Essayer différents formats de date
                    try:
                        parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
                    except:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except:
                    parsed_date = date.today()
            else:
                parsed_date = date.today()
                
            date_val = st.date_input(
                f"Date {i+1}",
                value=parsed_date,
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"date_cv_{i}"
            )
        charges_mod.append({"valeur": valeur, "date": str(date_val)})
    return charges_mod

# ---------------------
# Fonction pour afficher le taux de cd4
# ---------------------
def afficher_taux_cd4(t_cd4):
    charges_mod = []
    nb_initial = len(t_cd4)
    n_tcd4 = st.number_input("Nombre de mesure du taux de CD4", min_value=0, max_value=20, step=1, value=nb_initial, key="n_tcd4")
    
    for i in range(n_tcd4):
        col1, col2 = st.columns(2)
        with col1:
            valeur = t_cd4[i]["valeur"] if i < nb_initial and t_cd4 else ""
            valeur = st.text_input(f"Taux de CD4 {i+1}", value=valeur, key=f"taux_{i}")
        with col2:
            if i < nb_initial and t_cd4:
                raw_date = t_cd4[i]["date"]
                try:
                    try:
                        parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
                    except:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except:
                    parsed_date = date.today()
            else:
                parsed_date = date.today()
                
            date_val = st.date_input(
                f"Date {i+1}",
                value=parsed_date,
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"date_tcd4_{i}"
            )
        charges_mod.append({"valeur": valeur, "date": str(date_val)})
    return charges_mod

# ---------------------
# Historique thérapeutique
# ---------------------
arv_options = ["TDF+3TC+NVP", "TDF+3TC+EFV", "AZT+3TC+NVP", "ABC+3TC+LPV/r", "ABC+3TC+ATV/r", 
               "TDF+3TC+DTG", "TDF+3TC+ATV/r", "AZT+3TC+ATV/r", "ABC+3TC+NVP", "Autres"]
raison_options = ["Échec virologique", "Stock out", "Toxicité", "Grossesse", "Switch recommandé", "Intéruption du traitement"]

def afficher_et_modifier_historique(historique, arv_options, raison_options):
    st.subheader("💊 Historique thérapeutique")
    
    nb_initial = len(historique)
    n_tarv = st.number_input("Nombre de traitements", min_value=0, max_value=20, step=1, value=nb_initial, key="n_tarv")
    
    historique_modifie = []
    
    for i in range(n_tarv):
        st.markdown(f"**⏳ Traitement {i+1}**")
        col1, col2 = st.columns(2)
        
        # Valeurs par défaut
        arv_final = ""
        raison = raison_options[0]
        debut_str = "inconnue"
        fin_str = "inconnue"
        
        # Récupérer les valeurs existantes si disponibles
        if i < nb_initial and historique:
            traitement_existant = historique[i]
            arv_existant = traitement_existant.get("arv", "")
            raison_existant = traitement_existant.get("raison_changement", raison_options[0])
            debut_existant = traitement_existant.get("debut", "inconnue")
            fin_existant = traitement_existant.get("fin", "inconnue")
        else:
            arv_existant = ""
            raison_existant = raison_options[0]
            debut_existant = "inconnue"
            fin_existant = "inconnue"

        with col1:
            # Sélection ARV
            selection_index = arv_options.index(arv_existant) if arv_existant in arv_options else len(arv_options) - 1
            selection = st.selectbox(f"ARV {i+1}", arv_options, index=selection_index, key=f"arv_{i}")
            
            if selection == "Autres":
                arv_final = st.text_input("Veuillez entrer l'ARV", value=arv_existant if arv_existant not in arv_options else "", key=f"autre_arv_{i}")
            else:
                arv_final = selection
            
            # Raison du changement
            raison_index = raison_options.index(raison_existant) if raison_existant in raison_options else 0
            raison = st.selectbox("Raison", raison_options, index=raison_index, key=f"raison_{i}")

        with col2:
            # Gestion date début
            debut_inconnu = st.checkbox("Début inconnu", value=debut_existant == "inconnue", key=f"debut_inconnu_{i}")
            if not debut_inconnu:
                date_debut_default = date.today()
                if debut_existant != "inconnue":
                    try:
                        date_debut_default = datetime.strptime(debut_existant, "%d/%m/%Y").date()
                    except:
                        try:
                            date_debut_default = datetime.strptime(debut_existant, "%Y-%m-%d").date()
                        except:
                            pass
                
                date_debut = st.date_input("Début", value=date_debut_default, key=f"debut_{i}")
                debut_str = date_debut.strftime("%d/%m/%Y")
            else:
                debut_str = "inconnue"

            # Gestion date fin
            fin_inconnu = st.checkbox("Fin inconnue", value=fin_existant == "inconnue", key=f"fin_inconnu_{i}")
            if not fin_inconnu:
                date_fin_default = date.today()
                if fin_existant != "inconnue":
                    try:
                        date_fin_default = datetime.strptime(fin_existant, "%d/%m/%Y").date()
                    except:
                        try:
                            date_fin_default = datetime.strptime(fin_existant, "%Y-%m-%d").date()
                        except:
                            pass
                
                date_fin = st.date_input("Fin", value=date_fin_default, key=f"fin_{i}")
                fin_str = date_fin.strftime("%d/%m/%Y")
            else:
                fin_str = "inconnue"

        if arv_final:
            historique_modifie.append({
                "arv": arv_final,
                "debut": debut_str,
                "fin": fin_str,
                "raison_changement": raison
            })
    
    return historique_modifie

# ---------------------
# Section édition données extraites
# ---------------------
st.subheader("✏️ Modifier les données extraites")
col_sexe, col_naissance = st.columns(2)

with col_sexe:
    sexe = st.radio("Sexe", ["Masculin", "Féminin", "Autre"], 
                   index=["Masculin", "Féminin", "Autre"].index(sexe), 
                   horizontal=True)

with col_naissance:
    date_naissance = st.date_input("Date de naissance", value=date_naissance, 
                                  min_value=MIN_DATE, max_value=MAX_DATE)

# Affichage de l'historique thérapeutique
historique = afficher_et_modifier_historique(historique, arv_options, raison_options)

# ---------------------
# Observance
# ---------------------
st.subheader("📅 Observance")
col_obs1, col_obs2 = st.columns([2, 1])
with col_obs1:
    jours_manques_input = st.number_input("Jours manqués", min_value=0, step=1, value=0)
with col_obs2:
    inconnu = st.checkbox("Inconnu")
jours_manques = "inconnu" if inconnu else jours_manques_input

# ---------------------
# Co-infections
# ---------------------
st.subheader("🦠 Co-infections")
co_infections = []
n_coinf = st.number_input("Nombre de co-infections", min_value=0, max_value=10, step=1, value=0)

for i in range(n_coinf):
    col1, col2 = st.columns(2)
    with col1:
        maladie = st.text_input(f"Nom maladie {i+1}", key=f"maladie_{i}")
    with col2:
        duree = st.text_input(f"Durée (ex: 3 mois)", key=f"duree_{i}")
    if maladie:
        co_infections.append({"nom": maladie, "duree": duree})

# Affichage charges virales
st.markdown("### 📊 Charges virales")
charges_virales = afficher_charges_virales(charges_virales)

# Affichage t_cd4
st.markdown("### 📊 Taux de CD4")
t_cd4 = afficher_taux_cd4(t_cd4)

# ---------------------------
# Upload rapport mutations
# ---------------------------
st.subheader("📄 Rapport de Stanford sur les mutations (.docx)")
uploaded_doc = st.file_uploader("Importer le rapport Word (.docx)", type=["docx"], key="upload_mutations")
extracted_data = {}

if uploaded_doc:
    try:
        temp_path = "temp_mutations.docx"
        with open(temp_path, "wb") as f:
            f.write(uploaded_doc.getbuffer())
        
        # Vérifier si le module d'extraction est disponible
        try:
            from extract import extract_info_from_text
            extracted_data = extract_info_from_text(temp_path)
            st.success("✅ Données extraites automatiquement")
            
            # Afficher un aperçu des données extraites
            with st.expander("Voir les données extraites"):
                st.json(extracted_data)
                
        except ImportError:
            st.error("❌ Module extract non disponible pour l'extraction des mutations")
            
    except Exception as e:
        st.error(f"❌ Erreur lors du traitement du fichier: {e}")
    finally:
        # Nettoyage du fichier temporaire
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------
# Préparation prompt utilisateur
# ---------------------------
mutations_prompt = []
if extracted_data:
    for mut_block in extracted_data.get("mutations", []):
        section = mut_block.get("Section", "Unknown")
        mut_text = f"Section {section}:\n"
        for key, val in mut_block.items():
            if key == "Section": 
                continue
            mut_text += f"    {key}: {val}\n"
        mutations_prompt.append(mut_text)
mutations_prompt_str = "\n".join(mutations_prompt) if mutations_prompt else "Aucune mutation détectée"

scores_prompt = []
if extracted_data:
    for bloc in extracted_data.get("scores", []):
        section = bloc.get("section", "Unknown")
        sous_section = bloc.get("sous_section", None)
        scores = bloc.get("scores", {})
        efficacite = bloc.get("efficacite", {})
        title = f"{section}" + (f" - {sous_section}" if sous_section else "")
        scores_text = f"{title}:\n"
        for arv, score_val in scores.items():
            eff = efficacite.get(arv, "Non interprétable")
            scores_text += f"    {arv}: score={score_val}, efficacité={eff}\n"
        scores_prompt.append(scores_text)
scores_prompt_str = "\n".join(scores_prompt) if scores_prompt else "Aucun score ARV détectée"

# Préparation des données pour le prompt
user_prompt = f"""
### Contexte du patient:
Code patient: {code_patient}
Nom patient: {Nom_patient}
Sexe: {sexe}
Date de naissance: {date_naissance.strftime('%d/%m/%Y')}
Historique thérapeutique: {json.dumps(historique, ensure_ascii=False)}
Charges virales: {json.dumps(charges_virales, ensure_ascii=False)}
Taux de CD4: {json.dumps(t_cd4, ensure_ascii=False)}
Observance: {jours_manques} jours manqués
Co-infections: {json.dumps(co_infections, ensure_ascii=False)}

### Mutations du VIH détectées:
{mutations_prompt_str}

### Scores d'efficacité des ARV face aux mutations:
{scores_prompt_str}
### Instruction complémentaire:

"""

st.subheader("📝 Prompt généré pour le LLM")
with st.expander("Voir le prompt complet"):
    st.text_area("User prompt", user_prompt, height=300)

# ---------------------------
# Génération du rapport
# ---------------------------
interpretation_clinique = ""
premiere_interpretation = ""
if st.button("📝 Générer l'interprétation", type="primary"):
    with st.spinner("Génération de l'interprétation en cours..."):
        try:
            # Vérifier la disponibilité des modules de génération
            try:
                from generation_tr import generate_model_response
                from generate_with_ollama import generate_model_ollama_response
                
                premiere_interpretation = generate_model_response(user_prompt)
                if premiere_interpretation:
                    interpretation_clinique = generate_model_ollama_response(
                        premiere_interpretation, user_prompt
                    )
                else:
                    interpretation_clinique = "Erreur : la génération locale a échoué."
                    
            except ImportError:
                interpretation_clinique = "⚠️ Modules de génération non disponibles. Mode démonstration activé."
                interpretation_clinique = f"""
                RAPPORT MÉDICAL - MODE DÉMONSTRATION
                Patient: {Nom_patient} ({code_patient})
                Sexe: {sexe}
                Date de naissance: {date_naissance.strftime('%d/%m/%Y')}
                
                Données analysées:
                - Mutations: {len(mutations_prompt)} sections détectées
                - Scores ARV: {len(scores_prompt)} sections analysées
                - Historique traitement: {len(historique)} lignes
                - Charges virales: {len(charges_virales)} mesures
                - Taux CD4: {len(t_cd4)} mesures
                
                Ceci est une démonstration. Activez les modules de génération pour obtenir un rapport complet.
                """
                
        except Exception as e:
            interpretation_clinique = f"❌ Erreur lors de la génération : {str(e)}"

    if interpretation_clinique:
        st.subheader("📝 1 ere version de l'Interprétation générée")
        st.text_area("1 ere Interprétation clinique", premiere_interpretation, height=400)
        st.subheader("📝 Interprétation générée")
        st.text_area("Interprétation clinique", interpretation_clinique, height=400)

# ---------------------------
# Enregistrement du rapport
# ---------------------------
if interpretation_clinique:
    # Préparer le contenu
    contenu = f"RAPPORT - {code_patient}\n{interpretation_clinique}"
    
    st.download_button(
        label="📥 Télécharger le rapport",
        data=contenu,
        file_name=f"rapport_{code_patient}.txt",
        mime="text/plain"
    )
else:
    st.warning("Générez d'abord une interprétation")

# ---------------------------
# Nettoyage
# ---------------------------
gc.collect()