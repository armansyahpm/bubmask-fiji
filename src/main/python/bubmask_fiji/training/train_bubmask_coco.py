"""Fine-tune BubMask Mask R-CNN from a Roboflow COCO segmentation export.

This is intentionally conservative: it expects one foreground class, "bubble",
and writes checkpoints into a separate training run directory. Use a short
smoke run first before committing to a long GPU/overnight job.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ["BUBMASK_TRAINING_GRAPH_MODE"] = "1"

import tensorflow as tf
from imgaug import augmenters as iaa

# Matterport Mask R-CNN was written for graph-mode Keras. Inference can run in
# the current eager-friendly runtime, but training is more reliable when the
# graph is built before Keras loss registration.
tf.compat.v1.disable_eager_execution()

try:
    from tensorflow.python.trackable import data_structures as tf_data_structures

    tf_data_structures.ListWrapper.__hash__ = object.__hash__
    tf_data_structures._DictWrapper.__hash__ = object.__hash__
except Exception:
    # Compatibility shim only. If TensorFlow internals change, normal training
    # errors will still surface later with the original stack trace.
    pass

from bubble_analyser.bubble.bubble import BubbleConfig
from bubble_analyser.mrcnn import model as modellib
from bubmask_fiji.training.coco_dataset import BubbleCocoDataset


class UNSWBubbleTrainingConfig(BubbleConfig):
    NAME = "bubble_unsw_conservative"
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1
    NUM_CLASSES = 1 + 1
    IMAGE_RESIZE_MODE = "square"
    IMAGE_MIN_DIM = 256
    IMAGE_MAX_DIM = 512
    USE_MINI_MASK = False
    MAX_GT_INSTANCES = 600
    DETECTION_MAX_INSTANCES = 600
    RPN_TRAIN_ANCHORS_PER_IMAGE = 512
    TRAIN_ROIS_PER_IMAGE = 256
    STEPS_PER_EPOCH = 20
    VALIDATION_STEPS = 2
    DETECTION_MIN_CONFIDENCE = 0.6


def load_dataset(dataset_dir: Path, split: str) -> BubbleCocoDataset:
    dataset = BubbleCocoDataset()
    dataset.load_bubble_coco(dataset_dir, split)
    dataset.prepare()
    return dataset


def split_exists(dataset_dir: Path, split: str) -> bool:
    return (dataset_dir / split).exists()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Extracted Roboflow COCO dataset directory")
    parser.add_argument("--weights", required=True, help="Starting .h5 weights")
    parser.add_argument("--logs", default="training_runs", help="Directory for Mask R-CNN logs/checkpoints")
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--val-split", default="valid")
    parser.add_argument("--epochs-heads", type=int, default=2)
    parser.add_argument("--steps-per-epoch", type=int, default=20)
    parser.add_argument("--validation-steps", type=int, default=2)
    parser.add_argument("--learning-rate-scale", type=float, default=0.1)
    parser.add_argument("--no-augmentation", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and datasets without building/training model")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    logs_dir = Path(args.logs)
    weights_path = Path(args.weights)
    if not weights_path.exists():
        raise FileNotFoundError(weights_path)

    config = UNSWBubbleTrainingConfig()
    config.STEPS_PER_EPOCH = args.steps_per_epoch
    config.VALIDATION_STEPS = args.validation_steps
    config.display()

    train_dataset = load_dataset(dataset_dir, args.train_split)
    val_split = args.val_split if split_exists(dataset_dir, args.val_split) else args.train_split
    val_dataset = load_dataset(dataset_dir, val_split)

    if args.dry_run:
        summary = {
            "status": "dry_run_ok",
            "dataset": str(dataset_dir),
            "weights": str(weights_path),
            "train_split": args.train_split,
            "train_images": len(train_dataset.image_ids),
            "val_split": val_split,
            "val_images": len(val_dataset.image_ids),
            "classes": train_dataset.class_names,
            "note": "Model graph was not built and weights were not trained.",
        }
        print(json.dumps(summary, indent=2))
        return

    model = modellib.MaskRCNN(mode="training", config=config, model_dir=str(logs_dir))
    model.load_weights(str(weights_path), by_name=True)

    augmentation = None
    if not args.no_augmentation:
        augmentation = iaa.SomeOf((0, 2), [
            iaa.Fliplr(0.5),
            iaa.Flipud(0.5),
            iaa.Affine(rotate=(-15, 15)),
            iaa.Multiply((0.85, 1.15)),
            iaa.GaussianBlur(sigma=(0.0, 0.8)),
        ])

    run_manifest = {
        "dataset": str(dataset_dir),
        "weights": str(weights_path),
        "logs": str(logs_dir),
        "train_split": args.train_split,
        "val_split": val_split,
        "epochs_heads": args.epochs_heads,
        "steps_per_epoch": args.steps_per_epoch,
        "validation_steps": args.validation_steps,
        "learning_rate": config.LEARNING_RATE * args.learning_rate_scale,
        "classes": ["background", "bubble"],
        "note": "Bubble-only conservative fine-tuning. Unlabelled regions are treated as background.",
    }
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "training_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")

    model.train(
        train_dataset,
        val_dataset,
        learning_rate=config.LEARNING_RATE * args.learning_rate_scale,
        epochs=args.epochs_heads,
        layers="heads",
        augmentation=augmentation,
    )


if __name__ == "__main__":
    main()
