import os
import csv
import bisect


class TagDatabase:
    def __init__(self):
        self.tags = []
        self.tag_lower_map = {}
        self.aliases_map = {}
        self.loaded = False

    def load_csv(self, csv_path: str):
        if not os.path.exists(csv_path):
            return
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 1:
                    tag = row[0].strip().strip('"')
                    if tag and tag not in self.tag_lower_map:
                        lower = tag.lower()
                        self.tags.append(tag)
                        self.tag_lower_map[lower] = tag
        self.loaded = True

    def load_all(self, data_dir: str):
        for csv_name in ['danbooru.csv', 'e621.csv', 'quality.txt']:
            path = os.path.join(data_dir, csv_name)
            if csv_name == 'quality.txt':
                self._load_quality(path)
            else:
                self.load_csv(path)
        self.tags.sort(key=str.lower)
        self.loaded = True

    def _load_quality(self, path: str):
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                tag = line.strip()
                if tag and tag not in self.tag_lower_map:
                    self.tags.append(tag)
                    self.tag_lower_map[tag.lower()] = tag

    def search(self, prefix: str, limit: int = 20) -> list:
        if not prefix:
            return []
        prefix_lower = prefix.lower()
        result = []
        for tag in self.tags:
            if tag.lower().startswith(prefix_lower):
                result.append(tag)
                if len(result) >= limit:
                    break
        return result

    def search_with_priority(self, prefix: str, limit: int = 20) -> list:
        if not prefix:
            return []
        prefix_lower = prefix.lower()
        starts = []
        contains = []
        for tag in self.tags:
            tl = tag.lower()
            if tl.startswith(prefix_lower):
                starts.append(tag)
                if len(starts) >= limit:
                    break
        if len(starts) < limit:
            for tag in self.tags:
                tl = tag.lower()
                if prefix_lower in tl and not tl.startswith(prefix_lower):
                    contains.append(tag)
                    if len(starts) + len(contains) >= limit:
                        break
        return starts + contains[:limit - len(starts)]

    def get_translation_text(self, tag: str, translations: dict) -> str:
        trans = translations.get(tag, '')
        if trans:
            return f'{tag}  ({trans})'
        return tag
