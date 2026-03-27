"""
Checkpoint recovery tool for interrupted Graphiti graph builds.

Queries Neo4j for episode nodes already ingested under a 'mirofish_...' group_id,
reconstructs the completed-chunk index set, and writes a checkpoint file so that
`build_graph_async(resume_graph_id=...)` can skip those chunks on the next run.

Usage:
    cd backend
    uv run python recover_checkpoint.py

The script will list all MiroFish graph partitions found in Neo4j and let you
choose which one to recover.  It then writes:
    uploads/graph_checkpoints/{graph_id}.json
"""

import asyncio
import json
import os
import re
import sys

from dotenv import load_dotenv

# Load .env / .env.local from project root
ROOT = os.path.dirname(os.path.dirname(__file__))
for env_file in [".env", ".env.local"]:
    path = os.path.join(ROOT, env_file)
    if os.path.exists(path):
        load_dotenv(path)
        print(f"Loaded {env_file}")

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")

CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), "uploads/graph_checkpoints")


async def find_mirofish_groups(driver) -> list[str]:
    """Return all distinct group_ids that look like MiroFish graph partitions."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic)
        WHERE e.group_id STARTS WITH 'mirofish_'
        RETURN DISTINCT e.group_id AS group_id
        ORDER BY group_id
        """,
        routing_="r",
    )
    return [r["group_id"] for r in records]


async def get_episode_names(driver, group_id: str) -> list[str]:
    """Return the names of all Episodic entries for this group."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic)
        WHERE e.group_id = $group_id
        RETURN e.name AS name, e.created_at AS created_at
        ORDER BY e.created_at
        """,
        group_id=group_id,
        routing_="r",
    )
    return [r["name"] for r in records if r["name"]]


def parse_chunk_indices(episode_names: list[str]) -> list[int]:
    """Extract chunk indices from names like 'doc_chunk_0042_1718000000'."""
    indices = []
    for name in episode_names:
        m = re.match(r"doc_chunk_(\d+)_\d+", name)
        if m:
            indices.append(int(m.group(1)))
    return sorted(set(indices))


async def main():
    from neo4j import AsyncGraphDatabase

    print(f"\nConnecting to Neo4j at {NEO4J_URI} …")
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        await driver.verify_connectivity()
        print("Connected.\n")
    except Exception as e:
        print(f"ERROR: Could not connect to Neo4j: {e}")
        print("Check NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in your .env file.")
        await driver.close()
        sys.exit(1)

    groups = await find_mirofish_groups(driver)

    if not groups:
        print("No MiroFish graph partitions found in Neo4j.")
        print("Make sure the graph build ran at least one chunk before it was interrupted.")
        await driver.close()
        sys.exit(0)

    print("Found the following MiroFish graph partitions:\n")
    for i, g in enumerate(groups):
        episode_names = await get_episode_names(driver, g)
        indices = parse_chunk_indices(episode_names)
        print(f"  [{i}] {g}  —  {len(indices)} chunks ingested "
              f"(indices {min(indices) if indices else '?'}–{max(indices) if indices else '?'})")

    print()
    choice = input("Enter number to recover (or press Enter if there's only one): ").strip()
    if choice == "" and len(groups) == 1:
        choice = "0"
    try:
        idx = int(choice)
        graph_id = groups[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        await driver.close()
        sys.exit(1)

    episode_names = await get_episode_names(driver, graph_id)
    completed = parse_chunk_indices(episode_names)

    if not completed:
        print(f"\nNo doc_chunk_NNNN episodes found for {graph_id}.")
        print("The interrupted build may not have completed any chunks — nothing to recover.")
        await driver.close()
        sys.exit(0)

    total_guess = max(completed) + 1  # conservative lower bound; worker recomputes from text anyway
    print(f"\nRecovered {len(completed)} completed chunk indices for {graph_id}.")
    print(f"Highest chunk index seen: {max(completed)}")

    checkpoint = {
        "graph_id": graph_id,
        "graph_name": "Recovered",
        "total_chunks": total_guess,
        "completed_indices": completed,
        "updated_at": "recovered",
    }

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    out_path = os.path.join(CHECKPOINT_DIR, f"{graph_id}.json")
    with open(out_path, "w") as f:
        json.dump(checkpoint, f, indent=2)

    print(f"\nCheckpoint written to:\n  {out_path}\n")
    print("Next step — resume the build via the API or directly:")
    print(f'\n  graph_builder.build_graph_async(text=<original_text>, ontology={{}}, resume_graph_id="{graph_id}")')
    print("\nThe worker will skip the", len(completed), "completed chunks and process only the remainder.")

    await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
