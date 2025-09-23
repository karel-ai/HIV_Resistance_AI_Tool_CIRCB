import os, shutil
import torch
import gc
import psutil
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline, BitsAndBytesConfig
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFacePipeline
from langchain_ollama import OllamaLLM

# === 0) Chemins locaux ===
MERGED_MODEL_PATH = r".\Phi4_merged"

# Prompt systeme
system_prompt = """
Tu es un expert en virologie et infectiologie spécialisé dans la prise en charge du VIH/SIDA.
À partir des mutations génétiques, des scores d'efficacité des antiretroviraux (ARV), et du contexte clinique du patient, génère une interprétation clinique détaillée de 150 mots du génotype, sous forme de rapport médical structuré.
Ton analyse doit comprendre :
1. Un **cadre virologique** expliquant les échecs thérapeutiques passés et les mutations majeures en jeu.
2. Une **analyse des résistances croisées** et des médicaments encore efficaces.
3. Une **proposition de traitement optimisé** selon les ARV disponibles et une proposition d'association de molecules de la forme molecule1+molecule2+molecule3.
4. Un **commentaire sur l'observance** et le **suivi virologique à prévoir**.
Utilise un vocabulaire médical précis, sans faute, et emploie un ton professionnel.
Rédige ta reponse en seul paragraphe.

Ne repète pas sous aucun prétexte le prompt dans la réponse que tu vas générer.
"""

# Format de réponse attendue
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

# Mémoire
MEMORY_FILE = r".\memoire.txt"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write("")

# === 1) Device & dtype ===
device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float16 if device == "cuda" else torch.float32
print(f"[INFO] device={device} | dtype={dtype}")

def cleanup_memory():
    """Nettoyer la mémoire de façon sécurisée"""
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

def liberer_ram():
    """Libère la mémoire RAM avant une opération critique"""
    process = psutil.Process(os.getpid())
    mem_avant = process.memory_info().rss / 1024 / 1024  # MB
    
    # Force le garbage collection
    import gc
    gc.collect()
    
    # Si CUDA est disponible
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except:
            pass
    
    mem_apres = process.memory_info().rss / 1024 / 1024
    print(f"📊 Mémoire libérée: {mem_avant - mem_apres:.1f} MB")

cleanup_memory()

# === 2) Tokenizer ===
try:
    tokenizer = AutoTokenizer.from_pretrained(MERGED_MODEL_PATH, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token if tokenizer.eos_token else "<|endoftext|>"
    print("✅ Tokenizer chargé avec succès")
except Exception as e:
    print(f"❌ Erreur lors du chargement du tokenizer: {e}")
    # Fallback
    from transformers import GPT2Tokenizer
    tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
    tokenizer.pad_token = tokenizer.eos_token

# === 3) Charger le modèle avec meilleure gestion d'erreurs ===
offload_dir = r".\phi4_offload"
shutil.rmtree(offload_dir, ignore_errors=True)
os.makedirs(offload_dir, exist_ok=True)

model = None
try:
    # Essayer sans quantification mais avec gestion mémoire
    print("🔄 Tentative sans quantification...")
    model = AutoModelForCausalLM.from_pretrained(
        MERGED_MODEL_PATH,
        device_map="auto",
        torch_dtype=dtype,
        trust_remote_code=True,
        low_cpu_mem_usage=True
    )
    model.eval()
    print("✅ Modèle chargé sans quantification")
    
except Exception as e:
    print(f"❌ Erreur sans quantification: {e}")
    # Fallback: CPU seulement avec float32
    print("🔄 Tentative sur CPU...")
    model = AutoModelForCausalLM.from_pretrained(
        MERGED_MODEL_PATH,
        device_map="cpu",
        torch_dtype=torch.float32,
        trust_remote_code=True
    )
    model.eval()
    print("✅ Modèle chargé sur CPU")

# === 4) Pipeline HuggingFace avec paramètres optimisés ===
try:
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=812,  # Réduit pour économiser la mémoire
        temperature=0.2,
        do_sample=True,
        device_map="auto",
        batch_size=1,  # Important pour éviter les problèmes mémoire
        pad_token_id=tokenizer.eos_token_id
    )
    hf_llm = HuggingFacePipeline(pipeline=pipe)
    print("✅ Pipeline créé avec succès")
except Exception as e:
    print(f"❌ Erreur lors de la création du pipeline: {e}")
    hf_llm = None

# Templates et chaines (inchangés)
template = """Système : {system_prompt}
Utilisateur : {user_prompt}
Utilise le même vocabulaire que le {calque} mais en l'adaptant aux données du patient
Réponse :
"""

prompt = ChatPromptTemplate.from_template(template)

if hf_llm:
    chain = prompt | hf_llm
    print("✅ Modèle fine-tuné chargé avec succès")
else:
    print("erreur")

# === 5) Mémoire conversationnelle ===
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

# === 6) Génération avec meilleure gestion mémoire ===
def generate_model_response(user_msg: str):
    try:
        cleanup_memory()
        
        memory_context = read_memory()
        user_prompt_with_memory = f"{memory_context}\n{user_msg}"
        
        result = chain.invoke({
            "system_prompt": system_prompt, 
            "user_prompt": user_prompt_with_memory,
            "calque": calque
        })
        
        reponse = result.content if hasattr(result, "content") else str(result)
        final_form = reponse.split("Réponse :")[-1].strip()
        append_memory(user_msg, final_form)
        
        cleanup_memory()
        return final_form
        
    except Exception as e:
        print(f"Erreur lors de la génération de réponse : {e}")
        cleanup_memory()
        return "Je suis désolé, il y a eu une erreur."


