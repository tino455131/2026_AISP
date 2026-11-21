"""Command line: turn one audio file into a Traditional Chinese transcript.

Example (run inside voice_stt):
    python -m stt meeting.wav --speaker 組長 --out-dir transcripts
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from .engine import DEFAULT_MODEL, Engine, EngineConfig
from .output import fmt_ts, write_jsonl, write_markdown
from .postprocess import PostProcessor, make_opencc_converter
from .schema import Segment


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m stt",
        description="Transcribe one audio file to Taiwan Traditional Chinese.",
    )
    p.add_argument("audio", help="audio file (wav / mp3 / m4a / ogg / flac ...)")
    p.add_argument("--out-dir", default="transcripts", help="where to save results")
    p.add_argument("--speaker", help="speaker name (default: the file name)")
    p.add_argument("--session-id", help="recording id (default: file name + time)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="model repo id or folder")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument(
        "--compute-type",
        default="auto",
        choices=["auto", "float16", "int8_float16", "int8"],
        help="int8_float16 uses less GPU memory than float16",
    )
    p.add_argument("--glossary", help="text file, one term per line (# = comment)")
    p.add_argument("--no-opencc", action="store_true", help="skip OpenCC conversion")
    p.add_argument("--quiet", action="store_true", help="don't print each sentence")
    return p


def load_glossary(path: str | None) -> str | None:
    """Read glossary terms and join them into faster-whisper's hotwords string."""
    if not path:
        return None
    terms = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return " ".join(terms) or None


def main(argv: list[str] | None = None) -> int:
    # Windows terminals default to Big5/cp950; force UTF-8 so Chinese prints.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    audio = Path(args.audio)
    if not audio.is_file():
        print(f"找不到音檔：{audio}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    speaker = args.speaker or audio.stem
    session_id = args.session_id or f"{audio.stem}-{datetime.now():%Y%m%d-%H%M%S}"

    cfg = EngineConfig(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        hotwords=load_glossary(args.glossary),
    )
    convert = None if args.no_opencc else make_opencc_converter()

    print(f"載入模型 {cfg.model} ...（第一次會下載約 3 GB）")
    t0 = time.perf_counter()
    engine = Engine(cfg)
    print(f"模型就緒：{engine.device} / {engine.compute_type}（{time.perf_counter() - t0:.1f} 秒）")

    def show(seg: Segment) -> None:
        if not args.quiet:
            print(f"  [{fmt_ts(seg.start)}] {seg.text.strip()}")

    t1 = time.perf_counter()
    segments, duration = engine.transcribe(str(audio), on_segment=show)
    elapsed = time.perf_counter() - t1

    utterances, report = PostProcessor(convert).process(
        segments, session_id=session_id, speaker=speaker, source=audio.name
    )

    jsonl_path = out_dir / f"{audio.stem}.jsonl"
    md_path = out_dir / f"{audio.stem}.md"
    write_jsonl(utterances, jsonl_path)
    write_markdown(
        utterances,
        md_path,
        title=audio.name,
        meta={
            "模型": f"{cfg.model}（{engine.device} / {engine.compute_type}）",
            "產生時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "音檔長度": fmt_ts(duration),
        },
    )

    flagged = sum(1 for u in utterances if u.flags)
    speed = duration / elapsed if elapsed > 0 else 0.0
    print()
    print(f"完成：音檔 {fmt_ts(duration)}，辨識花了 {elapsed:.1f} 秒（{speed:.1f} 倍速）")
    print(f"保留 {report.kept} 句，其中 {flagged} 句標 ⚠️；丟掉 {len(report.dropped)} 句")
    for start, text, reason in report.dropped:
        print(f"  丟掉 [{fmt_ts(start)}] {text!r}（{reason}）")
    print(f"輸出：{jsonl_path}")
    print(f"      {md_path}")
    return 0
