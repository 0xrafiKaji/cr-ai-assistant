import os
import glob
import sqlite3
from datetime import datetime
from typing import List, Dict, Any
from pypdf import PdfReader
from config.settings import settings

class LocalKnowledgeBase:
    def __init__(self, kb_dir: str = settings.KNOWLEDGE_BASE_DIR):
        self.kb_dir = kb_dir
        self.documents: List[Dict[str, str]] = [] # [{title, content, filepath, source}]
        self.load_all()

    def _extract_docx_text(self, fpath: str) -> str:
        """Extract plain text from .docx file using standard library zipfile and XML."""
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(fpath) as z:
                xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            texts = [node.text for node in tree.iter() if node.tag.endswith("t") and node.text]
            return "\n".join(texts).strip()
        except Exception as e:
            print(f"Error reading docx {fpath}: {e}")
            return ""

    def _extract_image_text(self, content: bytes, filename: str) -> str:
        """Extract text / schedule / notice details from images using Gemini Vision."""
        try:
            from core.gemini_brain import gemini_brain
            from PIL import Image
            import io
            if not gemini_brain.gemini_client:
                gemini_brain._init_providers()
            img = Image.open(io.BytesIO(content))
            prompt = (
                "Carefully transcribe all readable text, tables, schedules, notices, dates, times, "
                "course names, and details from this image. Output clean plain text or Markdown."
            )
            extracted = gemini_brain.generate_content_with_fallback([img, prompt])
            if extracted:
                return extracted.strip()
        except Exception as e:
            print(f"Error analyzing image {filename}: {e}")
        return ""

    def load_all(self):
        """Load all documents, images, notes, SQLite Custom QA & Announcements."""
        os.makedirs(self.kb_dir, exist_ok=True)
        self.documents = []

        # 1. Load files from local folder (Any file format supported)
        text_exts = {
            ".txt", ".md", ".json", ".csv", ".tsv", ".log", ".html", ".xml",
            ".py", ".c", ".cpp", ".java", ".js", ".ts", ".sh", ".yaml", ".yml",
            ".ini", ".conf", ".text", ".rtf"
        }

        for fname in os.listdir(self.kb_dir):
            if fname.endswith(".meta.json"):
                continue
            fpath = os.path.join(self.kb_dir, fname)
            if not os.path.isfile(fpath):
                continue

            ext = os.path.splitext(fname)[1].lower()

            # Read companion metadata (user instruction / OCR text / is_active)
            instruction = ""
            extracted_meta_text = ""
            is_active = True
            meta_path = os.path.join(self.kb_dir, f"{fname}.meta.json")
            if os.path.exists(meta_path):
                try:
                    import json
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        mdata = json.load(mf)
                        instruction = mdata.get("instruction", "")
                        extracted_meta_text = mdata.get("extracted_text", "")
                        is_active = mdata.get("is_active", True)
                except Exception:
                    pass

            # If deactivated by CR, skip loading into AI active memory
            if not is_active:
                continue

            doc_text = ""
            source_type = "local_file"

            # A. Text formats
            if ext in text_exts:
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        doc_text = f.read().strip()
                except Exception as e:
                    print(f"Error loading {fpath}: {e}")

            # B. PDF Documents
            elif ext == ".pdf":
                source_type = "local_pdf"
                try:
                    reader = PdfReader(fpath)
                    pages_text = []
                    for p in reader.pages:
                        txt = p.extract_text()
                        if txt:
                            pages_text.append(txt)
                    doc_text = "\n".join(pages_text).strip()
                except Exception as e:
                    print(f"Error reading PDF {fpath}: {e}")

            # C. Word Documents (.docx)
            elif ext in [".docx", ".doc"]:
                source_type = "local_doc"
                doc_text = self._extract_docx_text(fpath)

            # D. Images (.png, .jpg, .jpeg, .webp)
            elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
                source_type = "local_image"
                doc_text = extracted_meta_text

            # E. Fallback for any other file (try reading plain text if printable)
            else:
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        candidate = f.read().strip()
                        if candidate and len([c for c in candidate[:300] if c.isprintable()]) > 200:
                            doc_text = candidate
                except Exception:
                    pass

            # Build enriched document representation with CR instructions
            sections = []
            if instruction:
                sections.append(f"📌 CR Instruction & Topic Guidance for this file:\n{instruction}")
            if doc_text:
                sections.append(f"📄 Document Contents / Extracted Data:\n{doc_text}")
            elif extracted_meta_text:
                sections.append(f"🖼 Visual Content / Notice Data:\n{extracted_meta_text}")

            full_content = "\n\n".join(sections).strip()
            if full_content:
                self.documents.append({
                    "title": f"File: {fname}" + (f" ({instruction[:50]}...)" if instruction else ""),
                    "content": full_content,
                    "filepath": fpath,
                    "source": source_type
                })

        # 2. Custom Q&A from SQLite
        try:
            from core.database import DB_PATH
            if os.path.exists(DB_PATH):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT id, question, answer, keywords FROM custom_qa")
                qas = c.fetchall()
                if qas:
                    qa_lines = [f"Q: {q}\nA: {a} (Keywords: {k})" for _, q, a, k in qas]
                    self.documents.append({
                        "title": "CR Custom Q&A Rules (Direct Administrator Instructions)",
                        "content": "\n\n".join(qa_lines),
                        "filepath": "sqlite://custom_qa",
                        "source": "database_qa"
                    })
                
                # 3. All Broadcasted Announcements Archive (Agent Never Forgets)
                c.execute("""
                    SELECT id, title, content, source, created_at 
                    FROM announcements 
                    WHERE status = 'broadcasted' 
                    ORDER BY id DESC LIMIT 50
                """)
                anns = c.fetchall()
                conn.close()
                if anns:
                    ann_lines = [f"[{dt}] {title} (Source: {src}):\n{content}" for _, title, content, src, dt in anns]
                    self.documents.append({
                        "title": "Historical Batch Announcements Archive (Posted on WhatsApp/Messenger)",
                        "content": "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(ann_lines),
                        "filepath": "sqlite://announcements",
                        "source": "announcements_archive"
                    })
        except Exception as e:
            print(f"Warning: Failed to load DB sources into Knowledge Base: {e}")

    def list_files(self) -> List[Dict[str, Any]]:
        """List all user-uploaded files in the knowledge_base folder, attaching any companion instruction."""
        os.makedirs(self.kb_dir, exist_ok=True)
        file_list = []
        import json
        for fname in os.listdir(self.kb_dir):
            if fname.endswith(".meta.json"):
                continue
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                instruction = ""
                is_active = True
                meta_path = os.path.join(self.kb_dir, f"{fname}.meta.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            mdata = json.load(mf)
                            instruction = mdata.get("instruction", "")
                            is_active = mdata.get("is_active", True)
                    except Exception:
                        pass
                file_list.append({
                    "name": fname,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "extension": os.path.splitext(fname)[1].lower().replace(".", ""),
                    "instruction": instruction,
                    "is_active": is_active
                })
        file_list.sort(key=lambda x: x["name"])
        return file_list

    def add_file(self, filename: str, content: bytes, instruction: Optional[str] = None) -> str:
        """Saves any file into knowledge_base dir, transcribes images if needed, and saves companion metadata."""
        import json
        safe_name = os.path.basename(filename)
        dest = os.path.join(self.kb_dir, safe_name)
        with open(dest, "wb") as f:
            f.write(content)

        meta_data = {
            "filename": safe_name,
            "instruction": instruction.strip() if instruction else "",
            "is_active": True,
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %I:%M %p")
        }

        ext = os.path.splitext(safe_name)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".webp"]:
            extracted_text = self._extract_image_text(content, safe_name)
            if extracted_text:
                meta_data["extracted_text"] = extracted_text

        meta_path = os.path.join(self.kb_dir, f"{safe_name}.meta.json")
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta_data, mf, ensure_ascii=False, indent=2)

        self.load_all()
        return dest

    def toggle_file_active(self, filename: str) -> bool:
        """Toggles the active/deactive status of a knowledge file."""
        import json
        safe_name = os.path.basename(filename)
        dest = os.path.join(self.kb_dir, safe_name)
        if not os.path.exists(dest):
            return False

        meta_path = os.path.join(self.kb_dir, f"{safe_name}.meta.json")
        mdata = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
            except Exception:
                mdata = {}

        current_status = mdata.get("is_active", True)
        new_status = not current_status
        mdata["filename"] = safe_name
        mdata["is_active"] = new_status
        if "instruction" not in mdata:
            mdata["instruction"] = ""

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(mdata, mf, ensure_ascii=False, indent=2)

        self.load_all()
        return new_status

    def delete_file(self, filename: str) -> bool:
        """Deletes a file and its companion metadata from knowledge_base dir."""
        safe_name = os.path.basename(filename)
        dest = os.path.join(self.kb_dir, safe_name)
        meta_path = os.path.join(self.kb_dir, f"{safe_name}.meta.json")
        deleted = False
        if os.path.exists(dest):
            os.remove(dest)
            deleted = True
        if os.path.exists(meta_path):
            os.remove(meta_path)
            deleted = True
        if deleted:
            self.load_all()
            return True
        return False

    def save_quick_note(self, note_text: str, title: str = "CR Quick Note") -> str:
        """Appends a quick note to quick_notes.md in the knowledge folder."""
        os.makedirs(self.kb_dir, exist_ok=True)
        notes_file = os.path.join(self.kb_dir, "quick_notes.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        entry = f"\n\n### 📝 {title.strip()} ({timestamp})\n{note_text.strip()}\n"
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(entry)
        self.load_all()
        return notes_file

    def list_quick_notes(self) -> List[Dict[str, Any]]:
        """Parses quick_notes.md and returns all entries with their index, title, timestamp, and content."""
        import re
        notes_file = os.path.join(self.kb_dir, "quick_notes.md")
        if not os.path.exists(notes_file):
            return []
        try:
            with open(notes_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            pattern = r"### 📝\s+(.*?)(?:\s+\((\d{4}-\d{2}-\d{2}[^)]*)\))?\n([\s\S]*?)(?=(?:\n### 📝|\Z))"
            matches = list(re.finditer(pattern, content))
            notes = []
            for idx, m in enumerate(matches):
                t = m.group(1).strip()
                ts = m.group(2) or ""
                body = m.group(3).strip()
                notes.append({
                    "id": idx,
                    "title": t,
                    "timestamp": ts,
                    "content": body
                })
            return list(reversed(notes))
        except Exception as e:
            print(f"Error reading quick_notes.md: {e}")
            return []

    def update_quick_note(self, note_id: int, new_title: str, new_content: str) -> bool:
        """Updates a quick note by original index in quick_notes.md."""
        import re
        notes_file = os.path.join(self.kb_dir, "quick_notes.md")
        if not os.path.exists(notes_file):
            return False
        try:
            with open(notes_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            pattern = r"### 📝\s+(.*?)(?:\s+\((\d{4}-\d{2}-\d{2}[^)]*)\))?\n([\s\S]*?)(?=(?:\n### 📝|\Z))"
            matches = list(re.finditer(pattern, content))
            if note_id < 0 or note_id >= len(matches):
                return False

            new_entries = []
            for idx, m in enumerate(matches):
                if idx == note_id:
                    ts = datetime.now().strftime("%Y-%m-%d %I:%M %p")
                    new_entries.append(f"### 📝 {new_title.strip()} ({ts})\n{new_content.strip()}\n")
                else:
                    orig_title = m.group(1).strip()
                    orig_ts = f" ({m.group(2).strip()})" if m.group(2) else ""
                    orig_body = m.group(3).strip()
                    new_entries.append(f"### 📝 {orig_title}{orig_ts}\n{orig_body}\n")

            with open(notes_file, "w", encoding="utf-8") as f:
                f.write("\n\n" + "\n\n".join(new_entries) + "\n")

            self.load_all()
            return True
        except Exception as e:
            print(f"Error updating quick_notes.md: {e}")
            return False

    def delete_quick_note(self, note_id: int) -> bool:
        """Deletes a quick note by original index from quick_notes.md."""
        import re
        notes_file = os.path.join(self.kb_dir, "quick_notes.md")
        if not os.path.exists(notes_file):
            return False
        try:
            with open(notes_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            pattern = r"### 📝\s+(.*?)(?:\s+\((\d{4}-\d{2}-\d{2}[^)]*)\))?\n([\s\S]*?)(?=(?:\n### 📝|\Z))"
            matches = list(re.finditer(pattern, content))
            if note_id < 0 or note_id >= len(matches):
                return False

            new_entries = []
            for idx, m in enumerate(matches):
                if idx == note_id:
                    continue
                orig_title = m.group(1).strip()
                orig_ts = f" ({m.group(2).strip()})" if m.group(2) else ""
                orig_body = m.group(3).strip()
                new_entries.append(f"### 📝 {orig_title}{orig_ts}\n{orig_body}\n")

            with open(notes_file, "w", encoding="utf-8") as f:
                if new_entries:
                    f.write("\n\n" + "\n\n".join(new_entries) + "\n")
                else:
                    f.write("")

            self.load_all()
            return True
        except Exception as e:
            print(f"Error deleting from quick_notes.md: {e}")
            return False

    def update_file_instruction(self, filename: str, instruction: str) -> bool:
        """Updates companion metadata instruction for a file."""
        import json
        safe_name = os.path.basename(filename)
        dest = os.path.join(self.kb_dir, safe_name)
        if not os.path.exists(dest):
            return False
        meta_path = os.path.join(self.kb_dir, f"{safe_name}.meta.json")
        meta_data = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta_data = json.load(mf)
            except Exception:
                pass
        meta_data["filename"] = safe_name
        meta_data["instruction"] = instruction.strip()
        if "is_active" not in meta_data:
            meta_data["is_active"] = True
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta_data, mf, indent=2, ensure_ascii=False)
        self.load_all()
        return True

    def search(self, query: str, top_k: int = 4) -> str:
        """Keyword and token scoring retrieval across loaded documents."""
        if not self.documents:
            return ""

        words = [w.lower().strip(" .,!?:;`'\"") for w in query.split() if len(w.strip()) >= 2]
        if not words:
            return ""

        scored_docs = []
        for doc in self.documents:
            content_lower = doc["content"].lower()
            score = 0
            for w in words:
                cnt = content_lower.count(w)
                if cnt > 0:
                    score += cnt * (3 if w in doc["title"].lower() else 1)
            
            # Bonus if phrase in document
            if query.lower() in content_lower:
                score += 10

            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored_docs[:top_k]

        if not top_docs:
            return ""

        context_snippets = []
        for score, doc in top_docs:
            snippet = doc["content"][:1500]
            context_snippets.append(f"--- Document: {doc['title']} ---\n{snippet}")

        return "\n\n".join(context_snippets)

knowledge_base = LocalKnowledgeBase()
