import os
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

from PIL import Image

from tagger.interrogators.base import Interrogator


@dataclass
class LabelData:
    names: list
    rating: list
    general: list
    artist: list
    character: list
    copyright: list
    meta: list
    quality: list
    model: list


def pil_ensure_rgb(image: Image.Image) -> Image.Image:
    if image.mode not in ["RGB", "RGBA"]:
        image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    return image


def pil_pad_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width == height:
        return image
    new_size = max(width, height)
    new_image = Image.new(image.mode, (new_size, new_size), (255, 255, 255))
    paste_position = ((new_size - width) // 2, (new_size - height) // 2)
    new_image.paste(image, paste_position)
    return new_image


def get_tags(probs, labels: LabelData):
    import numpy as np
    result = {
        "rating": [],
        "general": [],
        "character": [],
        "copyright": [],
        "artist": [],
        "meta": [],
        "quality": [],
        "model": []
    }
    if len(labels.rating) > 0:
        valid_indices = labels.rating[labels.rating < len(probs)]
        if len(valid_indices) > 0:
            rating_probs = probs[valid_indices]
            rating_idx_local = np.argmax(rating_probs)
            rating_idx_global = valid_indices[rating_idx_local]
            result["rating"].append((labels.names[rating_idx_global], float(rating_probs[rating_idx_local])))

    if len(labels.quality) > 0:
        valid_indices = labels.quality[labels.quality < len(probs)]
        if len(valid_indices) > 0:
            quality_probs = probs[valid_indices]
            quality_idx_local = np.argmax(quality_probs)
            quality_idx_global = valid_indices[quality_idx_local]
            result["quality"].append((labels.names[quality_idx_global], float(quality_probs[quality_idx_local])))

    category_map = {
        "general": labels.general,
        "character": labels.character,
        "copyright": labels.copyright,
        "artist": labels.artist,
        "meta": labels.meta,
        "model": labels.model
    }
    for category, indices in category_map.items():
        if len(indices) > 0:
            valid_indices = indices[(indices < len(probs))]
            for idx_local, idx_global in enumerate(valid_indices):
                result[category].append((labels.names[idx_global], float(probs[valid_indices][idx_local])))

    for k in result:
        result[k] = sorted(result[k], key=lambda x: x[1], reverse=True)
    return result


class CLTaggerInterrogator(Interrogator):
    def __init__(
            self,
            name: str,
            model_path='model.onnx',
            tag_mapping_path='tag_mapping.json',
            cache_dir: str = None,
            **kwargs
    ) -> None:
        super().__init__(name)
        self.model_path = model_path
        self.tag_mapping_path = tag_mapping_path
        self.cache_dir = cache_dir
        self.kwargs = kwargs

    def download(self):
        import huggingface_hub
        download_kwargs = dict(self.kwargs)
        download_kwargs['filename'] = self.model_path
        if self.cache_dir:
            download_kwargs['cache_dir'] = self.cache_dir
        model_path = Path(huggingface_hub.hf_hub_download(**download_kwargs))

        download_kwargs['filename'] = self.tag_mapping_path
        tag_mapping_path = Path(huggingface_hub.hf_hub_download(**download_kwargs))
        return model_path, tag_mapping_path

    def load(self) -> None:
        from onnxruntime import InferenceSession

        try:
            import torch
        except ImportError:
            pass

        model_path, tag_mapping_path = self.download()
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        self.model = InferenceSession(str(model_path), providers=providers)
        actual_provider = self.model.get_providers()[0]
        print(f'[{self.name}] 使用 {actual_provider} 进行推理')

        self.tags = self.load_tag_mapping(tag_mapping_path)

    def load_tag_mapping(self, mapping_path):
        import numpy as np
        import json
        with open(mapping_path, 'r', encoding='utf-8') as f:
            tag_mapping_data = json.load(f)
        if isinstance(tag_mapping_data, dict) and "idx_to_tag" in tag_mapping_data:
            idx_to_tag = {int(k): v for k, v in tag_mapping_data["idx_to_tag"].items()}
            tag_to_category = tag_mapping_data["tag_to_category"]
        elif isinstance(tag_mapping_data, dict):
            tag_mapping_data_int_keys = {int(k): v for k, v in tag_mapping_data.items()}
            idx_to_tag = {idx: data['tag'] for idx, data in tag_mapping_data_int_keys.items()}
            tag_to_category = {data['tag']: data['category'] for data in tag_mapping_data_int_keys.values()}
        else:
            raise ValueError("Unsupported tag mapping format")

        names = [None] * (max(idx_to_tag.keys()) + 1)
        rating, general, artist, character, copyright, meta, quality, model_name = [], [], [], [], [], [], [], []
        for idx, tag in idx_to_tag.items():
            if idx >= len(names):
                names.extend([None] * (idx - len(names) + 1))
            names[idx] = tag
            category = tag_to_category.get(tag, 'General')
            idx_int = int(idx)
            if category == 'Rating':
                rating.append(idx_int)
            elif category == 'General':
                general.append(idx_int)
            elif category == 'Artist':
                artist.append(idx_int)
            elif category == 'Character':
                character.append(idx_int)
            elif category == 'Copyright':
                copyright.append(idx_int)
            elif category == 'Meta':
                meta.append(idx_int)
            elif category == 'Quality':
                quality.append(idx_int)
            elif category == 'Model':
                model_name.append(idx_int)

        return LabelData(names=names, rating=np.array(rating, dtype=np.int64), general=np.array(general, dtype=np.int64),
                         artist=np.array(artist, dtype=np.int64), character=np.array(character, dtype=np.int64),
                         copyright=np.array(copyright, dtype=np.int64), meta=np.array(meta, dtype=np.int64),
                         quality=np.array(quality, dtype=np.int64), model=np.array(model_name, dtype=np.int64))

    def preprocess_image(self, image: Image.Image, target_size=(448, 448)):
        import numpy as np
        image = pil_ensure_rgb(image)
        image = pil_pad_square(image)
        image_resized = image.resize(target_size, Image.BICUBIC)
        img_array = np.array(image_resized, dtype=np.float32) / 255.0
        img_array = img_array.transpose(2, 0, 1)
        img_array = img_array[::-1, :, :]
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
        std = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
        img_array = (img_array - mean) / std
        img_array = np.expand_dims(img_array, axis=0)
        return image, img_array

    def interrogate(self, image: Image) -> dict:
        import numpy as np
        if not hasattr(self, 'model') or self.model is None:
            self.load()

        input_name = self.model.get_inputs()[0].name
        output_name = self.model.get_outputs()[0].name

        original_pil_image, input_tensor = self.preprocess_image(image)
        input_tensor = input_tensor.astype(np.float32)
        outputs = self.model.run([output_name], {input_name: input_tensor})[0]

        if np.isnan(outputs).any() or np.isinf(outputs).any():
            outputs = np.nan_to_num(outputs, nan=0.0, posinf=1.0, neginf=0.0)

        def stable_sigmoid(x):
            return 1 / (1 + np.exp(-np.clip(x, -30, 30)))

        probs = stable_sigmoid(outputs[0])
        predictions = get_tags(probs, self.tags)
        return predictions
