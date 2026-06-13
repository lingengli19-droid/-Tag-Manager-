import os
import re
from collections import OrderedDict
from glob import glob
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, UnidentifiedImageError

from tagger import format
from tagger.interrogators.base import Interrogator
from tagger.interrogators.wd14 import WaifuDiffusionInterrogator
from tagger.interrogators.cl import CLTaggerInterrogator

tag_escape_pattern = re.compile(r'([\\()])')


def create_interrogators(cache_dir: str = None) -> dict:
    return {
        'wd-convnext-v3': WaifuDiffusionInterrogator(
            'wd-convnext-v3',
            repo_id='SmilingWolf/wd-convnext-tagger-v3',
            cache_dir=cache_dir,
        ),
        'wd-swinv2-v3': WaifuDiffusionInterrogator(
            'wd-swinv2-v3',
            repo_id='SmilingWolf/wd-swinv2-tagger-v3',
            cache_dir=cache_dir,
        ),
        'wd-vit-v3': WaifuDiffusionInterrogator(
            'wd-vit-v3',
            repo_id='SmilingWolf/wd-vit-tagger-v3',
            cache_dir=cache_dir,
        ),
        'wd14-convnextv2-v2': WaifuDiffusionInterrogator(
            'wd14-convnextv2-v2', repo_id='SmilingWolf/wd-v1-4-convnextv2-tagger-v2',
            revision='v2.0', cache_dir=cache_dir,
        ),
        'wd14-swinv2-v2': WaifuDiffusionInterrogator(
            'wd14-swinv2-v2', repo_id='SmilingWolf/wd-v1-4-swinv2-tagger-v2',
            revision='v2.0', cache_dir=cache_dir,
        ),
        'wd14-vit-v2': WaifuDiffusionInterrogator(
            'wd14-vit-v2', repo_id='SmilingWolf/wd-v1-4-vit-tagger-v2',
            revision='v2.0', cache_dir=cache_dir,
        ),
        'wd14-moat-v2': WaifuDiffusionInterrogator(
            'wd14-moat-v2',
            repo_id='SmilingWolf/wd-v1-4-moat-tagger-v2',
            revision='v2.0', cache_dir=cache_dir,
        ),
        'wd-eva02-large-tagger-v3': WaifuDiffusionInterrogator(
            'wd-eva02-large-tagger-v3',
            repo_id='SmilingWolf/wd-eva02-large-tagger-v3',
            cache_dir=cache_dir,
        ),
        'wd-vit-large-tagger-v3': WaifuDiffusionInterrogator(
            'wd-vit-large-tagger-v3',
            repo_id='SmilingWolf/wd-vit-large-tagger-v3',
            cache_dir=cache_dir,
        ),
        'cl_tagger_1_01': CLTaggerInterrogator(
            'cl_tagger_1_01',
            repo_id='cella110n/cl_tagger',
            model_path='cl_tagger_1_01/model.onnx',
            tag_mapping_path='cl_tagger_1_01/tag_mapping.json',
            cache_dir=cache_dir,
        ),
    }


def split_str(s: str, separator=',') -> List[str]:
    return [x.strip() for x in s.split(separator) if x]


def check_dependencies() -> list:
    missing = []
    for mod, pkg in [
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('huggingface_hub', 'huggingface_hub'),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    has_onnx = False
    try:
        __import__('onnxruntime')
        has_onnx = True
    except ImportError:
        pass
    if not has_onnx:
        missing.append('onnxruntime (或 onnxruntime-gpu 用于 GPU 加速)')

    return missing


def run_interrogate(
        image_dir: str,
        recursive: bool,
        interrogator: Interrogator,
        threshold: float,
        character_threshold: float,
        add_rating_tag: bool,
        add_model_tag: bool,
        additional_tags: str,
        exclude_tags: str,
        sort_by_alphabetical_order: bool,
        add_confident_as_weight: bool,
        replace_underscore: bool,
        escape_tag: bool,
        progress_callback=None,
        log_callback=None,
        cancel_check=None,
):
    def log(msg):
        if log_callback:
            log_callback(msg)

    postprocess_opts = (
        threshold,
        character_threshold,
        add_rating_tag,
        add_model_tag,
        split_str(additional_tags),
        split_str(exclude_tags),
        sort_by_alphabetical_order,
        add_confident_as_weight,
        replace_underscore,
        [],
        escape_tag
    )

    supported_extensions = [
        e for e, f in Image.registered_extensions().items()
        if f in Image.OPEN
    ]

    pattern = os.path.join(image_dir, '**', '*') if recursive else os.path.join(image_dir, '*')
    paths = sorted([
        Path(p) for p in glob(pattern, recursive=recursive)
        if os.path.splitext(p)[1].lower() in supported_extensions
    ])

    total = len(paths)
    log(f'找到 {total} 张图片')

    if total == 0:
        log('没有找到支持的图片文件')
        return 0

    success_count = 0
    for idx, path in enumerate(paths):
        if cancel_check and cancel_check():
            log('标注已取消')
            break

        try:
            image = Image.open(path)
        except UnidentifiedImageError:
            log(f'跳过不支持的图片: {path}')
            continue

        tags = interrogator.interrogate(image)
        processed_tags = Interrogator.postprocess_tags(tags, *postprocess_opts)
        plain_tags = ', '.join(processed_tags.keys())

        output_path = path.with_suffix('.txt')
        output_path.write_text(plain_tags, encoding='utf-8')

        log(f'[{idx + 1}/{total}] {path.name}: {len(processed_tags)} 个标签')
        success_count += 1

        if progress_callback:
            progress_callback(idx + 1, total)

    log(f'完成！共处理 {success_count}/{total} 张图片')
    return success_count
