"""COCO segmentation dataset adapter for the local Matterport Mask R-CNN runtime."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import skimage.draw
import skimage.io

from bubble_analyser.mrcnn import utils


def find_coco_annotation_file(split_dir: Path) -> Path:
    candidates = sorted(split_dir.glob("*annotations*.json")) + sorted(split_dir.glob("*.coco.json"))
    if not candidates:
        raise FileNotFoundError(f"No COCO annotation file found in {split_dir}")
    return candidates[0]


def locate_image(split_dir: Path, file_name: str) -> Path:
    candidates = [
        split_dir / file_name,
        split_dir / "images" / file_name,
        split_dir.parent / file_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(split_dir.rglob(Path(file_name).name))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Could not find image {file_name} under {split_dir}")


def decode_coco_rle(segmentation: dict[str, Any]) -> np.ndarray:
    """Decode COCO RLE, including the compressed ASCII form Roboflow exports."""
    height, width = segmentation["size"]
    counts = segmentation["counts"]
    if isinstance(counts, str):
        decoded_counts: list[int] = []
        index = 0
        while index < len(counts):
            x = 0
            shift = 0
            more = True
            while more:
                c = ord(counts[index]) - 48
                index += 1
                x |= (c & 0x1F) << shift
                more = (c & 0x20) != 0
                shift += 5
                if not more and (c & 0x10):
                    x |= -1 << shift
            if len(decoded_counts) > 2:
                x += decoded_counts[-2]
            decoded_counts.append(x)
        counts = decoded_counts

    values = np.arange(len(counts), dtype=np.uint8) % 2
    flat = np.repeat(values, np.asarray(counts, dtype=np.int64))
    expected = int(height) * int(width)
    if flat.size < expected:
        flat = np.pad(flat, (0, expected - flat.size))
    elif flat.size > expected:
        flat = flat[:expected]
    return flat.reshape((int(height), int(width)), order="F").astype(bool)


class BubbleCocoDataset(utils.Dataset):
    """Roboflow COCO polygon segmentation dataset for bubble-only fine-tuning."""

    def load_bubble_coco(self, dataset_dir: str | Path, split: str = "train") -> None:
        dataset_dir = Path(dataset_dir)
        split_dir = dataset_dir / split
        if not split_dir.exists():
            raise FileNotFoundError(f"Split directory does not exist: {split_dir}")

        annotation_file = find_coco_annotation_file(split_dir)
        coco = json.loads(annotation_file.read_text(encoding="utf-8"))

        # BubMask-Fiji is currently a bubble-only model. Any COCO category in
        # this export is mapped to the single foreground class "bubble".
        self.add_class("bubble", 1, "bubble")

        category_by_id = {
            int(category["id"]): str(category.get("name", "")).strip().lower()
            for category in coco.get("categories", [])
        }
        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in coco.get("annotations", []):
            category_name = category_by_id.get(int(annotation.get("category_id", -1)), "")
            if category_name != "bubble":
                continue
            annotations_by_image[int(annotation["image_id"])].append(annotation)

        for image in coco.get("images", []):
            image_id = int(image["id"])
            image_path = locate_image(split_dir, image["file_name"])
            self.add_image(
                "bubble",
                image_id=f"{split}/{image_id}",
                path=str(image_path),
                width=int(image.get("width", 0)),
                height=int(image.get("height", 0)),
                annotations=annotations_by_image.get(image_id, []),
            )

    def load_mask(self, image_id: int) -> tuple[np.ndarray, np.ndarray]:
        info = self.image_info[image_id]
        height = int(info.get("height") or 0)
        width = int(info.get("width") or 0)
        if height <= 0 or width <= 0:
            image = skimage.io.imread(info["path"])
            height, width = image.shape[:2]

        masks: list[np.ndarray] = []
        for annotation in info.get("annotations", []):
            segmentation = annotation.get("segmentation")
            if isinstance(segmentation, dict):
                instance_mask = decode_coco_rle(segmentation)
            else:
                instance_mask = np.zeros((height, width), dtype=bool)
                if not isinstance(segmentation, list):
                    continue
                for polygon in segmentation:
                    if not isinstance(polygon, list) or len(polygon) < 6:
                        continue
                    xs = np.array(polygon[0::2], dtype=np.float32)
                    ys = np.array(polygon[1::2], dtype=np.float32)
                    rr, cc = skimage.draw.polygon(ys, xs, shape=(height, width))
                    instance_mask[rr, cc] = True
            if instance_mask.any():
                masks.append(instance_mask)

        if not masks:
            return np.empty((height, width, 0), dtype=bool), np.empty((0,), dtype=np.int32)

        mask_array = np.stack(masks, axis=-1).astype(bool)
        class_ids = np.ones((mask_array.shape[-1],), dtype=np.int32)
        return mask_array, class_ids

    def image_reference(self, image_id: int) -> str:
        return self.image_info[image_id]["path"]
