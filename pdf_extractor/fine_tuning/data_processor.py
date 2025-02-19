# pdf_extractor/fine_tuning/data_processor.py

from pathlib import Path
import json
from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

class FineTuningDataProcessor:
    """
    Processes data for fine-tuning OpenAI models with a 2-level caching system:
      1) Each PDF+JSON pair -> one chunk training file in `.cache`
      2) All chunks -> one .jsonl single training file (only rebuilt if chunks are newer)
    """

    @staticmethod
    def extract_pdf_text(pdf_path: Path) -> str:
        """Extract text content from a PDF file."""
        text = ""
        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    text += page.get_text() + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path}: {e}")
            raise

    def build_chunk_for_record(
        self,
        pdf_path: Path,
        json_path: Path,
        cache_dir: Path
    ) -> Optional[Path]:
        """
        Builds or reuses a *training chunk* file (a small JSON) for a single PDF+JSON record.
        
        Returns the path to `.cache/<stem>_training.json`, which contains:
          {
            "messages": [
              {"role": "user", "content": "...pdf text..."},
              {"role": "assistant", "content": "...fields..."}
            ]
          }
        
        (Caching #1): If .cache/<stem>_training.json is already newer than both the PDF and JSON,
                      we reuse it; otherwise we rebuild.
        """
        cache_dir.mkdir(exist_ok=True)
        chunk_path = cache_dir / f"{pdf_path.stem}_training.json"

        # If chunk is already newer than PDF+JSON, reuse it
        if chunk_path.exists():
            chunk_mtime = chunk_path.stat().st_mtime
            pdf_mtime = pdf_path.stat().st_mtime
            json_mtime = json_path.stat().st_mtime
            if chunk_mtime > max(pdf_mtime, json_mtime):
                logger.info(f"Reusing chunk file '{chunk_path.name}' for '{pdf_path.name}'")
                return chunk_path

        # Otherwise, rebuild
        logger.info(f"Building chunk file '{chunk_path.name}' for '{pdf_path.name}'")
        try:
            pdf_text = self.extract_pdf_text(pdf_path)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Construct the single example in chat format
            chunk_example = {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Extract the fields from this document:\n\n{pdf_text}"
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps({"fields": data["fields"]})
                    }
                ]
            }

            # Save the chunk
            with open(chunk_path, "w", encoding="utf-8") as cf:
                json.dump(chunk_example, cf, indent=2)
            return chunk_path

        except Exception as e:
            logger.error(f"Error creating chunk for {pdf_path.name}: {e}")
            return None

    def _existing_single_file(self, training_dir: Path) -> Optional[Path]:
        """
        Returns the existing single training .jsonl file if there is exactly one.
        If multiple exist, we keep the newest and remove older ones. If none exist, returns None.
        """
        single_files = sorted(training_dir.glob("training_*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not single_files:
            return None
        # If multiple, keep only the newest
        for old_file in single_files[:-1]:
            old_file.unlink()
            logger.info(f"Removed older single training file: {old_file.name}")
        return single_files[-1]

    def _all_chunks_newer_than(self, single_file: Path, chunk_files: List[Path]) -> bool:
        """
        Checks if any chunk file is newer than `single_file`.
        If so, we need to rebuild. If not, we can reuse `single_file`.
        """
        if not single_file.exists():
            return True
        single_mtime = single_file.stat().st_mtime
        for c in chunk_files:
            if c.stat().st_mtime > single_mtime:
                return True
        return False

    def prepare_training_data(
        self,
        training_dir: Path
    ) -> Tuple[List[Dict], Optional[Path]]:
        """
        Orchestrates the 2-level caching:
          1) For each PDF+JSON pair, build or reuse a chunk in `.cache/*.json`
          2) Combine all chunk files into one .jsonl single file (only if needed)
        
        Returns (examples_list, single_file_path):
          examples_list: The in-memory list of all chunk data
          single_file_path: The final .jsonl file (or None if error)
        """
        training_dir = Path(training_dir)
        cache_dir = training_dir / ".cache"
        cache_dir.mkdir(exist_ok=True)

        # Step 1: Build or reuse chunk files for each PDF+JSON pair
        chunk_paths = []
        for pdf_path in training_dir.glob("*.pdf"):
            json_path = pdf_path.with_suffix(".json")
            if not json_path.exists():
                logger.warning(f"No matching JSON file for {pdf_path.name}")
                continue
            chunk_file = self.build_chunk_for_record(pdf_path, json_path, cache_dir)
            if chunk_file:
                chunk_paths.append(chunk_file)

        if not chunk_paths:
            logger.error("No chunk files were created. Possibly no valid PDF+JSON pairs.")
            return [], None

        # Step 2: Combine chunk files into a single .jsonl if needed
        single_file = self._existing_single_file(training_dir)  # returns the newest .jsonl or None
        if single_file and not self._all_chunks_newer_than(single_file, chunk_paths):
            # Reuse existing single file
            logger.info(f"Reusing single training file: {single_file.name}")
            # Load it in memory
            all_examples = []
            with open(single_file, "r", encoding="utf-8") as sf:
                for line in sf:
                    if line.strip():
                        all_examples.append(json.loads(line))
            return all_examples, single_file
        else:
            # Build a new single file
            all_examples = []
            for cp in chunk_paths:
                try:
                    example = json.loads(cp.read_text(encoding="utf-8"))
                    all_examples.append(example)
                except Exception as e:
                    logger.error(f"Failed to load chunk {cp.name}: {e}")

            if not all_examples:
                logger.error("All chunk files failed to load. Cannot build single file.")
                return [], None

            # If there's an old single file, remove it (so we end with only one)
            if single_file and single_file.exists():
                single_file.unlink()
                logger.info(f"Removed older single file: {single_file.name}")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_single = training_dir / f"training_{timestamp}.jsonl"
            logger.info(f"Creating new single training file: {new_single.name} with {len(all_examples)} examples")

            try:
                with open(new_single, "w", encoding="utf-8") as out_f:
                    for ex in all_examples:
                        out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to write single training file '{new_single.name}': {e}")
                return [], None

            return all_examples, new_single

