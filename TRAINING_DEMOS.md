# Training demonstrations

Task cards provide a **Training demo** control for LIBERO, RoboTwin, RoboCasa and RoboDojo. Where a reference is available, the player switches between the recorded agent episodes and the benchmark's released training data. Demo links use `#benchmark=<benchmark>&task=<task>&view=demo`.

| Benchmark | Gallery tasks | Training videos | Source episode and camera | Playback |
| --- | ---: | ---: | --- | --- |
| LIBERO | 40 | 40 | `demo_0`, agent view | 128 × 128, 20 FPS |
| RoboTwin | 50 | 50 | `demo_clean`, `episode_0000000`, head camera | 320 × 240, 15 FPS |
| RoboCasa365 | 365 | 316 | Human `episode_000000`, left agent view | 256 × 256, 20 FPS |
| RoboDojo | 42 | 34 | `arx_x5`, `episode_0000000`, head camera | 640 × 480, 25 FPS |

The catalog accounts for all 497 tasks: 440 available videos and 57 explicit unavailable records. RoboCasa v1.0 provides exact-task training data for 316 of its 365 gallery tasks. RoboDojo provides exact matches for all 34 Generalization, Memory, Precision and Long-Horizon tasks. Its eight Open tasks have no matching source in the pinned training release: `align_blocks`, `general_pickup`, `solve_equation`, `stack_blocks_by_language`, `classify_objects_by_language`, `pick_from_conveyor_by_image`, `store_tools_in_toolbox` and `pour_by_language`. The extra dataset folder `dlc` demonstrates spelling “RoboDojo” with letters and is not substituted for an Open task. Existing LIBERO, RoboTwin and RoboCasa records are preserved.

Demonstrations use the source episode's actual instruction. Object variants, layouts and instruction parameters can differ from the evaluation episode for the same task. RoboCasa chooses target human demonstrations when available (50 tasks), followed by pretraining human demonstrations (266 tasks). Episode zero must belong to the source training split. The selected videos show one external camera at its original resolution and recorded frame rate.

The reference clips retain every recorded frame, in order, for the complete selected demonstration. LIBERO images are vertically flipped according to the upstream OpenGL image convention, then encoded with H.264. RoboTwin images are decoded through its official `decode_image_bit` helper, which handles both legacy and tagged RGB images, then encoded with H.264. RoboCasa and RoboDojo H.264 streams are remuxed with MP4 faststart; their encoded image data is preserved. Posters come from the same selected demonstrations.

These reference videos are browsing aids. The evaluation catalog contains 857 scored agent episodes across 497 tasks, and its success statistics use those episodes. The recorded evaluation policy did not receive these demonstrations.

## Sources and provenance

- [LIBERO datasets](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets), revision `f13aa24a3da8c43c7225569f28c562979fa0e35a`.
- [RoboTwin 2.0 datasets](https://huggingface.co/datasets/TianxingChen/RoboTwin2.0), revision `981c92aa34d8f94d4cff47e0d5bc2f7d4e0af042`.
- RoboCasa v1.0's official [dataset registry](https://github.com/robocasa/robocasa/blob/4f8a2980def75a55dff96b990745b83540425f09/robocasa/models/assets/box_links/box_links_ds.json). Each available record links to its exact Box archive and identifies the selected source MP4 and SHA256.
- [RoboDojo official training data](https://huggingface.co/datasets/RoboDojo-Benchmark/RoboDojo/tree/91f76c28d93dd20c5fa46ce6a5a1d96a4f384acd/data/RoboDojo), revision `91f76c28d93dd20c5fa46ce6a5a1d96a4f384acd`. Select `data/RoboDojo/<nativeTaskName>/arx_x5/preview_video/episode_0000000_cam_head.mp4` with exact native casing. The 34 selected source videos total 33,071,153 bytes. Their SHA256 values are checked against the pinned Hugging Face LFS metadata. The actual episode instructions were read from the corresponding HDF5 `instruction` field using bounded HTTP Range requests, without downloading complete HDF5 files, and cross-checked against the released LeRobot metadata.

[data/task-demos.json](data/task-demos.json) contains exact task/source mappings, original episode IDs, instructions, cameras, dimensions, frame counts, frame rates and output SHA256 values. LIBERO, RoboTwin and RoboDojo records identify pinned Hugging Face revisions and source hashes. RoboDojo instruction provenance identifies its separate HDF5 source; that HDF5 hash is the upstream LFS identifier, not a checksum computed from a complete local HDF5 download. Source paths in the public catalog are relative to the dataset.

## Export and validation

LIBERO/RoboTwin exporters require Python with `h5py`, NumPy and OpenCV, plus the RoboTwin checkout for its official image decoder. RoboCasa and RoboDojo exporters require Python 3.11 or newer. All need FFmpeg and ffprobe. The extracted RoboCasa datasets must retain the download receipts used to bind each directory to its official archive. RoboDojo downloads only selected MP4s and resumes verified partial downloads; the full 1.85 TB HDF5 export is unnecessary. Retain its complete pinned file listing and HDF5 instruction receipt in the dataset's `metadata/` directory.

```bash
python scripts/export_training_demos.py \
  --dataset-root /path/to/dataset \
  --robotwin-repo /path/to/RoboTwin \
  --work-dir /path/to/temporary-storage
python3 scripts/export_robocasa_demos.py \
  --dataset-root /path/to/dataset/robocasa/v1.0
python3 scripts/export_robodojo_demos.py \
  --metadata /path/to/dataset/robodojo/metadata/robodojo-RoboDojo-metadata.json \
  --instructions /path/to/dataset/robodojo/metadata/robodojo-training-episode0-instructions.json \
  --dataset-root /path/to/dataset/robodojo
python3 scripts/assemble_training_demos.py
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos --videos
python3 scripts/build_site.py
```

Exporters validate every generated video by full decoding and by comparing frame counts, dimensions and FPS with the selected source. Assembly requires an explicit available/unavailable record for each of the 497 tasks. The gallery validator checks source identity, asset paths, hashes, coverage and the combined Pages media budget. `--videos` includes both evaluation videos and training demos.

Training MP4s and JPEGs live in `media/demos/<benchmark>/` and are included directly in the static Pages build. RoboDojo adds about 35 MB including posters to the existing roughly 250 MB demonstration collection. RoboCasa evaluation rollouts continue to use their existing Release-hosted URLs. RoboDojo demonstration media is included in the repository's Pages build; its public availability depends on the deployment completing successfully.
