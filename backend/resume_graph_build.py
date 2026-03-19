"""
Resume an interrupted Graphiti graph build from its checkpoint.

Usage:
    cd backend
    uv run python resume_graph_build.py

The script reads the checkpoint written by recover_checkpoint.py, resumes
chunk ingestion from where it left off, and updates project.json when done.
"""

import json
import os
import sys
import time

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(__file__))
for env_file in [".env.local", ".env"]:
    path = os.path.join(ROOT, env_file)
    if os.path.exists(path):
        load_dotenv(path, override=True)
        print(f"Loaded {env_file}")
        break

GRAPH_ID    = "mirofish_8eb0f12963514f40"
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "uploads/projects/proj_8c129163089b")
TEXT_FILE   = os.path.join(PROJECT_DIR, "extracted_text.txt")
PROJECT_JSON = os.path.join(PROJECT_DIR, "project.json")
CHUNK_SIZE  = 500
CHUNK_OVERLAP = 50
BATCH_SIZE  = 3


def progress_callback(msg: str, frac: float):
    pct = int(frac * 100)
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    print(f"\r[{bar}] {pct:3d}%  {msg[:60]:<60}", end="", flush=True)


def main():
    print(f"\nResuming graph build for: {GRAPH_ID}")
    print(f"Text file: {TEXT_FILE}\n")

    if not os.path.exists(TEXT_FILE):
        print(f"ERROR: Text file not found: {TEXT_FILE}")
        sys.exit(1)

    text = open(TEXT_FILE, encoding="utf-8").read()
    print(f"Text loaded: {len(text):,} chars")

    # Import after env is loaded so config picks up the right values
    from app.services.text_processor import TextProcessor
    from app.services._backends.graphiti.graph_builder import GraphBuilderService

    chunks = TextProcessor.split_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
    total  = len(chunks)

    # Load checkpoint to show starting position
    ckpt_path = os.path.join(
        os.path.dirname(__file__),
        "uploads/graph_checkpoints",
        f"{GRAPH_ID}.json",
    )
    if os.path.exists(ckpt_path):
        ckpt = json.load(open(ckpt_path))
        done_so_far = len(ckpt.get("completed_indices", []))
        print(f"Checkpoint: {done_so_far}/{total} chunks already done, "
              f"{total - done_so_far} remaining\n")
    else:
        print("No checkpoint found — will start from chunk 0\n")

    svc = GraphBuilderService()

    start = time.time()

    # Drive the build synchronously so we can show live terminal progress.
    # (build_graph_async spins a daemon thread; we replicate the worker inline
    #  so the script stays alive until completion.)

    from app.services._backends.graphiti.graph_builder import _RETRY_MAX, _RETRY_BASE_DELAY, _RETRY_MAX_DELAY
    from graphiti_core.nodes import EpisodeType
    from app.services.graphiti_client import run_async
    from datetime import datetime, timezone

    checkpoint = svc._load_checkpoint(GRAPH_ID)
    skip_indices = set(checkpoint["completed_indices"]) if checkpoint else set()
    completed = set(skip_indices)

    print(f"Starting ingestion — {total - len(completed)} chunks to go …\n")

    try:
        for i, chunk in enumerate(chunks):
            if i in completed:
                continue

            batch_num   = i // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            frac = (i + 1) / total

            progress_callback(
                f"Chunk {i+1}/{total}  (batch {batch_num}/{total_batches})",
                frac,
            )

            ts = int(datetime.now().timestamp())
            last_exc = None

            for attempt in range(_RETRY_MAX + 1):
                try:
                    run_async(svc._graphiti.add_episode(
                        name=f"doc_chunk_{i:04d}_{ts}",
                        episode_body=chunk,
                        source_description="uploaded document",
                        reference_time=datetime.now(timezone.utc),
                        source=EpisodeType.text,
                        group_id=GRAPH_ID,
                    ))
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < _RETRY_MAX:
                        delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                        print(f"\n  Retry {attempt+1}/{_RETRY_MAX} for chunk {i+1} in {delay:.0f}s: {e}")
                        time.sleep(delay)

            if last_exc is not None:
                svc._save_checkpoint(GRAPH_ID, completed, total, "Resumed")
                print(f"\n\nERROR: Chunk {i+1} failed after {_RETRY_MAX} retries: {last_exc}")
                print(f"Progress saved — rerun this script to continue from chunk {i+1}.")
                sys.exit(1)

            completed.add(i)
            svc._save_checkpoint(GRAPH_ID, completed, total, "Resumed")
            time.sleep(0.5)

    except KeyboardInterrupt:
        svc._save_checkpoint(GRAPH_ID, completed, total, "Resumed")
        elapsed = time.time() - start
        print(f"\n\nInterrupted by user after {elapsed/60:.1f} min.")
        print(f"Progress saved ({len(completed)}/{total} done). Rerun to continue.")
        sys.exit(0)

    elapsed = time.time() - start
    print(f"\n\nAll {total} chunks ingested in {elapsed/60:.1f} min.")

    # Clean up checkpoint
    svc._clear_checkpoint(GRAPH_ID)

    # Update project.json so the frontend can find the graph
    if os.path.exists(PROJECT_JSON):
        proj = json.load(open(PROJECT_JSON))
        proj["graph_id"] = GRAPH_ID
        proj["status"] = "graph_built"
        json.dump(proj, open(PROJECT_JSON, "w"), indent=2)
        print(f"project.json updated with graph_id={GRAPH_ID}")

    print("\nDone. You can now proceed to the simulation step in the UI.")


if __name__ == "__main__":
    main()
