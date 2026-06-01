"""Create local train/valid/test splits from a single-split COCO export."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Any

from bubmask_fiji.training.coco_dataset import find_coco_annotation_file, locate_image


def _write_split(
    output_dir: Path,
    split: str,
    coco: dict[str, Any],
    images: list[dict[str, Any]],
    annotations_by_image: dict[int, list[dict[str, Any]]],
    source_split_dir: Path,
) -> dict[str, Any]:
    split_dir = output_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)

    image_ids = {int(image["id"]) for image in images}
    annotations = [
        annotation
        for image in images
        for annotation in annotations_by_image.get(int(image["id"]), [])
    ]

    for image in images:
        source_image = locate_image(source_split_dir, image["file_name"])
        shutil.copy2(source_image, split_dir / Path(image["file_name"]).name)
        image["file_name"] = Path(image["file_name"]).name

    split_coco = {
        "info": coco.get("info", {}),
        "licenses": coco.get("licenses", []),
        "categories": coco.get("categories", []),
        "images": images,
        "annotations": annotations,
    }
    (split_dir / "_annotations.coco.json").write_text(json.dumps(split_coco), encoding="utf-8")
    return {"split": split, "images": len(images), "annotations": len(annotations), "image_ids": sorted(image_ids)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Extracted Roboflow dataset containing a train split")
    parser.add_argument("--output", required=True, help="Output directory for local train/valid/test split")
    parser.add_argument("--seed", type=int, default=22)
    parser.add_argument("--train", type=float, default=0.70)
    parser.add_argument("--valid", type=float, default=0.15)
    parser.add_argument("--test", type=float, default=0.15)
    args = parser.parse_args()

    source_dir = Path(args.source)
    source_split_dir = source_dir / "train"
    annotation_file = find_coco_annotation_file(source_split_dir)
    coco = json.loads(annotation_file.read_text(encoding="utf-8"))

    images = list(coco.get("images", []))
    rng = random.Random(args.seed)
    rng.shuffle(images)

    n = len(images)
    n_train = round(n * args.train)
    n_valid = round(n * args.valid)
    train_images = images[:n_train]
    valid_images = images[n_train:n_train + n_valid]
    test_images = images[n_train + n_valid:]

    annotations_by_image: dict[int, list[dict[str, Any]]] = {}
    for annotation in coco.get("annotations", []):
        annotations_by_image.setdefault(int(annotation["image_id"]), []).append(annotation)

    output_dir = Path(args.output)
    if output_dir.exists():
        raise FileExistsError(f"Output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    summary = {
        "source": str(source_dir),
        "output": str(output_dir),
        "seed": args.seed,
        "ratios": {"train": args.train, "valid": args.valid, "test": args.test},
        "splits": [
            _write_split(output_dir, "train", coco, train_images, annotations_by_image, source_split_dir),
            _write_split(output_dir, "valid", coco, valid_images, annotations_by_image, source_split_dir),
            _write_split(output_dir, "test", coco, test_images, annotations_by_image, source_split_dir),
        ],
    }
    (output_dir / "split_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
