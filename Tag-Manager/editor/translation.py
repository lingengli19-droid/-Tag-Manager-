import os


def load_translations(file_path: str) -> dict:
    translations = {}
    if not os.path.exists(file_path):
        return translations
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            translations[key.strip()] = value.strip()
    return translations
