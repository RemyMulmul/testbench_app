import os
import json
from datetime import datetime
from PySide6.QtWidgets import QMessageBox, QFileDialog


def save_test_config(metadata: dict, config: dict, json_path: str):
    """Crée un fichier JSON initial avec les paramètres du test."""

    data = {
        "metadata": metadata,
        "config": config
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=4)

def append_results_to_config(results: dict, metadata: dict, folder_path):
    """Ajoute les résultats dans le fichier JSON de config existant."""
    json_path = os.path.join(folder_path, "config.json")

    try:
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
        else:
            data = metadata.copy()

        data["results"] = results
        data["results"]["timestamp"] = datetime.now().isoformat()

        with open(json_path, "w") as f:
            json.dump(data, f, indent=4)

        return True
    except Exception as e:
        print(f"❌ Erreur lors de l’écriture dans le JSON : {e}")
        return False
    

def sanitize_filename(name: str) -> str:
    return name.strip().replace(" ", "_")

def get_default_folder(base_dir: str, metadata: dict) -> str:
    """Construit le nom de dossier par défaut selon les métadonnées"""
    name   = sanitize_filename(metadata.get("name", "test"))
    splint = sanitize_filename(metadata.get("splint", "unknown"))
    date   = sanitize_filename(metadata.get("date", "unknown-date"))
    folder = f"{name}_{splint}_{date}"
    return os.path.join(base_dir, folder)

def ask_user_for_folder(parent, base_dir: str, default_folder: str) -> str:
    """Propose à l'utilisateur de choisir un dossier personnalisé"""

    ret = QMessageBox.question(
        parent,
        "Choix du dossier",
        "Voulez vous joindre ce test à un dossier déjà existant ? (oui si vous voulez mettre flexion/extension ensemble)",
        QMessageBox.Yes | QMessageBox.No
    )

    if ret == QMessageBox.Yes:
        selected = QFileDialog.getExistingDirectory(parent, "Choisir dossier", base_dir)
        return selected if selected else None
    else:
        return check_or_create_test_folder(default_folder)
    
def check_or_create_test_folder(test_name: str):
    """
    Vérifie si un dossier existe déjà. Si oui, propose d’écraser.
    Retourne le chemin du dossier si accepté, sinon None.
    """
    from utils.setting_utils import get_path_from_settings

    base_dir = get_path_from_settings("data_dir")
    test_dir = os.path.join(base_dir, test_name)

    if os.path.exists(test_dir):
        # Demande confirmation
        reply = QMessageBox.question(
            None,
            "Dossier existant",
            f"⚠️ Le dossier '{test_name}' existe déjà.\nVoulez-vous l'écraser ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return None  # Annuler
    else:
        os.makedirs(test_dir)

    return test_dir
    
def make_filename(metadata: dict, suffix: str = "_raw.txt") -> str:
    """
    Construit un nom de fichier à partir des métadonnées,
    avec un suffixe personnalisable.
    """
    name   = metadata.get("name", "test").strip().replace(" ", "_")
    splint = metadata.get("splint", "unknown").strip().replace(" ", "_")
    date   = metadata.get("date", "unknown-date")
    motion = metadata.get("motion", "mvt").strip().lower()

    return f"{name}_{splint}_{date}_{motion}{suffix}"