import json
import os
import platform
import shutil
import sys
from pathlib import Path

APP_NAME = "SwibraceBench"
SETTINGS_FILENAME = "settings.json"


# ---------- Racines utiles ----------
def get_app_root() -> Path:
    """Racine de l'application :
    - en prod (PyInstaller --onefile): dossier de l'exécutable
    - en dev: dossier parent du package (là où est app.py)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def packaged_data_root() -> Path:
    """Racine des données embarquées (PyInstaller), sinon fallback vers get_app_root."""
    base = Path(getattr(sys, "_MEIPASS", get_app_root()))
    return base


def user_config_base() -> Path:
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / APP_NAME
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        return Path.home() / ".config" / APP_NAME


def user_settings_path() -> Path:
    return user_config_base() / SETTINGS_FILENAME


def sibling_settings_path() -> Path:
    """Chemin du settings.json à côté de l'EXE (ou du script en dev)."""
    return get_app_root() / SETTINGS_FILENAME


def bundled_settings_path() -> Path:
    """Chemin du settings.json embarqué dans le bundle (lecture seule)."""
    return packaged_data_root() / SETTINGS_FILENAME


# ---------- Accès aux ressources (images, etc.) ----------
def resource_path(rel_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel_path
    return get_app_root() / rel_path



# ---------- Settings ----------
def ensure_settings(portable_first: bool = False) -> Path:
    """
    Garantit qu'un settings.json modifiable existe, puis retourne son chemin.
    - portable_first=False (défaut) : copie dans le dossier utilisateur si absent.
    - portable_first=True : préfère créer à côté de l'exécutable si absent.
    """
    sib = sibling_settings_path()
    usr = user_settings_path()
    bnd = bundled_settings_path()

    # Si un settings existe déjà à côté de l'exécutable -> priorité portable.
    if sib.exists():
        return sib

    # Sinon, si le settings utilisateur existe -> on l'utilise.
    if usr.exists():
        return usr

    # Sinon, initialisation à partir du settings embarqué (ou vide si absent).
    if not bnd.exists():
        raise FileNotFoundError(
            f"[❌] {SETTINGS_FILENAME} introuvable dans le bundle : {bnd}"
        )

    target = sib if portable_first else usr
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bnd, target)
    return target


def load_settings(portable_first: bool = False) -> dict:
    path = ensure_settings(portable_first=portable_first)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"[❌] Échec de lecture de {path} : {e}") from e


def save_settings(data: dict, portable_first: bool = False) -> Path:
    """
    Sauvegarde propre : n'essaie jamais d'écrire dans _MEIPASS.
    Écrit dans le fichier résolu par ensure_settings().
    """
    path = ensure_settings(portable_first=portable_first)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def _expand_path(s: str) -> Path:
    """
    Expand ~ and environment variables; keep as Path (does not check existence).
    """
    return Path(os.path.expanduser(os.path.expandvars(s)))

def resolve_path_value(value, base) -> Path:
    """
    Resolve a single path value that may be absolute or relative.
    - absolute -> returned as-is (after ~ and %VARS% expansion)
    - relative -> joined to base (default: app root)
    """
    base = base or get_app_root()
    p = _expand_path(str(value))
    return p if p.is_absolute() else (base / p)

def get_path_from_settings(key: str, settings: dict | None = None,
                           default: str | None = None,
                           base: Path | None = None) -> Path:
    """
    Fetch settings['default_paths'][key] and resolve it to an absolute path.
    If missing, uses `default`. If default is relative, resolves from `base` (app root by default).
    """
    if settings is None:
        settings = load_settings()
    dp = settings.get("default_paths", {})
    val = dp.get(key, default)
    if val is None:
        # return app root as a safe fallback; caller can handle non-existence
        return (base or get_app_root())
    return resolve_path_value(val, base=base)

def icons_dir(settings: dict | None = None) -> Path:
    return get_path_from_settings("icons_dir", settings, default="assets/icons")

def icon_path(name: str, settings: dict | None = None) -> Path:
    """
    Resolve a specific icon file. If `name` is absolute -> as-is.
    If it's just a filename -> join to icons_dir. If it contains directories -> resolve from app root.
    """
    p = _expand_path(name)
    if p.is_absolute():
        return p
    if len(p.parts) == 1:
        return icons_dir(settings) / p.name
    return resolve_path_value(p, base=get_app_root())