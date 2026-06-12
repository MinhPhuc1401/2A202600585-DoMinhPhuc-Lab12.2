from __future__ import annotations


def parse_policy_markdown(markdown_text: str) -> list[dict]:
    chunks = []
    lines = markdown_text.splitlines()
    current_h2 = ""
    current_h3 = ""
    current_content = []

    def save_chunk():
        nonlocal current_h2, current_h3, current_content
        if not current_h2:
            return
        text_content = "\n".join(current_content).strip()
        if not text_content:
            return
        if current_h3:
            chunks.append({
                "section_h2": current_h2,
                "section_h3": current_h3,
                "citation": f"{current_h2} > {current_h3}",
                "rendered_text": f"## {current_h2}\n### {current_h3}\n{text_content}"
            })
        else:
            chunks.append({
                "section_h2": current_h2,
                "section_h3": "",
                "citation": current_h2,
                "rendered_text": f"## {current_h2}\n{text_content}"
            })

    for line in lines:
        if line.startswith("## "):
            save_chunk()
            current_h2 = line[3:].strip()
            current_h3 = ""
            current_content = []
        elif line.startswith("### "):
            save_chunk()
            current_h3 = line[4:].strip()
            current_content = []
        else:
            current_content.append(line)
            
    save_chunk()
    return chunks
