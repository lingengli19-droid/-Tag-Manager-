import os
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image

from tagger.interrogators.base import Interrogator
from tagger import dbimutils


class WaifuDiffusionInterrogator(Interrogator):
    def __init__(
            self,
            name: str,
            model_path='model.onnx',
            tags_path='selected_tags.csv',
            cache_dir: str = None,
            **kwargs
    ) -> None:
        super().__init__(name)
        self.model_path = model_path
        self.tags_path = tags_path
        self.cache_dir = cache_dir
        self.kwargs = kwargs

    def download(self) -> Tuple[os.PathLike, os.PathLike]:
        import huggingface_hub
        download_kwargs = dict(self.kwargs)
        download_kwargs['filename'] = self.model_path
        if self.cache_dir:
            download_kwargs['cache_dir'] = self.cache_dir
        model_path = Path(huggingface_hub.hf_hub_download(**download_kwargs))

        download_kwargs['filename'] = self.tags_path
        tags_path = Path(huggingface_hub.hf_hub_download(**download_kwargs))
        return model_path, tags_path

    def load(self) -> None:
        model_path, tags_path = self.download()

        import pandas as pd
        from onnxruntime import InferenceSession

        try:
            import torch
        except ImportError:
            pass

        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        self.model = InferenceSession(str(model_path), providers=providers)
        actual_provider = self.model.get_providers()[0]
        print(f'[{self.name}] 使用 {actual_provider} 进行推理')

        self.tags = pd.read_csv(tags_path)

    def interrogate(self, image: Image) -> Dict[str, List[Tuple[str, float]]]:
        import numpy as np

        if not hasattr(self, 'model') or self.model is None:
            self.load()

        _, height, _, _ = self.model.get_inputs()[0].shape

        image = image.convert('RGBA')
        new_image = Image.new('RGBA', image.size, 'WHITE')
        new_image.paste(image, mask=image)
        image = new_image.convert('RGB')
        image = np.asarray(image)

        image = image[:, :, ::-1]
        image = dbimutils.make_square(image, height)
        image = dbimutils.smart_resize(image, height)
        image = image.astype(np.float32)
        image = np.expand_dims(image, 0)

        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        confidents = self.model.run([label_name], {input_name: image})[0]

        tags = self.tags[:][['name']]
        tags['confidents'] = confidents[0]

        ratings = dict(tags[:4].values)
        tags = dict(tags[4:].values)

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

        for tag, conf in ratings.items():
            result["rating"].append((tag, conf))

        for tag, conf in tags.items():
            result["general"].append((tag, conf))

        return result
