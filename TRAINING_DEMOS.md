# Training demonstrations

Each task card has a **Training demo** control. The player switches between the recorded agent episodes and a reference from the benchmark's released training data. Demo links use `#benchmark=<benchmark>&task=<task>&view=demo`.

| Benchmark | Gallery tasks | Training videos | Source episode and camera | Playback |
| --- | ---: | ---: | --- | --- |
| LIBERO | 40 | 40 | `demo_0`, agent view | 128 × 128, 20 FPS |
| RoboTwin | 50 | 50 | `demo_clean`, `episode_0000000`, head camera | 320 × 240, 15 FPS |
| RoboCasa365 | 365 | 316 | Human `episode_000000`, left agent view | 256 × 256, 20 FPS |

The RoboCasa v1.0 release contains exact-task training data for 316 of the gallery's 365 tasks. The remaining 49 task pages explicitly show that a training demonstration is unavailable. The catalog accounts for every task and records this distinction in its `status` field. All 406 available videos come from the corresponding task's training data.

Demonstrations use the source episode's actual instruction. Object variants, layouts and instruction parameters can differ from the evaluation episode for the same task. RoboCasa chooses target human demonstrations when available (50 tasks), followed by pretraining human demonstrations (266 tasks). Episode zero must belong to the source training split. The selected videos show one external camera at its original resolution and recorded frame rate.

The reference clips retain every recorded frame, in order, for the complete selected demonstration. LIBERO images are vertically flipped according to the upstream OpenGL image convention, then encoded with H.264. RoboTwin images are decoded through its official `decode_image_bit` helper, which handles both legacy and tagged RGB images, then encoded with H.264. RoboCasa H.264 streams are remuxed with MP4 faststart; their encoded image data is preserved. Posters come from the same selected demonstrations.

These reference videos are browsing aids. The evaluation catalog continues to contain 815 scored agent episodes, and its success statistics use those episodes. The recorded evaluation policy did not receive these demonstrations.

## Sources and provenance

- [LIBERO datasets](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets), revision `f13aa24a3da8c43c7225569f28c562979fa0e35a`.
- [RoboTwin 2.0 datasets](https://huggingface.co/datasets/TianxingChen/RoboTwin2.0), revision `981c92aa34d8f94d4cff47e0d5bc2f7d4e0af042`.
- RoboCasa v1.0's official [dataset registry](https://github.com/robocasa/robocasa/blob/4f8a2980def75a55dff96b990745b83540425f09/robocasa/models/assets/box_links/box_links_ds.json). Each available record links to its exact Box archive and identifies the selected source MP4 and SHA256.

[data/task-demos.json](data/task-demos.json) contains exact task/source mappings, original episode IDs, instructions, cameras, dimensions, frame counts, frame rates and output SHA256 values. LIBERO and RoboTwin records additionally identify pinned Hugging Face revisions and source archive/HDF5 hashes. Source paths in the public catalog are relative to the dataset.

## Export and validation

The exporters read previously downloaded official datasets. LIBERO/RoboTwin require Python with `h5py`, NumPy and OpenCV, plus the RoboTwin checkout for its official image decoder. RoboCasa requires Python 3.11 or newer. Both need FFmpeg and ffprobe. The extracted RoboCasa datasets must retain the download receipts used to bind each directory to its official archive.

```bash
python scripts/export_training_demos.py \
  --dataset-root /path/to/dataset \
  --robotwin-repo /path/to/RoboTwin \
  --work-dir /path/to/temporary-storage
python3 scripts/export_robocasa_demos.py \
  --dataset-root /path/to/dataset/robocasa/v1.0
python3 scripts/assemble_training_demos.py
python3 scripts/validate_gallery.py --require-robocasa --require-demos --videos
python3 scripts/build_site.py
```

Exporters validate every generated video by full decoding and by comparing frame counts, dimensions and FPS with the selected source. Assembly requires an explicit available/unavailable record for every gallery task. The gallery validator checks source identity, asset paths, hashes, coverage and the combined Pages media budget. `--videos` includes both evaluation videos and training demos.

Training MP4s and JPEGs live in `media/demos/<benchmark>/` and are included directly in the static Pages build. They add about 250 MB including posters. RoboCasa evaluation rollouts continue to use their existing Release-hosted URLs.
