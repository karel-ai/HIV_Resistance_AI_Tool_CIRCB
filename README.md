# 🧠 CIRCB – IA pour Rapports Cliniques VIH

Scripts et outils développés lors de mon stage au **CIRCB (Centre International de Référence Chantal Biya)**.
Ce projet automatise **l’extraction de données patients** depuis des rapports Word et utilise des **LLMs (Phi-4 Mini, Phi-4 quantifié)** pour générer des interprétations cliniques de pharmacorésistance du VIH.

---

## 📋 **Fonctionnalités**

* 📑 Extraction automatisée des informations patients et mutations (OCR et parsing `.docx`).
* 🎛️ **Fine-tuning** de Phi-4 Mini avec LoRA/qLoRA pour réduire l’usage mémoire.
* 🖥️ **Interface Streamlit** pour saisir, générer et corriger des rapports cliniques.
* 📊 Pipeline ETL et scripts pour transformer les données en JSONL pour l’entraînement.

---

## 🗂 **Arborescence**

```
📁 CIRCB_HIV_AI_2025/
├── fine_tuning_phi4.ipynb      # Fine-tuning du modèle Phi-4 Mini
├── generate_interpretation.py # Génération locale des interprétations
├── generate_with_ollama.py    # Amélioration via Ollama
├── interface_final.py           # Interface utilisateur Streamlit
├── data.py                      # Pipeline ETL pour préparer les données
├── extract.py / extractrslt.py  # Extraction de mutations et interprétations
└── README.md                    # Ce fichier
```

---

## ⚙️ **Installation**

1. **Cloner le dépôt**

   ```bash
   git clone https://github.com/<votre-utilisateur>/<nom-du-dépôt>.git
   cd <nom-du-dépôt>
   ```

2. **Créer un environnement virtuel et installer les dépendances**

   ```bash
    python3.10 --version  # Doit afficher 3.10.18
    python3.10 -m venv venv
    source venv/bin/activate  # ou .\venv\Scripts\activate sous Windows
    pip install -r requirements.txt

   ```

3. **Préparer vos modèles et données**

   * Téléchargez Phi-4 Mini et placez-le dans `./Phi-4-mini`.
   * Assurez-vous d’avoir vos rapports Word patients et mutations.

---

## ▶️ **Utilisation**

### Fine-tuning du modèle

```bash
jupyter notebook fine_tuning_phi4.ipynb
```

### Génération d’interprétation

```bash
python generation_interpretation.py
```

### Interface Streamlit

```bash
streamlit run interface_final.py
```

---

## 🧰 **Technologies principales**

* [Transformers](https://huggingface.co/transformers/) (Fine-tuning Phi-4)
* [BitsAndBytes](https://github.com/TimDettmers/bitsandbytes) (Quantification mémoire)
* [LangChain](https://www.langchain.com/) + Ollama (chaînes et amélioration)
* [Streamlit](https://streamlit.io/) (Interface utilisateur)
* Python ≥3.10

---

## 📌 **Notes**

* Destiné à un usage **local** pour préserver la confidentialité des données.
* Les données patients doivent rester anonymisées avant utilisation.
* Pour des performances optimales : GPU ≥16 Go VRAM recommandé (ex. RTX 4090).

---

## ✨ **Auteurs**

* **Karel Elong** – Chef de projet junior IA (Stage CIRCB 2025).
