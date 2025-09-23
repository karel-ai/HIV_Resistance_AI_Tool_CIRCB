from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFacePipeline
from langchain_ollama import OllamaLLM
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline, BitsAndBytesConfig
import os, gc, psutil, shutil
import torch

# === 0) Configuration ===
MEMORY_FILE = r"D:\docaivancity\PGE2\stage\IA_CIRCB\agent_circb\interpreteur\memoire.txt"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write("")

device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float16 if device == "cuda" else torch.float32
print(f"[INFO] device={device} | dtype={dtype}")

# === 1) Prompts et calque ===
system_prompt = """
Tu es un expert en virologie et infectiologie spécialisé dans la prise en charge du VIH/SIDA.
À partir des mutations génétiques, des scores d'efficacité des antiretroviraux (ARV), et du contexte clinique du patient, génère une interprétation clinique détaillée de 150 mots maximum du génotype, sous forme de rapport médical structuré.
Ton analyse doit comprendre :
1. Un **cadre immunovirologique** expliquant les échecs thérapeutiques passés et les mutations majeures en jeu.
2. Une **analyse des résistance** et des médicaments encore efficaces en evocant uniquement les.
3. Une **proposition de traitement optimisé** selon les ARV disponibles et une proposition d'association de molecules de la forme molecule1+molecule2+molecule3.
4. Un **commentaire sur l'observance** et le **suivi virologique à prévoir**.
Utilise un vocabulaire médical précis, sans faute, et emploie un ton professionnel.
Rédige ta reponse en seul paragraphe.
"""

calque = """
Cadre génotypique compatible à un début d’échec à toutes les molécules du traitement antirétroviral en cours, caractérisé spécifiquement par la présence de la mutation M46MI associée à la résistance de faible degré aux IP/r (ATV/r et LPV/r) ; 
et des mutations associées à la résistance de degrés variables aux INTIs et de degré élevé aux INNTIs de première génération (EFV et NVP) y compris DOR. Toutefois, l’AZT garde une bonne efficacité résiduelle et et TDF une efficacité partielle 
(tous deux favorisés par la mutation M184V). Par ailleurs, prenant en compte l’évolution lente du virus (une seule mutation majeure additionnelle par rapport au génotype de 2000), ainsi que l’exposition relativement courte sous TLD suggère 
une efficacité préservée du DTG, sous réserve de la confirmation par séquençage de la région d’intégrase.
Au regard de l’efficacité totale du DRV/r, de la bonne efficacité résiduelle de l’ATV/r, du LPV/r et de l’AZT, et de l’efficacité partielle du TDF et ABC, dans un contexte de virémie modérée (de l’ordre de 3 Log), un changement rapide de la thérapie est nécessaire, 
prenant en compte TDF*+3TC+DTG (préférentiellement) ou TDF*+3TC+DRV/r (alternativement).
* En cas d’usage de l’AZT (molécule ayant une bonne efficacité résiduelle contre le VIH), la présence du TDF reste indispensable dans la prise en charge du patient (pour le traitement de l’hépatite B). 
NB : Bien qu’inefficace, la présence du 3TC permet de maintenir la mutation M184V qui à son tour favorise l’efficacité du TDF tout en inhibant la réplication virale. 
Insister sur l’importance de l’observance pour la réussite du traitement, évaluer la virémie plasmatique à 12 semaines pour s’assurer de l’atteinte d’une charge virale indétectable, et ensuite continuer le suivi virologique annuel selon les directives nationales. 
Une actualisation des taux de lymphocytes T CD4 serait bénéfique pour la prévention/surveillance des risques d’émergence des maladies opportunistes. 

"""

template_0 = """Voici la réponse à améliorer : {reponse1}
Système : {system_prompt}
Utilisateur : {user_prompt}
Améliore la réponse en te basant sur les informations précédentes:
Utilise le même vocabulaire que le {calque} mais en l'adaptant aux données du patient
et commence ta réponsse par: " Cadre virologique compatible ou incompatible ..."
Ne repète jamais le prompt dans ta réponse.
Réponse :
"""
prompt_0 = ChatPromptTemplate.from_template(template_0)

# === 2) Initialisation Ollama ===
model_ollama = OllamaLLM(model='phi4')
chain0 = prompt_0 | model_ollama

# === 3) Gestion mémoire ===
def liberer_ram():
    """Libère la mémoire RAM avant une opération critique"""
    process = psutil.Process(os.getpid())
    mem_avant = process.memory_info().rss / 1024 / 1024  # MB
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except:
            pass
    mem_apres = process.memory_info().rss / 1024 / 1024
    print(f"📊 Mémoire libérée: {mem_avant - mem_apres:.1f} MB")

def cleanup_memory():
    """Nettoyer la mémoire GPU/MPS et RAM"""
    gc.collect()
    if device == "cuda":
        try:
            torch.cuda.empty_cache()
            print("✅ Mémoire CUDA nettoyée")
        except RuntimeError as e:
            print(f"⚠️ Impossible de vider le cache CUDA: {e}")
    elif device == "mps":
        try:
            torch.mps.empty_cache()
            print("✅ Mémoire MPS nettoyée")
        except:
            print("⚠️ Impossible de vider le cache MPS")

# === 4) Mémoire conversationnelle ===
def read_memory():
    """Lit le contenu du fichier mémoire"""
    if not os.path.exists(MEMORY_FILE):
        return ""
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return f.read()

def append_memory(user_msg, model_resp):
    """Ajoute l'interaction au fichier mémoire"""
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"\nUSER: {user_msg}\nMODEL: {model_resp}\n")


# === 5) Génération avec amélioration Ollama ===
def generate_model_ollama_response(response1, user_msg: str):
    """Améliore la réponse brute avec Ollama en respectant le calque"""
    try:
        cleanup_memory()
        memory_context = read_memory()

        # Génération principale avec modèle local si pas fourni
        if not response1:
            response1 = "Génère toi même tout le rapport"
        user_prompt_with_memory = f"{memory_context}\n{user_msg}"

        # Amélioration avec Ollama
        print("🔄 Amélioration avec Ollama...")
        liberer_ram()
        result = chain0.invoke({
            "reponse1": response1,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt_with_memory,
            "calque": calque,
        })

        # Normalisation en string
        if not isinstance(result, str):
            result = str(result)

        append_memory(user_msg, result)
        cleanup_memory()

        return result

    except Exception as e:
        print(f"Erreur lors de l'amélioration de réponse : {e}")
        liberer_ram()
        cleanup_memory()
        # Retourner la réponse originale sans amélioration
        return response1 if 'response1' in locals() else "Je suis désolé, il y a eu une erreur."
